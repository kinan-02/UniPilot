from dataclasses import dataclass, field

from pydantic import ValidationError

from app.models.normalized_course import NormalizedCourse


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)


def validate_normalized_course(record: dict) -> ValidationResult:
    try:
        NormalizedCourse.model_validate(record)
        return ValidationResult(is_valid=True)
    except ValidationError as exc:
        return ValidationResult(
            is_valid=False,
            errors=[error.get("msg", "Validation failed") for error in exc.errors()],
        )
