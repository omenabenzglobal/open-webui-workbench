#!/usr/bin/env bash
set -e

echo "=== [OMENA WORKBENCH] STARTING REPOSITORY-DRIVEN DEPLOYMENT ==="

INSTALL_DIR="/home/ubuntu/open-webui-workbench"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure system dependencies
if ! command -v uv &>/dev/null; then
    echo "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Prepare directories
mkdir -p "$INSTALL_DIR/data"
mkdir -p "$INSTALL_DIR/workspace"

# Setup Python 3.11 virtual environment
echo "Setting up Python virtual environment..."
cd "$REPO_DIR"
uv venv .venv --python 3.11
uv pip install -r backend/requirements.txt

# Ensure production .env exists
if [ ! -f .env ]; then
    echo "Creating production .env..."
    SECRET_KEY=$(openssl rand -hex 32)
    cat > .env << EOF
PORT=8080
HOST=127.0.0.1
DATA_DIR=$INSTALL_DIR/data
FRONTEND_BUILD_DIR=$REPO_DIR/build
WEBUI_SECRET_KEY=$SECRET_KEY
EXECUTION_MODE=AUTONOMOUS
EOF
    chmod 600 .env
fi

# Configure and start systemd service
echo "Configuring systemd service..."
sudo tee /etc/systemd/system/open-webui-workbench.service > /dev/null << EOF
[Unit]
Description=Open WebUI Autonomous Agent Workbench
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$REPO_DIR
EnvironmentFile=$REPO_DIR/.env
ExecStart=$REPO_DIR/.venv/bin/python -m uvicorn open_webui.main:app --host 127.0.0.1 --port 8080 --app-dir backend
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now open-webui-workbench

# Configure Caddy reverse proxy
echo "Configuring Caddy reverse proxy..."
sudo tee /etc/caddy/Caddyfile > /dev/null << 'EOF'
omenabenz.online, www.omenabenz.online {
    reverse_proxy 127.0.0.1:8080 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }
}
EOF

sudo systemctl reload caddy

# Health check
sleep 5
echo "Verifying local service health..."
curl -s http://127.0.0.1:8080/health || echo "Service starting up..."
echo ""
echo "=== [OMENA WORKBENCH] DEPLOYMENT COMPLETE ==="
