# BookMiro Agent Notes

This file is a living index for future agents working in this repo. Update it when a feature, incident, or architectural decision materially changes how the app works.

## File Index

- `backend/app/utils/llm_client.py` - OpenAI-compatible chat client, JSON parsing, and optional OpenRouter fallback client.
- `backend/app/services/graph_extractor.py` - chapter/chunk entity extraction, entity merge rules, graph construction, and fallback retry use.
- `backend/app/services/extraction_manager.py` - per-project background extraction worker, failed episode tracking, and retry scheduling.
- `backend/app/api/graph.py` - upload/project/episode/graph/extraction API routes.
- `frontend/src/views/ReaderView.vue` - reader shell, chapter navigation, read progress, extraction status polling, and retry action wiring.
- `frontend/src/components/GraphPanel.vue` - graph visualization, extraction banners, retry button, graph reveal controls, and detail panels.
- `locales/en.json`, `locales/zh.json` - UI strings for the reader, graph panel, and operational states.
- `render.yaml` - Render production deployment blueprint for backend, frontend, disk, and required secrets.
- `tools/selfheal/` - local Render log inspection and self-healing workflow.

## Built So Far

- Incremental book reader with per-chapter text loading, read coverage tracking, and graph reveal control.
- Knowledge graph extraction that streams chapter-by-chapter into persisted project graph data.
- Chapter review after upload, chapter drawer, chapter scrubber navigation, and graph cumulative/current-chapter modes.
- Extraction failure display in the graph panel with a user-visible retry button and a retrying state.
- OpenRouter fallback for failed primary LLM extraction calls using hardcoded `deepseek/deepseek-v3.2`.

## Decisions

- Keep extraction server-side and provider-agnostic through OpenAI-compatible APIs.
- Preserve the primary `LLM_*` provider as the first extraction attempt; use OpenRouter only as fallback when configured.
- OpenRouter fallback uses fixed base URL `https://openrouter.ai/api/v1` and fixed model `deepseek/deepseek-v3.2`; only `OPENROUTER_API_KEY` is read from env.
- Failed episodes are tracked and retried by `ExtractionManager`; retries should not require resetting the whole book graph.
- The reader chapter navigation uses a compact slider/scrubber instead of a long horizontal strip of numbered chips.
- Production uses Render services: `bookmiro-backend` and `bookmiro-frontend`.
- Entity extraction chunks are capped at 6000 characters per LLM call.

## Problems And Fixes

- Problem: extraction error banner had no direct retry affordance.
  Fix: `GraphPanel.vue` emits `retry-extraction`; `ReaderView.vue` calls the existing extraction ensure path.

- Problem: clicking retry left the stale error banner visible, making it unclear whether the click was processed.
  Fix: `ReaderView.vue` tracks `extractRetrying`; `GraphPanel.vue` shows "Retrying extraction..." while the backend worker is running.

- Problem: production logs showed chapter 11 failing with provider `400 data_inspection_failed`.
  Fix: failed primary LLM calls now retry once through OpenRouter DeepSeek V3.2 when `OPENROUTER_API_KEY` is configured.

- Problem: long books made the bottom chapter chip strip hard to use.
  Fix: replaced the chip strip with a slider/scrubber that previews chapter number, title, and read percentage.

## Maintenance Notes

- Do not log API keys or copied book text.
- Keep fallback provider changes isolated to the LLM/extraction layer; frontend retry should stay provider-agnostic.
- Add backend tests for extraction fallback behavior without hitting real networks.
- Run `cd frontend && npm test` and `cd frontend && npm run build` after reader or graph UI changes.
- Run `backend/.venv/bin/pytest backend/tests` after extraction, API, or backend config changes.
