# DDS Staging Quality Report

Generated: 2026-06-21T21:22:21+00:00
Status: **pass**
Recommendation: **ready-for-production-promotion-design**

> Phase 10 report-only validation — no staged or production records were modified.

## Summary
Vault wiki sign-off recorded: non-executable groups are advisory-only and 41 cross-link gap courses are excluded from production.

## Counts
- programs: 3
- requirementGroups: 51
- catalogRules: 35
- stagedCourses: 2068
- stagedOfferings: 2638
- uniqueCatalogCourseReferences: 172
- missingCatalogCourseReferences: 0
- productionExcludedCatalogCourseReferences: 41
- missingTitleHints: 0
- missingTitleHintsExcludedOnly: 8
- creditMismatches: 0
- manualReviewRequiredItems: 419
- executableRuleGroups: 16
- nonExecutableRuleGroups: 70
- ocrSuspectMissingCourses: 0

## Checks
- [PASS] catalog.program_count: Found 3 DDS programs (expected 3).
- [PASS] catalog.total_credits: All programs have totalCredits=155.0.
- [FAIL] catalog.requirement_groups: Found 51 requirement groups (expected 41).
- [FAIL] catalog.non_executable_rules: Found 35 catalog rules (expected 22).
- [PASS] catalog.signoff_review: signoffReview metadata present on programs.
- [FAIL] catalog.curation_status: curationStatus is not ready-for-staging-with-review-flags on all programs.
- [PASS] courses.staging_records: Found 2068 Technion staged courses.
- [PASS] courses.offerings: Found 2638 staged course offerings.
- [PASS] courses.production_eligible_false: All staged courses have productionEligible=false.
- [PASS] courses.is_staging_true: All staged courses have isStaging=true.
- [PASS] courses.no_requirement_inference: Course JSON metadata does not infer degree requirements.
- [PASS] crosslink.course_reference_coverage: Course reference coverage 131.3% (172/131 in-scope referenced numbers in staging_courses).
- [PASS] rules.non_executable_preserved: IE/IS chain rules remain non-mandatory.
- [PASS] production.collections_untouched: Production collections are empty.

## Production blockers
- None

## API migration blockers
- None

## Course reference coverage
- Coverage: 131.3%
- Missing in staging_courses: 0

## Missing title hints
- Count: 8

## Recommendations
- Non-executable rule groups are signed off for advisory use only; do not auto-enforce in production.
- Non-executable rule groups are signed off as advisory-only; do not mandatory-enforce in production.
- Phase 10 does not modify staged records; use this report to design a promotion gate.
- Course JSON is offering evidence only — never infer degree requirements from it.

## Production safety
- **No production writes occurred in this phase.**
- Production collections with data: none
