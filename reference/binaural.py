"""Reference render of the binaural layer (docs/signal-spec.md, Binaural layer and Rate curve; Story 2.5).

Implemented from the signal spec only, with the rules of reference/ideal.py,
never from engine code, engine binaries, or engine output (AD-16, AD-19).
Every value is binary64 with the ideal functions (NumPy cosine and sine,
reference/ideal.py's ideal sine), never the engine's approximation.

- WAVEFORMS: the binaural waveforms the spec models ("sine" only). The
  schema also accepts "triangle", which compile rejects; render raises
  ValueError for it and for any other text. An absent waveform is sine.
- cycle_constants(cycle, fs): (P0, inc_P, K) of a beat_rate_cycle object:
  P0 by the coupling phase rule on start_phase_deg (x = deg / 360.0, one
  binary64 division, x * 2^64 exact, rounded to the nearest integer, ties to
  even, mod 2^64), inc_P = ideal.phase_increment(1.0 / period_s, fs), and
  K = swing_hz * period_s / (2 * math.pi) in binary64.
- beat_offset_cycles(binaural, fs, frames): the ideal U[n] in cycles,
  K * (cos(2 pi P0 / 2^64) - cos(2 pi p_P[n] / 2^64)) with
  p_P[n] = P0 + n * inc_P mod 2^64 and each cosine taken of the signed phase
  in [-2^63, 2^63) times 2 pi / 2^64; zeros without a cycle.
- render(binaural, fs, frames): (left, right), each a float64 array of
  `frames` samples: left = ideal_sine(n * inc_L mod 2^64), inc_L from
  carrier_left_hz; f_C = carrier_left_hz + beat_rate_hz (one binary64
  addition), phase_C[n] = n * inc_C mod 2^64. Without a cycle the right ear
  is ideal_sine(phase_C); with one, y = phase_C / 2^64 + U in binary64,
  reduced to [-1/2, 1/2) by subtracting the nearest integer, and the right
  ear is sin(2 pi y).

NumPy, the standard library, and reference/ only.
"""

import math

import numpy as np

from . import ideal

WAVEFORMS = ("sine",)

_CYCLE = 2**64
_RADIANS_PER_UNIT = 2.0 * math.pi / 2.0**64


def _check(binaural):
    wave = binaural.get("waveform", "sine")
    if wave not in WAVEFORMS:
        raise ValueError(f"non-sine binaural not modeled: {wave!r}")


def _start_units(deg):
    x = float(deg) / 360.0
    return int(round(x * 2.0**64)) % _CYCLE  # x * 2^64 is exact; round() ties to even


def cycle_constants(cycle, fs):
    """(P0, inc_P, K) of a beat_rate_cycle object at sample rate fs."""
    p0 = _start_units(cycle["start_phase_deg"])
    period = float(cycle["period_s"])
    inc_p = ideal.phase_increment(1.0 / period, fs)
    k = float(cycle["swing_hz"]) * period / (2.0 * math.pi)
    return p0, inc_p, k


def _cosine(phases):
    s = np.ascontiguousarray(phases, dtype=np.uint64).view(np.int64).astype(np.float64)
    return np.cos(s * _RADIANS_PER_UNIT)


def beat_offset_cycles(binaural, fs, frames):
    """Ideal U[n] in cycles for n in [0, frames); zeros without a cycle."""
    frames = int(frames)
    if frames < 0:
        raise ValueError(f"frames must be >= 0, got {frames}")
    cycle = binaural.get("beat_rate_cycle")
    if cycle is None:
        return np.zeros(frames, dtype=np.float64)
    p0, inc_p, k = cycle_constants(cycle, fs)
    n = np.arange(frames, dtype=np.uint64)
    phase_p = np.uint64(p0) + n * np.uint64(inc_p)  # wraps modulo 2^64
    c0 = float(_cosine(np.array([p0], dtype=np.uint64))[0])
    return k * (c0 - _cosine(phase_p))


def render(binaural, fs, frames):
    """(left, right) binaural ears for n in [0, frames), binary64."""
    frames = int(frames)
    if frames < 0:
        raise ValueError(f"frames must be >= 0, got {frames}")
    _check(binaural)
    f_left = float(binaural["carrier_left_hz"])
    f_center = f_left + float(binaural["beat_rate_hz"])
    n = np.arange(frames, dtype=np.uint64)
    phase_l = n * np.uint64(ideal.phase_increment(f_left, fs))  # wraps modulo 2^64
    phase_c = n * np.uint64(ideal.phase_increment(f_center, fs))
    left = np.ascontiguousarray(ideal.ideal_sine(phase_l), dtype=np.float64)
    if binaural.get("beat_rate_cycle") is None:
        right = ideal.ideal_sine(phase_c)
    else:
        y = phase_c.astype(np.float64) / 2.0**64 + beat_offset_cycles(binaural, fs, frames)
        y = y - np.rint(y)
        right = np.sin(2.0 * math.pi * y)
    return left, np.ascontiguousarray(right, dtype=np.float64)
