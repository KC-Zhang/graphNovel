# Academic pages stay intact. Large graphs stay readable.

Released July 18, 2026.

This release adds an Academic reading mode for papers and textbooks, makes
document structure detection more reliable, and keeps the complete graph usable
as books grow. It changes PDF reading, extraction recovery, and graph rendering;
it does not remove any nodes or relationships from All Chapters.

Think of it as two reading paths:

| | Novel / continuous prose | Academic document |
|---|---|---|
| Best for | Novels and narrative books | Papers, textbooks, and research reports |
| Default PDF mode | Detected chapters | Physical pages |
| Reader presentation | Reflowed text | Original PDF pages |
| What stays intact | Chapter order and readable paragraphs | Formulas, figures, tables, captions, columns, images, and typography |
| Search and graph jumps | Exact extracted passage | Highlights and source links over the original page |

For this release, we:

1. Classify a PDF from a bounded early text sample, defaulting novels to chapters and papers or textbooks to physical pages. Uncertain documents ask the reader to choose.
2. Render physical pages through PDF.js instead of flattening an academic document into reflowed body text, while retaining search highlights and graph source jumps.
3. Prefer EPUB navigation and PDF outline or page-layout evidence before fallback segmentation, reducing false chapters from contents pages, citations, page numbers, and referenced books.
4. Open the reader before the complete graph is ready, load the current episode and initial graph in parallel, search on the server, and transfer later changes as graph deltas.
5. Move dense graphs to WebGL. Standard graphs receive a bounded layout window before freezing; massive graphs keep every node and edge in a static profile.
6. Draw a bounded, collision-aware set of labels. Important entities come first, zoom reveals more names, and searched or selected entities remain visible.
7. Present relationship details as source entity → relationship → target entity, merge entity types case-insensitively, and let failed chapters retry without rebuilding the book.

So:

- Academic PDFs keep the page structure that carries meaning instead of becoming a wall of extracted text.
- Page mode still supports search, reading progress, graph extraction, and jumps back to the source.
- All Chapters still contains every extracted node and relationship; the renderer only limits which labels are painted at the current zoom.
- The primary extraction provider remains the first attempt. OpenRouter is an optional fallback after a primary failure.
- The reader remains usable while extraction and graph delivery continue in the background.

One important detail: a cleaner graph overview does not mean graph data was
discarded. Label selection controls only which names are drawn at the current
camera position. Search targets and selected entities stay visible, zoom reveals
more names, and the complete node-and-edge topology remains available.

## Validation

- `cd frontend && npm test` — 59/59 tests passed.
- `cd frontend && npm run build` — production build completed.
- `cd frontend && npm run test:bundle` — 223,992 bytes against a 307,200-byte limit.
- The massive-graph browser fixture contains exactly 5,000 nodes and 20,000 relationships.
- The standard WebGL fixture contains 600 nodes and 1,200 relationships.
