"""Ingest — fold a run's new listings into the wiki.

After each scheduled run the new listings are grouped by district; every affected district page and
the market overview are regenerated from the full corpus (deterministic stats) plus a refreshed
`llm:synthesis` (cheap tier). The preferences page is (re)rendered from config.

The LLM writes prose only. It is given the prior synthesis so it revises rather than restarts, and
the deterministic stats so it never has to invent a number. If no router is configured, prior
synthesis is preserved and the rest of the page still updates.
"""

from __future__ import annotations

import logging
from datetime import date

from apartment_agent.models import FilterConfig, Listing
from apartment_agent.wiki import pages
from apartment_agent.wiki.store import WikiStore, district_label, district_slug

log = logging.getLogger(__name__)

_DISTRICT_SYNTH_SYSTEM = (
    "You maintain a personal wiki for someone hunting an affordable rental in the Munich area. "
    "Given the current stats for ONE district and the newest listings there, write a 2-4 sentence "
    "'market read': how this district looks for their budget, whether matches are scarce or "
    "plentiful, and anything worth acting on. Revise the prior read if given one. Be concrete and "
    "honest; do not restate the raw numbers verbatim. Plain prose, no markdown headings, no "
    "preamble."
)
_OVERVIEW_SYNTH_SYSTEM = (
    "You maintain a personal wiki for someone hunting an affordable rental in the Munich area. "
    "Given city-wide stats and the per-district breakdown, write a 3-5 sentence overview: where "
    "the budget realistically fits, which districts to focus on, and how the search is trending. "
    "Revise the prior overview if given one. Plain prose, no markdown headings, no preamble."
)


class WikiIngestor:
    def __init__(self, store: WikiStore, router=None, *, recent_limit: int = 8):
        self.store = store
        self.router = router
        self.recent_limit = recent_limit

    # -- synthesis (LLM, best-effort) ----------------------------------------
    def _synthesize(self, system: str, prior: str | None, facts: str) -> str:
        """Refresh a synthesis section. Falls back to the prior text on any failure / no router."""
        if self.router is None:
            return prior or ""
        from apartment_agent.llm.router import Tier

        user = (facts if not prior else f"Prior read:\n{prior}\n\n{facts}")
        try:
            text = self.router.complete(system, user, tier=Tier.CHEAP, max_tier=Tier.MEDIUM)
            return text.strip()
        except Exception as e:  # noqa: BLE001 - synthesis is best-effort; keep the old prose
            log.warning("wiki synthesis failed: %s", e)
            return prior or ""

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _recent_first(listings: list[Listing], limit: int) -> list[Listing]:
        def key(x: Listing):
            return (x.available_from or date.min, x.fit_score or -1)

        return sorted(listings, key=key, reverse=True)[:limit]

    @staticmethod
    def _facts_for_district(label: str, corpus: list[Listing], new: list[Listing]) -> str:
        lines = [f"District: {label}", "", "Stats:", pages.stats_table(corpus)]
        lines += ["", "Newest listings:"]
        lines += [pages.listing_line(x) for x in new] or ["(none)"]
        return "\n".join(lines)

    # -- public --------------------------------------------------------------
    def ingest(
        self,
        corpus: list[Listing],
        new: list[Listing],
        *,
        filter_cfg: FilterConfig,
        updated: date,
    ) -> list[str]:
        """Update the wiki for this run. Returns the slugs that were written."""
        by_slug: dict[str, list[Listing]] = {}
        labels: dict[str, str] = {}
        for x in corpus:
            slug = district_slug(x)
            by_slug.setdefault(slug, []).append(x)
            labels.setdefault(slug, district_label(x))

        affected: dict[str, list[Listing]] = {}
        for x in new:
            affected.setdefault(district_slug(x), []).append(x)

        written: list[str] = []
        all_district_slugs = sorted(by_slug)

        # 1. district pages with new listings
        for slug, new_here in affected.items():
            district_corpus = by_slug.get(slug, list(new_here))
            labels.setdefault(slug, district_label(new_here[0]))
            prior = self.store.read(slug)
            prior_synth = pages.extract_section(prior, "llm", "synthesis") if prior else None
            if prior_synth in ("_no synthesis yet_", ""):
                prior_synth = None
            facts = self._facts_for_district(labels[slug], district_corpus, new_here)
            synthesis = self._synthesize(_DISTRICT_SYNTH_SYSTEM, prior_synth, facts)
            neighbours = [s for s in all_district_slugs if s != slug] + [
                "market-overview", "preferences"
            ]
            page = pages.render_district_page(
                label=labels[slug],
                slug=slug,
                listings=district_corpus,
                recent=self._recent_first(district_corpus, self.recent_limit),
                synthesis=synthesis,
                neighbours=neighbours,
                updated=updated,
            )
            self.store.write(slug, page)
            written.append(slug)

        # 2. market overview (only when something new landed)
        if new:
            prior = self.store.read("market-overview")
            prior_synth = pages.extract_section(prior, "llm", "synthesis") if prior else None
            if prior_synth in ("_no synthesis yet_", ""):
                prior_synth = None
            facts = "City-wide stats:\n" + pages.stats_table(corpus)
            synthesis = self._synthesize(_OVERVIEW_SYNTH_SYSTEM, prior_synth, facts)
            page = pages.render_market_overview(
                listings=corpus,
                district_slugs=all_district_slugs,
                synthesis=synthesis,
                updated=updated,
                move_in=filter_cfg.move_in_date,
            )
            self.store.write("market-overview", page)
            written.append("market-overview")

        # 3. preferences (deterministic; refresh so it tracks config drift)
        self.store.write("preferences", pages.render_preferences(filter_cfg, updated=updated))
        written.append("preferences")

        log.info("wiki ingest updated %d page(s): %s", len(written), ", ".join(written))
        return written
