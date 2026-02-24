#!/usr/bin/env bash
# =============================================================================
# EC2 Setup Script — Agentic Trading Simulation System
# =============================================================================
# Tested on: Ubuntu 22.04 LTS (t3.small or larger)
#
# Usage:
#   chmod +x setup_ec2.sh
#   ./setup_ec2.sh
#
# What this script does:
#   1. Installs system dependencies (Python 3.12, PostgreSQL, Nginx)
#   2. Clones the project repository
#   3. Creates a Python virtual environment and installs requirements
#   4. Sets up the PostgreSQL database
#   5. Installs the Streamlit dashboard as a systemd service
#   6. Installs a cron job for daily trading runs at 9:35 AM ET
#   7. Configures Nginx as a reverse proxy on port 80
# =============================================================================

set -euo pipefail

# ---------- Configuration (edit before running) ----------
REPO_URL="https://github.com/YOUR_USERNAME/trading-sim-ai.git"   # ← change this
APP_DIR="/opt/trading-sim-ai"
APP_USER="ubuntu"           # EC2 default user; change to "ec2-user" for Amazon Linux
DB_NAME="trading_sim"
DB_USER="trading_sim_user"
DB_PASSWORD="$(openssl rand -hex 16)"   # auto-generated; saved to deploy/.db_password
PYTHON_VERSION="3.12"
# ---------------------------------------------------------

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

log()  { echo -e "${GREEN}[SETUP]${RESET} $*"; }
warn() { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
fail() { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }

# ---------- 1. System Dependencies ----------
log "Updating system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    git curl wget gnupg2 build-essential \
    software-properties-common ca-certificates \
    nginx postgresql postgresql-contrib \
    python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev \
    python3-pip libpq-dev

log "Python version: $(python${PYTHON_VERSION} --version)"
log "PostgreSQL version: $(psql --version)"

# ---------- 2. Clone / Update Repo ----------
if [ -d "$APP_DIR/.git" ]; then
    log "Repository already exists — pulling latest..."
    sudo -u "$APP_USER" git -C "$APP_DIR" pull
else
    log "Cloning repository to $APP_DIR..."
    if [ "$REPO_URL" = "https://github.com/YOUR_USERNAME/trading-sim-ai.git" ]; then
        warn "REPO_URL not set. Skipping clone — copy files manually to $APP_DIR."
        sudo mkdir -p "$APP_DIR"
        sudo chown "$APP_USER:$APP_USER" "$APP_DIR"
    else
        sudo git clone "$REPO_URL" "$APP_DIR"
        sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"
    fi
fi

# ---------- 3. Python Virtual Environment ----------
log "Creating Python virtual environment..."
sudo -u "$APP_USER" python${PYTHON_VERSION} -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip wheel setuptools -q
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q
log "Python dependencies installed."

# ---------- 4. PostgreSQL Setup ----------
log "Setting up PostgreSQL database..."

# Start PostgreSQL if not running
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Create DB user and database (idempotent)
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null || true

# Save generated password
echo "$DB_PASSWORD" | sudo tee "$APP_DIR/deploy/.db_password" > /dev/null
sudo chmod 600 "$APP_DIR/deploy/.db_password"
log "DB credentials saved to $APP_DIR/deploy/.db_password"

# Apply schema
if [ -f "$APP_DIR/db/schema.sql" ]; then
    sudo -u postgres psql -d "$DB_NAME" -f "$APP_DIR/db/schema.sql" 2>/dev/null || warn "Schema may already exist — skipping."
    log "Database schema applied."
fi

# ---------- 5. Environment File ----------
ENV_FILE="$APP_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    log "Creating .env from .env.example..."
    sudo -u "$APP_USER" cp "$APP_DIR/.env.example" "$ENV_FILE"
    sudo chmod 600 "$ENV_FILE"

    # Inject generated DB credentials
    sudo sed -i "s|DB_HOST=.*|DB_HOST=localhost|"           "$ENV_FILE"
    sudo sed -i "s|DB_NAME=.*|DB_NAME=$DB_NAME|"             "$ENV_FILE"
    sudo sed -i "s|DB_USER=.*|DB_USER=$DB_USER|"             "$ENV_FILE"
    sudo sed -i "s|DB_PASSWORD=.*|DB_PASSWORD=$DB_PASSWORD|" "$ENV_FILE"

    echo ""
    warn "===================================================================="
    warn "  .env created at $ENV_FILE"
    warn "  You MUST fill in these values before running the application:"
    warn ""
    warn "    OPENAI_API_KEY=sk-..."
    warn "    HUGGINGFACEHUB_API_TOKEN=hf_..."
    warn "    PINECONE_API_KEY=pcsk_..."
    warn "    POLYGON_API_KEY=..."
    warn "    HF_MODEL=mistralai/Mistral-7B-Instruct-v0.2"
    warn "    OPENAI_MODEL=gpt-3.5-turbo"
    warn "===================================================================="
    echo ""
else
    log ".env already exists — skipping creation."
fi

# ---------- 6. Streamlit Config ----------
log "Ensuring .streamlit/config.toml exists..."
sudo -u "$APP_USER" mkdir -p "$APP_DIR/.streamlit"
if [ ! -f "$APP_DIR/.streamlit/config.toml" ]; then
sudo -u "$APP_USER" tee "$APP_DIR/.streamlit/config.toml" > /dev/null << 'TOML'
[theme]
base = "dark"
backgroundColor = "#0E1117"
secondaryBackgroundColor = "#1A1F2E"
textColor = "#FAFAFA"
primaryColor = "#00D4AA"

[server]
headless = true
port = 8501
enableCORS = false
enableXsrfProtection = false
TOML
fi

# ---------- 7. Systemd Service (Streamlit dashboard) ----------
log "Installing systemd service for Streamlit dashboard..."
sudo tee /etc/systemd/system/trading-sim-dashboard.service > /dev/null << EOF
[Unit]
Description=Trading Sim AI — Streamlit Dashboard
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/streamlit run dashboard.py --server.port=8501 --server.headless=true
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=trading-sim-dashboard

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable trading-sim-dashboard
log "Dashboard service installed. Start with: sudo systemctl start trading-sim-dashboard"

# ---------- 8. Cron Job (daily run) ----------
log "Installing cron job for daily trading run (9:35 AM ET)..."

# 9:35 AM ET = 14:35 UTC (EST) or 13:35 UTC (EDT)
# Using 14:35 UTC as conservative default (covers EST)
CRON_LINE="35 14 * * 1-5  $APP_USER  cd $APP_DIR && $APP_DIR/venv/bin/python main.py --run-daily >> /var/log/trading-sim-daily.log 2>&1"
EOD_LINE="05 21 * * 1-5  $APP_USER  cd $APP_DIR && $APP_DIR/venv/bin/python main.py --evaluate-only >> /var/log/trading-sim-eod.log 2>&1"

echo "$CRON_LINE"  | sudo tee    /etc/cron.d/trading-sim-daily > /dev/null
echo "$EOD_LINE"   | sudo tee -a /etc/cron.d/trading-sim-daily > /dev/null
sudo chmod 644 /etc/cron.d/trading-sim-daily
log "Cron job installed: daily 9:35 AM ET (--run-daily), 4:05 PM ET (--evaluate-only)"

# ---------- 9. Nginx Reverse Proxy ----------
log "Configuring Nginx reverse proxy on port 80..."
sudo tee /etc/nginx/sites-available/trading-sim > /dev/null << 'NGINX'
server {
    listen 80;
    server_name _;   # Replace _ with your domain or EC2 public IP

    location / {
        proxy_pass         http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/trading-sim /etc/nginx/sites-enabled/trading-sim
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl enable nginx
log "Nginx configured: port 80 → localhost:8501"

# ---------- 10. Log rotation ----------
sudo tee /etc/logrotate.d/trading-sim > /dev/null << 'LOGROTATE'
/var/log/trading-sim-daily.log /var/log/trading-sim-eod.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
}
LOGROTATE

# ---------- Done ----------
echo ""
echo -e "${BOLD}${GREEN}======================================================${RESET}"
echo -e "${BOLD}${GREEN}  Setup complete!${RESET}"
echo -e "${BOLD}${GREEN}======================================================${RESET}"
echo ""
echo "  Next steps:"
echo "  1. Edit API keys:   nano $APP_DIR/.env"
echo "  2. Start dashboard: sudo systemctl start trading-sim-dashboard"
echo "  3. Check status:    sudo systemctl status trading-sim-dashboard"
echo "  4. View logs:       sudo journalctl -u trading-sim-dashboard -f"
echo "  5. Access at:       http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo '<your-ec2-ip>')"
echo ""
echo "  Daily run logs:     /var/log/trading-sim-daily.log"
echo "  EOD eval logs:      /var/log/trading-sim-eod.log"
echo "  DB password:        $APP_DIR/deploy/.db_password"
echo ""
