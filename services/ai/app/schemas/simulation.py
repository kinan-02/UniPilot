"""Simulation council schemas (AGT-3)."""

from typing import Any

from pydantic import BaseModel, Field


class NarrateSimulationRequest(BaseModel):
    scenario_name: str = Field(min_length=1, max_length=200)
    operations: list[dict[str, Any]] = Field(default_factory=list)
    before_snapshot: dict[str, Any] = Field(default_factory=dict)
    after_snapshot: dict[str, Any] = Field(default_factory=dict)
    deltas: dict[str, Any] = Field(default_factory=dict)
