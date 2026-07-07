"""Lab-only side-effect firewall for full LLM shadow replay (Phase 26)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


class SideEffectViolation(RuntimeError):
    """Raised when a blocked side effect is attempted during eval lab runs."""


class EvalSideEffectFirewall:
    """Block writes and action proposals during full shadow replay."""

    _WRITE_TARGETS: tuple[tuple[str, str, str], ...] = (
        ("app.repositories.student_profile_repository", "create_student_profile", "student_profile_write"),
        ("app.repositories.student_profile_repository", "update_student_profile_by_user_id", "student_profile_write"),
        ("app.repositories.completed_course_repository", "create_completed_course", "completed_course_write"),
        ("app.repositories.completed_course_repository", "update_completed_course_by_id_and_user_id", "completed_course_write"),
        ("app.repositories.semester_plan_repository", "create_semester_plan", "semester_plan_write"),
        ("app.repositories.semester_plan_repository", "update_semester_plan_by_id_and_user_id", "semester_plan_write"),
    )

    _ACTION_TARGETS: tuple[tuple[str, str, str], ...] = (
        ("app.repositories.agent_action_proposal_repository", "create_agent_action_proposal", "action_proposal"),
    )

    def __init__(self, *, block_writes: bool = True, block_action_proposals: bool = True) -> None:
        self.block_writes = block_writes
        self.block_action_proposals = block_action_proposals
        self._patches: list[Any] = []
        self._violations: list[dict[str, str]] = []

    def violations(self) -> list[dict[str, str]]:
        return list(self._violations)

    def _record(self, kind: str, target: str) -> None:
        self._violations.append({"kind": kind, "target": target})

    async def _blocked(self, kind: str, target: str, *_args: Any, **_kwargs: Any) -> None:
        self._record(kind, target)
        raise SideEffectViolation(f"side_effect_blocked:{kind}:{target}")

    def install(self) -> None:
        if self._patches:
            return

        targets: list[tuple[str, str, str]] = []
        if self.block_action_proposals:
            targets.extend(self._ACTION_TARGETS)
        if self.block_writes:
            targets.extend(self._WRITE_TARGETS)

        for module_name, func_name, kind in targets:
            target = f"{module_name}.{func_name}"

            async def _block(*_args: Any, _kind: str = kind, _target: str = target, **_kwargs: Any) -> None:
                await self._blocked(_kind, _target)

            self._patches.append(patch(target, new=_block))

        for item in self._patches:
            item.start()

    def uninstall(self) -> None:
        while self._patches:
            self._patches.pop().stop()

    def __enter__(self) -> EvalSideEffectFirewall:
        self.install()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.uninstall()
