# UniPilot AI — Risk Assessment

> Copy this template to `docs/reports/RISK_ASSESSMENT.md` and fill it in. Keep it grounded in the actual code/architecture — avoid generic boilerplate.

**Project:** UniPilot AI — AI-powered academic decision support platform
**Date:** <YYYY-MM-DD>
**Authors:** <team members>
**Version:** <commit / tag>

## 1. Scoring Scale
- **Likelihood:** Low / Medium / High
- **Impact:** Low / Medium / High
- **Residual risk:** remaining risk after mitigation (Low / Medium / High)

## 2. Risk Register

### Security Risks
| ID | Risk | Likelihood | Impact | Mitigation (implemented/planned) | Residual |
|----|------|-----------|--------|----------------------------------|----------|
| S-1 | JWT secret leakage / weak secret | | | Secret from env, strong value, short expiry | |
| S-2 | Password compromise | | | bcrypt (cost ≥ 10), never plaintext/returned | |
| S-3 | Broken access control (cross-account) | | | Ownership checks on student endpoints | |
| S-4 | Injection / malformed input | | | Schema validation at all boundaries | |
| S-5 | Brute force / abuse | | | Rate limiting (Redis) on auth + AI | |
| S-6 | Secret exposure in repo/images | | | `.env.example` only, `.dockerignore`, startup validation | |

### Data Risks
| ID | Risk | Likelihood | Impact | Mitigation | Residual |
|----|------|-----------|--------|-----------|----------|
| D-1 | Data loss on volume removal | | | Named volume; documented backup approach | |
| D-2 | Student PII handling | | | Minimal storage, access control | |
| D-3 | Inconsistent/corrupt writes | | | Schema validation, explicit error handling | |

### AI Risks
| ID | Risk | Likelihood | Impact | Mitigation | Residual |
|----|------|-----------|--------|-----------|----------|
| A-1 | AI provider outage/timeout | | | Timeouts + bounded retries; job marked failed | |
| A-2 | Cost/abuse via AI endpoints | | | Rate limiting; async queue | |
| A-3 | Unsafe/hallucinated output | | | Validate AI output as untrusted before use | |
| A-4 | Blocking API on long calls | | | Async worker + queue, 202 + polling | |

### Availability / Operational Risks
| ID | Risk | Likelihood | Impact | Mitigation | Residual |
|----|------|-----------|--------|-----------|----------|
| O-1 | Startup ordering failures | | | Healthchecks + retry/reconnect | |
| O-2 | Dependency outage (Mongo/Redis/AI) | | | Graceful errors, retries | |
| O-3 | Queue backlog under load | | | Worker scaling, backpressure | |
| O-4 | Scaling limits | | | Stateless API, shared Redis | |

## 3. Known Limitations
- <List anything out of scope or not fully hardened.>

## 4. Top Risks Summary
1. <highest residual risk + why>
2. <next>
3. <next>

## 5. References
- Architecture: `docs/architecture/ARCHITECTURE.md`
- Rules: `.cursor/rules/unipilot-security.mdc`, `unipilot-docker.mdc`, `unipilot-ai.mdc`, `unipilot-database.mdc`
