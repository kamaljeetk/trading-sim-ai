# Deploying Trading Sim AI on AWS EC2

## Recommended Instance
| Setting | Value |
|---|---|
| AMI | Ubuntu 22.04 LTS (us-east-1) |
| Instance type | t3.small (2 vCPU, 2 GB RAM) or t3.medium for comfort |
| Storage | 20 GB gp3 root volume |
| Security group | SSH (22), HTTP (80), Custom TCP 8501 (optional) |

## Quick Start

### Step 1 — Launch EC2 instance
1. Go to AWS Console → EC2 → Launch Instance
2. Choose **Ubuntu 22.04 LTS**
3. Select **t3.small** (or t3.medium)
4. Create or select a key pair (you'll need the `.pem` file to SSH in)
5. In Security Group, allow inbound:
   - **SSH** (port 22) — your IP only
   - **HTTP** (port 80) — Anywhere (for the dashboard)
   - Optional: **Custom TCP 8501** — Anywhere (to access Streamlit directly)
6. Launch

### Step 2 — SSH into the instance
```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>
```

### Step 3 — Push your code to GitHub (do this on your Mac first)
```bash
# On your Mac, in the project directory:
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/trading-sim-ai.git
git push -u origin main
```

> **Alternative (no GitHub):** Use `scp` to copy files directly:
> ```bash
> scp -i your-key.pem -r /Users/kamal/Documents/trading-sim-ai ubuntu@<EC2_IP>:/opt/
> ```

### Step 4 — Run the setup script
```bash
# On EC2:
git clone https://github.com/YOUR_USERNAME/trading-sim-ai.git /opt/trading-sim-ai
cd /opt/trading-sim-ai/deploy

# Edit the REPO_URL in setup_ec2.sh first:
nano setup_ec2.sh   # change REPO_URL at the top

chmod +x setup_ec2.sh
sudo ./setup_ec2.sh
```

The script will:
- Install Python 3.12, PostgreSQL, Nginx
- Set up the database automatically
- Install the Streamlit dashboard as a systemd service
- Set up cron jobs for daily trading runs
- Configure Nginx on port 80

### Step 5 — Add your API keys
```bash
nano /opt/trading-sim-ai/.env
```

Fill in all values (the DB credentials are already auto-filled by the setup script):
```
OPENAI_API_KEY=sk-...
HUGGINGFACEHUB_API_TOKEN=hf_...
HF_MODEL=mistralai/Mistral-7B-Instruct-v0.2
OPENAI_MODEL=gpt-3.5-turbo
PINECONE_API_KEY=pcsk_...
POLYGON_API_KEY=...        # optional; needed for live news
```

### Step 6 — Start the dashboard
```bash
sudo systemctl start trading-sim-dashboard
sudo systemctl status trading-sim-dashboard
```

Open your browser: `http://<EC2_PUBLIC_IP>`

---

## Daily Operations

### Manual run
```bash
cd /opt/trading-sim-ai
source venv/bin/activate

# Morning allocation (agents 1–5)
python main.py --run-daily

# EOD evaluation (agent 6)
python main.py --evaluate-only

# Full day simulation
python main.py --run-daily --evaluate

# View status
python main.py --status
```

### Automated cron schedule
The setup script installs two cron jobs in `/etc/cron.d/trading-sim-daily`:

| Time | Command |
|---|---|
| 9:35 AM ET (Mon–Fri) | `python main.py --run-daily` |
| 4:05 PM ET (Mon–Fri) | `python main.py --evaluate-only` |

View cron logs:
```bash
tail -f /var/log/trading-sim-daily.log
tail -f /var/log/trading-sim-eod.log
```

---

## Service Management

```bash
# Dashboard
sudo systemctl status  trading-sim-dashboard
sudo systemctl start   trading-sim-dashboard
sudo systemctl stop    trading-sim-dashboard
sudo systemctl restart trading-sim-dashboard

# Live logs
sudo journalctl -u trading-sim-dashboard -f

# Nginx
sudo systemctl status nginx
sudo nginx -t            # test config
sudo systemctl reload nginx
```

---

## Updating the Application

```bash
cd /opt/trading-sim-ai
git pull origin main

# Reinstall dependencies if requirements.txt changed
source venv/bin/activate
pip install -r requirements.txt

# Restart the dashboard
sudo systemctl restart trading-sim-dashboard
```

---

## Database Access

```bash
# Connect to the database
sudo -u postgres psql -d trading_sim

# Useful queries
\dt                          -- list tables
SELECT * FROM trading_days ORDER BY trade_date DESC LIMIT 5;
SELECT * FROM daily_portfolio_performance ORDER BY perf_id DESC LIMIT 5;
```

---

## Costs

| Resource | Monthly est. |
|---|---|
| t3.small EC2 | ~$15/mo |
| 20 GB gp3 storage | ~$1.60/mo |
| Data transfer | ~$1–2/mo |
| **Total** | **~$18–20/mo** |

> Use a **Reserved Instance** (1-year) to cut EC2 cost to ~$8/mo.

---

## Troubleshooting

**Dashboard not starting:**
```bash
sudo journalctl -u trading-sim-dashboard -n 50
# Common issue: .env not filled in, or PostgreSQL not running
```

**PostgreSQL not running:**
```bash
sudo systemctl start postgresql
sudo systemctl status postgresql
```

**Port 8501 not accessible directly:**
Access via Nginx on port 80 instead. If you want direct Streamlit access, add inbound rule for port 8501 in your EC2 security group.

**"relation does not exist" DB error:**
```bash
cd /opt/trading-sim-ai
sudo -u postgres psql -d trading_sim -f db/schema.sql
```

**HuggingFace API errors:**
The free tier of HF Inference API has rate limits. If agents fail, check your token and consider upgrading to HF PRO ($9/mo) for higher limits.
