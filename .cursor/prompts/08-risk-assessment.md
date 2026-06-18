# Prompt 08 — Risk Assessment

Use this prompt to produce/update the final risk assessment deliverable.

## Goal
Create an honest, code-grounded risk assessment using `docs/reports/RISK_ASSESSMENT_TEMPLATE.md`.

## Instructions
1. Copy the template to a final report (e.g. `docs/reports/RISK_ASSESSMENT.md`).
2. For each category, enumerate concrete risks tied to the actual implementation:
   - **Security** — JWT/secret handling, bcrypt usage, validation gaps, rate-limit coverage, attack surface.
   - **Data** — MongoDB persistence, volume removal data loss, backups, student PII.
   - **AI** — provider failures, timeouts, cost/abuse, unsafe/hallucinated output, async mitigation.
   - **Availability/Operational** — startup ordering, dependency outages (Mongo/Redis/AI), queue backlog, scaling.
   - **Known limitations** — out-of-scope or not-fully-hardened areas.
3. For each risk: likelihood, impact, mitigation implemented/planned, residual risk.
4. Cross-reference the security, docker, ai, and database rules.

## Output
- A finalized risk assessment that is specific (references files/architecture), not generic.

## Constraints
- Be honest about gaps; graders value accurate self-assessment.
- Keep it updated as features land; finalize before submission.
