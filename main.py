# =========================
# main.py
# =========================

from kiteconnect import KiteConnect
from datetime import datetime, timedelta
import pytz, time, requests, os, sys

# ================= CONFIG =================
API_KEY = os.getenv("API_KEY")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

NIFTY_TOKEN = 256265

STOP_PCT   = 0.12    # stop loss %
TARGET_PCT = 0.24    # target %

tz = pytz.timezone("Asia/Kolkata")
# =========================================

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

in_trade = False
trade_side = None      # "CE" or "PE"
entry_price = None

last_run_minute = None
last_action_sent = None
last_heartbeat_hour = None


def now_str():
    return datetime.now(tz).strftime("%H:%M")


def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=5
        )
    except:
        pass


def send_if_new(msg):
    global last_action_sent
    if msg != last_action_sent:
        print(msg)
        send_telegram(msg)
        last_action_sent = msg


def heartbeat(now):
    global last_heartbeat_hour
    if now.minute == 0 and now.hour != last_heartbeat_hour:
        msg = f"💓 HEARTBEAT | Bot alive | {now.strftime('%H:%M:%S')}"
        print(msg)
        send_telegram(msg)
        last_heartbeat_hour = now.hour


print("SYSTEM STARTED")
send_telegram("SYSTEM STARTED – WAITING FOR MARKET OPEN")

# ================= MAIN LOOP =================
while True:
    now = datetime.now(tz)

    # -------- Before market --------
    if now.hour < 9 or (now.hour == 9 and now.minute < 15):
        time.sleep(30)
        continue

    # -------- After market → STOP --------
    if now.hour > 15 or (now.hour == 15 and now.minute >= 15):
        send_telegram("MARKET CLOSED – SERVICE STOPPED")
        print("MARKET CLOSED – EXITING")
        break

    # -------- Hourly heartbeat --------
    heartbeat(now)

    # -------- Run only once per 5-min candle --------
    if now.minute % 5 != 0 or now.minute == last_run_minute:
        time.sleep(5)
        continue

    last_run_minute = now.minute

    # -------- Fetch candles --------
    try:
        candles = kite.historical_data(
            NIFTY_TOKEN,
            now - timedelta(days=3),
            now,
            "5minute"
        )
    except:
        time.sleep(10)
        continue

    if len(candles) < 15:
        time.sleep(10)
        continue

    c0, c1, c2 = candles[-2], candles[-3], candles[-4]
    last_10 = candles[-12:-2]

    nifty = round(c0["close"], 2)

    # ================= ENTRY =================
    if not in_trade:
        ce_green = (
            c0["close"] > c0["open"] and
            c1["close"] > c1["open"] and
            c2["close"] > c2["open"]
        )
        pe_red = (
            c0["close"] < c0["open"] and
            c1["close"] < c1["open"] and
            c2["close"] < c2["open"]
        )

        ce_net = (c0["close"] - c2["open"]) / c2["open"] * 100
        pe_net = (c2["open"] - c0["close"]) / c2["open"] * 100

        latest_range = c0["high"] - c0["low"]
        avg_range = sum(c["high"] - c["low"] for c in last_10) / len(last_10)

        if ce_green and ce_net >= 0.15 and latest_range >= 0.7 * avg_range:
            in_trade = True
            trade_side = "CE"
            entry_price = nifty
            send_if_new(f"{now_str()} | BUY CE | NIFTY {nifty}")

        elif pe_red and pe_net >= 0.15 and latest_range >= 0.7 * avg_range:
            in_trade = True
            trade_side = "PE"
            entry_price = nifty
            send_if_new(f"{now_str()} | BUY PE | NIFTY {nifty}")

    # ================= HOLD / EXIT =================
    else:
        if trade_side == "CE":
            move = (nifty - entry_price) / entry_price * 100
        else:
            move = (entry_price - nifty) / entry_price * 100

        if move <= -STOP_PCT:
            send_if_new(f"{now_str()} | SELL {trade_side} | STOP HIT | NIFTY {nifty}")
            in_trade = False
            trade_side = None
            entry_price = None

        elif move >= TARGET_PCT:
            send_if_new(f"{now_str()} | SELL {trade_side} | TARGET HIT | NIFTY {nifty}")
            in_trade = False
            trade_side = None
            entry_price = None

        else:
            send_if_new(f"{now_str()} | HOLD {trade_side} | NIFTY {nifty}")

    time.sleep(5)

# ================= CLEAN EXIT =================
send_telegram("BOT SHUTDOWN COMPLETE")
sys.exit(0)
