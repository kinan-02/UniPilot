# UniPilot Web

React + TypeScript frontend for UniPilot AI.

## Development

```bash
npm install
npm run dev
```

Dev server: [http://localhost:5173](http://localhost:5173). Proxies `/api` to the backend (`VITE_DEV_API_TARGET`, default `http://localhost:3010`).

## Tests

```bash
npm run test        # Vitest unit/component tests
npm run build       # Production build
npm run test:e2e    # Playwright smoke tests (Docker stack on port 3000)
```

## Docker

Built as the `web` service in root `docker-compose.yml`. Nginx serves the SPA and proxies `/api/` to the internal `api` container.
