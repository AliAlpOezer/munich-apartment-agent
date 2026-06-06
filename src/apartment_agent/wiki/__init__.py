"""The knowledge-wiki layer.

A synthesized, interlinked markdown layer maintained on top of the raw `listings` data, after
Karpathy's *LLM Wiki* pattern. See `WIKI_SCHEMA.md` at the repo root for the governing contract.

  store.py   - where pages live (filesystem markdown), slug helpers
  pages.py   - deterministic rendering + section-marker read/merge (no LLM, fully testable)
  ingest.py  - fold a run's new listings into the affected pages (cheap-tier synthesis)
  lint.py    - health-check the wiki (stale / orphan / gap / broken link [+ optional LLM])
"""

from __future__ import annotations

from apartment_agent.wiki.store import FilesystemWikiStore, WikiStore, district_slug, slugify

__all__ = ["WikiStore", "FilesystemWikiStore", "slugify", "district_slug"]
