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
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    tier1_models: str = "meta-llama/llama-3.3-70b-instruct:free"

    opencode_zen_api_key: str = ""
    opencode_zen_base_url: str = "https://opencode.ai/zen/v1"
    tier2_model: str = ""

    anthropic_api_key: str = ""
    tier3_model: str = "claude-sonnet-4-6"

    # --- Database ---
    supabase_url: str = ""
    supabase_service_key: str = ""

    # --- Notifications ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- Filters ---
    max_warm_rent_eur: float = 700.0
    min_size_sqm: float = 12.0
    move_in_date: date = date(2026, 10, 1)
    listing_types: str = "wg_room,apartment"

    # --- Behavior ---
    dry_run: bool = False
    enable_llm_enrich: bool = True
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
        )


def load_settings() -> Settings:
    return Settings()
