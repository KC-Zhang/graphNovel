# PageAndNode Agent Notes

This file is a living index for future agents working in this repo. Update it when a feature, incident, or architectural decision materially changes how the app works.

## File Index

- `backend/app/utils/llm_client.py` - OpenAI-compatible chat client, JSON parsing, and optional OpenRouter fallback client.
- `backend/app/utils/file_parser.py` - PDF/EPUB/Markdown/TXT text extraction, EPUB spine reading, and EPUB TOC-based episode extraction.
- `backend/app/services/document_classifier.py` - PDF novel/textbook/uncertain classification from a bounded 2000-character sample.
- `backend/app/services/pdf_segmenter.py` - physical-page episodes and page-aware PDF outline/layout chapter segmentation.
- `backend/app/services/graph_extractor.py` - chapter/chunk entity extraction, entity merge rules, graph construction, and fallback retry use.
- `backend/app/services/extraction_manager.py` - per-project background extraction worker, failed episode tracking, and retry scheduling.
- `backend/app/api/graph.py` - upload/project/episode/graph/extraction API routes, bounded book search, and graph full/delta responses.
- `frontend/src/releaseNotes.js` - structured English and Chinese release-note content rendered by the dedicated release route.
- `frontend/src/views/ReaderView.vue` - reader shell, chapter navigation, read progress, server search, graph delta polling, and retry action wiring.
- `frontend/src/views/Home.vue` - PageAndNode landing page, upload/library entry points, capability overview, and compact bilingual release timeline.
- `frontend/src/views/ReleaseNotesView.vue` - dedicated bilingual release-note page linked from the landing timeline.
- `frontend/src/components/PdfPageView.vue` - PDF.js canvas/text-layer rendering, search highlights, and graph mention overlays.
- `frontend/src/components/GraphPanel.vue` - keyed incremental D3 graph visualization, large-graph renderer switching, graph controls, and directional relationship detail panels.
- `frontend/src/components/LargeGraphView.vue` - lazy Sigma/WebGL renderer with cooperative hydration, collision-safe semantic-zoom labels, a bounded relationship-label canvas, dense-graph camera input, and bounded/frozen ForceAtlas2 layout.
- `frontend/src/utils/extractionSchedule.js` - whole-book background extraction target policy.
- `frontend/src/utils/graphDelta.js` - merges additive episode graph deltas into the reader's current graph snapshot.
- `frontend/src/utils/pdfAnnotations.js` - PDF.js text-span matching and exact graph-link/highlight annotation planning.
- `frontend/src/utils/largeGraph.js` - large/massive graph profiles, stable graph keys/positions, cooperative hydration, click-time edge picking, and Graphology synchronization.
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
- The reader route stays off the landing-page entry; PDF.js, WebGL, and history remain on-demand chunks, while `GraphPanel` ships with the reader route to avoid a second graph-critical network round trip. The entry bundle has an enforced 300 KiB raw-size budget.
- Book-body search runs on the server and returns bounded results instead of downloading every episode into the browser.
- Graph polling transfers episode deltas after the initial snapshot, and graph rendering preserves existing positions as chapters are revealed.
- Dense graphs automatically use a WebGL renderer and worker-based layout while smaller graphs keep the more detailed SVG renderer.
- Reader controls and graph loading state mount after project metadata; the initial graph and current episode then load in parallel with duplicate graph requests coalesced.
- Massive all-chapter graphs keep every node and edge but use a static WebGL profile that avoids continuous layout refreshes, native edge-picking buffers, and repeated wheel renders.
- Full-graph WebGL views keep the topology readable with collision-safe semantic labels: high-connectivity entities win overview priority, more local names appear as the camera zooms, and selected/search targets always remain eligible. Massive graphs rebuild this bounded label overlay cooperatively after camera movement. Dense relationship labels remain opt-in and render through a bounded overlay rather than Sigma's all-edge label pass.
- Standard WebGL graphs retain the original unweighted ForceAtlas2 topology for a bounded 6.5-second worker window after a topology change, then stop and kill the worker while preserving the settled positions. Dense overviews use a compact 12px label base with smooth capped growth for more-connected nodes; both tiers scale together with a deliberately damped camera-zoom curve.
- The landing page carries only a compact, dated bilingual release timeline. Full release narratives live on the dedicated `/release-notes` route and under `release-notes/`; `README.md` and `README-ZH.md` also keep timeline links instead of embedding full notes.

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
- PDF page mode renders native internal and safe external PDF link annotations above the PDF.js text layer; internal destinations map physical page numbers back to reader episodes and enter the shared navigation history.
- The desktop reader stays split and clamps the book pane at 320px; only phone-sized viewports below 640px use the reader/graph single-pane toggle.
- PDF chapter text is visually reflowed across soft layout line breaks while raw offsets remain unchanged for search and graph mentions.
- Relationship details read naturally in canonical graph direction as source entity → relationship → target entity. They lay out horizontally in ordinary panels and vertically in narrow panels, while an explicit localized aria label preserves the semantic roles.
- The default graph scope is cumulative through the current chapter, while sequential extraction is scheduled through the whole book immediately. Users can still switch to the current chapter alone or the complete book.
- Graph delta clients send `since_episode`; the API returns `revision_episode`, total counts, and either `mode: full` or `mode: delta`. Nodes and edges persist `last_episode` so metadata-only updates are not lost.
- Server text search is literal, capped at 300 results, and returns UTF-16 offsets compatible with browser text selections.
- Graphs switch from D3/SVG to lazy Sigma/WebGL at 500 visible nodes or 1,000 visible edges. Sigma paints deterministic positions first; below the massive threshold, ForceAtlas2 then loads and runs in a worker for a bounded layout window.
- At 2,000 visible nodes or 8,000 visible edges, use the massive static profile: preserve the exact Graphology graph, render simple line edges, disable z-index/native edge-picking buffers and live ForceAtlas2, select edges geometrically on click, and batch wheel/resize/style work. Capture massive-graph wheel input before Sigma because its normal event dispatch performs a synchronous GPU hit test per event.
- Standard WebGL ForceAtlas2 keeps the original unweighted settings and runs for at most 6.5 seconds after the last topology change. Metadata-only refreshes preserve the remaining deadline; they must not restart a full layout window. Once settled, stop and kill the supervisor so the graph remains frozen until topology actually changes.
- Connection count is display-only. At camera ratio 1, dense node labels keep a 12px base through three incident relationships, then grow logarithmically up to 18px. Camera zoom scales the hierarchy with a damped exponent and a 0.78–1.6 bound. Standard Sigma labels use finite spatial density while ForceAtlas2 moves, then the frozen graph switches to the same collision-aware overlay used by massive graphs; never feed relationship direction or endpoint degree back into layout geometry.
- Massive graphs keep Sigma's built-in edge-label renderer disabled because it scans every edge on each render. `LargeGraphView` instead selects at most 36 stable, high-connectivity/diverse relationship labels and draws only visible, non-overlapping candidates on a separate canvas; a selected relationship is always included.
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

- Problem: separate Source / Relationship / Target metadata boxes still made a relationship read like form fields, and earlier arrow placement did not clearly connect the two entities.
 Fix: render only the two entity cards with the relationship phrase above a single arrow between them, keep the canonical source-to-target DOM order, and rotate the flow downward in narrow detail panels.

- Problem: an open relationship detail card could cover graph navigation after the toolbar wrapped on a phone-width viewport.
 Fix: keep the graph header above detail cards, and keep the reader drawer toggle on the graph pane's left edge above graph overlays.

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

- Problem: the performance release made graph loading feel slower by waiting for the initial full graph before mounting the reader, deferring extraction after the first three episodes, and bootstrapping layout before the first WebGL frame.
 Fix: mount the reader immediately after metadata, fetch graph and episode concurrently, restore whole-book background extraction, paint Sigma before loading the layout worker, and keep cumulative-to-current scope plus delta transfer to bound render work.

- Problem: extraction status advances in memory just before `graph.json` and the project revision are persisted, so the reader could mark the final status as loaded while still holding the previous graph snapshot.
 Fix: compare status against the `revision_episode` confirmed by `/graph/data`, continue polling until they match, and coalesce concurrent initial/poll graph requests.

- Problem: a 5,000-node/20,000-edge All Chapters graph became slower after the first WebGL optimization; a ForceAtlas2 worker still copied every position back through Sigma on each iteration, native edge events maintained an extra picking framebuffer, and every wheel event performed a synchronous GPU hit test before app-level debouncing.
 Fix: cooperatively hydrate the full graph, use the massive static profile, keep neutral reducers off the initial render, update interactive styles in bounded partial batches, debounce resize, and capture/batch wheel input before Sigma. The acceptance loop now verifies exact graph counts, search, toolbar, maximize/restore, drag, and a 12-event wheel burst.

- Problem: painting every entity name in All Chapters technically preserved labels but turned a 1,280-node overview into an opaque text wall that hid the graph; fading rejected labels still rebuilt the same gray wall after ForceAtlas2 froze.
 Fix: standard and massive WebGL paths reject offscreen, toolbar-covered, and overlapping label boxes entirely. Important entities are considered first, the frozen layout uses a cooperatively painted overlay, zoom reveals more local labels, and searched/selected entities stay visible. Relationship labels remain independently capped at 36.

- Problem: selecting a search result while Sigma was scheduling a settings refresh could read temporarily unnormalized display coordinates and animate the camera far outside the graph.
 Fix: center search-selected nodes and edges by converting their stable source graph coordinates into framed coordinates instead of reading the transient display cache.

- Problem: an attempted hub-spreading optimization replaced the familiar graph structure with a nearly uniform scatter, reduced 1,000+ node labels to 9px, and made neutral links effectively disappear because translucent edge colors were composited with Sigma's premultiplied-alpha blend mode.
 Fix: restore the original unweighted ForceAtlas2 settings and 6.5-second window, use an opaque neutral edge color, keep edges visible while ordinary graphs move, and freeze the exact settled coordinates. Use a compact dense-graph label base, enlarge high-connection nodes with a capped logarithmic curve that does not influence layout, and apply the same damped camera zoom multiplier to both sizes.

- Problem: PDF graph source highlights and text-to-graph links covered whole PDF.js line spans, stretched beyond the printed text, dropped non-verbatim quote matches, and let overlapping relationships overwrite the intended node link.
 Fix: set the standalone PDF text layer's scale explicitly, map tolerant quote matches back to exact character fragments, reuse the matched episode-text slice, and preserve first-link/node priority across overlaps.

- Problem: read graph links faded to an almost invisible gray dotted line, graph-only mode had no explicit reader-return affordance, the history control floated midway down the whole reader, and native PDF references were inert.
 Fix: retain softer node/relationship colors for read links, use a bidirectional chevron drawer handle on the graph pane's left edge to hide/show the reader, move history to the graph header with a curved jump-back icon, and render PDF link annotations with physical-page navigation.

## Release Note System

- Full repository notes live at `release-notes/YYYY-MM-DD-short-slug.md`; add a matching `.zh.md` file for Chinese.
- Full website notes are structured in `frontend/src/releaseNotes.js` and rendered on the dedicated `/release-notes` route. Keep the route lazy-loaded so release prose and layout stay off the landing-page critical path.
- `Home.vue`, `README.md`, and `README-ZH.md` are indexes only. They may show a newest-first timeline with the date and linked title, but never the full narrative, screenshots, detailed bullets, or validation section.
- Use the same release date and outcome-focused title in the website timeline, both README timelines, and both full notes.
- Write every full note in this order:
  1. State the user-visible outcome and the important non-change in the opening paragraph.
  2. Use “Think of it as...” and a compact comparison table when two modes, states, or mechanisms are easy to confuse.
  3. Use “For this release, we:” and an ordered sequence of concrete inputs, actions, and outputs.
  4. Use “So:” for explicit conclusions, including what did not happen or what data was not removed.
  5. Use “One important detail:” for the main limitation, tradeoff, or likely misunderstanding.
  6. End with `Validation`, listing only checks that actually ran or named acceptance fixtures that exist in the repository.
- Prefer exact nouns and mechanisms. Name the reading mode, document type, renderer, preserved page elements, graph scope, and test-fixture size when they matter.
- Avoid headings such as “Improvements,” “Updates,” or “Better experience,” and avoid unsupported adjectives such as “seamless,” “powerful,” or “blazing fast.”
- Keep documentation-only changes separate from runtime changes. Never imply that a browser test, provider call, deployment, or production verification occurred unless it did.
- Update English and Chinese together, then verify every timeline link and route before calling the release note complete.

## Maintenance Notes

- Do not log API keys or copied book text.
- Keep release copy concrete and authorial: describe user-visible behavior, acknowledge unavoidable tradeoffs such as very dense overviews, and avoid generic launch-language or duplicated copy across Discord, the homepage, and README.
- Keep fallback provider changes isolated to the LLM/extraction layer; frontend retry should stay provider-agnostic.
- Add backend tests for extraction fallback behavior without hitting real networks.
- Run `cd frontend && npm test`, `cd frontend && npm run build`, and `cd frontend && npm run test:bundle` after reader or graph UI changes.
- Run `cd frontend && BOOKMIRO_ACADEMIC_PDF=/path/to/paper.pdf npm run test:e2e` for the PDF page-reading browser acceptance loop.
- Keep the large-graph Playwright scenario passing; it uses a self-contained 12-chapter fixture with 5,000 nodes and 20,000 edges, starts in the 96-node/240-edge cumulative-to-current scope, then measures the real All Chapters transition.
- Keep the standard-WebGL layout scenario passing; its 600-node/1,200-edge fixture verifies visible relationship draws during layout, a final frozen coordinate map, collision-free in-bounds labels, compact 12px ordinary-node type, hub emphasis, semantic zoom, and a sub-500ms main-thread heartbeat gap.
- The large-graph acceptance test must keep the reader usable while `/graph/data` is held, issue only one initial graph request, preserve exact All counts, become WebGL-ready within 3 seconds, accept search within 1 second, keep the one-time 5k/20k WebGL allocation gap below 550 ms (blocked portion below 535 ms), keep post-interaction gaps below 500 ms, and keep its 12-wheel burst below 1 second.
- At the 5,000-node/20,000-edge fixture size, the settled overview must report a non-empty, bounded, unique node-label set rather than all 5,000 overlapping names. The massive relationship overlay must remain capped at 36, toggle in under 1 second without a heartbeat gap above 500 ms, and keep a searched/selected relationship labelled while the global toggle is off.
- Run `backend/.venv/bin/pytest backend/tests` after extraction, API, or backend config changes.
