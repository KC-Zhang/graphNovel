# BookMiro Agent Notes

This file is a living index for future agents working in this repo. Update it when a feature, incident, or architectural decision materially changes how the app works.

## File Index

- `backend/app/utils/llm_client.py` - OpenAI-compatible chat client, JSON parsing, and optional OpenRouter fallback client.
- `backend/app/utils/file_parser.py` - PDF/EPUB/Markdown/TXT text extraction, EPUB spine reading, and EPUB TOC-based episode extraction.
- `backend/app/services/document_classifier.py` - PDF novel/textbook/uncertain classification from a bounded 2000-character sample.
- `backend/app/services/pdf_segmenter.py` - physical-page episodes and page-aware PDF outline/layout chapter segmentation.
- `backend/app/services/graph_extractor.py` - chapter/chunk entity extraction, entity merge rules, graph construction, and fallback retry use.
- `backend/app/services/extraction_manager.py` - per-project background extraction worker, failed episode tracking, and retry scheduling.
- `backend/app/api/graph.py` - upload/project/episode/graph/extraction API routes, bounded book search, and graph full/delta responses.
- `frontend/src/views/ReaderView.vue` - reader shell, chapter navigation, read progress, server search, graph delta polling, and retry action wiring.
- `frontend/src/components/PdfPageView.vue` - PDF.js canvas/text-layer rendering, search highlights, and graph mention overlays.
- `frontend/src/components/GraphPanel.vue` - keyed incremental D3 graph visualization, large-graph renderer switching, graph controls, and detail panels.
- `frontend/src/components/LargeGraphView.vue` - lazy Sigma/WebGL graph renderer with incremental Graphology sync and ForceAtlas2 worker layout.
- `frontend/src/utils/graphDelta.js` - merges additive episode graph deltas into the reader's current graph snapshot.
- `frontend/src/utils/largeGraph.js` - large-graph thresholds, stable graph keys/positions, and incremental Graphology synchronization.
- `locales/en.json`, `locales/zh.json` - UI strings for the reader, graph panel, and operational states.
- `render.yaml` - Render production deployment blueprint for backend, frontend, disk, and required secrets.
- `tools/selfheal/` - local Render log inspection and self-healing workflow.

## Built So Far

- Incremental book reader with per-chapter text loading, read coverage tracking, and graph reveal control.
- Knowledge graph extraction that streams chapter-by-chapter into persisted project graph data.
- Chapter review after upload, chapter drawer, chapter scrubber navigation, and graph cumulative/current-chapter modes.
- Extraction failure display in the graph panel with a user-visible retry button and a retrying state.
- OpenRouter fallback for failed primary LLM extraction calls using hardcoded `deepseek/deepseek-v3.2`.
- EPUB uploads can use structured NCX/EPUB navigation to build reader episodes before falling back to flattened-text segmentation.
- PDF uploads support pre-extraction chapter/page selection; page mode preserves physical pages, images, and layout while keeping search, progress, and graph jumps.
- Entity types are grouped with whitespace-normalized Unicode casefold keys while preserving the first-seen display spelling.
- Reader routes and heavy PDF/graph/history components load as separate chunks; the entry bundle has an enforced 300 KiB raw-size budget.
- Book-body search runs on the server and returns bounded results instead of downloading every episode into the browser.
- Graph polling transfers episode deltas after the initial snapshot, and graph rendering preserves existing positions as chapters are revealed.
- Dense graphs automatically use a WebGL renderer and worker-based layout while smaller graphs keep the more detailed SVG renderer.

## Decisions

- Keep extraction server-side and provider-agnostic through OpenAI-compatible APIs.
- Preserve the primary `LLM_*` provider as the first extraction attempt; use OpenRouter only as fallback when configured.
- Construct and call the configured OpenRouter fallback lazily, only after a primary extraction call raises.
- OpenRouter fallback uses fixed base URL `https://openrouter.ai/api/v1` and fixed model `deepseek/deepseek-v3.2`; only `OPENROUTER_API_KEY` is read from env.
- Failed episodes are tracked and retried by `ExtractionManager`; retries should not require resetting the whole book graph.
- The reader chapter navigation uses a compact slider/scrubber instead of a long horizontal strip of numbered chips.
- Production uses Render services: `bookmiro-backend` and `bookmiro-frontend`.
- Entity extraction chunks are capped at 6000 characters per LLM call.
- Deterministic fallback segmentation chooses heading runs by `tiktoken` token-span scoring without book-specific TOC rules.
- Upload/repair use an LLM-guided segmentation wrapper first: the LLM only infers heading/title structure from an early sample, while deterministic code still finds full-book offsets and falls back on failure.
- EPUB upload prefers whole-document TOC/nav targets and ignores nested `#anchor` section entries plus packaging pages such as Contents, Notes, Bibliography, copyright, and acknowledgments.
- PDF classification sends at most the first 2000 non-empty extracted characters to the LLM. Textbooks/papers default to page mode, novels to chapter mode, and uncertain results require user selection.
- PDF page mode keeps one episode per physical page, including image-only pages. Original PDFs are streamed through a project-scoped Range/conditional endpoint for PDF.js.
- PDF reading mode can change only before graph extraction starts; existing PDF projects are not migrated automatically.
- The desktop reader stays split and clamps the book pane at 320px; only phone-sized viewports below 640px use the reader/graph single-pane toggle.
- PDF chapter text is visually reflowed across soft layout line breaks while raw offsets remain unchanged for search and graph mentions.
- Relationship detail cards label source, relationship, and target explicitly instead of using ambiguous standalone arrows.
- The default graph scope is the current chapter. Extraction stays within the latest reached chapter plus two prefetched episodes unless the user explicitly selects the whole-book graph.
- Graph delta clients send `since_episode`; the API returns `revision_episode`, total counts, and either `mode: full` or `mode: delta`. Nodes and edges persist `last_episode` so metadata-only updates are not lost.
- Server text search is literal, capped at 300 results, and returns UTF-16 offsets compatible with browser text selections.
- Graphs switch from D3/SVG to lazy Sigma/WebGL at 500 visible nodes or 1,000 visible edges. ForceAtlas2 runs in a worker and stops after a bounded layout window.
- `npm run test:bundle` resolves the real entry script from built `index.html` and enforces a 300 KiB raw entry limit.

## Problems And Fixes

- Problem: extraction error banner had no direct retry affordance.
  Fix: `GraphPanel.vue` emits `retry-extraction`; `ReaderView.vue` calls the existing extraction ensure path.

- Problem: clicking retry left the stale error banner visible, making it unclear whether the click was processed.
  Fix: `ReaderView.vue` tracks `extractRetrying`; `GraphPanel.vue` shows "Retrying extraction..." while the backend worker is running.

- Problem: production logs showed chapter 11 failing with provider `400 data_inspection_failed`.
  Fix: failed primary LLM calls now retry once through OpenRouter DeepSeek V3.2 when `OPENROUTER_API_KEY` is configured.

- Problem: long books made the bottom chapter chip strip hard to use.
  Fix: replaced the chip strip with a slider/scrubber that previews chapter number, title, and read percentage.

- Problem: dense front matter such as table-of-contents rows can look like real chapter headings.
  Fix: chapter candidates are grouped into ordered runs and early dense duplicate runs are filtered by estimated token spans before exact-offset slicing.

- Problem: The Laws of Human Nature LLM structure probe confidently selected the front-matter TOC pattern (`same_line_number_title`) instead of body chapter starts.
  Fix: LLM-guided segmentation logs strategy/validation details, rejects tiny-span TOC-like strategies, and falls back to deterministic standalone-number/title/subtitle segmentation.

- Problem: EPUBs with rich internal TOCs, such as The Black Swan, could be flattened first and then mis-segmented by heading heuristics.
 Fix: EPUB upload now extracts episodes from NCX/EPUB navigation when available, using spine-ordered whole-document targets and falling back to existing segmentation otherwise.

- Problem: flattened PDF text treated citations, page numbers, and referenced-book headings as the host book's chapters (for example `How to Read a Book` produced `Chapter 0`, `Chapter 88`, and cited *Origin of Species* chapters).
 Fix: PDF chapter mode now prefers outline/layout evidence, validates ordered positive chapter runs, rejects outliers and pseudochapters, and offers physical-page mode when chapter evidence is unreliable.

- Problem: shrinking the split view below a readable width caused excessive wrapping and cramped controls.
 Fix: keep the desktop split view, clamp the reader at 320px, and reflow PDF soft line breaks into natural paragraphs; reserve full-width pane switching for phone layouts.

- Problem: relationship cards rendered arrows around the relationship label, making direction and meaning unclear.
 Fix: present every edge as explicit Source / Relationship / Target fields in canonical graph direction, with the supporting fact below.

- Problem: an open relationship detail card could cover the graph-to-reader control after the toolbar wrapped on a phone-width viewport.
 Fix: keep the graph header above detail cards so reader/graph navigation remains reachable at every supported width.

- Problem: entity types such as `concept`, `Concept`, and whitespace variants appeared as separate legend entries and colors.
 Fix: canonicalize entity-type keys case-insensitively in extraction/load and use the same key for frontend legend, color, and highlighting.

- Problem: the landing page (`Home.vue`) rendered with no orange accents and unstyled (transparent) buttons because its design tokens (`--black`, `--orange`, etc.) were declared in a `:root {}` rule inside `<style scoped>`; Vue rewrites that to `:root[data-v-…]`, which never matches `<html>`, so the variables were undefined.
 Fix: declare the tokens on `.home-container` (the component root element) inside the scoped block so they resolve and cascade to all descendants, including child components. Do not use `:root` inside scoped styles for shared variables.

- Problem: the landing page eagerly bundled the reader, PDF.js, graph code, and history UI, producing a roughly 916 KiB JavaScript entry and slow startup.
 Fix: split routes and heavy components, idle-load history, and enforce the entry budget; PDF.js and WebGL libraries are now requested only when their views need them.

- Problem: each graph mention normalized the entire chapter again while rendering backlinks, making long chapters pause for seconds.
 Fix: build one normalized quote matcher per chapter and reuse it for every mention.

- Problem: graph refreshes tore down all SVG elements and restarted layout, while hidden edge labels still incurred DOM and geometry work.
 Fix: use keyed D3 joins, persistent simulation records, animation-frame coalescing, write-only ticks, and remove hidden label DOM.

- Problem: SVG interaction and force layout degraded sharply for thousands of nodes and edges.
 Fix: switch dense visible graphs to Sigma/WebGL, synchronize Graphology incrementally, and run the bounded ForceAtlas2 layout in a worker.

- Problem: every search downloaded/scanned all chapters in the browser and every extraction update downloaded the full graph again.
 Fix: use bounded server search, a 20-episode text LRU, and revisioned graph delta responses.

## Maintenance Notes

- Do not log API keys or copied book text.
- Keep fallback provider changes isolated to the LLM/extraction layer; frontend retry should stay provider-agnostic.
- Add backend tests for extraction fallback behavior without hitting real networks.
- Run `cd frontend && npm test`, `cd frontend && npm run build`, and `cd frontend && npm run test:bundle` after reader or graph UI changes.
- Run `cd frontend && BOOKMIRO_ACADEMIC_PDF=/path/to/paper.pdf npm run test:e2e` for the PDF page-reading browser acceptance loop.
- Keep the large-graph Playwright scenario passing; it must exercise the WebGL threshold without requiring an external fixture.
- Run `backend/.venv/bin/pytest backend/tests` after extraction, API, or backend config changes.
