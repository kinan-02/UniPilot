# Prompt 09 — Final Demo & Submission Prep

Use this prompt before the final demo/submission of UniPilot AI.

## Goal
Verify the project is complete, runnable first-try, well-tested, documented, and that all team members contributed.

## Final Checklist
### Run & Architecture
- [ ] `docker compose down -v && docker compose up --build` works from a clean clone.
- [ ] At least two backend containers; only the API is exposed.
- [ ] MongoDB, Redis, worker, AI service are internal only.
- [ ] MongoDB persistence via named volume verified.

### Features
- [ ] All backlog features for the target scope are implemented (see `FEATURE_BACKLOG.md`).
- [ ] Async AI flow demoable: enqueue → worker → status → result.
- [ ] JWT auth, bcrypt, protected endpoints, validation, rate limiting all working.

### Tests
- [ ] Unit, integration, E2E, stress, and security tests pass.
- [ ] Coverage ≥ 80%.
- [ ] `docs/reports/TEST_REPORT.md` filled with latest results.

### Documentation
- [ ] README run + test instructions verified.
- [ ] `docs/architecture/ARCHITECTURE.md` matches the built system.
- [ ] `docs/reports/RISK_ASSESSMENT.md` finalized.
- [ ] Final project report assembled (architecture + tests + risk).

### Team / Git
- [ ] GitHub contributors graph shows commits from ALL team members.
- [ ] Commit history is feature-by-feature with conventional messages.
- [ ] No secrets committed; `.env.example` present.

## Demo Script (suggested)
1. Clean Docker start.
2. Register + login (show JWT).
3. Call a protected endpoint (show 401 without token).
4. Trigger an async AI request → show job status → final result.
5. Show rate limiting (429) on repeated AI/auth calls.
6. Show tests running and coverage.

## Output
- A go/no-go summary with any remaining blockers.
