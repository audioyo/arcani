"""Reference render of the gamma PAC layer (docs/signal-spec.md, Gamma PAC layer, Coupling, and Bursts; Stories 2.2, 2.3, and 2.4).

Implemented from the signal spec only, never from engine code, engine
binaries, or engine output (AD-16, AD-19), and not from reference/theta.py.
Every value is binary64 with the ideal functions (NumPy cosine and
reference/ideal.py's ideal sine), never the engine's approximation.

- CARRIER_WAVES: the carrier waves the spec models ("sine" only). The
  schema also accepts "triangle" and "softened_square", which compile
  rejects; render raises ValueError for them and for any other text.
- COUPLINGS: the couplings the spec models ("uncoupled", "smooth_swell",
  and "bursts"); anything else raises ValueError.
- BURST_WIDTH_MS, BURST_EDGE_MS: the burst constants in row units (range
  rows burst-width, the full width, and burst-edge).
- burst_half_width_units(rate_hz): Hb = ((BURST_WIDTH_MS / 1000) / 2 *
  rate_hz) * 2^64, rounded, with one binary64 rounding in 50 / 1000 and one
  in the product with rate_hz; a Python int.
- burst_edge_units(rate_hz): Wb = ((BURST_EDGE_MS / 1000) * rate_hz) * 2^64,
  rounded, with one binary64 rounding in each step; a Python int.
- burst(theta_envelope_phase, c_units, hb_units, wb_units): the ideal burst
  gate g of the Bursts section. u = p_E - C mod 2^64, m = u, or 2^64 - u
  past the half cycle; 1 for m <= Hb - Wb, (1 + cos(pi * r)) / 2 with
  r = (m - (Hb - Wb)) / Wb (one binary64 division) for Hb - Wb < m < Hb,
  0 for m >= Hb, chosen by exact integer comparisons. An int phase returns
  a float, a uint64 ndarray a float64 ndarray of the same shape.
- coupling_phase_units(deg): C, the coupling phase rule of the Coupling
  section: x = deg / 360.0 (one binary64 division), x * 2^64 (exact)
  rounded to the nearest integer, ties to even, modulo 2^64; a Python int.
- swell(theta_envelope_phase, c_units): the ideal smooth swell
  s = (1 + cos(2 pi (p_E - C) / 2^64)) / 2, 1 at the coupling phase and 0
  half a theta cycle away; the cosine is taken of the signed phase
  p_E - C mod 2^64, in [-2^63, 2^63), times 2 pi / 2^64. An int phase
  returns a float, a uint64 ndarray a float64 ndarray of the same shape.
- envelope(phase): the ideal envelope e = (1 + cos(2 pi p / 2^64)) / 2 of a
  gamma envelope phase p, peak 1 at phase 0 and 0 at the half cycle; phase
  an int (returns a float) or a uint64 ndarray (returns a float64 ndarray of
  the same shape). The cosine is taken of the signed phase, in
  [-2^63, 2^63), times 2 pi / 2^64.
- render(gamma_pac, fs, frames, theta_reference=None): the gamma tap of one
  channel, a[n] * ideal_sine(phase_G[n]) for n in [0, frames), with
  d = am_depth_percent / 100.0 (one binary64 division) and both gamma
  phases n * inc mod 2^64 (ideal.phase_increment of carrier_hz and
  rate_hz). Uncoupled: a = 1.0 - d * (1.0 - e[n]) in that order, the same d
  for every sample. smooth_swell: a = 1.0 - (d * s[n]) * (1.0 - e[n]) in
  that order, s[n] = swell(p_E[n], C), with the theta envelope phase
  p_E[n] = n * inc_E mod 2^64, inc_E = ideal.phase_increment of
  theta_reference["rate_hz"] (0 when theta_reference is None, so p_E = 0).
  bursts: a = 1.0 - (d * g[n]) * (1.0 - e[n]) in that order,
  g[n] = burst(p_E[n], C, Hb, Wb), with Hb and Wb at theta_reference
  ["rate_hz"] (0 without a theta reference). The gamma envelope phase runs
  free for every coupling. smooth_swell or bursts without coupling_phase_deg
  raises ValueError.

NumPy, the standard library, and reference/ only.
"""

import math

import numpy as np

from . import ideal

CARRIER_WAVES = ("sine",)
COUPLINGS = ("uncoupled", "smooth_swell", "bursts")
BURST_WIDTH_MS = 50.0
BURST_EDGE_MS = 10.0

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


def coupling_phase_units(deg):
    """C of a coupling phase in degrees; a Python int in [0, 2^64)."""
    x = float(deg) / 360.0
    return int(round(x * 2.0**64)) % 2**64  # x * 2^64 is exact; round() ties to even


def swell(theta_envelope_phase, c_units):
    """Ideal smooth swell of a theta envelope phase (int or uint64 ndarray)."""
    c = np.uint64(int(c_units) % 2**64)
    if isinstance(theta_envelope_phase, np.ndarray):
        u = np.ascontiguousarray(theta_envelope_phase, dtype=np.uint64) - c  # wraps modulo 2^64
        return _envelope_array(u)
    u = np.array([(int(theta_envelope_phase) - int(c)) % 2**64], dtype=np.uint64)
    return float(_envelope_array(u)[0])


def burst_half_width_units(rate_hz):
    """Hb, half the burst width in theta envelope phase units; a Python int."""
    half_width_s = BURST_WIDTH_MS / 1000.0 / 2.0
    w = half_width_s * float(rate_hz)
    return int(round(w * 2.0**64))  # w * 2^64 is exact; round() ties to even


def burst_edge_units(rate_hz):
    """Wb, one burst edge in theta envelope phase units; a Python int."""
    e = BURST_EDGE_MS / 1000.0
    w = e * float(rate_hz)
    return int(round(w * 2.0**64))


def _burst_array(u, hb, wb):
    """Ideal gate of uint64 offsets u = p_E - C from the burst center."""
    m = np.where(u < np.uint64(2**63), u, np.uint64(0) - u)  # wraps modulo 2^64
    out = np.zeros(u.shape, dtype=np.float64)
    plateau_end = np.uint64(hb - wb)
    out[m <= plateau_end] = 1.0
    edge = (m > plateau_end) & (m < np.uint64(hb))
    if np.any(edge):
        r = (m[edge] - plateau_end).astype(np.float64) / float(wb)
        out[edge] = (1.0 + np.cos(math.pi * r)) / 2.0
    return out


def burst(theta_envelope_phase, c_units, hb_units, wb_units):
    """Ideal burst gate of a theta envelope phase (int or uint64 ndarray)."""
    c = np.uint64(int(c_units) % 2**64)
    hb, wb = int(hb_units), int(wb_units)
    if isinstance(theta_envelope_phase, np.ndarray):
        u = np.ascontiguousarray(theta_envelope_phase, dtype=np.uint64) - c  # wraps modulo 2^64
        return _burst_array(u, hb, wb)
    u = np.array([(int(theta_envelope_phase) - int(c)) % 2**64], dtype=np.uint64)
    return float(_burst_array(u, hb, wb)[0])


def _check(gamma_pac):
    wave = gamma_pac["carrier_wave"]
    if wave not in CARRIER_WAVES:
        raise ValueError(f"non-sine carrier not modeled: {wave!r}")
    coupling = gamma_pac["coupling"]
    if coupling not in COUPLINGS:
        raise ValueError(f"coupling not modeled in the signal spec: {coupling!r}")
    if coupling in ("smooth_swell", "bursts") and "coupling_phase_deg" not in gamma_pac:
        raise ValueError("coupled gamma needs a coupling phase")


def render(gamma_pac, fs, frames, theta_reference=None):
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
    coupling = gamma_pac["coupling"]
    if coupling in ("smooth_swell", "bursts"):
        rate = 0.0 if theta_reference is None else float(theta_reference["rate_hz"])
        inc_e = np.uint64(ideal.phase_increment(rate, fs) if theta_reference is not None else 0)
        phase_e = n * inc_e  # theta envelope phase, wraps modulo 2^64
        c = coupling_phase_units(gamma_pac["coupling_phase_deg"])
        if coupling == "smooth_swell":
            s = swell(phase_e, c)
        else:
            s = burst(phase_e, c, burst_half_width_units(rate), burst_edge_units(rate))
        a = 1.0 - (d * s) * (1.0 - e)
    else:
        a = 1.0 - d * (1.0 - e)
    return np.ascontiguousarray(a * ideal.ideal_sine(phase_g), dtype=np.float64)
