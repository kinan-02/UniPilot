# Prompt 07 — README Update

Use this prompt whenever run/test behavior changes, and before submission.

## Goal
Keep `README.md` accurate so a grader can run the app and tests with no guesswork.

## Required README Sections
1. **Project overview** — UniPilot AI: AI-powered academic decision support platform (1–2 paragraphs).
2. **Architecture summary** — containers (api, worker, ai, mongo, redis) and which one is exposed. Link `docs/architecture/ARCHITECTURE.md`.
3. **Prerequisites** — Docker + Docker Compose versions.
4. **Setup** — copy env:
   ```bash
   cp .env.example .env
   ```
5. **Run (first-try Docker)**:
   ```bash
   docker compose up --build
   ```
   State the API base URL/port (only the API is exposed).
6. **Environment variables** — table of vars from `.env.example` with descriptions (no real secrets).
7. **API usage** — key endpoints with auth requirements and example requests.
8. **Running tests** — exact commands for unit, integration, E2E, stress, and security tests, plus how to see coverage.
9. **Project structure** — short tree of important folders.
10. **Reports** — link to risk assessment and test report.

## Instructions
- Verify every command actually works as written.
- Keep instructions copy-paste runnable.
- Update after each feature that changes commands or env vars.

## Output
- Updated `README.md` with all sections current.
