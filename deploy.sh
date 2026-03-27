#!/usr/bin/env bash
# deploy.sh — Install or update RAG web app on Raspberry Pi 5
set -euo pipefail

REPO_URL="https://github.com/speedswimmer/rag.git"
APP_DIR="/home/jarvis/rag"
SERVICE_NAME="rag-web"

echo "=== RAG Deploy Script ==="

# 1. Clone or update repository
if [ -d "$APP_DIR/.git" ]; then
    echo "[1/5] Pulling latest changes..."
    git -C "$APP_DIR" pull
else
    echo "[1/5] Cloning repository..."
    git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"

# 2. Install system dependencies (OCR + PDF rendering)
echo "[2/6] Installing system packages for OCR..."
sudo apt-get install -y tesseract-ocr tesseract-ocr-deu poppler-utils

# 3. Create/update Python venv
echo "[3/6] Setting up Python environment (this can take 10-20 minutes on first run)..."
if [ ! -d venv ]; then
    echo "      Creating virtual environment..."
    python3 -m venv venv
fi
echo "      Upgrading pip..."
venv/bin/pip install --upgrade pip
echo "      Installing packages (chromadb + sentence-transformers take the longest)..."
venv/bin/pip install -r requirements.txt

# 3. Check .env
echo "[4/6] Checking configuration..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "  ATTENTION: .env was created from .env.example"
    echo "  Edit /home/jarvis/rag/.env and set ANTHROPIC_API_KEY before starting!"
    echo ""
else
    if ! grep -q "^ANTHROPIC_API_KEY=sk-" .env; then
        echo "  WARNING: ANTHROPIC_API_KEY does not look set in .env"
    fi
fi

# 4. Ensure dokumente/ directory exists
echo "[5/6] Ensuring dokumente/ directory exists..."
mkdir -p dokumente

# 5. Install and (re)start systemd service
echo "[6/6] Installing and starting service..."
sudo cp rag-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

sleep 2
echo ""
echo "=== Deployment complete ==="
sudo systemctl status "$SERVICE_NAME" --no-pager -l
