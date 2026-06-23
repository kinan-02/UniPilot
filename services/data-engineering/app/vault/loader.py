"""Load Obsidian wiki pages from the catalog vault."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.paths import catalog_vault_wiki_root

FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


@dataclass(frozen=True)
class WikiPage:
    slug: str
    path: Path
    frontmatter: dict[str, Any]
    body: str
    english_body: str

    @property
    def title(self) -> str:
        value = self.frontmatter.get("title")
        return str(value) if value else self.slug

    @property
    def title_he(self) -> str | None:
        value = self.frontmatter.get("title_he")
        return str(value) if value else None

    @property
    def page_type(self) -> str | None:
        value = self.frontmatter.get("type")
        return str(value) if value else None


def _unwrap_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] in "'\"" and value[0] == value[-1]:
        return value[1:-1]
    return value


def _parse_scalar(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return ""
    if stripped.startswith("[") and stripped.endswith("]"):
        inner = stripped[1:-1].strip()
        if not inner:
            return []
        parts = [_unwrap_wrapping_quotes(part.strip()) for part in inner.split(",")]
        return [part for part in parts if part]
    if stripped.lower() in {"true", "false"}:
        return stripped.lower() == "true"
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    if re.fullmatch(r"-?\d+\.\d+", stripped):
        return float(stripped)
    return _unwrap_wrapping_quotes(stripped)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}, text

    frontmatter: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = _parse_scalar(value)

    body = text[match.end() :]
    return frontmatter, body


def english_section(body: str) -> str:
    marker = "## נתונים בעברית"
    if marker in body:
        return body.split(marker, 1)[0].strip()
    return body.strip()


def load_wiki_page(path: Path) -> WikiPage:
    text = path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(text)
    slug = path.stem
    return WikiPage(
        slug=slug,
        path=path,
        frontmatter=frontmatter,
        body=body.strip(),
        english_body=english_section(body),
    )


def wiki_root(vault_path: Path | None = None) -> Path:
    if vault_path is not None:
        candidate = vault_path / "wiki" if (vault_path / "wiki").is_dir() else vault_path
        return candidate.resolve()
    return catalog_vault_wiki_root().resolve()


def iter_wiki_pages(root: Path, *, subdir: str | None = None) -> list[WikiPage]:
    base = root / subdir if subdir else root
    if not base.exists():
        return []
    pages: list[WikiPage] = []
    for path in sorted(base.rglob("*.md")):
        if path.name in {"index.md", "log.md"}:
            continue
        pages.append(load_wiki_page(path))
    return pages


def load_pages_by_slug(root: Path) -> dict[str, WikiPage]:
    pages: dict[str, WikiPage] = {}
    for subdir in ("entities", "courses", "concepts", "sources"):
        for page in iter_wiki_pages(root, subdir=subdir):
            pages[page.slug] = page
    return pages


def extract_field(text: str, label: str) -> str | None:
    pattern = re.compile(rf"\*\*{re.escape(label)}:\*\*\s*(.+)", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1).strip()


def extract_wikilinks(text: str) -> list[str]:
    return [match.group(1).strip() for match in WIKILINK_PATTERN.finditer(text)]
