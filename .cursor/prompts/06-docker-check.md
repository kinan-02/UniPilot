# Prompt 06 — Docker First-Run Check

Use this prompt before committing Docker changes and before submission.

## Goal
Guarantee the app runs on the FIRST try with Docker and respects the container/exposure rules.

## Steps
1. Confirm a committed `.env.example` exists with every required variable.
2. Confirm a single documented command starts everything (e.g. `docker compose up --build`).
3. Clean run from scratch:
   ```bash
   docker compose down -v
   docker compose up --build
   ```
4. Verify services:
   - [ ] At least two backend containers (api + worker, plus ai).
   - [ ] MongoDB and Redis start and the app connects (with retry/healthchecks).
   - [ ] Worker consumes the Redis queue.
   - [ ] AI service reachable internally only.
5. Verify exposure:
   - [ ] ONLY the API/web container publishes a host port.
   - [ ] MongoDB, Redis, worker, AI have NO host port mappings.
6. Verify persistence:
   - [ ] MongoDB uses a named volume; data survives `docker compose restart`.
7. Image hygiene:
   - [ ] `.dockerignore` present; no secrets baked into images; pinned base versions.

## Output
- Confirmation the clean run succeeded.
- Port map proving only the API is exposed.
- Any fixes applied to reach first-run success.

## Constraints
- Do not rely on manual setup steps beyond copying `.env.example` and one compose command.
