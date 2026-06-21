# Production Deployment Runbook

This document describes how to deploy UniPilot AI beyond local Docker Compose development.

## Architecture

| Service | Exposure | Notes |
|---------|----------|-------|
| `web` | Public (HTTPS) | React SPA; reverse-proxy `/api` to API |
| `api` | Internal or public via proxy | FastAPI; only service that needs DB credentials |
| `mongo`, `redis`, `worker`, `ai`, `data-engineering` | **Internal only** | No host port mappings |

## Pre-deploy checklist

1. Copy `.env.example` to `.env` on the deployment host.
2. Set `ENVIRONMENT=production`.
3. Set a unique `JWT_SECRET` (≥ 32 characters; not the dev placeholder).
4. Set strong `MONGO_ROOT_PASSWORD` and restrict MongoDB to the internal network.
5. Tune rate limits for production traffic:
   - `AUTH_RATE_LIMIT_MAX=5` (login/register)
   - `AI_RATE_LIMIT_MAX=5` (`POST /academic-risks/analyze`)
6. Keep `AUTO_SEED_CATALOG=false`; promote catalog via `data-engineering` CLI.
7. Confirm CI is green on the release commit (`.github/workflows/ci.yml`).

## TLS / HTTPS

Terminate TLS at a reverse proxy (nginx, Caddy, cloud load balancer) in front of `web`:

```nginx
server {
    listen 443 ssl http2;
    server_name unipilot.example.com;

    ssl_certificate     /etc/ssl/certs/unipilot.crt;
    ssl_certificate_key /etc/ssl/private/unipilot.key;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Do **not** expose MongoDB or Redis ports to the public internet.

## Startup verification

```bash
docker compose up --build -d
docker compose ps
curl -fsS http://localhost:8000/health
docker compose exec -T api printenv ENVIRONMENT JWT_SECRET AUTH_RATE_LIMIT_MAX AI_RATE_LIMIT_MAX
```

Expected in production:

- `ENVIRONMENT=production`
- `JWT_SECRET` is not `unipilot_dev_jwt_secret_change_in_production` or `replace_me_with_secure_jwt_secret`
- Rate limit vars match your policy

## Catalog data

After a fresh Mongo volume:

```bash
docker compose run --rm data-engineering python -m app.main export-vault-catalog --faculty dds
docker compose run --rm data-engineering python -m app.main import-dds-catalog-staging
docker compose run --rm data-engineering python -m app.main import-dds-courses-staging
docker compose run --rm data-engineering python -m app.main promote-dds-to-production \
  --i-confirm-dangerous-production-write --allow-warnings
docker compose run --rm data-engineering python -m app.main verify-vault-production-parity --faculty dds
```

## Rollback

1. Redeploy the previous Docker image tag / git commit.
2. If a bad catalog promotion occurred, restore Mongo from backup (`mongo_data` volume snapshot).
3. Flush rate-limit keys if needed: `docker compose exec redis redis-cli --scan --pattern 'rl:*'`.

## Monitoring

- Health: `GET /health` (API), web container file check.
- Logs: `docker compose logs -f api worker ai`
- Do not log JWT tokens, passwords, or full request bodies containing credentials.

## Incident contacts

Document your on-call owner and escalation path before public launch.
