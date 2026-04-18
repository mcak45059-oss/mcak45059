# Apex BTC Spot Agent

Automated BTC/USDT trading bot for Binance Spot.
Strategy: **limit-buy a dip → limit-sell a target → market stop-loss exit**.

> **Disclaimer**: trading crypto involves substantial risk of loss. Use at your own risk. Test in `DRY_RUN` and `TESTNET` modes before risking real funds. The author is not responsible for any losses.

---

## Features

- **3 safety modes**: `DRY_RUN` (no orders), `TESTNET` (Binance sandbox), `LIVE`.
- State machine survives restarts (`btc_agent_state.json`).
- Configurable via `.env` — no code edits needed.
- Optional Telegram alerts.
- Stop-loss + drift cancel + timeout cancel.
- Decimal-only math (no float errors).
- Graceful shutdown on `SIGINT`/`SIGTERM`.
- Three deploy options: shell, Docker, systemd.

---

## Quick start

### 1. Get API keys

| Mode | URL | What to enable |
|------|-----|----------------|
| **Testnet** (recommended first) | https://testnet.binance.vision/ | Spot trading |
| **Live** | https://www.binance.com/en/my/settings/api-management | "Enable Spot Trading" only. **Disable withdrawals.** Restrict to your IP. |

### 2. Install

```bash
git clone https://github.com/mcak45059-oss/mcak45059.git
cd mcak45059
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — paste your API keys
```

### 3. Test in 3 stages

**Stage A — DRY_RUN** (no real orders, just logs decisions):

```bash
# .env
DRY_RUN=true
BINANCE_TESTNET=false
```
```bash
./run.sh
```

**Stage B — TESTNET** (free fake money, real Binance API):

```bash
# .env
DRY_RUN=false
BINANCE_TESTNET=true
TRADE_USDT=11
```

**Stage C — LIVE, small size**:

```bash
# .env
DRY_RUN=false
BINANCE_TESTNET=false
TRADE_USDT=11   # just above the 10 USDT minimum
```

Watch one full cycle: `BUY placed → BUY filled → SELL placed → SELL filled`. Then scale up by raising `TRADE_USDT`.

---

## Strategy parameters

| Variable | Default | Meaning |
|----------|---------|---------|
| `TRADE_USDT` | 20 | USDT per cycle (must be >= 10) |
| `DIP_PERCENT` | 1.5 | Buy this far below market |
| `TARGET_PERCENT` | 2.0 | Sell this far above buy price |
| `STOP_PERCENT` | 3.0 | Market sell if price drops this far below buy |
| `MAX_WAIT_HOURS` | 24 | Cancel unfilled buy after this long |
| `DRIFT_CANCEL` | 2.0 | Cancel buy if spot rises this much above limit |
| `CHECK_INTERVAL` | 60 | Seconds between cycles |
| `FEE_RATE` | 0.001 | Binance taker fee, used in PnL math |

---

## Deployment

### A) Plain shell (laptop / VPS)

```bash
./run.sh
# or under tmux/screen so it survives logout:
tmux new -s apex './run.sh'
```

### B) Docker

```bash
cp .env.example .env  # fill in keys
docker compose up -d --build
docker compose logs -f
```

State persists in `./data/`.

### C) systemd (Linux server)

```bash
sudo useradd -r -s /bin/false apex
sudo mkdir -p /opt/apex-btc-agent
sudo cp -r . /opt/apex-btc-agent/
sudo chown -R apex:apex /opt/apex-btc-agent
sudo -u apex python3 -m venv /opt/apex-btc-agent/.venv
sudo -u apex /opt/apex-btc-agent/.venv/bin/pip install -r /opt/apex-btc-agent/requirements.txt
sudo cp apex-btc-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now apex-btc-agent
sudo journalctl -u apex-btc-agent -f
```

---

## State machine

```
[IDLE] -> place limit buy @ price * (1 - DIP%)
              |
              v
[BUY OPEN] -> filled?  -> place limit sell @ buy * (1 + TARGET%)
            |- canceled / expired -> reset
            |- timeout or +DRIFT% -> cancel & reset
                          |
                          v
              [SELL OPEN] -> filled? -> log net PnL, reset
                          |- canceled / expired -> reset
                          |- price <= buy*(1-STOP%) -> cancel + market sell
```

---

## Telegram alerts (optional)

1. Talk to @BotFather -> `/newbot` -> copy token.
2. Talk to @userinfobot -> copy your chat ID.
3. Add to `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC...
   TELEGRAM_CHAT_ID=987654321
   ```
4. Send `/start` to your bot once so it can DM you.

---

## Security checklist

- [ ] `.env` is in `.gitignore` (already done) — never commit it.
- [ ] Binance API key has **withdrawals disabled**.
- [ ] Binance API key is **IP-restricted** to your server.
- [ ] Run as a **non-root user** (Docker image and systemd unit already do this).
- [ ] Server time synced (`sudo timedatectl set-ntp on`) — Binance rejects requests with skewed timestamps.
- [ ] First run is in `DRY_RUN`, second in `TESTNET`, third in `LIVE` with `TRADE_USDT=11`.

---

## Troubleshooting

| Symptom | Likely cause |
|--------|--------------|
| `Missing BINANCE_API_KEY` | `.env` not loaded — use `./run.sh` or `set -a; . .env; set +a` |
| `Filter failure: MIN_NOTIONAL` | `TRADE_USDT` < 10 |
| `Timestamp for this request is outside of the recvWindow` | Server clock drift — enable NTP |
| `Invalid API-key, IP, or permissions` | Check IP whitelist on Binance and that "Spot Trading" is enabled |
| Bot doesn't react to Ctrl-C immediately | It finishes the current cycle (<= 60s) then exits cleanly |

---

## Files

| File | Purpose |
|------|---------|
| `apex_btc_agent.py` | Main bot |
| `.env.example` | Config template |
| `requirements.txt` | Python deps |
| `run.sh` | Loads `.env` and runs the bot |
| `Dockerfile` | Container image |
| `docker-compose.yml` | One-command deploy |
| `apex-btc-agent.service` | systemd unit |
| `btc_agent_state.json` | Runtime state (auto-created, gitignored) |
