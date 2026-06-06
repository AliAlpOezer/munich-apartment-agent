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

import random
import re
import time
from datetime import date

from selectolax.parser import HTMLParser, Node

from apartment_agent.models import FilterConfig, Listing, ListingType
from apartment_agent.sources.base import SourceAdapter

BASE = "https://www.wg-gesucht.de"
MUNICH_CITY_ID = 90  # WG-Gesucht's city id for München

# (url-slug, category-code, listing type) — category code is the 2nd number in the URL
_CATEGORIES = {
    ListingType.WG_ROOM: [("wg-zimmer", 0)],
    ListingType.APARTMENT: [("1-zimmer-wohnungen", 1), ("wohnungen", 2)],
}

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
            size = _to_float(bolds[-1].text(strip=True))      # m²
        center = mid.css_first(".col-xs-5.text-center, .text-center")
        if center is not None:
            avail_from, avail_to = _parse_dates(center.text(strip=True))

    return Listing(
        source="wg_gesucht",
        external_id=ext_id,
        url=url,
        title=title or None,
        # The list view shows a single "Miete"; treat it as the warm-rent proxy for
        # filtering. The detail page (optional later fetch) carries the warm/cold split.
        price_warm=price,
        size_sqm=size,
        listing_type=_type_from_href(href),
        city=city,
        district=district,
        address=address,
        available_from=avail_from,
        available_to=avail_to,
        raw={"list_price_text": price_text},
    )


class WgGesuchtAdapter(SourceAdapter):
    name = "wg_gesucht"

    def __init__(self, city_id: int = MUNICH_CITY_ID, request_delay: float = 2.5):
        self.city_id = city_id
        self.request_delay = request_delay

    def build_search_urls(self, cfg: FilterConfig) -> list[str]:
        urls: list[str] = []
        for ltype in cfg.listing_types:
            for slug, cat in _CATEGORIES.get(ltype, []):
                # <slug>-in-Muenchen.<city>.<category>.1.0.html  (page 1)
                urls.append(f"{BASE}/{slug}-in-Muenchen.{self.city_id}.{cat}.1.0.html")
        return urls

    def fetch(self, url: str) -> str:
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

    def parse(self, html: str) -> list[Listing]:
        tree = HTMLParser(html)
        out: list[Listing] = []
        for card in tree.css("div[data-id]"):
            listing = _parse_card(card)
            if listing is not None:
                out.append(listing)
        return out
