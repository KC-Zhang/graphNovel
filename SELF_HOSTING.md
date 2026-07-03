# Self-Hosting BookMiro

This repository is the **complete, self-hostable application** — every feature (reading-synced
graph reveal, language-locked extraction, jump-to-source, edge reel, read-tracking, reverse
linking) works when you run it yourself. There is no "trial" or "limited" mode: self-hosting and
the future hosted product ([STRATEGY.md](./STRATEGY.md)) run the exact same application code.
The only things a hosted version adds on top are multi-tenant extras (accounts, billing, a shared
public library, takedown handling) — see [What self-hosting does *not* include](#what-self-hosting-does-not-include)
below.

All you provide is an LLM API key. Your books, extracted graphs, and reading progress stay on
your own machine/server — nothing is sent anywhere except the LLM calls needed to extract each
chapter's graph.

## What you need

| Requirement | Why |
|---|---|
| An LLM API key (any OpenAI SDK-compatible endpoint) | Extraction calls the LLM once per chapter. Any provider works — OpenAI, Alibaba Bailian/DashScope (Qwen), etc. |
| One of: your own machine, a server, or a free/cheap cloud host | To run the Flask backend + static frontend |

Nothing else is required — no database, no object storage, no third-party graph service. Data is
stored as plain files on disk (see [Data & storage](#data--storage)).

## Choose a deployment method

| Method | Best for | Effort |
|---|---|---|
| [Local (source)](#1-local-source---for-development-or-personal-use-on-your-own-machine) | Trying it out, personal use on your own computer | Low |
| [Docker Compose](#2-docker-compose---personal-use-on-a-nas-home-server-or-any-machine-with-docker) | Personal use on a home server/NAS, or anywhere with Docker | Low |
| [Render Blueprint](#3-render-blueprint---your-own-instance-in-the-cloud) | A personal instance reachable from anywhere, minimal ops | Low-Medium |
| Any other host (Fly.io, Railway, a VPS, etc.) | Same idea as Render — see [Deploying elsewhere](#deploying-elsewhere) | Medium |

All four run the identical codebase; pick whichever fits where you want it to live.

### 1. Local (source) - for development or personal use on your own machine

Prerequisites:

| Tool | Version | Check |
|---|---|---|
| Node.js | 18+ | `node -v` |
| Python | ≥3.11, ≤3.12 | `python --version` |
| uv | latest | `uv --version` |

```bash
cp .env.example .env
# edit .env, set LLM_API_KEY (and LLM_BASE_URL/LLM_MODEL_NAME if not using OpenAI directly)

npm run setup:all   # installs root + frontend (npm) and backend (uv) deps
npm run dev         # starts backend (:5001) and frontend (:3000)
```

Open `http://localhost:3000`. See [README.md](./README.md) for the full walkthrough.

### 2. Docker Compose - personal use on a NAS, home server, or any machine with Docker

Uses the image published by this repo's [GitHub Action](.github/workflows/docker-image.yml) to
`ghcr.io/666ghj/mirofish` (built from [Dockerfile](./Dockerfile), which runs both frontend and
backend together via `npm run dev`).

```bash
cp .env.example .env
# edit .env, set LLM_API_KEY

docker compose up -d
```

This uses [docker-compose.yml](./docker-compose.yml): reads `.env` from the project root, maps
`3000` (frontend) / `5001` (backend), and persists uploaded books to `./backend/uploads` on the
host so they survive container restarts/upgrades.

To build the image yourself instead of pulling it: `docker build -t bookmiro .`

### 3. Render Blueprint - your own instance in the cloud

[render.yaml](./render.yaml) deploys **your own single-tenant instance** to
[Render](https://render.com) — same app, just reachable from anywhere instead of only
`localhost`. This is not the hosted multi-tenant product; it's a personal deployment.

1. Fork this repo (so Render can auto-deploy on push).
2. In the Render Dashboard: **New > Blueprint**, point it at your fork.
3. Render provisions two services from `render.yaml`:
   - `bookmiro-backend` - Flask + gunicorn, with a small persistent disk mounted at
     `/var/data/uploads` for your book library (survives redeploys).
   - `bookmiro-frontend` - the static Vue build.
4. When prompted, set the secret env vars (`sync: false` in `render.yaml`): `LLM_API_KEY`,
   `LLM_BASE_URL`, `LLM_MODEL_NAME`.
5. Deploy. The frontend's `VITE_API_BASE_URL` is hardcoded in `render.yaml` to the backend's
   public `https://bookmiro-backend.onrender.com` URL — **if you rename either service**, update
   that value (and see the comment above it in `render.yaml` for why it must be a public URL, not
   a `fromService`/private-network reference).

Cost note: the backend plan is set to `starter` (paid) because free Render web services sleep
after inactivity, which would kill any in-progress graph extraction, and free instances can't
mount a persistent disk. Downgrade at your own risk if you don't need either guarantee.

### Deploying elsewhere

The app is a plain Flask backend + static Vue frontend, so any host that can run a Python web
service (with a persistent disk or volume) and serve a static site works the same way:

- **Backend**: install with `uv sync --frozen` (in `backend/`), run with
  `gunicorn -w 1 --threads 8 -t 600 -b 0.0.0.0:$PORT "app:create_app()"`. **`-w 1` (a single
  worker) is required** — `ExtractionManager` tracks in-progress extraction in memory, so multiple
  workers/processes would not share extraction state. Point `UPLOAD_FOLDER` at a persistent path.
- **Frontend**: `npm run build` (in `frontend/`) produces a static `dist/` folder; serve it with
  SPA fallback (unknown routes -> `index.html`, for Vue Router history mode) and set
  `VITE_API_BASE_URL` (at build time) to the backend's public URL.

## Environment variables reference

| Variable | Required | Default | Notes |
|---|---|---|---|
| `LLM_API_KEY` | Yes | - | Any OpenAI SDK-compatible provider |
| `LLM_BASE_URL` | No | `https://api.openai.com/v1` | Set for non-OpenAI providers (DashScope, etc.) |
| `LLM_MODEL_NAME` | No | `gpt-4o-mini` | Extraction runs once per chapter - prefer a cost-efficient model |
| `SECRET_KEY` | Recommended for anything beyond local use | `bookmiro-secret-key` | Set your own random value once you're not running purely on localhost |
| `FLASK_DEBUG` | No | `True` | Set to `false` for any non-local deployment |
| `FLASK_HOST` / `FLASK_PORT` | No | `0.0.0.0` / `5001` | Only used by `python run.py`; ignored when running via gunicorn (which binds `$PORT` directly, e.g. on Render) |
| `UPLOAD_FOLDER` | No | `backend/uploads` | Point at a persistent volume/disk in any non-local deployment |
| `VITE_API_BASE_URL` (frontend, build-time) | No | `http://localhost:5001` | Must be the backend's full public URL (with scheme) once frontend and backend aren't both on localhost |

## Data & storage

Everything lives under `UPLOAD_FOLDER` (default `backend/uploads/projects/<project_id>/`), as
plain files — no database required:

- `project.json` - book metadata (name, language, episode list, extraction progress)
- `episodes.json` - full chapter text with character offsets
- `graph.json` - extracted nodes/edges (each tagged with `first_episode` + source quotes)
- `extracted_text.txt`, `files/` - the original upload and its extracted text

Reading/seen-tracking (which chapters/nodes/edges you've reviewed) is stored in your browser's
`localStorage`, keyed per book - it's per-device and never leaves your browser.

**Backup**: copy the `UPLOAD_FOLDER` directory. **Multiple books**: just keep reading/uploading -
each becomes its own project directory; there's no artificial limit.

## What self-hosting does *not* include

Everything above is 100% of the reading/graph functionality. What's described in
[STRATEGY.md](./STRATEGY.md) as the future **hosted** product adds a separate layer on top for
running BookMiro as a *shared, multi-user, paid* service - not more reading features:

- User accounts and Stripe billing (pay-once-per-book unlock)
- A shared public library (Postgres + object storage instead of local files)
- Rights acknowledgment + a public DMCA takedown flow
- An admin panel

None of that is required, or missing, for your own personal use of this repo.
