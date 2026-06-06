"""Eval harness: score fit-ranking against expected bands, and judge synthesis quality.

`run_fit_evals` runs the real `assess_listing` path, so it exercises structured-output + escalation.
`judge_synthesis` is LLM-as-judge: a model checks whether a wiki synthesis is coherent and grounded
in the supplied facts (no invented numbers). Both take a router, so tests inject a fake.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel

from apartment_agent.evals.cases import GOLDEN, EvalCase
from apartment_agent.graph import assess_listing
from apartment_agent.llm.router import ModelRouter, Tier

log = logging.getLogger(__name__)


class FitEvalResult(BaseModel):
    name: str
    score: int
    lo: int
    hi: int

    @property
    def passed(self) -> bool:
        return self.lo <= self.score <= self.hi


class EvalReport(BaseModel):
    results: list[FitEvalResult] = []

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.results)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.results else 1.0


def run_fit_evals(router, cases: list[EvalCase] | None = None) -> EvalReport:
    """Score each golden listing and check it falls in its expected band."""
    cases = cases if cases is not None else GOLDEN
    results: list[FitEvalResult] = []
    for case in cases:
        assessment = assess_listing(router, case.listing)
        results.append(FitEvalResult(
            name=case.name, score=assessment.fit_score, lo=case.lo, hi=case.hi,
        ))
    return EvalReport(results=results)


class JudgeVerdict(BaseModel):
    grounded: bool
    reason: str = ""


_JUDGE_SYSTEM = (
    "You are a strict reviewer. Given FACTS and a SYNTHESIS written about them, decide whether the "
    "synthesis is coherent and grounded — it must not state numbers or claims absent from the "
    'facts. Respond with ONLY JSON: {"grounded": <true|false>, "reason": "<short>"}. No preamble.'
)
_JSON_RE = re.compile(r"\{.*\}", re.S)


def judge_synthesis(router, facts: str, synthesis: str) -> JudgeVerdict:
    """LLM-as-judge: is `synthesis` coherent and grounded in `facts`? Uses the hard tier."""
    user = f"FACTS:\n{facts}\n\nSYNTHESIS:\n{synthesis}"
    text = router.complete(_JUDGE_SYSTEM, user, tier=Tier.MEDIUM, max_tier=Tier.HARD)
    match = _JSON_RE.search(text)
    if not match:
        return JudgeVerdict(grounded=False, reason=f"no JSON in judge response: {text[:80]!r}")
    data = json.loads(match.group(0))
    return JudgeVerdict(grounded=bool(data.get("grounded")), reason=str(data.get("reason", "")))


def main() -> int:
    """Run the live fit evals and print a report (needs LLM keys)."""
    import logging as _logging

    from apartment_agent.config import load_settings

    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    has_key = (
        settings.opencode_zen_api_key or settings.openrouter_api_key or settings.anthropic_api_key
    )
    if not has_key:
        print("no LLM keys configured — set one in .env to run live evals")
        return 1
    report = run_fit_evals(ModelRouter(settings))
    for r in report.results:
        mark = "PASS" if r.passed else "FAIL"
        print(f"  [{mark}] {r.name}: score={r.score} expected {r.lo}-{r.hi}")
    print(f"fit evals: {report.passed}/{report.total} passed ({report.pass_rate:.0%})")
    return 0 if report.pass_rate == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
