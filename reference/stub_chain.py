"""Reference render of the stub chain (docs/signal-spec.md, Stub chain; Story 1.5).

Implemented from the signal spec only, never from engine code, engine
binaries, or engine output (AD-16, AD-19). Every value is binary64 and every
oscillator uses the ideal sine of reference/ideal.py, never the engine's
approximation.

render(recipe_path, fs, frames=None) reads the recipe JSON with the standard
library and returns a dict with the keys "output", "theta", "gamma", "bus",
"join", and "master". Each value is a 1-D C-contiguous float64 array of
2 * T samples, interleaved stereo (left, right per frame), where T is
`frames` when given and else N = seconds_to_samples(length_s, fs). Every
sample at frame n >= N is +0.0.

For 0 <= n < N and each channel c, in the spec's order:

    theta[c][n]  = a_T * sine(phase_T[n])     the same value in both channels
    gamma[c][n]  = +0.0
    bus[c][n]    = theta[c][n] + gamma[c][n]
    bin[c][n]    = a_c * sine(phase_c[n])
    join[c][n]   = bus[c][n] + bin[c][n]
    master[c][n] = join[c][n] * 1.0
    out[c][n]    = master[c][n]

with inc_T = phase_increment(theta_reference.carrier_hz, fs) and a_T = 1.0
when the recipe has `theta_reference` (else inc_T = 0, a_T = 0.0); f_L =
carrier_left_hz, f_R = carrier_left_hz + beat_rate_hz (one binary64
addition), inc_c = phase_increment(f_c, fs) and a_c = 1.0 when the recipe has
`binaural` (else 0 and 0.0); phase[n] = n * inc mod 2^64.

NumPy, the standard library, and reference/ only.
"""

import json

import numpy as np

from . import ideal

KEYS = ("output", "theta", "gamma", "bus", "join", "master")


def _oscillator(inc, amplitude, n_frames):
    """a * ideal_sine(n * inc mod 2^64) for n in [0, n_frames), binary64."""
    phases = np.arange(n_frames, dtype=np.uint64) * np.uint64(inc)  # wraps modulo 2^64
    return amplitude * ideal.ideal_sine(phases)


def _interleave(left, right, total):
    out = np.zeros(2 * total, dtype=np.float64)
    live = min(left.size, total)
    out[0:2 * live:2] = left[:live]
    out[1:2 * live:2] = right[:live]
    return out


def render(recipe_path, fs, frames=None):
    """Taps and output of the stub chain for one recipe at sample rate fs."""
    with open(recipe_path, "r", encoding="utf-8") as f:
        recipe = json.load(f)
    n_session = ideal.seconds_to_samples(float(recipe["length_s"]), fs)
    total = n_session if frames is None else int(frames)
    if total < 0:
        raise ValueError(f"frames must be >= 0, got {frames}")
    n = min(n_session, total)

    theta_ref = recipe.get("theta_reference")
    if theta_ref is not None:
        inc_t = ideal.phase_increment(float(theta_ref["carrier_hz"]), fs)
        a_t = 1.0
    else:
        inc_t = 0
        a_t = 0.0
    theta = _oscillator(inc_t, a_t, n)
    gamma = np.zeros(n, dtype=np.float64)
    bus = theta + gamma

    binaural = recipe.get("binaural")
    if binaural is not None:
        f_left = float(binaural["carrier_left_hz"])
        f_right = f_left + float(binaural["beat_rate_hz"])
        incs = (ideal.phase_increment(f_left, fs), ideal.phase_increment(f_right, fs))
        amps = (1.0, 1.0)
    else:
        incs = (0, 0)
        amps = (0.0, 0.0)

    joins = []
    masters = []
    for c in (0, 1):
        binaural_c = _oscillator(incs[c], amps[c], n)
        join_c = bus + binaural_c
        joins.append(join_c)
        masters.append(join_c * 1.0)

    out = {
        "theta": _interleave(theta, theta, total),
        "gamma": _interleave(gamma, gamma, total),
        "bus": _interleave(bus, bus, total),
        "join": _interleave(joins[0], joins[1], total),
        "master": _interleave(masters[0], masters[1], total),
    }
    out["output"] = out["master"].copy()
    return {key: np.ascontiguousarray(out[key]) for key in KEYS}
