---
title: Remediation Plan — Completeness and Organizational Fixes
title_he: תוכנית תיקון — מילוי פערים ותיקון מבנה
type: concept
tags: [meta, remediation, planning]
sources: 0
created: 2026-06-23
updated: 2026-06-24
---

# Remediation Plan — 2026-06-23 (COMPLETE 2026-06-24)

Derived from the deep audit. Addresses all completeness gaps and organizational issues found.

---

## Summary of Issues

| Category | Issue | Scale |
|----------|-------|-------|
| Organizational | Track pages list course codes as plain text — no wiki links to course pages | All ~50 track pages |
| Organizational | Index.md doesn't catalog non-DDS courses | 1,062 pages |
| Completeness | Missing courses referenced in track tables | 514 unique codes |
| Completeness | Missing courses from faculty own-prefix in PDF | ~1,063 pages |
| Completeness | Unknown-prefix codes in track tables (019, 021, 032, etc.) | ~89 codes |
| Schema | (Fixed) 8 wrong-type, 4 stray files, DDS 7/8-digit mismatch | Done ✅ |

---

## Phase 1 — Organizational Fixes (automated, no PDF) ✅ → IN PROGRESS

### Step 1.1 — Add wiki cross-links in track tables
- Read every non-stub track page in `wiki/entities/`
- Find 8-digit course codes in table rows
- For each code that has a wiki page, replace `00140003` with `[[00140003-statistics|00140003]]`
- For codes without a wiki page yet, leave as plain text (will be linked after Phase 2)
- Tool: Python script on all track files

### Step 1.2 — Update index.md with course catalog section
- Add a "Course Catalog" section explaining the wiki/courses/ structure
- Add faculty-by-faculty course count table pointing to the prefix patterns
- Avoids listing all 1,100+ pages individually

---

## Phase 2 — Supplemental Course Ingestion (parallel agents)

**Total new pages to create: ~1,063 (from PDF) + ~89 (unknown prefix)**

### Wave 1 — 4 agents simultaneously (highest impact: cross-referenced courses)

| Agent | Faculty | PDF Pages | Missing | Priority reason |
|-------|---------|-----------|---------|-----------------|
| 2A | Mathematics (010xxx) | 169–178 | 127 | Referenced in 15+ other faculty tracks |
| 2B | Physics (011xxx) | 179–193 | 51 | Referenced in ECE, CS, Aerospace, BME tracks |
| 2C | Mechanical Engineering (003xxx) | 96–103 | 93 | 104 missing from Mech track table |
| 2D | Chemical Engineering (005xxx) | 130–139 | 45 | 21 missing from Chem track table |

### Wave 2 — 3 agents simultaneously (large faculty catalogs)

| Agent | Faculty | PDF Pages | Missing | Notes |
|-------|---------|-----------|---------|-------|
| 2E | Civil Engineering (001xxx) | 73–95 | 219 | Large elective catalog |
| 2F | Architecture (020xxx) | 217–228 | 165 | Studio + elective courses |
| 2G | CS (023xxx) | 246–269 | 184 | Includes grad courses (023400+) |

### Wave 3 — 3 agents simultaneously (medium gaps)

| Agent | Faculty | PDF Pages | Missing | Notes |
|-------|---------|-----------|---------|-------|
| 2H | Medicine (027xxx) | 270–288 | 121 | Clinical + graduate courses |
| 2I | Chemistry (012xxx) + Biology (013xxx) | 194–216 | 19+14 | Two faculties, one agent |
| 2J | ECE sub-dept (004xxx) | 104–129 | 22 | Sub-dept labs 0044–0047xxx |

### Wave 4 — Small fixes (inline, no agent needed)

- Materials: 2 missing (`03141000`, `03150062`) — extract inline from PDF pp 289-299
- Aerospace: 1 missing (`00805852`) — extract inline from PDF pp 146-155

### Wave 5 — Unknown prefix investigation

Unknown-prefix codes found in track tables:
- **019xxx (11 codes)**: Likely Applied Mathematics interdisciplinary courses (program code 19)
  → Search PDF pp 313 (Applied Math section) + any faculty section that listed them
- **021xxx (43 codes)**: Appear in Architecture/Education tracks — possibly Architecture sub-dept
  → Search PDF Architecture section pp 217-228 and Education pp 229-245
- **032xxx (20 codes)**: Language Center courses (different from 039 Humanities)
  → Search PDF Humanities/Arts section pp 300-301
- **000xxx, 002xxx, 034xxx, 035xxx, 054xxx, 088xxx**: Single codes each — investigate in PDF
- **009xxx (12 codes)**: DDS 8-digit codes — check if alias fix resolved them, otherwise add 8-digit pages

---

## Phase 3 — Track Cross-Linking Pass (after Phase 2 complete)

Re-run Step 1.1 script after all Phase 2 courses are in place, to link the newly created pages.

---

## Phase 4 — Final Verification

1. Re-run full verification suite (broken links, schema, Hebrew sections)
2. Re-run track-table coverage check (should be near 0 missing)
3. Re-run PDF vs wiki comparison (measure gap reduction)
4. Update `wiki/log.md` with final counts
5. Update `wiki/index.md` header with new totals
6. Update `wiki/ingestion-plan-full-catalog.md` — mark remediation complete

---

## Status Tracking

| Phase                                        | Status | Notes |
| -------------------------------------------- | ------ | ----- |
| Phase 1.1 — Track cross-linking              | ✅     | 2,582 cross-links, 100% coverage |
| Phase 1.2 — Index update                     | ✅     | Faculty-by-prefix course catalog table added |
| Phase 2 Wave 1 (Math, Physics, Mech, Chem)   | ✅     | 1,852 total course pages created |
| Phase 2 Wave 2 (Civil, Architecture, CS)     | ✅     | All faculties complete |
| Phase 2 Wave 3 (Medicine, Chem+Bio, ECE)     | ✅     | All faculties complete |
| Phase 2 Wave 4 (Materials, Aerospace inline) | ✅     | Done inline |
| Phase 2 Wave 5 (Unknown prefixes)            | ✅     | 019/021/032/039 all resolved |
| Phase 3 — Cross-linking re-run               | ✅     | 0 unlinked codes, all tracks covered |
| Phase 4 — Final verification                 | ✅     | 100% schema valid, 100% bilingual, 0 Hebrew-as-English titles |

## Sources
- [[technion-full-catalog-2025-2026]]
