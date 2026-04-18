"""
Apex BTC Spot Agent — v3 (production-ready)
Strategy: Limit buy at dip → limit sell at target → stop-loss exit
Exchange: Binance Spot (BTCUSDT) — supports live + testnet + dry-run
"""

import os
import json
import time
import signal
import logging
from decimal import Decimal
from pathlib import Path

import requests
from binance.client import Client
from binance.exceptions import BinanceAPIException

# ─── CONFIG (env vars) ──────────────────────────────────────

API_KEY    = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TG_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")   # optional
TG_CHAT    = os.getenv("TELEGRAM_CHAT_ID")     # optional

USE_TESTNET = os.getenv("BINANCE_TESTNET", "false").lower() == "true"
DRY_RUN     = os.getenv("DRY_RUN", "false").lower() == "true"

SYMBOL          = os.getenv("SYMBOL", "BTCUSDT")
TRADE_USDT      = Decimal(os.getenv("TRADE_USDT", "20"))
DIP_PERCENT     = Decimal(os.getenv("DIP_PERCENT", "1.5"))
TARGET_PERCENT  = Decimal(os.getenv("TARGET_PERCENT", "2.0"))
STOP_PERCENT    = Decimal(os.getenv("STOP_PERCENT", "3.0"))
MAX_WAIT_HOURS  = int(os.getenv("MAX_WAIT_HOURS", "24"))
CHECK_INTERVAL  = int(os.getenv("CHECK_INTERVAL", "60"))
DRIFT_CANCEL    = Decimal(os.getenv("DRIFT_CANCEL", "2.0"))   # cancel buy if spot rises X% above limit
FEE_RATE        = Decimal(os.getenv("FEE_RATE", "0.001"))     # 0.1% Binance taker fee

STATE_FILE = Path(os.getenv("STATE_FILE", "btc_agent_state.json"))

# ─── SETUP ──────────────────────────────────────────────────

if not API_KEY or not API_SECRET:
    raise SystemExit("Missing BINANCE_API_KEY / BINANCE_API_SECRET env vars.")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("apex")

mode_tag = "DRY-RUN" if DRY_RUN else ("TESTNET" if USE_TESTNET else "LIVE")
log.info(f"Mode: {mode_tag}  Symbol: {SYMBOL}  Trade size: {TRADE_USDT} USDT")

client = Client(API_KEY, API_SECRET, testnet=USE_TESTNET)

_shutdown = False
def _on_signal(signum, _frame):
    global _shutdown
    log.info(f"Signal {signum} received — shutting down after current cycle.")
    _shutdown = True
signal.signal(signal.SIGINT, _on_signal)
signal.signal(signal.SIGTERM, _on_signal)

# ─── HELPERS ────────────────────────────────────────────────

def notify(msg: str):
    log.info(msg)
    if not (TG_TOKEN and TG_CHAT):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": f"[{mode_tag}] Apex {SYMBOL}\n{msg}"},
            timeout=5,
        )
    except Exception as e:
        log.warning(f"Telegram failed: {e}")

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"buy_order_id": None, "sell_order_id": None, "buy_price": None, "buy_ts": None}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def get_filters() -> dict:
    info = client.get_symbol_info(SYMBOL)
    f = {x["filterType"]: x for x in info["filters"]}
    notional = f.get("NOTIONAL", f.get("MIN_NOTIONAL", {"minNotional": "10"}))
    return {
        "tick_size":    Decimal(f["PRICE_FILTER"]["tickSize"]),
        "step_size":    Decimal(f["LOT_SIZE"]["stepSize"]),
        "min_qty":      Decimal(f["LOT_SIZE"]["minQty"]),
        "min_notional": Decimal(notional["minNotional"]),
    }

def round_step(value: Decimal, step: Decimal) -> Decimal:
    return (value // step) * step

def fmt(d: Decimal) -> str:
    s = format(d.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"

# ─── MARKET / ACCOUNT ───────────────────────────────────────

def get_price() -> Decimal:
    return Decimal(client.get_symbol_ticker(symbol=SYMBOL)["price"])

def get_balance(asset: str) -> Decimal:
    return Decimal(client.get_asset_balance(asset=asset)["free"])

# ─── ORDER ACTIONS (dry-run aware) ──────────────────────────

def place_limit_buy(price: Decimal, usdt: Decimal, filters: dict) -> dict:
    price = round_step(price, filters["tick_size"])
    qty   = round_step(usdt / price, filters["step_size"])
    if qty < filters["min_qty"] or qty * price < filters["min_notional"]:
        raise ValueError(f"Order too small: qty={qty}, notional={qty*price}")

    if DRY_RUN:
        notify(f"[DRY] BUY would place @ {price} | qty {qty}")
        return {"orderId": f"dry-buy-{int(time.time())}", "price": fmt(price), "origQty": fmt(qty)}

    order = client.order_limit_buy(symbol=SYMBOL, quantity=fmt(qty), price=fmt(price))
    notify(f"BUY placed @ {price} | qty {qty} | id {order['orderId']}")
    return order

def place_limit_sell(price: Decimal, qty: Decimal, filters: dict) -> dict:
    price = round_step(price, filters["tick_size"])
    qty   = round_step(qty, filters["step_size"])

    if DRY_RUN:
        notify(f"[DRY] SELL would place @ {price} | qty {qty}")
        return {"orderId": f"dry-sell-{int(time.time())}", "price": fmt(price), "origQty": fmt(qty)}

    order = client.order_limit_sell(symbol=SYMBOL, quantity=fmt(qty), price=fmt(price))
    notify(f"SELL placed @ {price} | qty {qty} | id {order['orderId']}")
    return order

def market_sell(qty: Decimal, filters: dict) -> dict:
    qty = round_step(qty, filters["step_size"])
    if DRY_RUN:
        notify(f"[DRY] MARKET SELL (stop-loss) | qty {qty}")
        return {"orderId": f"dry-mkt-{int(time.time())}"}
    order = client.order_market_sell(symbol=SYMBOL, quantity=fmt(qty))
    notify(f"MARKET SELL (stop-loss) | qty {qty}")
    return order

def cancel_order(order_id):
    if DRY_RUN or str(order_id).startswith("dry-"):
        return
    client.cancel_order(symbol=SYMBOL, orderId=order_id)

def get_order(order_id) -> dict:
    """In DRY-RUN we synthesize a 'NEW' status so the loop keeps running harmlessly."""
    if DRY_RUN or str(order_id).startswith("dry-"):
        return {"status": "NEW", "executedQty": "0", "origQty": "0", "price": "0"}
    return client.get_order(symbol=SYMBOL, orderId=order_id)

# ─── MAIN LOOP ──────────────────────────────────────────────

def run():
    notify(f"=== Apex BTC Agent started ({mode_tag}) ===")
    filters = get_filters()
    log.info(f"Filters: {filters}")
    state = load_state()

    while not _shutdown:
        try:
            price = get_price()
            usdt  = get_balance("USDT")
            base  = SYMBOL.replace("USDT", "")
            btc   = get_balance(base)
            log.info(f"{SYMBOL} {price} | USDT {usdt:.2f} | {base} {btc:.6f}")

            # STATE 1: idle → place buy
            if not state["buy_order_id"] and not state["sell_order_id"]:
                if usdt >= TRADE_USDT or DRY_RUN:
                    target = price * (Decimal(1) - DIP_PERCENT / 100)
                    order  = place_limit_buy(target, TRADE_USDT, filters)
                    state.update(
                        buy_order_id=order["orderId"],
                        buy_price=str(round_step(target, filters["tick_size"])),
                        buy_ts=int(time.time()),
                    )
                    save_state(state)
                else:
                    log.info(f"Insufficient USDT ({usdt} < {TRADE_USDT}) — waiting.")

            # STATE 2: buy open → check fill / timeout / drift
            elif state["buy_order_id"]:
                o = get_order(state["buy_order_id"])
                buy_price = Decimal(state["buy_price"])

                if o["status"] == "FILLED":
                    filled = Decimal(o["executedQty"])
                    notify(f"BUY filled @ {buy_price} | qty {filled}")
                    target = buy_price * (Decimal(1) + TARGET_PERCENT / 100)
                    sell = place_limit_sell(target, filled, filters)
                    state.update(buy_order_id=None, sell_order_id=sell["orderId"])
                    save_state(state)

                elif o["status"] in ("CANCELED", "EXPIRED", "REJECTED"):
                    notify(f"Buy {o['status']} — resetting.")
                    state.update(buy_order_id=None, buy_price=None, buy_ts=None)
                    save_state(state)

                else:
                    age_h = (time.time() - state["buy_ts"]) / 3600
                    drift_pct = (price - buy_price) / buy_price * 100

                    if age_h > MAX_WAIT_HOURS or drift_pct > DRIFT_CANCEL:
                        reason = "timeout" if age_h > MAX_WAIT_HOURS else f"drift +{drift_pct:.2f}%"
                        log.info(f"Cancel buy ({reason}) — will re-place next cycle.")
                        try:
                            cancel_order(state["buy_order_id"])
                        except BinanceAPIException as e:
                            log.warning(f"Cancel failed: {e}")
                        state.update(buy_order_id=None, buy_price=None, buy_ts=None)
                        save_state(state)

            # STATE 3: sell open → check fill / stop-loss
            elif state["sell_order_id"]:
                o = get_order(state["sell_order_id"])
                buy_price = Decimal(state["buy_price"])

                if o["status"] == "FILLED":
                    sell_px  = Decimal(o["price"])
                    qty      = Decimal(o["executedQty"])
                    gross    = (sell_px - buy_price) * qty
                    fees     = (sell_px + buy_price) * qty * FEE_RATE
                    pnl      = gross - fees
                    notify(f"SELL filled @ {sell_px} | gross {gross:.4f} | fees {fees:.4f} | net {pnl:.4f} USDT")
                    state.update(sell_order_id=None, buy_price=None, buy_ts=None)
                    save_state(state)

                elif o["status"] in ("CANCELED", "EXPIRED", "REJECTED"):
                    notify(f"Sell {o['status']} — resetting.")
                    state.update(sell_order_id=None)
                    save_state(state)

                else:
                    stop_px = buy_price * (Decimal(1) - STOP_PERCENT / 100)
                    if price <= stop_px:
                        notify(f"STOP-LOSS hit @ {price} (buy was {buy_price})")
                        try:
                            cancel_order(state["sell_order_id"])
                            remaining = Decimal(o["origQty"]) - Decimal(o["executedQty"])
                            if remaining > 0:
                                market_sell(remaining, filters)
                        except BinanceAPIException as e:
                            log.error(f"Stop-loss failed: {e}")
                        state.update(sell_order_id=None, buy_price=None, buy_ts=None)
                        save_state(state)

        except BinanceAPIException as e:
            log.error(f"Binance error: {e}")
        except Exception as e:
            log.exception(f"Unexpected: {e}")

        # Interruptible sleep
        for _ in range(CHECK_INTERVAL):
            if _shutdown:
                break
            time.sleep(1)

    notify("=== Apex BTC Agent stopped ===")


if __name__ == "__main__":
    run()
