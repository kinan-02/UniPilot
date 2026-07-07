"""Static safety checks for offline eval package (Phase 23)."""

from __future__ import annotations

from pathlib import Path

_FORBIDDEN_PATTERNS = (
    ".insert_one(",
    ".update_one(",
    ".delete_one(",
    "create_agent_action_proposal(",
    "confirm_action(",
    "reject_action(",
    "/confirm",
    "/reject",
    "chat.completions",
    "ChatOpenAI",
    "OpenAI(",
    "llm.invoke",
    "llm.ainvoke",
    "exec(",
    "eval(",
    "compile(",
)

_EVAL_FILES = (
    "replay_schemas.py",
    "sanitizer.py",
    "case_loader.py",
    "oracles.py",
    "fake_reasoning.py",
    "gates_eval.py",
    "metrics.py",
    "reporting.py",
    "replay_runner.py",
    "safety.py",
    "real_world_schemas.py",
    "real_world_anonymizer.py",
    "real_world_importer.py",
    "side_effect_firewall.py",
    "llm_trace_summary.py",
    "full_shadow_runner.py",
    "full_shadow_reporting.py",
    "final_answer_eval.py",
    "final_answer_runner.py",
    "final_answer_judge.py",
    "regression_assertions.py",
    "trace_logging.py",
    "trace_extraction.py",
    "trace_run_loader.py",
)


def scan_eval_replay_forbidden_patterns() -> list[str]:
    eval_dir = Path(__file__).resolve().parent
    violations: list[str] = []
    for name in _EVAL_FILES:
        if name == "safety.py":
            continue
        path = eval_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern not in text:
                continue
            if pattern == "compile(" and "re.compile(" in text:
                continue
            if pattern == "eval(" and ("evaluate_" in text or "gates_eval" in name):
                continue
            violations.append(f"{name}:{pattern}")
    return violations


def assert_eval_replay_safe() -> None:
    violations = scan_eval_replay_forbidden_patterns()
    if violations:
        raise RuntimeError(f"eval_replay_safety_violations:{', '.join(violations)}")
