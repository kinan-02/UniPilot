"""Denormalise `courseNumber` onto existing `completed_courses` rows.

DRY RUN BY DEFAULT. Pass `--apply` to write.

New rows get their course number at write time (see
`completed_course_repository.build_completed_course_document`). This backfills the
rows written before that, so a transcript stops depending on a foreign `_id`
staying valid.

## Why

A transcript row's only identity is `courseId`, an ObjectId into `courses`.
Measured 2026-08-26: 28% of rows (155 of 554) reference a document that no longer
exists, and 38 of 145 students have no readable row at all. Those rows carry no
course number, no `courseOfferingId` and empty `metadata`, so what the student
actually studied is unrecoverable -- see
`repair_transcript_course_refs.py` for the forensics.

`semester_plans.plannedCourses` stores the id AND the number, and that redundancy
is the only reason any of the broken rows could be repaired at all. This makes
the transcript as durable as the plan already is.

## What it can reach

Only rows whose `courseId` still resolves -- roughly 399 of 554. The rest have
nothing to look up, and this script does not guess: a course inferred from
credits or semester would attach a plausible course to a real grade, and nothing
about that invites doubt.

So this does not repair the existing damage. It stops the SAME damage happening
to today's intact rows the next time a `courses._id` changes -- a restore, a
reseed, an import from another environment.

## Order of operations

Run `repair_transcript_course_refs.py --apply` FIRST if you intend to. It maps a
handful of stale ids back to live courses using the plans, and any row it fixes
becomes resolvable here. Running this one first simply leaves those rows for the
next pass.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient


async def backfill(database: Any, *, apply: bool) -> dict[str, int]:
    total = await database["completed_courses"].count_documents({})
    already = await database["completed_courses"].count_documents(
        {"courseNumber": {"$exists": True, "$ne": None}}
    )

    # Only the catalog rows a transcript actually points at, so the map stays
    # small regardless of catalog size.
    course_ids = await database["completed_courses"].distinct(
        "courseId", {"courseNumber": {"$exists": False}}
    )
    numbers: dict[Any, str] = {
        document["_id"]: str(document["courseNumber"])
        async for document in database["courses"].find(
            {"_id": {"$in": course_ids}, "courseNumber": {"$exists": True}},
            {"_id": 1, "courseNumber": 1},
        )
    }

    written = 0
    for course_id, number in numbers.items():
        if apply:
            result = await database["completed_courses"].update_many(
                {"courseId": course_id, "courseNumber": {"$exists": False}},
                {"$set": {"courseNumber": number}},
            )
            written += result.modified_count
        else:
            written += await database["completed_courses"].count_documents(
                {"courseId": course_id, "courseNumber": {"$exists": False}}
            )

    unreachable = await database["completed_courses"].count_documents(
        {"courseNumber": {"$exists": False}, "courseId": {"$nin": list(numbers)}}
    )
    return {
        "rows_total": total,
        "already_had_a_number": already,
        "distinct_courses_resolved": len(numbers),
        "rows_backfilled": written,
        "rows_unreachable": unreachable,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()

    uri = os.environ.get("MONGO_URI")
    if not uri:
        raise SystemExit("MONGO_URI is not set")
    database = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=10000)[
        os.environ.get("MONGO_DB") or "unipilot"
    ]

    print("APPLYING CHANGES" if args.apply else "DRY RUN -- nothing will be written")
    for key, value in (await backfill(database, apply=args.apply)).items():
        print(f"{key}: {value}")
    print(
        "\nUnreachable rows reference a course the catalog no longer holds. They are "
        "left alone rather than guessed -- see this module's docstring."
    )


if __name__ == "__main__":
    asyncio.run(main())
