"""Background checks: high CO₂, Pi/sensor offline, daily morning report."""

import logging
import threading
import time
from datetime import datetime

import config
import reports
import store
import telegram_bot

log = logging.getLogger("alerts")
CHECK_INTERVAL_S = 60


def _check_offline(muted):
    latest = store.latest()
    if not latest:
        return
    age_min = (time.time() - latest["ts"]) / 60
    was_offline = store.get_setting("offline_alerted") == "1"
    if age_min > config.OFFLINE_ALERT_MIN and not was_offline:
        store.set_setting("offline_alerted", "1")
        if not muted:
            telegram_bot.send_message(
                f"📴 No data for {age_min:.0f} min.\nThe Pi is offline or the sensor stopped working."
            )
    elif age_min <= config.OFFLINE_ALERT_MIN and was_offline:
        store.set_setting("offline_alerted", "0")
        if not muted:
            telegram_bot.send_message("✅ Data is coming in again.\n\n" + reports.now_text())


def _check_co2(muted):
    avg = store.avg_co2_since(int(time.time()) - config.CO2_ALERT_WINDOW_MIN * 60)
    if avg is None:
        return
    was_high = store.get_setting("co2_alerted") == "1"
    if avg > config.CO2_ALERT_PPM and not was_high:
        store.set_setting("co2_alerted", "1")
        if not muted:
            telegram_bot.send_message(
                f"🔴 CO₂ is high: <b>{avg:.0f} ppm</b> "
                f"(avg over {config.CO2_ALERT_WINDOW_MIN} min).\nOpen a window 🪟"
            )
    elif avg < config.CO2_ALERT_PPM - config.CO2_ALERT_HYSTERESIS_PPM and was_high:
        store.set_setting("co2_alerted", "0")
        if not muted:
            telegram_bot.send_message(f"🟢 CO₂ back to <b>{avg:.0f} ppm</b>.")


def _check_morning_report():
    now = datetime.now(config.TZ)
    hour, minute = (int(x) for x in config.MORNING_REPORT_TIME.split(":"))
    today = now.date().isoformat()
    if (now.hour, now.minute) < (hour, minute) or store.get_setting("morning_report_date") == today:
        return
    store.set_setting("morning_report_date", today)
    start, end = reports.night_bounds(now)
    if not store.stats(start, end)["samples"]:
        return
    telegram_bot.send_photo(
        reports.chart_png(start, end, "Last night"),
        reports.summary_text(start, end, "☀️ Good morning – last night's air"),
    )


def _loop():
    while True:
        try:
            muted = not telegram_bot.alerts_enabled()
            _check_offline(muted)
            _check_co2(muted)
            _check_morning_report()
        except Exception:
            log.exception("alert check failed")
        time.sleep(CHECK_INTERVAL_S)


def start():
    if not telegram_bot.enabled():
        log.info("Telegram not configured; alerts disabled")
        return
    threading.Thread(target=_loop, name="alerts", daemon=True).start()
