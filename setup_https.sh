#!/usr/bin/env bash
# setup_https.sh — Configure Nginx as HTTPS reverse proxy for the RAG web app
# Run this once after deploy.sh has completed successfully.
set -euo pipefail

APP_DIR="/home/jarvis/rag"
SERVICE_NAME="rag-web"
CERT_DIR="/etc/ssl/private/rag"
NGINX_CONF="/etc/nginx/sites-available/rag"

echo "=== HTTPS Setup for RAG Web App ==="

# 1. Install Nginx
echo "[1/5] Installing Nginx..."
sudo apt-get install -y nginx

# 2. Generate self-signed certificate (non-interactive)
echo "[2/5] Generating self-signed TLS certificate (valid 10 years)..."
sudo mkdir -p "$CERT_DIR"
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout "$CERT_DIR/rag.key" \
    -out "$CERT_DIR/rag.crt" \
    -subj "/CN=rag-local/O=RAG/C=DE"
sudo chmod 600 "$CERT_DIR/rag.key"

# 3. Write Nginx config
echo "[3/5] Writing Nginx configuration..."
sudo tee "$NGINX_CONF" > /dev/null <<'EOF'
server {
    listen 443 ssl;
    listen [::]:443 ssl;

    ssl_certificate     /etc/ssl/private/rag/rag.crt;
    ssl_certificate_key /etc/ssl/private/rag/rag.key;

    # Modern TLS only
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    # Proxy to Gunicorn
    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # Allow large file uploads (matches app's 50 MB limit)
        client_max_body_size 55M;

        # SSE: disable buffering for live upload progress
        proxy_buffering    off;
        proxy_read_timeout 300s;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    return 301 https://$host$request_uri;
}
EOF

# 4. Enable site and reload Nginx
echo "[4/5] Enabling site and reloading Nginx..."
sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/rag
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx

# 5. Firewall: open 443/80, block direct access to port 8080
echo "[5/5] Configuring firewall..."
if command -v ufw &>/dev/null; then
    sudo ufw allow 443/tcp
    sudo ufw allow 80/tcp
    sudo ufw deny 8080/tcp
    echo "      UFW rules applied."
else
    echo "      UFW not found — skipping firewall config."
    echo "      Make sure port 8080 is not reachable from outside!"
fi

echo ""
echo "=== HTTPS setup complete ==="
echo ""
# Determine IP for convenience
IP=$(hostname -I | awk '{print $1}')
echo "  App is now available at: https://$IP"
echo ""
echo "  Note: Your browser will show a certificate warning the first time."
echo "  This is expected for self-signed certificates — click 'Advanced' and proceed."
echo ""
