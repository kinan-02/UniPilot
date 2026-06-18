# Playbook — Security Review

## When to Use
Before committing any change that touches authentication, user data, endpoints, AI processing, secrets, or Docker exposure. Mandatory before submission.

## Owner
Security Engineer (with Backend/AI Engineer for fixes).

## Workflow
1. Identify scope: list files/areas changed.
2. Run the checklist from `.cursor/rules/unipilot-security.mdc` and prompt `05-security-review.md`.
3. For each finding, assign severity (CRITICAL/HIGH/MEDIUM/LOW) with `file:line` and a concrete fix.
4. Fix CRITICAL/HIGH before commit; rotate any exposed secret.
5. Re-run security tests to confirm fixes.

## Required Checks
- [ ] **Auth:** JWT required on student endpoints; signature + expiry verified (401); secret from env.
- [ ] **Authorization:** ownership enforced (403 on others' data).
- [ ] **Passwords:** bcrypt (cost ≥ 10); never plaintext; hashes never returned.
- [ ] **Validation:** all inputs schema-validated; unknown fields rejected (400); AI output validated.
- [ ] **Rate limiting:** auth + AI endpoints, Redis-backed (429).
- [ ] **Secrets:** from env; `.env.example` updated; none committed; validated at startup.
- [ ] **Exposure:** only `api` client-facing; Mongo/Redis/worker/ai internal.
- [ ] **Errors:** no stack traces/secrets leaked.
- [ ] **Security tests:** 401/403/400/429 + bcrypt assertions pass.

## Final Deliverables
- Security review report (findings + severities + fixes).
- Verdict: PASS or BLOCK.
- Passing security test suite.
- Any secrets rotated and `.env.example` updated.
