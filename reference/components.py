"""Reference component table (docs/signal-spec.md, Components; Story 3.1).

Implemented from the signal spec only, with the rules of reference/ideal.py
and reference/rate_curve.py, never from engine code, engine binaries, or
engine output (AD-16, AD-19). Every value is binary64 with NumPy's sine,
cosine, and square root; the same stable form of P(k, w) near 2 k w = 1 and
the same search bounds as the spec. Nothing is rendered, sampled, or
transformed.

- `Component`: one row, the fields layer ("theta_reference", "gamma_pac",
  "binaural"), ear ("left", "right"), center_hz, low_hz, high_hz, level (the
  line amplitude over the layer's carrier line), gamma_mult, theta_mult,
  beat_mult.
- `NoComponentModel(ValueError)`: a shape the spec has no model for, with
  parameter, value, rule ("no component model"), and limit; checked in the
  order theta shape, gamma carrier wave, binaural waveform.
- `component_table(recipe, mute="none")`: the table of a parsed recipe JSON
  in table order (the left ear's rows first; inside an ear the theta
  reference, the gamma PAC layer, then the binaural row; inside a layer by
  center_hz, then gamma_mult, theta_mult, beat_mult). It reads the three
  layer objects and mute ("none", "left", "right") only.
- `component_table_from_file(recipe_path, mute="none")`: the same from a file.

NumPy, the standard library, and reference/ only.
"""

import json
import math
from pathlib import Path
from typing import NamedTuple

import numpy as np

from . import rate_curve

LAYERS = ("theta_reference", "gamma_pac", "binaural")
EARS = ("left", "right")
NO_MODEL_RULE = "no component model"
THETA_SHAPES = "sine, smoothed_on_off, sawtooth, reverse_saw"
LEVEL_DB = 40.0          # row spectral-component-level
THETA_EDGE_MS = 10.0     # row theta-edge
BURST_WIDTH_MS = 50.0    # row burst-width
BURST_EDGE_MS = 10.0     # row burst-edge
THETA_HALF_ON = 0.25     # h = H / 2^64 (row theta-on-share, 50 percent)
_STABLE = 2.0**-5        # P(k, w) switches to the stable form below this |2 k w - 1|
_SLACK = 1.0 + 2.0**-20  # the search bounds look one term further on a rounding
_CYCLE = 2**64


class Component(NamedTuple):
    layer: str
    ear: str
    center_hz: float
    low_hz: float
    high_hz: float
    level: float
    gamma_mult: int
    theta_mult: int
    beat_mult: int


class NoComponentModel(ValueError):
    def __init__(self, parameter, value, limit):
        super().__init__(f"{parameter} {value}: {NO_MODEL_RULE} (limit {limit})")
        self.parameter = parameter
        self.value = value
        self.rule = NO_MODEL_RULE
        self.limit = limit


def threshold():
    """T = 10^(-L / 20) for the row value L in dB."""
    return 10.0 ** (-LEVEL_DB / 20.0)


def _edge_factor(k, w):
    """P(k, w) = cos(pi k w) / (1 - (2 k w)^2), pi / 4 at 2 k w = 1."""
    x = 2.0 * k * w
    delta = x - 1.0
    if abs(delta) >= _STABLE:
        return float(np.cos(math.pi * k * w)) / (1.0 - x * x)
    y = (math.pi / 2.0) * delta
    y2 = y * y
    s = 1.0 - y2 / 6.0 + y2 * y2 / 120.0 - y2 * y2 * y2 / 5040.0
    return (math.pi / 2.0) * s / (2.0 + delta)


def _edge_bound(k, w):
    x2 = (2.0 * k * w) ** 2
    return 1.0 if x2 <= 2.0 else 1.0 / (x2 - 1.0)


def _on_off(k, h, w):
    """Signed c_k of the smoothed on-off form (half on share h, edge share w)."""
    width = 2.0 * h - w
    if k == 0:
        return width
    k = abs(k)
    return float(np.sin(math.pi * k * width)) / (math.pi * k) * _edge_factor(k, w)


def _on_off_bound(k, w):
    return _edge_bound(k, w) / (math.pi * k)


def _sawtooth(k, w):
    """|c_k| of the sawtooth and the reverse saw."""
    if k == 0:
        return 0.5
    k = abs(k)
    pk = math.pi * k
    return abs(_edge_factor(k, w) + float(np.sin(math.pi * k * w)) / (pk * (1.0 - w))) / (2.0 * pk)


def _sawtooth_bound(k, w):
    pk = math.pi * k
    return (_edge_bound(k, w) + 1.0 / (pk * (1.0 - w))) / (2.0 * pk)


def _swing(layer, key):
    """(swing_hz, P0) of a rate cycle with swing above 0, else (0.0, 0)."""
    cycle = (layer or {}).get(key)
    if cycle is None or not float(cycle["swing_hz"]) > 0.0:
        return 0.0, 0
    return float(cycle["swing_hz"]), rate_curve.start_units(cycle["start_phase_deg"])


def _cos_units(units):
    """cos(2 pi units / 2^64) of an integer phase, from its signed value."""
    units %= _CYCLE
    signed = units - _CYCLE if units >= _CYCLE // 2 else units
    return float(np.cos(signed * (2.0 * math.pi / 2.0**64)))


def _sin_units(units):
    units %= _CYCLE
    signed = units - _CYCLE if units >= _CYCLE // 2 else units
    return float(np.sin(signed * (2.0 * math.pi / 2.0**64)))


def _theta_lines(theta, t):
    """[(theta_mult, amplitude)], the carrier first."""
    d = float(theta["am_depth_percent"]) / 100.0
    w = (THETA_EDGE_MS / 1000.0) * float(theta["rate_hz"])
    shape = theta["shape"]
    if shape == "sine":
        return [(0, 1.0 - d / 2.0), (1, d / 4.0), (-1, d / 4.0)]
    if shape == "smoothed_on_off":
        c0 = _on_off(0, THETA_HALF_ON, w)
        coefficient = lambda k: abs(_on_off(k, THETA_HALF_ON, w))  # noqa: E731
        bound = lambda k: _on_off_bound(k, w)  # noqa: E731
    else:
        c0 = 0.5
        coefficient = lambda k: _sawtooth(k, w)  # noqa: E731
        bound = lambda k: _sawtooth_bound(k, w)  # noqa: E731
    carrier = 1.0 - d + d * c0
    lines = [(0, carrier)]
    k = 1
    while d * bound(k) * _SLACK >= t * carrier:
        c = coefficient(k)
        lines += [(k, d * c), (-k, d * c)]
        k += 1
    return lines


def _whole(x):
    return x >= 0.0 and (x >= 2.0**53 or float(int(x)) == x)


def _gamma_lines(gamma, theta, t):
    """[(gamma_mult, theta_mult, amplitude)], the carrier first; coincident burst lines summed."""
    d = float(gamma["am_depth_percent"]) / 100.0
    coupling = gamma["coupling"]
    if coupling == "uncoupled":
        return [(0, 0, 1.0 - d / 2.0), (1, 0, d / 4.0), (-1, 0, d / 4.0)]
    if d == 0.0 or theta is None:
        return [(0, 0, 1.0)]
    if coupling == "smooth_swell":
        lines = [(0, 0, 1.0 - d / 4.0)]
        lines += [(0, j, d / 8.0) for j in (1, -1)]
        lines += [(i, 0, d / 8.0) for i in (1, -1)]
        lines += [(i, j, d / 16.0) for i in (1, -1) for j in (1, -1)]
        return lines
    theta_rate = float(theta["rate_hz"])
    h = (BURST_WIDTH_MS / 1000.0 / 2) * theta_rate
    w = (BURST_EDGE_MS / 1000.0) * theta_rate
    c_units = rate_curve.start_units(gamma["coupling_phase_deg"])
    gate = {}

    def g(j):
        j = abs(j)
        if j not in gate:
            gate[j] = _on_off(j, h, w)
        return gate[j]

    def last_j(scale, carrier):
        j = 0
        while scale * _on_off_bound(j + 1, w) * _SLACK >= t * carrier:
            j += 1
        return j

    def rotated(j, scale):
        units = (j * c_units) % _CYCLE
        v = scale * g(j)
        return complex(v * _cos_units(units), -v * _sin_units(units))

    def magnitude(*parts):
        z = sum(parts, 0j)
        return float(np.sqrt(z.real * z.real + z.imag * z.imag))

    n2 = None
    if _swing(gamma, "rate_cycle")[0] == 0.0 and _swing(theta, "rate_cycle")[0] == 0.0:
        two = 2.0 * float(gamma["rate_hz"])
        q = two / theta_rate
        if _whole(q) and q * theta_rate == two and q > 0.0:
            n2 = int(q)
    if n2 is not None and n2 % 2 == 0:
        n = n2 // 2

        def line(m):
            parts = [rotated(m, -d / 2.0), rotated(m - n, d / 4.0), rotated(m + n, d / 4.0)]
            if m == 0:
                parts.append(1.0 + 0j)
            return magnitude(*parts)

        carrier = line(0)
        last = n + last_j(d, carrier)
        return [(0, 0, carrier)] + [(0, m, line(m)) for m in range(-last, last + 1) if m != 0]
    carrier = 1.0 - d * g(0) / 2.0
    last = last_j(d / 2.0, carrier)
    lines = [(0, 0, carrier)]
    lines += [(0, j, d * abs(g(j)) / 2.0) for j in range(-last, last + 1) if j != 0]
    if n2 is None:
        lines += [(i, j, d * abs(g(j)) / 4.0) for j in range(-last, last + 1) for i in (1, -1)]
        return lines
    for j in range(-n2 - last, last + 1):
        amp = magnitude(rotated(j, d / 4.0), rotated(j + n2, d / 4.0))
        lines.append((1, j, amp) if abs(j) < abs(j + n2) else (-1, j + n2, amp))
    return lines


def _listed(center, half):
    """(center, low, high) after the below-0 Hz rule."""
    low, high = center - half, center + half
    if high <= 0.0:
        return -center, -high, -low
    if low < 0.0:
        return abs(center), 0.0, max(-low, high)
    return center, low, high


def _no_model(recipe):
    theta, gamma, binaural = (recipe.get(k) for k in LAYERS)
    if theta is not None and theta.get("shape") not in THETA_SHAPES.split(", "):
        raise NoComponentModel("/theta_reference/shape", str(theta.get("shape")), THETA_SHAPES)
    if gamma is not None and gamma.get("carrier_wave") != "sine":
        raise NoComponentModel("/gamma_pac/carrier_wave", str(gamma.get("carrier_wave")), "sine")
    if binaural is not None and binaural.get("waveform", "sine") != "sine":
        raise NoComponentModel("/binaural/waveform", str(binaural.get("waveform")), "sine")


def _sorted(rows):
    return sorted(rows, key=lambda r: (r[0], r[3], r[4], r[5]))


def component_table(recipe, mute="none"):
    """The component table of a parsed recipe JSON; see the module docstring."""
    if mute not in ("none", "left", "right"):
        raise ValueError(f"mute must be none, left, or right: {mute!r}")
    _no_model(recipe)
    t = threshold()
    theta, gamma, binaural = (recipe.get(k) for k in LAYERS)
    swing_theta, start_theta = _swing(theta, "rate_cycle")
    rows = {layer: [] for layer in LAYERS}  # (center, low, high, gamma_mult, theta_mult, beat_mult, level)

    if theta is not None:
        carrier_hz, rate = float(theta["carrier_hz"]), float(theta["rate_hz"])
        lines = _theta_lines(theta, t)
        carrier = lines[0][1]
        for k, amp in lines:
            level = amp / carrier
            if level >= t:
                c, lo, hi = _listed(carrier_hz + k * rate, abs(k) * swing_theta)
                rows["theta_reference"].append((c, lo, hi, 0, k, 0, level))

    if gamma is not None:
        carrier_hz, rate = float(gamma["carrier_hz"]), float(gamma["rate_hz"])
        theta_rate = float(theta["rate_hz"]) if theta is not None else 0.0
        swing_gamma, start_gamma = _swing(gamma, "rate_cycle")
        cos_between = _cos_units(start_gamma - start_theta)
        lines = _gamma_lines(gamma, theta, t)
        carrier = lines[0][2]
        for i, j, amp in lines:
            level = amp / carrier
            if not level >= t:
                continue
            a, b = i * swing_gamma, j * swing_theta
            if a != 0.0 and b != 0.0:
                half = float(np.sqrt(max(a * a + b * b + 2.0 * a * b * cos_between, 0.0)))
            else:
                half = abs(a) + abs(b)
            c, lo, hi = _listed(carrier_hz + (i * rate + j * theta_rate), half)
            rows["gamma_pac"].append((c, lo, hi, i, j, 0, level))

    binaural_rows = {"left": [], "right": []}
    if binaural is not None:
        left = float(binaural["carrier_left_hz"])
        if mute != "left":
            binaural_rows["left"].append((left, left, left, 0, 0, 0, 1.0))
        if mute != "right":
            swing, _ = _swing(binaural, "beat_rate_cycle")
            c, lo, hi = _listed(left + float(binaural["beat_rate_hz"]), swing)
            binaural_rows["right"].append((c, lo, hi, 0, 0, 1, 1.0))

    out = []
    for ear in EARS:
        for layer, layer_rows in (("theta_reference", rows["theta_reference"]), ("gamma_pac", rows["gamma_pac"]),
                                  ("binaural", binaural_rows[ear])):
            for c, lo, hi, i, j, b, level in _sorted(layer_rows):
                out.append(Component(layer, ear, float(c), float(lo), float(hi), float(level), int(i), int(j),
                                     int(b)))
    return out


def component_table_from_file(recipe_path, mute="none"):
    """The component table of the recipe file at recipe_path."""
    recipe = json.loads(Path(recipe_path).read_text(encoding="utf-8"))
    return component_table(recipe, mute)
