"""Parse Technion official transcript PDF text (Hebrew and English layouts)."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from app.schemas.parse_result import ParsedCourseEntry
from app.services.course_attempts import assign_sequential_course_attempts, detect_attempt_from_text

COURSE_NUMBER_ONLY = re.compile(r"^0\d{7}$")
CONCATENATED_ROW = re.compile(
    r"^(?P<number>0\d{7})(?P<middle>.*?)(?P<credits>\d+(?:\.\d)?)$",
    re.DOTALL,
)
CONCATENATED_EXEMPTION = re.compile(
    r"^(?P<number>0\d{7})(?P<middle>.+(?:פטור ללא ניקוד|פטור עם ניקוד))$",
    re.IGNORECASE,
)
TITLE_WITH_DECIMAL_CREDITS = re.compile(r"^(?P<title>.*?)(?P<credits>\d+\.\d)$")
TITLE_WITH_HEBREW_TRAILING_CREDITS = re.compile(
    r"^(?P<title>.*[\u0590-\u05FF])(?P<credits>\d+)$",
)
CREDITS_ONLY = re.compile(r"^\d+(?:\.\d)?$")
NUMERIC_GRADE = re.compile(r"^\d+(?:\.\d)?$")
ACADEMIC_YEAR = re.compile(r"(?P<start>\d{4})-(?P<end>\d{4})")
HEADER_LINES_HE = frozenset({"מקצוע", "ניקוד", "ציון", "סמסטר"})
HEADER_LINES_EN = frozenset({"SUBJECT", "CREDITS", "GRADE", "SEMESTER"})
FOOTER_MARKERS = (
    "END OF TRANSCRIPT",
    "סוף תעודת הציונים",
)
EXEMPTION_WITHOUT_POINTS = re.compile(
    r"exemption without points|פטור ללא ניקוד",
    re.IGNORECASE,
)
EXEMPTION_WITH_POINTS = re.compile(
    r"exemption with points|פטור עם ניקוד",
    re.IGNORECASE,
)
PASS_GRADE = re.compile(r"^\s*pass\s*$|^\s*עובר\s*$", re.IGNORECASE)
NUMERIC_GRADE_PREFIX = re.compile(r"^(\d+(?:\.\d)?)")
HEBREW_SPRING = re.compile(r"אביב", re.IGNORECASE)
HEBREW_WINTER = re.compile(r"חורף", re.IGNORECASE)
HEBREW_SUMMER = re.compile(r"קיץ", re.IGNORECASE)
ENGLISH_SPRING = re.compile(r"\bspring\b", re.IGNORECASE)
ENGLISH_WINTER = re.compile(r"\bwinter\b", re.IGNORECASE)
ENGLISH_SUMMER = re.compile(r"\bsummer\b", re.IGNORECASE)
STUDENT_ID_PATTERN = re.compile(r"ID:\s*(\d{9})", re.IGNORECASE)
STUDENT_NAME_EN = re.compile(r"Transcript of (.+?) ID:", re.IGNORECASE | re.DOTALL)
STUDENT_NAME_HE = re.compile(r"תעודת ציונים של\s+(.+?)\s+ת\.?ז")


@dataclass(frozen=True)
class ParsedBlock:
    course_number: str
    semester_code: str
    grade: float
    credits_earned: float
    title: str | None
    confidence: float
    warnings: tuple[str, ...]
    marked_attempt: int = 1


def _marked_attempt_from_parts(*parts: str | None) -> int:
    combined = " ".join(part.strip() for part in parts if part and part.strip())
    return detect_attempt_from_text(combined)


@dataclass(frozen=True)
class _AttemptBlock:
    block: ParsedBlock
    attempt: int


def extract_student_id(raw_text: str) -> str | None:
    id_match = STUDENT_ID_PATTERN.search(raw_text)
    if id_match:
        return id_match.group(1)

    for line in raw_text.splitlines()[:8]:
        match = re.search(r"\b(\d{9})\b", line)
        if match:
            return match.group(1)
    return None


def extract_student_name(raw_text: str) -> str | None:
    english = STUDENT_NAME_EN.search(raw_text)
    if english:
        return " ".join(english.group(1).split())

    hebrew = STUDENT_NAME_HE.search(raw_text)
    if hebrew:
        return hebrew.group(1).strip()
    return None


def is_half_credit_increment(value: float) -> bool:
    return abs(value * 2 - round(value * 2)) < 1e-9


def parse_credits_token(value: str) -> float | None:
    try:
        numeric = float(value.strip())
    except ValueError:
        return None
    if numeric < 0 or numeric > 36:
        return None
    if not is_half_credit_increment(numeric):
        return None
    return numeric


def parse_numeric_grade(value: str) -> float | None:
    try:
        numeric = float(value.strip())
    except ValueError:
        return None
    if numeric < 0 or numeric > 100:
        return None
    return numeric


def parse_grade_line(line: str) -> float | None:
    stripped = line.strip()
    direct = parse_numeric_grade(stripped)
    if direct is not None:
        return direct
    prefix = NUMERIC_GRADE_PREFIX.match(stripped)
    if prefix:
        return parse_numeric_grade(prefix.group(1))
    return None


def infer_term_from_semester_line(line: str) -> int | None:
    if HEBREW_WINTER.search(line) or ENGLISH_WINTER.search(line):
        return 1
    if HEBREW_SPRING.search(line) or ENGLISH_SPRING.search(line):
        return 2
    if HEBREW_SUMMER.search(line) or ENGLISH_SUMMER.search(line):
        return 3
    return None


def parse_semester_from_line(line: str) -> str | None:
    year_match = ACADEMIC_YEAR.search(line)
    if not year_match:
        return None

    term = infer_term_from_semester_line(line)
    if term is None:
        return None

    start_year = year_match.group("start")
    return f"{start_year}-{term}"


def is_header_or_footer(line: str) -> bool:
    stripped = line.strip()
    if stripped in HEADER_LINES_HE or stripped in HEADER_LINES_EN:
        return True
    upper = stripped.upper()
    if any(marker in stripped for marker in FOOTER_MARKERS):
        return True
    if upper.startswith("PAGE ") or " מתוך" in stripped or stripped.endswith("עמוד"):
        return True
    return False


def is_course_start(line: str) -> bool:
    if COURSE_NUMBER_ONLY.match(line):
        return True
    if CONCATENATED_ROW.match(line):
        return True
    if CONCATENATED_EXEMPTION.match(line):
        return True
    return False


def split_title_and_credits(line: str) -> tuple[str | None, float | None]:
    if CREDITS_ONLY.match(line):
        return None, parse_credits_token(line)

    decimal_match = TITLE_WITH_DECIMAL_CREDITS.match(line)
    if decimal_match:
        return clean_title(decimal_match.group("title")), parse_credits_token(
            decimal_match.group("credits")
        )

    hebrew_match = TITLE_WITH_HEBREW_TRAILING_CREDITS.match(line)
    if hebrew_match:
        return clean_title(hebrew_match.group("title")), parse_credits_token(
            hebrew_match.group("credits")
        )

    return line, None


def finish_block(
    *,
    course_number: str,
    index: int,
    lines: list[str],
    title: str | None,
    credits: float,
    warnings: list[str],
    confidence: float,
) -> tuple[ParsedBlock | None, int]:
    if index >= len(lines):
        return None, index

    grade_line = lines[index].strip()
    exemption = parse_exemption_grade(grade_line)
    if exemption:
        grade, _exemption_credits, exemption_warnings = exemption
        warnings.extend(exemption_warnings)
        index += 1
    else:
        grade = parse_grade_line(grade_line)
        index += 1
        if grade is None:
            return None, index

    semester_line = lines[index].strip() if index < len(lines) else ""
    semester_code = parse_semester_from_line(semester_line)
    index += 1
    if not semester_code:
        return None, index

    marked_attempt = _marked_attempt_from_parts(grade_line, semester_line, title)

    return (
        ParsedBlock(
            course_number=course_number,
            semester_code=semester_code,
            grade=grade,
            credits_earned=credits,
            title=title,
            confidence=confidence,
            warnings=tuple(warnings),
            marked_attempt=marked_attempt,
        ),
        index,
    )


def parse_exemption_grade(line: str) -> tuple[float, float, tuple[str, ...]] | None:
    if EXEMPTION_WITHOUT_POINTS.search(line):
        return 0.0, 0.0, ("Recorded as exemption without points",)
    if EXEMPTION_WITH_POINTS.search(line):
        return 55.0, 0.0, ("Recorded as exemption with points; verify credits",)
    if PASS_GRADE.search(line.strip()):
        return 56.0, 0.0, ("Recorded as pass grade",)
    return None


def clean_title(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" '\"")
    return cleaned or None


def parse_block_from_index(lines: list[str], start: int) -> tuple[ParsedBlock | None, int]:
    line = lines[start].strip()
    index = start + 1
    warnings: list[str] = []

    exemption_concat = CONCATENATED_EXEMPTION.match(line)
    if exemption_concat:
        course_number = exemption_concat.group("number")
        title = clean_title(exemption_concat.group("middle"))
        exemption = parse_exemption_grade(line)
        if exemption is None:
            return None, index
        grade, credits, exemption_warnings = exemption
        warnings.extend(exemption_warnings)
        semester_line = lines[index].strip() if index < len(lines) else ""
        semester_code = parse_semester_from_line(semester_line)
        index += 1
        if not semester_code:
            return None, index
        marked_attempt = _marked_attempt_from_parts(line, semester_line, title)
        return (
            ParsedBlock(
                course_number=course_number,
                semester_code=semester_code,
                grade=grade,
                credits_earned=credits,
                title=title,
                confidence=0.86,
                warnings=tuple(warnings),
                marked_attempt=marked_attempt,
            ),
            index,
        )

    concatenated = CONCATENATED_ROW.match(line)
    if concatenated:
        course_number = concatenated.group("number")
        credits = parse_credits_token(concatenated.group("credits"))
        title = clean_title(concatenated.group("middle"))
        if credits is None:
            return None, index
        return finish_block(
            course_number=course_number,
            index=index,
            lines=lines,
            title=title,
            credits=credits,
            warnings=warnings,
            confidence=0.92,
        )

    if not COURSE_NUMBER_ONLY.match(line):
        return None, index

    course_number = line
    title_parts: list[str] = []
    credits: float | None = None

    while index < len(lines):
        current = lines[index].strip()
        if not current:
            index += 1
            continue
        if is_course_start(current) or is_header_or_footer(current):
            break

        if parse_exemption_grade(current):
            grade, exemption_credits, exemption_warnings = parse_exemption_grade(current)
            warnings.extend(exemption_warnings)
            index += 1
            semester_line = lines[index].strip() if index < len(lines) else ""
            semester_code = parse_semester_from_line(semester_line)
            index += 1
            if not semester_code:
                return None, index
            block_title = clean_title(" ".join(title_parts))
            marked_attempt = _marked_attempt_from_parts(current, semester_line, block_title)
            return (
                ParsedBlock(
                    course_number=course_number,
                    semester_code=semester_code,
                    grade=grade,
                    credits_earned=exemption_credits,
                    title=block_title,
                    confidence=0.85,
                    warnings=tuple(warnings),
                    marked_attempt=marked_attempt,
                ),
                index,
            )

        title_part, parsed_credits = split_title_and_credits(current)
        if parsed_credits is not None:
            if title_part:
                title_parts.append(title_part)
            credits = parsed_credits
            index += 1
            break

        title_parts.append(title_part or current)
        index += 1

    if credits is None:
        return None, index

    return finish_block(
        course_number=course_number,
        index=index,
        lines=lines,
        title=clean_title(" ".join(title_parts)),
        credits=credits,
        warnings=warnings,
        confidence=0.9,
    )


def find_body_start(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if "SEMESTER" in line.upper() or "סמסטר" in line:
            return index + 1
    for index, line in enumerate(lines):
        if is_course_start(line.strip()):
            return index
    return 0


def parse_technion_official_transcript(raw_text: str) -> tuple[list[ParsedCourseEntry], list[str]]:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    warnings: list[str] = []
    blocks: list[ParsedBlock] = []

    start = find_body_start(lines)
    index = start
    while index < len(lines):
        line = lines[index]
        if is_header_or_footer(line) or not is_course_start(line):
            index += 1
            continue

        block, next_index = parse_block_from_index(lines, index)
        if block:
            blocks.append(block)
        index = max(next_index, index + 1)

    if not blocks and raw_text.strip():
        warnings.append("No course rows detected in transcript text.")

    deduped: dict[tuple[str, str, float, float, int], ParsedBlock] = {}
    for block in blocks:
        key = (
            block.course_number,
            block.semester_code,
            block.grade,
            block.credits_earned,
            block.marked_attempt,
        )
        existing = deduped.get(key)
        if existing is None or block.confidence >= existing.confidence:
            deduped[key] = block

    attempt_rows = [
        _AttemptBlock(block=block, attempt=block.marked_attempt) for block in deduped.values()
    ]
    assigned_rows = assign_sequential_course_attempts(
        attempt_rows,
        course_number=lambda row: row.block.course_number,
        semester_code=lambda row: row.block.semester_code,
        attempt=lambda row: row.attempt,
        with_attempt=lambda row, resolved: replace(row, attempt=resolved),
    )

    courses = [
        ParsedCourseEntry(
            courseNumber=row.block.course_number,
            semesterCode=row.block.semester_code,
            grade=row.block.grade,
            creditsEarned=row.block.credits_earned,
            attempt=row.attempt,
            title=row.block.title,
            confidence=row.block.confidence,
            warnings=list(row.block.warnings),
        )
        for row in assigned_rows
    ]
    courses.sort(key=lambda item: (item.semesterCode, item.courseNumber))
    return courses, warnings
