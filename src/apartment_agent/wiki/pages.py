"""Deterministic page rendering and section helpers — the code-owned half of the wiki.

No LLM, no I/O: pure functions from listings → markdown, so the wiki's factual content (stats,
listing lists, links) is reproducible and unit-tested. The only model-authored region is the
`llm:synthesis` section, which the caller supplies as a plain string.

Sections are delimited by HTML-comment markers (see WIKI_SCHEMA.md) so an ingest can read back the
prior synthesis and regenerate the deterministic sections in place.
"""

from __future__ import annotations

import re
import statistics
from datetime import date

from apartment_agent.models import FilterConfig, Listing

WIKI_TAG = "apartment-agent:wiki"


def _marker(kind: str, name: str, edge: str) -> str:
    return f"<!-- {edge} {kind}:{name} -->"


def section(kind: str, name: str, body: str) -> str:
    """Wrap `body` in BEGIN/END markers, e.g. section('auto', 'stats', table)."""
    return f"{_marker(kind, name, 'BEGIN')}\n{body.rstrip()}\n{_marker(kind, name, 'END')}"


def extract_section(text: str, kind: str, name: str) -> str | None:
    """Inner text of a marked section, or None if absent. Used to carry prior synthesis forward."""
    begin = re.escape(_marker(kind, name, "BEGIN"))
    end = re.escape(_marker(kind, name, "END"))
    pat = re.compile(begin + r"\n(.*?)\n?" + end, re.S)
    m = pat.search(text)
    return m.group(1).strip() if m else None


_WIKILINK_RE = re.compile(r"\[\[([a-z0-9][a-z0-9-]*)\]\]")


def find_wikilinks(text: str) -> set[str]:
    """All `[[slug]]` targets referenced in a page."""
    return set(_WIKILINK_RE.findall(text))


# --- formatting helpers -----------------------------------------------------
def _eur(value: float | None) -> str:
    return f"{value:.0f} €" if value is not None else "—"


def _sqm(value: float | None) -> str:
    return f"{value:.0f} m²" if value is not None else "—"


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def listing_line(x: Listing) -> str:
    """One listing as a markdown bullet for a 'recent matches' section."""
    title = x.title or "(no title)"
    bits = [_eur(x.effective_warm_rent), _sqm(x.size_sqm), x.listing_type.value]
    if x.available_from:
        bits.append(f"ab {x.available_from.isoformat()}")
    if x.fit_score is not None:
        bits.append(f"fit {x.fit_score}/100")
    return f"- **[{title}]({x.url})** — " + " · ".join(bits)


# --- stats ------------------------------------------------------------------
def stats_table(listings: list[Listing]) -> str:
    """Deterministic stats over a set of listings, as a markdown table."""
    warm = [x.effective_warm_rent for x in listings if x.effective_warm_rent is not None]
    sizes = [x.size_sqm for x in listings if x.size_sqm is not None]
    types: dict[str, int] = {}
    for x in listings:
        types[x.listing_type.value] = types.get(x.listing_type.value, 0) + 1
    type_summary = ", ".join(f"{k} ×{v}" for k, v in sorted(types.items())) or "—"
    rent_range = f"{_eur(min(warm))}–{_eur(max(warm))}" if warm else "—"
    rows = [
        ("listings seen", str(len(listings))),
        ("median warm rent", _eur(_median(warm))),
        ("rent range", rent_range),
        ("median size", _sqm(_median(sizes))),
        ("types", type_summary),
    ]
    body = "| metric | value |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows)
    return body


def _links_section(neighbours: list[str]) -> str:
    targets = [f"[[{n}]]" for n in neighbours]
    return section("auto", "links", " · ".join(targets) if targets else "_no links yet_")


def _header(emoji: str, title: str, slug: str, subtitle: str, updated: date) -> str:
    return (
        f"# {emoji} {title}\n\n"
        f"<!-- {WIKI_TAG} {slug} -->\n"
        f"*{subtitle} · last updated {updated.isoformat()}*"
    )


# --- page renderers ---------------------------------------------------------
def render_district_page(
    *,
    label: str,
    slug: str,
    listings: list[Listing],
    recent: list[Listing],
    synthesis: str,
    neighbours: list[str],
    updated: date,
) -> str:
    """A district page: snapshot stats, recent matches, the LLM 'market read', links.

    `listings` is the full known corpus for the district (drives stats); `recent` is the subset to
    list (newest first, already truncated by the caller); `synthesis` is the model-authored prose
    (may be '' to leave the section empty).
    """
    parts = [
        _header("📍", label, slug, "Munich district", updated),
        "## Snapshot\n" + section("auto", "stats", stats_table(listings)),
        "## Recent matches\n"
        + section("auto", "listings", "\n".join(listing_line(x) for x in recent) or "_none yet_"),
        "## Market read\n" + section("llm", "synthesis", synthesis or "_no synthesis yet_"),
        "## See also\n" + _links_section(neighbours),
    ]
    return "\n\n".join(parts)


def render_market_overview(
    *,
    listings: list[Listing],
    district_slugs: list[str],
    synthesis: str,
    updated: date,
    move_in: date | None = None,
) -> str:
    """City-wide overview: totals, per-district breakdown, the LLM synthesis, links out."""
    by_district: dict[str, list[Listing]] = {}
    for x in listings:
        by_district.setdefault(x.district or x.city or "Unknown", []).append(x)
    breakdown_rows = sorted(by_district.items(), key=lambda kv: len(kv[1]), reverse=True)
    if breakdown_rows:
        lines = ["| district | listings | median warm |", "|---|---|---|"]
        for name, items in breakdown_rows:
            warm = [x.effective_warm_rent for x in items if x.effective_warm_rent is not None]
            lines.append(f"| {name} | {len(items)} | {_eur(_median(warm))} |")
        breakdown = "\n".join(lines)
    else:
        breakdown = "_no listings yet_"

    target = f" · target move-in {move_in.isoformat()}" if move_in else ""
    subtitle = "Munich rental search" + target
    parts = [
        _header("🏙️", "Market overview", "market-overview", subtitle, updated),
        "## Totals\n" + section("auto", "stats", stats_table(listings)),
        "## By district\n" + section("auto", "breakdown", breakdown),
        "## Market read\n" + section("llm", "synthesis", synthesis or "_no synthesis yet_"),
        "## Districts\n" + _links_section(sorted(set(district_slugs))),
    ]
    return "\n\n".join(parts)


def render_preferences(cfg: FilterConfig, *, updated: date) -> str:
    """The search intent, rendered straight from FilterConfig — the 'schema of desires'.

    Fully deterministic for now; a future feedback loop (Telegram 👍/👎) can layer a learned
    `llm:synthesis` section on top without changing this skeleton.
    """
    types = ", ".join(sorted(t.value for t in cfg.listing_types)) or "—"
    areas = ", ".join(cfg.allowed_locations[:6]) + (
        f", +{len(cfg.allowed_locations) - 6} more" if len(cfg.allowed_locations) > 6 else ""
    )
    rows = [
        ("max warm rent", _eur(cfg.max_warm_rent_eur)),
        ("min size", _sqm(cfg.min_size_sqm)),
        ("move-in", cfg.move_in_date.isoformat()),
        ("availability window", f"−{cfg.available_from_before_grace_days}d / "
                                 f"+{cfg.available_from_after_window_days}d around move-in"),
        ("listing types", types),
        ("areas", areas),
    ]
    table = "| preference | value |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows)
    parts = [
        _header("🎯", "Search preferences", "preferences", "what a good match looks like", updated),
        section("auto", "filters", table),
        "## See also\n" + _links_section(["market-overview"]),
    ]
    return "\n\n".join(parts)
