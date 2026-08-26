"""Course code -> human-readable name, for rendering answers a student can read.

The live evals shipped grounded, correct, near-unreadable answers: "The courses
on your record with a final grade above 90 are: 00940704, 00940219, 03240033."
Seven of ten answers in the 2026-07-18 run carried bare codes.

The name cannot come from the model. The grounding backstop checks NUMERALS
only (`answer_boundary._NUM`), so a course name typed into prose is never
validated -- and a plausible fabricated name attached to a real code is worse
than no name, because nothing about it invites doubt. So the name is read from
the catalog here, in code, and slotted at the answer boundary exactly as every
other grounded value is.

Source is the course wiki page's frontmatter title, which reads
`<code> — <English name> (<Hebrew name>)` and covers 2601 of 2611 course pages.
`engine.graph.nodes[code]["name"]` is NOT the source: it is Hebrew-only and
missing outright for some courses (00940704, 01040065 among them).
"""

from __future__ import annotations

import difflib
import logging
import re
from functools import lru_cache

from app.retrieval.graph_engine.graph_registry import graph_registry

logger = logging.getLogger(__name__)

# A course code as it appears in a fact value: exactly 8 digits. Narrow on
# purpose -- a grade, a credit total and a semester code must never be looked up
# as if they were courses.
_COURSE_CODE = re.compile(r"^\d{8}$")
# The same shape, unanchored, for scanning prose rather than testing one value.
_COURSE_CODE_IN_TEXT = re.compile(r"\b\d{8}\b")
# A course code as the wiki RENDERS it: 8 digits with the leading zero dropped.
# Used by `canonical_course_code` to restore it; see there for why.
_SEVEN_DIGIT_CODE = re.compile(r"^\d{7}$")
_FRONTMATTER_TITLE = re.compile(r"^title:\s*\"?(.+?)\"?\s*$", re.M)
# The title's leading `<code> — ` prefix; the code is already in the answer.
_TITLE_LEAD = re.compile(r"^\s*\d{6,8}\s*[—\-–]\s*")
_TRAILING_PARENS = re.compile(r"\s*\(([^()]*)\)\s*$")
_HEBREW = re.compile(r"[֐-׿]")
# Frontmatter sits at the top; no need to scan whole course pages.
_FRONTMATTER_SCAN_CHARS = 1500


def _english_name(title: str) -> str | None:
    """The English portion of a wiki title, or None if it has none.

    Drops ONLY a trailing parenthesised group that contains Hebrew. Stripping
    every parenthesised group instead would turn "Introduction to Data
    Engineering (Advanced)" into the name of a different course.
    """
    name = _TITLE_LEAD.sub("", title.strip())
    trailing = _TRAILING_PARENS.search(name)
    if trailing and _HEBREW.search(trailing.group(1)):
        name = name[: trailing.start()].strip()
    if not name or _HEBREW.search(name):
        return None
    return name


@lru_cache(maxsize=1)
def _name_index() -> dict[str, tuple[str, str]]:
    """code -> (English name, Hebrew name), built once from the wiki pages (~20ms).

    Degrades to an empty index if the graph is not configured: a missing name
    costs readability, never correctness, so it must not raise into an answer.

    BOTH halves of the title are kept, where this used to keep only the English.
    The Hebrew half is not for display -- `_catalog_names` covers that -- it is
    what lets `_same_course` check that the wiki page and the catalog row are
    talking about the same course before the English name is trusted.
    """
    try:
        engine = graph_registry.get_engine()
    except Exception:  # noqa: BLE001 -- unconfigured/unloadable graph is not fatal here
        return {}
    index: dict[str, tuple[str, str]] = {}
    for slug, code in engine.slug_to_course_code.items():
        content = (engine.wiki_pages.get(slug) or {}).get("content") or ""
        title = _FRONTMATTER_TITLE.search(content[:_FRONTMATTER_SCAN_CHARS])
        if not title:
            continue
        name = _english_name(title.group(1))
        if name:
            index[code] = (name, _hebrew_name(title.group(1)))
    return index


_HEBREW_HALF = re.compile(r"\(([^()]*[֐-׿][^()]*)\)\s*$")


def _hebrew_name(title: str) -> str:
    """The Hebrew half of a wiki title -- the trailing parenthesised group."""
    match = _HEBREW_HALF.search(title.strip())
    return match.group(1).strip() if match else ""


def _same_course(wiki_english: str, wiki_hebrew: str, catalog_title: str) -> bool:
    """Whether a wiki page and a catalog row describe the SAME course.

    The wiki's code -> page mapping is wrong for roughly 6.8% of courses, and a
    wrong English name attached to a real code is the worst kind of error this
    module can make: nothing about it invites doubt. A student told to take
    "Service Systems Engineering" for a code that is actually organic chemistry
    has no way to notice.

    Compared on the HEBREW halves, because that is the language both sources
    hold: the wiki title's parenthesised group against the catalog title. A
    fuzzy ratio rather than equality, since the two disagree on punctuation and
    construct-state spacing far more often than they disagree on the course.
    """
    if not wiki_hebrew or not catalog_title:
        # Nothing to corroborate WITH. Trusting the wiki here is the status quo
        # ante and is right far more often than not; the check exists to catch
        # active disagreement, not to demand proof.
        return True
    ratio = difflib.SequenceMatcher(None, wiki_hebrew, catalog_title.strip()).ratio()
    return ratio >= _SAME_COURSE_RATIO


_SAME_COURSE_RATIO = 0.6
"""How alike two Hebrew titles must be to be the same course.

Loose on purpose. The failure it guards against is a title for an entirely
different subject, which scores far below this; the near-misses it must NOT
reject are punctuation and spacing differences between two transcriptions of one
name, which score far above it."""


# code -> catalog title, loaded once at startup by `load_catalog_names`. The wiki
# index above is always preferred because its names are English; this covers what
# the wiki does not. The ISE wiki holds 2601 courses, but a student's record also
# carries general electives and humanities that were never wiki'd -- 03240305
# ("היסטוריה של המדע") shipped as a bare code in a live 2026-07-19 answer, sitting
# among eight correctly-named courses. A Hebrew title is not ideal inside an
# English sentence, but a student can read it; an 8-digit number tells them
# nothing at all.
_catalog_names: dict[str, str] = {}


async def load_catalog_names() -> int:
    """Load code -> catalog title from Mongo, returning how many were loaded.

    Degrades to an empty map on ANY failure, for the same reason `_name_index`
    does: a missing name costs readability, never correctness. It must never
    raise into an answer, and must never block service startup.
    """
    global _catalog_names
    try:
        from app.config import get_settings
        from app.db.mongo import get_database

        database = await get_database()
        collection = database[get_settings().courses_collection]
        loaded: dict[str, str] = {}
        async for doc in collection.find({}, {"courseNumber": 1, "title": 1}):
            code, title = doc.get("courseNumber"), doc.get("title")
            if isinstance(code, str) and isinstance(title, str) and title.strip():
                loaded[code] = title.strip()
        _catalog_names = loaded
    except Exception:  # noqa: BLE001 -- readability fallback, never fatal
        logger.warning("catalog course names unavailable; falling back to bare codes", exc_info=True)
        return 0
    return len(_catalog_names)


def course_display_name(value: str, hebrew: bool = False) -> str | None:
    """The course's display name, or None if `value` is not a known course code.

    The two sources hold the two languages -- the wiki title is English, the
    catalog title is Hebrew -- so which one leads is decided by the language the
    ANSWER is written in, not by a fixed preference. A student who asks in
    Hebrew and is told they need "Service Systems Engineering" has to translate
    it back before they can find it on their registration page.

    Whichever is not preferred still serves as the fallback: 2,601 courses have
    a wiki page and 2,613 have a catalog row, so each covers gaps in the other,
    and a name in the wrong language beats an 8-digit number in any case.
    """
    if not _COURSE_CODE.match(value or ""):
        return None
    catalog = _catalog_names.get(value)
    entry = _name_index().get(value)
    english = None
    if entry is not None:
        name, hebrew_half = entry
        # The wiki page must be about the same course the catalog names, or its
        # English title is discarded -- see `_same_course`.
        if catalog is None or _same_course(name, hebrew_half, catalog):
            english = name
    if hebrew:
        return catalog or english
    return english or catalog


def canonical_course_code(value: str) -> str:
    """Restore the leading zero the wiki drops from a course code.

    Technion course codes are 8 digits (`_COURSE_CODE`), but the wiki RENDERS them
    one digit short: the wikilink `[[00960600-organizational-behavior|0960600]]`
    displays `0960600`, and the extractor reads that label. A 7-digit code will
    not join to the catalog's 8-digit `courseNumber`, so a whole elective list
    extracted from the wiki silently matches nothing. Left-pad the one missing
    zero; leave anything that is not a bare 7-digit run untouched -- 8-digit codes,
    6-digit program codes, slugs -- so this is safe over any extracted identifier.
    """
    return f"0{value}" if _SEVEN_DIGIT_CODE.match(value or "") else value


def course_codes_in(text: str) -> set[str]:
    """Every course code appearing in free text.

    The unanchored twin of `_COURSE_CODE`: that one asks "is this value a course
    code", this one asks "which course codes does this prose mention".
    """
    return set(_COURSE_CODE_IN_TEXT.findall(text or ""))


def set_catalog_names(names: dict[str, str]) -> None:
    """Test hook -- seeds the fallback without a database."""
    global _catalog_names
    _catalog_names = dict(names)


_NOT_IN_CATALOG = ("not in the course catalog", "לא נמצא בקטלוג")
"""Said of a code the prerequisite graph names and the catalog does not.

NOT an error and not a guess: the edge is real, the course is genuinely
referenced as a requirement, and nothing about it can be looked up. A student
told "you need 00940226" and nothing else cannot tell whether the agent failed
or the data did."""


_ALREADY_NAMED = re.compile(r"\A\s*[（(]")


def pair_codes_with_names(text: str, hebrew: bool = False) -> str:
    """Show a course code with its name the first time the answer mentions it.

    A live answer, and the reason this exists:

        "You need 00960324 first. It has 2 prerequisite options: 00940314,
         00980413. 0 of those are already on your passed list..."

    Every claim in it is derived and none of it tells a student which courses
    those are. Reading it means opening the catalog three times.

    FIRST MENTION ONLY. Repeating the name at every occurrence turns a two-line
    answer into a paragraph, and the reader already has it.

    SKIPPED when the name is already on that line, which is the normal case for
    a `:detail` plan row -- those project `title` next to the number, and
    pairing there would print it twice.

    The name is read from the catalog in code, never from the model. A
    fabricated name attached to a real code is worse than no name, because
    nothing about it invites doubt -- and the grounding invariant checks
    numerals, so a typed course name is never validated.
    """
    body = text or ""
    if not body:
        return body
    # Only claim a course is absent from the catalog when the catalog is
    # actually LOADED. If the index failed to fill, every code would be
    # labelled unknown -- turning a loading failure into 2613 false statements
    # about the curriculum. Silence is the correct degradation.
    catalog_known = bool(_catalog_names) or bool(_name_index())
    seen: set[str] = set()

    def name_it(match: "re.Match[str]") -> str:
        code = match.group(0)
        if code in seen:
            return code
        name = course_display_name(code, hebrew)
        if not name:
            # Named by the prerequisite graph and absent from the catalog: 768
            # of 4766 edges point at 259 such codes. The agent can offer no
            # name, credits or offerings for them, and printing a bare number
            # beside fully-described courses reads as though it were one of
            # them. Saying so is the honest render -- it tells the student the
            # limit is in the data, not in what they asked.
            if not catalog_known:
                return code
            seen.add(code)
            return f"{code} ({_NOT_IN_CATALOG[1] if hebrew else _NOT_IN_CATALOG[0]})"
        seen.add(code)
        line_start = body.rfind("\n", 0, match.start()) + 1
        line_end = body.find("\n", match.end())
        line = body[line_start : line_end if line_end != -1 else len(body)]
        if name in line:
            return code
        if _ALREADY_NAMED.match(body[match.end() :]):
            return code
        return f"{code} ({name})"

    return _COURSE_CODE_IN_TEXT.sub(name_it, body)


def reset_course_name_index() -> None:
    """Test hook -- the index is built from whichever graph engine is loaded."""
    _name_index.cache_clear()
    set_catalog_names({})
