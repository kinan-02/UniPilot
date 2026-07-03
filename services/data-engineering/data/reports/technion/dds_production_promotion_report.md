# DDS Production Promotion Report (Phase 12)

Promotion run: `dds-promotion-1c7d820335ae`
Started: 2026-07-03T09:16:38+00:00
Finished: 2026-07-03T09:18:48+00:00
Status: **completed**
Gate status: **pass-with-warnings**
Dry run: **False**
Confirmation flag: **True**
Production writes performed: **True**

## Policies applied
- nonExecutableRulesPolicy: `advisory-only`
- enforceNonExecutableRulesInProduction: `False`
- productionExcludedCoursePolicy: `omit-from-production-do-not-ingest`
- productionExcludedCourseNumbers: 51

## Counts planned
- degreePrograms: 5
- catalogPathOptions: 17
- catalogFaculties: 1
- hardDegreeRequirements: 26
- advisoryCatalogRules: 54
- courses: 2613
- courseOfferings: 6580
- skippedItems: 104
- skippedExcludedCourses: 50

## Counts written
- degree_programs: 5
- degree_requirements: 26
- catalog_rules: 54
- courses: 2613
- course_offerings: 6580

## Production collection counts
### Before
- catalog_faculties: 17
- catalog_path_options: 271
- catalog_rules: 987
- course_offerings: 6450
- courses: 2585
- degree_programs: 61
- degree_requirements: 316
- promotion_runs: 47
### After
- catalog_faculties: 17
- catalog_path_options: 271
- catalog_rules: 995
- course_offerings: 6580
- courses: 2613
- degree_programs: 61
- degree_requirements: 319
- promotion_runs: 48

## Skipped excluded courses
- `00960226` — production-excluded-by-catalog-signoff
- `00960244` — production-excluded-by-catalog-signoff
- `00960311` — production-excluded-by-catalog-signoff
- `00960351` — production-excluded-by-catalog-signoff
- `00970280` — production-excluded-by-catalog-signoff
- `00960335` — production-excluded-by-catalog-signoff
- `00980455` — production-excluded-by-catalog-signoff
- `00960251` — production-excluded-by-catalog-signoff
- `00960293` — production-excluded-by-catalog-signoff
- `00960470` — production-excluded-by-catalog-signoff
- `00970200` — production-excluded-by-catalog-signoff
- `00970211` — production-excluded-by-catalog-signoff
- `00970216` — production-excluded-by-catalog-signoff
- `00970245` — production-excluded-by-catalog-signoff
- `00970272` — production-excluded-by-catalog-signoff
- `00970329` — production-excluded-by-catalog-signoff
- `01200124` — production-excluded-by-catalog-signoff
- `02340252` — production-excluded-by-catalog-signoff
- `02360268` — production-excluded-by-catalog-signoff
- `02360278` — production-excluded-by-catalog-signoff
- ... and 30 more

## Advisory rule handling
- Non-executable groups promoted to `catalog_rules` with `enforceInGraduationProgress: false`.

## Rollback notes
- Delete production docs with promotionRunId=dds-promotion-1c7d820335ae to roll back this run.
- Do not delete staging data.
- Advisory catalog rules remain non-enforced in graduation progress.

## Safety
- Staging collections were not modified.
- Production promotion used stable `productionKey` upserts.
- Roll back with `rollback-dds-production-promotion --promotion-run-id <id> --i-confirm-dangerous-production-write` (deletes only matching promotionRunId).
