"""Frequency accuracy tool (Stories 2.1, 2.5, and 2.6, FR-1).

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
- Phase mode (Story 2.5), for a carrier whose rate follows a rate curve:
  phase_track(x, fs, expected_cycles) takes the FFT analytic signal of x
  (each end tapered by a raised cosine over the first half of its TRIM_S
  trim, so the record's end jump does not ring into the kept part), removes
  the expected phase integral (cycles per sample, any constant offset),
  trims TRIM_S at each end, and unwraps: the residual in cycles (its first
  value subtracted), the instantaneous rate error np.diff(residual) * fs,
  its maximum magnitude, and the largest per-sample step.
  check_phase(name, x, fs, expected_cycles) is the report assertion shape
  of check() on row frequency-accuracy: measured is the maximum
  instantaneous rate error; it passes only when that is strictly below the
  row and no per-sample step reaches PHASE_STEP_CYCLES (note "phase step");
  a NaN or infinite measure fails with note "not finite".
- Envelope phase mode (Story 2.6), for a theta or gamma envelope whose rate
  follows a rate curve: curve_phase(t, rate_hz, cycle=None) is the ideal
  phase integral in cycles (r t without a cycle; cycle a mapping with
  swing_hz, period_s, start_phase_deg). envelope_phase_track(x, fs,
  expected_cycles) takes |analytic(x)|, removes its mean, tapers each end
  by a raised cosine over ENVELOPE_TAPER_S, forms its analytic signal with
  every bin below half the bottom of row theta-rate zeroed, removes the
  expected phase, trims ENVELOPE_TRIM_S at each end, and unwraps: the same
  dict as phase_track. For a sine-shape theta tap or an uncoupled gamma tap.
  check_envelope_phase(name, x, fs, expected_cycles) is check_phase's
  report shape on row frequency-accuracy.

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


# ------------------------------------------------------------ phase mode
#
# Story 2.5: along a rate curve the instantaneous rate must follow the
# schedule within row frequency-accuracy, with continuous phase. The tool
# subtracts the closed-form phase integral from the tap's analytic phase.

# A per-sample phase change this large (in cycles) is a step, not a rate:
# at 48 kHz row frequency-accuracy allows about 2e-7 cycles per sample.
PHASE_STEP_CYCLES = 1e-4


def phase_track(x, fs, expected_cycles) -> dict:
    """Residual phase of x against the expected phase integral (cycles per sample)."""
    a = np.asarray(x, dtype=np.float64)
    expected = np.asarray(expected_cycles, dtype=np.float64)
    if expected.shape != a.shape:
        raise ValueError(f"expected_cycles has shape {expected.shape}, x has {a.shape}")
    # A raised-cosine taper over each trimmed end removes the jump at the
    # ends of the record, which would otherwise ring through the analytic
    # phase; inside the kept part the taper is 1, so the phase is unchanged.
    k = int(round(TRIM_S * fs))
    if a.size <= 2 * k + 1:
        raise ValueError(f"signal of {a.size} samples is too short for a {TRIM_S} s trim at each end")
    taper = np.ones(a.size)
    m = k // 2
    edge = 0.5 - 0.5 * np.cos(math.pi * np.arange(m) / m)
    taper[:m] = edge
    taper[a.size - m:] = edge[::-1]
    z = _analytic(a * taper)
    # Remove the expected phase before unwrapping, so the unwrapped value
    # stays small and keeps its precision over long renders.
    frac = expected - np.rint(expected)
    z = z * np.exp(-2j * math.pi * frac)
    z, _ = _trimmed(z, fs)
    residual = np.unwrap(np.angle(z)) / (2.0 * math.pi)
    residual = residual - residual[0]
    step = np.diff(residual)
    rate_error = step * float(fs)
    return {
        "residual_cycles": residual,
        "rate_error_hz": rate_error,
        "max_rate_error_hz": float(np.max(np.abs(rate_error))) if rate_error.size else 0.0,
        "max_step_cycles": float(np.max(np.abs(step))) if step.size else 0.0,
    }


def check_phase(name, x, fs, expected_cycles) -> dict:
    r = row(ACCURACY_ROW)
    result = {"name": name, "row": ACCURACY_ROW, "threshold": r.value, "unit": r.unit,
              "measured": None, "result": "fail", "note": ""}
    track = phase_track(x, fs, expected_cycles)
    measured = track["max_rate_error_hz"]
    step = track["max_step_cycles"]
    if not (math.isfinite(measured) and math.isfinite(step)):
        result["note"] = "not finite"
        return result
    result["measured"] = measured
    if not step < PHASE_STEP_CYCLES:
        result["note"] = "phase step"
        return result
    result["result"] = "pass" if measured < r.value else "fail"
    return result


# --------------------------------------------------- envelope phase mode
#
# Story 2.6: along a theta or gamma rate curve the envelope rate must follow
# the schedule within row frequency-accuracy, with continuous phase. The
# envelope of a sine-shape theta tap or an uncoupled gamma tap is a raised
# cosine of the envelope phase, so its mean-removed analytic signal carries
# that phase. The envelope runs at 1 Hz and up, so its record ends ring far
# longer than a carrier's: a longer taper and trim, and every bin below half
# the bottom of row theta-rate removed (the mean and its leakage).

ENVELOPE_TRIM_S = 10.0
ENVELOPE_TAPER_S = 5.0


def curve_phase(t, rate_hz, cycle=None) -> np.ndarray:
    """Ideal phase integral in cycles at times t (signal spec, Rate curve, Phase integral)."""
    t = np.asarray(t, dtype=np.float64)
    r = float(rate_hz)
    if cycle is None:
        return r * t
    s = float(cycle["swing_hz"])
    period = float(cycle["period_s"])
    phi0 = math.radians(float(cycle["start_phase_deg"]))
    k = s * period / (2.0 * math.pi)
    return r * t + k * (math.cos(phi0) - np.cos(2.0 * math.pi * t / period + phi0))


def envelope_phase_track(x, fs, expected_cycles) -> dict:
    """Residual phase of the envelope of x against the expected envelope phase integral."""
    a = np.asarray(x, dtype=np.float64)
    expected = np.asarray(expected_cycles, dtype=np.float64)
    if expected.shape != a.shape:
        raise ValueError(f"expected_cycles has shape {expected.shape}, x has {a.shape}")
    k = int(round(ENVELOPE_TRIM_S * fs))
    m = int(round(ENVELOPE_TAPER_S * fs))
    if a.size <= 2 * k + 1:
        raise ValueError(f"signal of {a.size} samples is too short for a {ENVELOPE_TRIM_S} s trim at each end")
    env = np.abs(_analytic(a))
    env = env - float(np.mean(env))
    taper = np.ones(a.size)
    edge = 0.5 - 0.5 * np.cos(math.pi * np.arange(m) / m)
    taper[:m] = edge
    taper[a.size - m:] = edge[::-1]
    spectrum = np.fft.fft(env * taper)
    f = np.fft.fftfreq(a.size, d=1.0 / float(fs))
    low = row("theta-rate").min / 2.0
    z = np.fft.ifft(spectrum * np.where(f > low, 2.0, 0.0))
    frac = expected - np.rint(expected)
    z = z * np.exp(-2j * math.pi * frac)
    z = z[k:a.size - k]
    residual = np.unwrap(np.angle(z)) / (2.0 * math.pi)
    residual = residual - residual[0]
    step = np.diff(residual)
    rate_error = step * float(fs)
    return {
        "residual_cycles": residual,
        "rate_error_hz": rate_error,
        "max_rate_error_hz": float(np.max(np.abs(rate_error))) if rate_error.size else 0.0,
        "max_step_cycles": float(np.max(np.abs(step))) if step.size else 0.0,
    }


def check_envelope_phase(name, x, fs, expected_cycles) -> dict:
    r = row(ACCURACY_ROW)
    result = {"name": name, "row": ACCURACY_ROW, "threshold": r.value, "unit": r.unit,
              "measured": None, "result": "fail", "note": ""}
    a = np.asarray(x, dtype=np.float64)
    if not np.all(np.isfinite(a)):
        result["note"] = "not finite"
        return result
    track = envelope_phase_track(a, fs, expected_cycles)
    measured = track["max_rate_error_hz"]
    step = track["max_step_cycles"]
    if not (math.isfinite(measured) and math.isfinite(step)):
        result["note"] = "not finite"
        return result
    result["measured"] = measured
    if not step < PHASE_STEP_CYCLES:
        result["note"] = "phase step"
        return result
    result["result"] = "pass" if measured < r.value else "fail"
    return result
