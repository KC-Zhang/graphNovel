<div align="center">

<a href="https://pageandnode.com">
  <img src="./frontend/src/assets/logo/PageAndNode_mark.png" alt="PageAndNode logo" width="260"/>
</a>

# PageAndNode

**Read a book as a living knowledge graph.**
</br>
<em>Upload a book, paper, or textbook, and PageAndNode turns it into a living knowledge graph without flattening away the original document.</em>

[Website](https://pageandnode.com) | [English](./README.md) | [中文文档](./README-ZH.md)

</div>

## Overview

**PageAndNode** converts books and academic documents into knowledge graphs and syncs them to your reading progress. Instead of dumping the whole graph up front, it reveals only what you have already read — so it never spoils what is coming.

You only need to upload a book, paper, or textbook (PDF / EPUB / TXT / Markdown). PageAndNode will:

- Split it into ordered episodes (chapters, with a fixed-size fallback).
- Extract entities (characters, places, organizations, items, concepts) and their relationships, **in the same language as the book**.
- Reveal the graph chapter by chapter as you read, streaming new nodes/edges in as you advance.

## Release timeline

- **2026-07-18** — [Academic pages stay intact. Large graphs stay readable.](./release-notes/2026-07-18-big-books-update.md)

## Features

- **Academic reading mode**: read papers and textbooks as their original PDF pages, preserving structure, formulas, figures, tables, and formatting while keeping search highlights and graph source jumps available.
- **Reading-synced reveal**: the graph grows as you progress; already-read chapters only. Newly introduced nodes pulse so you can spot "what's new this chapter".
- **Language-locked extraction**: a Chinese book yields Chinese nodes, edge labels, and types — never mismatched English.
- **Jump to the source**: every node and relationship stores verbatim quotes; click to jump into the book text and read the surrounding context, with the passage highlighted.
- **Effortless relationship browsing (edge reel)**: select a character and scroll or arrow-key through all of its relationships, each auto-highlighting on the graph.
- **Background + streaming**: reading starts immediately while extraction continues chapter by chapter through the whole book; graph updates arrive as small deltas instead of repeatedly downloading the full graph.

## Quick Start

### Option 1: Source Code (Recommended)

#### Prerequisites

| Tool | Version | Description | Check |
|------|---------|-------------|-------|
| **Node.js** | 18+ | Frontend runtime (includes npm) | `node -v` |
| **Python** | ≥3.11, ≤3.12 | Backend runtime | `python --version` |
| **uv** | Latest | Python package manager | `uv --version` |

#### 1. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env and fill in your LLM API key
```

**Required environment variables:**

```env
# LLM API (any OpenAI SDK-compatible endpoint)
# Graph extraction calls the LLM per chapter, so prefer a cost-efficient model.
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
```

> PageAndNode extracts graphs locally via direct LLM calls — no third-party graph service required.

#### 2. Install Dependencies

```bash
# One-click install (root + frontend + backend)
npm run setup:all
```

Or step by step:

```bash
npm run setup          # Node deps (root + frontend)
npm run setup:backend  # Python deps (backend, creates a virtualenv)
```

#### 3. Start

```bash
npm run dev            # start frontend + backend
```

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5001`

Start individually:

```bash
npm run backend
npm run frontend
```

### Option 2: Docker

```bash
cp .env.example .env
docker compose up -d
```

Reads `.env` from the project root and maps ports `3000` (frontend) / `5001` (backend).

### Other ways to run it

See [SELF_HOSTING.md](./SELF_HOSTING.md) for Render deployment, the full environment variable
reference, and data/backup notes.

## How It Works

```
Upload (PDF/EPUB/TXT) -> Split into episodes -> Per-episode LLM extraction (language-locked)
   -> graph.json (nodes/edges tagged with first_episode + source quotes)
   -> Reader reveals the graph up to your current chapter
```

## Acknowledgements

PageAndNode was inspired by the **《红楼梦》 (Dream of the Red Chamber) demo** from **[MiroFish](https://github.com/666ghj/MiroFish)** — a multi-agent prediction engine that, among other things, deduced a lost ending of *Dream of the Red Chamber* from a knowledge graph of the first 80 chapters. That demo sparked the idea of reading any book through its evolving character graph. Many thanks to the MiroFish team for the inspiration.

## License

AGPL-3.0. See [LICENSE](./LICENSE).
