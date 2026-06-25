---
title: Ingestion Plan — Technion Full Catalog 2025/2026
title_he: תוכנית עיבוד — קטלוג הטכניון המלא תשפ״ו
type: concept
tags: [meta, ingestion, planning]
sources: 1
created: 2026-06-21
updated: 2026-06-24
---

# Ingestion Plan — Technion Full Catalog 2025/2026

**Source file:** `raw/catalog2025-26.pdf`  
**Total pages:** ~380  
**Total lines (pdftotext):** ~70,809  
**Actual wiki pages created:** 1,968 (105 entities, 11 concepts, 1,852 courses, 2 sources)  
**Ingestion depth:** Level A (full) — faculty entity + track pages + individual course pages for all units  
**STATUS: ✅ COMPLETE — Remediation finished 2026-06-24**  
- 0 missing track table references (down from 514 at start)
- 2,582 cross-links in track tables (100% coverage)
- 100% schema validity, 100% bilingual coverage
- 0 pages with Hebrew-as-English titles

---

## Document Map (Page Ranges)

| Section | Content | Pages | Status |
|---------|---------|-------|--------|
| **Part A** | General Technion info + academic calendar | 4–27 | ✅ DONE |
| **Part B** | Undergraduate regulations | 28–41 | ✅ DONE |
| **Part C** | Graduate regulations | 42–72 | ✅ DONE |
| **Part D — Faculty 01** | הנדסה אזרחית וסביבתית (Civil & Environmental Engineering) | 73–95 | ✅ Pass1+Pass2 (102 course pages, 001xxx) |
| **Part D — Faculty 02** | הנדסת מכונות (Mechanical Engineering) | 96–103 | ✅ Pass1+Pass2 (37 course pages, 003xxx) |
| **Part D — Faculty 03** | הנדסת חשמל ומחשבים (Electrical & Computer Engineering) | 104–129 | ✅ Pass1+Pass2 (136 course pages, 004xxx) |
| **Part D — Faculty 04** | הנדסה כימית (Chemical Engineering) | 130–139 | ✅ Pass1+Pass2 (15 course pages, 005xxx — partial) |
| **Part D — Faculty 05** | הנדסת ביוטכנולוגיה ומזון (Biotechnology & Food Engineering) | 140–145 | ✅ Pass1 done; Pass2 in progress (006xxx) |
| **Part D — Faculty 06** | הנדסת אוירונוטיקה וחלל (Aerospace Engineering) | 146–155 | ✅ Pass1+Pass2 (18 course pages, 008xxx) |
| **Part D — Faculty 07** | מדעי הנתונים וההחלטות (DDS) | 156–168 | ✅ DONE (from DDS catalog; 37 course pages, 09xxxx) |
| **Part D — Faculty 08** | מתמטיקה (Mathematics) | 169–178 | ✅ Pass1+Pass2 (53 course pages, 010xxx) |
| **Part D — Faculty 09** | פיזיקה (Physics) | 179–193 | ✅ Pass1+Pass2 (37 course pages, 011xxx) |
| **Part D — Faculty 10** | כימיה (Chemistry) | 194–205 | ✅ Pass1+Pass2 (91 course pages, 012xxx) |
| **Part D — Faculty 11** | ביולוגיה (Biology) | 206–216 | ✅ Pass1+Pass2 (43 course pages, 013xxx) |
| **Part D — Faculty 12** | ארכיטקטורה ובינוי ערים (Architecture & Town Planning) | 217–228 | ✅ Pass1+Pass2 (45 course pages, 020xxx) |
| **Part D — Faculty 13** | חינוך למדע וטכנולוגיה (Education in Science & Technology) | 229–245 | ✅ Pass1 done; Pass2 via shared-faculty courses |
| **Part D — Faculty 14** | מדעי המחשב (Computer Science) | 246–269 | ✅ Pass1+Pass2 (66 course pages, 023xxx) |
| **Part D — Faculty 15** | רפואה (Medicine) | 270–288 | ✅ Pass1 done; Pass2 in progress |
| **Part D — Faculty 16** | מדע והנדסה של חומרים (Materials Science & Engineering) | 289–299 | ✅ Pass1+Pass2 (16 course pages, 031xxx) |
| **Part D — Dept 17** | לימודים הומניסטיים ואמנויות (Humanities & Arts) | 300–301 | ✅ Pass1 done; Pass2 via 039xxx (2 pages) |
| **Part D — Faculty 18** | הנדסה ביו-רפואית (Biomedical Engineering) | 302–312 | ✅ Pass1 done; Pass2 in progress (033xxx) |
| **Part D — Inter 01** | מתמטיקה שימושית (Applied Mathematics) | 313 | ✅ Pass1 done (entity page) |
| **Part D — Inter 02** | ננו-מדעים וננו-טכנולוגיה (Nano Science & Technology) | 314 | ✅ Pass1 done (entity page) |
| **Part D — Inter 03** | ביוטכנולוגיה (Biotechnology, interdisciplinary) | 315 | ✅ Pass1 done (entity page) |
| **Part D — Inter 04** | הנדסת פולימרים (Polymer Engineering) | 316 | ✅ Pass1 done (entity page) |
| **Part D — Inter 05** | הנדסת תכן וניהול הייצור (Design & Production Management) | 317 | ✅ Pass1 done (entity page) |
| **Part D — Inter 06** | הנדסת מערכות (Systems Engineering) | 318 | ✅ Pass1 done (entity page) |
| **Part D — Inter 07** | אנרגיה (Energy) | 319–320 | ✅ Pass1 done (entity page) |
| **Part D — Inter 08** | מערכות אוטונומיות ורובוטיקה (Autonomous Systems & Robotics) | 321 | ✅ Pass1 done (entity page) |
| **Part D — Inter 09** | הנדסה עירונית (Urban Engineering) | 322 | ✅ Pass1 done (entity page) |
| **Part D — Inter 10** | הנדסה ימית (Naval Engineering) | 323–325 | ✅ Pass1 done (entity page) |
| **Part E** | Appendices (regulations, student rights, discipline) | 326–380 | ✅ DONE |

---

## Ingestion Phases

### Phase 0 — Infrastructure ✅ DONE
- [x] CLAUDE.md updated for Technion-wide scope
- [x] This ingestion plan created
- [x] `wiki/sources/technion-full-catalog-2025-2026.md` (source summary page) ✅
- [x] `wiki/entities/technion.md` (institution entity page) ✅

### Phase 1 — University-Wide Regulations (Pages 1–72) ✅ DONE (graduate regs in progress)

**Wiki pages created:**
- [x] `wiki/concepts/academic-calendar.md` ✅
- [x] `wiki/concepts/regulations-undergraduate.md` ✅
- [x] `wiki/concepts/regulations-graduate.md` ✅
- [x] `wiki/concepts/technion-specializations.md` ✅

**Priority:** HIGH — these rules apply to every student regardless of faculty.

---

### Phase 2 — Faculty Ingests (Pages 73–325)

Run in **4 parallel batches**. Within each batch, spawn one agent per faculty simultaneously. Each agent reads its page range (1–2 reads of 20 pages max), then writes all wiki pages.

---

#### Batch A — Pages 73–155 (4 faculties, ~83 pages)

Spawn 4 agents simultaneously:

| Agent | Faculty | Pages | Size | Expected wiki pages |
|-------|---------|-------|------|---------------------|
| A1 | הנדסה אזרחית וסביבתית (Civil & Environmental Eng.) | 73–95 | 23 pp | ~40–60 |
| A2 | הנדסת מכונות (Mechanical Engineering) | 96–103 | 8 pp | ~20–30 |
| A3 | הנדסת חשמל ומחשבים (Electrical & Computer Eng.) | 104–129 | 26 pp | ~50–80 |
| A4 | הנדסה כימית + ביוטכנולוגיה + אוירונוטיקה (Chemical + Biotech + Aerospace) | 130–155 | 26 pp | ~40–60 |

**After Batch A:** Update `index.md`, `log.md`. Verify cross-links.

---

#### Batch B — Pages 169–228 (5 faculties, ~60 pages)

Spawn 5 agents simultaneously (skip pages 156–168 = DDS, already done):

| Agent | Faculty | Pages | Size | Expected wiki pages |
|-------|---------|-------|------|---------------------|
| B1 | מתמטיקה (Mathematics) | 169–178 | 10 pp | ~15–25 |
| B2 | פיזיקה (Physics) | 179–193 | 15 pp | ~25–35 |
| B3 | כימיה (Chemistry) | 194–205 | 12 pp | ~20–30 |
| B4 | ביולוגיה (Biology) | 206–216 | 11 pp | ~20–30 |
| B5 | ארכיטקטורה ובינוי ערים (Architecture & Town Planning) | 217–228 | 12 pp | ~20–30 |

**After Batch B:** Update `index.md`, `log.md`.

---

#### Batch C — Pages 229–299 (4 faculties, ~71 pages)

Spawn 4 agents simultaneously:

| Agent | Faculty | Pages | Size | Expected wiki pages |
|-------|---------|-------|------|---------------------|
| C1 | חינוך למדע וטכנולוגיה (Education in Science & Technology) | 229–245 | 17 pp | ~25–40 |
| C2 | מדעי המחשב (Computer Science) | 246–269 | 24 pp | ~50–80 |
| C3 | רפואה (Medicine) | 270–288 | 19 pp | ~30–50 |
| C4 | מדע והנדסה של חומרים (Materials Science & Engineering) | 289–299 | 11 pp | ~20–30 |

**After Batch C:** Update `index.md`, `log.md`.

---

#### Batch D — Pages 300–325 (2 depts + 10 interdisciplinary, ~26 pages)

Spawn 3 agents simultaneously:

| Agent | Unit | Pages | Notes |
|-------|------|-------|-------|
| D1 | לימודים הומניסטיים + הנדסה ביו-רפואית (Humanities + Biomedical Eng.) | 300–312 | 13 pp |
| D2 | Interdisciplinary programs 1–5 (Applied Math + Nano + Biotech + Polymer + Design/Prod) | 313–317 | 5 pp (1 page each) |
| D3 | Interdisciplinary programs 6–10 (Systems Eng + Energy + Robotics + Urban + Naval) | 318–325 | 8 pp |

**After Batch D:** Update `index.md`, `log.md`.

---

### Phase 3 — Appendices (Pages 326–380)

**Read strategy:** 3 reads (pages 326–345, 346–365, 366–380)

**Wiki pages to create:**
- `wiki/concepts/student-discipline-regulations.md` — התקנון המשמעתי
- `wiki/concepts/student-rights.md` — חוק זכויות הסטודנט 2007
- `wiki/concepts/sexual-harassment-prevention.md` — נוהל למניעת הטרדה מינית
- `wiki/concepts/reserve-service-adaptations.md` — נוהל שירות מילואים
- `wiki/concepts/pregnancy-fertility-adaptations.md` — נוהל הריון ופוריות
- `wiki/concepts/research-ethics.md` — אתיקה של המחקר המדעי

**Priority:** MEDIUM — important for advisors answering questions about rights and accommodations.

---

### Phase 4 — Cross-Linking and Lint ✅ After all phases

1. Run `/lint` — find orphan pages, missing cross-references, contradictions
2. Update `wiki/overview.md` with full Technion-wide synthesis
3. Expand the Hebrew mapping table in CLAUDE.md with all track slugs from ingested faculties
4. Final `log.md` entry documenting completion

---

## Status Tracking

Update the ☐/✅ markers in the Document Map as each section is completed.

**Last updated:** 2026-06-23  
**Phases completed:** Phase 0 ✅, Phase 1 ✅, Phase 2 Pass 1 ✅, Phase 2 Pass 2 ✅, Phase 3 ✅, Verification pass ✅  
**Wiki size:** 104 entity pages + 11 concept pages + 1100 course pages + 2 source pages = **1217 pages total**  
**Verification pass result:** 0 broken links | 0 missing title_he | 0 missing Hebrew sections | 18 stub pages created for missing tracks | 38 DDS course pages patched (trailing-quote bug fixed + Hebrew sections added)  
**Course coverage (all faculties ✅):**  
- Civil (001xxx): 102 | Mechanical (003xxx): 37 | ECE (004xxx): 136 | Chemical (005xxx): 23  
- Biotechnology (006xxx): 64 | Aerospace (008xxx): 102 | DDS (09xxxx): 37  
- Math (010xxx): 51 | Physics (011xxx): 37 | Chemistry (012xxx): 91 | Biology (013xxx): 43  
- Architecture (020xxx): 45 | CS (023xxx): 66 | Medicine (027xxx): 111  
- Materials (031xxx): 71 | Biomedical (033xxx): 26  
**Next step:** ✅ ALL PHASES COMPLETE — wiki is ready for use as advisor agent knowledge base. Stub tracks (18 pages) may be enriched from catalog pages if deeper detail is needed.

---

## Reading Commands

Extract any page range with:
```bash
pdftotext -f <start_page> -l <end_page> "raw/catalog2025-26.pdf" -
```

Full text extraction (for grep):
```bash
pdftotext "raw/catalog2025-26.pdf" - | grep -n "search term"
```

Note: Text is Hebrew RTL. Table values may be reversed. Always cross-check credit values that appear ambiguous.

## Sources

- [[technion-full-catalog-2025-2026]]
