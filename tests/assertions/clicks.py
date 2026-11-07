"""Click tool (Story 2.1).

Looks for discontinuities: a zero-phase high-pass at row `click-highpass`,
then the largest absolute sample outside the session's first and last
EXCLUDE_S seconds against row `click-level`. Calibrated on
Python-synthesized signals first (tests/python/test_click_tool.py).

- EXCLUDE_S: session onset and end belong to the gain ramps (Story 4.4), so
  round(EXCLUDE_S * fs) samples at each end are left out of the peak.
- highpass(x, fs): a 4th-order Butterworth high-pass at the row corner,
  applied forward and backward, done as one FFT-domain magnitude on a
  zero-padded signal: |H(f)|^2 = 1 / (1 + (f_c / f)^8), 0 at DC. Real and
  even in frequency, so zero phase.
- peak_dbfs(x, fs, exclude_s=EXCLUDE_S): 20 log10 of the largest
  |highpass(x, fs)| outside the excluded ends; -inf when that part is all
  zero; ValueError when the signal is too short to leave any part.
- check(name, x, fs): the report assertion shape (Story 1.4), pass when the
  peak is strictly below the row; a NaN or infinite sample fails with note
  "not finite" and measured None.

NumPy and the standard library only.
"""

from __future__ import annotations

import math

import numpy as np

from . import row

LEVEL_ROW = "click-level"
HIGHPASS_ROW = "click-highpass"
EXCLUDE_S = 0.05
# Zero padding past the signal, in seconds, so the filter response of the
# last samples does not wrap onto the first.
_PAD_S = 0.1


def _corner_hz() -> float:
    r = row(HIGHPASS_ROW)
    if r.unit != "kHz":
        raise ValueError(f"row {HIGHPASS_ROW} unit is {r.unit}, expected kHz")
    return r.value * 1000.0


def highpass(x, fs) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    if a.ndim != 1:
        raise ValueError(f"need one channel, got shape {a.shape}")
    fc = _corner_hz()
    size = 1
    while size < a.size + int(math.ceil(_PAD_S * fs)):
        size *= 2
    f = np.fft.rfftfreq(size, d=1.0 / fs)
    gain = np.zeros(f.size)
    above = f > 0.0
    gain[above] = 1.0 / (1.0 + (fc / f[above]) ** 8)
    y = np.fft.irfft(np.fft.rfft(a, n=size) * gain, n=size)
    return np.ascontiguousarray(y[:a.size])


def peak_dbfs(x, fs, exclude_s=EXCLUDE_S) -> float:
    y = highpass(x, fs)
    k = int(round(exclude_s * fs))
    part = y[k:y.size - k]
    if part.size == 0:
        raise ValueError(f"signal of {y.size} samples is too short: no samples outside the "
                         f"first and last {exclude_s} s at {fs} Hz")
    peak = float(np.max(np.abs(part)))
    return -math.inf if peak == 0.0 else 20.0 * math.log10(peak)


def check(name, x, fs) -> dict:
    level = row(LEVEL_ROW)
    _corner_hz()
    result = {"name": name, "row": LEVEL_ROW, "threshold": level.value, "unit": level.unit,
              "measured": None, "result": "fail", "note": ""}
    a = np.asarray(x, dtype=np.float64)
    if not np.all(np.isfinite(a)):
        result["note"] = "not finite"
        return result
    measured = peak_dbfs(a, fs)
    result["measured"] = measured
    result["result"] = "pass" if measured < level.value else "fail"
    return result
