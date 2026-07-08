"""Provenance tracking for agent context (spec §19)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

SourceType = Literal[
    "mongodb",
    "course_offering_json",
    "course_offering_mongo",
    "catalog",
    "catalog_wiki",
]

RetrievalMethod = Literal[
    "exact_lookup",
    "metadata_filtered_hybrid_search",
    "keyword_search",
    "mongo_query",
]

ConfidenceLevel = Literal["high", "medium", "low"]


class ProvenanceRecord(BaseModel):
    claim: str
    source_type: SourceType
    source_id: str | None = None
    retrieval_method: RetrievalMethod
    confidence: ConfidenceLevel | float = "high"
    field_path: str | None = None
    retrieved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )

    def summary_line(self) -> str:
        return f"{self.claim} [{self.source_type}:{self.retrieval_method}]"


def provenance_claim(
    *,
    claim: str,
    source_type: SourceType,
    source_id: str | None = None,
    retrieval_method: RetrievalMethod,
    confidence: ConfidenceLevel | float = "high",
    field_path: str | None = None,
) -> ProvenanceRecord:
    return ProvenanceRecord(
        claim=claim,
        source_type=source_type,
        source_id=source_id,
        retrieval_method=retrieval_method,
        confidence=confidence,
        field_path=field_path,
    )


def provenance_to_strings(records: list[ProvenanceRecord]) -> list[str]:
    return [record.summary_line() for record in records]


def user_facing_sources(records: list[ProvenanceRecord]) -> list[str]:
    labels: dict[SourceType, str] = {
        "mongodb": "Your profile and completed courses",
        "course_offering_mongo": "Semester course offerings",
        "course_offering_json": "Semester course offerings (JSON)",
        "catalog": "Degree catalog requirements",
        "catalog_wiki": "Catalog wiki explanations",
    }
    seen: set[str] = set()
    ordered: list[str] = []
    for record in records:
        label = labels.get(record.source_type, record.source_type)
        if label not in seen:
            seen.add(label)
            ordered.append(label)
    return ordered
