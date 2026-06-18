# Prompt 04 — Write Tests

Use this prompt to add or complete the test suite for a feature.

## Goal
Ensure the feature has all five required test types and meets ≥ 80% coverage.

## Required Test Types
1. **Unit** — pure functions, validators, services in isolation. Mock the AI provider and DB.
2. **Integration** — API endpoint + MongoDB + auth middleware wired together.
3. **E2E / system** — full user flow (register → login → protected request → async AI job → result).
4. **Stress** — concurrency/load on auth and AI endpoints; verify the queue holds and rate limiting kicks in.
5. **Security** — assert:
   - Missing/invalid JWT → 401; valid token without ownership → 403.
   - Invalid request body → 400.
   - Rate limit exceeded → 429.
   - Passwords stored as bcrypt hashes, never plaintext, never returned.

## Instructions
1. For each test type, list the cases (success + failure paths).
2. Write deterministic, isolated tests; reset DB state between integration tests.
3. Make tests runnable via the documented command (Docker or local) in the README.
4. Record results in `docs/reports/TEST_REPORT_TEMPLATE.md` (copy to a dated report).

## Output
- New/updated test files.
- Coverage summary (must be ≥ 80%).
- Filled test report.

## Constraints
- Fix the implementation, not the test, unless the test itself is wrong.
- Do not skip stress or security tests — they are graded.
