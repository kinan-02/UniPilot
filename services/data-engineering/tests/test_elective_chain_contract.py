"""Regression tests for the shared elective chain contract."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app.config import get_settings
from app.importers.dds_catalog_staging_importer import (
    _remove_stale_faculty_staging_records,
    import_dds_catalog_to_staging,
    load_reviewed_catalog,
)
from app.promotion.dds_production_promoter import _retire_superseded_catalog_rules
from app.vault.elective_chain_contract import (
    _normalize_contract,
    _programs_by_code_and_track,
    _resolve_program_for_entry,
    _validate_pools_for_faculty,
    apply_elective_chain_violations,
    contracted_faculty_ids,
    faculty_contract,
    iter_contract_pools,
    load_elective_chain_contract,
    resolve_document_faculty,
    validate_elective_chain_export,
    validate_elective_chain_export_all_faculties,
    validate_staging_requirement_group,
)
from app.vault.export_dds_catalog import (
    _dne_starred_course_refs,
    _merge_unique_course_refs,
    export_vault_catalog,
)
from app.vault.loader import WikiPage, load_pages_by_slug, wiki_root

FIXTURE_CATALOG = Path(__file__).parent / "fixtures" / "dds_catalog_staging_import_catalog.json"
FIXTURE_READINESS_OK = Path(__file__).parent / "fixtures" / "dds_catalog_phase8_readiness_ok.json"


def test_contract_defines_all_ie_is_chain_pools():
    contract = load_elective_chain_contract()
    dds = contract.get("faculties", {}).get("dds", {})
    suffixes = {entry["suffix"] for entry in dds.get("pools") or []}
    assert "ie-focus-chain" not in suffixes
    assert {
        "ie-statistics-elective-chain",
        "ie-behavior-science-chain",
        "ie-focus-chain-game-theory",
        "ie-focus-chain-advanced-industry",
        "ie-focus-chain-operations-research",
        "is-behavior-science-chain",
        "is-focus-chain-performance",
        "is-focus-chain-ml",
        "is-focus-chain-game-theory",
    } <= suffixes


def test_contract_is_scoped_to_technion_dds():
    assert "dds" in contracted_faculty_ids()


def test_validation_skips_uncontracted_faculty_export():
    document = {
        "programs": [],
        "parserReport": {"faculty": "civil"},
    }
    assert validate_elective_chain_export(document) == []


def test_live_vault_export_satisfies_elective_chain_contract():
    document, readiness = export_vault_catalog(vault_path=wiki_root(), faculty="dds")
    violations = validate_elective_chain_export(document)
    assert violations == [], "\n".join(violations)
    assert readiness["canImportToStaging"] is True


def test_ie_focus_chains_do_not_include_group_four_course_flood():
    pages = load_pages_by_slug(wiki_root())
    from app.vault.export_dds_catalog import _iem_elective_groups

    iem = pages["track-industrial-engineering-management"]
    groups = {g["groupId"].split(":")[-1]: g for g in _iem_elective_groups(iem, "009009-1-000")}
    assert len(groups["ie-focus-chain-operations-research"]["courseReferences"]) <= 10
    assert len(groups["ie-focus-chain-game-theory"]["courseReferences"]) <= 10


def test_is_ml_chain_includes_dne_starred_sample():
    pages = load_pages_by_slug(wiki_root())
    from app.vault.export_dds_catalog import _is_elective_groups

    ise = pages["track-information-systems-engineering"]
    groups = {g["groupId"].split(":")[-1]: g for g in _is_elective_groups(ise, "009118-1-000", pages)}
    numbers = {ref["courseNumber"] for ref in groups["is-focus-chain-ml"]["courseReferences"]}
    assert "00970215" in numbers


def test_normalize_legacy_contract_without_faculties_key():
    raw = {
        "version": 1,
        "institutionId": "technion",
        "description": "legacy",
        "pools": [{"suffix": "ie-statistics-elective-chain"}],
        "deprecatedPoolSuffixes": ["ie-focus-chain"],
    }
    normalized = _normalize_contract(raw)
    assert normalized["faculties"]["dds"]["pools"] == [{"suffix": "ie-statistics-elective-chain"}]
    assert normalized["faculties"]["dds"]["deprecatedPoolSuffixes"] == ["ie-focus-chain"]


def test_resolve_document_faculty_sources():
    assert resolve_document_faculty({"parserReport": {"faculty": "DDS"}}) == "dds"
    assert resolve_document_faculty({"source": {"facultyId": "dds"}}) == "dds"
    assert (
        resolve_document_faculty({"programs": [{"metadata": {"faculty": "dds"}}]})
        == "dds"
    )
    assert resolve_document_faculty({}) is None


def test_iter_contract_pools_scoped_to_faculty():
    dds_pools = iter_contract_pools(faculty_id="dds")
    assert dds_pools
    assert all(pool.get("programCode") for pool in dds_pools)
    assert iter_contract_pools(faculty_id="unknown") == []


def test_faculty_contract_lookup():
    assert faculty_contract("dds") is not None
    assert faculty_contract("unknown") is None


def test_validate_elective_chain_export_without_faculty_returns_empty():
    assert validate_elective_chain_export({"programs": []}) == []


def test_validate_elective_chain_export_reports_contract_violations():
    document = {
        "programs": [
            {
                "programCode": "009009-1-000",
                "requirementGroups": [
                    {
                        "groupId": "009009-1-000:ie-focus-chain",
                        "ruleExpression": {"operator": "choose_chain"},
                        "courseReferences": [],
                    },
                    {
                        "groupId": "009009-1-000:ie-statistics-elective-chain",
                        "ruleExpression": {"operator": "wrong"},
                        "courseReferences": [{"courseNumber": "00940345"}],
                    },
                ],
            }
        ]
    }
    violations = validate_elective_chain_export(document, faculty_id="dds")
    assert any("deprecated pool still exported" in item for item in violations)
    assert any("operator=" in item for item in violations)
    assert any("course refs" in item for item in violations)
    assert any("missing catalogDescription" in item for item in violations)


def test_validate_elective_chain_export_missing_program_and_required_course():
    document = {"programs": []}
    missing_program = validate_elective_chain_export(document, faculty_id="dds")
    assert any("missing program" in item for item in missing_program)

    refs = [{"courseNumber": f"0094034{i}"} for i in range(20)]
    document = {
        "programs": [
            {
                "programCode": "009118-1-000",
                "requirementGroups": [
                    {
                        "groupId": "009118-1-000:is-focus-chain-ml",
                        "ruleExpression": {"operator": "choose_chain"},
                        "courseReferences": refs,
                        "catalogDescription": "ML chain",
                    }
                ],
            }
        ]
    }
    violations = validate_elective_chain_export(document, faculty_id="dds")
    assert any("missing required course" in item for item in violations)


def test_validate_elective_chain_export_all_faculties_and_apply_violations():
    document = {"programs": []}
    violations = validate_elective_chain_export_all_faculties(document)
    assert violations

    payload: dict = {"curationMetadata": {}, "curationReport": {}}
    apply_elective_chain_violations(payload, ["missing program 009009-1-000:ie-statistics-elective-chain"])
    assert payload["curationMetadata"]["unresolvedIssues"]
    assert payload["curationReport"]["warnings"]
    apply_elective_chain_violations(payload, [])
    apply_elective_chain_violations(payload, ["missing program 009009-1-000:ie-statistics-elective-chain"])


def test_validate_staging_requirement_group_contract_rules():
    assert validate_staging_requirement_group({"requirementGroup": {}}) == []
    assert validate_staging_requirement_group({"requirementGroup": {"groupId": "unknown:pool"}}) == []

    too_few = validate_staging_requirement_group(
        {
            "requirementGroup": {
                "groupId": "009009-1-000:ie-statistics-elective-chain",
                "courseReferences": [{"courseNumber": "00940345"}],
            }
        }
    )
    assert any("refs" in item for item in too_few)

    missing_description = validate_staging_requirement_group(
        {
            "requirementGroup": {
                "groupId": "009009-1-000:ie-statistics-elective-chain",
                "courseReferences": [{"courseNumber": f"0094034{i}"} for i in range(8)],
            }
        }
    )
    assert any("catalogDescription" in item for item in missing_description)

    mandatory_flag = validate_staging_requirement_group(
        {
            "requirementGroup": {
                "groupId": "009009-1-000:ie-statistics-elective-chain",
                "courseReferences": [{"courseNumber": f"0094034{i}"} for i in range(8)],
                "catalogDescription": "Statistics chain",
            },
            "treatsCoursesAsMandatory": True,
        }
    )
    assert any("treats chain courses as mandatory" in item for item in mandatory_flag)


def test_validate_elective_chain_export_resolves_shared_program_codes_by_track_slug():
    document = {
        "programs": [
            {
                "programCode": "013043-1-000",
                "metadata": {"wikiPage": "track-biology-general"},
                "requirementGroups": [
                    {
                        "groupId": "013043-1-000:biology-faculty-elective-list-pool",
                        "ruleExpression": {"operator": "choose_n"},
                        "courseReferences": [{"courseNumber": f"0134006{i}"} for i in range(7)],
                        "catalogDescription": "List A",
                    }
                ],
            },
            {
                "programCode": "013043-1-000",
                "metadata": {"wikiPage": "track-biology-human-development"},
                "requirementGroups": [
                    {
                        "groupId": "013043-1-000:biology-list-a1-pool",
                        "ruleExpression": {"operator": "choose_n"},
                        "courseReferences": [{"courseNumber": f"0134015{i}"} for i in range(3)],
                        "catalogDescription": "List A1",
                    }
                ],
            },
        ]
    }
    pools = [
        {
            "programCode": "013043-1-000",
            "trackSlug": "track-biology-general",
            "suffix": "biology-faculty-elective-list-pool",
            "operator": "choose_n",
            "minCourseRefs": 7,
            "maxCourseRefs": 7,
            "requiresCatalogDescription": True,
        },
        {
            "programCode": "013043-1-000",
            "trackSlug": "track-biology-human-development",
            "suffix": "biology-list-a1-pool",
            "operator": "choose_n",
            "minCourseRefs": 3,
            "maxCourseRefs": 3,
            "requiresCatalogDescription": True,
        },
    ]
    violations = _validate_pools_for_faculty(
        document,
        faculty_id="biology",
        pools=pools,
        deprecated=set(),
    )
    assert violations == []


def test_resolve_program_for_entry_falls_back_to_suffix_match_without_track_slug():
    document = {
        "programs": [
            {
                "programCode": "013043-1-000",
                "metadata": {"wikiPage": "track-a"},
                "requirementGroups": [],
            },
            {
                "programCode": "013043-1-000",
                "metadata": {"wikiPage": "track-b"},
                "requirementGroups": [
                    {
                        "groupId": "013043-1-000:biology-list-a-pool",
                        "ruleExpression": {"operator": "choose_n"},
                        "courseReferences": [{"courseNumber": "01340069"}],
                    }
                ],
            },
        ]
    }
    by_code, by_code_track = _programs_by_code_and_track(document)
    program = _resolve_program_for_entry(
        {
            "programCode": "013043-1-000",
            "suffix": "biology-list-a-pool",
        },
        by_code=by_code,
        by_code_track=by_code_track,
    )
    assert program is not None
    assert program["metadata"]["wikiPage"] == "track-b"


def test_validate_staging_requirement_group_matches_track_slug_when_codes_collide():
    entry = next(
        item
        for item in iter_contract_pools(faculty_id="biology")
        if item.get("trackSlug") == "track-biology-general"
        and item.get("suffix") == "biology-list-a-pool"
    )
    ref_count = int(entry["minCourseRefs"])
    violations = validate_staging_requirement_group(
        {
            "metadata": {"wikiPage": "track-biology-general"},
            "requirementGroup": {
                "groupId": "013043-1-000:biology-list-a-pool",
                "courseReferences": [
                    {"courseNumber": f"0134006{i}"} for i in range(ref_count)
                ],
                "catalogDescription": "Faculty electives",
            },
        }
    )
    assert violations == []


def test_validate_staging_requirement_group_biology_general_faculty_list_pool():
    violations = validate_staging_requirement_group(
        {
            "metadata": {"wikiPage": "track-biology-general"},
            "requirementGroup": {
                "groupId": "013043-1-000:biology-faculty-elective-list-pool",
                "courseReferences": [
                    {"courseNumber": f"0134006{i}"} for i in range(7)
                ],
                "catalogDescription": "Faculty electives",
            },
        }
    )
    assert violations == []


def test_validate_staging_requirement_group_skips_when_track_slug_mismatches():
    violations = validate_staging_requirement_group(
        {
            "metadata": {"wikiPage": "track-biology-general"},
            "requirementGroup": {
                "groupId": "013043-1-000:biology-list-a1-pool",
                "courseReferences": [{"courseNumber": "01340150"}],
                "catalogDescription": "List A1",
            },
        }
    )
    assert violations == []


def test_validate_staging_requirement_group_falls_back_to_single_contract_entry():
    violations = validate_staging_requirement_group(
        {
            "metadata": {"wikiPage": "track-unknown"},
            "requirementGroup": {
                "groupId": "009009-1-000:ie-statistics-elective-chain",
                "courseReferences": [{"courseNumber": f"0094034{i}"} for i in range(8)],
                "catalogDescription": "Statistics chain",
            },
        }
    )
    assert violations == []


def test_validate_deprecated_pool_entry_in_contract_list():
    document = {"programs": [{"programCode": "009009-1-000", "requirementGroups": []}]}
    violations = _validate_pools_for_faculty(
        document,
        faculty_id="dds",
        pools=[
            {
                "programCode": "009009-1-000",
                "suffix": "ie-focus-chain",
                "operator": "choose_chain",
            }
        ],
        deprecated={"ie-focus-chain"},
    )
    assert violations == ["deprecated pool still exported: 009009-1-000:ie-focus-chain"]


def test_dne_starred_course_refs_skips_unbuildable_reference(monkeypatch):
    dne = WikiPage(
        slug="track-data-information-engineering",
        path=Path("/tmp/dne.md"),
        frontmatter={},
        body="",
        english_body="""## DNE Elective Course List
| code | name | credits |
|------|------|---------|
| 00970215 | * ML Project | 3 |
""",
    )

    def _reject_reference(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.vault.export_dds_catalog.build_course_reference",
        _reject_reference,
    )
    assert _dne_starred_course_refs({"track-data-information-engineering": dne}) == []


def test_merge_unique_course_refs_skips_empty_and_duplicate_numbers():
    merged = _merge_unique_course_refs(
        [{"courseNumber": "00940345"}, {"courseNumber": ""}, {"courseNumber": None}],
        [{"courseNumber": "00940345"}, {"courseNumber": "01040031"}],
    )
    numbers = [ref["courseNumber"] for ref in merged]
    assert numbers == ["00940345", "01040031"]


def test_dne_starred_course_refs_fallback_and_table_branches():
    fallback_refs = _dne_starred_course_refs({})
    assert fallback_refs

    dne = WikiPage(
        slug="track-data-information-engineering",
        path=Path("/tmp/dne.md"),
        frontmatter={},
        body="",
        english_body="No DNE elective section here.",
    )
    assert _dne_starred_course_refs({"track-data-information-engineering": dne}) == []

    table_body = """## DNE Elective Course List
| code | name | credits |
|------|------|---------|
| bad-code | * Invalid | 3 |
| 00970215 | * ML Project | 3 |
| 00970215 | * Duplicate | 3 |
"""
    dne_with_table = WikiPage(
        slug="track-data-information-engineering",
        path=Path("/tmp/dne.md"),
        frontmatter={},
        body="",
        english_body=table_body,
    )
    refs = _dne_starred_course_refs({"track-data-information-engineering": dne_with_table})
    numbers = [ref["courseNumber"] for ref in refs]
    assert numbers.count("00970215") == 1


def test_remove_stale_dds_staging_records_and_retire_superseded_rules():
    settings = get_settings()
    database = MagicMock()
    active_keys = {f"technion-dds:catalog:2025-2026:program:009216-1-000"}
    stale_key = "technion-dds:catalog:2025-2026:requirement:stale-group"
    collection = MagicMock()
    collection.find.return_value = [{"stagingKey": stale_key}]
    delete_result = MagicMock(deleted_count=1)
    collection.delete_many.return_value = delete_result
    database.__getitem__.return_value = collection

    removed = _remove_stale_faculty_staging_records(
        database,
        settings=settings,
        faculty_id="dds",
        catalog_version="2025-2026",
        active_staging_keys=active_keys,
    )
    assert removed == 5
    assert collection.delete_many.call_count == 5

    assert (
        _retire_superseded_catalog_rules(
            database,
            settings=settings,
            planned_production_keys=set(),
            catalog_version="2025-2026",
            catalog_source_name="technion-dds-catalog",
        )
        == 0
    )


def test_import_removes_stale_staging_records(mongo_database):
    settings = get_settings()
    import_dds_catalog_to_staging(
        mongo_database,
        catalog_path=FIXTURE_CATALOG,
        readiness_path=FIXTURE_READINESS_OK,
        settings=settings,
    )
    catalog_version = load_reviewed_catalog(FIXTURE_CATALOG).source.catalogVersion
    stale_key = f"technion-dds:catalog:{catalog_version}:requirement:stale-group"
    mongo_database[settings.staging_degree_requirements_collection].insert_one(
        {
            "stagingKey": stale_key,
            "requirementGroup": {"groupId": "stale-group"},
        }
    )
    import_dds_catalog_to_staging(
        mongo_database,
        catalog_path=FIXTURE_CATALOG,
        readiness_path=FIXTURE_READINESS_OK,
        settings=settings,
    )
    assert (
        mongo_database[settings.staging_degree_requirements_collection].find_one(
            {"stagingKey": stale_key}
        )
        is None
    )
