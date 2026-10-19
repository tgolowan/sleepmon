import logging
import time

import requests

import config
import reports
import store

log = logging.getLogger("telegram")

HELP = (
    "<b>Sleep monitor</b>\n"
    "/now – current CO₂, temperature, humidity\n"
    "/night – last night's summary + chart\n"
    "/chart [hours] – CO₂ chart, default 12 h\n"
    "/status – sensor & alert status\n"
    "/alerts on|off – enable or mute alerts"
)

COMMANDS = [
    ("now", "Current CO₂, temperature, humidity"),
    ("night", "Last night's summary and chart"),
    ("chart", "CO₂ chart (optional: hours)"),
    ("status", "Sensor and alert status"),
    ("alerts", "on / off"),
    ("help", "List commands"),
]


def enabled():
    return bool(config.TELEGRAM_BOT_TOKEN)


def _api(method, **kwargs):
    url = f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_BOT_TOKEN}/{method}"
    r = requests.post(url, timeout=30, **kwargs)
    if not r.ok:
        log.warning("Telegram %s failed: %s %s", method, r.status_code, r.text[:200])
    return r


def send_message(text, chat_id=None):
    chat_id = chat_id or config.TELEGRAM_CHAT_ID
    if not (enabled() and chat_id):
        return
    _api("sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


def send_photo(png, caption, chat_id=None):
    chat_id = chat_id or config.TELEGRAM_CHAT_ID
    if not (enabled() and chat_id):
        return
    if png is None:
        send_message(caption + "\n\n(no data to chart)", chat_id)
        return
    _api(
        "sendPhoto",
        data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
        files={"photo": ("co2.png", png, "image/png")},
    )


def alerts_enabled():
    return store.get_setting("alerts", "on") == "on"


def setup_webhook():
    if not (enabled() and config.PUBLIC_URL):
        log.info("Telegram webhook not configured (missing token or public URL)")
        return
    _api(
        "setWebhook",
        json={
            "url": f"{config.PUBLIC_URL}/telegram/webhook",
            "secret_token": config.TELEGRAM_WEBHOOK_SECRET,
            "allowed_updates": ["message"],
        },
    )
    _api("setMyCommands", json={"commands": [{"command": c, "description": d} for c, d in COMMANDS]})
    log.info("Telegram webhook set to %s/telegram/webhook", config.PUBLIC_URL)


def handle_update(update):
    msg = update.get("message") or {}
    text = (msg.get("text") or "").strip()
    chat_id = str((msg.get("chat") or {}).get("id", ""))
    if not text or not chat_id:
        return

    if chat_id != str(config.TELEGRAM_CHAT_ID):
        send_message(
            f"This bot is private.\nYour chat ID is <code>{chat_id}</code> – "
            "set it as TELEGRAM_CHAT_ID on Railway to use the bot.",
            chat_id,
        )
        return

    command, *args = text.split()
    command = command.split("@")[0].lower()

    if command in ("/start", "/help"):
        send_message(HELP)
    elif command == "/now":
        send_message(reports.now_text())
    elif command == "/night":
        start, end = reports.night_bounds()
        send_photo(reports.chart_png(start, end, "Last night"), reports.summary_text(start, end, "🌙 Last night"))
    elif command == "/chart":
        try:
            hours = max(1, min(int(args[0]), 24 * 14)) if args else 12
        except ValueError:
            hours = 12
        end = int(time.time())
        start = end - hours * 3600
        send_photo(
            reports.chart_png(start, end, f"Last {hours} h"),
            reports.summary_text(start, end, f"📊 Last {hours} h"),
        )
    elif command == "/status":
        latest = store.latest()
        age = f"{(time.time() - latest['ts']) / 60:.0f} min ago" if latest else "never"
        send_message(
            f"📡 Last reading: {age}\n"
            f"🔔 Alerts: {'on' if alerts_enabled() else 'off'}\n"
            f"⚠️ CO₂ alert above {config.CO2_ALERT_PPM} ppm "
            f"(avg over {config.CO2_ALERT_WINDOW_MIN} min)\n"
            f"📴 Offline alert after {config.OFFLINE_ALERT_MIN} min\n"
            f"☀️ Morning report at {config.MORNING_REPORT_TIME}"
        )
    elif command == "/alerts":
        if args and args[0].lower() in ("on", "off"):
            store.set_setting("alerts", args[0].lower())
        send_message(f"🔔 Alerts are {'on' if alerts_enabled() else 'off'}.")
    else:
        send_message(HELP)
