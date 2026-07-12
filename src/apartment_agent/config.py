"""Runtime configuration loaded from environment / .env.

Secrets and tunables live here; `FilterConfig` (in models.py) is built from these.
"""

from __future__ import annotations

from datetime import date

from pydantic_settings import BaseSettings, SettingsConfigDict

from apartment_agent.models import FilterConfig, ListingType


def _parse_listing_types(raw: str) -> set[ListingType]:
    out: set[ListingType] = set()
    for tok in raw.split(","):
        tok = tok.strip().lower()
        if tok:
            out.add(ListingType(tok))
    return out or {ListingType.WG_ROOM, ListingType.APARTMENT}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- LLM tiers ---
    # tier1 = cheap: OpenRouter free models (rotated on rate-limit). tier2 = OpenCode Zen,
    # tier3 = Anthropic/Claude. The listing rater starts at tier1 and only escalates on failure.
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Provider-diverse rotation: free models rate-limit hard *per upstream provider*, so the list
    # spans several. `openrouter/free` auto-routes to whatever free capacity is live; the others are
    # strong instruct models. The router rotates on 429 and escalates to tier2 if all are throttled.
    tier1_models: str = (
        "openrouter/free,"
        "nvidia/nemotron-3-super-120b-a12b:free,"
        "qwen/qwen3-next-80b-a3b-instruct:free,"
        "meta-llama/llama-3.3-70b-instruct:free"
    )

    opencode_zen_api_key: str = ""
    opencode_zen_base_url: str = "https://opencode.ai/zen/v1"
    tier2_model: str = ""

    anthropic_api_key: str = ""
    tier3_model: str = "claude-sonnet-4-6"

    # --- Database (local SQLite; self-initializing, no server) ---
    db_path: str = "apartments.sqlite"

    # --- Notifications ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- Filters ---
    max_warm_rent_eur: float = 657.0
    min_size_sqm: float = 10.0
    move_in_date: date = date(2026, 09, 1)
    listing_types: str = "wg_room,apartment"

    # --- Search geo-radius ---
    # Center the search on a point + radius (metres) instead of the whole city. Defaults to a 5 km
    # radius around Alte Heide (north Munich). Blank lat/lng falls back to a city-wide search.
    search_center_label: str = "Alte Heide, München, Deutschland, 80805"
    search_center_lat: float | None = 48.1783353
    search_center_lng: float | None = 11.5978799
    search_radius_m: int = 5000

    # --- Behavior ---
    dry_run: bool = False
    # Fetch each new listing's detail page to resolve the real warm/cold rent before the final
    # filter (the list card only shows one ambiguous figure). Off -> filter on the listed figure.
    enable_detail_fetch: bool = True
    # Parallel detail-page fetches for new listings. Kept low to stay polite to the source.
    detail_concurrency: int = 3
    enable_llm_enrich: bool = True
    enable_wiki: bool = True
    # Human-in-the-loop: send one message per listing so 👍/👎 reactions map to a listing, sync them
    # with `--sync-feedback`, and fold the learned signal into the wiki preferences page.
    enable_feedback: bool = True
    # Durable execution: persist graph state per super-step so an interrupted run resumes.
    enable_checkpointing: bool = True
    checkpoint_db: str = "agent_state.sqlite"
    # Web dashboard auto-search interval in minutes (0 disables the timer; manual button always on).
    web_auto_search_minutes: int = 180
    # Shared token required on /api requests when set (the dashboard sends it as X-API-Token).
    # Strongly recommended once the box is reachable from a public GitHub Pages frontend.
    web_api_token: str = ""
    # Allowed CORS origins for the API (comma-separated), e.g. your https://<user>.github.io page.
    web_cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.web_cors_origins.split(",") if o.strip()] or ["*"]
    # Where the knowledge wiki is written. Gitignored so it survives `git reset --hard` redeploys.
    wiki_dir: str = "wiki"
    log_level: str = "INFO"

    @property
    def tier1_model_list(self) -> list[str]:
        return [m.strip() for m in self.tier1_models.split(",") if m.strip()]

    def filter_config(self) -> FilterConfig:
        return FilterConfig(
            max_warm_rent_eur=self.max_warm_rent_eur,
            min_size_sqm=self.min_size_sqm,
            move_in_date=self.move_in_date,
            listing_types=_parse_listing_types(self.listing_types),
            search_center_label=self.search_center_label,
            search_center_lat=self.search_center_lat,
            search_center_lng=self.search_center_lng,
            search_radius_m=self.search_radius_m,
        )


def load_settings() -> Settings:
    return Settings()
