"""Normalizer stubs for future Technion DDS source ingestion."""

from typing import Any


def normalize_technion_dds_course(raw_record: dict[str, Any]) -> dict[str, Any]:
    """Placeholder for future Technion DDS course normalization.

    Real PDF/HTML/CSV parsers will live under app/sources/ and call into this module.
    """
    raise NotImplementedError(
        "Technion DDS course normalization is not implemented yet. "
        "Use sample ingestion commands for foundation testing."
    )


def normalize_technion_dds_degree_requirement(raw_record: dict[str, Any]) -> dict[str, Any]:
    """Placeholder for future Technion DDS degree requirement normalization."""
    raise NotImplementedError(
        "Technion DDS degree requirement normalization is not implemented yet. "
        "Use sample ingestion commands for foundation testing."
    )
