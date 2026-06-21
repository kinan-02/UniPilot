# DDS Production Promotion Report (Phase 12)

Promotion run: `dds-promotion-7dab26bc3683`
Started: 2026-06-21T22:02:36+00:00
Finished: 2026-06-21T22:02:36+00:00
Status: **failed**
Gate status: **pass**
Dry run: **False**
Confirmation flag: **False**
Production writes performed: **False**

## Policies applied
- nonExecutableRulesPolicy: `advisory-only`
- enforceNonExecutableRulesInProduction: `False`
- productionExcludedCoursePolicy: `omit-from-production-do-not-ingest`
- productionExcludedCourseNumbers: 1

## Counts planned
- degreePrograms: 3
- hardDegreeRequirements: 19
- advisoryCatalogRules: 35
- courses: 3
- courseOfferings: 3
- skippedItems: 36
- skippedExcludedCourses: 1

## Counts written

## Production collection counts
### Before
- catalog_rules: 0
- course_offerings: 0
- courses: 0
- degree_programs: 0
- degree_requirements: 0
- promotion_runs: 0
### After

## Skipped excluded courses
- `00960226` — production-excluded-by-catalog-signoff

## Advisory rule handling
- Non-executable groups promoted to `catalog_rules` with `enforceInGraduationProgress: false`.

## Rollback notes
- Delete production docs with promotionRunId=dds-promotion-7dab26bc3683 to roll back this run.
- Do not delete staging data.
- Advisory catalog rules remain non-enforced in graduation progress.

## Errors
- Refusing production promotion without --i-confirm-dangerous-production-write.

## Safety
- Staging collections were not modified.
- Production promotion used stable `productionKey` upserts.
- Roll back with `rollback-dds-production-promotion --promotion-run-id <id> --i-confirm-dangerous-production-write` (deletes only matching promotionRunId).
