"""WG-Gesucht adapter.

Fetching uses curl-cffi with Chrome TLS impersonation (plain requests get blocked).
Parsing is deterministic over the search-result cards; selectors were derived from a
captured fixture (tests/fixtures/wg_*.html) and are isolated here so a layout change
only touches this file.

Card anatomy (search results):
  div[data-id]                              -> listing id
    h2.truncate_title a[href]               -> title + detail URL
    div.col-xs-11 span (first, contains '|')-> "<type> | <city> <district> | <street>"
    div.row.middle .col-xs-3 b   (first)    -> price  ("750 €")
                   .col-xs-5.text-center    -> availability ("20.10.2026 - 31.03.2027")
                   .col-xs-3.text-right b    -> size   ("21 m²")
"""

from __future__ import annotations

import logging
import random
import re
import time
from datetime import UTC, date, datetime
from urllib.parse import quote_plus

from selectolax.parser import HTMLParser, Node

from apartment_agent.models import FilterConfig, Listing, ListingType
from apartment_agent.retry import network_retry
from apartment_agent.sources.base import SourceAdapter

log = logging.getLogger(__name__)

BASE = "https://www.wg-gesucht.de"
MUNICH_CITY_ID = 90  # WG-Gesucht's city id for München

_DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
_NUM_RE = re.compile(r"\d[\d.]*(?:,\d+)?")


def _to_float(text: str | None) -> float | None:
    """German-formatted number to float: '1.250' -> 1250.0, '21,5' -> 21.5."""
    if not text:
        return None
    m = _NUM_RE.search(text)
    if not m:
        return None
    raw = m.group(0).replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_dates(text: str | None) -> tuple[date | None, date | None]:
    """'20.10.2026 - 31.03.2027' -> (from, to); single date -> (from, None)."""
    if not text:
        return (None, None)
    dates = [date(int(y), int(mo), int(d)) for d, mo, y in _DATE_RE.findall(text)]
    if not dates:
        return (None, None)  # e.g. "ab sofort" / empty -> available now
    return (dates[0], dates[1] if len(dates) > 1 else None)


def _type_from_href(href: str) -> ListingType:
    if "/wg-zimmer" in href:
        return ListingType.WG_ROOM
    if "/wohnungen" in href or "-zimmer-wohnungen" in href:
        return ListingType.APARTMENT
    return ListingType.UNKNOWN


def _split_detail(text: str) -> tuple[str | None, str | None, str | None]:
    """'3er WG | München Neuhausen | Amortstrasse' -> (city, district, address)."""
    parts = [p.strip() for p in text.split("|")]
    city = district = address = None
    if len(parts) >= 2 and parts[1]:
        toks = parts[1].split(None, 1)
        city = toks[0]
        district = toks[1] if len(toks) > 1 else None
    if len(parts) >= 3:
        address = parts[2] or None
    return (city, district, address)


def _parse_card(card: Node) -> Listing | None:
    ext_id = card.attributes.get("data-id")
    if not ext_id or not ext_id.isdigit():
        return None

    link = card.css_first("h2.truncate_title a") or card.css_first("a[href*='.html']")
    href = (link.attributes.get("href") if link else "") or ""
    title = link.text(strip=True) if link else None
    url = href if href.startswith("http") else f"{BASE}{href}"

    city = district = address = None
    for span in card.css("div.col-xs-11 span"):
        t = span.text(strip=True)
        if "|" in t:
            city, district, address = _split_detail(t)
            break

    mid = card.css_first("div.row.middle")
    price = size = None
    price_text = None
    avail_from = avail_to = None
    if mid is not None:
        bolds = mid.css("b")
        if bolds:
            price_text = bolds[0].text(strip=True)
            price = _to_float(price_text)                     # listed rent
            if price is not None and price < 50:              # "auf Anfrage" / parse noise
                price = None
            size = _to_float(bolds[-1].text(strip=True))      # m²
        center = mid.css_first(".col-xs-5.text-center, .text-center")
        if center is not None:
            avail_from, avail_to = _parse_dates(center.text(strip=True))

    return Listing(
        source="wg_gesucht",
        external_id=ext_id,
        url=url,
        title=title or None,
        # The list card shows one figure of ambiguous basis (usually Kaltmiete). Keep it as
        # `price_listed` for the permissive pre-filter; `fetch_costs` resolves warm/cold from the
        # detail page before the final filter so the warm-rent cap isn't applied to a cold figure.
        price_listed=price,
        size_sqm=size,
        listing_type=_type_from_href(href),
        city=city,
        district=district,
        address=address,
        available_from=avail_from,
        available_to=avail_to,
        raw={"list_price_text": price_text},
    )


# --- detail-page cost parsing -----------------------------------------------
# The detail page lists costs as label/value PAIRS. The value must be read from its own element,
# never as "the first number in the row" — WG-Gesucht wraps everything in Bootstrap `.row` divs,
# so a whole-row text scan concatenates unrelated figures (size, floor, dates) and returns garbage
# (this is the bug that made every stored price wildly wrong). Specific labels are matched before
# the generic "miete", and deposit ("Kaution") / buyout ("Ablöse") rows are dropped.
_COST_KEYS: list[tuple[str, str]] = [
    ("gesamtmiete", "warm"),
    ("warmmiete", "warm"),
    ("kaltmiete", "cold"),
    ("nebenkosten", "extra"),
    ("heizkosten", "extra"),
    ("sonstige kosten", "extra"),
    ("sonstige", "extra"),
    ("miete", "cold"),  # generic base rent — must stay last
]


# A real monthly rent is never a couple euros. Some listers enter a placeholder (e.g. "2 €") in the
# rent field; without a floor that garbage becomes the price AND sneaks the listing past the rent
# cap. Base-rent (warm/cold) values below this are treated as unresolved. Extras (Nebenkosten) are
# exempt — 0 € is legitimate. Mirrors the list-card parser's own `< 50` guard.
_MIN_PLAUSIBLE_RENT_EUR = 50.0


def _classify_cost_label(label: str) -> str | None:
    """Map a cost-row *label* (not the whole row) to warm/cold/extra, or None to ignore."""
    label = label.lower()
    if "kaution" in label or "ablös" in label or "ablos" in label:
        return None  # deposit / buyout — not a monthly rent component
    for sub, key in _COST_KEYS:
        if sub in label:
            return key
    return None


def _panel_pairs(tree: HTMLParser) -> list[tuple[str, float]]:
    """(label, value) pairs from WG-Gesucht's structured cost panels, each value read from its own
    element. Returns [] when the panels aren't present (older layouts / test fixtures)."""
    pairs: list[tuple[str, float]] = []
    # Key facts: Gesamtmiete / Warmmiete appear as a label span + a sibling <b> value.
    for d in tree.css("span.key_fact_detail"):
        par = d.parent
        val = par.css_first("b.key_fact_value, span.key_fact_value") if par else None
        num = _to_float(val.text(strip=True)) if val is not None else None
        if num is not None:
            pairs.append((d.text(strip=True), num))
    # Cost breakdown: label span in one grid column, value span in the sibling column of the .row.
    for lab in tree.css("span.section_panel_detail"):
        row = lab.parent.parent if (lab.parent and lab.parent.parent) else None
        val = row.css_first("span.section_panel_value") if row is not None else None
        num = _to_float(val.text(strip=True)) if val is not None else None
        if num is not None:
            pairs.append((lab.text(strip=True), num))
    return pairs


def _generic_pairs(tree: HTMLParser) -> list[tuple[str, float]]:
    """Fallback for label/value tables without WG-Gesucht's panel classes: per row, take the label
    from the cell that names a cost and the value from a *separate* cell holding a number."""
    pairs: list[tuple[str, float]] = []
    for row in tree.css("tr, div.row, li"):
        label: str | None = None
        value: float | None = None
        for cell in row.css("td, th, div, span"):
            text = cell.text(strip=True)
            if not text:
                continue
            if label is None and _classify_cost_label(text) is not None:
                label = text
                continue
            if value is None:
                num = _to_float(text)
                if num is not None:
                    value = num
        if label is not None and value is not None:
            pairs.append((label, value))
    return pairs


def parse_detail_costs(html: str) -> tuple[float | None, float | None]:
    """Resolve (warm, cold) EUR/month from a WG-Gesucht detail page.

    Reads the cost breakdown as label→value pairs (structured panels first, a generic label/value
    table as fallback); if no explicit Warmmiete/Gesamtmiete is present, derives warm as Kaltmiete +
    the extra-cost rows (Nebenkosten/Heizkosten/Sonstige). Returns (None, None) when no cost rows
    are found, so the caller keeps the permissive list-card figure.
    """
    tree = HTMLParser(html)
    pairs = _panel_pairs(tree) or _generic_pairs(tree)
    warm: float | None = None
    cold: float | None = None
    extras = 0.0
    seen_extra = False
    for label, value in pairs:
        key = _classify_cost_label(label)
        if key in ("warm", "cold") and value < _MIN_PLAUSIBLE_RENT_EUR:
            continue  # implausible base rent (e.g. a placeholder "2 €") — treat as unresolved
        if key == "warm" and warm is None:
            warm = value
        elif key == "cold" and cold is None:
            cold = value
        elif key == "extra":
            extras += value
            seen_extra = True
    if warm is None and cold is not None and seen_extra:
        warm = cold + extras
    return warm, cold


class WgGesuchtAdapter(SourceAdapter):
    name = "wg_gesucht"

    def __init__(self, city_id: int = MUNICH_CITY_ID, request_delay: float = 2.5):
        self.city_id = city_id
        self.request_delay = request_delay

    def build_search_urls(self, cfg: FilterConfig) -> list[str]:
        """One combined search: all 4 categories (WG room, 1-room, flat, house), rent <= cap,
        available from the move-in date onward (WG-Gesucht's `dFr` timestamp), newest first, offers
        only, deactivated hidden. When `cfg.has_radius`, results are constrained to within
        `search_radius_m` of the configured centre (WG-Gesucht's radAdd/radLat/radLng/radDis);
        otherwise the search is city-wide. Size is NOT filtered server-side (the local filter does).
        """
        dfr = int(
            datetime(
                cfg.move_in_date.year, cfg.move_in_date.month, cfg.move_in_date.day, tzinfo=UTC
            ).timestamp()
        )
        rmax = int(cfg.max_warm_rent_eur)
        path = (
            f"{BASE}/wg-zimmer-und-1-zimmer-wohnungen-und-wohnungen-und-haeuser-"
            f"in-Muenchen.{self.city_id}.0+1+2+3.1.0.html"
        )
        params = [
            "categories%5B%5D=0", "categories%5B%5D=1", "categories%5B%5D=2", "categories%5B%5D=3",
            "rent_types%5B%5D=2", "rent_types%5B%5D=1", "rent_types%5B%5D=3",
            f"rent_range=0%2C{rmax}", "min_rent=0", f"max_rent={rmax}",
            "offer_filter=1", f"city_id={self.city_id}",
            "sort_column=3", "sort_order=0", "noDeact=1",
            "rMin=0", f"rMax={rmax}", f"dFr={dfr}",
        ]
        if cfg.has_radius:
            params += [
                f"radAdd={quote_plus(cfg.search_center_label)}",
                f"radLat={cfg.search_center_lat}",
                f"radLng={cfg.search_center_lng}",
                f"radDis={cfg.search_radius_m}",
            ]
        return [f"{path}?{'&'.join(params)}"]

    def fetch(self, url: str) -> str:
        """Fetch a page. Primary path is curl-cffi with Chrome-TLS impersonation; if that fails
        (e.g. the source starts blocking it) fall back to a real headless browser via Playwright,
        when it is installed. Raises the original curl error if no fallback succeeds."""
        try:
            return self._fetch_curl(url)
        except Exception as curl_err:  # noqa: BLE001 - any curl failure warrants the browser try
            log.warning("curl-cffi fetch failed for %s (%s); trying Playwright fallback",
                        url, curl_err)
            html = self._fetch_playwright(url)
            if html is not None:
                return html
            raise

    @network_retry()
    def _fetch_curl(self, url: str) -> str:
        from curl_cffi import requests  # lazy: parsing/tests need no network deps

        time.sleep(self.request_delay + random.uniform(0, 1.5))  # gentle, human-ish pacing
        resp = requests.get(
            url,
            impersonate="chrome",
            headers={
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.text

    def _fetch_playwright(self, url: str) -> str | None:
        """Headless-browser fallback for when curl-cffi is blocked. Returns None when Playwright is
        not installed (the optional `browser` extra) so the caller re-raises the original error.

        Runs the sync Playwright API, which is safe here because scraping happens on worker threads
        (the detail-fetch pool / the dashboard's background run thread), never in an asyncio loop.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.warning(
                "Playwright not installed; skipping browser fallback "
                "(install with: pip install -e '.[browser]' && playwright install chromium)"
            )
            return None

        time.sleep(self.request_delay + random.uniform(0, 1.5))
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    ctx = browser.new_context(
                        locale="de-DE",
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                        ),
                        extra_http_headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.8"},
                    )
                    page = ctx.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    return page.content()
                finally:
                    browser.close()
        except Exception as e:  # noqa: BLE001 - fallback failed too; let caller raise the curl error
            log.warning("Playwright fallback also failed for %s: %s", url, e)
            return None

    def parse(self, html: str) -> list[Listing]:
        tree = HTMLParser(html)
        out: list[Listing] = []
        for card in tree.css("div[data-id]"):
            listing = _parse_card(card)
            if listing is not None:
                out.append(listing)
        return out

    def fetch_costs(self, listing: Listing) -> None:
        """Populate accurate `price_warm`/`price_cold` from the listing's detail page.

        Best-effort and in-place: on any parse miss the listing keeps its list-card `price_listed`,
        so the permissive pre-filter result still stands.
        """
        if not listing.url:
            return
        warm, cold = parse_detail_costs(self.fetch(listing.url))
        if cold is not None:
            listing.price_cold = cold
        if warm is not None:
            listing.price_warm = warm
