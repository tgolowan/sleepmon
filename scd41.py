"""Minimal Sensirion SCD41 driver over Linux I2C (smbus2)."""

import time

from smbus2 import SMBus, i2c_msg

ADDR = 0x62

CMD_START_PERIODIC = 0x21B1
CMD_STOP_PERIODIC = 0x3F86
CMD_READ_MEASUREMENT = 0xEC05
CMD_GET_DATA_READY = 0xE4B8
CMD_GET_SERIAL = 0x3682
CMD_REINIT = 0x3646
CMD_SET_ALTITUDE = 0x2427
CMD_SET_TEMP_OFFSET = 0x241D


def _crc8(data):
    crc = 0xFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


class SCD41:
    def __init__(self, bus=1):
        self._bus = SMBus(bus)

    def close(self):
        self._bus.close()

    def _send(self, command, delay=0.001):
        self._bus.i2c_rdwr(i2c_msg.write(ADDR, [command >> 8, command & 0xFF]))
        time.sleep(delay)

    def _send_word(self, command, word, delay=0.001):
        payload = [word >> 8, word & 0xFF]
        self._bus.i2c_rdwr(
            i2c_msg.write(ADDR, [command >> 8, command & 0xFF, *payload, _crc8(payload)])
        )
        time.sleep(delay)

    def _read_words(self, command, count):
        self._send(command)
        msg = i2c_msg.read(ADDR, count * 3)
        self._bus.i2c_rdwr(msg)
        raw = list(msg)
        words = []
        for i in range(0, len(raw), 3):
            if _crc8(raw[i:i + 2]) != raw[i + 2]:
                raise OSError("SCD41 CRC mismatch")
            words.append(raw[i] << 8 | raw[i + 1])
        return words

    def stop(self):
        self._send(CMD_STOP_PERIODIC, delay=0.5)

    def reinit(self):
        self._send(CMD_REINIT, delay=0.03)

    def serial_number(self):
        w = self._read_words(CMD_GET_SERIAL, 3)
        return (w[0] << 32) | (w[1] << 16) | w[2]

    def set_altitude(self, meters):
        """Only valid while idle (call stop() first)."""
        self._send_word(CMD_SET_ALTITUDE, int(meters))

    def set_temperature_offset(self, celsius):
        """Compensates self-heating. Only valid while idle (call stop() first)."""
        self._send_word(CMD_SET_TEMP_OFFSET, int(round(celsius * 65535 / 175)))

    def start(self):
        self._send(CMD_START_PERIODIC)

    def data_ready(self):
        return bool(self._read_words(CMD_GET_DATA_READY, 1)[0] & 0x07FF)

    def read(self):
        """Returns (co2_ppm, temperature_c, humidity_pct)."""
        co2, t_raw, rh_raw = self._read_words(CMD_READ_MEASUREMENT, 3)
        return co2, -45 + 175 * t_raw / 65535, 100 * rh_raw / 65535
