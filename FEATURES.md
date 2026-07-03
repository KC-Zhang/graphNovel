# BookMiro — Feature Log

A running log of the reader/graph features built so far. Append new entries as features land.

## Ingestion & extraction
- **Upload PDF / TXT / MD** — drag-and-drop or browse; multiple files per book (`Home.vue`, `api/book.js`).
- **Automatic chapter splitting** — uploaded text is segmented into ordered episodes.
- **Incremental, on-demand extraction** — entities and relationships are extracted chapter-by-chapter, prefetching ahead of the reading position (`ensureAhead`, `PREFETCH`). You can start reading immediately while the graph builds in the background.
- **Same-language graph** — the knowledge graph is built in the book's own language.
- **Live build status** — polling surfaces `extracted_upto` / `running`, with a "building graph" hint on the graph while it catches up.

## Reading experience
- **Chapter reader** with title, per-chapter counter, and a chapter drawer (table of contents) showing read/unread state.
- **Progress tracking (localStorage, per book)** — read episodes, reading position (`revealMax` / `viewEpisode`), and read relationships persist across sessions.
- **Auto mark-as-read** — a chapter is marked read when scrolled to the bottom, or immediately if it fits without scrolling.
- **No-spoiler progressive reveal** — the graph only reveals entities/relationships up to the furthest chapter read (`first_episode <= revealMax`).
- **Resizable split** — drag the divider between the reading pane and the graph pane to set the proportion; the choice is persisted (`bookmiro:splitPct`).

## Text ↔ graph cross-linking
- **Reverse links in the text** — entity mentions (purple) and relationship mentions (pink) are highlighted inline; clicking one selects and centers it in the graph.
- **Jump to source** — from any entity/relationship in the graph, jump back to the exact quote in the chapter, with scroll + flash highlight.

## Read-tracking model (edge-derived)
- **Relationships are the unit of "read".** Only relationships (edges) are tracked directly in `seenEdges`.
- **Entity read-state is derived** — an entity is considered read when all of its currently-shown relationships are read (an entity with no relationships counts as read). It reactivates automatically when a new relationship for it appears in a later chapter.
- **Auto-clear on scroll** — relationship links scroll past the top of the reading viewport are marked read.
- **Auto-clear on page turn** — clicking 下一页 / Next marks all relationship links on the finished page as read.
- **Manual toggle** — the detail panel's "mark read/unread" toggles a relationship, or (for an entity) all of its shown relationships.

## Knowledge graph panel
- **Force-directed D3 graph** with drag, zoom/pan, curved multi-edges, and self-loops.
- **Entity type legend** with per-type colors; toggle for relationship labels.
- **Unread emphasis** — unread entities pulse and render larger; read ones shrink and dim.
- **Focus unread (只看未读)** — fades already-read entities/relationships to spotlight what's new.
- **Current-chapter vs cumulative view (本章)** — toggle between the full cumulative graph and only the entities/relationships mentioned in the chapter you're currently viewing; the chapter view keeps the simulation small and fast on large books.
- **Entity detail + relationship reel** — an entity's relationships are listed and can be walked one-by-one (scroll or ↑/↓, or autoplay), each highlighting on the graph. The reel flows with the detail panel (no nested scrollbar).
- **Stable layout** — node positions are cached so the graph doesn't jump as it expands chapter by chapter.

## Platform
- **Bilingual UI (中文 / English)** via vue-i18n with a language switcher.
- **Library / history** of previously uploaded books.
