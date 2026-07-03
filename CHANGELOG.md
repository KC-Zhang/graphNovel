# Changelog

## 2026-07-03 - Reader, Graph, Chapter, and Extraction Improvements

This entry documents the current implementation work on the `main` branch, including the committed reader/graph workflow changes and the reading-coverage rework described below.

### Reader Workflow

- Added a chapter review step after upload so users can inspect detected sections before graph extraction starts.
- Added incremental reader navigation that restores the last project-specific reading position from local storage.
- Added chapter drawer read state indicators and read counts.
- Added text-to-graph back links in the reader: detected entity and relationship mentions in the book text can select and center the matching graph item.
- Added read/unread styling for in-text graph links.
- Added automatic relationship read tracking while reading.
- Reworked reading coverage tracking to be based on actual viewport dwell time instead of chapter navigation or scroll position alone:
  - Tracks normalized viewport intervals per chapter (`episodeRanges`) instead of a single furthest-scroll marker.
  - Removed the page-turn behavior that marked every relationship link on the current page as read on "Next chapter"; link clearing now depends only on scrolling.
  - Requires a short dwell (about 1.2s of no scrolling) on a screen before it counts as read, so casually scrolling through a chapter no longer marks it as read.
  - Avoids marking skipped relationship links as read when jumping into the middle of a chapter from the graph panel: only the intervals actually dwelt on are covered, and the animated scroll-to-quote no longer marks the skipped-over text as read.
  - Adds a clickable/draggable vertical reading rail beside the chapter text showing visited (possibly non-contiguous) ranges and the current viewport position; replaces the native `.book-text` scrollbar so there is a single scroll indicator.
  - Adds per-chapter partial-progress coloring to the chapter scrubber track and unread/partial/read states (with percentage) in the chapter drawer.

### Knowledge Graph Panel

- Added graph maximize/restore so the graph can take the full reader width.
- Added chapter-only graph mode to inspect only the current chapter's graph data.
- Added focus-unread mode and read/unread graph styling.
- Added node and relationship read controls in the detail panel.
- Added relationship walk-through behavior for selected nodes.
- Added graph-to-reader jumps from entity and relationship mentions.
- Added dense-graph performance handling:
  - Edge labels are automatically hidden when a visible graph is dense.
  - The automatic hiding can be overridden by the user.
  - The dense-graph explanation was moved behind a small help marker near the edge-label toggle, so it no longer blocks the graph view.
- Added graph density utility tests.

### Chapter Detection and Titles

- Improved chapter segmentation so PDF page numbers are not treated as chapters.
- Kept legitimate numbered chapters supported when they form a plausible chapter sequence.
- Added support for letter-spaced PDF chapter markers such as `C H A P T E R`.
- Added support for PDF-extracted spaced chapter numbers such as `1 0` and `2 5`.
- Combined multi-line English chapter titles, for example `Chapter 10 - Managing the Gatekeeper Artfully`.
- Improved fallback section titles so they use meaningful nearby text instead of generic `Section N` whenever possible.
- Preserved useful Chinese chapter headings and tested Chinese chapter segmentation.

### Entity Extraction

- Restored smaller extraction granularity inside long reader sections.
- Reader navigation can still use meaningful chapters/sections, but graph extraction now splits long section text into smaller LLM calls again.
- Reduced the extraction window from 6000 characters to 3000 characters per call to avoid chapter-scale summarization that skipped too many entities and relationships.
- Added a backend regression test that verifies a long reader section is extracted through multiple smaller LLM excerpts while keeping mentions mapped to the same reader chapter.

### Library and Project Management

- Added compact project-list responses so library views do not receive full episode payloads for every book.
- Added repair/rebuild episode metadata from saved extracted text.
- Added reset/reprocess graph state for a project.
- Added delete and repair/reprocess actions in the library/history UI.
- Reset in-memory extraction state when project graph state is reset or repaired.

### Backend and Deployment

- Added configurable CORS origins.
- Updated deployment config to include the CORS setting.
- Improved project metadata handling for episode counts and compact summaries.
- Kept partial graph data usable when extraction has already produced some results.

### Tests and Verification

- Added root `npm test` orchestration for frontend and backend tests.
- Added frontend `node:test` coverage for:
  - Graph density label hiding behavior.
  - Reader link matching and link-read behavior.
  - Reading coverage interval utilities (clamping, merging, coverage math, range containment).
  - Reader link clearing regression checks (no page-turn clearing, mid-chapter jump links stay unseen).
- Added backend pytest coverage for:
  - Chapter segmentation edge cases.
  - Project list compact summaries.
  - Project repair behavior.
  - Project reset behavior.
  - Smaller extraction chunks inside long sections.
- Verified the work with:
  - `npm test`
  - `npm run build`

### Operational Notes

- Existing saved graphs that were extracted with the larger 6000-character windows will not automatically improve. Reset/reprocess the book graph or re-upload the book to regenerate graph data with the smaller extraction chunks.
- Existing projects with old generic chapter titles may need repair/reprocess or re-upload so their saved episode metadata is rebuilt with the improved segmenter.
- The Vite build still reports the existing non-fatal warning about `pendingUpload.js` being imported both dynamically and statically.
