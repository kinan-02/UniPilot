"""Tests for the Postgres->Mongo constraint translation.

These pin the decisions that make the translation *safe* rather than merely
mechanical. Each one corresponds to a way the port could quietly go wrong and
reject correct data, which on a collection of 1,386 real users is the expensive
direction to fail in.
"""

from __future__ import annotations

import pytest

from app.db.schema_constraints import (
    ALL_RULES,
    COMPLETED_COURSES,
    COURSES,
    NUMBER,
    REFERENCES,
    STUDENT_PROFILES,
    UNIQUE_INDEXES,
    CollectionRules,
    FieldRule,
    all_plans,
    plan_for,
)


class TestNullability:
    """`not null` is the only thing that becomes `required`."""

    def test_a_required_field_does_not_admit_null(self):
        rule = FieldRule("courseNumber", ("string",), required=True)
        assert "null" not in rule.json_schema()["bsonType"]

    def test_an_optional_field_admits_null(self):
        """A nullable Postgres column holds NULL; the Mongo equivalent must too,
        or every row that legitimately has none is a violation."""
        rule = FieldRule("title", ("string",))
        assert "null" in rule.json_schema()["bsonType"]

    def test_optional_fields_are_absent_from_required(self):
        assert "title" not in COURSES.required
        assert "courseNumber" in COURSES.required

    def test_program_slug_is_not_required(self):
        """918 of 1,000 live profiles do not carry it, and schema.sql leaves it
        nullable. Requiring it would fail 92% of the collection, which describes
        a broken rule rather than broken data."""
        assert "programSlug" not in STUDENT_PROFILES.required


class TestTypesMatchWhatMongoActuallyStores:
    """The DDL renders everything as Postgres types; Mongo stores BSON. These
    were sampled from live collections, not translated."""

    def test_numeric_fields_accept_both_int_and_double(self):
        """`grade` is float on 371 rows and int on 193; `creditsEarned` is
        float on 499 and int on 65. Demanding `double` would reject correct
        rows for being whole numbers."""
        assert "int" in NUMBER and "double" in NUMBER
        grade = next(f for f in COMPLETED_COURSES.fields if f.name == "grade")
        assert "int" in grade.bson_types
        assert "double" in grade.bson_types

    def test_identity_fields_are_object_ids_not_strings(self):
        """schema.sql renders ObjectIds as `text` because Postgres has no such
        type. Copying that across would reject every document in Mongo."""
        for name in ("_id", "courseId", "userId"):
            rule = next(f for f in COMPLETED_COURSES.fields if f.name == name)
            assert rule.bson_types == ("objectId",), name


class TestTheGeneratedSchema:
    def test_undeclared_fields_are_permitted(self):
        """Live plan documents carry `weeklySchedule`, `selectedLessonEvents`
        and more that no registry declares. Closing the schema would reject
        every one of them while saying nothing about correctness."""
        for rules in ALL_RULES:
            assert "additionalProperties" not in rules.json_schema()

    def test_every_collection_produces_an_object_schema(self):
        for rules in ALL_RULES:
            assert rules.json_schema()["bsonType"] == "object"

    def test_a_rule_set_with_no_required_fields_omits_the_key(self):
        """Mongo rejects `required: []`."""
        rules = CollectionRules("x", (FieldRule("a", ("string",)),))
        assert "required" not in rules.json_schema()


class TestTheRolloutIsNonDestructive:
    def test_the_default_action_is_warn(self):
        """Warn logs the violation and still accepts the write. Nothing in the
        product breaks on the day this is switched on."""
        for plan in all_plans():
            assert plan.action == "warn"

    def test_error_mode_has_to_be_asked_for(self):
        plan = plan_for(COURSES, action="error")
        assert plan.action == "error"

    def test_the_plan_carries_a_jsonschema_payload(self):
        plan = plan_for(COURSES)
        assert "$jsonSchema" in plan.validator


class TestReferences:
    def test_the_transcript_course_reference_is_deliberately_unenforced(self):
        """schema.sql: 'A FK would refuse the load; instead the rows come in and
        the join fails CLOSED.' 133 live rows point at deleted catalog
        documents; rejecting them loses a student's whole transcript, while
        keeping them yields DENIED rather than false eligibility."""
        reference = next(
            r for r in REFERENCES
            if r.collection == "completed_courses" and r.field == "courseId"
        )
        assert reference.enforced is False

    def test_the_offering_course_reference_is_enforced(self):
        reference = next(
            r for r in REFERENCES
            if r.collection == "course_offerings" and r.field == "courseNumber"
        )
        assert reference.enforced is True

    @pytest.mark.parametrize("reference", REFERENCES, ids=lambda r: f"{r.collection}.{r.field}")
    def test_every_reference_targets_a_collection_we_declare(self, reference):
        declared = {rules.collection for rules in ALL_RULES}
        assert reference.target_collection in declared

    @pytest.mark.parametrize("reference", REFERENCES, ids=lambda r: f"{r.collection}.{r.field}")
    def test_an_unenforced_reference_explains_itself(self, reference):
        """Silently declining to enforce is how a deliberate decision decays
        into a forgotten one."""
        if not reference.enforced:
            assert reference.note.strip()


class TestUniqueness:
    @pytest.mark.parametrize("index", UNIQUE_INDEXES, ids=lambda i: i.name)
    def test_unique_indexes_name_declared_collections(self, index):
        declared = {rules.collection for rules in ALL_RULES}
        assert index.collection in declared

    @pytest.mark.parametrize("index", UNIQUE_INDEXES, ids=lambda i: i.name)
    def test_unique_index_keys_are_declared_fields(self, index):
        rules = next(r for r in ALL_RULES if r.collection == index.collection)
        names = {f.name for f in rules.fields}
        for key in index.keys:
            assert key in names, key


class TestUniqueIndexFilters:
    """A unique index must not quietly make an optional field mandatory."""

    def test_the_filter_is_derived_from_the_declared_type(self):
        from app.db.schema_constraints import partial_filter_for

        index = next(i for i in UNIQUE_INDEXES if i.collection == "courses")
        assert partial_filter_for(index) == {
            "courseNumber": {"$exists": True, "$type": ["string"]}
        }

    def test_an_object_id_key_filters_on_object_id(self):
        from app.db.schema_constraints import partial_filter_for

        index = next(i for i in UNIQUE_INDEXES if i.collection == "student_profiles")
        assert partial_filter_for(index)["userId"]["$type"] == ["objectId"]

    @pytest.mark.parametrize("index", UNIQUE_INDEXES, ids=lambda i: i.name)
    def test_no_filter_uses_an_operator_mongo_rejects(self, index):
        """`partialFilterExpression` accepts $exists, $type, equality and
        ranges. `$ne` is not on that list and fails at creation time."""
        from app.db.schema_constraints import partial_filter_for

        for condition in partial_filter_for(index).values():
            assert "$ne" not in condition
