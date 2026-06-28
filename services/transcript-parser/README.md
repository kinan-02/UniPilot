# Transcript Parser Service

Internal FastAPI container that receives official Technion transcript PDFs (Hebrew or English) and returns structured course rows for the main API to review and persist.

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | none | Service health |
| `POST` | `/parse` | `X-Internal-Service-Token` (when configured) | Upload PDF (`multipart/form-data`, field `file`) |

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `TRANSCRIPT_PARSER_PORT` | `8010` | Uvicorn listen port inside container |
| `INTERNAL_SERVICE_TOKEN` | empty | Shared secret with `api` service |
| `MAX_UPLOAD_BYTES` | `5242880` (5 MiB) | Maximum PDF upload size |
| `ENVIRONMENT` | `development` | Hides OpenAPI in production |

## Local tests

```bash
cd services/transcript-parser
pip install -r requirements-dev.txt
pytest
```

## Related docs

- Integration plan: `docs/planning/TRANSCRIPT_PDF_IMPORT_PLAN.md`
- Architecture: `docs/architecture/ARCHITECTURE.md`
