"""Unit tests for app/curation/catalog_signoff.py (62% → ~100%)."""

from __future__ import annotations

from app.curation.catalog_signoff import (
    SIGNOFF_SOURCE_HUMAN,
    SIGNOFF_SOURCE_VAULT,
    extract_catalog_signoff,
    extract_human_signoff_from_staged_programs,
    signoff_source_label,
)


class TestExtractCatalogSignoff:
    def test_returns_empty_dict_for_empty_list(self):
        assert extract_catalog_signoff([]) == {}

    def test_returns_empty_dict_when_no_curation_report(self):
        programs = [{"programCode": "P001"}]
        assert extract_catalog_signoff(programs) == {}

    def test_returns_empty_dict_when_report_not_dict(self):
        programs = [{"curationReport": "invalid"}]
        assert extract_catalog_signoff(programs) == {}

    def test_returns_vault_signoff_when_present(self):
        vault = {"signedOffBy": "vault-wiki", "signoffSource": "vault-wiki"}
        programs = [{"curationReport": {"vaultSignoff": vault}}]
        result = extract_catalog_signoff(programs)
        assert result == vault

    def test_returns_human_signoff_when_vault_missing(self):
        human = {"signedOffBy": "john.doe", "date": "2025-01-01"}
        programs = [{"curationReport": {"humanSignoff": human}}]
        result = extract_catalog_signoff(programs)
        assert result == human

    def test_vault_takes_precedence_over_human(self):
        vault = {"signedOffBy": "vault-wiki"}
        human = {"signedOffBy": "john.doe"}
        programs = [{"curationReport": {"vaultSignoff": vault, "humanSignoff": human}}]
        result = extract_catalog_signoff(programs)
        assert result == vault

    def test_skips_programs_without_signed_off_by(self):
        programs = [
            {"curationReport": {"vaultSignoff": {"note": "not signed"}}},
            {"curationReport": {"humanSignoff": {"signedOffBy": "jane"}}},
        ]
        result = extract_catalog_signoff(programs)
        assert result["signedOffBy"] == "jane"

    def test_skips_vault_without_signed_off_by_falls_through_to_human(self):
        vault = {"someField": "no signedOffBy"}
        human = {"signedOffBy": "backup"}
        programs = [{"curationReport": {"vaultSignoff": vault, "humanSignoff": human}}]
        result = extract_catalog_signoff(programs)
        assert result["signedOffBy"] == "backup"

    def test_merges_vault_signoffs_across_programs(self):
        programs = [
            {"curationReport": {}},
            {
                "curationReport": {
                    "vaultSignoff": {
                        "signedOffBy": "vault-wiki",
                        "signedOffNonExecutableRuleGroupIds": ["a:group-1"],
                        "productionExcludedCourseNumbers": ["00000001"],
                    }
                }
            },
            {
                "curationReport": {
                    "vaultSignoff": {
                        "signedOffBy": "vault-wiki",
                        "signedOffNonExecutableRuleGroupIds": ["a:group-2", "a:group-1"],
                        "productionExcludedCourseNumbers": ["00000002"],
                    }
                }
            },
        ]
        result = extract_catalog_signoff(programs)
        assert result["signedOffBy"] == "vault-wiki"
        assert result["signedOffNonExecutableRuleGroupIds"] == ["a:group-1", "a:group-2"]
        assert result["productionExcludedCourseNumbers"] == ["00000001", "00000002"]


class TestExtractHumanSignoffAlias:
    def test_alias_returns_same_as_extract_catalog_signoff(self):
        programs: list = []
        assert extract_human_signoff_from_staged_programs(programs) == extract_catalog_signoff(programs)

    def test_alias_with_human_signoff(self):
        human = {"signedOffBy": "alice"}
        programs = [{"curationReport": {"humanSignoff": human}}]
        assert extract_human_signoff_from_staged_programs(programs) == human


class TestSignoffSourceLabel:
    def test_vault_source_field_returns_vault_label(self):
        signoff = {"signoffSource": SIGNOFF_SOURCE_VAULT}
        assert signoff_source_label(signoff) == "vaultSignoff"

    def test_signed_off_by_vault_wiki_returns_vault_label(self):
        signoff = {"signedOffBy": SIGNOFF_SOURCE_VAULT}
        assert signoff_source_label(signoff) == "vaultSignoff"

    def test_human_signoff_returns_human_label(self):
        signoff = {"signedOffBy": "john.doe"}
        assert signoff_source_label(signoff) == "humanSignoff"

    def test_empty_signoff_returns_human_label(self):
        assert signoff_source_label({}) == "humanSignoff"

    def test_unknown_source_returns_human_label(self):
        signoff = {"signoffSource": "legacy", "signedOffBy": "someone"}
        assert signoff_source_label(signoff) == "humanSignoff"
