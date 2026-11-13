"""When a frame was captured, as the aim filter wants it."""

from __future__ import annotations

# Same rule as the ESP32 firmware's `bp_capture_ms`: trust the sensor's
# timestamp when it is plausible, else stamp at grab.
MAX_AGE_S = 1.0


def capture_time(sensor_s: float | None, now_s: float) -> float:
    """`sensor_s` and `now_s` are on the same clock, in seconds."""
    if sensor_s is not None and 0 < sensor_s <= now_s and now_s - sensor_s <= MAX_AGE_S:
        return sensor_s
    return now_s
