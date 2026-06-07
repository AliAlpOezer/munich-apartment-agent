"""Entrypoint: build the graph from env config and run one pass.

  python -m apartment_agent.main            # real run (DB + Telegram)
  python -m apartment_agent.main --dry-run  # scrape→filter→(enrich off), no DB/Telegram
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime

from apartment_agent.config import load_settings
from apartment_agent.graph import Deps, build_graph
from apartment_agent.llm.router import ModelRouter
from apartment_agent.models import RunResult
from apartment_agent.sources.wg_gesucht import WgGesuchtAdapter

log = logging.getLogger("apartment_agent")


def _build_deps(settings):
    adapters = [WgGesuchtAdapter()]

    router = None
    if settings.enable_llm_enrich and (
        settings.openrouter_api_key or settings.opencode_zen_api_key or settings.anthropic_api_key
    ):
        router = ModelRouter(settings)

    db = None
    if not settings.dry_run and settings.supabase_url and settings.supabase_service_key:
        from apartment_agent.db.supabase_client import ListingsDB

        db = ListingsDB(settings.supabase_url, settings.supabase_service_key)

    notifier = None
    if not settings.dry_run and settings.telegram_bot_token and settings.telegram_chat_id:
        from apartment_agent.notify.telegram import TelegramNotifier

        notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)

    wiki = None
    if settings.enable_wiki:
        from apartment_agent.wiki.ingest import WikiIngestor
        from apartment_agent.wiki.store import FilesystemWikiStore

        wiki = WikiIngestor(FilesystemWikiStore(settings.wiki_dir), router=router)

    return Deps(
        settings=settings,
        filter_cfg=settings.filter_config(),
        adapters=adapters,
        router=router,
        db=db,
        notifier=notifier,
        wiki=wiki,
    )


def _run_graph(settings) -> dict:
    """Build deps and run one full pass of the graph; returns the final state dict.

    Shared by the CLI and the web backend so both invoke the agent identically (checkpointing,
    metrics persistence, token accounting). The web app calls `run_pipeline` for just the RunResult.
    """
    deps = _build_deps(settings)
    result = RunResult(started_at=datetime.now(UTC))

    if settings.enable_checkpointing and not settings.dry_run:
        from langgraph.checkpoint.sqlite import SqliteSaver

        from apartment_agent.checkpoint import new_thread_id, resume_incomplete

        with SqliteSaver.from_conn_string(settings.checkpoint_db) as saver:
            graph = build_graph(deps, checkpointer=saver)
            resumed = resume_incomplete(graph)
            if resumed:
                log.info("resumed %d interrupted run(s): %s", len(resumed), ", ".join(resumed))
            config = {"configurable": {"thread_id": new_thread_id()}}
            final = graph.invoke({"result": result}, config=config)
    else:
        final = build_graph(deps).invoke({"result": result})

    r = final.get("result", result)
    r.finished_at = datetime.now(UTC)
    if deps.router is not None:
        r.tokens = deps.router.usage
    if deps.db is not None and not settings.dry_run:
        try:
            deps.db.record_run(r)
        except Exception as e:  # noqa: BLE001 - metrics persistence must not fail the run
            log.warning("could not record run metrics: %s", e)
    return final


def run_pipeline(settings) -> RunResult:
    """Run one full agent pass and return its RunResult (used by the web backend)."""
    return _run_graph(settings).get("result", RunResult())


def _print_dry_run(state) -> None:
    new = state.get("new", [])
    print(f"\n=== DRY RUN: {len(new)} listing(s) passed the filter ===")
    for x in new:
        price = f"{x.effective_warm_rent:.0f}€" if x.effective_warm_rent is not None else "?€"
        size = f"{x.size_sqm:.0f}m²" if x.size_sqm is not None else "?m²"
        print(f"  [{x.listing_type.value:9s}] {price:>6} {size:>6}  "
              f"{x.city}/{x.district}  ab {x.available_from}  {x.url}")
        if x.title:
            print(f"      {x.title}")


def _run_lint(settings) -> int:
    """Lint operation: health-check the wiki, write the report page, print a summary."""
    from datetime import UTC, datetime

    from apartment_agent.wiki.lint import WikiLinter
    from apartment_agent.wiki.store import FilesystemWikiStore

    store = FilesystemWikiStore(settings.wiki_dir)
    linter = WikiLinter(store)
    corpus = None
    if settings.supabase_url and settings.supabase_service_key:
        from apartment_agent.db.supabase_client import ListingsDB

        corpus = ListingsDB(settings.supabase_url, settings.supabase_service_key).all_listings()

    today = datetime.now(UTC).date()
    report = linter.lint(today=today, corpus=corpus)
    store.write("lint-report", linter.render_report(report, today=today))
    print(f"wiki lint: {report.checked} page(s) checked, {len(report.findings)} finding(s)")
    for f in report.findings:
        print(f"  [{f.kind}] {f.slug}: {f.message}")
    return 0


def _run_sync_feedback(settings) -> int:
    """Pull Telegram 👍/👎 reactions, store them mapped to their listing, advance the offset."""
    configured = (
        settings.telegram_bot_token and settings.supabase_url and settings.supabase_service_key
    )
    if not configured:
        print("sync-feedback needs Telegram + Supabase configured")
        return 1
    from apartment_agent.db.supabase_client import ListingsDB
    from apartment_agent.feedback import sync_feedback
    from apartment_agent.notify.telegram import TelegramNotifier

    db = ListingsDB(settings.supabase_url, settings.supabase_service_key)
    tg = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)

    saved = sync_feedback(
        fetch_updates=lambda offset: tg.get_updates(offset),
        resolve_listing=db.listing_for_message,
        save_feedback=db.save_feedback,
        offset_get=lambda: int(db.get_state("tg_offset", "0") or 0),
        offset_set=lambda v: db.set_state("tg_offset", str(v)),
    )
    log.info("synced %d feedback reaction(s)", saved)
    print(f"synced {saved} reaction(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Munich apartment-hunter agent")
    parser.add_argument("--dry-run", action="store_true", help="no DB writes / no Telegram")
    parser.add_argument("--lint", action="store_true", help="health-check the wiki and exit")
    parser.add_argument("--sync-feedback", action="store_true",
                        help="pull Telegram reactions into stored feedback and exit")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.dry_run:
        settings.dry_run = True
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.lint:
        return _run_lint(settings)
    if args.sync_feedback:
        return _run_sync_feedback(settings)

    final = _run_graph(settings)
    r = final.get("result", RunResult())

    if settings.dry_run:
        _print_dry_run(final)

    log.info(
        "run done: scraped=%d matched=%d new=%d notified=%d errors=%d",
        r.scraped, r.matched, r.new, r.notified, len(r.errors),
    )
    for err in r.errors:
        log.warning("run error: %s", err)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
