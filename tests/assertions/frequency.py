"""Frequency accuracy tool (Story 2.1, FR-1).

Measures the carrier and the AM rate of one channel. Calibrated on
Python-synthesized signals of known carrier and rate first
(tests/python/test_frequency_tool.py, row `frequency-accuracy-calibration`);
the verdict reads row `frequency-accuracy` through `row` on every call.

- TRIM_S: the first and last TRIM_S seconds are left out of both
  measurements (session onset and end).
- carrier_hz(x, fs): the analytic signal of x (FFT method), trimmed; its
  phase unwrapped; the carrier is the slope of the weighted least-squares
  line through (t, phase), weights |analytic|^2, divided by 2 pi.
- rate_hz(x, fs): the AM rate. The analytic envelope |analytic|, trimmed and
  mean-removed, times a 4-term Blackman-Harris window; the strongest peak of
  its zero-padded DFT above the window's main lobe at 0 Hz, refined by
  golden-section search on the windowed DTFT magnitude. rate_hz(x, fs,
  min_hz) (Story 2.3) starts the peak search at the larger of the main lobe
  and min_hz: a coupled gamma envelope has a theta-rate swell line as strong
  as its gamma-rate line.
- check(name, measured_hz, expected_hz): the report assertion shape (Story
  1.4), pass when |measured - expected| is strictly below the row; a NaN or
  infinite measured value fails with note "not finite" and measured None.

NumPy and the standard library only.
"""

from __future__ import annotations

import math

import numpy as np

from . import row

ACCURACY_ROW = "frequency-accuracy"
TRIM_S = 0.5

# 4-term Blackman-Harris window coefficients (Harris 1978, minimum 4-term).
_BH = (0.35875, 0.48829, 0.14128, 0.01168)
# Half width of the window's main lobe, in DFT bins of the unpadded length.
_MAIN_LOBE_BINS = 4
_PAD = 8
_GOLDEN = (math.sqrt(5.0) - 1.0) / 2.0
_SEARCH_STEPS = 40


def _analytic(x) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    if a.ndim != 1 or a.size < 2:
        raise ValueError(f"need one channel of at least 2 samples, got shape {a.shape}")
    n = a.size
    spectrum = np.fft.fft(a)
    h = np.zeros(n)
    h[0] = 1.0
    if n % 2 == 0:
        h[n // 2] = 1.0
        h[1:n // 2] = 2.0
    else:
        h[1:(n + 1) // 2] = 2.0
    return np.fft.ifft(spectrum * h)


def _trimmed(z, fs) -> tuple[np.ndarray, np.ndarray]:
    k = int(round(TRIM_S * fs))
    if z.size <= 2 * k + 1:
        raise ValueError(f"signal of {z.size} samples is too short for a {TRIM_S} s trim at each end")
    t = np.arange(k, z.size - k, dtype=np.float64) / float(fs)
    return z[k:z.size - k], t


def carrier_hz(x, fs) -> float:
    z, t = _trimmed(_analytic(x), fs)
    phase = np.unwrap(np.angle(z))
    w = np.abs(z) ** 2
    sw = float(np.sum(w))
    t_mean = float(np.sum(w * t)) / sw
    p_mean = float(np.sum(w * phase)) / sw
    dt = t - t_mean
    slope = float(np.sum(w * dt * (phase - p_mean))) / float(np.sum(w * dt * dt))
    return slope / (2.0 * math.pi)


def _window(n) -> np.ndarray:
    k = np.arange(n, dtype=np.float64) * (2.0 * math.pi / (n - 1))
    return _BH[0] - _BH[1] * np.cos(k) + _BH[2] * np.cos(2.0 * k) - _BH[3] * np.cos(3.0 * k)


def _dtft_magnitude(y, fs, f_hz) -> float:
    n = np.arange(y.size, dtype=np.float64)
    return float(np.abs(np.sum(y * np.exp(-2j * math.pi * f_hz * n / fs))))


def rate_hz(x, fs, min_hz=None) -> float:
    z, _ = _trimmed(_analytic(x), fs)
    env = np.abs(z)
    env = env - float(np.mean(env))
    y = env * _window(env.size)
    size = _PAD * env.size
    spectrum = np.abs(np.fft.rfft(y, n=size))
    lowest = _MAIN_LOBE_BINS * _PAD
    if min_hz is not None:
        lowest = max(lowest, int(math.ceil(float(min_hz) * size / fs)))
    k = lowest + int(np.argmax(spectrum[lowest:]))
    step = fs / size
    lo, hi = (k - 1) * step, (k + 1) * step
    # Golden-section search for the DTFT maximum inside one padded bin each side.
    a = hi - _GOLDEN * (hi - lo)
    b = lo + _GOLDEN * (hi - lo)
    fa, fb = _dtft_magnitude(y, fs, a), _dtft_magnitude(y, fs, b)
    for _ in range(_SEARCH_STEPS):
        if fa > fb:
            hi, b, fb = b, a, fa
            a = hi - _GOLDEN * (hi - lo)
            fa = _dtft_magnitude(y, fs, a)
        else:
            lo, a, fa = a, b, fb
            b = lo + _GOLDEN * (hi - lo)
            fb = _dtft_magnitude(y, fs, b)
    return (lo + hi) / 2.0


def check(name, measured_hz, expected_hz) -> dict:
    r = row(ACCURACY_ROW)
    result = {"name": name, "row": ACCURACY_ROW, "threshold": r.value, "unit": r.unit,
              "measured": None, "result": "fail", "note": ""}
    measured = float(measured_hz)
    if not math.isfinite(measured):
        result["note"] = "not finite"
        return result
    error = abs(measured - float(expected_hz))
    result["measured"] = error
    result["result"] = "pass" if error < r.value else "fail"
    return result
