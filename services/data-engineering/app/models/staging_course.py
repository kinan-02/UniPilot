"""Staging models for Technion semester course JSON import (Phase 9)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StagedTechnionCourseOffering(BaseModel):
    """Semester-specific offering evidence from Technion course JSON."""

    model_config = ConfigDict(extra="forbid")

    stagingKey: str = Field(min_length=1, max_length=200)
    courseNumber: str = Field(min_length=8, max_length=8, pattern=r"^0\d{7}$")
    academicYear: int = Field(ge=1990, le=2100)
    semesterCode: int = Field(ge=200, le=202)
    semesterName: str = Field(min_length=1, max_length=20)
    scheduleGroups: list[dict[str, Any]] = Field(default_factory=list)
    examDates: dict[str, str | None] = Field(default_factory=dict)
    instructors: str | None = None
    sourceFile: str = Field(min_length=1, max_length=300)
    isStaging: bool = True
    productionEligible: bool = False
    requiresHumanReview: bool = True
    importedAt: str | None = None
    importRunId: str | None = None
    warnings: list[str] = Field(default_factory=list)


class StagedTechnionCourse(BaseModel):
    """Merged Technion course metadata staged from one or more semester JSON files."""

    model_config = ConfigDict(extra="forbid")

    stagingKey: str = Field(min_length=1, max_length=100)
    institutionId: str = Field(default="technion", min_length=1, max_length=100)
    courseNumber: str = Field(min_length=8, max_length=8, pattern=r"^0\d{7}$")
    titleHebrew: str | None = None
    syllabus: str | None = None
    faculty: str | None = None
    studyFramework: str | None = None
    credits: float | None = Field(default=None, ge=0, le=30)
    prerequisitesText: str | None = None
    corequisitesText: str | None = None
    noAdditionalCreditText: str | None = None
    instructors: str | None = None
    notes: str | None = None
    sourceFiles: list[str] = Field(min_length=1)
    semestersOffered: list[int] = Field(default_factory=list)
    offerings: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Embedded semester offering summaries (full detail in staging_course_offerings).",
    )
    exams: dict[str, str | None] = Field(default_factory=dict)
    scheduleSummary: str | None = None
    rawFieldKeys: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    isStaging: bool = True
    productionEligible: bool = False
    requiresHumanReview: bool = True
    sourceName: str = Field(min_length=1, max_length=200)
    sourceType: str = Field(min_length=1, max_length=100)
    importedAt: str | None = None
    importRunId: str | None = None


class TechnionCourseStagingImportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dryRun: bool = False
    ddsOnly: bool = False
    filesRead: int = 0
    rawRecordsRead: int = 0
    validCourses: int = 0
    invalidRecords: int = 0
    uniqueCourses: int = 0
    ddsFacultyCourses: int = 0
    offeringsObserved: int = 0
    warnings: list[str] = Field(default_factory=list)
    stagingCollections: dict[str, str] = Field(default_factory=dict)
    ingestionRunId: str | None = None
    ingestionStatus: str | None = None
