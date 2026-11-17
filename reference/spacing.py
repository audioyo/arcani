"""Reference spacing rule (docs/signal-spec.md, Spacing; Story 3.2).

Implemented from the signal spec only, never from engine code, engine
binaries, or engine output (AD-16, AD-19). Every value is binary64 with
NumPy's sine, cosine, arc cosine, arc tangent, and square root; the first
time of a minimum is found in closed form. The table is the reference's own
(reference/components.py). Nothing is rendered or sampled.

- `SPACING_HZ = 50.0`: row spacing-rule.
- `SpacingPair`: the worst pair of one ear: ear, min_distance_hz, margin_hz
  (min distance less SPACING_HZ), component_1 and component_2 (table
  indices, the smaller first), and where (the where text of the error
  detail grammar, with this module's own numbers).
- `SpacingError(ValueError)`: parameter, value, rule ("spacing_rule"),
  limit, detail of the reported failure.
- `spacing_margins(recipe, mute="none")`: {"left": SpacingPair or None,
  "right": ...}; None with fewer than two layers in that ear. Filled for a
  rejected recipe too (its margins are below 0).
- `check_spacing(recipe, mute="none")`: None when every pair passes, else
  raises SpacingError for the smallest failing distance (ties to the left
  ear, then the smaller index of row 1, then of row 2).
- `pair_form(c_hz, di, dj, db, gamma=(0.0, 0.0), theta=(0.0, 0.0),
  beat=(0.0, 0.0))`: (x, y, h, min_distance_hz, first) of two rows that
  differ by c_hz and the multipliers, each cycle (swing_hz,
  start_phase_deg) on the 60 s period; first is the cycle fraction t / P of
  the first time of the minimum, None without a sweep.

NumPy, the standard library, and reference/ only.
"""

import math
from decimal import Decimal
from typing import NamedTuple

import numpy as np

from . import components, rate_curve

SPACING_HZ = 50.0       # row spacing-rule
RULE = "spacing_rule"
WHOLE_SESSION = "whole session"
LISTED_INTERVALS = "listed intervals, a row mirrored below 0 Hz"
CARRIER_FIELDS = {"gamma_pac": "/gamma_pac/carrier_hz", "binaural": "/binaural/carrier_left_hz"}
LAYER_ORDER = {"theta_reference": 0, "gamma_pac": 1, "binaural": 2}
_CYCLE = 2**64
_QUARTER = 2**62
_TWO_PI = 2.0 * math.pi


class SpacingPair(NamedTuple):
    ear: str
    min_distance_hz: float
    margin_hz: float
    component_1: int
    component_2: int
    where: str


class SpacingError(ValueError):
    def __init__(self, parameter, value, limit, detail):
        super().__init__(f"{parameter} {value}: {RULE} (limit {limit}); {detail}")
        self.parameter = parameter
        self.value = value
        self.rule = RULE
        self.limit = limit
        self.detail = detail


def _shortest(x):
    """The shortest round-trip text of a binary64, written as std::to_chars does
    (fixed or scientific, whichever is shorter, ties to fixed)."""
    x = float(x)
    if x == 0.0:
        return "-0" if math.copysign(1.0, x) < 0 else "0"
    sign, digit_tuple, exponent = Decimal(repr(x)).as_tuple()
    digits = "".join(str(d) for d in digit_tuple).lstrip("0")
    while len(digits) > 1 and digits.endswith("0"):
        digits = digits[:-1]
        exponent += 1
    n = len(digits)  # value = digits * 10^exponent
    if exponent >= 0:
        fixed = digits + "0" * exponent
    elif -exponent < n:
        fixed = digits[:n + exponent] + "." + digits[n + exponent:]
    else:
        fixed = "0." + "0" * (-exponent - n) + digits
    e = exponent + n - 1
    sci = digits[0] + ("." + digits[1:] if n > 1 else "") + f"e{'-' if e < 0 else '+'}{abs(e):02d}"
    return ("-" if sign else "") + (sci if len(sci) < len(fixed) else fixed)


def _cos_sin(units):
    """(cos, sin) of 2 pi units / 2^64, exact at the quarter points."""
    units %= _CYCLE
    if units % _QUARTER == 0:
        return ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))[units // _QUARTER]
    signed = units - _CYCLE if units >= _CYCLE // 2 else units
    angle = signed * (_TWO_PI / 2.0**64)
    return float(np.cos(angle)), float(np.sin(angle))


class _Cycle(NamedTuple):
    present: bool
    rate_hz: float
    swing_hz: float
    p0: int
    cos_phi: float
    sin_phi: float
    period_s: float


def _cycle(layer, rate_key, cycle_key):
    if layer is None:
        return _Cycle(False, 0.0, 0.0, 0, 0.0, 0.0, 0.0)
    rate = float(layer[rate_key])
    c = layer.get(cycle_key)
    if c is None or not float(c["swing_hz"]) > 0.0:
        return _Cycle(True, rate, 0.0, 0, 0.0, 0.0, 0.0)
    p0 = rate_curve.start_units(c["start_phase_deg"])
    cos_phi, sin_phi = _cos_sin(p0)
    return _Cycle(True, rate, float(c["swing_hz"]), p0, cos_phi, sin_phi, float(c["period_s"]))


def _cycles(recipe):
    """(gamma, theta, beat) cycles of a recipe."""
    return (_cycle(recipe.get("gamma_pac"), "rate_hz", "rate_cycle"),
            _cycle(recipe.get("theta_reference"), "rate_hz", "rate_cycle"),
            _cycle(recipe.get("binaural"), "beat_rate_hz", "beat_rate_cycle"))


def _xy(d, cycles):
    x = y = 0.0
    for dk, cyc in zip(d, cycles):
        a = dk * cyc.swing_hz
        x += a * cyc.cos_phi
        y += a * cyc.sin_phi
    return x, y


def _sweeps(mults, cycles):
    return any(m != 0 and cyc.swing_hz > 0.0 for m, cyc in zip(mults, cycles))


def _first_fraction(c, x, y, h):
    """The cycle fraction of the first time |c + x sin + y cos| is at its minimum."""
    if h == 0.0:
        return 0.0
    sigma = 1.0 if c >= 0.0 else -1.0
    m = (float(np.arctan2(-sigma * x, -sigma * y)) / _TWO_PI) % 1.0
    if abs(c) >= h:
        return m
    beta = float(np.arccos(min(1.0, abs(c) / h))) / _TWO_PI
    return min((m - beta) % 1.0, (m + beta) % 1.0)


def pair_form(c_hz, di, dj, db, gamma=(0.0, 0.0), theta=(0.0, 0.0), beat=(0.0, 0.0)):
    """See the module docstring."""
    cycles = []
    for swing, start in (gamma, theta, beat):
        layer = {"rate_hz": 0.0}
        if float(swing) > 0.0:
            layer["rate_cycle"] = {"swing_hz": float(swing), "period_s": 60.0, "start_phase_deg": float(start)}
        cycles.append(_cycle(layer, "rate_hz", "rate_cycle"))
    d = (int(di), int(dj), int(db))
    x, y = _xy(d, cycles)
    h = float(np.sqrt(x * x + y * y))
    distance = max(0.0, abs(float(c_hz)) - h)
    first = _first_fraction(float(c_hz), x, y, h) if _sweeps(d, cycles) else None
    return x, y, h, distance, first


def _mults(r):
    return (r.gamma_mult, r.theta_mult, r.beat_mult)


def _unmirrored_center(r, recipe):
    """The row's frequency at the center rates before the below-0 Hz rule."""
    theta, gamma, binaural = (recipe.get(k) for k in components.LAYERS)
    theta_rate = float(theta["rate_hz"]) if theta is not None else 0.0
    if r.layer == "theta_reference":
        return float(theta["carrier_hz"]) + r.theta_mult * theta_rate
    if r.layer == "gamma_pac":
        return float(gamma["carrier_hz"]) + (r.gamma_mult * float(gamma["rate_hz"]) + r.theta_mult * theta_rate)
    return float(binaural["carrier_left_hz"]) + r.beat_mult * float(binaural["beat_rate_hz"])


def _mirrored(r, recipe, cycles):
    x, y = _xy(_mults(r), cycles)
    return _unmirrored_center(r, recipe) - math.hypot(x, y) < 0.0


def _row_text(r):
    return f"{r.layer} ({r.gamma_mult}, {r.theta_mult}, {r.beat_mult}) at {_shortest(r.center_hz)} Hz"


def _pair(r1, r2, m1, m2, cycles):
    """(distance, where text) of two rows (Spacing, Distance of two rows)."""
    sweeps = _sweeps(_mults(r1), cycles) or _sweeps(_mults(r2), cycles)
    if m1 or m2:
        distance = max(0.0, r2.low_hz - r1.high_hz, r1.low_hz - r2.high_hz)
        return distance, (LISTED_INTERVALS if sweeps else WHOLE_SESSION)
    c = r1.center_hz - r2.center_hz
    d = tuple(a - b for a, b in zip(_mults(r1), _mults(r2)))
    x, y = _xy(d, cycles)
    h = float(np.sqrt(x * x + y * y))
    distance = max(0.0, abs(c) - h)
    if not sweeps:
        return distance, WHOLE_SESSION
    frac = _first_fraction(c, x, y, h)
    period = next(cyc.period_s for cyc in cycles if cyc.swing_hz > 0.0)
    parts = [f"first at {_shortest(frac * period)} s"]
    for name, cyc in zip(("gamma", "theta", "beat"), cycles):
        if not cyc.present:
            parts.append(f"{name} rate none")
            continue
        rate = cyc.rate_hz
        if cyc.swing_hz > 0.0:
            rate = cyc.rate_hz + cyc.swing_hz * float(np.sin(_TWO_PI * frac + _TWO_PI * cyc.p0 / 2.0**64))
        parts.append(f"{name} rate {_shortest(rate)} Hz")
    return distance, ", ".join(parts)


def _evaluate(recipe, mute):
    table = components.component_table(recipe, mute)
    cycles = _cycles(recipe)
    mirrored = [_mirrored(r, recipe, cycles) for r in table]
    margins = {}
    failure = None  # (distance, ear index, i, j, where)
    for e, ear in enumerate(components.EARS):
        worst = None
        rows = [(i, r) for i, r in enumerate(table) if r.ear == ear]
        for a in range(len(rows)):
            for b in range(a + 1, len(rows)):
                (i, r1), (j, r2) = rows[a], rows[b]
                if r1.layer == r2.layer:
                    continue
                distance, where = _pair(r1, r2, mirrored[i], mirrored[j], cycles)
                if worst is None or distance < worst[0]:
                    worst = (distance, i, j, where)
                if distance < SPACING_HZ and (failure is None or distance < failure[0]):
                    failure = (distance, e, i, j, where)
        margins[ear] = None if worst is None else SpacingPair(
            ear, worst[0], worst[0] - SPACING_HZ, worst[1], worst[2], worst[3])
    return table, margins, failure


def spacing_margins(recipe, mute="none"):
    """See the module docstring."""
    return _evaluate(recipe, mute)[1]


def check_spacing(recipe, mute="none"):
    """See the module docstring."""
    table, _, failure = _evaluate(recipe, mute)
    if failure is None:
        return None
    distance, e, i, j, where = failure
    r1, r2 = table[i], table[j]
    later = r1.layer if LAYER_ORDER[r1.layer] > LAYER_ORDER[r2.layer] else r2.layer
    detail = f"{components.EARS[e]} ear: {_row_text(r1)} and {_row_text(r2)}; {where}"
    raise SpacingError(CARRIER_FIELDS[later], _shortest(distance), f">= {_shortest(SPACING_HZ)} Hz (row spacing-rule)",
                       detail)
