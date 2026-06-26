# DDS Production Promotion Plan (Phase 11 — Dry Run)

Generated: 2026-06-26T13:05:27+00:00
Gate status: **pass-with-warnings**
Can promote (future Phase 12): **True**

> **No production writes were performed in this phase.**

## Summary
Gate passed with warnings. Phase 12 may implement promote-dds-to-production with explicit approval and dangerous confirmation flag.

## Policies applied
- nonExecutableRulesPolicy: `advisory-only`
- enforceNonExecutableRulesInProduction: `False`
- productionExcludedCoursePolicy: `omit-from-production-do-not-ingest`
- productionExcludedCourseNumbers: 183 courses
- signedOffBy: vault-wiki at 2026-06-26T13:05:21+00:00

## Planned production writes (counts)
- degreePrograms: 7
- catalogPathOptions: 18
- catalogFaculties: 1
- hardDegreeRequirements: 20
- advisoryCatalogRules: 71
- courses: 2466
- courseOfferings: 6004
- skippedItems: 254
- skippedExcludedCourses: 183

## Target collections
- degreePrograms → `degree_programs`
- catalogPathOptions → `catalog_path_options`
- catalogFaculties → `catalog_faculties`
- hardDegreeRequirements → `degree_requirements`
- advisoryCatalogRules → `catalog_rules`
- courses → `courses`
- courseOfferings → `course_offerings`

## Advisory rule handling
- 71 rule/group identifiers promoted as **advisory-only** (enforceInGraduationProgress=false).

## Skipped / excluded courses
- `00440102` — production-excluded-by-catalog-signoff
- `00440105` — production-excluded-by-catalog-signoff
- `00440127` — production-excluded-by-catalog-signoff
- `00440131` — production-excluded-by-catalog-signoff
- `00440137` — production-excluded-by-catalog-signoff
- `00440157` — production-excluded-by-catalog-signoff
- `00440167` — production-excluded-by-catalog-signoff
- `00440169` — production-excluded-by-catalog-signoff
- `00460210` — production-excluded-by-catalog-signoff
- `01040012` — production-excluded-by-catalog-signoff
- `01040013` — production-excluded-by-catalog-signoff
- `01040016` — production-excluded-by-catalog-signoff
- `01040031` — production-excluded-by-catalog-signoff
- `01040032` — production-excluded-by-catalog-signoff
- `01040033` — production-excluded-by-catalog-signoff
- `01040034` — production-excluded-by-catalog-signoff
- `01040066` — production-excluded-by-catalog-signoff
- `01040122` — production-excluded-by-catalog-signoff
- `01040134` — production-excluded-by-catalog-signoff
- `01040135` — production-excluded-by-catalog-signoff
- ... and 163 more

## Gate checks
- [PASS] staging.program_count: Found 7 staged computer-science programs (expected at least 1).
- [PASS] staging.program_codes: All expected program codes present.
- [PASS] staging.total_credits: All programs have valid totalCredits.
- [PASS] staging.requirement_groups: Found 91 staged requirement groups.
- [PASS] staging.courses: Found 2620 staged courses.
- [PASS] staging.offerings: Found 6590 staged course offerings.
- [PASS] staging.safety_flags: All staging documents have isStaging=true and productionEligible=false.
- [PASS] policy.catalog_signoff_present: vaultSignoff metadata present on staged programs.
- [PASS] policy.non_executable_advisory: nonExecutableRulesPolicy is advisory-only.
- [PASS] policy.no_mandatory_non_executable: enforceNonExecutableRulesInProduction is false.
- [PASS] policy.excluded_courses_policy: productionExcludedCoursePolicy is omit-from-production-do-not-ingest.
- [PASS] policy.excluded_courses_list: Production-excluded course list matches catalog refs absent from semester JSON staging.
- [PASS] policy.non_executable_groups_signed_off: All staged non-executable groups are covered by catalog sign-off.
- [PASS] quality.no_production_blockers: No production blockers in live quality review.
- [PASS] quality.missing_title_hints: missingTitleHints is 0.
- [PASS] quality.credit_mismatches: creditMismatches is 0.
- [PASS] quality.chain_rules_preserved: No chain/focus rule violations.
- [PASS] quality.ocr_suspects: No known OCR suspect gaps.
- [PASS] production.collections_read_only: Dry-run performed without production writes.
- [FAIL] production.existing_data: Production collections already contain data: {'catalog_rules': 71, 'completed_courses': 31, 'course_offerings': 6557, 'courses': 2614, 'degree_programs': 10, 'degree_requirements': 36, 'promotion_runs': 12, 'semester_plans': 86}
- [PASS] plan.no_excluded_courses_in_writes: Excluded courses are not in planned course writes.
- [PASS] plan.advisory_rules_not_mandatory: All advisory catalog rules have enforceInGraduationProgress=false.

## Warnings
- Production collections already contain data: {'catalog_rules': 71, 'completed_courses': 31, 'course_offerings': 6557, 'courses': 2614, 'degree_programs': 10, 'degree_requirements': 36, 'promotion_runs': 12, 'semester_plans': 86}

## Production safety
- **No production collection writes occurred.**
- Existing production data (review only): {'catalog_rules': 71, 'completed_courses': 31, 'course_offerings': 6557, 'courses': 2614, 'degree_programs': 10, 'degree_requirements': 36, 'promotion_runs': 12, 'semester_plans': 86}

## Rollback notes
- Phase 11 dry-run only — no production documents were written.
- Phase 12 should support promotion run id + snapshot for rollback.
- Do not delete staging data during promotion.
- Advisory catalog rules must remain non-enforced in graduation progress.

## Phase 12 recommendation
Implement `promote-dds-to-production` only after explicit approval, with `--i-confirm-dangerous-production-write` and idempotent upsert semantics.
