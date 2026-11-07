"""Reference render of the theta reference (docs/signal-spec.md, Theta reference; Story 2.1).

Implemented from the signal spec only, never from engine code, engine
binaries, or engine output (AD-16, AD-19). Segments are chosen by the spec's
exact integer comparisons on the integer phases; inside a segment every value
is binary64 with the ideal functions (NumPy cosine and reference/ideal.py's
ideal sine), never the engine's approximation.

- SHAPES: the shapes the spec models, in schema order. Anything else,
  "custom" included, raises ValueError.
- ON_SHARE_PERCENT, EDGE_MS: the fixed constants in row units (range rows
  theta-on-share and theta-edge).
- half_on_units(): H = (ON_SHARE_PERCENT / 100) * 2^63, rounded (2^62).
- edge_units(rate_hz): W = ((EDGE_MS / 1000) * rate_hz) * 2^64, rounded,
  with one binary64 rounding in the first product.
- envelope(shape, phase, rate_hz): the ideal envelope e in [0, 1] of an
  envelope phase (an int, giving a float, or a uint64 ndarray, giving a
  float64 ndarray of the same shape), peak at phase 0:
    sine:            (1 + cos(2 pi p / 2^64)) / 2
    smoothed_on_off: m = p, or 2^64 - p past the half cycle; 1 for
                     m <= H - W, rc(m - (H - W)) for H - W < m < H, 0 for m >= H
    sawtooth:        rc(p) for p < W, else (p - W) / (2^64 - W)
    reverse_saw:     the sawtooth of 2^64 - p mod 2^64
  with rc(u) = (1 + cos(pi * u / W)) / 2.
- render(theta_reference, fs, frames): the theta tap of one channel,
  a[n] * ideal_sine(phase_T[n]) for n in [0, frames), with
  a = 1.0 - d * (1.0 - e[n]), d = am_depth_percent / 100.0, and both phases
  n * inc mod 2^64 (ideal.phase_increment of carrier_hz and rate_hz).

NumPy, the standard library, and reference/ only.
"""

import math

import numpy as np

from . import ideal

SHAPES = ("sine", "smoothed_on_off", "sawtooth", "reverse_saw")
ON_SHARE_PERCENT = 50.0
EDGE_MS = 10.0

_HALF = np.uint64(2**63)
_ZERO = np.uint64(0)


def half_on_units():
    """H, half the on share in phase units; a Python int."""
    d = ON_SHARE_PERCENT / 100.0
    return int(round(d * 2.0**63))


def edge_units(rate_hz):
    """W, the edge length in envelope phase units at rate_hz; a Python int."""
    e = EDGE_MS / 1000.0
    w = e * float(rate_hz)
    return int(round(w * 2.0**64))


def _raised_cosine(u, w):
    """(1 + cos(pi * u / W)) / 2 for uint64 offsets u, 0 <= u <= W."""
    r = u.astype(np.float64) / float(w)
    return (1.0 + np.cos(math.pi * r)) / 2.0


def _sawtooth(q, w):
    """Drop edge for q < W, then the linear rise (q - W) / (2^64 - W)."""
    out = np.empty(q.shape, dtype=np.float64)
    w64 = np.uint64(w)
    drop = q < w64
    out[drop] = _raised_cosine(q[drop], w)
    rise = ~drop
    out[rise] = (q[rise] - w64).astype(np.float64) / float(2**64 - w)
    return out


def _envelope_array(shape, p, rate_hz):
    w = edge_units(rate_hz)
    h = half_on_units()
    if shape == "sine":
        s = p.view(np.int64).astype(np.float64)  # signed, in [-2^63, 2^63)
        return (1.0 + np.cos(s * (2.0 * math.pi / 2.0**64))) / 2.0
    if shape == "smoothed_on_off":
        m = np.where(p < _HALF, p, _ZERO - p)  # uint64, wraps modulo 2^64
        out = np.zeros(p.shape, dtype=np.float64)
        plateau_end = np.uint64(h - w)
        out[m <= plateau_end] = 1.0
        edge = (m > plateau_end) & (m < np.uint64(h))
        out[edge] = _raised_cosine(m[edge] - plateau_end, w)
        return out
    if shape == "sawtooth":
        return _sawtooth(p, w)
    # reverse_saw: the sawtooth of 2^64 - p mod 2^64
    return _sawtooth(_ZERO - p, w)


def envelope(shape, phase, rate_hz):
    """Ideal envelope of an envelope phase (int or uint64 ndarray)."""
    if shape not in SHAPES:
        raise ValueError(f"shape not modeled in the signal spec: {shape!r}")
    if isinstance(phase, np.ndarray):
        p = np.ascontiguousarray(phase, dtype=np.uint64)
        return _envelope_array(shape, p, rate_hz)
    p = np.array([int(phase) % 2**64], dtype=np.uint64)
    return float(_envelope_array(shape, p, rate_hz)[0])


def render(theta_reference, fs, frames):
    """Theta tap of one channel for n in [0, frames), binary64."""
    frames = int(frames)
    if frames < 0:
        raise ValueError(f"frames must be >= 0, got {frames}")
    shape = theta_reference["shape"]
    if shape not in SHAPES:
        raise ValueError(f"shape not modeled in the signal spec: {shape!r}")
    rate_hz = float(theta_reference["rate_hz"])
    inc_t = np.uint64(ideal.phase_increment(float(theta_reference["carrier_hz"]), fs))
    inc_e = np.uint64(ideal.phase_increment(rate_hz, fs))
    n = np.arange(frames, dtype=np.uint64)
    phase_t = n * inc_t  # wraps modulo 2^64
    phase_e = n * inc_e
    e = _envelope_array(shape, phase_e, rate_hz)
    d = float(theta_reference["am_depth_percent"]) / 100.0
    a = 1.0 - d * (1.0 - e)
    return np.ascontiguousarray(a * ideal.ideal_sine(phase_t), dtype=np.float64)
