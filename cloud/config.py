import os
from zoneinfo import ZoneInfo


def _env(name, default=None, cast=str):
    value = os.environ.get(name)
    return cast(value) if value not in (None, "") else default


TZ = ZoneInfo(_env("TIMEZONE", "Europe/Warsaw"))

INGEST_TOKEN = _env("INGEST_TOKEN")
DASHBOARD_PASSWORD = _env("DASHBOARD_PASSWORD")

TELEGRAM_API_URL = _env("TELEGRAM_API_URL", "https://api.telegram.org")
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID")
TELEGRAM_WEBHOOK_SECRET = _env("TELEGRAM_WEBHOOK_SECRET")
PUBLIC_URL = _env("PUBLIC_URL") or (
    f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}" if os.environ.get("RAILWAY_PUBLIC_DOMAIN") else None
)

CO2_ALERT_PPM = _env("CO2_ALERT_PPM", 1400, int)
CO2_ALERT_WINDOW_MIN = _env("CO2_ALERT_WINDOW_MIN", 5, int)
CO2_ALERT_HYSTERESIS_PPM = _env("CO2_ALERT_HYSTERESIS_PPM", 200, int)
OFFLINE_ALERT_MIN = _env("OFFLINE_ALERT_MIN", 15, int)
MORNING_REPORT_TIME = _env("MORNING_REPORT_TIME", "08:30")
NIGHT_START_HOUR = _env("NIGHT_START_HOUR", 20, int)
NIGHT_END_HOUR = _env("NIGHT_END_HOUR", 10, int)
