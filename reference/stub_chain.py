"""Reference render of the stub chain (docs/signal-spec.md, Stub chain; Story 1.5; Story 2.1; Story 2.2; Story 2.3; Story 2.5; Story 2.7).

Implemented from the signal spec only, never from engine code, engine
binaries, or engine output (AD-16, AD-19). Every value is binary64 and every
oscillator uses the ideal sine of reference/ideal.py, never the engine's
approximation.

render(recipe_path, fs, frames=None, start=0, mode="measure") reads the recipe JSON with the
standard library and returns a dict with the keys "output", "theta",
"gamma", "bus", "join", "master", and (Story 4.4) "theta_gained",
"gamma_gained", "binaural", and "binaural_gained" (theta and gamma are
before each layer's gain). Each value is a 1-D C-contiguous
float64 array of 2 * T samples, interleaved stereo (left, right per frame),
for the frames [start, start + T), where T is `frames` when given and else
max(N - start, 0), N = seconds_to_samples(length_s, fs). Every sample at
frame n >= N is +0.0. A negative start raises ValueError. Each layer renders
the window straight from its frame indices (Story 2.7, ideal.frame_index),
so a window of a long session costs only its own frames.

loop_frames(recipe, fs) (docs/signal-spec.md, Loop, Frames; Story 2.7):
None for a recipe dict without `loop`, else a dict with
"opening_end_frame" O = seconds_to_samples(opening_s, fs), "body_frames"
B = seconds_to_samples(body_s, fs), "seam_frames" [O + k * B for k >= 1
while O + k * B < N], and "end_frame" N. It assumes a compile-accepted
loop (B > 0); looping changes no sample, so render() needs no loop term.

For 0 <= n < N and each channel c, in the spec's order:

    theta[c][n]  = theta.render(...)[n]       the same value in both channels
    gamma[c][n]  = gamma.render(...)[n]       the same value in both channels
    theta_g      = theta[c][n] * gT[n]       Story 4.4: gains from reference/gain.py
    gamma_g      = gamma[c][n] * gG[n]
    bus[c][n]    = theta_g + gamma_g
    bin[c][n]    = binaural.render(...)[c][n]   ear c (left, right)
    bin_g[c][n]  = bin[c][n] * gB[n]          one gain for both ears
    join[c][n]   = bus[c][n] + bin_g[c][n]
    master[c][n] = (join[c][n] * g) * gM[n]
    out[c][n]    = master[c][n]

with g = 1.0 in mode "measure" (the default) and, in mode "final" (Story
4.2; docs/signal-spec.md, Loudness gain, Linear gain), the linear gain of the
recipe's loudness_gain_db: k = round(100.0 * v), a tie away from zero, then
c^|k| by binary exponentiation with c = 0x1.004b7e9b5ce5dp+0, and 1 / p
for k < 0, every step one binary64 operation in the spec's order.

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
import math
from fractions import Fraction

import numpy as np

from . import binaural as binaural_layer, gain as gain_layer, gamma as gamma_layer, ideal, theta as theta_layer

KEYS = ("output", "theta", "gamma", "bus", "join", "master", "theta_gained", "gamma_gained", "binaural",
        "binaural_gained")
MODES = ("measure", "final")
GAIN_STEP = float.fromhex("0x1.004b7e9b5ce5dp+0")  # the binary64 nearest 10^(1/2000)


def gain_steps(gain_db):
    """Loudness gain, Linear gain: k, the integer nearest 100.0 * v (a tie away from zero)."""
    x = 100.0 * float(gain_db)                 # one binary64 rounding
    a = abs(Fraction(x))
    n = math.floor(a + Fraction(1, 2))         # exact
    return -n if x < 0 else n


def linear_gain(gain_db):
    """Loudness gain, Linear gain: g = c^|k| by binary exponentiation in binary64, 1 / p for k < 0."""
    k = gain_steps(gain_db)
    m, p, b = abs(k), 1.0, GAIN_STEP
    while m > 0:
        if m % 2 == 1:
            p = p * b
        m //= 2
        if m > 0:
            b = b * b
    return 1.0 / p if k < 0 else p


def _interleave(left, right, total):
    out = np.zeros(2 * total, dtype=np.float64)
    live = min(left.size, total)
    out[0:2 * live:2] = left[:live]
    out[1:2 * live:2] = right[:live]
    return out


def loop_frames(recipe, fs):
    """Opening end, body, seams, and end of a looping recipe dict, in frames; None without loop."""
    loop = recipe.get("loop")
    if loop is None:
        return None
    o = ideal.seconds_to_samples(float(loop["opening_s"]), fs)
    b = ideal.seconds_to_samples(float(loop["body_s"]), fs)
    end = ideal.seconds_to_samples(float(recipe["length_s"]), fs)
    if b <= 0:
        raise ValueError(f"loop body of {b} frames: not a compile-accepted loop")
    seams = list(range(o + b, end, b))
    return {"opening_end_frame": o, "body_frames": b, "seam_frames": seams, "end_frame": end}


def render(recipe_path, fs, frames=None, start=0, mode="measure"):
    """Taps and output of the stub chain for one recipe at sample rate fs, frames [start, start + T)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    with open(recipe_path, "r", encoding="utf-8") as f:
        recipe = json.load(f)
    if mode == "final":
        if "loudness_gain_db" not in recipe:
            raise ValueError("final mode needs loudness_gain_db")
        g = linear_gain(recipe["loudness_gain_db"])
    else:
        g = 1.0
    start = int(start)
    if start < 0:
        raise ValueError(f"start must be >= 0, got {start}")
    n_session = ideal.seconds_to_samples(float(recipe["length_s"]), fs)
    total = max(n_session - start, 0) if frames is None else int(frames)
    if total < 0:
        raise ValueError(f"frames must be >= 0, got {frames}")
    # The live frames of the window: start to min(N, start + T) - 1.
    n = np.arange(start, max(min(n_session, start + total), start), dtype=np.uint64)

    theta_ref = recipe.get("theta_reference")
    if theta_ref is not None:
        theta = theta_layer.render(theta_ref, fs, n)
    else:
        theta = np.zeros(n.size, dtype=np.float64)
    gamma_pac = recipe.get("gamma_pac")
    if gamma_pac is not None:
        gamma = gamma_layer.render(gamma_pac, fs, n, theta_ref)
    else:
        gamma = np.zeros(n.size, dtype=np.float64)
    # Story 4.4 (Gain ramps): each layer's gain after its before-gain tap,
    # the master gain after the loudness gain; 1.0 without a gain member.
    def schedule(holder):
        return None if holder is None else holder.get("gain")

    theta_g = theta * gain_layer.values(schedule(theta_ref), fs, n)
    gamma_g = gamma * gain_layer.values(schedule(gamma_pac), fs, n)
    bus = theta_g + gamma_g

    binaural = recipe.get("binaural")
    if binaural is not None:
        ears = binaural_layer.render(binaural, fs, n)
    else:
        ears = (np.zeros(n.size, dtype=np.float64), np.zeros(n.size, dtype=np.float64))
    g_binaural = gain_layer.values(schedule(binaural), fs, n)
    g_master = gain_layer.values(schedule(recipe.get("master")), fs, n)

    joins = []
    masters = []
    ears_g = []
    for c in (0, 1):
        ear_g = ears[c] * g_binaural
        ears_g.append(ear_g)
        join_c = bus + ear_g
        joins.append(join_c)
        masters.append((join_c * g) * g_master)

    out = {
        "theta": _interleave(theta, theta, total),
        "gamma": _interleave(gamma, gamma, total),
        "bus": _interleave(bus, bus, total),
        "join": _interleave(joins[0], joins[1], total),
        "master": _interleave(masters[0], masters[1], total),
        "theta_gained": _interleave(theta_g, theta_g, total),
        "gamma_gained": _interleave(gamma_g, gamma_g, total),
        "binaural": _interleave(ears[0], ears[1], total),
        "binaural_gained": _interleave(ears_g[0], ears_g[1], total),
    }
    out["output"] = out["master"].copy()
    return {key: np.ascontiguousarray(out[key]) for key in KEYS}
