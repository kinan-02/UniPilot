# DDS Production Promotion Plan (Phase 11 — Dry Run)

Generated: 2026-06-21T21:04:49+00:00
Gate status: **pass-with-warnings**
Can promote (future Phase 12): **True**

> **No production writes were performed in this phase.**

## Summary
Gate passed with warnings. Phase 12 may implement promote-dds-to-production with explicit approval and dangerous confirmation flag.

## Policies applied
- nonExecutableRulesPolicy: `advisory-only`
- enforceNonExecutableRulesInProduction: `False`
- productionExcludedCoursePolicy: `omit-from-production-do-not-ingest`
- productionExcludedCourseNumbers: 41 courses
- signedOffBy: vault-wiki at 2026-06-21T20:54:37+00:00

## Planned production writes (counts)
- degreePrograms: 3
- hardDegreeRequirements: 19
- advisoryCatalogRules: 35
- courses: 2068
- courseOfferings: 2638
- skippedItems: 111
- skippedExcludedCourses: 41

## Target collections
- degreePrograms → `degree_programs`
- hardDegreeRequirements → `degree_requirements`
- advisoryCatalogRules → `catalog_rules`
- courses → `courses`
- courseOfferings → `course_offerings`

## Advisory rule handling
- 35 rule/group identifiers promoted as **advisory-only** (enforceInGraduationProgress=false).

## Skipped / excluded courses
- `00400314` — production-excluded-by-catalog-signoff
- `00401222` — production-excluded-by-catalog-signoff
- `00401422` — production-excluded-by-catalog-signoff
- `00401652` — production-excluded-by-catalog-signoff
- `00402731` — production-excluded-by-catalog-signoff
- `00402851` — production-excluded-by-catalog-signoff
- `00940179` — production-excluded-by-catalog-signoff
- `00940197` — production-excluded-by-catalog-signoff
- `00960221` — production-excluded-by-catalog-signoff
- `00960226` — production-excluded-by-catalog-signoff
- `00960244` — production-excluded-by-catalog-signoff
- `00960251` — production-excluded-by-catalog-signoff
- `00960292` — production-excluded-by-catalog-signoff
- `00960293` — production-excluded-by-catalog-signoff
- `00960311` — production-excluded-by-catalog-signoff
- `00960335` — production-excluded-by-catalog-signoff
- `00960351` — production-excluded-by-catalog-signoff
- `00960401` — production-excluded-by-catalog-signoff
- `00960425` — production-excluded-by-catalog-signoff
- `00960470` — production-excluded-by-catalog-signoff
- ... and 21 more

## Gate checks
- [PASS] staging.program_count: Found 3 staged DDS programs (expected 3).
- [PASS] staging.program_codes: All expected program codes present.
- [PASS] staging.total_credits: All programs have totalCredits=155.0.
- [PASS] staging.requirement_groups: Found 54 staged requirement groups.
- [PASS] staging.courses: Found 2068 staged courses.
- [PASS] staging.offerings: Found 2638 staged course offerings.
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
- [FAIL] production.existing_data: Production collections already contain data: {'catalog_rules': 35, 'completed_courses': 8, 'course_offerings': 2638, 'courses': 2068, 'degree_programs': 3, 'degree_requirements': 19, 'promotion_runs': 4, 'semester_plans': 132}
- [PASS] plan.no_excluded_courses_in_writes: Excluded courses are not in planned course writes.
- [PASS] plan.advisory_rules_not_mandatory: All advisory catalog rules have enforceInGraduationProgress=false.

## Warnings
- Production collections already contain data: {'catalog_rules': 35, 'completed_courses': 8, 'course_offerings': 2638, 'courses': 2068, 'degree_programs': 3, 'degree_requirements': 19, 'promotion_runs': 4, 'semester_plans': 132}

## Production safety
- **No production collection writes occurred.**
- Existing production data (review only): {'catalog_rules': 35, 'completed_courses': 8, 'course_offerings': 2638, 'courses': 2068, 'degree_programs': 3, 'degree_requirements': 19, 'promotion_runs': 4, 'semester_plans': 132}

## Rollback notes
- Phase 11 dry-run only — no production documents were written.
- Phase 12 should support promotion run id + snapshot for rollback.
- Do not delete staging data during promotion.
- Advisory catalog rules must remain non-enforced in graduation progress.

## Phase 12 recommendation
Implement `promote-dds-to-production` only after explicit approval, with `--i-confirm-dangerous-production-write` and idempotent upsert semantics.
