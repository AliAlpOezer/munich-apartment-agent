"""Tests for the knowledge-wiki layer — store, deterministic rendering, ingest, lint.

The deterministic pieces (store, pages, stats, lint) run with no LLM. Ingest is tested both without
a router (synthesis preserved) and with a fake router (synthesis written + prior fed back).
"""

from __future__ import annotations

from datetime import date

from apartment_agent.models import FilterConfig, Listing, ListingType
from apartment_agent.wiki import pages
from apartment_agent.wiki.ingest import WikiIngestor
from apartment_agent.wiki.lint import WikiLinter
from apartment_agent.wiki.store import FilesystemWikiStore, district_slug, slugify

TODAY = date(2026, 6, 6)


def make_listing(**overrides) -> Listing:
    base = dict(
        source="wg_gesucht",
        external_id="1",
        url="https://www.wg-gesucht.de/1",
        title="Helles Zimmer",
        price_warm=650.0,
        size_sqm=18.0,
        listing_type=ListingType.WG_ROOM,
        district="Schwabing",
        city="München",
        available_from=date(2026, 10, 1),
    )
    base.update(overrides)
    return Listing(**base)


class FakeRouter:
    """Records calls and returns a canned synthesis string."""

    def __init__(self, reply: str = "Synthesized read."):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system, user, *, tier=None, max_tier=None):
        self.calls.append((system, user))
        return self.reply


# --- slugs ------------------------------------------------------------------
def test_slugify_folds_unicode_and_punctuation():
    assert slugify("München Schwabing!") == "munchen-schwabing"
    assert slugify("   ") == "unknown"


def test_district_slug_prefers_district_then_city():
    assert district_slug(make_listing(district="Schwabing")) == "district-schwabing"
    assert district_slug(make_listing(district=None, city="Garching")) == "district-garching"
    assert district_slug(make_listing(district=None, city=None)) == "district-unknown"


# --- store ------------------------------------------------------------------
def test_store_roundtrip(tmp_path):
    store = FilesystemWikiStore(tmp_path)
    assert store.read("x") is None and not store.exists("x")
    store.write("x", "hello")
    assert store.exists("x") and store.read("x") == "hello\n"
    assert store.list_slugs() == ["x"]


# --- deterministic rendering ------------------------------------------------
def test_stats_table_computes_medians_and_range():
    items = [make_listing(price_warm=600.0, size_sqm=14.0),
             make_listing(price_warm=700.0, size_sqm=20.0)]
    table = pages.stats_table(items)
    assert "listings seen | 2" in table
    assert "650 €" in table              # median of 600/700
    assert "600 €–700 €" in table        # range
    assert "wg_room ×2" in table


def test_section_roundtrip():
    text = pages.section("llm", "synthesis", "the prose")
    assert "BEGIN llm:synthesis" in text and "END llm:synthesis" in text
    assert pages.extract_section(text, "llm", "synthesis") == "the prose"
    assert pages.extract_section(text, "auto", "stats") is None


def test_render_district_page_has_sections_and_links():
    page = pages.render_district_page(
        label="Schwabing", slug="district-schwabing",
        listings=[make_listing()], recent=[make_listing()],
        synthesis="Tight market.", neighbours=["district-garching", "market-overview"],
        updated=TODAY,
    )
    assert "# 📍 Schwabing" in page
    assert pages.extract_section(page, "llm", "synthesis") == "Tight market."
    assert "[[district-garching]]" in page and "[[market-overview]]" in page
    assert "Helles Zimmer" in page
    assert pages.find_wikilinks(page) == {"district-garching", "market-overview"}


def test_render_preferences_from_config():
    page = pages.render_preferences(FilterConfig(), updated=TODAY)
    assert "700 €" in page and "12 m²" in page and "2026-10-01" in page
    assert "[[market-overview]]" in page


# --- ingest -----------------------------------------------------------------
def test_ingest_without_router_writes_pages_and_keeps_placeholder(tmp_path):
    store = FilesystemWikiStore(tmp_path)
    ingestor = WikiIngestor(store, router=None)
    new = [make_listing(external_id="1"), make_listing(external_id="2", district="Garching")]
    written = ingestor.ingest(new, new, filter_cfg=FilterConfig(), updated=TODAY)

    assert set(written) == {"district-schwabing", "district-garching",
                            "market-overview", "preferences"}
    overview = store.read("market-overview")
    assert "Schwabing" in overview and "Garching" in overview
    # no router -> synthesis stays the empty placeholder
    assert pages.extract_section(store.read("district-schwabing"), "llm", "synthesis") \
        == "_no synthesis yet_"


def test_ingest_with_router_writes_synthesis_and_feeds_prior(tmp_path):
    store = FilesystemWikiStore(tmp_path)
    router = FakeRouter(reply="First read.")
    ingestor = WikiIngestor(store, router=router)
    new = [make_listing()]

    ingestor.ingest(new, new, filter_cfg=FilterConfig(), updated=TODAY)
    page = store.read("district-schwabing")
    assert pages.extract_section(page, "llm", "synthesis") == "First read."

    # second run: the prior synthesis must be handed back to the model as context
    router.reply = "Updated read."
    ingestor.ingest(new, new, filter_cfg=FilterConfig(), updated=TODAY)
    district_calls = [u for _, u in router.calls if "District:" in u]
    assert any("First read." in u for u in district_calls)
    assert pages.extract_section(store.read("district-schwabing"), "llm", "synthesis") \
        == "Updated read."


def test_ingest_preserves_prior_synthesis_when_router_disappears(tmp_path):
    store = FilesystemWikiStore(tmp_path)
    new = [make_listing()]
    WikiIngestor(store, router=FakeRouter("Kept.")).ingest(
        new, new, filter_cfg=FilterConfig(), updated=TODAY)
    # re-ingest with no router -> existing prose is retained
    WikiIngestor(store, router=None).ingest(new, new, filter_cfg=FilterConfig(), updated=TODAY)
    assert pages.extract_section(store.read("district-schwabing"), "llm", "synthesis") == "Kept."


# --- lint -------------------------------------------------------------------
def test_lint_clean_after_ingest(tmp_path):
    store = FilesystemWikiStore(tmp_path)
    new = [make_listing()]
    WikiIngestor(store, router=None).ingest(new, new, filter_cfg=FilterConfig(), updated=TODAY)
    report = WikiLinter(store).lint(today=TODAY, corpus=new)
    assert report.ok, [f.message for f in report.findings]


def test_lint_flags_broken_link_orphan_stale_and_gap(tmp_path):
    store = FilesystemWikiStore(tmp_path)
    # an orphan page that links to a non-existent slug and is stale
    store.write("district-old", (
        "# 📍 Old\n\n*Munich district · last updated 2026-01-01*\n\n[[district-ghost]]"
    ))
    report = WikiLinter(store).lint(
        today=TODAY, corpus=[make_listing(district="Neuhausen")], stale_days=14
    )
    kinds = {f.kind for f in report.findings}
    assert {"broken-link", "orphan", "stale", "gap"} <= kinds
    # the gap is the district that has a listing but no page
    assert any(f.kind == "gap" and f.slug == "district-neuhausen" for f in report.findings)


def test_lint_report_renders(tmp_path):
    store = FilesystemWikiStore(tmp_path)
    linter = WikiLinter(store)
    clean = linter.render_report(linter.lint(today=TODAY), today=TODAY)
    assert "No issues found" in clean
