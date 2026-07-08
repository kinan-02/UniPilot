"""Validate a reasoning result dict against a caller-supplied JSON schema."""

from __future__ import annotations

from typing import Any

import jsonschema
from jsonschema.exceptions import SchemaError

from app.agent_core.reasoning.schemas import SchemaValidationResult


def _format_error(error: jsonschema.exceptions.ValidationError) -> str:
    path = ".".join(str(part) for part in error.absolute_path) or "<root>"
    return f"{path}: {error.message}"


def validate_against_schema(result: Any, schema: dict[str, Any]) -> SchemaValidationResult:
    """Validate `result` against `schema` (JSON Schema draft supported by `jsonschema`).

    Detects: non-dict/invalid shape, missing required fields, wrong field
    types, invalid enum values, and additional-properties violations when the
    schema forbids them.
    """
    if result is None:
        return SchemaValidationResult(valid=False, errors=["result_is_missing"])
    if not isinstance(result, dict):
        return SchemaValidationResult(valid=False, errors=["result_must_be_a_json_object"])

    try:
        validator_cls = jsonschema.validators.validator_for(schema)
        validator_cls.check_schema(schema)
    except SchemaError as exc:
        return SchemaValidationResult(valid=False, errors=[f"invalid_output_schema: {exc.message}"])

    validator = validator_cls(schema)
    errors = sorted(validator.iter_errors(result), key=lambda error: list(error.absolute_path))
    if not errors:
        return SchemaValidationResult(valid=True)
    return SchemaValidationResult(valid=False, errors=[_format_error(error) for error in errors])
