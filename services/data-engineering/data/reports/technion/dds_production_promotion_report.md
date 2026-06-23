# DDS Production Promotion Report (Phase 12)

Promotion run: `dds-promotion-dd3c5ae786d2`
Started: 2026-06-23T13:56:00+00:00
Finished: 2026-06-23T13:56:01+00:00
Status: **completed**
Gate status: **pass-with-warnings**
Dry run: **False**
Confirmation flag: **True**
Production writes performed: **True**

## Policies applied
- nonExecutableRulesPolicy: `advisory-only`
- enforceNonExecutableRulesInProduction: `False`
- productionExcludedCoursePolicy: `omit-from-production-do-not-ingest`
- productionExcludedCourseNumbers: 59

## Counts planned
- degreePrograms: 3
- catalogPathOptions: 20
- catalogFaculties: 9
- hardDegreeRequirements: 16
- advisoryCatalogRules: 46
- courses: 165
- courseOfferings: 199
- skippedItems: 105
- skippedExcludedCourses: 59

## Counts written
- degree_programs: 3
- degree_requirements: 16
- catalog_rules: 46
- courses: 165
- course_offerings: 199

## Production collection counts
### Before
- catalog_faculties: 9
- catalog_path_options: 20
- catalog_rules: 46
- course_offerings: 199
- courses: 165
- degree_programs: 3
- degree_requirements: 16
- promotion_runs: 4
### After
- catalog_faculties: 9
- catalog_path_options: 20
- catalog_rules: 46
- course_offerings: 199
- courses: 165
- degree_programs: 3
- degree_requirements: 16
- promotion_runs: 5

## Skipped excluded courses
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
- `00960465` — production-excluded-by-catalog-signoff
- ... and 39 more

## Advisory rule handling
- Non-executable groups promoted to `catalog_rules` with `enforceInGraduationProgress: false`.

## Rollback notes
- Delete production docs with promotionRunId=dds-promotion-dd3c5ae786d2 to roll back this run.
- Do not delete staging data.
- Advisory catalog rules remain non-enforced in graduation progress.

## Safety
- Staging collections were not modified.
- Production promotion used stable `productionKey` upserts.
- Roll back with `rollback-dds-production-promotion --promotion-run-id <id> --i-confirm-dangerous-production-write` (deletes only matching promotionRunId).
