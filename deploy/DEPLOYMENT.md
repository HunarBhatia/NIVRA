# Deploying Nivra

Nivra runs as four services: **PostgreSQL**, the **API** (FastAPI), one **worker** (page checks and the scheduler), and the **website** (Next.js). They're defined in [`docker-compose.yml`](../docker-compose.yml). Section 21 of [`PROJECT_DETAILS.txt`](../PROJECT_DETAILS.txt) explains each choice.

> These Docker files were written and reviewed, but not built on the development machine (Docker wasn't installed). The parts they depend on were verified separately: the production website build and its standalone server, the full test suite and migrations on PostgreSQL, and an end-to-end smoke test. Build and smoke-test once on the target server before launch.

## 1. Before you start

- A Linux server or VM with Docker and Docker Compose.
- A domain name, and a TLS-terminating reverse proxy (Caddy, nginx, or a cloud load balancer). Production cookies require HTTPS.
- Read the **launch checklist** in `PROJECT_DETAILS.txt` section 21.13. Some items are legal and human checks, not code.

## 2. Configure

```bash
cp deploy/.env.production.example deploy/.env.production
```

Fill in every value. The API **refuses to start** in production if a safety setting is wrong: cookies not Secure, prototype tools on, SQLite, private-host fetching allowed, no `NIVRA_DATA_KEY`, non-https origins, or relative data paths.

Generate `NIVRA_DATA_KEY` once and store it safely. Losing it makes stored emails unreadable:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 3. Start

```bash
docker compose up -d --build
```

The `migrate` service applies database migrations before the API and worker start. Run **exactly one worker**: it also runs the scheduler (re-checks, reminders, digests, data retention).

Point your reverse proxy at `127.0.0.1:3000`. Only the website is exposed; it forwards `/api/*` to the API internally.

## 4. Verify

```bash
docker compose exec api python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/api/ready').read())"
```

Then, from any machine with the repository:

```bash
cd backend && .venv/Scripts/python scripts/smoke_test.py https://your-domain.example
```

All checks must pass. The smoke test creates and then deletes a throwaway account.

## 5. Operate

- **Health checks:** `/api/health` (process up) and `/api/ready` (database, evidence storage and platform directory OK). Point your uptime monitor at `/api/ready`.
- **Logs:** JSON lines on stdout (`NIVRA_LOG_FORMAT=json`), each with a `request_id`. Logs contain methods, routes, status codes and error types only, never request bodies, links, emails or passphrases.
- **Backups:** back up the `pgdata` and `nivradata` volumes. `nivradata` holds the encrypted evidence files and agent checkpoints. Evidence is encrypted with users' passphrases, so a backup is useless to anyone without them, but keep backups private anyway.
- **Data retention:** old audit events, read updates, finished page checks and agent runs are purged daily (`NIVRA_RETENTION_*`). Users' cases, evidence and protected images stay until they delete them.
- **Updating:** `git pull && docker compose up -d --build` (migrations run automatically). Re-run the smoke test afterwards.
- **Dependencies:** run `pip-audit -r backend/requirements.txt` and `npm audit --omit=dev` in `web/` regularly, and before each release.

## 6. Testing on PostgreSQL without Docker

```bash
cd backend
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python scripts/test_on_postgres.py
```

This starts a temporary PostgreSQL, applies every migration, checks the schema matches the code, and runs the full test suite against it.
