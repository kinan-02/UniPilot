"""Repair `completed_courses.courseId` values that point at deleted catalog rows.

DRY RUN BY DEFAULT. Pass `--apply` to write.

## What is broken

`completed_courses.courseId` is an ObjectId referencing `courses._id`. A catalog
promotion REPLACES the `courses` collection -- every document is written with a
fresh `_id` (staging and production do not share ids either) -- so every
transcript row written before the current promotion now references a document
that no longer exists.

Measured 2026-08-26 against the live database:

    distinct courseId values      243
    resolve to a course           105
    DANGLING                      138   (57% of distinct ids)
    transcript rows affected      155 / 554  (28%)
    students with NO usable row    38 / 145

All 2,613 courses carry one `promotionRunId`, so this is the state after a single
promotion. The next one will do it again to whatever is currently intact.

## Why it matters

`courses` is the only route from a transcript row to a course CODE --
`completed_courses` stores no `courseNumber`, and `courseOfferingId` is null on
all 554 rows. So a dangling reference means the agent cannot say WHICH course a
grade belongs to: `passed_courses.courseNumber` is absent for those rows, and
`remaining_courses` cannot subtract them, so it reports courses as still to take
that the student has already passed.

It fails in the safe direction -- eligibility comes back denied rather than
granted -- but it is wrong, and it is invisible to every test in the suite
because the query is correct and the data is not.

## What this script can and cannot fix

`semester_plans.semesters[].plannedCourses[]` denormalises BOTH `courseId` and
`courseNumber`, so a plan that referenced a course before the promotion still
records what that course was. That is the only surviving mapping.

    dangling ids recoverable this way   7 / 138  (5%)
    transcript rows repaired           22 / 155

The other 131 ids appear in NO collection -- not `staging_courses`, not
`promotion_runs`, not any planning collection -- and the rows carry nothing else
that identifies a course: no course number, no offering, empty `metadata`. They
are unrecoverable from this database, and this script does not guess. Matching a
grade to a course by credits or semester would attach a plausible course to a
real grade, which is the failure that invites no doubt.

## The actual fix, which is not this script

Stop referencing the catalog by a surrogate key the pipeline regenerates. Every
course already carries `productionKey` (`technion:course:00940333`), which is
derived from the course number and is STABLE across promotions. Either:

  1. promote by upserting on `productionKey` so `_id` survives a promotion, or
  2. denormalise `courseNumber` onto `completed_courses` at write time, the way
     `semester_plans.plannedCourses` already does.

(2) is what makes this script's repair possible at all, and it is the reason
plans survived a promotion that transcripts did not.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections import Counter
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient


async def _course_number_by_stale_id(database: Any) -> dict[str, str]:
    """`courseId` -> `courseNumber`, read off the plans that recorded both.

    Plans store `courseId` as a STRING while transcripts store an ObjectId, so
    the two never match without an explicit conversion. A `$in` of ObjectIds
    against this field returns zero rows and looks exactly like "no mapping
    exists" -- which is what it looked like the first time.
    """
    mapping: dict[str, str] = {}
    conflicts: Counter[str] = Counter()

    async for plan in database["semester_plans"].find(
        {},
        {
            "semesters.plannedCourses.courseId": 1,
            "semesters.plannedCourses.courseNumber": 1,
        },
    ):
        for semester in plan.get("semesters") or []:
            for planned in semester.get("plannedCourses") or []:
                course_id, number = planned.get("courseId"), planned.get("courseNumber")
                if not course_id or not number:
                    continue
                key = str(course_id)
                if key in mapping and mapping[key] != number:
                    # One stale id claiming two different courses is a mapping
                    # that cannot be trusted for EITHER, so it is dropped rather
                    # than resolved by picking one.
                    conflicts[key] += 1
                mapping[key] = str(number)

    for key in conflicts:
        mapping.pop(key, None)
    return mapping


async def repair(database: Any, *, apply: bool) -> dict[str, int]:
    course_ids = await database["completed_courses"].distinct("courseId")
    live = {
        document["_id"]
        async for document in database["courses"].find({"_id": {"$in": course_ids}}, {"_id": 1})
    }
    dangling = [cid for cid in course_ids if cid not in live]

    mapping = await _course_number_by_stale_id(database)

    # Only a mapping whose course still EXISTS is a repair; one pointing at a
    # course the current catalog dropped would replace a dead reference with
    # another dead reference and report it as fixed.
    wanted = {mapping[str(cid)] for cid in dangling if str(cid) in mapping}
    current: dict[str, ObjectId] = {
        document["courseNumber"]: document["_id"]
        async for document in database["courses"].find(
            {"courseNumber": {"$in": sorted(wanted)}}, {"_id": 1, "courseNumber": 1}
        )
    }

    repaired = 0
    for stale in dangling:
        number = mapping.get(str(stale))
        target = current.get(number) if number else None
        if target is None:
            continue
        result = await database["completed_courses"].update_many(
            {"courseId": stale},
            {"$set": {"courseId": target, "metadata.repairedFrom": str(stale)}},
        ) if apply else None
        matched = (
            result.modified_count
            if result is not None
            else await database["completed_courses"].count_documents({"courseId": stale})
        )
        repaired += matched
        print(f"  {stale} -> {number} ({target}): {matched} row(s)")

    total_rows = await database["completed_courses"].count_documents({})
    broken_rows = await database["completed_courses"].count_documents(
        {"courseId": {"$in": dangling}}
    )
    return {
        "distinct_ids": len(course_ids),
        "dangling_ids": len(dangling),
        "rows_total": total_rows,
        "rows_broken": broken_rows if apply else broken_rows,
        "rows_repaired": repaired,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the repairs. Without it nothing is modified and the counts are a preview.",
    )
    args = parser.parse_args()

    uri = os.environ.get("MONGO_URI")
    if not uri:
        raise SystemExit("MONGO_URI is not set")
    database = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=10000)[
        os.environ.get("MONGO_DB") or "unipilot"
    ]

    print("APPLYING CHANGES" if args.apply else "DRY RUN -- nothing will be written")
    summary = await repair(database, apply=args.apply)
    print("\n".join(f"{key}: {value}" for key, value in summary.items()))
    unrecoverable = summary["rows_broken"] - summary["rows_repaired"]
    print(
        f"\n{unrecoverable} row(s) carry no recoverable course identity and are left alone. "
        "They are not a bug to route around -- see this module's docstring."
    )


if __name__ == "__main__":
    asyncio.run(main())
