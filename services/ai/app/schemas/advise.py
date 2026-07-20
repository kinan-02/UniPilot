"""Request schema for the internal /advise route."""

from pydantic import BaseModel, ConfigDict, Field


class AdviseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(min_length=1)
    conversation_id: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Optional thread id. When present, the prior exchanges of this conversation are "
            "loaded so a follow-up ('continue', 'what about spring?') resolves, and this answer "
            "is appended. Omit for a one-off question."
        ),
    )
