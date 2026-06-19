import pytest
from pydantic import ValidationError

from app.models.normalized_degree_requirement import NormalizedDegreeRequirement
from app.sources.sample_data import SAMPLE_DEGREE_REQUIREMENTS
from app.validators.degree_requirement_validator import validate_normalized_degree_requirement


def test_sample_degree_requirement_records_are_valid():
    for record in SAMPLE_DEGREE_REQUIREMENTS:
        result = validate_normalized_degree_requirement(record)
        assert result.is_valid is True


def test_normalized_degree_requirement_rejects_invalid_type():
    record = {
        **SAMPLE_DEGREE_REQUIREMENTS[0],
        "requirementType": "unknown",
    }

    with pytest.raises(ValidationError):
        NormalizedDegreeRequirement.model_validate(record)


def test_normalized_degree_requirement_rejects_invalid_degree_id():
    record = {
        **SAMPLE_DEGREE_REQUIREMENTS[0],
        "degreeId": "bad-id",
    }

    result = validate_normalized_degree_requirement(record)
    assert result.is_valid is False
