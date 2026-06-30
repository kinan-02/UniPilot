"""Unified Academic Knowledge Graph retrieval engine using NetworkX."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

import networkx as nx

from app.services.semester_catalog import (
    SemesterCatalogInfo,
    discover_semester_catalogs,
    format_semester_catalog_summary,
    semester_info_from_path,
)

Intent = Literal[
    "schedule",
    "structure",
    "eligibility",
    "syllabus",
    "prerequisites",
    "course_info",
    "wiki_page",
    "wiki_search",
]

FRONTMATTER_TITLE_RE = re.compile(r'^title:\s*"?([^"\n]+)"?', re.MULTILINE)
FRONTMATTER_TITLE_HE_RE = re.compile(r"^title_he:\s*(.+)$", re.MULTILINE)
FRONTMATTER_ALIASES_RE = re.compile(r"^aliases:\s*\[(.+)\]", re.MULTILINE)
FRONTMATTER_TYPE_RE = re.compile(r"^type:\s*(\w+)", re.MULTILINE)

COURSE_CODE_RE = re.compile(r"\d{8}")
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
FRONTMATTER_COURSE_CODE_RE = re.compile(r'^course_code:\s*"?(\d{8})"?', re.MULTILINE)


def parse_prerequisites_string(prereq_string: str) -> dict[str, Any]:
    """Parse Hebrew prerequisite string into an AST (OR > AND > COURSE)."""
    text = (prereq_string or "").strip()
    if not text or text.lower() in {"none", "none listed", "אין"}:
        return {"type": "AND", "operands": []}

    tokens = _tokenize_prerequisites(text)
    if not tokens:
        return {"type": "AND", "operands": []}

    ast, pos = _parse_or(tokens, 0)
    if pos != len(tokens):
        raise ValueError(f"Unexpected tokens after position {pos}: {tokens[pos:]}")
    return ast


def _tokenize_prerequisites(text: str) -> list[str | tuple[str, str]]:
    tokens: list[str | tuple[str, str]] = []
    i = 0
    length = len(text)

    while i < length:
        if text[i].isspace():
            i += 1
            continue
        if text[i] == "(":
            tokens.append("(")
            i += 1
            continue
        if text[i] == ")":
            tokens.append(")")
            i += 1
            continue
        if text.startswith("או", i) and (i + 2 >= length or not text[i + 2].isalnum()):
            tokens.append("OR")
            i += 2
            continue
        if text.startswith("ו-", i):
            tokens.append("AND")
            i += 2
            continue

        match = COURSE_CODE_RE.match(text, i)
        if match:
            tokens.append(("COURSE", match.group(0)))
            i = match.end()
            continue

        i += 1

    return _strip_empty_parens(tokens)


def _strip_empty_parens(
    tokens: list[str | tuple[str, str]],
) -> list[str | tuple[str, str]]:
    """Remove empty () groups produced by malformed catalog strings."""
    cleaned: list[str | tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "(" and i + 1 < len(tokens) and tokens[i + 1] == ")":
            i += 2
            continue
        cleaned.append(tokens[i])
        i += 1
    return cleaned


def _parse_or(
    tokens: list[str | tuple[str, str]], pos: int
) -> tuple[dict[str, Any], int]:
    left, pos = _parse_and(tokens, pos)
    operands = [left]
    while pos < len(tokens) and tokens[pos] == "OR":
        pos += 1
        right, pos = _parse_and(tokens, pos)
        operands.append(right)
    if len(operands) == 1:
        return operands[0], pos
    return {"type": "OR", "operands": operands}, pos


def _parse_and(
    tokens: list[str | tuple[str, str]], pos: int
) -> tuple[dict[str, Any], int]:
    left, pos = _parse_primary(tokens, pos)
    operands = [left]
    while pos < len(tokens) and tokens[pos] == "AND":
        pos += 1
        right, pos = _parse_primary(tokens, pos)
        operands.append(right)
    if len(operands) == 1:
        return operands[0], pos
    return {"type": "AND", "operands": operands}, pos


def _parse_primary(
    tokens: list[str | tuple[str, str]], pos: int
) -> tuple[dict[str, Any], int]:
    if pos >= len(tokens):
        raise ValueError("Unexpected end of prerequisite expression")

    token = tokens[pos]
    if token == "(":
        expr, pos = _parse_or(tokens, pos + 1)
        if pos >= len(tokens) or tokens[pos] != ")":
            raise ValueError("Missing closing parenthesis")
        return expr, pos + 1
    if isinstance(token, tuple) and token[0] == "COURSE":
        return {"type": "COURSE", "id": token[1]}, pos + 1
    raise ValueError(f"Unexpected token at {pos}: {token!r}")


class AcademicGraphEngine:
    """Academic knowledge graph built from wiki markdown and Technion catalog JSON."""

    def __init__(self) -> None:
        self.graph: nx.DiGraph = nx.DiGraph()
        self.wiki_pages: dict[str, dict[str, Any]] = {}
        self.slug_to_course_code: dict[str, str] = {}
        self.course_catalog: dict[str, dict[str, Any]] = {}
        self.wiki_catalog: list[dict[str, Any]] = []
        self.available_semesters: list[SemesterCatalogInfo] = []
        self.active_semester: SemesterCatalogInfo | None = None
        self._semester_catalog_cache: dict[str, dict[str, dict[str, Any]]] = {}
        self._wiki_loaded = False
        self._loaded = False
        self._built = False

    @staticmethod
    def parse_prerequisites_string(prereq_string: str) -> dict[str, Any]:
        return parse_prerequisites_string(prereq_string)

    def load_wiki(self, md_dir_path: str) -> None:
        md_root = Path(md_dir_path)
        self.wiki_pages.clear()
        self.slug_to_course_code.clear()
        self.wiki_catalog.clear()

        for md_file in md_root.rglob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            slug = md_file.stem
            rel = md_file.relative_to(md_root).as_posix()
            course_code = _extract_course_code(content, slug)
            page_kind = _classify_page(rel)

            self.wiki_pages[slug] = {
                "slug": slug,
                "path": rel,
                "content": content,
                "course_code": course_code,
                "kind": page_kind,
            }
            if course_code:
                self.slug_to_course_code[slug] = course_code

            meta = _parse_frontmatter(content)
            self.wiki_catalog.append(
                {
                    "slug": slug,
                    "path": rel,
                    "kind": page_kind,
                    "course_code": course_code,
                    "title": meta.get("title", slug),
                    "title_he": meta.get("title_he", ""),
                    "aliases": meta.get("aliases", []),
                    "page_type": meta.get("type", page_kind),
                }
            )

        self._wiki_loaded = True
        self._loaded = True
        self._built = False

    def discover_semesters(self, technion_raw_dir: str) -> list[SemesterCatalogInfo]:
        self.available_semesters = discover_semester_catalogs(Path(technion_raw_dir))
        return self.available_semesters

    def load_semester_catalog(self, json_file_path: str) -> SemesterCatalogInfo:
        json_path = Path(json_file_path)
        info = semester_info_from_path(json_path)
        if info is None:
            raise ValueError(f"Unsupported semester catalog filename: {json_path.name}")

        if info.filename not in self._semester_catalog_cache:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            catalog: dict[str, dict[str, Any]] = {}
            for entry in raw:
                general = entry.get("general", {})
                code = str(general.get("מספר מקצוע", "")).strip()
                if code:
                    catalog[code] = entry
            self._semester_catalog_cache[info.filename] = catalog

        self.course_catalog = self._semester_catalog_cache[info.filename]
        self.active_semester = info
        self._loaded = True
        self._built = False
        return info

    def set_active_semester(self, filename: str, technion_raw_dir: str) -> SemesterCatalogInfo:
        path = Path(technion_raw_dir) / filename
        if not path.is_file():
            raise FileNotFoundError(f"Semester catalog not found: {path}")
        return self.load_semester_catalog(str(path))

    def load_from_paths(
        self,
        md_dir_path: str,
        technion_raw_dir: str,
        *,
        semester_filename: str | None = None,
    ) -> None:
        self.load_wiki(md_dir_path)
        self.discover_semesters(technion_raw_dir)
        if semester_filename:
            self.set_active_semester(semester_filename, technion_raw_dir)
        elif self.available_semesters:
            default = self.available_semesters[-1]
            self.load_semester_catalog(default.path)

    def load_data(self, md_dir_path: str, json_file_path: str) -> None:
        self.load_wiki(md_dir_path)
        info = self.load_semester_catalog(json_file_path)
        self.available_semesters = [info]

    def build_graph(self) -> nx.DiGraph:
        if not self._loaded:
            raise RuntimeError("Call load_data() before build_graph()")

        self.graph = nx.DiGraph()

        for code, entry in self.course_catalog.items():
            general = entry.get("general", {})
            prereq_raw = str(general.get("מקצועות קדם", "") or "").strip()
            prereq_ast: dict[str, Any] = {"type": "AND", "operands": []}
            if prereq_raw:
                try:
                    prereq_ast = parse_prerequisites_string(prereq_raw)
                except ValueError:
                    prereq_ast = {"type": "AND", "operands": []}
            self.graph.add_node(
                code,
                node_type="course",
                name=general.get("שם מקצוע", ""),
                syllabus=general.get("סילבוס", ""),
                schedule=entry.get("schedule", []),
                faculty=general.get("פקולטה", ""),
                credits=general.get("נקודות", ""),
                prerequisites_raw=prereq_raw,
                prerequisites_ast=prereq_ast,
            )

        for slug, page in self.wiki_pages.items():
            if slug not in self.graph:
                self.graph.add_node(
                    slug,
                    node_type=page["kind"],
                    course_code=page.get("course_code"),
                )

        for slug, page in self.wiki_pages.items():
            source_kind = page["kind"]
            source_course = page.get("course_code")
            for target_slug, _display in _extract_wikilinks(page["content"]):
                target = self.wiki_pages.get(target_slug)
                if not target:
                    continue
                target_kind = target["kind"]
                target_course = target.get("course_code") or self.slug_to_course_code.get(
                    target_slug
                )

                if source_kind == "track" and target_course:
                    self.graph.add_edge(slug, target_course, relation="contains")
                elif source_kind == "course" and target_kind == "track":
                    src = source_course or slug
                    self.graph.add_edge(src, target_slug, relation="belongs_to")

        for code, entry in self.course_catalog.items():
            prereq_raw = str(entry.get("general", {}).get("מקצועות קדם", "") or "").strip()
            if not prereq_raw:
                continue
            try:
                ast = parse_prerequisites_string(prereq_raw)
            except ValueError:
                continue
            for prereq_id in _collect_course_ids(ast):
                if prereq_id not in self.graph:
                    self.graph.add_node(prereq_id, node_type="course")
                self.graph.add_edge(code, prereq_id, relation="has_prerequisite")

        self._built = True
        return self.graph

    def evaluate_eligibility(
        self, course_id: str, completed_courses: list[str] | set[str] | None
    ) -> tuple[bool, list[str]]:
        if not self._built:
            raise RuntimeError("Call build_graph() before evaluate_eligibility()")

        completed = set(completed_courses or [])
        node = self.graph.nodes.get(course_id, {})
        ast = node.get("prerequisites_ast") or {"type": "AND", "operands": []}
        missing = _missing_from_ast(ast, completed)
        return len(missing) == 0, missing

    def retrieve_context(
        self,
        intent: Intent,
        course_id: str | None = None,
        user_completed_courses: list[str] | None = None,
        wiki_slug: str | None = None,
        search_query: str | None = None,
    ) -> str:
        if not self._built:
            raise RuntimeError("Call build_graph() before retrieve_context()")

        if intent == "schedule":
            if not course_id:
                raise ValueError("course_id is required for schedule intent")
            return self._context_schedule(course_id)
        if intent == "structure":
            if not course_id:
                raise ValueError("course_id is required for structure intent")
            return self._context_structure(course_id)
        if intent == "eligibility":
            if not course_id:
                raise ValueError("course_id is required for eligibility intent")
            return self._context_eligibility(course_id, user_completed_courses or [])
        if intent == "syllabus":
            if not course_id:
                raise ValueError("course_id is required for syllabus intent")
            return self._context_syllabus(course_id)
        if intent == "prerequisites":
            if not course_id:
                raise ValueError("course_id is required for prerequisites intent")
            return self._context_prerequisites(course_id)
        if intent == "course_info":
            if not course_id:
                raise ValueError("course_id is required for course_info intent")
            return self._context_course_info(course_id)
        if intent == "wiki_page":
            if not wiki_slug:
                raise ValueError("wiki_slug is required for wiki_page intent")
            return self._context_wiki_page(wiki_slug)
        if intent == "wiki_search":
            if not search_query:
                raise ValueError("search_query is required for wiki_search intent")
            return self._context_wiki_search(search_query)
        raise ValueError(f"Unknown intent: {intent}")

    def execute_retrievals(
        self,
        actions: list[dict[str, Any]],
        user_completed_courses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run multiple retrieval actions and return structured blocks."""
        if not self._built:
            raise RuntimeError("Call build_graph() before execute_retrievals()")

        blocks: list[dict[str, Any]] = []
        completed = user_completed_courses or []

        for action in actions:
            intent = action.get("intent")
            course_id = action.get("course_id")
            wiki_slug = action.get("wiki_slug")
            search_query = action.get("search_query")

            context = self.retrieve_context(
                intent=intent,
                course_id=course_id,
                user_completed_courses=completed,
                wiki_slug=wiki_slug,
                search_query=search_query,
            )

            facts: dict[str, Any] = {}
            if intent == "eligibility" and course_id:
                eligible, missing = self.evaluate_eligibility(course_id, completed)
                facts = {
                    "eligible": eligible,
                    "missing_prerequisites": missing,
                    "course_id": course_id,
                }

            blocks.append(
                {
                    "intent": intent,
                    "course_id": course_id,
                    "wiki_slug": wiki_slug,
                    "search_query": search_query,
                    "context": context,
                    "facts": facts,
                }
            )

        return blocks

    def get_semester_catalog_summary(self) -> str:
        return format_semester_catalog_summary(self.available_semesters)

    def get_wiki_catalog_summary(self, *, max_entries: int = 120) -> str:
        """Compact catalog for LLM routing (concepts, regulations, tracks first)."""
        priority_kinds = {"concept", "wiki", "track", "faculty"}
        prioritized = [
            entry
            for entry in self.wiki_catalog
            if entry.get("kind") in priority_kinds
            or entry.get("page_type") == "concept"
            or entry.get("path", "").startswith("concepts/")
        ]
        prioritized.sort(key=lambda e: (e.get("kind", ""), e.get("slug", "")))
        lines = [
            f"- {e['slug']}: {e.get('title_he') or e.get('title')} "
            f"({e.get('kind')})"
            for e in prioritized[:max_entries]
        ]
        return "\n".join(lines)

    def search_wiki(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Keyword search over wiki catalog and page bodies."""
        if not self._loaded:
            raise RuntimeError("Call load_data() before search_wiki()")

        tokens = _tokenize_search(query)
        if not tokens:
            return []

        scored: list[tuple[int, dict[str, Any]]] = []
        for slug, page in self.wiki_pages.items():
            meta = next((m for m in self.wiki_catalog if m["slug"] == slug), {})
            haystack = " ".join(
                [
                    slug,
                    meta.get("title", ""),
                    meta.get("title_he", ""),
                    " ".join(meta.get("aliases", [])),
                    page.get("content", "")[:4000],
                ]
            ).lower()
            score = sum(3 if token in haystack else 0 for token in tokens)
            if meta.get("kind") == "concept" or meta.get("path", "").startswith("concepts/"):
                score += sum(2 for token in tokens if token in haystack)
            if score > 0:
                scored.append((score, meta or {"slug": slug, "kind": page.get("kind")}))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    def graph_stats(self) -> dict[str, Any]:
        if not self._built:
            return {"loaded": self._loaded, "built": False}
        relations: dict[str, int] = {}
        for _, _, data in self.graph.edges(data=True):
            rel = data.get("relation", "unknown")
            relations[rel] = relations.get(rel, 0) + 1
        return {
            "loaded": True,
            "built": True,
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "courses_in_catalog": len(self.course_catalog),
            "wiki_pages": len(self.wiki_pages),
            "edge_relations": relations,
            "active_semester": self.active_semester.filename if self.active_semester else None,
            "active_semester_label": (
                self.active_semester.display_label if self.active_semester else None
            ),
            "available_semesters": [semester.filename for semester in self.available_semesters],
        }

    def _semester_header(self) -> str:
        if not self.active_semester:
            return "semester: unknown"
        return (
            f"semester: {self.active_semester.display_label} "
            f"({self.active_semester.filename})"
        )

    def _context_schedule(self, course_id: str) -> str:
        node = self.graph.nodes.get(course_id, {})
        name = node.get("name", course_id)
        schedule = node.get("schedule") or []
        if not schedule:
            return f"{self._semester_header()}\n{course_id} {name}: no schedule data."
        lines = [self._semester_header(), f"{course_id} {name} schedule:"]
        for slot in schedule:
            lines.append(
                f"- grp {slot.get('קבוצה')} {slot.get('סוג')} "
                f"{slot.get('יום')} {slot.get('שעה')} "
                f"{slot.get('מרצה/מתרגל', '')}".strip()
            )
        return "\n".join(lines)

    def _context_structure(self, course_id: str) -> str:
        node = self.graph.nodes.get(course_id, {})
        name = node.get("name", course_id)
        tracks = sorted(
            succ
            for succ in self.graph.successors(course_id)
            if self.graph.edges[course_id, succ].get("relation") == "belongs_to"
        )
        containers = sorted(
            pred
            for pred in self.graph.predecessors(course_id)
            if self.graph.edges[pred, course_id].get("relation") == "contains"
        )
        parts = [f"{course_id} {name}"]
        if tracks:
            parts.append(f"tracks: {', '.join(tracks)}")
        if containers:
            parts.append(f"contained_in: {', '.join(containers)}")
        if not tracks and not containers:
            parts.append("no structure links found")
        return " | ".join(parts)

    def _context_eligibility(self, course_id: str, completed: list[str]) -> str:
        eligible, missing = self.evaluate_eligibility(course_id, completed)
        node = self.graph.nodes.get(course_id, {})
        name = node.get("name", course_id)
        prereq_raw = node.get("prerequisites_raw", "")
        status = "eligible" if eligible else "not eligible"
        missing_text = ", ".join(missing) if missing else "none"

        prereq_edges = sorted(
            succ
            for succ in self.graph.successors(course_id)
            if self.graph.edges[course_id, succ].get("relation") == "has_prerequisite"
        )
        prereq_graph = f" | prereq_nodes: {', '.join(prereq_edges)}" if prereq_edges else ""

        return (
            f"{course_id} {name}: {status} | prereqs: {prereq_raw or 'none'} "
            f"| missing: {missing_text}{prereq_graph}"
        )

    def _context_syllabus(self, course_id: str) -> str:
        node = self.graph.nodes.get(course_id, {})
        name = node.get("name", course_id)
        syllabus = str(node.get("syllabus") or "").strip()
        if not syllabus:
            return f"{self._semester_header()}\n{course_id} {name}: no syllabus in catalog."
        return f"{self._semester_header()}\n{course_id} {name} syllabus:\n{syllabus[:2000]}"

    def _context_prerequisites(self, course_id: str) -> str:
        node = self.graph.nodes.get(course_id, {})
        name = node.get("name", course_id)
        prereq_raw = node.get("prerequisites_raw", "")
        prereq_ast = node.get("prerequisites_ast", {})
        prereq_edges = sorted(
            succ
            for succ in self.graph.successors(course_id)
            if self.graph.edges[course_id, succ].get("relation") == "has_prerequisite"
        )
        return (
            f"{course_id} {name} prerequisites:\n"
            f"raw: {prereq_raw or 'none'}\n"
            f"ast: {json.dumps(prereq_ast, ensure_ascii=False)}\n"
            f"edges: {', '.join(prereq_edges) if prereq_edges else 'none'}"
        )

    def _context_course_info(self, course_id: str) -> str:
        node = self.graph.nodes.get(course_id, {})
        if not node:
            return f"{course_id}: not found in catalog."
        return (
            f"{course_id} {node.get('name', '')} | "
            f"credits: {node.get('credits', '')} | "
            f"faculty: {node.get('faculty', '')} | "
            f"prereqs: {node.get('prerequisites_raw', 'none')}"
        )

    def _context_wiki_page(self, wiki_slug: str) -> str:
        page = self.wiki_pages.get(wiki_slug)
        if not page:
            return f"wiki page '{wiki_slug}' not found."
        body = _strip_frontmatter(page["content"])
        return f"wiki:{wiki_slug}\n{body[:3000]}"

    def _context_wiki_search(self, query: str) -> str:
        hits = self.search_wiki(query, limit=3)
        if not hits:
            return f"wiki_search '{query}': no matches."

        sections: list[str] = [f"wiki_search '{query}' top matches:"]
        for hit in hits:
            slug = hit.get("slug", "")
            page = self.wiki_pages.get(slug)
            if not page:
                continue
            title = hit.get("title_he") or hit.get("title") or slug
            body = _strip_frontmatter(page["content"])
            sections.append(f"\n--- {slug} ({title}) ---\n{body[:1500]}")
        return "\n".join(sections)


def _parse_frontmatter(content: str) -> dict[str, Any]:
    title_match = FRONTMATTER_TITLE_RE.search(content)
    title_he_match = FRONTMATTER_TITLE_HE_RE.search(content)
    aliases_match = FRONTMATTER_ALIASES_RE.search(content)
    type_match = FRONTMATTER_TYPE_RE.search(content)

    aliases: list[str] = []
    if aliases_match:
        aliases = [
            part.strip().strip('"').strip("'")
            for part in aliases_match.group(1).split(",")
            if part.strip()
        ]

    return {
        "title": title_match.group(1).strip() if title_match else "",
        "title_he": title_he_match.group(1).strip() if title_he_match else "",
        "aliases": aliases,
        "type": type_match.group(1) if type_match else "",
    }


def _strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            return content[end + 4 :].strip()
    return content.strip()


def _tokenize_search(query: str) -> list[str]:
    tokens = re.findall(r"[\w\u0590-\u05FF]+", query.lower())
    return [token for token in tokens if len(token) >= 2]


def _extract_course_code(content: str, slug: str) -> str | None:
    match = FRONTMATTER_COURSE_CODE_RE.search(content)
    if match:
        return match.group(1)
    slug_match = COURSE_CODE_RE.match(slug)
    return slug_match.group(0) if slug_match else None


def _classify_page(rel_path: str) -> str:
    if rel_path.startswith("courses/"):
        return "course"
    if rel_path.startswith("entities/tracks/"):
        return "track"
    if rel_path.startswith("entities/faculty"):
        return "faculty"
    return "wiki"


def _extract_wikilinks(content: str) -> list[tuple[str, str | None]]:
    return [(m.group(1).strip(), m.group(2)) for m in WIKILINK_RE.finditer(content)]


def _collect_course_ids(ast: dict[str, Any]) -> list[str]:
    node_type = ast.get("type")
    if node_type == "COURSE":
        return [ast["id"]]
    return [
        course_id
        for operand in ast.get("operands", [])
        for course_id in _collect_course_ids(operand)
    ]


def _missing_from_ast(ast: dict[str, Any], completed: set[str]) -> list[str]:
    node_type = ast.get("type")
    if node_type == "COURSE":
        return [] if ast["id"] in completed else [ast["id"]]
    if node_type == "AND":
        missing: list[str] = []
        for operand in ast.get("operands", []):
            missing.extend(_missing_from_ast(operand, completed))
        return _dedupe(missing)
    if node_type == "OR":
        branches = [_missing_from_ast(op, completed) for op in ast.get("operands", [])]
        if any(len(branch) == 0 for branch in branches):
            return []
        return min(branches, key=len)
    return []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


if __name__ == "__main__":
    root = _repo_root()
    md_dir = root / "services/data-engineering/data/catalog_valut/catalog_valut/wiki"
    technion_raw = root / "services/data-engineering/data/raw/technion"

    print("=== Prerequisite parser smoke test ===")
    sample = "(00440105 ו-00440140) או (00440105 ו-01140245) או (01140246 ו-00440105)"
    print(json.dumps(parse_prerequisites_string(sample), ensure_ascii=False, indent=2))

    engine = AcademicGraphEngine()
    engine.load_from_paths(
        str(md_dir),
        str(technion_raw),
        semester_filename="courses_2025_201.json",
    )
    engine.build_graph()
    print("\nGraph stats:", json.dumps(engine.graph_stats(), ensure_ascii=False, indent=2))

    print("\n--- Test 1: schedule (00440148) ---")
    print(engine.retrieve_context("schedule", course_id="00440148"))

    print("\n--- Test 2: eligibility (00440148, completed 00440105+00440140) ---")
    eligible, missing = engine.evaluate_eligibility(
        "00440148", ["00440105", "00440140"]
    )
    print(f"eligible={eligible}, missing={missing}")
    print(
        engine.retrieve_context(
            "eligibility",
            course_id="00440148",
            user_completed_courses=["00440105", "00440140"],
        )
    )

    print("\n--- Test 3: structure (00440148) ---")
    print(engine.retrieve_context("structure", course_id="00440148"))
