"""Conversation agent evaluation harness.

Includes:
- Full-turn HTTP eval (`agent_eval_runner`, `run_agent_eval.py`)
- Offline replay eval for autonomous behavior gates (Phase 23)
- Promotion readiness scorecards (Phase 24)
"""

from app.agent.evaluation.case_loader import load_eval_cases
from app.agent.evaluation.readiness_scorecard import build_readiness_scorecard
from app.agent.evaluation.replay_runner import run_eval_case, run_eval_cases
from app.agent.evaluation.reporting import build_eval_report, render_markdown_eval_report
from app.agent.evaluation.suite_loader import load_eval_suites

__all__ = [
    "load_eval_cases",
    "load_eval_suites",
    "run_eval_case",
    "run_eval_cases",
    "build_eval_report",
    "render_markdown_eval_report",
    "build_readiness_scorecard",
]
