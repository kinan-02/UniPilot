# DDS Production Promotion Report (Phase 12)

Promotion run: `dds-promotion-4b29ce342e75`
Started: 2026-06-27T12:43:40+00:00
Finished: 2026-06-27T12:43:42+00:00
Status: **completed**
Gate status: **pass-with-warnings**
Dry run: **False**
Confirmation flag: **True**
Production writes performed: **True**

## Policies applied
- nonExecutableRulesPolicy: `advisory-only`
- enforceNonExecutableRulesInProduction: `False`
- productionExcludedCoursePolicy: `omit-from-production-do-not-ingest`
- productionExcludedCourseNumbers: 242

## Counts planned
- degreePrograms: 5
- catalogPathOptions: 15
- catalogFaculties: 1
- hardDegreeRequirements: 21
- advisoryCatalogRules: 70
- courses: 2433
- courseOfferings: 5963
- skippedItems: 305
- skippedExcludedCourses: 235

## Counts written
- degree_programs: 5
- degree_requirements: 21
- catalog_rules: 70
- courses: 2433
- course_offerings: 5963

## Production collection counts
### Before
- catalog_faculties: 16
- catalog_path_options: 256
- catalog_rules: 749
- course_offerings: 6234
- courses: 2485
- degree_programs: 58
- degree_requirements: 306
- promotion_runs: 35
### After
- catalog_faculties: 17
- catalog_path_options: 271
- catalog_rules: 819
- course_offerings: 5963
- courses: 2433
- degree_programs: 63
- degree_requirements: 327
- promotion_runs: 36

## Skipped excluded courses
- `00440102` — production-excluded-by-catalog-signoff
- `00960226` — production-excluded-by-catalog-signoff
- `00960244` — production-excluded-by-catalog-signoff
- `00960311` — production-excluded-by-catalog-signoff
- `00960335` — production-excluded-by-catalog-signoff
- `00960351` — production-excluded-by-catalog-signoff
- `00970280` — production-excluded-by-catalog-signoff
- `00980455` — production-excluded-by-catalog-signoff
- `01040000` — production-excluded-by-catalog-signoff
- `01040012` — production-excluded-by-catalog-signoff
- `01040013` — production-excluded-by-catalog-signoff
- `01040030` — production-excluded-by-catalog-signoff
- `01040031` — production-excluded-by-catalog-signoff
- `01040032` — production-excluded-by-catalog-signoff
- `01040033` — production-excluded-by-catalog-signoff
- `01040034` — production-excluded-by-catalog-signoff
- `01040038` — production-excluded-by-catalog-signoff
- `01040064` — production-excluded-by-catalog-signoff
- `01040066` — production-excluded-by-catalog-signoff
- `01040112` — production-excluded-by-catalog-signoff
- ... and 215 more

## Advisory rule handling
- Non-executable groups promoted to `catalog_rules` with `enforceInGraduationProgress: false`.

## Rollback notes
- Delete production docs with promotionRunId=dds-promotion-4b29ce342e75 to roll back this run.
- Do not delete staging data.
- Advisory catalog rules remain non-enforced in graduation progress.

## Safety
- Staging collections were not modified.
- Production promotion used stable `productionKey` upserts.
- Roll back with `rollback-dds-production-promotion --promotion-run-id <id> --i-confirm-dangerous-production-write` (deletes only matching promotionRunId).
