"""Measure a collection's real shape, and propose constraint rules from it.

READ-ONLY. Writes nothing, and never prints a field VALUE.

`schema_constraints` covers the six collections the agent's `db/schema.sql` had
already profiled against live data. The other 31 have no such profile, and
guessing their rules is the failure this whole exercise exists to avoid -- a
validator asserted rather than measured either rejects correct data or asserts
nothing.

So: measure first.

    python scripts/profile_collection.py users
    python scripts/profile_collection.py users --propose

`--propose` prints a `CollectionRules` block ready to paste into
`app/db/schema_constraints.py`, with `required=True` on exactly those fields
that are present and non-null on EVERY document. That threshold is deliberate:
a field present on 99% of rows is a data gap to close, not a rule that holds.

## Values are never printed

`users` carries emails and password hashes; `student_profiles` carries academic
records. This script reports names, bson types, and counts. Nothing else leaves
the database, so its output is safe to paste into a review, a ticket, or a chat.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections import Counter, defaultdict

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

# bson type name for a python value, matching what `$type` expects.
_BSON = {
    "ObjectId": "objectId",
    "str": "string",
    "int": "int",
    "float": "double",
    "bool": "bool",
    "list": "array",
    "dict": "object",
    "datetime": "date",
    "Decimal128": "decimal",
    "bytes": "binData",
    "Binary": "binData",
    "Int64": "long",
}

# Suggested for these, because a constant they are not.
_NEVER_REQUIRED = {"updatedAt", "revision"}


def _bson_name(value: object) -> str:
    return _BSON.get(type(value).__name__, type(value).__name__)


async def profile(
    database: AsyncIOMotorDatabase, collection: str, *, limit: int
) -> tuple[int, dict[str, Counter], dict[str, int]]:
    """(documents seen, field -> type counter, field -> null count)."""
    types: dict[str, Counter] = defaultdict(Counter)
    nulls: dict[str, int] = defaultdict(int)
    seen = 0
    async for document in database[collection].find({}).limit(limit):
        seen += 1
        for name, value in document.items():
            if value is None:
                nulls[name] += 1
            else:
                types[name][_bson_name(value)] += 1
    return seen, types, nulls


def _report(collection: str, seen: int, types, nulls) -> list[str]:
    """Field names that are present and non-null on every document."""
    print("collection : %s" % collection)
    print("documents  : %d\n" % seen)
    print("%-28s %7s %7s %7s  %s" % ("field", "present", "null", "absent", "bson types"))
    print("-" * 86)

    always: list[str] = []
    names = sorted(set(types) | set(nulls), key=lambda n: (n != "_id", n))
    for name in names:
        non_null = sum(types[name].values())
        null = nulls.get(name, 0)
        present = non_null + null
        absent = seen - present
        kinds = ", ".join("%s:%d" % kv for kv in types[name].most_common())
        flag = ""
        if absent == 0 and null == 0 and name not in _NEVER_REQUIRED:
            always.append(name)
            flag = "  <- always"
        print("%-28s %7d %7d %7d  %s%s" % (name, present, null, absent, kinds, flag))
    return always


def _propose(collection: str, types, always: list[str]) -> None:
    const = collection.upper()
    print("\n\n# --- paste into app/db/schema_constraints.py ---")
    print("%s = CollectionRules(" % const)
    print("    collection=%r," % collection)
    print("    fields=(")
    for name in sorted(types, key=lambda n: (n != "_id", n)):
        kinds = tuple(sorted(types[name]))
        literal = {
            ("objectId",): "OBJECT_ID",
            ("string",): "STRING",
            ("array",): "ARRAY",
        }.get(kinds)
        if literal is None and set(kinds) <= set(("double", "int", "long", "decimal")):
            literal = "NUMBER"
        if literal is None and set(kinds) <= set(("int", "long")):
            literal = "INT"
        rendered = literal or repr(kinds)
        suffix = ", required=True" if name in always else ""
        print("        FieldRule(%r, %s%s)," % (name, rendered, suffix))
    print("    ),\n)")
    print("# then add %s to ALL_RULES and re-run audit_schema_constraints.py" % const)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collection")
    parser.add_argument("--limit", type=int, default=100_000)
    parser.add_argument("--propose", action="store_true")
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGO_URI"))
    parser.add_argument("--mongo-db", default=os.environ.get("MONGO_DB", "unipilot"))
    args = parser.parse_args()

    if not args.mongo_uri:
        raise SystemExit("MONGO_URI is not set and --mongo-uri was not given.")

    database = AsyncIOMotorClient(args.mongo_uri)[args.mongo_db]
    seen, types, nulls = await profile(database, args.collection, limit=args.limit)
    if seen == 0:
        print("%s is empty -- nothing to profile." % args.collection)
        return

    always = _report(args.collection, seen, types, nulls)
    if args.propose:
        _propose(args.collection, types, always)


if __name__ == "__main__":
    asyncio.run(main())
