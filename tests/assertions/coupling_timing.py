"""Coupling timing tool (Story 2.3, FR-3).

Measures, from the theta reference tap and the gamma PAC tap alone, how far
each gamma swell peak lies from its coupling phase. It never reads an engine
plan, the engine's depth, or any engine internal: only the two taps, the
sample rate, and the recipe's theta rate, theta shape, and coupling phase.
Calibrated on Python-synthesized signals of known peak times first
(tests/python/test_coupling_timing_tool.py, row
`coupling-timing-calibration`); the engine verdict reads row
`coupling-timing`. Both rows are read through `row` on every call.

- TRIM_S: the first and last TRIM_S seconds are left out (session onset and
  end, and the FFT edges).
- envelope(x): the analytic envelope |analytic| of one channel (FFT method),
  untrimmed.
- shape_template(shape, phi, rate_hz): the ideal theta envelope e in [0, 1]
  of the signal spec (Theta reference, Envelope shapes) at the cycle
  fractions phi (any real; taken modulo 1), with the fixed on share and edge
  length of rows `theta-on-share` and `theta-edge`. Peak (the 0 degree
  point) at phi = 0.
- zero_degree_times(theta, fs, theta_rate_hz, shape): the times in seconds
  (sample 0 at t = 0) of every theta 0 degree point whose cycle window lies
  inside the trimmed span. The theta tap's analytic envelope is fitted, one
  cycle at a time, by alpha + beta * shape_template(rate * (t - tau)) in
  least squares over a window of one theta period centered on tau; tau is
  found by a grid search and refined by golden-section search, so it is
  sub-sample.
- swell_curve(gamma, fs): 1 - |analytic| of the gamma tap, low-passed by a
  zero-phase FFT-domain filter (gain 1 up to the top of row `theta-rate`,
  a raised-cosine fall to 0 at the bottom of row `gamma-rate` minus the top
  of row `theta-rate`, so every gamma rate in the locked range and its swell
  side frequencies are removed). Zero phase: no delay.
- timing_errors(gamma, theta, fs, theta_rate_hz, shape, coupling_phase_deg):
  for each theta 0 degree time z, the expected swell peak is
  p = z + (coupling_phase_deg / 360) / theta_rate_hz. Over the window of one
  theta period centered on p (inside the trimmed span), the swell curve is
  fitted by c0 + c1 cos(w t) + c2 sin(w t), w = 2 pi theta_rate_hz, in least
  squares; its peak is the cosine maximum nearest p. The error is that peak
  minus p, wrapped into [-T / 2, T / 2), T = 1 / theta_rate_hz. Seconds,
  one per cycle. A cycle whose fitted swell amplitude hypot(c1, c2) is
  below row `reference-match` read as linear full-scale amplitude (the AM
  depth tool's reuse, design log (mm)) has no swell to time: ValueError
  "no swell in gamma tap", so check() fails with that note.
- check(name, gamma, theta, fs, theta_rate_hz, shape, coupling_phase_deg,
  row_id=ROW): the report assertion shape (Story 1.4). measured is the
  largest |error| in ms; pass when it is strictly below the row. A
  non-finite input or measurement, or no full cycle, fails with a note and
  measured None.

NumPy and the standard library only.
"""

from __future__ import annotations

import math

import numpy as np

from . import row

ROW = "coupling-timing"
CALIBRATION_ROW = "coupling-timing-calibration"
SWELL_FLOOR_ROW = "reference-match"
TRIM_S = 0.5
SHAPES = ("sine", "smoothed_on_off", "sawtooth", "reverse_saw")

_GOLDEN = (math.sqrt(5.0) - 1.0) / 2.0
_GRID_STEPS = 48
_SEARCH_STEPS = 48


def envelope(x) -> np.ndarray:
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


def _fixed(row_id) -> float:
    r = row(row_id)
    return float(r.min)


def shape_template(shape, phi, rate_hz) -> np.ndarray:
    if shape not in SHAPES:
        raise ValueError(f"shape not modeled in the signal spec: {shape!r}")
    p = np.mod(np.asarray(phi, dtype=np.float64), 1.0)
    if shape == "sine":
        return (1.0 + np.cos(2.0 * math.pi * p)) / 2.0
    half_on = _fixed("theta-on-share") / 100.0 / 2.0           # H, in cycles
    edge = _fixed("theta-edge") / 1000.0 * float(rate_hz)      # W, in cycles

    def rc(u):
        return (1.0 + np.cos(math.pi * u / edge)) / 2.0

    if shape == "smoothed_on_off":
        m = np.minimum(p, 1.0 - p)
        out = np.zeros_like(m)
        plateau = half_on - edge
        out[m <= plateau] = 1.0
        mid = (m > plateau) & (m < half_on)
        out[mid] = rc(m[mid] - plateau)
        return out
    q = p if shape == "sawtooth" else np.mod(1.0 - p, 1.0)
    out = np.empty_like(q)
    drop = q < edge
    out[drop] = rc(q[drop])
    out[~drop] = (q[~drop] - edge) / (1.0 - edge)
    return out


def _trim_bounds(n, fs):
    k = int(round(TRIM_S * fs))
    if n <= 2 * k + 1:
        raise ValueError(f"signal of {n} samples is too short for a {TRIM_S} s trim at each end")
    return k, n - k


def _fit_template(env, t, shape, rate, tau):
    """Least-squares residual of alpha + beta * template(rate * (t - tau))."""
    g = shape_template(shape, rate * (t - tau), rate)
    gm = g - g.mean()
    em = env - env.mean()
    denom = float(np.dot(gm, gm))
    beta = float(np.dot(gm, em)) / denom if denom > 0.0 else 0.0
    if not beta > 0.0:
        # A falling template is a different point of the cycle (for the sine
        # shape, the trough): never a fit.
        return 2.0 * float(np.dot(em, em)) + 1.0, beta
    r = em - beta * gm
    return float(np.dot(r, r)), beta


def _golden(f, lo, hi, steps):
    a = hi - _GOLDEN * (hi - lo)
    b = lo + _GOLDEN * (hi - lo)
    fa, fb = f(a), f(b)
    for _ in range(steps):
        if fa < fb:
            hi, b, fb = b, a, fa
            a = hi - _GOLDEN * (hi - lo)
            fa = f(a)
        else:
            lo, a, fa = a, b, fb
            b = lo + _GOLDEN * (hi - lo)
            fb = f(b)
    return (lo + hi) / 2.0


def _window(fs, center, period, lo, hi):
    """Sample indices of one period centered on `center` (seconds), or None
    when it leaves [lo, hi)."""
    first = int(math.ceil((center - period / 2.0) * fs))
    last = int(math.floor((center + period / 2.0) * fs))
    if first < lo or last >= hi:
        return None
    return np.arange(first, last + 1)


def zero_degree_times(theta, fs, theta_rate_hz, shape) -> np.ndarray:
    rate = float(theta_rate_hz)
    if not (math.isfinite(rate) and rate > 0.0):
        raise ValueError(f"theta_rate_hz must be positive and finite, got {theta_rate_hz!r}")
    if shape not in SHAPES:
        raise ValueError(f"shape not modeled in the signal spec: {shape!r}")
    env = envelope(theta)
    lo, hi = _trim_bounds(env.size, fs)
    period = 1.0 / rate
    t_all = np.arange(env.size, dtype=np.float64) / float(fs)

    # First cycle: a grid over one whole period finds where the 0 degree point
    # lies, then each cycle is refined around its predicted time.
    start = lo / float(fs) + period / 2.0
    idx = _window(fs, start, period, lo, hi)
    if idx is None:
        return np.zeros(0)
    grid = start + (np.arange(_GRID_STEPS * 4) / (_GRID_STEPS * 4) - 0.5) * period
    sse = [_fit_template(env[idx], t_all[idx], shape, rate, tau)[0] for tau in grid]
    tau = float(grid[int(np.argmin(sse))])
    times = []
    step = period / (_GRID_STEPS * 4)
    while True:
        idx = _window(fs, tau, period, lo, hi)
        if idx is None:
            if tau * fs >= hi:
                break
            tau += period
            continue
        e, t = env[idx], t_all[idx]

        def cost(x, e=e, t=t):
            return _fit_template(e, t, shape, rate, x)[0]

        local = tau + (np.arange(-8, 9)) * step
        best = float(local[int(np.argmin([cost(x) for x in local]))])
        found = _golden(cost, best - step, best + step, _SEARCH_STEPS)
        times.append(found)
        tau = found + period
    return np.asarray(times, dtype=np.float64)


def swell_curve(gamma, fs) -> np.ndarray:
    theta_top = row("theta-rate").max
    gamma_bottom = row("gamma-rate").min
    f_pass, f_stop = theta_top, gamma_bottom - theta_top
    y = 1.0 - envelope(gamma)
    spectrum = np.fft.rfft(y)
    f = np.fft.rfftfreq(y.size, d=1.0 / float(fs))
    gain = np.zeros_like(f)
    gain[f <= f_pass] = 1.0
    mid = (f > f_pass) & (f < f_stop)
    gain[mid] = (1.0 + np.cos(math.pi * (f[mid] - f_pass) / (f_stop - f_pass))) / 2.0
    return np.fft.irfft(spectrum * gain, n=y.size)


def timing_errors(gamma, theta, fs, theta_rate_hz, shape, coupling_phase_deg) -> np.ndarray:
    g = np.asarray(gamma, dtype=np.float64)
    th = np.asarray(theta, dtype=np.float64)
    if g.shape != th.shape:
        raise ValueError(f"gamma and theta taps differ in shape: {g.shape} and {th.shape}")
    rate = float(theta_rate_hz)
    zeros = zero_degree_times(th, fs, rate, shape)
    curve = swell_curve(g, fs)
    lo, hi = _trim_bounds(curve.size, fs)
    period = 1.0 / rate
    w = 2.0 * math.pi * rate
    offset = (float(coupling_phase_deg) / 360.0) * period
    floor = 10.0 ** (row(SWELL_FLOOR_ROW).value / 20.0)
    errors = []
    for z in zeros:
        p = z + offset
        idx = _window(fs, p, period, lo, hi)
        if idx is None:
            continue
        t = idx / float(fs) - p
        basis = np.stack([np.ones_like(t), np.cos(w * t), np.sin(w * t)], axis=1)
        c, *_ = np.linalg.lstsq(basis, curve[idx], rcond=None)
        if not math.hypot(float(c[1]), float(c[2])) >= floor:
            raise ValueError("no swell in gamma tap")
        peak = math.atan2(float(c[2]), float(c[1])) / w   # cosine maximum nearest p, in [-T/2, T/2]
        errors.append(math.remainder(peak, period))
    return np.asarray(errors, dtype=np.float64)


def check(name, gamma, theta, fs, theta_rate_hz, shape, coupling_phase_deg, row_id=ROW) -> dict:
    r = row(row_id)
    result = {"name": name, "row": row_id, "threshold": r.value, "unit": r.unit,
              "measured": None, "result": "fail", "note": ""}
    g = np.asarray(gamma, dtype=np.float64)
    th = np.asarray(theta, dtype=np.float64)
    if not (np.all(np.isfinite(g)) and np.all(np.isfinite(th))):
        result["note"] = "not finite"
        return result
    try:
        errors = timing_errors(g, th, fs, theta_rate_hz, shape, coupling_phase_deg)
    except ValueError as exc:
        result["note"] = str(exc)
        return result
    if errors.size == 0:
        result["note"] = "no full cycle"
        return result
    worst_ms = float(np.max(np.abs(errors))) * 1000.0
    if not math.isfinite(worst_ms):
        result["note"] = "not finite"
        return result
    result["measured"] = worst_ms
    result["result"] = "pass" if worst_ms < r.value else "fail"
    return result
