"""Heartbeat formatting + scheduled-run heartbeat gating.

No network: a fake notifier records sends; a stub adapter returns fixed listings.
"""

from __future__ import annotations

from datetime import date

from apartment_agent.config import Settings
from apartment_agent.graph import Deps
from apartment_agent.main import _run_graph
from apartment_agent.models import Listing, ListingType, RunResult
from apartment_agent.notify.telegram import format_heartbeat
from apartment_agent.sources.base import SourceAdapter


def test_format_heartbeat_no_errors():
    msg = format_heartbeat(RunResult(scraped=18, matched=12, new=0))
    assert "🟢 No new listings this run" in msg
    assert "scraped 18 · matched 12 · 0 new" in msg


def test_format_heartbeat_with_errors():
    msg = format_heartbeat(RunResult(scraped=0, matched=0, new=0, errors=["scrape: boom"]))
    assert "⚠️ Ran with 1 error(s), no new listings" in msg


class _FakeNotifier:
    def __init__(self):
        self.sent: list[str] = []

    def send(self, text: str) -> int:
        self.sent.append(text)
        return 1


class _StubSource(SourceAdapter):
    name = "wg_gesucht"

    def __init__(self, listings):
        self._listings = listings

    def build_search_urls(self, cfg):
        return []

    def fetch(self, url):
        return ""

    def parse(self, html):
        return []

    def search(self, cfg):
        return list(self._listings)

    def fetch_costs(self, listing):
        listing.price_warm = listing.price_listed


def _listing(ext_id: str, warm: float) -> Listing:
    return Listing(
        source="wg_gesucht", external_id=ext_id, url=f"http://x/{ext_id}", title=f"L{ext_id}",
        price_listed=warm, size_sqm=18.0, listing_type=ListingType.WG_ROOM,
        district="Schwabing", city="München", available_from=date(2026, 10, 1),
    )


def _deps(listings, notifier):
    # not a dry run (so the heartbeat path is live) but no DB / LLM / wiki.
    s = Settings(dry_run=False, enable_llm_enrich=False, enable_wiki=False,
                 enable_checkpointing=False, enable_feedback=False)
    return Deps(settings=s, filter_cfg=s.filter_config(), adapters=[_StubSource(listings)],
                notifier=notifier)


def test_heartbeat_sent_on_empty_run(monkeypatch):
    notifier = _FakeNotifier()
    monkeypatch.setattr("apartment_agent.main._build_deps", lambda s: _deps([], notifier))
    _run_graph(Settings(dry_run=False, enable_wiki=False, enable_checkpointing=False),
               heartbeat_on_empty=True)
    assert len(notifier.sent) == 1
    assert "No new listings" in notifier.sent[0]


def test_no_heartbeat_when_flag_off(monkeypatch):
    notifier = _FakeNotifier()
    monkeypatch.setattr("apartment_agent.main._build_deps", lambda s: _deps([], notifier))
    _run_graph(Settings(dry_run=False, enable_wiki=False, enable_checkpointing=False))
    assert notifier.sent == []
