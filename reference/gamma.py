"""Reference render of the gamma PAC layer, uncoupled (docs/signal-spec.md, Gamma PAC layer; Story 2.2).

Implemented from the signal spec only, never from engine code, engine
binaries, or engine output (AD-16, AD-19), and not from reference/theta.py.
Every value is binary64 with the ideal functions (NumPy cosine and
reference/ideal.py's ideal sine), never the engine's approximation.

- CARRIER_WAVES: the carrier waves the spec models ("sine" only). The
  schema also accepts "triangle" and "softened_square", which compile
  rejects; render raises ValueError for them and for any other text.
- COUPLINGS: the couplings the spec models ("uncoupled" only); anything
  else raises ValueError.
- envelope(phase): the ideal envelope e = (1 + cos(2 pi p / 2^64)) / 2 of a
  gamma envelope phase p, peak 1 at phase 0 and 0 at the half cycle; phase
  an int (returns a float) or a uint64 ndarray (returns a float64 ndarray of
  the same shape). The cosine is taken of the signed phase, in
  [-2^63, 2^63), times 2 pi / 2^64.
- render(gamma_pac, fs, frames): the gamma tap of one channel,
  a[n] * ideal_sine(phase_G[n]) for n in [0, frames), with
  a = 1.0 - d * (1.0 - e[n]) in that order, d = am_depth_percent / 100.0
  (one binary64 division, the same for every sample: uncoupled), and both
  phases n * inc mod 2^64 (ideal.phase_increment of carrier_hz and rate_hz).

NumPy, the standard library, and reference/ only.
"""

import math

import numpy as np

from . import ideal

CARRIER_WAVES = ("sine",)
COUPLINGS = ("uncoupled",)

_RADIANS_PER_UNIT = 2.0 * math.pi / 2.0**64


def _envelope_array(p):
    s = p.view(np.int64).astype(np.float64)  # signed phase, in [-2^63, 2^63)
    return (1.0 + np.cos(s * _RADIANS_PER_UNIT)) / 2.0


def envelope(phase):
    """Ideal gamma envelope of an envelope phase (int or uint64 ndarray)."""
    if isinstance(phase, np.ndarray):
        return _envelope_array(np.ascontiguousarray(phase, dtype=np.uint64))
    p = np.array([int(phase) % 2**64], dtype=np.uint64)
    return float(_envelope_array(p)[0])


def _check(gamma_pac):
    wave = gamma_pac["carrier_wave"]
    if wave not in CARRIER_WAVES:
        raise ValueError(f"non-sine carrier not modeled: {wave!r}")
    coupling = gamma_pac["coupling"]
    if coupling not in COUPLINGS:
        raise ValueError(f"coupling not modeled in the signal spec: {coupling!r}")


def render(gamma_pac, fs, frames):
    """Gamma tap of one channel for n in [0, frames), binary64."""
    frames = int(frames)
    if frames < 0:
        raise ValueError(f"frames must be >= 0, got {frames}")
    _check(gamma_pac)
    inc_g = np.uint64(ideal.phase_increment(float(gamma_pac["carrier_hz"]), fs))
    inc_m = np.uint64(ideal.phase_increment(float(gamma_pac["rate_hz"]), fs))
    n = np.arange(frames, dtype=np.uint64)
    phase_g = n * inc_g  # wraps modulo 2^64
    phase_m = n * inc_m
    e = _envelope_array(phase_m)
    d = float(gamma_pac["am_depth_percent"]) / 100.0
    a = 1.0 - d * (1.0 - e)
    return np.ascontiguousarray(a * ideal.ideal_sine(phase_g), dtype=np.float64)
