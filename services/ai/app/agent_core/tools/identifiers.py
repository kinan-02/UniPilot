"""One description for every course-identifier argument, and one repair message.

A course is addressed by its CODE (`"00970800"`). Records that mention a course
also carry a Mongo `courseId` (`"6a3db0e382df7b7cb04552c8"`) -- a database
reference that resolves nowhere in the academic graph. The two look
interchangeable and are not, and the argument is spelled `course_id` while the
field is spelled `courseId`, so picking the wrong one is the obvious mistake
rather than a careless one.

`get_entity.entity_id` was given this warning after a live eval caught the
confusion there. The warning stayed on that one field, so every other tool kept
the same trap: 8 of 9 identifier arguments had no description at all. Seeding the
student's semester plan -- whose `plannedCourses[]` carry BOTH `courseId` and
`courseNumber` -- made it reachable, and `plan_eligibility_sweep` has never once
passed: it mapped `check_eligibility` over the six `courseId`s, got six
`entity_not_found`s that named no alternative, retried the same six serially, and
exhausted with zero eligibility results.
"""

from __future__ import annotations

COURSE_ID_DESCRIPTION = (
    "The course CODE, e.g. '00970800' -- an 8-digit number. NEVER a Mongo "
    "`courseId`/`_id` (e.g. '6a3db0e382df7b7cb04552c8'): that is a database "
    "reference, resolves to nothing here, and always fails with entity_not_found. "
    "A completed-course record or a plan's `plannedCourses[]` entry carries BOTH -- "
    "use its `courseNumber`, never its `courseId`."
)

ENTITY_ID_DESCRIPTION = (
    "The entity's CODE or wiki slug -- a course code like '00970800', or a slug "
    "like 'track-information-systems-engineering'. NEVER a Mongo `courseId`/`_id`, "
    "which is a database reference and always fails with entity_not_found."
)

# A Mongo ObjectId hex string: 24 chars, all hex. Course codes are 8 digits, so
# the two never collide.
_OBJECT_ID_LENGTH = 24


def looks_like_object_id(value: str) -> bool:
    candidate = (value or "").strip()
    if len(candidate) != _OBJECT_ID_LENGTH:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in candidate)


def not_found_error(value: str, *, kind: str = "course") -> str:
    """`entity_not_found`, plus the repair when the value is a database id.

    The bare error named the value and nothing else, so a model that passed a
    `courseId` learned only that it had failed -- and retried it verbatim, six
    times, then six more."""
    base = f"entity_not_found: {value}"
    if looks_like_object_id(value):
        return (
            f"{base} -- that is a Mongo id, not a {kind} code. Use the record's "
            "`courseNumber` (an 8-digit code like '00970800') instead."
        )
    return base
