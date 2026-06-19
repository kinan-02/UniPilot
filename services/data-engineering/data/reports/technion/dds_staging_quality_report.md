# DDS Staging Quality Report

Generated: 2026-06-19T17:17:00+00:00
Status: **pass-with-warnings**
Recommendation: **ready-for-production-promotion-design**

> Phase 10 report-only validation — no staged or production records were modified.

## Summary
Staged DDS catalog and course data are structurally present. Production promotion remains blocked pending human signoff and metadata fixes.

## Counts
- programs: 3
- requirementGroups: 41
- catalogRules: 22
- stagedCourses: 2204
- stagedOfferings: 2806
- uniqueCatalogCourseReferences: 84
- missingCatalogCourseReferences: 0
- productionExcludedCatalogCourseReferences: 14
- missingTitleHints: 0
- creditMismatches: 0
- manualReviewRequiredItems: 175
- executableRuleGroups: 19
- nonExecutableRuleGroups: 44
- ocrSuspectMissingCourses: 0

## Checks
- [PASS] catalog.program_count: Found 3 DDS programs (expected 3).
- [PASS] catalog.total_credits: All programs have totalCredits=155.0.
- [PASS] catalog.requirement_groups: Found 41 requirement groups (expected 41).
- [PASS] catalog.non_executable_rules: Found 22 catalog rules (expected 22).
- [PASS] catalog.signoff_review: signoffReview metadata present on programs.
- [PASS] catalog.curation_status: curationStatus is ready-for-staging-with-review-flags.
- [PASS] courses.staging_records: Found 2204 Technion staged courses.
- [PASS] courses.offerings: Found 2806 staged course offerings.
- [PASS] courses.production_eligible_false: All staged courses have productionEligible=false.
- [PASS] courses.is_staging_true: All staged courses have isStaging=true.
- [PASS] courses.no_requirement_inference: Course JSON metadata does not infer degree requirements.
- [PASS] crosslink.course_reference_coverage: Course reference coverage 120.0% (84/70 in-scope referenced numbers in staging_courses).
- [PASS] rules.non_executable_preserved: IE/IS chain rules remain non-mandatory.
- [PASS] production.collections_untouched: Production collections are empty.

## Production blockers
- None

## API migration blockers
- None

## Course reference coverage
- Coverage: 120.0%
- Missing in staging_courses: 0

## Missing title hints
- Count: 0

## Recommendations
- Non-executable rule groups are signed off for advisory use only; do not auto-enforce in production.
- Do not promote to production until human signoff on non-executable rules and OCR-suspect numbers.
- Phase 10 does not modify staged records; use this report to design a promotion gate.
- Course JSON is offering evidence only — never infer degree requirements from it.

## Production safety
- **No production writes occurred in this phase.**
- Production collections with data: none
