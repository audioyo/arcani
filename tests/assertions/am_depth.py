"""AM depth tool (Story 2.2).

Checks that a gamma tap's AM depth is constant at the recipe value. Calibrated
on Python-synthesized AM tones first (tests/python/test_am_depth_tool.py);
the verdict reads row `reference-match` through `row` on every call, as a
linear full-scale amplitude. No new row.

- TRIM_S: the first and last TRIM_S seconds are left out (session onset and
  end).
- envelope(x, fs): the analytic envelope |analytic| of one channel (FFT
  method), untrimmed.
- cycle_extrema(x, fs, rate_hz): the envelope with the first and last TRIM_S
  seconds trimmed, cut into consecutive windows of fs / rate_hz samples from
  the trim start (boundaries at round(start + k * fs / rate_hz)); for each
  full window, its maximum (peaks) and its minimum (troughs), two float64
  arrays.
- check(name, x, fs, rate_hz, depth_percent): the report assertion shape
  (Story 1.4). With d = depth_percent / 100, the worst deviation is the
  largest of |peak - 1| and |trough - (1 - d)| over every full cycle; pass
  when it is strictly below 10^(row / 20). measured is the worst deviation
  in dBFS. A non-finite input or measurement, or a signal with no full cycle,
  fails with a note and measured None.

NumPy and the standard library only.
"""

from __future__ import annotations

import math

import numpy as np

from . import row

ROW = "reference-match"
TRIM_S = 0.5


def envelope(x, fs) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    if a.ndim != 1 or a.size < 2:
        raise ValueError(f"need one channel of at least 2 samples, got shape {a.shape}")
    n = a.size
    h = np.zeros(n)
    h[0] = 1.0
    if n % 2 == 0:
        h[n // 2] = 1.0
        h[1:n // 2] = 2.0
    else:
        h[1:(n + 1) // 2] = 2.0
    return np.abs(np.fft.ifft(np.fft.fft(a) * h))


def cycle_extrema(x, fs, rate_hz) -> tuple[np.ndarray, np.ndarray]:
    rate = float(rate_hz)
    if not (math.isfinite(rate) and rate > 0.0):
        raise ValueError(f"rate_hz must be positive and finite, got {rate_hz!r}")
    env = envelope(x, fs)
    k = int(round(TRIM_S * fs))
    start, stop = k, env.size - k
    period = float(fs) / rate
    peaks, troughs = [], []
    j = 0
    while True:
        lo = int(round(start + j * period))
        hi = int(round(start + (j + 1) * period))
        if hi > stop:
            break
        window = env[lo:hi]
        peaks.append(float(np.max(window)))
        troughs.append(float(np.min(window)))
        j += 1
    return np.asarray(peaks, dtype=np.float64), np.asarray(troughs, dtype=np.float64)


def check(name, x, fs, rate_hz, depth_percent) -> dict:
    r = row(ROW)
    result = {"name": name, "row": ROW, "threshold": r.value, "unit": r.unit,
              "measured": None, "result": "fail", "note": ""}
    a = np.asarray(x, dtype=np.float64)
    if not np.all(np.isfinite(a)):
        result["note"] = "not finite"
        return result
    try:
        peaks, troughs = cycle_extrema(a, fs, rate_hz)
    except ValueError as exc:
        result["note"] = str(exc)
        return result
    if peaks.size == 0:
        result["note"] = "no full cycle"
        return result
    d = float(depth_percent) / 100.0
    worst = max(float(np.max(np.abs(peaks - 1.0))), float(np.max(np.abs(troughs - (1.0 - d)))))
    if not math.isfinite(worst):
        result["note"] = "not finite"
        return result
    limit = 10.0 ** (r.value / 20.0)
    result["measured"] = 20.0 * math.log10(worst) if worst > 0.0 else -math.inf
    result["result"] = "pass" if worst < limit else "fail"
    return result
