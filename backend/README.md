# Nivra backend

FastAPI + SQLAlchemy 2 + Alembic. SQLite in development, PostgreSQL in production (decision D15). The reasons behind each choice are in `../PROJECT_DETAILS.txt` (sections 13 and 14).

## Setup (Windows, Git Bash)

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python -m pip install -r requirements-dev.txt
cp .env.example .env            # then fill in NIVRA_DATA_KEY if you want optional emails
./.venv/Scripts/alembic upgrade head
```

## Run

```bash
./.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Then start the website (`cd ../web && npm run dev`) and open http://localhost:3000. The website proxies `/api/*` to this server, so the browser only ever talks to `localhost:3000`.

Interactive API docs (development only): http://localhost:8000/api/docs

## Test

```bash
./.venv/Scripts/python -m pytest -q
```

## Database changes

Edit `app/models.py`, then:

```bash
./.venv/Scripts/alembic revision --autogenerate -m "describe the change"
./.venv/Scripts/alembic upgrade head
```

## API (phase 2)

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | Liveness check |
| POST | `/api/auth/register` | Create an anonymous account from a passphrase; returns the Nivra ID and logs in |
| POST | `/api/auth/login` | Log in with Nivra ID + passphrase (rate-limited) |
| POST | `/api/auth/logout` | End the session on the server |
| GET | `/api/auth/me` | The logged-in account |
| PATCH | `/api/account` | Add or remove the optional email (stored encrypted) |
| DELETE | `/api/account` | Delete the account and all its data (needs the passphrase) |
| GET / POST | `/api/cases` | List or create cases |
| GET / PATCH / DELETE | `/api/cases/{id}` | Read, rename the notice signature, or delete a case |
| POST | `/api/cases/{id}/links` | Add links (validated, duplicates skipped) |
| POST | `/api/links/{id}/status` | Change a link's status (server enforces allowed moves) |
| POST | `/api/links/{id}/simulate-deadline` | Prototype only; disabled in production |

## API (phase 3: protected images)

Only fingerprints are accepted; no endpoint takes image data (decision D13).

| Method | Path | What it does |
|---|---|---|
| GET / POST | `/api/images` | List protected images, or register one from browser-computed fingerprints (consent required) |
| PATCH | `/api/images/{id}` | Rename, or pause/resume monitoring |
| PUT | `/api/images/{id}/embedding` | Add or replace the AI similarity fingerprint |
| DELETE | `/api/images/{id}` | Revoke protection and delete its fingerprints |
| POST | `/api/images/check` | Compare a copy's fingerprints with your own protected images |

The pHash must match the website's version. After changing either, run both checks:

```bash
./.venv/Scripts/python -m pytest tests/test_fingerprint.py -q
cd ../web && node --experimental-strip-types scripts/check-phash.ts
```

Note: `--reload` may not notice file changes inside a OneDrive folder; restart the server after editing code.

## API (phase 4: discovery)

| Method | Path | What it does |
|---|---|---|
| POST / GET | `/api/discovery/jobs` | Queue a check of a page or image link / list recent checks |
| GET | `/api/discovery/jobs/{id}` | Progress and result of one check |
| GET | `/api/matches` | Matches found (optional `?status_filter=pending`, `confirmed` or `rejected`) |
| POST | `/api/matches/{id}/review` | The user's decision: `confirmed`, `rejected` or back to `pending` |
| POST | `/api/matches/{id}/add-to-case` | Add a confirmed match's page to an existing or new case |

Jobs run in a background thread of the API in development. In production, run the worker separately:

```bash
./.venv/Scripts/python -m app.discovery.worker
```

To test discovery against a page on your own machine, start the API with `NIVRA_DISCOVERY_ALLOW_PRIVATE_HOSTS=true` and use `127.0.0.1` links. Never enable it in production (the server refuses to start).

## API (phase 5: AI agents)

| Method | Path | What it does |
|---|---|---|
| GET | `/api/agents/status` | Whether an LLM is configured, and which |
| POST | `/api/agents/complaint` | Draft a notice for a link, then wait for approval |
| POST | `/api/agents/verification` | Explain a match (no approval needed; never decides) |
| POST | `/api/agents/follow-up` | Check deadlines; draft follow-ups, then wait for approval |
| POST | `/api/agents/discovery` | Plan page re-checks, then wait for approval |
| GET | `/api/agents/runs`, `/api/agents/runs/{id}` | Runs, optionally filtered by `agent` and `subject_id` |
| POST | `/api/agents/runs/{id}/decision` | `approve` (optionally `approved_ids`) or `reject` |

AI drafting uses Google Gemini (`gemini-3.1-flash-lite` by default). Put `GEMINI_API_KEY=...` in `backend/.env` and restart the API. Without a key the agents use Nivra's templates and rules; set `NIVRA_LLM_PROVIDER=none` to never call a model. The model only ever receives the case type, platform and legal grounds, never links, names or images. Tests never call the real model, even when a key is set.

## API (phase 6: complaints, evidence, overview)

| Method | Path | What it does |
|---|---|---|
| GET | `/api/cases/{id}/complaints` | Complaints in a case (with filled-in text and history) |
| POST | `/api/links/{id}/complaints` | Use a notice for a link (starts at "Approved by you") |
| POST | `/api/complaints/{id}/status` | Record the next step (submitted, confirmed, replied, resolved, rejected) |
| DELETE | `/api/complaints/{id}` | Discard a draft that hasn't been sent |
| GET | `/api/cases/{id}/timeline` | Everything that happened in a case, newest first |
| GET | `/api/overview` | Dashboard counts and cases |
| GET | `/api/platforms`, `/api/platforms/{id}` | The shared platform directory |
| GET / POST | `/api/evidence/locker` | Locker salt and key check (set up once) |
| GET / POST | `/api/cases/{id}/evidence` | List or add encrypted evidence |
| GET | `/api/evidence/{id}/blob` | Download an encrypted file |
| DELETE | `/api/evidence/{id}` | Delete an item and its file |

Evidence arrives already encrypted by the browser; the server can't read it. Files are stored in `NIVRA_EVIDENCE_DIR` (default `./evidence-store`, not web-served).

The platform directory lives in `../shared/platforms.json`. The website copies it automatically before `npm run dev` / `npm run build`; a backend test fails if the copies differ.

## API (phase 7: monitoring and notifications)

| Method | Path | What it does |
|---|---|---|
| GET / POST | `/api/watch` | List watched pages / start watching a page or case link |
| PATCH / DELETE | `/api/watch/{id}` | Pause, resume, change interval (12, 24, 72 or 168 hours) / stop watching |
| GET | `/api/notifications` | Latest updates |
| GET | `/api/notifications/unread-count` | Number of unread updates |
| POST | `/api/notifications/{id}/read`, `/api/notifications/read-all` | Mark as read |
| GET / PATCH | `/api/settings/notifications` | Monitoring switch, update kinds, email mode |

The worker runs a scheduler tick every `NIVRA_SCHEDULER_INTERVAL_SECONDS` (default 60): it queues due re-checks of watched pages, creates deadline reminders and sends daily digests. Emails are discreet (no details) and are only logged in development (`NIVRA_EMAIL_BACKEND=console`); use `smtp` with the `NIVRA_SMTP_*` settings in production. Optional email needs `NIVRA_DATA_KEY`.

Every case and link query is scoped to the logged-in account, so another account's IDs return 404.
