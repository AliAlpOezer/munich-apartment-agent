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

    return Deps(
        settings=settings,
        filter_cfg=settings.filter_config(),
        adapters=adapters,
        router=router,
        db=db,
        notifier=notifier,
    )


def _print_dry_run(state) -> None:
    new = state.get("new", [])
    print(f"\n=== DRY RUN: {len(new)} listing(s) passed the filter ===")
    for x in new:
        price = f"{x.price_warm:.0f}€" if x.price_warm is not None else "?€"
        size = f"{x.size_sqm:.0f}m²" if x.size_sqm is not None else "?m²"
        print(f"  [{x.listing_type.value:9s}] {price:>6} {size:>6}  "
              f"{x.city}/{x.district}  ab {x.available_from}  {x.url}")
        if x.title:
            print(f"      {x.title}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Munich apartment-hunter agent")
    parser.add_argument("--dry-run", action="store_true", help="no DB writes / no Telegram")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.dry_run:
        settings.dry_run = True
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    deps = _build_deps(settings)
    graph = build_graph(deps)

    result = RunResult(started_at=datetime.now(UTC))
    final = graph.invoke({"result": result})
    result.finished_at = datetime.now(UTC)

    if settings.dry_run:
        _print_dry_run(final)

    r = final.get("result", result)
    log.info(
        "run done: scraped=%d matched=%d new=%d notified=%d errors=%d",
        r.scraped, r.matched, r.new, r.notified, len(r.errors),
    )
    for err in r.errors:
        log.warning("run error: %s", err)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
