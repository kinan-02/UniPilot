"""Unit tests for app/vault/verify_vault_production_parity.py (78% → ~95%)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.vault.verify_vault_production_parity import (
    GroupSnapshot,
    ParityMismatch,
    VaultProductionParityResult,
    _normalize_credits,
    _course_refs_from_group,
    _course_refs_from_production,
    _snapshot_from_vault_group,
    _snapshot_from_production_doc,
    compare_group_snapshots,
    extract_catalog_signoff_from_document,
    render_parity_markdown,
    write_parity_report,
    default_parity_report_json_path,
    default_parity_report_md_path,
)


# ---------------------------------------------------------------------------
# _normalize_credits
# ---------------------------------------------------------------------------

class TestNormalizeCredits:
    def test_none_returns_none(self):
        assert _normalize_credits(None) is None

    def test_int_converts(self):
        assert _normalize_credits(3) == 3.0

    def test_float_rounds_to_2dp(self):
        assert _normalize_credits(3.1415926) == 3.14

    def test_string_number_converts(self):
        assert _normalize_credits("4.5") == 4.5

    def test_invalid_string_returns_none(self):
        assert _normalize_credits("not-a-number") is None

    def test_empty_string_returns_none(self):
        assert _normalize_credits("") is None


# ---------------------------------------------------------------------------
# _course_refs_from_group / _course_refs_from_production
# ---------------------------------------------------------------------------

class TestCourseRefsFromGroup:
    def test_empty_course_references(self):
        group = {}
        assert _course_refs_from_group(group) == ()

    def test_refs_sorted_by_course_number(self):
        group = {
            "courseReferences": [
                {"courseNumber": "09876543", "creditsHint": 3.0},
                {"courseNumber": "01234567", "creditsHint": None},
            ]
        }
        refs = _course_refs_from_group(group)
        assert refs[0][0] == "01234567"
        assert refs[1][0] == "09876543"

    def test_skips_entries_without_course_number(self):
        group = {"courseReferences": [{"creditsHint": 2.0}]}
        assert _course_refs_from_group(group) == ()

    def test_credits_hint_normalized(self):
        group = {"courseReferences": [{"courseNumber": "01234567", "creditsHint": "3"}]}
        refs = _course_refs_from_group(group)
        assert refs[0] == ("01234567", 3.0)


class TestCourseRefsFromProduction:
    def test_empty_returns_empty_tuple(self):
        assert _course_refs_from_production({}) == ()

    def test_refs_sorted_by_course_number(self):
        doc = {
            "courseReferences": [
                {"courseNumber": "09000000"},
                {"courseNumber": "01000000"},
            ]
        }
        refs = _course_refs_from_production(doc)
        assert refs[0][0] == "01000000"

    def test_skips_missing_course_number(self):
        doc = {"courseReferences": [{"creditsHint": 3}]}
        assert _course_refs_from_production(doc) == ()


# ---------------------------------------------------------------------------
# _snapshot_from_vault_group / _snapshot_from_production_doc
# ---------------------------------------------------------------------------

class TestSnapshotFromVaultGroup:
    def test_basic_snapshot(self):
        group = {
            "groupId": "G001",
            "title": "Core Courses",
            "requirementType": "mandatory",
            "minCredits": 30.0,
            "ruleExpression": {"type": "and", "operator": "all", "minCredits": None, "semester": None},
            "courseReferences": [],
        }
        snap = _snapshot_from_vault_group(group, "PROG001", "hard")
        assert snap.group_id == "G001"
        assert snap.program_code == "PROG001"
        assert snap.classification == "hard"
        assert snap.title == "Core Courses"
        assert snap.min_credits == 30.0

    def test_effective_min_credits_from_top_level(self):
        group = {
            "groupId": "G1",
            "minCredits": 15.0,
            "ruleExpression": {"minCredits": 10.0},
            "courseReferences": [],
        }
        snap = _snapshot_from_vault_group(group, "P", "advisory")
        assert snap.min_credits == 15.0

    def test_effective_min_from_rule_when_top_none(self):
        group = {
            "groupId": "G2",
            "ruleExpression": {"minCredits": 8.0},
            "courseReferences": [],
        }
        snap = _snapshot_from_vault_group(group, "P", "hard")
        assert snap.min_credits == 8.0


class TestSnapshotFromProductionDoc:
    def test_basic_production_snapshot(self):
        doc = {
            "requirementGroupId": "G001",
            "programCode": "P001",
            "title": "Electives",
            "requirementType": "elective",
            "minCredits": 12.0,
            "ruleExpression": {"type": "or", "operator": "min"},
            "courseReferences": [],
        }
        snap = _snapshot_from_production_doc(doc, "hard")
        assert snap.group_id == "G001"
        assert snap.program_code == "P001"
        assert snap.classification == "hard"


# ---------------------------------------------------------------------------
# compare_group_snapshots
# ---------------------------------------------------------------------------

def _make_snap(group_id="G1", **kwargs) -> GroupSnapshot:
    defaults = dict(
        group_id=group_id,
        program_code="P001",
        classification="hard",
        title="Test Group",
        requirement_type="mandatory",
        min_credits=10.0,
        rule_type="and",
        rule_operator="all",
        rule_min_credits=None,
        rule_semester=None,
        course_numbers=("01234567",),
        course_refs=(("01234567", 3.0),),
    )
    defaults.update(kwargs)
    return GroupSnapshot(**defaults)


class TestCompareGroupSnapshots:
    def test_identical_snapshots_no_mismatches(self):
        snap = _make_snap()
        mismatches = compare_group_snapshots(snap, snap)
        assert mismatches == []

    def test_classification_mismatch(self):
        expected = _make_snap(classification="hard")
        actual = _make_snap(classification="advisory")
        mismatches = compare_group_snapshots(expected, actual)
        fields = [m.field for m in mismatches]
        assert "classification" in fields

    def test_title_mismatch(self):
        expected = _make_snap(title="Old Title")
        actual = _make_snap(title="New Title")
        mismatches = compare_group_snapshots(expected, actual)
        assert any(m.field == "title" for m in mismatches)

    def test_min_credits_mismatch(self):
        expected = _make_snap(min_credits=10.0)
        actual = _make_snap(min_credits=12.0)
        mismatches = compare_group_snapshots(expected, actual)
        assert any(m.field == "minCredits" for m in mismatches)

    def test_course_numbers_mismatch(self):
        expected = _make_snap(course_numbers=("01234567",))
        actual = _make_snap(course_numbers=("09876543",))
        mismatches = compare_group_snapshots(expected, actual)
        assert any(m.field == "courseNumbers" for m in mismatches)


# ---------------------------------------------------------------------------
# extract_catalog_signoff_from_document
# ---------------------------------------------------------------------------

class TestExtractCatalogSignoffFromDocument:
    def test_returns_vault_signoff(self):
        doc = {"curationReport": {"vaultSignoff": {"signedOffBy": "vault"}}}
        result = extract_catalog_signoff_from_document(doc)
        assert result["signedOffBy"] == "vault"

    def test_returns_empty_when_no_report(self):
        doc = {}
        result = extract_catalog_signoff_from_document(doc)
        assert result == {}

    def test_returns_empty_when_no_vault_signoff(self):
        doc = {"curationReport": {"humanSignoff": {"signedOffBy": "human"}}}
        result = extract_catalog_signoff_from_document(doc)
        assert result == {}


# ---------------------------------------------------------------------------
# VaultProductionParityResult.ok property
# ---------------------------------------------------------------------------

class TestVaultProductionParityResultOk:
    def test_pass_status_is_ok(self):
        result = VaultProductionParityResult(
            status="pass",
            wiki_root="/wiki",
            exported_at="2025-01-01",
            expected_hard_count=1,
            expected_advisory_count=0,
            production_hard_count=1,
            production_advisory_count=0,
        )
        assert result.ok is True

    def test_fail_status_not_ok(self):
        result = VaultProductionParityResult(
            status="fail",
            wiki_root="/wiki",
            exported_at="2025-01-01",
            expected_hard_count=1,
            expected_advisory_count=0,
            production_hard_count=0,
            production_advisory_count=0,
        )
        assert result.ok is False


# ---------------------------------------------------------------------------
# render_parity_markdown
# ---------------------------------------------------------------------------

class TestRenderParityMarkdown:
    def _make_result(self, status="pass", **kwargs):
        defaults = dict(
            status=status,
            wiki_root="/wiki/root",
            exported_at="2025-01-01T00:00:00+00:00",
            expected_hard_count=5,
            expected_advisory_count=3,
            production_hard_count=5,
            production_advisory_count=3,
            missing_in_production=[],
            extra_in_production=[],
            classification_mismatches=[],
            field_mismatches=[],
            matched_groups=8,
        )
        defaults.update(kwargs)
        return VaultProductionParityResult(**defaults)

    def test_pass_status_includes_success_message(self):
        result = self._make_result("pass")
        md = render_parity_markdown(result)
        assert "PASS" in md
        assert "All requirement groups" in md

    def test_fail_status_included(self):
        result = self._make_result("fail")
        md = render_parity_markdown(result)
        assert "FAIL" in md

    def test_missing_in_production_listed(self):
        result = self._make_result("fail", missing_in_production=["G001", "G002"])
        md = render_parity_markdown(result)
        assert "G001" in md
        assert "G002" in md
        assert "Missing in production" in md

    def test_extra_in_production_listed(self):
        result = self._make_result("fail", extra_in_production=["X001"])
        md = render_parity_markdown(result)
        assert "X001" in md
        assert "Extra in production" in md

    def test_classification_mismatches_listed(self):
        result = self._make_result("fail", classification_mismatches=["G003"])
        md = render_parity_markdown(result)
        assert "G003" in md
        assert "Classification mismatches" in md

    def test_field_mismatches_listed(self):
        mismatch = ParityMismatch(
            group_id="G004",
            program_code="P001",
            field="title",
            expected="Old",
            actual="New",
        )
        result = self._make_result("fail", field_mismatches=[mismatch])
        md = render_parity_markdown(result)
        assert "G004" in md
        assert "title" in md

    def test_many_field_mismatches_truncated(self):
        mismatches = [
            ParityMismatch(f"G{i:03d}", "P001", "title", "old", "new") for i in range(60)
        ]
        result = self._make_result("fail", field_mismatches=mismatches)
        md = render_parity_markdown(result)
        assert "more" in md

    def test_counts_table_included(self):
        result = self._make_result()
        md = render_parity_markdown(result)
        assert "Hard requirements" in md
        assert "Advisory rules" in md


# ---------------------------------------------------------------------------
# write_parity_report
# ---------------------------------------------------------------------------

class TestWriteParityReport:
    def _make_result(self):
        return VaultProductionParityResult(
            status="pass",
            wiki_root="/wiki",
            exported_at="2025-01-01",
            expected_hard_count=2,
            expected_advisory_count=1,
            production_hard_count=2,
            production_advisory_count=1,
            matched_groups=3,
        )

    def test_writes_json_and_md_files(self, tmp_path):
        result = self._make_result()
        json_path = tmp_path / "report.json"
        md_path = tmp_path / "report.md"

        out_json, out_md = write_parity_report(result, json_path=json_path, md_path=md_path)

        assert out_json == json_path
        assert out_md == md_path
        assert json_path.exists()
        assert md_path.exists()

    def test_json_content_valid(self, tmp_path):
        result = self._make_result()
        json_path = tmp_path / "r.json"
        md_path = tmp_path / "r.md"

        write_parity_report(result, json_path=json_path, md_path=md_path)

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["status"] == "pass"
        assert payload["counts"]["matchedGroups"] == 3
        assert payload["missingInProduction"] == []

    def test_creates_parent_dirs_if_needed(self, tmp_path):
        result = self._make_result()
        nested_json = tmp_path / "deep" / "nested" / "r.json"
        nested_md = tmp_path / "deep" / "nested" / "r.md"

        write_parity_report(result, json_path=nested_json, md_path=nested_md)

        assert nested_json.exists()

    def test_default_paths_used_when_none(self, tmp_path):
        result = self._make_result()
        with patch(
            "app.vault.verify_vault_production_parity.default_parity_report_json_path",
            return_value=tmp_path / "default.json",
        ), patch(
            "app.vault.verify_vault_production_parity.default_parity_report_md_path",
            return_value=tmp_path / "default.md",
        ):
            out_json, out_md = write_parity_report(result)

        assert out_json == tmp_path / "default.json"


# ---------------------------------------------------------------------------
# default path helpers
# ---------------------------------------------------------------------------

class TestDefaultPaths:
    def test_json_path_is_path_object(self):
        p = default_parity_report_json_path()
        assert isinstance(p, Path)
        assert p.suffix == ".json"

    def test_md_path_is_path_object(self):
        p = default_parity_report_md_path()
        assert isinstance(p, Path)
        assert p.suffix == ".md"
