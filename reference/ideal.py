"""Ideal signals of docs/signal-spec.md, sections Core and Sine (Python reference).

Implemented from the signal spec only, never from engine code (AD-16, AD-19).
It renders the ideal sine, sin(2*pi*phase/2^64), with NumPy's sine in
binary64; it never implements the engine's approximation (design log
2026-10-28 (o)).

- phase_increment(f_hz, fs): q = (f_hz * 2^64) / fs in binary64 (Python
  floats are binary64; the multiply by 2^64 is exact and the division rounds
  once), then round(q), which rounds to the nearest integer with ties to
  even. Domain 0 <= f_hz < fs / 2, else 0.
- seconds_to_samples(t_s, fs): x = t_s * fs in binary64, then round(x). Domain
  t_s >= 0 and finite with x < 2^64, else 0.
- ideal_sine(phase): sin(2*pi*phase/2^64). The phase is read as a signed
  64-bit value first, so the argument stays in [-pi, pi) and keeps its
  precision near the top of the cycle.
- frame_index(frames) (Story 2.7): the frame indices a layer renders, as a
  uint64 ndarray: 0 to frames - 1 for an int, or a 1-D integer ndarray of
  frame indices itself (any order, each >= 0), so a window renders straight
  from its frame numbers. A negative count or index raises ValueError
  ("frames must be >= 0").
- render_probe_segment(f_hz, fs, n): n samples of an unmodulated sine at
  carrier f_hz, phase[0] = 0, phase[k] = k * inc mod 2^64.
- probe_sine_component(fs): the hash probe's sine-<fs> component, 1 s each
  of the PROBE_CARRIERS_HZ carriers, unmodulated, each from phase 0.

NumPy and the standard library only.
"""

import math

import numpy as np

CYCLE = 2**64
TWO_POW_64 = 2.0**64
PROBE_CARRIERS_HZ = (1.0, 450.0, 1000.0)


def phase_increment(f_hz, fs):
    """Phase increment rule (signal spec, Core); returns a Python int."""
    f = float(f_hz)
    rate = float(fs)
    if not (f >= 0.0 and f < rate / 2.0):
        return 0
    q = (f * TWO_POW_64) / rate
    return int(round(q))


def seconds_to_samples(t_s, fs):
    """Seconds-to-samples rule (signal spec, Core); returns a Python int."""
    t = float(t_s)
    if not (t >= 0.0 and math.isfinite(t)):
        return 0
    x = t * float(fs)
    if not (x < TWO_POW_64):
        return 0
    return int(round(x))


def _signed(phase):
    """Phase as signed 64-bit values in [-2^63, 2^63), as float64."""
    if isinstance(phase, (int, np.integer)) and not isinstance(phase, np.ndarray):
        p = int(phase) % CYCLE
        return float(p - CYCLE if p >= CYCLE // 2 else p)
    arr = np.asarray(phase, dtype=np.uint64)
    return arr.view(np.int64).astype(np.float64)


def ideal_sine(phase):
    """sin(2*pi*phase/2^64) for an int or an array of uint64 phases."""
    s = _signed(phase)
    y = np.sin(s * (2.0 * math.pi / TWO_POW_64))
    if isinstance(s, float):
        return float(y)
    return y


def frame_index(frames):
    """Frame indices as a uint64 array: arange(frames) for an int, else the index array."""
    if isinstance(frames, np.ndarray):
        if frames.ndim != 1 or not (frames.size == 0 or np.issubdtype(frames.dtype, np.integer)):
            raise ValueError(f"frames must be an int or a 1-D integer array, got {frames.dtype} {frames.shape}")
        if frames.size and int(frames.min()) < 0:
            raise ValueError(f"frames must be >= 0, got {int(frames.min())}")
        return frames.astype(np.uint64)
    count = int(frames)
    if count < 0:
        raise ValueError(f"frames must be >= 0, got {frames}")
    return np.arange(count, dtype=np.uint64)


def render_probe_segment(f_hz, fs, n):
    """n samples of the ideal unmodulated sine at carrier f_hz, from phase 0."""
    inc = np.uint64(phase_increment(f_hz, fs))
    phases = np.arange(n, dtype=np.uint64) * inc  # wraps modulo 2^64
    return ideal_sine(phases)


def probe_sine_component(fs):
    """Ideal sine-<fs> probe component: 1 s of each carrier, float64."""
    return np.concatenate([render_probe_segment(f, fs, int(fs)) for f in PROBE_CARRIERS_HZ])
