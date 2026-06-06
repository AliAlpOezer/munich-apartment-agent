"""Where wiki pages live, and how listings map to page slugs.

A `WikiStore` is a tiny key→markdown blob store (slug → page text). The default
`FilesystemWikiStore` keeps one `<slug>.md` file per page under a root dir; the abstraction
leaves room for a Supabase-backed store later without touching ingest/lint.

Slugs are stable, lowercase, ascii-folded identifiers (`district-schwabing`, `market-overview`).
Kept dependency-light (stdlib only) so it is trivially unit-testable.
"""

from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod
from pathlib import Path

from apartment_agent.models import Listing

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """'Münched Schwabing!' -> 'munched-schwabing'. Empty/garbage -> 'unknown'."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", folded.lower()).strip("-")
    return slug or "unknown"


def district_slug(listing: Listing) -> str:
    """The page a listing belongs to: its district, else its city, else 'unknown'."""
    label = (listing.district or listing.city or "").strip()
    return f"district-{slugify(label)}" if label else "district-unknown"


def district_label(listing: Listing) -> str:
    """Human-readable name for the listing's district page."""
    return (listing.district or listing.city or "Unknown area").strip()


class WikiStore(ABC):
    """A slug → markdown page store."""

    @abstractmethod
    def read(self, slug: str) -> str | None:
        """Page markdown, or None if the page does not exist."""

    @abstractmethod
    def write(self, slug: str, content: str) -> None:
        """Create or overwrite a page."""

    @abstractmethod
    def exists(self, slug: str) -> bool: ...

    @abstractmethod
    def list_slugs(self) -> list[str]:
        """All existing page slugs, sorted."""


class FilesystemWikiStore(WikiStore):
    """One `<slug>.md` file per page under `root` (created on first write)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, slug: str) -> Path:
        return self.root / f"{slug}.md"

    def read(self, slug: str) -> str | None:
        path = self._path(slug)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def write(self, slug: str, content: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not content.endswith("\n"):
            content += "\n"
        self._path(slug).write_text(content, encoding="utf-8")

    def exists(self, slug: str) -> bool:
        return self._path(slug).exists()

    def list_slugs(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("*.md"))
