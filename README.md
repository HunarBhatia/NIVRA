# Nivra

Nivra helps people get images that were shared without their consent taken down. It finds the right reporting channel, drafts the legal notice, tracks every link and escalates when platforms don't respond. Your images never leave your device.

Read [PROJECT_DETAILS.txt](PROJECT_DETAILS.txt) for the full guide: every decision and the reason behind it.

## Repository layout

- `web/` is the Next.js website (Garden design).
- `backend/` is the FastAPI API: accounts, cases, links, history ([backend/README.md](backend/README.md)).
- `shared/platforms.json` is the platform directory used by both.
- `deploy/` has the deployment guide and production settings template; `docker-compose.yml` runs the full stack.
- `extension/` will hold the Chrome extension (later phase).

## Run locally

First-time backend setup is in [backend/README.md](backend/README.md). Then use two terminals.

Terminal 1, the API:

```bash
cd backend
./.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Terminal 2, the website:

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000. The website forwards `/api/*` to the backend.

## Tests

```bash
cd backend && ./.venv/Scripts/python -m pytest -q          # 168 backend tests
cd backend && ./.venv/Scripts/python scripts/test_on_postgres.py   # same suite on PostgreSQL
cd web && npm test                                          # encryption tests + shared pHash check
cd backend && ./.venv/Scripts/python scripts/smoke_test.py   # end-to-end, needs both servers running
```

## Deploying

See [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md), and the launch checklist in section 21.13 of the guide.
