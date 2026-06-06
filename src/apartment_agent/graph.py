"""LangGraph orchestration.

    START → scrape → filter → dedup ──(new?)──► enrich → persist → notify → END
                                     └────(none)─────────────────────────► END

Node logic lives here as closures over `Deps`; the pure filter logic stays in
nodes/filter.py. The LLM is used only in `enrich` (fit-ranking) and escalates per the
ModelRouter; everything else is deterministic.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TypedDict

from pydantic import BaseModel, Field

from apartment_agent.config import Settings
from apartment_agent.db.supabase_client import ListingsDB
from apartment_agent.llm.router import ModelRouter, Tier
from apartment_agent.models import FilterConfig, Listing, RunResult
from apartment_agent.nodes.filter import filter_listings
from apartment_agent.notify.telegram import TelegramNotifier
from apartment_agent.sources.base import SourceAdapter

log = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    raw: list[Listing]
    matched: list[Listing]
    rejected: list[tuple[Listing, list[str]]]
    new: list[Listing]
    result: RunResult


@dataclass
class Deps:
    settings: Settings
    filter_cfg: FilterConfig
    adapters: list[SourceAdapter]
    router: ModelRouter | None = None
    db: ListingsDB | None = None
    notifier: TelegramNotifier | None = None


class ListingAssessment(BaseModel):
    """Structured enrichment output."""

    fit_score: int = Field(ge=0, le=100, description="0-100 how well it fits the search")
    summary: str = Field(description="one concise sentence; mention the standout pro/con")


_ENRICH_SYSTEM = (
    "You help someone relocating to Munich pick rentals. They want an affordable place "
    "(warm rent <= 700€), at least 12 m², available around 1 October 2026, in Munich or a "
    "commutable suburb. Given one listing, rate fit 0-100 (price, size, location, timing) "
    "and write one concise sentence highlighting the main pro or con."
)


def _enrich_user(x: Listing) -> str:
    return (
        f"Title: {x.title}\nType: {x.listing_type.value}\nWarm rent: {x.price_warm}€\n"
        f"Size: {x.size_sqm} m²\nDistrict: {x.district}\nCity: {x.city}\n"
        f"Available: {x.available_from} to {x.available_to}\nURL: {x.url}"
    )


def build_graph(deps: Deps):
    def scrape(state: AgentState) -> dict:
        result = state["result"]
        raw: list[Listing] = []
        for adapter in deps.adapters:
            try:
                raw.extend(adapter.search(deps.filter_cfg))
            except Exception as e:  # noqa: BLE001
                result.errors.append(f"scrape {adapter.name}: {e}")
                log.exception("scrape failed for %s", adapter.name)
        result.scraped = result.parsed = len(raw)
        log.info("scraped %d listings", len(raw))
        return {"raw": raw}

    def filter_node(state: AgentState) -> dict:
        matched, rejected = filter_listings(state.get("raw", []), deps.filter_cfg)
        state["result"].matched = len(matched)
        log.info("matched %d / rejected %d", len(matched), len(rejected))
        return {"matched": matched, "rejected": rejected}

    def dedup(state: AgentState) -> dict:
        matched = state.get("matched", [])
        if deps.settings.dry_run or deps.db is None:
            new = list(matched)
        else:
            by_source: dict[str, list[Listing]] = defaultdict(list)
            for m in matched:
                by_source[m.source].append(m)
            seen: set[tuple[str, str]] = set()
            for source, items in by_source.items():
                try:
                    ids = [i.external_id for i in items]
                    seen |= {(source, e) for e in deps.db.existing_external_ids(source, ids)}
                except Exception as e:  # noqa: BLE001
                    state["result"].errors.append(f"dedup {source}: {e}")
            new = [m for m in matched if (m.source, m.external_id) not in seen]
        state["result"].new = len(new)
        log.info("%d new listings", len(new))
        return {"new": new}

    def enrich(state: AgentState) -> dict:
        new = state.get("new", [])
        if not (deps.settings.enable_llm_enrich and deps.router and not deps.settings.dry_run):
            return {}
        for x in new:
            try:
                a = deps.router.structured(
                    _ENRICH_SYSTEM, _enrich_user(x), ListingAssessment, tier=Tier.MEDIUM
                )
                x.fit_score = max(0, min(100, int(a.fit_score)))
                x.summary = a.summary
            except Exception as e:  # noqa: BLE001
                state["result"].errors.append(f"enrich {x.external_id}: {e}")
        new.sort(key=lambda x: (x.fit_score if x.fit_score is not None else -1), reverse=True)
        return {"new": new}

    def persist(state: AgentState) -> dict:
        if deps.settings.dry_run or deps.db is None:
            return {}
        try:
            deps.db.upsert_listings(state.get("new", []))
        except Exception as e:  # noqa: BLE001
            state["result"].errors.append(f"persist: {e}")
        return {}

    def notify(state: AgentState) -> dict:
        new = state.get("new", [])
        result = state["result"]
        if deps.settings.dry_run or not deps.notifier or not new:
            return {}
        try:
            result.notified = deps.notifier.send_digest(new)
            if deps.db is not None:
                by_source: dict[str, list[str]] = defaultdict(list)
                for x in new:
                    by_source[x.source].append(x.external_id)
                for source, ids in by_source.items():
                    deps.db.mark_notified(source, ids)
        except Exception as e:  # noqa: BLE001
            result.errors.append(f"notify: {e}")
        return {}

    def route_after_dedup(state: AgentState) -> str:
        return "enrich" if state.get("new") else "END"

    from langgraph.graph import END, START, StateGraph

    g = StateGraph(AgentState)
    for name, fn in [
        ("scrape", scrape), ("filter", filter_node), ("dedup", dedup),
        ("enrich", enrich), ("persist", persist), ("notify", notify),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "scrape")
    g.add_edge("scrape", "filter")
    g.add_edge("filter", "dedup")
    g.add_conditional_edges("dedup", route_after_dedup, {"enrich": "enrich", "END": END})
    g.add_edge("enrich", "persist")
    g.add_edge("persist", "notify")
    g.add_edge("notify", END)
    return g.compile()
