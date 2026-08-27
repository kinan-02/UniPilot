#!/usr/bin/env python3
"""Audit completed-course records whose `courseId` matches no catalog document.

Queries the database the AGENT actually uses -- `MONGO_URI` from the root `.env`,
which is Atlas, not the local `mongo` container. An earlier version of this
script read the container and reported 14 orphans out of 93; the real database
holds 554 records and 155 orphans. Auditing a stale copy is worse than not
auditing at all, because it returns a number that looks like an answer.

A script rather than a pytest case: the suite has no credentials for the real
database, so a test would skip on every machine, and a check that always skips is
a green tick meaning nothing.

WHAT THIS DETECTS
    A `completed_courses` row referencing a `courses._id` that does not exist.
    The record keeps its grade and credits, so credit totals stay correct; what
    it loses is course IDENTITY, so any join to the catalog fails -- and fails
    CLOSED, by design, because a join that silently drops rows makes "which
    requirements remain" return courses the student already passed.

WHY IT IS NOT REPAIRABLE
    Measured 2026-07-19: 155 of 554 records (28%), across 138 phantom ObjectIds.
    The records carry no metadata -- no course number, no title, no offering id
    -- so which course each represents cannot be recovered. Repairing them would
    mean inventing catalog rows, or assigning students a grade in a course
    somebody guessed. Neither is a fix.

WHAT THE IDS SAY ABOUT THE WRITER
    An ObjectId encodes its origin: 4 bytes of timestamp, 5 identifying the
    process, 3 of counter. The 138 phantoms group into 29 process-runs of ~11
    ids each, all on 2026-07-13 between 21:16 and 23:50. Eleven courses per run
    is transcript-shaped, and the clustering says a bulk path rather than a
    person typing.

    That contradicts the code as it stands: `transcript_import_service` resolves
    every row with `find_course_by_number` and routes misses to an `unresolved`
    list instead of writing them, and the completed-course route has validated
    `courseId` since 2026-06-20. So either something else writes this collection,
    or that evening ran a version that did not. UNRESOLVED -- and the reason this
    script exists.

    exit 0  count unchanged or lower
    exit 1  count grew -- whatever wrote them ran again
    exit 2  could not reach the database
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ai"))

KNOWN_ORPHANS = 155

_ORPHANS = [
    {"$lookup": {"from": "courses", "localField": "courseId", "foreignField": "_id", "as": "c"}},
    {"$match": {"c": {"$size": 0}}},
]


async def _measure() -> dict:
    """Query through the agent's own settings, so this cannot drift onto a
    different database from the one the agent reads."""
    from app.db.mongo import get_database

    database = await get_database()
    pipeline = [
        *_ORPHANS,
        {"$group": {"_id": "$courseId", "n": {"$sum": 1}, "sems": {"$addToSet": "$semesterCode"}}},
        {"$sort": {"n": -1}},
    ]
    rows = [row async for row in database["completed_courses"].aggregate(pipeline)]

    # 4 bytes timestamp + 5 bytes per-process => 18 hex chars identify one run.
    runs = Counter(str(row["_id"])[:18] for row in rows)

    return {
        "database": database.name,
        "total": await database["completed_courses"].count_documents({}),
        "orphaned": sum(row["n"] for row in rows),
        "distinctIds": len(rows),
        "processRuns": [
            {
                "prefix": prefix,
                "ids": count,
                "minted": datetime.fromtimestamp(int(prefix[:8], 16), timezone.utc).isoformat(),
            }
            for prefix, count in runs.most_common()
        ],
        "worstOffenders": [
            {"courseId": str(row["_id"]), "records": row["n"], "semesters": sorted(row["sems"])}
            for row in rows[:5]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect", type=int, default=KNOWN_ORPHANS)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    try:
        report = asyncio.run(_measure())
    except Exception as error:  # noqa: BLE001 -- any failure to reach the db is exit 2
        print(f"could not reach the database: {type(error).__name__}: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        share = 100 * report["orphaned"] / report["total"] if report["total"] else 0
        print(f"database:              {report['database']}")
        print(f"completed_courses:     {report['total']}")
        print(f"orphaned references:   {report['orphaned']}  ({share:.1f}%, expected <= {args.expect})")
        print(f"distinct phantom ids:  {report['distinctIds']} from {len(report['processRuns'])} process-run(s)")
        for run in report["processRuns"][:5]:
            print(f"   {run['prefix']}...  {run['ids']:3} ids  minted {run['minted'][:16]}")
        if len(report["processRuns"]) > 5:
            print(f"   ... and {len(report['processRuns']) - 5} more runs")

    if report["orphaned"] > args.expect:
        print(
            f"\nFAIL: orphaned references grew from {args.expect} to {report['orphaned']}.\n"
            "Whatever wrote them has run again. Neither known write path can produce this -- both "
            "validate courseId against the catalog -- so find the writer now: these records carry "
            "no course identity and cannot be repaired afterwards.",
            file=sys.stderr,
        )
        return 1

    if report["orphaned"] < args.expect:
        print(f"\nNote: count dropped to {report['orphaned']}. Lower --expect to re-pin it.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
