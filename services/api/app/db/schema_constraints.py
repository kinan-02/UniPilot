"""The agent's Postgres constraints, expressed against MongoDB.

## Where these rules come from

`unipilot-agent/db/schema.sql` is 441 lines of DDL that was **profiled against
the live Atlas database on 2026-08-14** -- its nullability and row counts were
measured, not assumed. That file is currently the only place in either codebase
where a rule like "`courses.courseNumber` is not null and unique" is written
down, and it is enforced only in Supabase, which holds a rebuildable mirror.

Mongo holds the users. It has 37 collections and, before this module, zero
schema validators -- nothing at the database level stopped 918 profiles being
written with no `programSlug`, or 133 transcript rows pointing at catalog
documents that do not exist.

This module ports the *constraints*, not the data. Same rules, same measured
provenance, applied where the writes actually land.

## What survives the translation, and what cannot

| Postgres                      | Mongo                                    |
|-------------------------------|------------------------------------------|
| `not null`                    | `required` + a null-free `bsonType`      |
| column type                   | `bsonType`                               |
| `unique`                      | a unique index (see `UNIQUE_INDEXES`)    |
| `references` (foreign key)    | **nothing** -- see `REFERENCES` below    |
| `generated always as (...)`   | already `ViewSchema` in `services/ai`    |

`$jsonSchema` cannot look at another document, so no foreign key survives. Those
are declared in `REFERENCES` and checked by `scripts/audit_schema_constraints.py`
as a reported number rather than an enforced rule.

## Types are measured, not copied

`schema.sql` renders every ObjectId as `text`, because Postgres has no such type
(see its convention #2). Mongo stores the real thing, so the bson types here were
sampled from the live collections rather than translated from the DDL:

    grade           float:371, int:193      -> both are legal
    creditsEarned   float:499, int:65       -> both are legal
    _id, userId, courseId, degreeId         -> objectId, never string

A validator that demanded `double` for `grade` would reject 193 rows that are
perfectly correct. Numeric fields therefore accept the whole numeric family.

## `programSlug` is deliberately not required

918 of 1,000 profiles do not carry it and 1 more is null. It is nullable in
`schema.sql` too. Making it required would not describe a rule -- it would just
fail 92% of the collection. Fixing that data is a separate job from declaring
what the shape is; this module only declares rules the data can actually be held
to, which is what makes a violation meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cost only matters at runtime
    from motor.motor_asyncio import AsyncIOMotorDatabase

# The numeric family. Mongo stores whichever of these the writer happened to
# produce, and `grade`/`creditsEarned` demonstrably hold both int and double.
NUMBER = ("double", "int", "long", "decimal")
OBJECT_ID = ("objectId",)
STRING = ("string",)
INT = ("int", "long")
ARRAY = ("array",)
DATE = ("date",)
BOOL = ("bool",)
OBJECT = ("object",)


@dataclass(frozen=True)
class FieldRule:
    """One column's worth of `schema.sql`, as a Mongo type rule.

    `required` mirrors Postgres `not null`: the field must be present AND its
    type may not include null. Everything else is checked only when the field is
    present, which is how an optional column behaves.
    """

    name: str
    bson_types: tuple[str, ...]
    required: bool = False
    note: str = ""

    def json_schema(self) -> dict[str, object]:
        types = self.bson_types if self.required else (*self.bson_types, "null")
        rule: dict[str, object] = {"bsonType": list(types)}
        if self.note:
            rule["description"] = self.note
        return rule


@dataclass(frozen=True)
class CollectionRules:
    """The declared shape of one collection."""

    collection: str
    fields: tuple[FieldRule, ...]
    note: str = ""

    @property
    def required(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields if f.required)

    def json_schema(self) -> dict[str, object]:
        """A `$jsonSchema` for `collMod`.

        `additionalProperties` is left permissive on purpose. These collections
        carry fields no registry declares -- `semester_plans` documents alone
        carry `weeklySchedule`, `selectedLessonEvents` and `constraintsSnapshot`
        -- and rejecting them would reject every live document while saying
        nothing about correctness.
        """
        schema: dict[str, object] = {
            "bsonType": "object",
            "properties": {f.name: f.json_schema() for f in self.fields},
        }
        if self.required:
            schema["required"] = list(self.required)
        if self.note:
            schema["description"] = self.note
        return schema


@dataclass(frozen=True)
class Reference:
    """A foreign key that Mongo cannot enforce.

    `enforced` records whether the rule is one we would *want* the database to
    refuse writes on if it could. One of them is deliberately False -- see
    `completed_courses.courseId`.
    """

    collection: str
    field: str
    target_collection: str
    target_field: str
    enforced: bool
    note: str = ""


@dataclass(frozen=True)
class UniqueIndex:
    """A Postgres `unique` / `primary key`, as a Mongo unique index."""

    collection: str
    keys: tuple[str, ...]
    name: str
    note: str = ""


# ---------------------------------------------------------------------------
# The rules, collection by collection.
#
# Every `required` below is a `not null` in schema.sql. Nothing has been made
# stricter than that file, because that file is the one that was measured
# against real rows.
# ---------------------------------------------------------------------------

COURSES = CollectionRules(
    collection="courses",
    note="The catalog. 2,613 rows.",
    fields=(
        FieldRule("_id", OBJECT_ID, required=True),
        FieldRule(
            "courseNumber",
            STRING,
            required=True,
            note=(
                "The code a human says out loud, and the key `find` sorts on. "
                "Distinct from `_id`, which is what completed_courses.courseId "
                "joins to -- confusing the two returned an empty prerequisite "
                "set in a live eval."
            ),
        ),
        FieldRule("title", STRING),
        FieldRule("titleHebrew", STRING),
        FieldRule("credits", NUMBER),
        FieldRule("faculty", STRING),
        FieldRule("studyFramework", STRING),
        FieldRule("catalogYear", INT),
        FieldRule("status", STRING),
        FieldRule(
            "noAdditionalCreditText",
            STRING,
            note=(
                "מקצועות ללא זיכוי נוסף -- the courses this one grants no "
                "additional credit alongside. 872 of 2,613 carry it. The term "
                "planner's only hard exclusion is built from this column; when "
                "it was missing from the first Supabase schema the exclusion "
                "silently never fired."
            ),
        ),
    ),
)

COURSE_OFFERINGS = CollectionRules(
    collection="course_offerings",
    note="When a course actually runs. 6,580 rows.",
    fields=(
        FieldRule("_id", OBJECT_ID, required=True),
        FieldRule("courseNumber", STRING, required=True),
        FieldRule(
            "semesterName",
            STRING,
            note="spring | summer | winter -- what `forecast` keys on.",
        ),
        FieldRule(
            "semesterCode",
            INT,
            note=(
                "An integer here (200/201/202), while "
                "completed_courses.semesterCode is the text '2025-2'. Two "
                "vocabularies, deliberately typed apart."
            ),
        ),
        FieldRule("academicYear", INT),
        FieldRule("catalogVersion", STRING),
        FieldRule("status", STRING),
    ),
)

DEGREE_PROGRAMS = CollectionRules(
    collection="degree_programs",
    note="61 rows.",
    fields=(
        FieldRule("_id", OBJECT_ID, required=True),
        FieldRule("name", STRING),
        FieldRule("totalCredits", NUMBER),
    ),
)

STUDENT_PROFILES = CollectionRules(
    collection="student_profiles",
    note="1,000 rows.",
    fields=(
        FieldRule("_id", OBJECT_ID, required=True),
        FieldRule(
            "userId",
            OBJECT_ID,
            required=True,
            note=(
                "The identity, and the column every query filters on. NOT "
                "`institutionId`, which is a tenant name -- all live profiles "
                "share one of its two values, so keyed on it every profile had "
                "the same identity."
            ),
        ),
        FieldRule("institutionId", STRING, required=True),
        FieldRule("facultyId", STRING),
        FieldRule("programType", STRING),
        FieldRule("degreeId", OBJECT_ID),
        FieldRule(
            "programSlug",
            STRING,
            note=(
                "The filter into track curricula. Nullable, and absent on 918 "
                "of 1,000 live profiles -- that is a data gap to close, not a "
                "rule to declare. See the module docstring."
            ),
        ),
        FieldRule("catalogYear", INT),
        FieldRule("currentSemesterCode", STRING),
    ),
)

COMPLETED_COURSES = CollectionRules(
    collection="completed_courses",
    note="The transcript. 564 rows.",
    fields=(
        FieldRule("_id", OBJECT_ID, required=True),
        FieldRule("courseId", OBJECT_ID, required=True),
        FieldRule("userId", OBJECT_ID, required=True),
        FieldRule("semesterCode", STRING, note="Text, e.g. '2025-2'."),
        FieldRule(
            "grade",
            NUMBER,
            note="Stored as both int and double across live rows; both legal.",
        ),
        FieldRule("gradePoints", NUMBER),
        FieldRule(
            "creditsEarned",
            NUMBER,
            note=(
                "CANNOT be summed to get credits toward the degree. Course "
                "01040166 is graded 30 -- a fail -- and still carries its full "
                "5.5. Summing this told a live student 135 credits when the "
                "answer is 129.5. Use the derived `creditsCounted`, which is "
                "0 below a grade of 55."
            ),
        ),
        FieldRule("attempt", INT),
        FieldRule("source", STRING),
    ),
)

SEMESTER_PLANS = CollectionRules(
    collection="semester_plans",
    note="275 rows.",
    fields=(
        FieldRule("_id", OBJECT_ID, required=True),
        FieldRule("userId", OBJECT_ID, required=True),
        FieldRule("name", STRING),
        FieldRule("plannerType", STRING),
        FieldRule("status", STRING),
        FieldRule("version", INT),
        FieldRule("semesters", ARRAY, required=True),
    ),
)

USERS = CollectionRules(
    collection="users",
    note=(
        "1,386 rows. Not in the agent's schema.sql -- it has no use for "
        "credentials -- so this was profiled with `scripts/profile_collection.py` "
        "instead. Measured 2026-08-28."
    ),
    fields=(
        FieldRule("_id", OBJECT_ID, required=True),
        FieldRule("email", STRING, required=True, note="Present on all 1,386, unique."),
        FieldRule("createdAt", DATE, required=True),
        FieldRule(
            "updatedAt",
            DATE,
            note=(
                "Present on all 1,386 today, but deliberately not required: it "
                "is bookkeeping, and a write path that legitimately omits it on "
                "creation should not be a schema violation."
            ),
        ),
        FieldRule(
            "authProvider",
            STRING,
            note="Absent on 46 legacy local accounts, all of which have a passwordHash.",
        ),
        FieldRule(
            "passwordHash",
            STRING,
            note=(
                "Absent on the 19 Google accounts. Not required, because "
                "requiring it would reject every federated login -- but see "
                "`scripts/audit_schema_constraints.py`: 0 users have neither "
                "this nor `googleId`, which is the property that actually "
                "matters and which no single-field rule can express."
            ),
        ),
        FieldRule("googleId", STRING, note="Present on 19."),
    ),
)

DEGREE_REQUIREMENTS = CollectionRules(
    collection="degree_requirements",
    note=(
        "319 rows, written by the catalog promoter. Profiled 2026-08-28: every "
        "declared field is present and non-null on every row, which is what a "
        "single controlled writer looks like. The value of a validator here is "
        "catching the day that stops being true."
    ),
    fields=(
        FieldRule("_id", OBJECT_ID, required=True),
        FieldRule("productionKey", STRING, required=True),
        FieldRule("programCode", STRING, required=True),
        FieldRule("institutionId", STRING, required=True),
        FieldRule("requirementGroupId", STRING, required=True),
        FieldRule("requirementType", STRING, required=True),
        FieldRule("courseReferences", ARRAY, required=True),
        FieldRule("minCredits", NUMBER, required=True),
        FieldRule("isMandatory", BOOL, required=True),
        FieldRule("advisoryOnly", BOOL, required=True),
        FieldRule(
            "enforceInGraduationProgress",
            BOOL,
            required=True,
            note="Read by the graduation calculator; a missing value would silently change what counts.",
        ),
        FieldRule("ruleIsExecutable", BOOL, required=True),
        FieldRule("ruleExpression", OBJECT, required=True),
        FieldRule("catalogYear", INT, required=True),
        FieldRule("catalogVersion", STRING, required=True),
        FieldRule("promotionRunId", STRING, required=True),
        FieldRule(
            "promotedAt",
            STRING,
            required=True,
            note=(
                "A STRING here, while `degree_programs.promotedAt` is a real "
                "date. Recorded rather than corrected -- the inconsistency is "
                "in the promoter, and a validator is the wrong place to "
                "discover that."
            ),
        ),
    ),
)

MOODLE_GRADES = CollectionRules(
    collection="moodle_grades",
    note="81 rows. An agent source (`sources.MOODLE_GRADES`). Profiled 2026-08-28.",
    fields=(
        FieldRule("_id", OBJECT_ID, required=True),
        FieldRule("userId", OBJECT_ID, required=True),
        FieldRule("courseNumber", STRING, required=True),
        FieldRule("courseTitle", STRING, required=True),
        FieldRule("assignment", STRING, required=True),
        FieldRule(
            "grade",
            NUMBER,
            note=(
                "Null on 43 of 81 -- an assignment that exists but is not "
                "marked yet. Nullable on purpose: a not-yet-graded item is not "
                "a zero, and the agent must be able to tell the difference."
            ),
        ),
        FieldRule("outOf", NUMBER, required=True),
        FieldRule("term", STRING, required=True),
        FieldRule("termIndex", INT, required=True),
        FieldRule("observedAt", DATE, required=True),
    ),
)

ALL_RULES: tuple[CollectionRules, ...] = (
    COURSES,
    COURSE_OFFERINGS,
    DEGREE_PROGRAMS,
    STUDENT_PROFILES,
    COMPLETED_COURSES,
    SEMESTER_PLANS,
    USERS,
    DEGREE_REQUIREMENTS,
    MOODLE_GRADES,
)


# ---------------------------------------------------------------------------
# Uniqueness -- Postgres `unique` and `primary key`.
# ---------------------------------------------------------------------------

UNIQUE_INDEXES: tuple[UniqueIndex, ...] = (
    UniqueIndex(
        collection="courses",
        keys=("courseNumber",),
        name="courses_course_number_unique",
        note="`courseNumber text not null unique` in schema.sql.",
    ),
    UniqueIndex(
        collection="student_profiles",
        keys=("userId",),
        name="student_profiles_user_id_unique",
        note="`userId text primary key` in schema.sql.",
    ),
    UniqueIndex(
        collection="users",
        keys=("email",),
        name="users_unique_email",
        note="ALREADY EXISTS under this name. Declared so it is documented, not recreated.",
    ),
    UniqueIndex(
        collection="users",
        keys=("googleId",),
        name="users_unique_google_id",
        note="ALREADY EXISTS under this name.",
    ),
)


# ---------------------------------------------------------------------------
# References -- what a foreign key would say, if Mongo had them.
# ---------------------------------------------------------------------------

REFERENCES: tuple[Reference, ...] = (
    Reference(
        collection="course_offerings",
        field="courseNumber",
        target_collection="courses",
        target_field="courseNumber",
        enforced=True,
        note=(
            "A real FK in schema.sql, and it held: 0 of 6,580 offerings "
            "referenced a course that does not exist."
        ),
    ),
    Reference(
        collection="student_profiles",
        field="degreeId",
        target_collection="degree_programs",
        target_field="_id",
        enforced=True,
        note="`degreeId text references degree_programs (\"_id\")`.",
    ),
    Reference(
        collection="student_profiles",
        field="userId",
        target_collection="users",
        target_field="_id",
        enforced=True,
        note=(
            "Not in schema.sql -- the agent's Supabase has no `users` table. "
            "A profile whose user does not exist is unreachable by definition."
        ),
    ),
    Reference(
        collection="moodle_grades",
        field="userId",
        target_collection="users",
        target_field="_id",
        enforced=True,
        note="Same shape as student_profiles.userId; see the ghost-user finding.",
    ),
    Reference(
        collection="completed_courses",
        field="courseId",
        target_collection="courses",
        target_field="_id",
        enforced=False,
        note=(
            "DELIBERATELY NOT ENFORCED, and schema.sql spells out why: 'A FK "
            "would refuse the load; instead the rows come in and the join to "
            "`courses` fails CLOSED, which is why the wrong answer never "
            "reaches anyone.' For one student every passed course is orphaned; "
            "refusing those rows loses the transcript, while keeping them "
            "yields DENIED rather than a false eligibility. Wrong in the safe "
            "direction, and visible. Report the count, never reject the write."
        ),
    ),
)


@dataclass(frozen=True)
class ValidatorPlan:
    """What would be applied to one collection, without applying it."""

    collection: str
    validator: dict[str, object]
    action: str
    level: str
    required: tuple[str, ...] = field(default_factory=tuple)


def plan_for(rules: CollectionRules, *, action: str = "warn", level: str = "strict") -> ValidatorPlan:
    """The `collMod` payload for one collection.

    `action="warn"` is the default on purpose: Mongo logs the violation and
    still accepts the write. Nothing in the product breaks on the day this is
    switched on, which is the only responsible way to introduce a constraint to
    a collection holding 1,386 real users.
    """
    return ValidatorPlan(
        collection=rules.collection,
        validator={"$jsonSchema": rules.json_schema()},
        action=action,
        level=level,
        required=rules.required,
    )


def all_plans(*, action: str = "warn", level: str = "strict") -> tuple[ValidatorPlan, ...]:
    return tuple(plan_for(rules, action=action, level=level) for rules in ALL_RULES)


async def apply_validators(
    database: "AsyncIOMotorDatabase",
    *,
    action: str = "warn",
    level: str = "strict",
) -> tuple[str, ...]:
    """Attach the validators to live collections. Returns the names modified.

    NOT called at startup, and deliberately not wired into `main.py`. Turning a
    constraint on is a decision about a database holding real users, not a side
    effect of a deploy -- run it explicitly, having first read what
    `scripts/audit_schema_constraints.py` says would fail.

    `action="warn"` means Mongo logs the violation and accepts the write, so
    this is reversible and non-breaking. Only move to `action="error"` once the
    audit reports zero enforceable violations for the collection in question.
    """
    modified: list[str] = []
    for plan in all_plans(action=action, level=level):
        await database.command(
            {
                "collMod": plan.collection,
                "validator": plan.validator,
                "validationLevel": plan.level,
                "validationAction": plan.action,
            }
        )
        modified.append(plan.collection)
    return tuple(modified)


async def ensure_unique_indexes(
    database: "AsyncIOMotorDatabase", *, partial: bool = True
) -> tuple[str, ...]:
    """Create the indexes for the Postgres `unique` / `primary key` constraints.

    Returns the index names created.

    Creating a unique index FAILS if duplicates already exist, so run
    `scripts/audit_schema_constraints.py` first -- section 2 is exactly this
    question. It reported zero duplicates on both keys, which is why these can
    be built at all.

    `partial=True` restricts each index to documents where the key is present
    and non-null. Mongo treats a missing key as `null` and considers two missing
    keys equal, so a plain unique index would refuse the SECOND document that
    happens to omit the field -- turning an optional column into a mandatory
    one by a side effect nobody declared.
    """
    created: list[str] = []
    for index in UNIQUE_INDEXES:
        if await _already_unique_on(database, index):
            continue
        kwargs: dict[str, object] = {"name": index.name, "unique": True}
        if partial:
            kwargs["partialFilterExpression"] = partial_filter_for(index)
        await database[index.collection].create_index(
            [(key, 1) for key in index.keys], **kwargs
        )
        created.append(index.name)
    return tuple(created)


async def _already_unique_on(
    database: "AsyncIOMotorDatabase", index: UniqueIndex
) -> bool:
    """True if some index already enforces uniqueness on exactly these keys.

    `users.email` and `users.googleId` were indexed long before this module
    existed, under their own names. Creating a second unique index over the same
    keys is at best redundant and at worst an `IndexOptionsConflict` that aborts
    the whole run, so an existing equivalent is left exactly as it is.
    """
    existing = await database[index.collection].index_information()
    wanted = tuple(index.keys)
    for spec in existing.values():
        keys = tuple(field for field, _direction in spec.get("key", []))
        if keys == wanted and spec.get("unique"):
            return True
    return False


def partial_filter_for(index: UniqueIndex) -> dict[str, object]:
    """Restrict a unique index to documents that actually carry the key.

    `$type` rather than `$ne: null`, because `partialFilterExpression` accepts
    `$exists`, `$type`, equality and ranges -- but not `$ne`. The type comes
    from the field's own declaration, so this cannot drift from `ALL_RULES`.
    """
    rules = next(r for r in ALL_RULES if r.collection == index.collection)
    by_name = {f.name: f for f in rules.fields}
    return {
        key: {"$exists": True, "$type": list(by_name[key].bson_types)}
        for key in index.keys
    }


async def clear_validators(database: "AsyncIOMotorDatabase") -> tuple[str, ...]:
    """Detach every validator this module attached. The way back."""
    cleared: list[str] = []
    for rules in ALL_RULES:
        await database.command(
            {"collMod": rules.collection, "validator": {}, "validationLevel": "off"}
        )
        cleared.append(rules.collection)
    return tuple(cleared)
