"""Reference render of the stub chain (docs/signal-spec.md, Stub chain; Story 1.5; Story 2.1; Story 2.2; Story 2.3; Story 2.5).

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

    theta[c][n]  = theta.render(...)[n]       the same value in both channels
    gamma[c][n]  = gamma.render(...)[n]       the same value in both channels
    bus[c][n]    = theta[c][n] + gamma[c][n]
    bin[c][n]    = binaural.render(...)[c][n]   ear c (left, right)
    join[c][n]   = bus[c][n] + bin[c][n]
    master[c][n] = join[c][n] * 1.0
    out[c][n]    = master[c][n]

with the theta tap from reference/theta.py (docs/signal-spec.md, Theta
reference: the carrier amplitude-modulated at the theta rate by the recipe's
envelope shape and depth) when the recipe has `theta_reference`, else +0.0;
the gamma tap from reference/gamma.py (docs/signal-spec.md, Gamma PAC layer:
a sine carrier amplitude-modulated at the gamma rate, its depth constant
when uncoupled; Coupling: with smooth_swell its depth follows the theta
reference envelope phase; Bursts: with bursts the burst gate of that phase
scales it; so the recipe's theta_reference is passed in)
when the recipe has `gamma_pac`, else +0.0; and both ears from
reference/binaural.py (docs/signal-spec.md, Binaural layer and Rate curve:
a pure sine per ear, the right carrier the left carrier plus the beat rate,
with the beat rate cycle's closed-form phase offset when the recipe has
`beat_rate_cycle`) when the recipe has `binaural`, else +0.0.

NumPy, the standard library, and reference/ only.
"""

import json

import numpy as np

from . import binaural as binaural_layer, gamma as gamma_layer, ideal, theta as theta_layer

KEYS = ("output", "theta", "gamma", "bus", "join", "master")


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
        theta = theta_layer.render(theta_ref, fs, n)
    else:
        theta = np.zeros(n, dtype=np.float64)
    gamma_pac = recipe.get("gamma_pac")
    if gamma_pac is not None:
        gamma = gamma_layer.render(gamma_pac, fs, n, theta_ref)
    else:
        gamma = np.zeros(n, dtype=np.float64)
    bus = theta + gamma

    binaural = recipe.get("binaural")
    if binaural is not None:
        ears = binaural_layer.render(binaural, fs, n)
    else:
        ears = (np.zeros(n, dtype=np.float64), np.zeros(n, dtype=np.float64))

    joins = []
    masters = []
    for c in (0, 1):
        join_c = bus + ears[c]
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
