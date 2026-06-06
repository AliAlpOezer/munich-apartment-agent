"""Evaluation harness for the LLM-touching steps.

Convention: every model-touching change ships with an eval. This package holds a small labelled
golden set (`cases.py`) and a harness (`harness.py`) that scores the fit-ranking against expected
bands and judges wiki synthesis quality (LLM-as-judge). Runs offline against a fake router in tests,
and against the live router via `python -m apartment_agent.evals` when keys are present.
"""

from __future__ import annotations

from apartment_agent.evals.cases import GOLDEN, EvalCase
from apartment_agent.evals.harness import (
    EvalReport,
    JudgeVerdict,
    judge_synthesis,
    run_fit_evals,
)

__all__ = [
    "GOLDEN",
    "EvalCase",
    "EvalReport",
    "JudgeVerdict",
    "run_fit_evals",
    "judge_synthesis",
]
