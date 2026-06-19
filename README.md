# UniPilot AI — Phase 2 Auth Backend Foundation

UniPilot AI is an AI-powered academic decision support platform.  
This repository currently implements backend foundation plus **Phase 2 authentication backend**:

- Dockerized backend services
- Health endpoint in the API
- Register/login endpoints
- bcrypt password hashing
- JWT access tokens
- Protected auth route middleware
- Input validation and auth rate limiting
- Unit, integration, and auth security tests

Student profiles and business recommendation logic are intentionally not implemented yet.

## Services

- `api` (Node.js/Express) — **only exposed service**
- `worker` (Node.js/Express health stub) — internal only
- `ai` (Node.js/Express health/infer stub) — internal only
- `mongo` (MongoDB) — internal only, persisted via volume
- `redis` (Redis) — internal only, queue/rate-limit foundation

## Prerequisites

- Docker + Docker Compose
- Node.js 20+ (only needed for local test execution)

## Setup

```bash
cp .env.example .env
```

Security note: `.env.example` contains local development defaults. Replace secret values (especially `JWT_SECRET` and `MONGO_ROOT_PASSWORD`) before any non-local deployment.

## Run (First-Try Docker)

```bash
docker compose up --build
```

API health URL:

- `http://localhost:<API_PORT>/health`

Example with defaults from `.env.example`:

- [http://localhost:3000/health](http://localhost:3000/health)

## Stop and Clean

```bash
docker compose down -v
```

## Run Tests

API tests (health + auth unit/integration/security):

```bash
cd services/api
npm install
npm test
```

Run only auth-focused suites:

```bash
cd services/api
npm run test:unit
npm run test:integration
npm run test:security
```

## Auth API (Phase 2)

### Register

- `POST /auth/register`
- Request body:

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!"
}
```

### Login

- `POST /auth/login`
- Request body:

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!"
}
```

### Get Current User (Protected)

- `GET /auth/me`
- Header: `Authorization: Bearer <accessToken>`

## Notes

- Only the API service exposes a host port (`3000` by default).
- MongoDB data is persisted in the `mongo_data` named volume.
- Worker and AI services remain internal skeletons prepared for async queue flow in later phases.
- Passwords are stored as bcrypt hashes; plaintext passwords are never stored.
