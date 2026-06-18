# ADR-NNNN: <Short Title>

> Copy this file to `docs/decisions/NNNN-<kebab-title>.md`, increment the number, and fill it in.

- **Status:** Proposed | Accepted | Superseded by ADR-XXXX | Deprecated
- **Date:** <YYYY-MM-DD>
- **Deciders:** <team members>
- **Related:** <ADRs, rules, docs>

## Context
<The problem, constraints, and forces at play. Reference the UniPilot mandatory requirements that apply: Docker first-run, backend-first, MongoDB persistence, Redis async worker, internal AI service, JWT, bcrypt, protected endpoints, rate limiting, testing, docs.>

## Decision
<The choice made, stated clearly and actively: "We will ...">

## Alternatives Considered
- **Option A** — <pros / cons>
- **Option B** — <pros / cons>

## Consequences
- **Positive:** <benefits>
- **Negative / trade-offs:** <costs, risks>
- **Follow-ups:** <required work, tests, doc updates>

## Compliance Check
- [ ] Backend-first
- [ ] Docker first-run reliability preserved
- [ ] Only API exposed; internal services stay internal
- [ ] MongoDB remains source of truth
- [ ] Async AI via Redis + worker (if AI involved)
- [ ] Security (JWT, bcrypt, validation, rate limiting) unaffected or improved
- [ ] Test + documentation impact captured
