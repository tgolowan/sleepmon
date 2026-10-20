import io
import math
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

BANDS = [
    (0, 800, "#4caf50"),
    (800, 1000, "#ffeb3b"),
    (1000, 1400, "#ff9800"),
    (1400, 10000, "#f44336"),
]


def co2_chart(points, bucket_s, tz, title):
    """points: rows with t, co2, temp, rh. Returns PNG bytes, or None if there is no data."""
    if not points:
        return None

    xs, ys = [], []
    for i, p in enumerate(points):
        if i and p["t"] - points[i - 1]["t"] > bucket_s * 3:
            xs.append(datetime.fromtimestamp(points[i - 1]["t"] + bucket_s, tz))
            ys.append(float("nan"))
        xs.append(datetime.fromtimestamp(p["t"], tz))
        ys.append(p["co2"])

    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=110)
    top = max(1200, max(y for y in ys if not math.isnan(y)) + 100)
    for lo, hi, color in BANDS:
        ax.axhspan(lo, min(hi, top), color=color, alpha=0.12, linewidth=0)
    ax.plot(xs, ys, color="#1f77b4", linewidth=1.4)
    ax.set_ylim(400, top)
    ax.set_xlim(xs[0], xs[-1])
    ax.set_ylabel("CO₂ (ppm)")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=tz))
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
