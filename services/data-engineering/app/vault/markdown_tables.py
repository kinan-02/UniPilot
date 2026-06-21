"""Parse markdown pipe tables from wiki page bodies."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MarkdownTable:
    headers: list[str]
    rows: list[list[str]]


TABLE_ROW_PATTERN = re.compile(r"^\s*\|(.+)\|\s*$")


def _split_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells if cell)


def parse_markdown_tables(text: str) -> list[MarkdownTable]:
    tables: list[MarkdownTable] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not TABLE_ROW_PATTERN.match(line):
            index += 1
            continue

        header_cells = _split_cells(line)
        index += 1
        if index >= len(lines):
            break

        separator_cells = _split_cells(lines[index])
        if not _is_separator_row(separator_cells):
            continue
        index += 1

        rows: list[list[str]] = []
        while index < len(lines) and TABLE_ROW_PATTERN.match(lines[index]):
            row_cells = _split_cells(lines[index])
            if _is_separator_row(row_cells):
                index += 1
                continue
            rows.append(row_cells)
            index += 1

        tables.append(MarkdownTable(headers=header_cells, rows=rows))

    return tables


def table_after_heading(text: str, heading: str) -> MarkdownTable | None:
    pattern = re.compile(rf"^#{{1,6}}\s+{re.escape(heading)}\s*$", re.MULTILINE | re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None
    remainder = text[match.end() :]
    tables = parse_markdown_tables(remainder)
    return tables[0] if tables else None


def find_table_with_header(text: str, header_fragment: str) -> MarkdownTable | None:
    for table in parse_markdown_tables(text):
        joined = " | ".join(table.headers).lower()
        if header_fragment.lower() in joined:
            return table
    return None
