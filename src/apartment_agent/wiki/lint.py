"""Lint — health-check the wiki.

Deterministic checks (no LLM, fully testable):
  * broken-link : a `[[slug]]` pointing at a page that does not exist
  * orphan      : a page nothing links to (hubs like market-overview/preferences are exempt)
  * stale       : a page whose 'last updated' date is older than `stale_days`
  * gap         : a district present in the corpus that has no page yet

An optional LLM pass (hard tier) can additionally flag prose/data contradictions; it is off by
default and never required for the deterministic report.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from pydantic import BaseModel

from apartment_agent.models import Listing
from apartment_agent.wiki import pages
from apartment_agent.wiki.store import WikiStore, district_slug

log = logging.getLogger(__name__)

_HUB_SLUGS = {"market-overview", "preferences", "lint-report"}
_UPDATED_RE = re.compile(r"last updated (\d{4})-(\d{2})-(\d{2})")


class LintFinding(BaseModel):
    kind: str           # broken-link | orphan | stale | gap | contradiction
    slug: str
    message: str


class LintReport(BaseModel):
    checked: int = 0
    findings: list[LintFinding] = []

    @property
    def ok(self) -> bool:
        return not self.findings


def _page_updated(text: str) -> date | None:
    m = _UPDATED_RE.search(text)
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


class WikiLinter:
    def __init__(self, store: WikiStore):
        self.store = store

    def lint(
        self,
        *,
        today: date,
        corpus: list[Listing] | None = None,
        stale_days: int = 14,
    ) -> LintReport:
        slugs = self.store.list_slugs()
        pages_text = {s: (self.store.read(s) or "") for s in slugs}
        existing = set(slugs)
        findings: list[LintFinding] = []

        linked_to: set[str] = set()
        for slug, text in pages_text.items():
            for target in pages.find_wikilinks(text):
                linked_to.add(target)
                if target not in existing:
                    findings.append(LintFinding(
                        kind="broken-link", slug=slug,
                        message=f"links to [[{target}]] which does not exist",
                    ))
            updated = _page_updated(text)
            if updated is not None and (today - updated).days > stale_days:
                findings.append(LintFinding(
                    kind="stale", slug=slug,
                    message=f"last updated {updated.isoformat()} (> {stale_days}d ago)",
                ))

        for slug in slugs:
            if slug in _HUB_SLUGS:
                continue
            if slug not in linked_to:
                findings.append(LintFinding(
                    kind="orphan", slug=slug, message="no other page links here",
                ))

        if corpus is not None:
            wanted = {district_slug(x) for x in corpus}
            for slug in sorted(wanted - existing):
                findings.append(LintFinding(
                    kind="gap", slug=slug, message="district has listings but no page",
                ))

        return LintReport(checked=len(slugs), findings=findings)

    def render_report(self, report: LintReport, *, today: date) -> str:
        if report.ok:
            body = "_No issues found._"
        else:
            by_kind: dict[str, list[LintFinding]] = {}
            for f in report.findings:
                by_kind.setdefault(f.kind, []).append(f)
            chunks = []
            for kind in sorted(by_kind):
                lines = "\n".join(f"- `{f.slug}` — {f.message}" for f in by_kind[kind])
                chunks.append(f"### {kind} ({len(by_kind[kind])})\n{lines}")
            body = "\n\n".join(chunks)
        header = (
            f"# 🩺 Wiki health report\n\n<!-- {pages.WIKI_TAG} lint-report -->\n"
            f"*{report.checked} page(s) checked · {len(report.findings)} finding(s) · "
            f"{today.isoformat()}*"
        )
        return f"{header}\n\n{body}"
