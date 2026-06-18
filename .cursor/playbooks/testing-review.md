# Playbook — Testing Review

## When to Use
After implementing a feature, before security review and commit, and as a gate before submission.

## Owner
QA / Test Engineer (with Backend/AI Engineer for fixes).

## Workflow
1. Confirm TDD was followed (tests written before implementation).
2. Ensure all five test types exist for the feature (prompt `04-write-tests.md`):
   - Unit, Integration, E2E/system, Stress, Security.
3. Run the full suite via the documented command (Docker or local, matching README).
4. Measure coverage; confirm ≥ 80% (lines/branches/functions).
5. Triage failures: fix implementation (not tests) unless a test is wrong.
6. Fill `docs/reports/TEST_REPORT_TEMPLATE.md` → dated `TEST_REPORT.md`.

## Required Checks
- [ ] **Unit:** isolated; AI provider + DB mocked; success + failure paths.
- [ ] **Integration:** API + MongoDB + auth middleware; DB reset between tests.
- [ ] **E2E:** register → login → protected request → async AI job → result.
- [ ] **Stress:** concurrency on auth + AI; queue holds; rate limit triggers.
- [ ] **Security:** 401/403/400/429 + bcrypt-only passwords asserted.
- [ ] Coverage ≥ 80%.
- [ ] Tests deterministic and isolated.
- [ ] Test commands match the README.

## Final Deliverables
- Green test suite across all five types.
- Coverage report ≥ 80%.
- Filled test report in `docs/reports/`.
- List of any quarantined/flaky tests with follow-up issues.
