"""Reads the SCD41 every 5 s and stores readings in SQLite."""

import contextlib
import logging
import os
import signal
import time

import db
from scd41 import SCD41

ALTITUDE_M = os.environ.get("SLEEPMON_ALTITUDE_M")
TEMP_OFFSET_C = os.environ.get("SLEEPMON_TEMP_OFFSET_C")
MAX_FAILURES = 5

log = logging.getLogger("co2_logger")
running = True


def _stop(*_):
    global running
    running = False


def start_sensor(sensor):
    sensor.stop()
    sensor.reinit()
    log.info("SCD41 serial 0x%012x", sensor.serial_number())
    if ALTITUDE_M:
        sensor.set_altitude(float(ALTITUDE_M))
    if TEMP_OFFSET_C:
        sensor.set_temperature_offset(float(TEMP_OFFSET_C))
    sensor.start()


def main():
    logging.basicConfig(
        level=os.environ.get("SLEEPMON_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
    )
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    conn = db.connect()
    sensor = SCD41()
    start_sensor(sensor)
    log.info("Logging to %s", db.DB_PATH)

    failures = 0
    last_reading = time.time()
    while running:
        time.sleep(1)
        try:
            if not sensor.data_ready():
                if time.time() - last_reading > 30:
                    raise OSError("no data for 30 s")
                continue
            co2, temp, rh = sensor.read()
        except OSError as e:
            failures += 1
            log.warning("sensor error (%d/%d): %s", failures, MAX_FAILURES, e)
            if failures >= MAX_FAILURES:
                log.warning("restarting sensor")
                try:
                    start_sensor(sensor)
                    failures = 0
                except OSError as e2:
                    log.error("restart failed: %s", e2)
                last_reading = time.time()
            continue

        failures = 0
        last_reading = time.time()
        if co2 == 0:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO co2 (ts, co2, temp, rh) VALUES (?, ?, ?, ?)",
            (int(last_reading), co2, round(temp, 2), round(rh, 2)),
        )
        conn.commit()
        log.debug("CO2 %d ppm  T %.1f °C  RH %.1f %%", co2, temp, rh)

    with contextlib.suppress(OSError):
        sensor.stop()
    sensor.close()
    conn.close()
    log.info("stopped")


if __name__ == "__main__":
    main()
