# DDS Staging Quality Report

Generated: 2026-07-03T09:15:37+00:00
Status: **pass**
Recommendation: **ready-for-production-promotion-design**

> Phase 10 report-only validation — no staged or production records were modified.

## Summary
Vault wiki sign-off recorded: non-executable groups are advisory-only and 43 cross-link gap courses are excluded from production.

## Counts
- programs: 5
- requirementGroups: 80
- catalogRules: 0
- stagedCourses: 2620
- stagedOfferings: 6590
- uniqueCatalogCourseReferences: 263
- missingCatalogCourseReferences: 0
- productionExcludedCatalogCourseReferences: 43
- missingTitleHints: 0
- missingTitleHintsExcludedOnly: 0
- creditMismatches: 0
- manualReviewRequiredItems: 85
- executableRuleGroups: 26
- nonExecutableRuleGroups: 54
- ocrSuspectMissingCourses: 0
- crossFacultyCatalogReferences: 0

## Checks
- [PASS] catalog.program_count: Found 5 staged programs for medicine.
- [PASS] catalog.total_credits: All programs have totalCredits=155.0.
- [PASS] catalog.requirement_groups: Found 80 requirement groups for medicine.
- [PASS] catalog.non_executable_rules: Found 0 catalog rules for medicine.
- [PASS] catalog.signoff_review: signoffReview metadata present on programs.
- [FAIL] catalog.curation_status: curationStatus is not ready-for-staging-with-review-flags on all programs.
- [PASS] courses.staging_records: Found 2620 Technion staged courses.
- [PASS] courses.offerings: Found 6590 staged course offerings.
- [PASS] courses.production_eligible_false: All staged courses have productionEligible=false.
- [PASS] courses.is_staging_true: All staged courses have isStaging=true.
- [PASS] courses.no_requirement_inference: Course JSON metadata does not infer degree requirements.
- [PASS] crosslink.course_reference_coverage: Course reference coverage 119.55% (263/220 in-scope referenced numbers in staging_courses).
- [PASS] elective_chain.contract: Elective chain pools satisfy shared explorer contract.
- [PASS] rules.non_executable_preserved: IE/IS chain rules remain non-mandatory.
- [FAIL] production.collections_untouched: Production collections contain data: {'catalog_rules': 987, 'completed_courses': 192, 'course_offerings': 6450, 'courses': 2585, 'degree_programs': 61, 'degree_requirements': 316, 'promotion_runs': 47, 'semester_plans': 262}

## Production blockers
- None

## API migration blockers
- None

## Course reference coverage
- Coverage: 119.55%
- Missing in staging_courses: 0

## Missing title hints
- Count: 0

## Recommendations
- Non-executable rule groups are signed off for advisory use only; do not auto-enforce in production.
- Non-executable rule groups are signed off as advisory-only; do not mandatory-enforce in production.
- Phase 10 does not modify staged records; use this report to design a promotion gate.
- Course JSON is offering evidence only — never infer degree requirements from it.

## Production safety
- **No production writes occurred in this phase.**
- Production collections with data: {'catalog_rules': 987, 'completed_courses': 192, 'course_offerings': 6450, 'courses': 2585, 'degree_programs': 61, 'degree_requirements': 316, 'promotion_runs': 47, 'semester_plans': 262}
