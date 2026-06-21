# Wiki Log

Append-only. New entries go at the top.
Parse with: `grep "^## \[" wiki/log.md | head -10`

---

## [2026-06-21] ingest | Phase 0–1 + Phase 3 (appendices) — Technion Full Catalog 2025/2026

- Summary: Ingested pages 1–72 (regulations + calendar) and general Technion info from the 380-page catalog. Source summary page created. Two background agents handling graduate regulations (pages 42–72) and appendices (pages 326–380).
- Pages created (completed):
  - wiki/sources/technion-full-catalog-2025-2026.md — full catalog source summary with document map
  - wiki/entities/technion.md — Technion entity page: history, leadership, 18 faculties, all student services with contacts
  - wiki/concepts/academic-calendar.md — full 2025/2026 calendar: winter/spring/summer semesters, moed A/B dates, all holidays, grad school deadlines
  - wiki/concepts/regulations-undergraduate.md — comprehensive BSc regulations: passing grade (55), GPA threshold (65), non-regular standing (8 conditions), honors (84/91), language/physics requirements, exam rules, grade appeals, max load (29), re-admission
  - wiki/concepts/technion-specializations.md — Entrepreneurial Leadership Minor: 10 credits, 3-layer structure, eligibility (36 credits + avg >75), transcript appendix
- Pages created (background agents — all ✅):
  - wiki/concepts/regulations-graduate.md ✅ — pages 42–72; MSc/PhD degree types (MSc/ME/MBA/MArch/MUE), admission GPA thresholds, tuition structure (₪484 registration + 200–300%), scholarship stipends, English requirement, research ethics (21-question Moodle), MSc tracks + time limits (8–10 semesters), PhD qualifying exam (תיאור תמציתי, ≤11 months, ≥5-member committee), direct-PhD eligibility (GPA ≥90), leave of absence rules
  - wiki/concepts/student-rights.md ✅ — Student Rights Law 5767-2007; foundational rights, admission/scholarship/exam rights, Ombudsman (נציב קבילות §22)
  - wiki/concepts/student-discipline-regulations.md ✅ — Disciplinary Code (in force 2016, amended 2018); 20+ offenses, 3-tier judicial structure, 15 punishment types, statute of limitations (3 years)
  - wiki/concepts/reserve-service-adaptations.md ✅ — §19a + 5772-2012 national rules; special exam within 45 days, assignment extensions, tutoring entitlement, early course registration, scholarship/dormitory discretionary benefits, study extension for 150+ cumulative days, 2 academic credit option
  - wiki/concepts/pregnancy-fertility-adaptations.md ✅ — §19b; 21-day qualifying threshold, 4 qualifying events, 12 adaptation categories: 6-week/30% post-birth absence, 25% exam time extension, parking permit from month 7, partner/spouse rights (1-week absence, exam within 3 weeks of birth), 2-semester study extension
- Pages updated: wiki/index.md (added 2nd source, technion entity section, expanded concepts section)
- Next steps: Faculty ingestion (Phase 2) — 17 remaining faculties starting from highest priority

---

## [2026-06-21] schema-update | CLAUDE.md expanded for Technion-wide scope; ingestion plan created

- Summary: Expanded CLAUDE.md from DDS-specific to full Technion scope (all ~18 faculties); created detailed ingestion plan for 380-page Technion catalog.
- CLAUDE.md changes: updated Identity section (now Technion-wide advisor), added `faculty` frontmatter field, updated directory naming conventions, added Large Faculty Ingest Protocol (two-pass), added Parallel Agent Strategy reference, expanded Hebrew→slug mapping table to all 18 faculties + 10 interdisciplinary programs + university-wide concepts, updated Session Start Protocol to include ingestion plan.
- Pages created: wiki/ingestion-plan-full-catalog.md — full document map with page ranges for all 28 academic units, 4-batch parallel agent strategy, and status tracker.
- Source: raw/catalog2025-26.pdf — 380 pages, ~70,809 lines pdftotext.
- Next step: Phase 0 completion (source page + technion.md), then Phase 1 (regulations, pages 1–72).

---

## [2026-06-21] schema-update | Full Hebrew content added to all major pages

- Summary: All entity and concept pages now contain full Hebrew content sections (`## נתונים בעברית`) so the advisor agent can answer Hebrew queries by reading Hebrew text directly — not by translating English.
- CLAUDE.md updated: schema now mandates a `## נתונים בעברית` section on every entity/concept page, with all factual content (descriptions, credit requirements, rules, eligibility criteria, course lists) in Hebrew. Course pages must include `## פרטי הקורס בעברית`.
- Pages updated with full `## נתונים בעברית` sections:
  - entities: faculty-dds, track-data-information-engineering, track-industrial-engineering-management, track-information-systems-engineering, program-excellence, program-avivim, program-alonim, program-barak-at, minor-robotics, minor-economics, graduate-programs
  - concepts: focus-chains, specialization-cognitive-science, specialization-math-analysis
- Coverage: descriptions, credit breakdowns, semester tables, course lists, rules, eligibility criteria — all now available in Hebrew
- Course pages: Hebrew course names were already in titles and tables; full `## פרטי הקורס בעברית` sections to be added as part of next content pass

---

## [2026-06-21] schema-update | Bilingual support (Hebrew + English)
- Summary: Added bilingual support rules to CLAUDE.md schema and retroactively added title_he + aliases frontmatter to all high-priority pages.
- CLAUDE.md changes: updated frontmatter template (added title_he, aliases fields); added "Bilingual Support" section with language-detection rules, Hebrew→page mapping table, and ingest rules for Hebrew sources.
- Pages updated with title_he + aliases:
  - entities: faculty-dds, track-data-information-engineering, track-industrial-engineering-management, track-information-systems-engineering, program-excellence, program-avivim, program-alonim, program-barak-at, program-dual-medicine, minor-robotics, minor-economics, graduate-programs
  - concepts: focus-chains, specialization-cognitive-science, specialization-math-analysis
  - courses: 0940224, 0940345, 0940424, 0960411, 0960570, 0970200, 0970209, 0970215 (and all remaining course pages have Hebrew names inline in their titles)
- Remaining course pages: Hebrew name is embedded in the title field (e.g. "Statistics 1 (סטטיסטיקה 1)") — sufficient for full-text search. Add explicit aliases field to any course page when that page is next edited.

---

## [2026-06-21] ingest | Technion DDS Catalog 2025/2026

- Summary: Ingested the full Technion Faculty of Data Science & Decisions undergraduate/graduate catalog for academic year 2025/2026 (PDF, ~155 pages, 2676 lines extracted text). Wiki now covers the complete faculty structure for use as truth source for an academic advisor agent.
- Pages created:
  - wiki/sources/technion-dds-catalog-2025-2026.md
  - wiki/entities/faculty-dds.md
  - wiki/entities/ran-smorodinsky.md
  - wiki/entities/track-data-information-engineering.md
  - wiki/entities/track-industrial-engineering-management.md
  - wiki/entities/track-information-systems-engineering.md
  - wiki/entities/program-excellence.md
  - wiki/entities/program-avivim.md
  - wiki/entities/program-alonim.md
  - wiki/entities/program-barak-at.md
  - wiki/entities/program-dual-medicine.md
  - wiki/entities/minor-robotics.md
  - wiki/entities/minor-economics.md
  - wiki/entities/graduate-programs.md
  - wiki/concepts/specialization-cognitive-science.md
  - wiki/concepts/specialization-math-analysis.md
  - wiki/concepts/focus-chains.md
  - wiki/courses/0940224-data-structures-algorithms.md
  - wiki/courses/0940241-database-management.md
  - wiki/courses/0940290-science-elective-dne.md
  - wiki/courses/0940312-deterministic-or-models.md
  - wiki/courses/0940314-stochastic-or-models.md
  - wiki/courses/0940345-discrete-mathematics.md
  - wiki/courses/0940411-probability.md
  - wiki/courses/0940424-statistics-1.md
  - wiki/courses/0940564-senior-seminar.md
  - wiki/courses/0940700-dne-practicum.md
  - wiki/courses/0950605-intro-psychology.md
  - wiki/courses/0960210-ai-foundations.md
  - wiki/courses/0960211-ecommerce-models.md
  - wiki/courses/0960212-probabilistic-graphical-models.md
  - wiki/courses/0960219-software-engineering.md (= 0940219)
  - wiki/courses/0960224-distributed-info-management.md
  - wiki/courses/0960226-computation-game-theory-economics.md
  - wiki/courses/0960231-mathematical-models-advanced-ir.md
  - wiki/courses/0960250-distributed-information-systems.md
  - wiki/courses/0960275-human-factor-data-collection.md
  - wiki/courses/0960311-optimization-theory-algorithms.md
  - wiki/courses/0960317-cooperative-game-theory.md (= 0970317)
  - wiki/courses/0960324-service-systems-engineering.md
  - wiki/courses/0960327-nonlinear-or-models.md
  - wiki/courses/0960335-optimization-under-uncertainty.md
  - wiki/courses/0960411-industrial-statistics.md (= 0960414)
  - wiki/courses/0960411-machine-learning-1.md
  - wiki/courses/0960570-game-theory-economic-behavior.md
  - wiki/courses/0960578-social-choice-joint-decisions.md
  - wiki/courses/0960606-behavioral-economics-technology.md
  - wiki/courses/0960617-thinking-decision-making.md
  - wiki/courses/0960693-psychological-cognitive-networks.md
  - wiki/courses/0960700-final-project-dne.md
  - wiki/courses/0970200-deep-learning.md
  - wiki/courses/0970209-machine-learning-2.md
  - wiki/courses/0970215-nlp-methods.md
  - wiki/courses/0970216-advanced-nlp.md
  - wiki/courses/0970317-cooperative-game-theory.md
  - wiki/courses/0970400-causal-inference.md
  - wiki/courses/0970414-statistics-2.md
  - wiki/courses/0970800-final-project-iem-ise.md
- Pages updated:
  - wiki/index.md — full content catalog added
  - wiki/overview.md — complete faculty synthesis
  - wiki/log.md (this entry)
- Contradictions flagged:
  - Course 0940312 credit value: 3.5 in robotics minor list vs. implied 4.0 from IEM/ISE semester totals
  - Course 0960211 (e-commerce models): DNE/IEM use code 0960211; ISE uses 0960221 — may be same or different course
- Note: RTL Hebrew PDF extracted via pdftotext; some table values may have minor parsing errors in credit counts

---

## [2026-06-21] init | Wiki created
- Schema written to CLAUDE.md
- Folder structure: raw/, raw/assets/, wiki/sources/, wiki/entities/, wiki/concepts/
- Files created: wiki/index.md, wiki/log.md, wiki/overview.md
- Sources: 0
- Pages: 1 (overview)
- Ready to ingest first source
