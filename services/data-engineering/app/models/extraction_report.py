from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExtractionReport(BaseModel):
    """Summary of a local PDF text extraction run (no database persistence)."""

    model_config = ConfigDict(extra="forbid")

    sourceFile: str = Field(min_length=1)
    sourceType: str = Field(min_length=1)
    pageCount: int = Field(ge=0)
    extractedPageCount: int = Field(ge=0)
    totalCharacters: int = Field(ge=0)
    averageCharactersPerPage: float = Field(ge=0)
    lowTextPages: list[int] = Field(default_factory=list)
    extractionWarnings: list[str] = Field(default_factory=list)
    extractorName: str = Field(min_length=1)
    createdAt: datetime
    outputDirectory: str = Field(min_length=1)
