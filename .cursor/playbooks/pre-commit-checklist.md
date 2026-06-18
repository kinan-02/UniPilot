# Playbook — Pre-Commit Checklist

## When to Use
Before every commit/push to the UniPilot AI repository.

## Owner
The committing engineer (each team member commits under their own GitHub identity).

## Workflow
1. Review the diff: scope is one feature/concern; no stray changes.
2. Run the relevant gates: testing review, security review, Docker readiness (for infra changes).
3. Confirm docs are updated if behavior/commands changed.
4. Write a conventional commit message and push.

## Required Checks
### Code & Architecture
- [ ] Backend-first; matches current phase/backlog item.
- [ ] Persistent data in MongoDB; long AI work async via Redis + worker.
- [ ] Internal services not exposed; only `api` is client-facing.

### Security
- [ ] JWT on student endpoints + ownership checks.
- [ ] bcrypt passwords; no plaintext; hashes never returned.
- [ ] All inputs validated; rate limiting on auth/AI endpoints.
- [ ] No secrets committed; `.env.example` updated; secrets from env.

### Tests
- [ ] Relevant unit/integration/E2E/stress/security tests added and passing.
- [ ] Coverage ≥ 80%.

### Docker & Docs
- [ ] `docker compose up --build` still works (if infra touched).
- [ ] README run/test instructions accurate.

### Git
- [ ] Conventional commit message (`feat|fix|refactor|docs|test|chore|perf|ci`).
- [ ] Feature-by-feature commit (no giant mixed commit).
- [ ] Committed under the correct team member's identity.

## Final Deliverables
- A clean, conventional commit pushed to GitHub.
- All gates green (or change blocked until fixed).
- Contributor history reflects all team members over time.
