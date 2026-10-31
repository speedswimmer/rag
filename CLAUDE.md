# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

Requires `ANTHROPIC_API_KEY` as environment variable:
```bash
export ANTHROPIC_API_KEY='your-key'
```

Install dependencies:
```bash
pip install -r requirements.txt
```

## Running

```bash
# Local development
python wsgi.py

# Production (Pi)
gunicorn wsgi:app
```

## Architecture

Flask web application with RAG pipeline (`app/rag_engine.py`):

1. **Document loading** - PDF, DOCX, TXT, MD from `./dokumente/` with OCR fallback for scanned PDFs
2. **Chunking** - `RecursiveCharacterTextSplitter` (1000 chars, 200 overlap)
3. **Embedding** - `paraphrase-multilingual-MiniLM-L12-v2` (HuggingFace, CPU)
4. **Vector store** - ChromaDB at `./chroma_db/` with smart indexing (SHA-256 + mtime)
5. **Hybrid retrieval** - Ensemble of semantic vector search + BM25 keyword search with RRF fusion, configurable weight via `BM25_WEIGHT` env var (default 0.5)
6. **Generation** - `claude-sonnet-5-5` via Anthropic API, streaming responses
7. **Conversation context** - Condense-question pattern for follow-up questions

App factory in `app/__init__.py`, config dataclass in `app/config.py`, routes in `app/routes/`.

## Key Config (env vars / .env)

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for LLM calls |
| `LLM_MODEL` | `claude-sonnet-5-5` | Claude model for generation |
| `LLM_EFFORT` | `low` | Thinking depth of the model (`low` to `max`) |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Local embedding model |
| `BM25_WEIGHT` | `0.5` | BM25 weight in hybrid search (0.0 = vector only, 1.0 = BM25 only) |
| `CONTEXT_MESSAGES` | `5` | Number of history messages for condense-question |
| `SECRET_KEY` | `change-me-in-production` | Flask session secret |
