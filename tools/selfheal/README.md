# selfheal

A local CLI that reads deployed **error logs from Render**, groups them into distinct
issues, and — for the ones you pick — runs a coding agent on an isolated branch and
opens a **PR** via `gh`. Stdlib only; run it in your terminal.

```
Render API /v1/logs  ->  group issues  ->  you pick  ->  agent fixes on a branch  ->  gh pr create
```

## What you need to connect

1. **Render API key** (the one new secret) — provide it either way:
   - In the repo-root `.env` (already gitignored):
     ```
     RENDER_API_KEY=rnd_xxxxxxxx
     ```
   - Or exported in the shell (takes precedence over `.env`):
     ```bash
     export RENDER_API_KEY=rnd_xxxxxxxx
     ```
2. **The service** — pick it once via `setup`; the id + owner id are saved to
   `tools/selfheal/config.json` (gitignored). No manual copying.
3. Already required and present in this environment:
   - `gh` authenticated (`gh auth status`) — used to open PRs against the repo remote.
   - A coding agent CLI: **`codex`** (default) or `cursor-agent`.
   - Python 3 — the script is stdlib-only, no venv/deps needed to run it.

## Usage

Run from the repo root with plain `python3` (no `uv`/venv required — the script only
uses the standard library):

```bash
# 1. Connect the Render service and check your environment (once)
python3 tools/selfheal/selfheal.py setup

# 2. Look at recent errors (read-only, no changes)
python3 tools/selfheal/selfheal.py logs --since 6h

# 3. Fix interactively: pick issues, review each diff, open PRs
python3 tools/selfheal/selfheal.py run --since 6h
```

(`uv run tools/selfheal/selfheal.py ...` also works if you prefer running it inside the
backend's project environment, but it's not required.)

### `run` flags
- `--since 30m|6h|2d` — time window to pull logs for (default `6h`).
- `--level error,warning` — log levels to include (default `error`).
- `--type app,build,request` — log sources (default `app,build`, so build/deploy
  failures are captured too).
- `--agent codex|cursor` — override the fix agent (default: saved config / auto-detect).
- `--limit N` — only consider the top N issues.
- `--auto` — skip the per-issue diff confirmation (still one branch + PR per issue).

## How it works

- **Logs**: `GET /v1/logs` with your `ownerId` + `serviceId`, filtered by level/type,
  paginated backward over the time window.
- **Grouping**: multi-line Python tracebacks are stitched into one issue keyed by the
  terminating `SomeError: ...` line plus the deepest app-code frame; other error lines
  are normalized (timestamps, ids, numbers, paths removed) and de-duplicated. Issues are
  sorted by occurrence count.
- **Fix + PR**: for each selected issue the tool creates `selfheal/<date>-<slug>`, runs
  the agent with the error + log excerpt, shows you `git diff`, and on approval commits,
  pushes, and runs `gh pr create`. It returns to the base branch between issues.

## Safety

- The Render API key is read from the environment only — never written to disk or committed.
- Requires a clean working tree; every change is isolated on its own branch and lands
  only as a PR you merge. Diffs are shown before pushing (unless `--auto`).
- `config.json` holds only non-secret ids and is gitignored.

## Notes / tuning

- Agent invocation templates live in the `AGENTS` dict at the top of `selfheal.py` if you
  need to adjust flags for your `codex` / `cursor-agent` version (e.g. if a future
  `codex` release renames `-s workspace-write` again). The agent subprocess's stdin is
  always redirected to `/dev/null` — some agent CLIs otherwise block forever waiting for
  input that will never come.
- If Render changes log query parameters, adjust `fetch_logs()`.
- Optional future step: a `--watch` mode that re-polls after redeploy to confirm the
  error cleared (a true self-iterating loop).

## Verified

Run end-to-end against the live `bookmiro-backend` deployment: pulled logs, grouped a
recurring `uv`/`VIRTUAL_ENV` build warning into one issue, ran `codex exec`, and opened
a real PR with the fix (`uv sync --active --frozen` / `uv run --active gunicorn`) against
`render.yaml`.
