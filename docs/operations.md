# FitAi — Operations Guide

## VM Access

```bash
# Browser SSH (always works)
# Go to console.cloud.google.com → Compute Engine → VM instances → SSH button

# SSH details
VM: nutrition-bot
Project: finance-assistant-476706
Zone: us-central1-a
External IP: 34.46.12.202
```

---

## Prefect UI

The Prefect UI runs on the VM but is only accessible via SSH tunnel (not exposed to the internet).

**Open the UI:**
```bash
# On your Mac — creates a tunnel on localhost:4200
gcloud compute ssh nutrition-bot \
  --project=finance-assistant-476706 \
  --zone=us-central1-a \
  --tunnel-through-iap \
  -- -L 4200:localhost:4200 -N
```

Then open **http://localhost:4200** in your browser.

**What you can do in the UI:**
- View all scheduled flow runs (Deployments tab)
- Manually trigger a flow: Deployments → click deployment → Run
- Inspect logs for any flow run
- See flow run history and failures

**Scheduled flows (America/Los_Angeles):**

| Flow | Schedule | What it does |
|---|---|---|
| morning-report | 10:30am daily | Steps + sleep + weather → Haiku → Telegram |
| lunch-alert | 3:00pm daily | Alert if no breakfast/lunch logged |
| dinner-alert | 10:30pm daily | Alert if no dinner logged |
| daily-summary | 11:30pm daily | DailySummaryAgent → PatternDetectorAgent |
| semantic-extraction | 6:00pm Sunday | Extract facts from 90-day history |
| weekly-report | 8:00pm Sunday | WeeklyReportAgent → PatternDetectorAgent |

**Manually trigger a flow from the VM:**
```bash
cd /opt/nutrition-bot
PYTHONPATH=/opt/nutrition-bot /opt/nutrition-bot/venv/bin/prefect deployment run morning_report/morning-report
```

---

## Uptime Kuma

**URL:** http://34.46.12.202:3001

Monitors the bot heartbeat. The bot pings Uptime Kuma every 5 minutes. If no ping is received for 10 minutes, you get a Telegram alert.

**What to check:**
- `nutrition-bot` monitor should show **Up** (green)
- If it shows **Down**, the bot process has crashed — check with `sudo systemctl status nutrition-bot`

---

## Service Management

All services run on the VM via systemd.

```bash
# Check status
sudo systemctl status nutrition-bot
sudo systemctl status prefect-server
sudo systemctl status prefect-worker

# Restart bot after a code update
sudo systemctl restart nutrition-bot

# View live bot logs
sudo journalctl -u nutrition-bot -f

# View Prefect flow runner logs
sudo journalctl -u prefect-worker -f
```

---

## Deploying Code Updates

```bash
# On your Mac — push changes
git push

# On the VM — pull and restart
cd /opt/nutrition-bot
sudo git pull
sudo systemctl restart nutrition-bot
# If requirements.txt changed:
sudo /opt/nutrition-bot/venv/bin/pip install -r requirements.txt -q
sudo systemctl restart nutrition-bot prefect-worker
```

---

## Google Health API Token

The OAuth token is stored in diskcache and auto-refreshes. If it ever expires or becomes invalid:

```bash
# On your Mac — re-run the auth script
cd /Users/sahilkhandwala/Desktop/FitAi
python scripts/get_health_token.py \
  "716324459547-171vsoknvpc6cf2l036h7aglirmgt04i.apps.googleusercontent.com" \
  "<CLIENT_SECRET>"
# Follow prompts, sign in with skhandwala1@gmail.com
# Paste the printed command into the VM terminal
```

---

## Database

SQLite WAL mode at `/opt/nutrition-bot/nutrition.db`.

```bash
# Inspect on the VM
sqlite3 /opt/nutrition-bot/nutrition.db ".tables"
sqlite3 /opt/nutrition-bot/nutrition.db "SELECT * FROM meal_logs ORDER BY logged_at DESC LIMIT 5;"
```

---

## Monocle Traces

LangGraph traces are written to `/opt/nutrition-bot/logs/traces/` as JSON files.

```bash
# Download traces to Mac for inspection
gcloud compute scp "nutrition-bot:/opt/nutrition-bot/logs/traces/*.json" ~/Downloads/ \
  --project=finance-assistant-476706 --zone=us-central1-a --tunnel-through-iap
```
