from pydantic import ValidationError

from app.models.normalized_degree_requirement import NormalizedDegreeRequirement
from app.validators.course_validator import ValidationResult


def validate_normalized_degree_requirement(record: dict) -> ValidationResult:
    try:
        NormalizedDegreeRequirement.model_validate(record)
        return ValidationResult(is_valid=True)
    except ValidationError as exc:
        return ValidationResult(
            is_valid=False,
            errors=[error.get("msg", "Validation failed") for error in exc.errors()],
        )
