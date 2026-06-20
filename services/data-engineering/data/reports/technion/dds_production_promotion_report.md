# DDS Production Promotion Report (Phase 12)

Promotion run: `dds-promotion-f92665dcf502`
Started: 2026-06-20T10:49:23+00:00
Finished: 2026-06-20T10:49:24+00:00
Status: **completed**
Gate status: **pass-with-warnings**
Dry run: **False**
Confirmation flag: **True**
Production writes performed: **True**

## Policies applied
- nonExecutableRulesPolicy: `advisory-only`
- enforceNonExecutableRulesInProduction: `False`
- productionExcludedCoursePolicy: `omit-from-production-do-not-ingest`
- productionExcludedCourseNumbers: 14

## Counts planned
- degreePrograms: 3
- hardDegreeRequirements: 19
- advisoryCatalogRules: 44
- courses: 2204
- courseOfferings: 2806
- skippedItems: 36
- skippedExcludedCourses: 14

## Counts written
- degree_programs: 3
- degree_requirements: 19
- catalog_rules: 44
- courses: 2204
- course_offerings: 2806

## Production collection counts
### Before
- catalog_rules: 44
- course_offerings: 2806
- courses: 2204
- degree_programs: 3
- degree_requirements: 19
- promotion_runs: 3
### After
- catalog_rules: 44
- course_offerings: 2806
- courses: 2204
- degree_programs: 3
- degree_requirements: 19
- promotion_runs: 4

## Skipped excluded courses
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

## Advisory rule handling
- Non-executable groups promoted to `catalog_rules` with `enforceInGraduationProgress: false`.

## Rollback notes
- Delete production docs with promotionRunId=dds-promotion-f92665dcf502 to roll back this run.
- Do not delete staging data.
- Advisory catalog rules remain non-enforced in graduation progress.

## Safety
- Staging collections were not modified.
- Production promotion used stable `productionKey` upserts.
- Roll back with `rollback-dds-production-promotion --promotion-run-id <id> --i-confirm-dangerous-production-write` (deletes only matching promotionRunId).
