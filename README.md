# RAG Web App

A self-hosted document question-answering system built with Flask, ChromaDB, and the Claude API. Upload PDFs, Word documents, or text files — then ask questions about them in natural language.

Built to run on a Raspberry Pi 5, but works on any Linux system with Python 3.11+.

## Features

- Upload PDF, DOCX, and TXT files via drag-and-drop
- OCR fallback for scanned PDFs (Tesseract, German + English)
- Live upload progress via Server-Sent Events
- Smart indexing — only changed files are re-indexed (SHA-256 + mtime)
- Answers in the language of the question (multilingual)
- Dark theme UI, runs well on mobile
- CSRF protection, XSS-safe, sanitized error messages
- Auto-retry on Anthropic API overload (3 attempts)
- systemd service with Gunicorn (1 worker, 4 threads)

## Requirements

- Python 3.11+
- Anthropic API key — get one at [console.anthropic.com](https://console.anthropic.com)
- System packages: `tesseract-ocr tesseract-ocr-deu poppler-utils`

## Installation

Clone the repo and run the deploy script. It handles everything: system packages, Python virtualenv, dependencies, and the systemd service.

```bash
git clone https://github.com/speedswimmer/rag.git
cd rag
bash deploy.sh
```

After the first run, edit `.env` and set your API key:

```bash
nano /home/jarvis/rag/.env
```

```env
ANTHROPIC_API_KEY=sk-ant-...
SECRET_KEY=some-random-string-here
```

Then restart the service:

```bash
sudo systemctl restart rag-web
```

The app is now running at `http://<your-ip>:8080`.

## HTTPS Setup (recommended)

Run the HTTPS script once after the initial deployment. It installs Nginx as a reverse proxy with a self-signed TLS certificate and blocks direct access to port 8080.

```bash
bash setup_https.sh
```

After that, the app is available at `https://<your-ip>`. The browser will show a one-time certificate warning — this is expected for self-signed certificates. Click *Advanced* and proceed.

> If you have a public domain pointing to this machine, replace the self-signed certificate with one from Let's Encrypt (`certbot --nginx`).

## Updating

```bash
cd /home/jarvis/rag
git pull
venv/bin/pip install -r requirements.txt   # only needed when requirements changed
sudo systemctl restart rag-web
```

## Configuration

All settings live in `.env`. The defaults work out of the box — only `ANTHROPIC_API_KEY` and `SECRET_KEY` are required.

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** Your Anthropic API key |
| `SECRET_KEY` | — | **Required.** Random string for Flask session signing |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Local sentence-transformer model (~80 MB, downloaded on first run) |
| `LLM_MODEL` | `claude-sonnet-4-20250514` | Claude model used for answer generation |

## Architecture

```
dokumente/          # Drop your files here
chroma_db/          # ChromaDB vector store (auto-created)
app/
├── rag_engine.py   # RAG pipeline: embed → retrieve → generate
├── indexer.py      # Smart indexer: tracks file changes via SHA-256 + mtime
├── config.py       # Central config, loaded from .env
└── routes/
    ├── chat.py     # POST /ask — question answering
    ├── documents.py # Upload, delete, index status
    └── info.py     # App info and config overview
wsgi.py             # Gunicorn entry point
deploy.sh           # Full install/update script
setup_https.sh      # Nginx + TLS setup (run once after deploy.sh)
```

**RAG pipeline steps:**

1. Documents are split into 1000-character chunks with 200-character overlap
2. Chunks are embedded with `all-MiniLM-L6-v2` (local, CPU-only, no API calls)
3. Embeddings are stored in ChromaDB
4. On each question, the top 10 most relevant chunks are retrieved
5. Claude generates an answer based on those chunks

## License

GPL-3.0 — see [LICENSE](LICENSE).
