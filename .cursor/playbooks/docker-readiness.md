# Playbook — Docker Readiness

## When to Use
After any change to Docker config or service topology, and as a hard gate before submission. The app MUST run first-try with Docker.

## Owner
DevOps Engineer.

## Workflow
1. Confirm `.env.example` contains every required variable.
2. Confirm one documented command starts everything (`docker compose up --build`).
3. Clean run from scratch:
   ```bash
   docker compose down -v
   docker compose up --build
   ```
4. Verify services come up healthy with retry/reconnect (no crash loop on ordering).
5. Verify exposure and persistence (checks below).
6. Record results using prompt `06-docker-check.md`.

## Required Checks
- [ ] At least two backend containers (`api` + `worker`, plus `ai`).
- [ ] ONLY `api` publishes a host port.
- [ ] Mongo, Redis, worker, ai have NO host port mappings.
- [ ] `depends_on` + healthchecks; app retries dependencies.
- [ ] MongoDB named volume; data survives `docker compose restart`.
- [ ] App boots from copied `.env.example` defaults (no manual steps).
- [ ] `.dockerignore` present; no secrets in images; pinned base versions.
- [ ] Clean run succeeds end-to-end.

## Final Deliverables
- Confirmation of a successful clean run from a fresh clone.
- Port map proving only the API is exposed.
- Docker readiness verdict: READY / NOT READY (with fixes applied).
