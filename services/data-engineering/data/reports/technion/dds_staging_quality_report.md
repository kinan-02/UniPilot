# DDS Staging Quality Report

Generated: 2026-06-19T17:01:43+00:00
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
- missingCatalogCourseReferences: 14
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
- [FAIL] crosslink.course_reference_coverage: Course reference coverage 83.33% (70/84 referenced numbers in staging_courses).
- [PASS] rules.non_executable_preserved: IE/IS chain rules remain non-mandatory.
- [PASS] production.collections_untouched: Production collections are empty.

## Production blockers
- 44 non-executable rule groups require human signoff before production.
- Missing catalog course 00960226 may be OCR-corrupted. Nearby staged matches: ['00960426', '00960267', '00960266']
- Missing catalog course 00960244 may be OCR-corrupted. Nearby staged matches: ['00960644', '00960414', '00960324']
- Missing catalog course 00960251 may be OCR-corrupted. Nearby staged matches: ['00970251', '00960625', '00960501']
- Missing catalog course 00960293 may be OCR-corrupted. Nearby staged matches: ['00960693', '00960291', '00960290']
- Missing catalog course 00960311 may be OCR-corrupted. Nearby staged matches: ['00960411', '00960231', '00960211']
- Missing catalog course 00960335 may be OCR-corrupted. Nearby staged matches: ['00960336', '00960235', '00960135']
- Missing catalog course 00960351 may be OCR-corrupted. Nearby staged matches: ['00960501', '00960235', '00960231']
- Missing catalog course 00960470 may be OCR-corrupted. Nearby staged matches: ['00960570', '00960475', '00960450']
- Missing catalog course 00970211 may be OCR-corrupted. Nearby staged matches: ['00970251', '00970217', '00970215']
- Missing catalog course 00970280 may be OCR-corrupted. Nearby staged matches: ['00970980', '00970920', '00970800']
- Missing catalog course 00970329 may be OCR-corrupted. Nearby staged matches: ['00970325', '00970249', '00970209']
- Missing catalog course 00980312 may be OCR-corrupted. Nearby staged matches: ['00980322', '00980310', '00980123']
- Missing catalog course 00980455 may be OCR-corrupted. Nearby staged matches: ['00980425', '00850455', '00980460']
- Missing catalog course 02740300 may be OCR-corrupted. Nearby staged matches: ['02770300', '02740320', '03240630']

## API migration blockers
- API migration must expose non-executable rules as manual-review items or remain staging-only.

## Course reference coverage
- Coverage: 83.33%
- Missing in staging_courses: 14

## Missing title hints
- Count: 0

## Recommendations
- Do not promote to production until human signoff on non-executable rules and OCR-suspect numbers.
- Phase 10 does not modify staged records; use this report to design a promotion gate.
- Course JSON is offering evidence only — never infer degree requirements from it.

## Production safety
- **No production writes occurred in this phase.**
- Production collections with data: none
