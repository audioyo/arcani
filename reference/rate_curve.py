"""Reference rate cycle (docs/signal-spec.md, Rate curve; Stories 2.5 and 2.6).

Implemented from the signal spec only, with the rules of reference/ideal.py,
never from engine code, engine binaries, or engine output (AD-16, AD-19).
Every value is binary64 with the ideal functions (NumPy cosine), never the
engine's cycle cosine.

A cycle is a mapping with swing_hz, period_s, and start_phase_deg (the
binaural beat_rate_cycle, or a theta_reference or gamma_pac rate_cycle).

- start_units(deg): P0 by the coupling phase rule: x = deg / 360.0 (one
  binary64 division), x * 2^64 (exact) rounded to the nearest integer, ties
  to even, mod 2^64; a Python int.
- cycle_constants(cycle, fs): (P0, inc_P, K) with
  inc_P = ideal.phase_increment(1.0 / period_s, fs) and
  K = swing_hz * period_s / (2 * math.pi) in binary64.
- offset_cycles(cycle, fs, frames): the ideal U[n] in cycles for n in
  [0, frames), K * (cos(2 pi P0 / 2^64) - cos(2 pi p_P[n] / 2^64)) with
  p_P[n] = P0 + n * inc_P mod 2^64 and each cosine taken of the signed phase
  in [-2^63, 2^63) times 2 pi / 2^64; a float64 ndarray, zeros when cycle is
  None.
- cycles_to_units(v): the cycles-to-units rule on a float64 ndarray:
  (v mod 1) * 2^64 rounded to the nearest integer, ties to even, mod 2^64
  (numpy.trunc for the whole part, numpy.rint of the exact fraction times
  2^64, a negative value wrapped modulo 2^64); NaN, infinities, and
  |v| >= 2^52 give 0. A uint64 ndarray of the same shape.
- offset_units(cycle, fs, frames): cycles_to_units(offset_cycles(...)), the
  ideal U in phase units, a uint64 ndarray; zeros when cycle is None. A
  curved envelope phase is n * inc + offset_units mod 2^64.

NumPy, the standard library, and reference/ only.
"""

import math

import numpy as np

from . import ideal

_CYCLE = 2**64
_RADIANS_PER_UNIT = 2.0 * math.pi / 2.0**64


def start_units(deg):
    """P0 of a start phase in degrees; a Python int in [0, 2^64)."""
    x = float(deg) / 360.0
    return int(round(x * 2.0**64)) % _CYCLE  # x * 2^64 is exact; round() ties to even


def cycle_constants(cycle, fs):
    """(P0, inc_P, K) of a rate cycle at sample rate fs."""
    p0 = start_units(cycle["start_phase_deg"])
    period = float(cycle["period_s"])
    inc_p = ideal.phase_increment(1.0 / period, fs)
    k = float(cycle["swing_hz"]) * period / (2.0 * math.pi)
    return p0, inc_p, k


def _cosine(phases):
    s = np.ascontiguousarray(phases, dtype=np.uint64).view(np.int64).astype(np.float64)
    return np.cos(s * _RADIANS_PER_UNIT)


def _frames(frames):
    frames = int(frames)
    if frames < 0:
        raise ValueError(f"frames must be >= 0, got {frames}")
    return frames


def offset_cycles(cycle, fs, frames):
    """Ideal U[n] in cycles for n in [0, frames); zeros without a cycle."""
    frames = _frames(frames)
    if cycle is None:
        return np.zeros(frames, dtype=np.float64)
    p0, inc_p, k = cycle_constants(cycle, fs)
    n = np.arange(frames, dtype=np.uint64)
    phase_p = np.uint64(p0) + n * np.uint64(inc_p)  # wraps modulo 2^64
    c0 = float(_cosine(np.array([p0], dtype=np.uint64))[0])
    return k * (c0 - _cosine(phase_p))


def cycles_to_units(v):
    """The cycles-to-units rule on a float64 array; a uint64 array."""
    v = np.asarray(v, dtype=np.float64)
    out = np.zeros(v.shape, dtype=np.uint64)
    ok = np.abs(v) < 2.0**52  # False for NaN and both infinities
    f = v[ok] - np.trunc(v[ok])  # exact: the fraction bits of v, with its sign
    mag = np.rint(np.abs(f) * 2.0**64)  # exact scale, then ties to even; at most 2^64 - 2048
    units = mag.astype(np.uint64)
    neg = f < 0.0
    units[neg] = np.uint64(0) - units[neg]  # wraps modulo 2^64; 0 stays 0
    out[ok] = units
    return out


def offset_units(cycle, fs, frames):
    """Ideal U[n] in phase units for n in [0, frames); zeros without a cycle."""
    frames = _frames(frames)
    if cycle is None:
        return np.zeros(frames, dtype=np.uint64)
    return cycles_to_units(offset_cycles(cycle, fs, frames))
