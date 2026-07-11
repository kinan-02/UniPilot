"""Request schema for the internal /advise route."""

from pydantic import BaseModel, ConfigDict, Field


class AdviseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(min_length=1)
