# Self-Hosting BookMiro

This repo is the full app. Self-hosting = 100% of the functionality, no accounts/billing
involved. You need an LLM API key; everything else runs locally as files on disk.

## Requirements

- An LLM API key (any OpenAI SDK-compatible endpoint: OpenAI, DashScope/Qwen, etc.)
- A machine to run a Flask backend + static frontend on (your computer, a server, or any host)

No database, no object storage, no third-party graph service.

## 1. Local (source)

| Tool | Version | Check |
|---|---|---|
| Node.js | 18+ | `node -v` |
| Python | ≥3.11, ≤3.12 | `python --version` |
| uv | latest | `uv --version` |

```bash
cp .env.example .env
# set LLM_API_KEY (and LLM_BASE_URL/LLM_MODEL_NAME if not using OpenAI directly)

npm run setup:all   # installs root + frontend (npm) and backend (uv) deps
npm run dev         # backend :5001, frontend :3000
```

## 2. Docker Compose

```bash
cp .env.example .env
docker compose up -d
```

Pulls the image published by [.github/workflows/docker-image.yml](.github/workflows/docker-image.yml)
to `ghcr.io/666ghj/mirofish` (built from [Dockerfile](./Dockerfile)). [docker-compose.yml](./docker-compose.yml)
maps `3000`/`5001` and bind-mounts `./backend/uploads` on the host so data survives
restarts/upgrades. To build locally instead: `docker build -t bookmiro .`

## 3. Render Blueprint

[render.yaml](./render.yaml) deploys your own single-tenant instance to Render.

1. Fork the repo.
2. Render Dashboard -> **New > Blueprint** -> point at your fork.
3. It creates `bookmiro-backend` (Flask + gunicorn, persistent disk at `/var/data/uploads`) and
   `bookmiro-frontend` (static build).
4. Set the `sync: false` env vars when prompted: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL_NAME`.
5. `VITE_API_BASE_URL` is hardcoded in `render.yaml` to `https://bookmiro-backend.onrender.com`.
   If you rename either service, update it (see the comment in `render.yaml` for why it must be a
   public URL, not a `fromService`/private-network reference).

Backend plan is `starter` (paid): free Render web services sleep (kills in-progress extraction)
and can't mount a disk.

## 4. Any other host

- **Backend**: `uv sync --frozen` in `backend/`, then run
  `gunicorn -w 1 --threads 8 -t 600 -b 0.0.0.0:$PORT "app:create_app()"`. `-w 1` is required —
  `ExtractionManager` tracks extraction progress in memory, not shared across workers/processes.
  Point `UPLOAD_FOLDER` at a persistent path.
- **Frontend**: `npm run build` in `frontend/` produces `dist/`; serve with SPA fallback (unknown
  routes -> `index.html`) and set `VITE_API_BASE_URL` (build-time) to the backend's public URL.

## Environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `LLM_API_KEY` | Yes | - | Any OpenAI SDK-compatible provider |
| `LLM_BASE_URL` | No | `https://api.openai.com/v1` | Set for non-OpenAI providers |
| `LLM_MODEL_NAME` | No | `gpt-4o-mini` | Called once per chapter during extraction |
| `OPENROUTER_API_KEY` | No | - | Optional fallback key; failed primary extraction calls retry through OpenRouter DeepSeek V3.2 |
| `SECRET_KEY` | No | `bookmiro-secret-key` | Set a real value once not running purely on localhost |
| `FLASK_DEBUG` | No | `True` | Set `false` for any non-local deployment |
| `FLASK_HOST` / `FLASK_PORT` | No | `0.0.0.0` / `5001` | Only used by `python run.py`; ignored under gunicorn (binds `$PORT` directly) |
| `UPLOAD_FOLDER` | No | `backend/uploads` | Point at a persistent volume/disk in production |
| `VITE_API_BASE_URL` (frontend, build-time) | No | `http://localhost:5001` | Full backend URL with scheme, once not both on localhost |

## Data

Everything is under `UPLOAD_FOLDER/projects/<project_id>/`, no database:

- `project.json` — book metadata (name, language, episodes, extraction progress)
- `episodes.json` — chapter text with character offsets
- `graph.json` — extracted nodes/edges (`first_episode` + source quotes)
- `extracted_text.txt`, `files/` — original upload + extracted text

Read/seen-tracking is client-side only, in browser `localStorage` per book.

Backup = copy `UPLOAD_FOLDER`. Multiple books = multiple project directories, no limit.

## Code map (for anyone doing the repo split in STRATEGY.md)

Today, everything in this repo is self-host app code. There is no hosting-only code yet.

**App (needed for self-host, and reused as-is by any future hosted version):**
- `frontend/src/{views,components,composables,api,router,store,i18n}` — Vue app
- `backend/app/{api,services,models,utils}` — Flask backend, LLM extraction, file-based persistence
- `locales/` — i18n strings
- `render.yaml`, `docker-compose.yml`, `Dockerfile`, `.env.example` — deployment configs, all single-tenant

**Not part of the running app (skip these when reasoning about "what does self-host need"):**
- `tools/selfheal/` — local ops CLI for reading Render logs and opening fix PRs; not shipped to or used by end users
- `.github/workflows/` — CI (Docker image publishing); not needed to self-host from source or a pre-built image
- `STRATEGY.md`, `SELF_HOSTING*.md` — docs, not code

**Hosting-only (per STRATEGY.md, not yet implemented anywhere in this repo):** accounts/auth,
Stripe billing, Postgres catalog + object storage, rights-acknowledgment/DMCA takedown, admin
panel. When built, per STRATEGY.md section 1, this goes in a separate private `bookmiro-cloud`
repo that depends on this one — not mixed into `backend/app/` or `frontend/src/` above.
