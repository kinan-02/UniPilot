# Prompt 05 — Security Review

Use this prompt before committing any feature that touches auth, user data, endpoints, or AI.

## Goal
Verify the change meets UniPilot security requirements (see `.cursor/rules/unipilot-security.mdc`).

## Checklist
### Authentication & Authorization
- [ ] JWT required on all student-specific endpoints.
- [ ] Token signature + expiry verified; 401 on invalid/expired.
- [ ] Ownership enforced — user can only access their own data; 403 otherwise.
- [ ] JWT secret loaded from env, not hardcoded.

### Passwords
- [ ] Passwords hashed with bcrypt (cost ≥ 10) before storage.
- [ ] No plaintext passwords anywhere (DB, logs, responses, errors).
- [ ] Password hashes never returned in responses.

### Input Validation
- [ ] All request bodies/params/queries validated with a schema.
- [ ] Unknown fields rejected; 400 with non-leaky message.
- [ ] AI responses treated as untrusted and validated.

### Rate Limiting
- [ ] Auth endpoints rate limited.
- [ ] AI endpoints rate limited.
- [ ] Redis-backed so limits hold across replicas; 429 on exceed.

### Secrets & Errors
- [ ] All secrets from env; `.env.example` updated; no secrets committed.
- [ ] Required secrets validated at startup.
- [ ] No stack traces/secrets leaked to clients.

### Network Exposure
- [ ] Only the API container is client-facing.
- [ ] MongoDB, Redis, worker, AI service remain internal.

## Output
- Pass/fail per item with evidence (file:line).
- Fix CRITICAL/HIGH issues before committing; rotate any exposed secret.
