import time
from datetime import datetime, timedelta

import charts
import config
import store


def night_bounds(now=None):
    """Most recent night: NIGHT_START_HOUR yesterday until NIGHT_END_HOUR today (or now if earlier)."""
    now = now or datetime.now(config.TZ)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = (midnight - timedelta(days=1)).replace(hour=config.NIGHT_START_HOUR)
    end = midnight.replace(hour=config.NIGHT_END_HOUR)
    return int(start.timestamp()), int(min(end, now).timestamp())


def _fmt_minutes(m):
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


def _co2_emoji(ppm):
    if ppm < 800:
        return "🟢"
    if ppm < 1000:
        return "🟡"
    if ppm < 1400:
        return "🟠"
    return "🔴"


def now_text():
    r = store.latest()
    if not r:
        return "No data yet."
    age_min = (time.time() - r["ts"]) / 60
    when = datetime.fromtimestamp(r["ts"], config.TZ).strftime("%H:%M:%S")
    text = (
        f"{_co2_emoji(r['co2'])} CO₂: <b>{r['co2']} ppm</b>\n"
        f"🌡 Temperature: {r['temp']:.1f} °C\n"
        f"💧 Humidity: {r['rh']:.0f} %\n"
        f"🕒 {when}"
    )
    if age_min > 2:
        text += f"\n⚠️ Last reading was {age_min:.0f} min ago"
    return text


def summary_text(start, end, title):
    s = store.stats(start, end)
    if not s["samples"]:
        return f"<b>{title}</b>\nNo data in this period."
    fmt = "%a %H:%M"
    period = (
        f"{datetime.fromtimestamp(start, config.TZ).strftime(fmt)} – "
        f"{datetime.fromtimestamp(end, config.TZ).strftime(fmt)}"
    )
    return (
        f"<b>{title}</b>\n{period}\n\n"
        f"{_co2_emoji(s['co2_avg'])} Average CO₂: <b>{s['co2_avg']} ppm</b>\n"
        f"📈 Peak: {s['co2_max']} ppm · 📉 Min: {s['co2_min']} ppm\n"
        f"🟠 Above 1000 ppm: {_fmt_minutes(s['min_over_1000'])}\n"
        f"🔴 Above 1400 ppm: {_fmt_minutes(s['min_over_1400'])}\n"
        f"🌡 {s['temp_avg']} °C · 💧 {s['rh_avg']} %"
    )


def chart_png(start, end, title):
    bucket, points = store.series(start, end, max_points=600)
    return charts.co2_chart(points, bucket, config.TZ, title)
