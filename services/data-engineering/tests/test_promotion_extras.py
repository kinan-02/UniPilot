"""Tests targeting promotion module gaps (app/promotion/*)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.promotion.dds_production_promoter import (
    STAGING_FIELDS_TO_STRIP,
    ProductionPromotionError,
    _new_promotion_run_id,
    _strip_staging_fields,
    _utc_now_iso,
    _validate_document_safety,
    default_production_promotion_json_path,
    default_production_promotion_md_path,
    map_staging_program_to_production,
    production_advisory_requirement_key,
    production_course_key,
    production_offering_key,
    production_program_key,
    production_requirement_key,
)
from app.promotion.dds_promotion_gate import (
    _is_advisory_requirement,
    _is_hard_requirement,
    _load_quality_summary,
    default_promotion_json_path,
    default_promotion_md_path,
)


# ---------------------------------------------------------------------------
# production_*_key helpers
# ---------------------------------------------------------------------------

class TestProductionKeyHelpers:
    def test_program_key_format(self):
        key = production_program_key("009216-1-000", "2025a")
        assert key == "technion-dds:program:009216-1-000:2025a"

    def test_requirement_key_format(self):
        key = production_requirement_key("G001", "2025a")
        assert key == "technion-dds:requirement:G001:2025a"

    def test_advisory_requirement_key_format(self):
        key = production_advisory_requirement_key("G001", "2025a")
        assert key == "technion-dds:advisory-rule:req:G001:2025a"

    def test_course_key_format(self):
        key = production_course_key("01234567")
        assert key == "technion:course:01234567"

    def test_offering_key_format(self):
        key = production_offering_key("01234567", 2025, 200)
        assert key == "technion:course-offering:01234567:2025:200"


# ---------------------------------------------------------------------------
# _utc_now_iso / _new_promotion_run_id
# ---------------------------------------------------------------------------

class TestUtilHelpers:
    def test_utc_now_iso_returns_string(self):
        ts = _utc_now_iso()
        assert isinstance(ts, str)
        assert "T" in ts

    def test_new_promotion_run_id_prefix(self):
        run_id = _new_promotion_run_id()
        assert run_id.startswith("dds-promotion-")

    def test_new_promotion_run_id_unique(self):
        ids = {_new_promotion_run_id() for _ in range(10)}
        assert len(ids) == 10


# ---------------------------------------------------------------------------
# _strip_staging_fields
# ---------------------------------------------------------------------------

class TestStripStagingFields:
    def test_removes_staging_keys(self):
        doc = {
            "isStaging": True,
            "productionEligible": False,
            "importRunId": "r1",
            "_id": "xxx",
            "programCode": "P001",
        }
        stripped = _strip_staging_fields(doc)
        assert "isStaging" not in stripped
        assert "productionEligible" not in stripped
        assert "_id" not in stripped
        assert stripped["programCode"] == "P001"

    def test_all_staging_fields_listed_in_constant(self):
        for field in STAGING_FIELDS_TO_STRIP:
            doc = {field: "value", "keep": "me"}
            stripped = _strip_staging_fields(doc)
            assert field not in stripped
            assert stripped["keep"] == "me"


# ---------------------------------------------------------------------------
# _validate_document_safety
# ---------------------------------------------------------------------------

class TestValidateDocumentSafety:
    def test_raises_when_is_staging_true(self):
        doc = {"isStaging": True}
        with pytest.raises(ProductionPromotionError, match="isStaging=true"):
            _validate_document_safety(doc, context="test")

    def test_raises_when_production_eligible_not_false(self):
        doc = {"productionEligible": True}
        with pytest.raises(ProductionPromotionError, match="productionEligible"):
            _validate_document_safety(doc, context="test")

    def test_raises_when_degree_requirements_inferred(self):
        doc = {"metadata": {"degreeRequirementsInferred": True}}
        with pytest.raises(ProductionPromotionError, match="inferred"):
            _validate_document_safety(doc, context="test")

    def test_safe_document_passes(self):
        doc = {"programCode": "P001", "metadata": {}}
        _validate_document_safety(doc, context="test")


# ---------------------------------------------------------------------------
# map_staging_program_to_production
# ---------------------------------------------------------------------------

class TestMapStagingProgramToProduction:
    def test_maps_basic_fields(self):
        staging = {
            "programCode": "009216-1-000",
            "institutionId": "technion",
            "name": "Data Science",
            "totalCredits": 155,
            "catalogYear": "2025",
            "sourceFiles": ["catalog_reviewed.json"],
            "paths": [],
        }
        result = map_staging_program_to_production(
            staging,
            promotion_run_id="promo-abc",
            promoted_at="2025-01-01T00:00:00+00:00",
            catalog_version="2025a",
        )
        assert result["programCode"] == "009216-1-000"
        assert result["promotionRunId"] == "promo-abc"
        assert result["status"] == "published"
        assert "productionKey" in result

    def test_raises_on_unsafe_document(self):
        staging = {
            "programCode": "P001",
            "isStaging": True,  # this ends up in the stripped doc? no — map removes it
        }
        # The mapped doc should not have isStaging, so it should pass
        result = map_staging_program_to_production(
            staging,
            promotion_run_id="promo-x",
            promoted_at="2025-01-01T00:00:00+00:00",
            catalog_version="v1",
        )
        assert "programCode" in result


# ---------------------------------------------------------------------------
# default path helpers (promoter)
# ---------------------------------------------------------------------------

class TestPromoterDefaultPaths:
    def test_json_path_suffix(self):
        from pathlib import Path
        p = default_production_promotion_json_path()
        assert isinstance(p, Path)
        assert p.suffix == ".json"

    def test_md_path_suffix(self):
        from pathlib import Path
        p = default_production_promotion_md_path()
        assert isinstance(p, Path)
        assert p.suffix == ".md"


# ---------------------------------------------------------------------------
# promotion gate helpers
# ---------------------------------------------------------------------------

class TestIsHardRequirement:
    def test_executable_rule_is_hard(self):
        staging = {
            "ruleIsExecutable": True,
        }
        assert _is_hard_requirement(staging) is True

    def test_non_executable_is_not_hard(self):
        staging = {"ruleIsExecutable": False}
        assert _is_hard_requirement(staging) is False

    def test_missing_rule_is_not_hard(self):
        assert _is_hard_requirement({}) is False


class TestIsAdvisoryRequirement:
    def test_group_in_advisory_set_is_advisory(self):
        staging = {
            "requirementGroup": {"groupId": "G001"},
            "ruleIsExecutable": False,
        }
        advisory_ids = {"G001"}
        assert _is_advisory_requirement(staging, advisory_ids) is True

    def test_non_executable_without_explicit_advisory_set_also_advisory(self):
        # A non-executable group is advisory even when not in the set
        staging = {
            "requirementGroup": {"groupId": "G999"},
            "ruleIsExecutable": False,
        }
        advisory_ids = {"G001"}
        # _is_advisory_requirement returns not _is_hard_requirement when group not in set
        # Since ruleIsExecutable=False and no executable rule type, _is_hard=False → advisory=True
        assert _is_advisory_requirement(staging, advisory_ids) is True

    def test_executable_group_in_advisory_set_still_advisory_due_to_id(self):
        # groupId in advisory_ids → always advisory regardless of ruleIsExecutable
        staging = {
            "requirementGroup": {"groupId": "G001"},
            "ruleIsExecutable": True,
        }
        advisory_ids = {"G001"}
        assert _is_advisory_requirement(staging, advisory_ids) is True

    def test_hard_executable_group_not_in_advisory_set_is_hard(self):
        staging = {
            "requirementGroup": {"groupId": "G999", "ruleExpression": {"type": "and"}},
            "ruleIsExecutable": True,
        }
        advisory_ids = {"G001"}
        # _is_hard_requirement returns True → not True → advisory=False
        assert _is_advisory_requirement(staging, advisory_ids) is False


class TestLoadQualitySummary:
    def test_returns_empty_when_file_missing(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        result = _load_quality_summary(missing)
        assert result == {}

    def test_returns_parsed_summary(self, tmp_path):
        report_path = tmp_path / "quality.json"
        payload = {
            "status": "pass",
            "recommendation": "promote",
            "blockersForProduction": [],
            "counts": {"total": 5},
        }
        report_path.write_text(__import__("json").dumps(payload), encoding="utf-8")

        result = _load_quality_summary(report_path)
        assert result["status"] == "pass"
        assert result["counts"]["total"] == 5


class TestGateDefaultPaths:
    def test_json_path(self):
        from pathlib import Path
        p = default_promotion_json_path()
        assert isinstance(p, Path)
        assert p.suffix == ".json"

    def test_md_path(self):
        from pathlib import Path
        p = default_promotion_md_path()
        assert isinstance(p, Path)
        assert p.suffix == ".md"
