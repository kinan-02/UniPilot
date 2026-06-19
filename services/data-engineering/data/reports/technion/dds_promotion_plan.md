# DDS Production Promotion Plan (Phase 11 — Dry Run)

Generated: 2026-06-19T17:36:43+00:00
Gate status: **pass**
Can promote (future Phase 12): **True**

> **No production writes were performed in this phase.**

## Summary
Gate passed. Phase 12 may implement promote-dds-to-production after explicit approval.

## Policies applied
- nonExecutableRulesPolicy: `advisory-only`
- enforceNonExecutableRulesInProduction: `False`
- productionExcludedCoursePolicy: `omit-from-production-do-not-ingest`
- productionExcludedCourseNumbers: 14 courses
- signedOffBy: project-owner at 2026-06-19T17:16:42+00:00

## Planned production writes (counts)
- degreePrograms: 3
- hardDegreeRequirements: 19
- advisoryCatalogRules: 44
- courses: 2204
- courseOfferings: 2806
- skippedItems: 36
- skippedExcludedCourses: 14

## Target collections
- degreePrograms → `degree_programs`
- hardDegreeRequirements → `degree_requirements`
- advisoryCatalogRules → `catalog_rules`
- courses → `courses`
- courseOfferings → `course_offerings`

## Advisory rule handling
- 22 rule/group identifiers promoted as **advisory-only** (enforceInGraduationProgress=false).

## Skipped / excluded courses
- `00960226` — production-excluded-by-human-signoff
- `00960244` — production-excluded-by-human-signoff
- `00960251` — production-excluded-by-human-signoff
- `00960293` — production-excluded-by-human-signoff
- `00960311` — production-excluded-by-human-signoff
- `00960335` — production-excluded-by-human-signoff
- `00960351` — production-excluded-by-human-signoff
- `00960470` — production-excluded-by-human-signoff
- `00970211` — production-excluded-by-human-signoff
- `00970280` — production-excluded-by-human-signoff
- `00970329` — production-excluded-by-human-signoff
- `00980312` — production-excluded-by-human-signoff
- `00980455` — production-excluded-by-human-signoff
- `02740300` — production-excluded-by-human-signoff

## Gate checks
- [PASS] staging.program_count: Found 3 staged DDS programs (expected 3).
- [PASS] staging.program_codes: All expected program codes present.
- [PASS] staging.total_credits: All programs have totalCredits=155.0.
- [PASS] staging.requirement_groups: Found 41 staged requirement groups.
- [PASS] staging.courses: Found 2204 staged courses.
- [PASS] staging.offerings: Found 2806 staged course offerings.
- [PASS] staging.safety_flags: All staging documents have isStaging=true and productionEligible=false.
- [PASS] policy.human_signoff_present: humanSignoff metadata present on staged programs.
- [PASS] policy.non_executable_advisory: nonExecutableRulesPolicy is advisory-only.
- [PASS] policy.no_mandatory_non_executable: enforceNonExecutableRulesInProduction is false.
- [PASS] policy.excluded_courses_policy: productionExcludedCoursePolicy is omit-from-production-do-not-ingest.
- [PASS] policy.excluded_courses_list: Production-excluded course list matches expected 14 numbers.
- [PASS] quality.no_production_blockers: No production blockers in live quality review.
- [PASS] quality.missing_title_hints: missingTitleHints is 0.
- [PASS] quality.credit_mismatches: creditMismatches is 0.
- [PASS] quality.chain_rules_preserved: No chain/focus rule violations.
- [PASS] quality.ocr_suspects: No known OCR suspect gaps.
- [PASS] production.collections_read_only: Dry-run performed without production writes.
- [PASS] plan.no_excluded_courses_in_writes: Excluded courses are not in planned course writes.
- [PASS] plan.advisory_rules_not_mandatory: All advisory catalog rules have enforceInGraduationProgress=false.

## Production safety
- **No production collection writes occurred.**
- Production collections are empty.

## Rollback notes
- Phase 11 dry-run only — no production documents were written.
- Phase 12 should support promotion run id + snapshot for rollback.
- Do not delete staging data during promotion.
- Advisory catalog rules must remain non-enforced in graduation progress.

## Phase 12 recommendation
Implement `promote-dds-to-production` only after explicit approval, with `--i-confirm-dangerous-production-write` and idempotent upsert semantics.
