# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

Requires `ANTHROPIC_API_KEY` as environment variable:
```bash
export ANTHROPIC_API_KEY='your-key'
```

Install dependencies:
```bash
pip install langchain langchain-anthropic langchain-community langchain-text-splitters langchain-classic chromadb sentence-transformers pypdf
```

## Running

```bash
python rag_demo.py
```

Place `.pdf` or `.txt` files into `./dokumente/` before starting. The script will exit if no documents are found.

## Architecture

Single-file RAG pipeline (`rag_demo.py`) with these stages:

1. **Document loading** - Loads PDFs and TXT files from `./dokumente/` via LangChain `DirectoryLoader`
2. **Chunking** - Splits text into 1000-char chunks with 200-char overlap via `RecursiveCharacterTextSplitter`
3. **Embedding** - Uses `all-MiniLM-L6-v2` (HuggingFace, ~80MB, CPU-only) to embed chunks
4. **Vector store** - Persists embeddings in ChromaDB at `./chroma_db/`
5. **Retrieval + Generation** - `RetrievalQA` chain retrieves top-3 chunks and passes them to `claude-sonnet-4-20250514` via the Anthropic API
6. **Interactive loop** - REPL that accepts questions, prints answers and source citations

The vector store is rebuilt from scratch on every run (no incremental update logic). The embedding model is downloaded on first run.

## Key Config Constants

| Constant | Value | Purpose |
|---|---|---|
| `DOCS_DIR` | `./dokumente` | Source document folder |
| `CHROMA_DIR` | `./chroma_db` | Vector DB persistence path |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Local sentence-transformer model |
| `LLM_MODEL` | `claude-sonnet-4-20250514` | Claude model for generation |
