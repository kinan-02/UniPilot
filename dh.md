# Catalog promotion & curriculum verification — status (2026-06-27)

Scratch notes folded into project docs (`README.md`, `docs/PROJECT_CONTEXT.md`, `services/data-engineering/README.md`).

## Done

| Item | Status |
|------|--------|
| Export pipeline (Hebrew semesters, electiveSource matrices, canonical aliases) | ✅ |
| 17-faculty production promotion (local Mongo) | ✅ |
| `scripts/promote_and_verify_faculty.sh` | ✅ |
| `scripts/verify_promoted_faculty_curriculum.py` — **17/17** | ✅ |
| Civil E2E + integration smoke (`civil-critical-path.spec.ts`) | ✅ |
| API alias track onboarding (`curriculumWikiSlug`) | ✅ |

## Promote one faculty

```bash
docker compose run --rm data-engineering python -m app.main import-technion-courses-staging   # once per clean volume
bash scripts/promote_and_verify_faculty.sh <faculty-id>
```

## Verify all promoted faculties

```bash
python3 scripts/verify_promoted_faculty_curriculum.py --base-url http://localhost:8000
```

## Next (product)

- Async AI pipeline (Redis queue, worker, AI service) — see `FEATURE_BACKLOG.md` P0
- Optional CI: wire `audit_primary_elective_pools.py` / `verify_wiki_export_parity.py` as gate jobs
- Submission prep: risk report, test report, team commit graph
