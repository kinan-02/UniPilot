"""Unit tests for app/vault/markdown_tables.py (77% → ~100%)."""

from __future__ import annotations

import pytest

from app.vault.markdown_tables import (
    MarkdownTable,
    _is_separator_row,
    _split_cells,
    find_table_with_header,
    parse_markdown_tables,
    table_after_heading,
)


# ---------------------------------------------------------------------------
# _split_cells
# ---------------------------------------------------------------------------

class TestSplitCells:
    def test_simple_row(self):
        result = _split_cells("| a | b | c |")
        assert result == ["a", "b", "c"]

    def test_strips_whitespace(self):
        result = _split_cells("|  hello  |  world  |")
        assert result == ["hello", "world"]

    def test_row_without_leading_pipe(self):
        result = _split_cells("a | b | c")
        # strips leading/trailing | then splits
        assert "a" in result
        assert "b" in result

    def test_preserves_pipes_inside_wikilinks(self):
        result = _split_cells("| [[00940345-discrete-mathematics|0940345]] | מתמטיקה | **\\*** |")
        assert result[0] == "[[00940345-discrete-mathematics|0940345]]"
        assert result[1] == "מתמטיקה"
        assert result[2] == "**\\***"


# ---------------------------------------------------------------------------
# _is_separator_row
# ---------------------------------------------------------------------------

class TestIsSeparatorRow:
    def test_simple_dashes(self):
        assert _is_separator_row(["---", "---"]) is True

    def test_with_colons(self):
        assert _is_separator_row([":---", "---:", ":---:"]) is True

    def test_not_separator(self):
        assert _is_separator_row(["header1", "header2"]) is False

    def test_mixed_not_separator(self):
        assert _is_separator_row(["---", "value"]) is False

    def test_empty_cells_ignored(self):
        assert _is_separator_row(["---", "", "---"]) is True


# ---------------------------------------------------------------------------
# parse_markdown_tables
# ---------------------------------------------------------------------------

SIMPLE_TABLE = """
| Name | Age |
|------|-----|
| Alice | 30 |
| Bob | 25 |
""".strip()

class TestParseMarkdownTables:
    def test_parses_simple_table(self):
        tables = parse_markdown_tables(SIMPLE_TABLE)
        assert len(tables) == 1
        table = tables[0]
        assert table.headers == ["Name", "Age"]
        assert len(table.rows) == 2

    def test_no_tables_in_text(self):
        tables = parse_markdown_tables("No table here\nJust text")
        assert tables == []

    def test_multiple_tables(self):
        text = """
| A | B |
|---|---|
| 1 | 2 |

| X | Y |
|---|---|
| 3 | 4 |
""".strip()
        tables = parse_markdown_tables(text)
        assert len(tables) == 2

    def test_table_without_separator_skipped(self):
        text = "| A | B |\n| 1 | 2 |"
        tables = parse_markdown_tables(text)
        assert tables == []

    def test_header_line_at_end_of_text_skipped(self):
        text = "| A | B |"
        tables = parse_markdown_tables(text)
        assert tables == []

    def test_row_data_preserved(self):
        tables = parse_markdown_tables(SIMPLE_TABLE)
        assert tables[0].rows[0] == ["Alice", "30"]
        assert tables[0].rows[1] == ["Bob", "25"]


# ---------------------------------------------------------------------------
# table_after_heading
# ---------------------------------------------------------------------------

HEADING_AND_TABLE = """
# My Section

| Col1 | Col2 |
|------|------|
| R1   | V1   |

# Other Section

Some text
""".strip()


class TestTableAfterHeading:
    def test_finds_table_after_heading(self):
        table = table_after_heading(HEADING_AND_TABLE, "My Section")
        assert table is not None
        assert table.headers[0] == "Col1"

    def test_returns_none_when_heading_not_found(self):
        table = table_after_heading(HEADING_AND_TABLE, "Nonexistent Section")
        assert table is None

    def test_returns_none_when_no_table_after_heading(self):
        text = "# No Table Here\n\nJust some text"
        table = table_after_heading(text, "No Table Here")
        assert table is None

    def test_case_insensitive_heading_match(self):
        table = table_after_heading(HEADING_AND_TABLE, "my section")
        assert table is not None

    def test_stops_at_first_table_under_heading(self):
        text = """
## Section

| A | B |
|---|---|
| 1 | 2 |

| C | D |
|---|---|
| 3 | 4 |
""".strip()
        table = table_after_heading(text, "Section")
        assert table is not None
        assert table.headers == ["A", "B"]


# ---------------------------------------------------------------------------
# find_table_with_header
# ---------------------------------------------------------------------------

class TestFindTableWithHeader:
    def test_finds_table_by_header_fragment(self):
        text = """
| CourseNumber | Title |
|---|---|
| 01234567 | Intro |
""".strip()
        table = find_table_with_header(text, "CourseNumber")
        assert table is not None
        assert "CourseNumber" in table.headers

    def test_returns_none_when_no_match(self):
        text = """
| A | B |
|---|---|
| 1 | 2 |
""".strip()
        result = find_table_with_header(text, "NotExisting")
        assert result is None

    def test_case_insensitive_match(self):
        text = """
| CourseNumber | Title |
|---|---|
| 01234567 | Intro |
""".strip()
        table = find_table_with_header(text, "coursenumber")
        assert table is not None
