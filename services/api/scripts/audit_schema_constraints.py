"""Report how many live documents violate the constraints in `schema_constraints`.

READ-ONLY. This script never writes -- there is no `--apply`. It answers one
question: if the rules the agent's Postgres schema already enforces were turned
on against Mongo, what would they catch?

That number is worth having before anything is enforced, because a validator
that fails most of a collection is a wrong rule rather than a finding.

    python scripts/audit_schema_constraints.py

Three kinds of check, and they are not equally enforceable:

1. **Shape** -- required fields and bson types. Enforceable by `$jsonSchema`,
   which is what `schema_constraints.plan_for` builds.
2. **Uniqueness** -- enforceable by a unique index, but creating one FAILS if
   duplicates already exist, so it has to be measured first.
3. **References** -- NOT enforceable in Mongo at all. Reported here, and
   reported forever; `completed_courses.courseId` is deliberately expected to
   have violations (see `REFERENCES` in `schema_constraints`).
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.db.schema_constraints import (
    ALL_RULES,
    REFERENCES,
    UNIQUE_INDEXES,
    CollectionRules,
    Reference,
    UniqueIndex,
)

RULE = "-" * 72


async def _count_failing_schema(
    database: AsyncIOMotorDatabase, rules: CollectionRules
) -> int:
    """Documents the whole `$jsonSchema` would reject."""
    return await database[rules.collection].count_documents(
        {"$nor": [{"$jsonSchema": rules.json_schema()}]}
    )


async def _field_breakdown(
    database: AsyncIOMotorDatabase, rules: CollectionRules
) -> list[tuple[str, int, int]]:
    """Per field: (name, missing-or-null, wrong-type).

    Split apart because the two have different fixes. A missing required field
    is absent data; a wrong type is a writer producing the wrong thing.
    """
    collection = database[rules.collection]
    out: list[tuple[str, int, int]] = []
    for rule in rules.fields:
        missing = 0
        if rule.required:
            missing = await collection.count_documents(
                {"$or": [{rule.name: {"$exists": False}}, {rule.name: None}]}
            )
        legal: list[str] = list(rule.bson_types)
        if not rule.required:
            legal.append("null")
        wrong = await collection.count_documents(
            {rule.name: {"$exists": True, "$not": {"$type": legal}}}
        )
        if missing or wrong:
            out.append((rule.name, missing, wrong))
    return out


async def _count_duplicates(
    database: AsyncIOMotorDatabase, index: UniqueIndex
) -> tuple[int, int]:
    """(duplicate groups, documents involved) for a would-be unique index."""
    key = {k: f"${k}" for k in index.keys}
    pipeline: list[dict[str, Any]] = [
        {"$match": {k: {"$exists": True, "$ne": None} for k in index.keys}},
        {"$group": {"_id": key, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$group": {"_id": None, "groups": {"$sum": 1}, "docs": {"$sum": "$n"}}},
    ]
    rows = await database[index.collection].aggregate(pipeline).to_list(1)
    if not rows:
        return (0, 0)
    return (rows[0]["groups"], rows[0]["docs"])


async def _count_dangling(
    database: AsyncIOMotorDatabase, reference: Reference
) -> tuple[int, int, int]:
    """(rows with a dangling ref, distinct dangling values, rows checked)."""
    collection = database[reference.collection]
    present = {reference.field: {"$exists": True, "$ne": None}}
    checked = await collection.count_documents(present)
    values = await collection.distinct(reference.field, present)
    if not values:
        return (0, 0, checked)

    target = database[reference.target_collection]
    known = set(
        await target.distinct(
            reference.target_field, {reference.target_field: {"$in": list(values)}}
        )
    )
    dangling = [v for v in values if v not in known]
    if not dangling:
        return (0, 0, checked)

    rows = await collection.count_documents({reference.field: {"$in": dangling}})
    return (rows, len(dangling), checked)


async def audit(database: AsyncIOMotorDatabase) -> int:
    """Print the report. Returns the number of *enforceable* violations."""
    enforceable = 0

    print("\n1. SHAPE -- required fields and types  (enforceable by $jsonSchema)")
    print(RULE)
    print("%-24s %8s %10s   %s" % ("collection", "docs", "would fail", "verdict"))
    print(RULE)
    breakdowns: list[tuple[str, list[tuple[str, int, int]]]] = []
    for rules in ALL_RULES:
        total = await database[rules.collection].count_documents({})
        failing = await _count_failing_schema(database, rules)
        enforceable += failing
        verdict = "clean" if failing == 0 else "%.1f%% of rows" % (100.0 * failing / total if total else 0)
        print("%-24s %8d %10d   %s" % (rules.collection, total, failing, verdict))
        detail = await _field_breakdown(database, rules)
        if detail:
            breakdowns.append((rules.collection, detail))

    if breakdowns:
        print("\n   per-field breakdown (only fields with violations)")
        print("   %-22s %-22s %10s %11s" % ("collection", "field", "missing", "wrong type"))
        for collection, detail in breakdowns:
            for name, missing, wrong in detail:
                print("   %-22s %-22s %10d %11d" % (collection, name, missing, wrong))

    print("\n2. UNIQUENESS  (enforceable by a unique index, once duplicates are gone)")
    print(RULE)
    print("%-24s %-18s %8s %10s" % ("collection", "key", "dup grps", "docs"))
    print(RULE)
    for index in UNIQUE_INDEXES:
        groups, docs = await _count_duplicates(database, index)
        enforceable += docs
        print("%-24s %-18s %8d %10d" % (index.collection, "+".join(index.keys), groups, docs))

    print("\n3. REFERENCES  (NOT enforceable in Mongo -- reported, never rejected)")
    print(RULE)
    print("%-24s %-14s %9s %9s %8s" % ("collection", "field", "checked", "dangling", "distinct"))
    print(RULE)
    for reference in REFERENCES:
        rows, distinct, checked = await _count_dangling(database, reference)
        flag = "" if reference.enforced else "   <- expected, by design"
        print(
            "%-24s %-14s %9d %9d %8d%s"
            % (reference.collection, reference.field, checked, rows, distinct, flag)
        )
        if rows and reference.enforced:
            enforceable += rows

    return enforceable


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGO_URI"))
    parser.add_argument("--mongo-db", default=os.environ.get("MONGO_DB", "unipilot"))
    args = parser.parse_args()

    if not args.mongo_uri:
        raise SystemExit("MONGO_URI is not set and --mongo-uri was not given.")

    client = AsyncIOMotorClient(args.mongo_uri)
    database = client[args.mongo_db]
    print("database: %s" % args.mongo_db)
    print("mode    : READ-ONLY (this script has no --apply)")

    enforceable = await audit(database)

    print("\n" + RULE)
    if enforceable == 0:
        print("No enforceable violations. The rules can be switched on as written.")
    else:
        print("%d enforceable violation(s). Fix or amend before leaving warn mode." % enforceable)
    print(RULE)


if __name__ == "__main__":
    asyncio.run(main())
