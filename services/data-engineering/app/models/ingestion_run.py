from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

IngestionStatus = Literal["pending", "running", "completed", "failed", "partial"]


class IngestionRun(BaseModel):
    """Tracks a single ingestion job against staging collections."""

    model_config = ConfigDict(extra="forbid")

    sourceName: str = Field(min_length=1, max_length=200)
    sourceType: str = Field(min_length=1, max_length=100)
    status: IngestionStatus = "pending"
    startedAt: datetime
    finishedAt: datetime | None = None
    itemsRead: int = Field(default=0, ge=0)
    itemsValid: int = Field(default=0, ge=0)
    itemsInvalid: int = Field(default=0, ge=0)
    errors: list[str] = Field(default_factory=list)
