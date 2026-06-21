"""Filter offering schedule groups by per-type user selection."""

from __future__ import annotations

from typing import Any

from app.planning.weekly_schedule import normalize_schedule_group

SLOT_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "lecture": ("lecture", "הרצאה", "lec"),
    "tutorial": ("tutorial", "תרגול", "recitation", "lesson", "תר"),
    "lab": ("lab", "מעבדה", "laboratory"),
    "project": ("project", "פרויקט", "workshop", "סדנה"),
}


def _canonical_slot_type(slot_type: str) -> str:
    normalized = slot_type.strip().lower()
    if not normalized:
        return "other"
    for canonical, aliases in SLOT_TYPE_ALIASES.items():
        if normalized in aliases or any(alias.lower() in normalized for alias in aliases):
            return canonical
    return normalized


def group_schedule_by_type(schedule_groups: list[dict[str, Any]]) -> dict[str, list[tuple[int, dict[str, Any]]]]:
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, group in enumerate(schedule_groups or []):
        normalized = normalize_schedule_group(group)
        canonical = _canonical_slot_type(normalized.get("slotType") or "")
        grouped.setdefault(canonical, []).append((index, group))
    return grouped


def filter_schedule_groups_by_selection(
    schedule_groups: list[dict[str, Any]],
    selected_groups: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return schedule groups included in the plan based on selectedGroups."""
    if not schedule_groups:
        return []
    if not selected_groups:
        return list(schedule_groups)

    explicit_values = [
        value
        for key, value in selected_groups.items()
        if key in {"lecture", "tutorial", "lab", "project"} and value is not None
    ]
    if not explicit_values:
        return list(schedule_groups)

    grouped = group_schedule_by_type(schedule_groups)
    selected: list[dict[str, Any]] = []

    for slot_key in ("lecture", "tutorial", "lab", "project"):
        selection = selected_groups.get(slot_key)
        if selection is None:
            continue
        bucket = grouped.get(slot_key, [])
        if not bucket:
            continue
        if isinstance(selection, int):
            if 0 <= selection < len(bucket):
                selected.append(bucket[selection][1])
            continue
        if isinstance(selection, str):
            for _, group in bucket:
                normalized = normalize_schedule_group(group)
                if normalized.get("slotType") == selection:
                    selected.append(group)
                    break

    return selected if selected else list(schedule_groups)


def available_group_options(schedule_groups: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Summarize selectable groups per slot type for UI."""
    grouped = group_schedule_by_type(schedule_groups)
    options: dict[str, list[dict[str, Any]]] = {}
    for slot_key, items in grouped.items():
        options[slot_key] = [
            {
                "index": index,
                "label": normalize_schedule_group(group).get("slotType") or slot_key,
                "day": normalize_schedule_group(group).get("day"),
                "timeRange": normalize_schedule_group(group).get("timeRange"),
            }
            for index, group in items
        ]
    return options
