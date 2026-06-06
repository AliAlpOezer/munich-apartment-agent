"""Source-adapter interface. Each listing site implements one of these."""

from __future__ import annotations

from abc import ABC, abstractmethod

from apartment_agent.models import FilterConfig, Listing


class SourceAdapter(ABC):
    """A pluggable listing source (e.g. WG-Gesucht, ImmoScout24)."""

    #: short stable identifier stored on every Listing and used for dedup keys
    name: str

    @abstractmethod
    def build_search_urls(self, cfg: FilterConfig) -> list[str]:
        """Search-result URLs to crawl for the given filters."""

    @abstractmethod
    def fetch(self, url: str) -> str:
        """Return the HTML for a search-result page (raises on hard failure)."""

    @abstractmethod
    def parse(self, html: str) -> list[Listing]:
        """Parse one search-result page into normalized Listings."""

    def search(self, cfg: FilterConfig) -> list[Listing]:
        """Default orchestration: fetch every search URL and parse it.

        Errors on a single page are swallowed so one bad page doesn't sink the run;
        subclasses can override for source-specific pacing/anti-bot handling.
        """
        out: list[Listing] = []
        for url in self.build_search_urls(cfg):
            try:
                out.extend(self.parse(self.fetch(url)))
            except Exception:  # noqa: BLE001 - per-page resilience; caller logs run errors
                continue
        return out
