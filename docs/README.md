# UniPilot Documentation

Last updated: 2026-06-20

This folder contains the published documentation for the UniPilot AI backend. Start with the root [README.md](../README.md) for setup, tests, and Docker.

## Quick links

| Document | Purpose |
|----------|---------|
| [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) | **Source of truth** — vision, architecture, phase status, what is implemented |
| [API_SPEC.md](API_SPEC.md) | HTTP API contract (routes, validation, errors) |
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | MongoDB collections, indexes, ownership rules |
| [DOMAIN_MODEL.md](DOMAIN_MODEL.md) | Academic domain entities and relationships |
| [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | Container topology, request flows, cross-cutting concerns |
| [ARCHITECTURE_FREEZE.md](ARCHITECTURE_FREEZE.md) | Frozen MVP decisions (change only via ADR) |
| [DATA_INGESTION_ARCHITECTURE.md](DATA_INGESTION_ARCHITECTURE.md) | Technion catalog ingestion design and pipeline stages |
| [data-sources/TECHNION_DDS_SOURCE_MAPPING.md](data-sources/TECHNION_DDS_SOURCE_MAPPING.md) | DDS PDF/JSON → normalized schema mapping |

## Planning & history

| Document | Purpose |
|----------|---------|
| [planning/IMPLEMENTATION_PHASES.md](planning/IMPLEMENTATION_PHASES.md) | Original phased delivery roadmap |
| [planning/FEATURE_BACKLOG.md](planning/FEATURE_BACKLOG.md) | Feature priorities and backlog |
| [planning/PYTHON_BACKEND_MIGRATION_PLAN.md](planning/PYTHON_BACKEND_MIGRATION_PLAN.md) | **Archived** — Node → FastAPI migration (complete) |
| [planning/REAL_DATA_ALIGNMENT_PLAN.md](planning/REAL_DATA_ALIGNMENT_PLAN.md) | Real Technion DDS data alignment |

## Decisions & submission templates

| Document | Purpose |
|----------|---------|
| [decisions/0001-system-architecture.md](decisions/0001-system-architecture.md) | ADR: multi-container Docker architecture |
| [decisions/ADR_TEMPLATE.md](decisions/ADR_TEMPLATE.md) | Template for new ADRs |
| [reports/RISK_ASSESSMENT_TEMPLATE.md](reports/RISK_ASSESSMENT_TEMPLATE.md) | Risk report template |
| [reports/TEST_REPORT_TEMPLATE.md](reports/TEST_REPORT_TEMPLATE.md) | Test report template |

## Service-specific docs

| Document | Purpose |
|----------|---------|
| [../services/data-engineering/README.md](../services/data-engineering/README.md) | Staging import, quality gates, production promotion CLI |

## Current stack (summary)

- **API:** FastAPI (`services/api`) — sole client-facing container
- **Database:** MongoDB (`MONGO_DB`, default `unipilot_python`) with promoted Technion DDS catalog
- **Internal:** `worker`, `ai`, `data-engineering`, `redis` — not host-exposed
- **Tests:** pytest (unit, integration, security, stress) + `services/api/scripts/verify_and_benchmark.py` for Docker E2E

When docs conflict, follow: assignment requirements → ADRs → `PROJECT_CONTEXT.md` → update this index if paths change.
