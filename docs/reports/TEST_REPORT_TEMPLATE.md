# UniPilot AI — Test Report

> Copy this template to `docs/reports/TEST_REPORT.md` (or a dated copy) and fill it after a test run.

**Project:** UniPilot AI
**Date:** <YYYY-MM-DD>
**Commit / tag:** <hash>
**Run by:** <name>
**Environment:** <Docker / local; versions>

## 1. How to Reproduce
```bash
# Commands used to run the suites (must match README)
<unit test command>
<integration test command>
<e2e test command>
<stress test command>
<security test command>
```

## 2. Summary
| Suite | Tests | Passed | Failed | Skipped | Notes |
|-------|-------|--------|--------|---------|-------|
| Unit | | | | | |
| Integration | | | | | |
| E2E / System | | | | | |
| Stress | | | | | |
| Security | | | | | |
| **Total** | | | | | |

## 3. Coverage
| Metric | Result | Target | Pass? |
|--------|--------|--------|-------|
| Lines | | ≥ 80% | |
| Branches | | ≥ 80% | |
| Functions | | ≥ 80% | |

Coverage report location: `<path/to/coverage>`

## 4. Security Test Results
| Check | Expected | Result |
|-------|----------|--------|
| Missing/invalid JWT | 401 | |
| Valid token, not owner | 403 | |
| Invalid request body | 400 | |
| Rate limit exceeded | 429 | |
| Password stored as bcrypt hash | yes | |
| Password never returned | yes | |

## 5. Stress Test Results
| Endpoint | Concurrency | Requests | p95 latency | Error rate | Notes |
|----------|-------------|----------|-------------|------------|-------|
| Auth (login) | | | | | |
| AI (enqueue) | | | | | |
| Job status | | | | | |

Observations: <queue behavior, rate-limit kick-in, failures under load>

## 6. Failures & Follow-ups
| Test | Failure | Root cause | Action / Issue |
|------|---------|-----------|----------------|
| | | | |

## 7. Conclusion
- [ ] All five test types executed.
- [ ] Coverage ≥ 80%.
- [ ] No outstanding critical failures.
- Overall status: **PASS / FAIL**
