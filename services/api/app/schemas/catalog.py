"""Read-only catalog API schemas (Phase 13 — production collections)."""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

COURSE_NUMBER_PATTERN = r"^0\d{7}$"
PROGRAM_CODE_PATTERN = r"^\d{6}-\d-\d{3}$"
VALID_SEMESTER_CODES = frozenset({200, 201, 202})


class CourseMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    degreeRequirementsInferred: bool = False
    offeringSnapshotOnly: bool | None = None
    notCanonicalCatalog: bool | None = None


class SemesterOfferingSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    academicYear: int
    semesterCode: int
    slotTypes: list[str] = Field(default_factory=list)
    instructors: str | None = None


class CourseSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    courseNumber: str
    institutionId: str | None = None
    title: str | None = None
    titleHebrew: str | None = None
    credits: float | None = None
    faculty: str | None = None
    studyFramework: str | None = None
    catalogYear: int | None = None
    catalogVersion: str | None = None
    status: str = "published"
    metadata: CourseMetadata = Field(default_factory=CourseMetadata)
    semesterOfferingSummary: SemesterOfferingSummary | None = None


class CourseOffering(BaseModel):
    model_config = ConfigDict(extra="ignore")

    courseNumber: str
    academicYear: int
    semesterCode: int
    semesterName: str | None = None
    scheduleGroups: list[dict[str, Any]] = Field(default_factory=list)
    examDates: dict[str, str | None] = Field(default_factory=dict)
    instructors: str | None = None
    sourceFile: str | None = None
    catalogVersion: str | None = None
    status: str = "published"


class CourseDetail(CourseSummary):
    syllabus: str | None = None
    prerequisitesText: str | None = None
    corequisitesText: str | None = None
    noAdditionalCreditText: str | None = None
    instructors: str | None = None
    notes: str | None = None
    semestersOffered: list[int] = Field(default_factory=list)
    scheduleSummary: str | None = None
    offerings: list[CourseOffering] = Field(default_factory=list)


class PaginatedCourseResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[CourseSummary]
    total: int
    limit: int
    offset: int


class DegreeProgram(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    programCode: str
    institutionId: str
    name: str | None = None
    nameEn: str | None = None
    nameHebrew: str | None = None
    totalCredits: float | None = None
    catalogYear: int | None = None
    catalogVersion: str | None = None
    status: str = "published"
    paths: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CatalogFaculty(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    facultyId: str
    institutionId: str
    wikiSlug: str
    name: str | None = None
    nameHe: str | None = None
    nameEn: str | None = None
    aliases: list[str] = Field(default_factory=list)
    catalogPrefix: str | None = None
    catalogYear: int | None = None
    catalogVersion: str | None = None
    status: str = "published"


class CatalogPathOption(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    optionKey: str
    institutionId: str
    facultyId: str
    wikiSlug: str
    kind: str
    name: str | None = None
    nameHe: str | None = None
    nameEn: str | None = None
    studyLevels: list[str] = Field(default_factory=list)
    selectableAsPrimary: bool = False
    linkedProgramCode: str | None = None
    linkedDegreeProgramId: str | None = None
    curriculumWikiSlug: str | None = None
    description: str | None = None
    duration: str | None = None
    totalCreditsRequired: str | None = None
    catalogYear: int | None = None
    catalogVersion: str | None = None
    status: str = "published"


class DegreeRequirement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requirementGroupId: str
    programCode: str
    institutionId: str | None = None
    title: str | None = None
    requirementType: str | None = None
    minCredits: float | None = None
    courseReferences: list[dict[str, Any]] = Field(default_factory=list)
    ruleExpression: dict[str, Any] | None = None
    ruleIsExecutable: bool = True
    isMandatory: bool = True
    requirementEnforcement: str = "hard"
    enforceInGraduationProgress: bool = True
    advisoryOnly: bool = False
    catalogYear: int | None = None
    catalogVersion: str | None = None
    status: str = "published"


class AdvisoryCatalogRule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requirementGroupId: str
    programCode: str
    institutionId: str | None = None
    recordType: str | None = None
    title: str | None = None
    requirementType: str | None = None
    courseReferences: list[dict[str, Any]] = Field(default_factory=list)
    ruleExpression: dict[str, Any] | None = None
    notes: list[str] = Field(default_factory=list)
    advisoryOnly: bool = True
    enforceInGraduationProgress: bool = False
    notHardRequirement: bool = True
    manualReviewRequired: bool = True
    ruleIsExecutable: bool = False
    isMandatory: bool = False
    catalogYear: int | None = None
    catalogVersion: str | None = None
    status: str = "published"


class CatalogSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    program: DegreeProgram
    hardRequirements: list[DegreeRequirement]
    advisoryRules: list[AdvisoryCatalogRule]
    counts: dict[str, int]


class CourseListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(default=None, max_length=200)
    faculty: str | None = Field(default=None, max_length=200)
    courseNumber: str | None = Field(default=None, max_length=8)
    academicYear: int | None = Field(default=None, ge=1990, le=2100)
    semesterCode: int | None = None
    minCredits: float | None = Field(default=None, ge=0)
    maxCredits: float | None = Field(default=None, ge=0)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    includeOfferings: bool = False

    @field_validator("courseNumber")
    @classmethod
    def validate_course_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(COURSE_NUMBER_PATTERN, value):
            raise ValueError("courseNumber must be an 8-digit Technion course number")
        return value

    @field_validator("semesterCode")
    @classmethod
    def validate_semester_code(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value not in VALID_SEMESTER_CODES:
            raise ValueError("semesterCode must be one of 200, 201, 202")
        return value

    @model_validator(mode="after")
    def validate_semester_pair(self) -> "CourseListQuery":
        has_year = self.academicYear is not None
        has_code = self.semesterCode is not None
        if has_year ^ has_code:
            raise ValueError("academicYear and semesterCode must be provided together")
        return self


class CourseOfferingsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    academicYear: int | None = Field(default=None, ge=1990, le=2100)
    semesterCode: int | None = None

    @field_validator("semesterCode")
    @classmethod
    def validate_semester_code(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value not in VALID_SEMESTER_CODES:
            raise ValueError("semesterCode must be one of 200, 201, 202")
        return value
