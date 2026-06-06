"""Graph-level tests — the detail node's warm-rent re-filter (C1) and empty-run routing.

Uses a stub adapter, no network / DB / LLM.
"""

from __future__ import annotations

from datetime import date

from apartment_agent.config import Settings
from apartment_agent.graph import Deps, build_graph
from apartment_agent.models import Listing, ListingType, RunResult
from apartment_agent.sources.base import SourceAdapter


class StubSource(SourceAdapter):
    """Returns fixed listings; `fetch_costs` stamps a per-listing warm rent from `warm_by_id`."""

    name = "wg_gesucht"

    def __init__(self, listings, warm_by_id):
        self._listings = listings
        self._warm_by_id = warm_by_id

    def build_search_urls(self, cfg):
        return []

    def fetch(self, url):
        return ""

    def parse(self, html):
        return []

    def search(self, cfg):
        return list(self._listings)

    def fetch_costs(self, listing):
        listing.price_warm = self._warm_by_id.get(listing.external_id)


def _listing(ext_id: str, listed: float) -> Listing:
    return Listing(
        source="wg_gesucht", external_id=ext_id, url=f"http://x/{ext_id}", title=f"L{ext_id}",
        price_listed=listed, size_sqm=18.0, listing_type=ListingType.WG_ROOM,
        district="Schwabing", city="München", available_from=date(2026, 10, 1),
    )


def _deps(adapter, **over):
    s = Settings(dry_run=True, enable_llm_enrich=False, enable_wiki=False, **over)
    return Deps(settings=s, filter_cfg=s.filter_config(), adapters=[adapter])


def test_detail_node_drops_listing_over_warm_cap():
    # both pass the list-level filter on their listed (cold-ish) figure of 650...
    listings = [_listing("a", 650.0), _listing("b", 650.0)]
    # ...but the detail page reveals B's true Warmmiete is 750 (> 700 cap) -> dropped
    adapter = StubSource(listings, warm_by_id={"a": 680.0, "b": 750.0})
    final = build_graph(_deps(adapter)).invoke({"result": RunResult()})
    kept = [x.external_id for x in final["new"]]
    assert kept == ["a"]
    assert final["result"].new == 1


def test_detail_fetch_can_be_disabled():
    listings = [_listing("a", 650.0), _listing("b", 650.0)]
    adapter = StubSource(listings, warm_by_id={"a": 680.0, "b": 750.0})
    final = build_graph(_deps(adapter, enable_detail_fetch=False)).invoke({"result": RunResult()})
    # no detail fetch -> both survive on the listed figure, neither warm rent is resolved
    assert sorted(x.external_id for x in final["new"]) == ["a", "b"]
    assert all(x.price_warm is None for x in final["new"])


def test_empty_scrape_routes_to_end():
    adapter = StubSource([], warm_by_id={})
    final = build_graph(_deps(adapter)).invoke({"result": RunResult()})
    assert final["result"].matched == 0 and final["result"].new == 0
