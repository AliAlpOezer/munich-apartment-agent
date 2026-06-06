"""LangGraph orchestration.

    START → scrape → filter → dedup ─(new?)─► detail → enrich → persist → wiki → notify → END
                                     └─(none)──────────────────────────────────────────► END

Node logic lives here as closures over `Deps`; the pure filter logic stays in
nodes/filter.py. `detail` fetches each new listing's page to resolve the real warm/cold rent and
re-applies the filter. The LLM is used in `enrich` (fit-ranking) and `wiki` (synthesis prose),
escalating per the ModelRouter; everything else — parsing, filtering, dedup, wiki stats — is
deterministic. The `wiki` node is the *Ingest* operation of the knowledge wiki (see WIKI_SCHEMA.md).
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict

from apartment_agent.config import Settings
from apartment_agent.db.supabase_client import ListingsDB
from apartment_agent.llm.router import ModelRouter, Tier
from apartment_agent.models import FilterConfig, Listing, RunResult
from apartment_agent.nodes.filter import filter_listings, passes_filter
from apartment_agent.notify.telegram import TelegramNotifier
from apartment_agent.sources.base import SourceAdapter
from apartment_agent.wiki.ingest import WikiIngestor

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
    wiki: WikiIngestor | None = None


_ENRICH_SYSTEM = (
    "You help someone relocating to Munich pick rentals. They want an affordable place "
    "(warm rent <= 700€), at least 12 m², available around 1 October 2026, in Munich or a "
    "commutable suburb. Rate how well a listing fits (0-100, weighing price, size, location, "
    "timing) and summarize it in one sentence highlighting the standout pro or con. "
    'Respond with ONLY a JSON object: {"fit_score": <int 0-100>, "summary": "<one sentence>"}. '
    "No markdown, no preamble."
)

# Tolerant extraction: free/reasoning models often wrap the JSON in prose or <think> blocks.
_JSON_RE = re.compile(r'\{[^{}]*"fit_score"[^{}]*\}', re.S)


def _parse_assessment(text: str) -> tuple[int, str]:
    match = _JSON_RE.search(text) or re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"no JSON in response: {text[:120]!r}")
    data = json.loads(match.group(0))
    score = max(0, min(100, int(data["fit_score"])))
    return score, str(data.get("summary", "")).strip()


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

    def detail(state: AgentState) -> dict:
        """Resolve true warm/cold rent for new listings, then re-apply the filter.

        The list-level filter ran on the ambiguous card figure; once the detail page gives the real
        Warmmiete, drop anything whose warm rent actually exceeds the cap.
        """
        new = state.get("new", [])
        if not deps.settings.enable_detail_fetch or not new:
            return {}
        by_name = {a.name: a for a in deps.adapters}
        kept: list[Listing] = []
        for x in new:
            adapter = by_name.get(x.source)
            if adapter is not None:
                try:
                    adapter.fetch_costs(x)
                except Exception as e:  # noqa: BLE001 - keep the listed figure on any failure
                    state["result"].errors.append(f"detail {x.external_id}: {e}")
            ok, reasons = passes_filter(x, deps.filter_cfg)
            if ok:
                kept.append(x)
            else:
                log.info("dropped after detail fetch: %s (%s)", x.external_id, "; ".join(reasons))
        dropped = len(new) - len(kept)
        if dropped:
            log.info("detail re-filter dropped %d of %d new listing(s)", dropped, len(new))
        state["result"].new = len(kept)
        return {"new": kept}

    def enrich(state: AgentState) -> dict:
        new = state.get("new", [])
        if not (deps.settings.enable_llm_enrich and deps.router and not deps.settings.dry_run):
            return {}
        for x in new:
            try:
                text = deps.router.complete(
                    _ENRICH_SYSTEM, _enrich_user(x), tier=Tier.CHEAP, max_tier=Tier.MEDIUM
                )
                x.fit_score, x.summary = _parse_assessment(text)
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

    def wiki(state: AgentState) -> dict:
        """Ingest operation: fold the run's new listings into the knowledge wiki."""
        new = state.get("new", [])
        if deps.wiki is None or not new:
            return {}
        try:
            if deps.db is not None and not deps.settings.dry_run:
                corpus = deps.db.all_listings()  # includes the rows just persisted
            else:
                corpus = list(new)
            deps.wiki.ingest(
                corpus, new, filter_cfg=deps.filter_cfg, updated=datetime.now(UTC).date()
            )
        except Exception as e:  # noqa: BLE001
            state["result"].errors.append(f"wiki: {e}")
            log.exception("wiki ingest failed")
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
        return "detail" if state.get("new") else "END"

    from langgraph.graph import END, START, StateGraph

    g = StateGraph(AgentState)
    for name, fn in [
        ("scrape", scrape), ("filter", filter_node), ("dedup", dedup), ("detail", detail),
        ("enrich", enrich), ("persist", persist), ("wiki", wiki), ("notify", notify),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "scrape")
    g.add_edge("scrape", "filter")
    g.add_edge("filter", "dedup")
    g.add_conditional_edges("dedup", route_after_dedup, {"detail": "detail", "END": END})
    g.add_edge("detail", "enrich")
    g.add_edge("enrich", "persist")
    g.add_edge("persist", "wiki")
    g.add_edge("wiki", "notify")
    g.add_edge("notify", END)
    return g.compile()
