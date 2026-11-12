"""Writes the worked test vectors of docs/signal-spec.md: core, sine, internal block size, stub chain, theta reference, gamma PAC layer, coupling, binaural layer and rate curve, 24-bit rounding.

Usage:
  python tools/signal_spec_vectors.py            write tests/data/signal_spec_vectors.json
  python tools/signal_spec_vectors.py --check    exit 0 if the file equals a fresh run, else 1
  python tools/signal_spec_vectors.py --tables   print the spec's vector tables as Markdown
  --out FILE selects another file for writing and --check.

Every value comes from exact or high-precision arithmetic, never from the
engine or from binary64 library calls:

- Increment rule: q is the binary64 nearest to the exact rational
  f_hz * 2^64 / fs (Python's float(Fraction) is correctly rounded, which is
  what one IEEE binary64 division of two exact operands gives). inc is q
  rounded to the nearest integer, ties to even, in exact Fraction arithmetic.
- Seconds to samples: the product t_s * fs is rounded to binary64 the same
  way, then to the nearest integer, ties to even.
- Ideal sine: sin(2*pi*phase/2^64) in decimal arithmetic at 60 digits (pi by
  Machin's formula, sine by its Taylor series after exact reduction), written
  with 25 significant digits.
- Sine coefficients: the binary64 nearest to 1/k!, written as hex floats.
- Engine sine bits: the spec's engine sine algorithm evaluated in Python
  binary64 floats (IEEE 754, round to nearest, no fused multiply-add) in the
  spec's exact operation order, written as the 64-bit pattern of the result.
  This pins the engine's exact output bits: a wrong constant or a reordered
  Horner step that stays under the error bound still changes them. It lives
  here, in tools/, never in reference/ (the reference renders the ideal sine).
- Internal blocks: frame k lies in block k // 64 at offset k % 64, exact
  integer arithmetic.
- Stub chain: the spec's stub chain (Story 1.2, theta reference oscillator
  Story 1.5) for the 1 s binaural fixtures, in binary64 in the spec's
  operation order, from the engine sine bits above, written as 64-bit
  patterns, plus the ideal values of the same phases at 25 digits for the
  Python reference: the ideal sine of the theta phase, and per channel the
  exact sum of the ideal theta sine and the ideal binaural sine (the ideal
  output), rounded once to 25 digits.
- Theta reference (Story 2.1): the spec's envelope, ratio-to-phase, and
  edge rules evaluated in binary64 in the spec's operation order (engine
  bits, from the engine sine bits above), and the ideal values of the same
  phases at 25 digits: ideal cosines in decimal arithmetic, exact ratios,
  and the exact depth law on the binary64 depth, for the Python reference.
- Gamma PAC layer, uncoupled (Story 2.2): the spec's AM law (the sine
  envelope at the gamma rate, a constant depth) evaluated in binary64 in the
  spec's operation order (engine bits), and the ideal values at 25 digits:
  the ideal cosine and sine in decimal arithmetic and the exact depth law on
  the binary64 depth. The bus of the theta and gamma fixture is one binary64
  addition of the two engine taps; its ideal is the exact sum of the two
  ideal taps, rounded once to 25 digits.
- Coupling, smooth swell (Story 2.3): the coupling phase rule in exact
  Fraction arithmetic (x = deg / 360 is one binary64 division), and the
  swell law s = sine_envelope(p_E - C), a = 1 - (d * s) * (1 - e) evaluated
  in binary64 in the spec's operation order (engine bits), with the ideal
  values at 25 digits: ideal cosines and sine in decimal arithmetic and the
  exact law on the binary64 depth. The bus is one binary64 addition of the
  engine theta and gamma taps; its ideal is the exact sum of the ideal taps.
- Binaural layer and rate curve (Story 2.5): the cycles-to-units rule in
  exact Fraction arithmetic, the rate cycle constants (P0 by the coupling
  phase rule, inc_P by the increment rule on 1.0 / P, K = (s * P) * the
  binary64 nearest 1 / (2 pi), checked against decimal pi), and the right
  ear phase phase_C + U evaluated in binary64 in the spec's operation order
  (engine bits), with ideal values at 25 digits: the exact K = s P / (2 pi),
  ideal cosines of the integer cycle phases, and the ideal sine of
  phase_C / 2^64 + U in decimal arithmetic. The ideal rate-curve law
  (rate and beat phase at chosen times) is exact in decimal arithmetic.
- 24-bit rounding (Story 1.4): x = s * 2^23 in exact Fraction arithmetic,
  clamped to [-8388608, 8388607], else rounded to the nearest integer, ties
  to even; NaN gives 0. Written as 3 bytes, little-endian two's complement.

Standard library only.
"""

import argparse
import functools
import json
import math
import struct
import sys
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "tests" / "data" / "signal_spec_vectors.json"

CYCLE = 2**64
PREC = 60
DIGITS = 25
RATES = (44100, 48000)


# ------------------------------------------------------------ exact rules


def round_half_even(x):
    """Nearest integer to the Fraction x, ties to even."""
    x = Fraction(x)
    floor = x.numerator // x.denominator
    rest = x - floor
    if rest > Fraction(1, 2):
        return floor + 1
    if rest < Fraction(1, 2):
        return floor
    return floor if floor % 2 == 0 else floor + 1


def binary64(x):
    """The binary64 nearest to the exact value x (ties to even)."""
    return float(Fraction(x))


def increment(f_hz, fs):
    """Spec increment rule; f_hz is a binary64 value (float)."""
    if not (f_hz >= 0.0 and f_hz < fs / 2):
        return 0, None
    if f_hz == 0.0:
        return 0, f_hz  # keeps the sign of zero, as binary64 arithmetic does
    q = binary64(Fraction(f_hz) * CYCLE / fs)
    return round_half_even(Fraction(q)), q


def samples(t_s, fs):
    """Spec seconds-to-samples rule; t_s is a binary64 value (float)."""
    if not (t_s >= 0.0):
        return 0, None
    if math.isinf(t_s):
        return 0, None
    product = binary64(Fraction(t_s) * fs)
    if product >= 2.0**64:
        return 0, product
    return round_half_even(Fraction(product)), product


# ---------------------------------------------------------- decimal sine


@functools.lru_cache(maxsize=None)
def decimal_pi():
    """pi by Machin's formula, at the current decimal precision."""

    def arctan_inv(x):
        x = Decimal(x)
        total = Decimal(0)
        term = 1 / x
        x2 = x * x
        k = 0
        while True:
            delta = term / (2 * k + 1)
            if delta == 0:
                break
            total += -delta if k % 2 else delta
            term /= x2
            k += 1
        return total

    return 4 * (4 * arctan_inv(5) - arctan_inv(239))


def ideal_sine(phase):
    """sin(2*pi*phase/2^64) as a Decimal string with DIGITS significant digits."""
    return format_ideal(ideal_sine_decimal(phase))


def ideal_sine_decimal(phase):
    """sin(2*pi*phase/2^64) as a Decimal at about PREC digits."""
    phase %= CYCLE
    # Exact reduction to [-2^62, 2^62] with sin symmetry, so the series argument
    # is at most pi/2 in size.
    s = phase - CYCLE if phase >= CYCLE // 2 else phase
    if s > CYCLE // 4:
        s = CYCLE // 2 - s
    elif s < -(CYCLE // 4):
        s = -(CYCLE // 2) - s
    if s == 0:
        return Decimal(0)
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        x = 2 * decimal_pi() * Decimal(s) / Decimal(CYCLE)
        total = Decimal(0)
        term = x
        k = 1
        while abs(term) > Decimal(10) ** -(PREC + 5):
            total += term
            term = -term * x * x / ((k + 1) * (k + 2))
            k += 2
        total += term
    return total


def format_ideal(total):
    """A Decimal written with DIGITS significant digits ("0" for zero)."""
    if total == 0:
        return "0"
    with localcontext() as ctx:
        ctx.prec = DIGITS
        value = +total
    if value == value.to_integral_value() and abs(value) == 1:
        return "1" if value > 0 else "-1"
    return format(value, "f") if abs(value) >= Decimal("1e-6") else format(value, "e")


# --------------------------------------------------------------- vectors


def hexf(x):
    if math.isnan(x):
        return "nan"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return float.hex(x)


def dec(x):
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return repr(x)


SINE_POWERS = (1, 3, 5, 7, 9, 11)
# Binary64 nearest to pi, times 2^-63 (exact): the binary64 nearest to 2*pi/2^64.
RADIANS_PER_UNIT_HEX = "0x1.921fb54442d18p-62"


def engine_sine(phase):
    """Spec engine sine (Sine, steps 1 to 3) in binary64, exact operation order."""
    p = phase % CYCLE
    # Step 1: exact integer fold, unsigned mod 2^64, then read as signed.
    if CYCLE // 4 < p < CYCLE // 2 + CYCLE // 4:
        p = (CYCLE // 2 - p) % CYCLE
    s = p - CYCLE if p >= CYCLE // 2 else p
    # Step 2: one conversion (Python's float(int) rounds to nearest, ties to
    # even), then one multiply.
    x = float(s) * float.fromhex(RADIANS_PER_UNIT_HEX)
    # Step 3: fixed Horner order, one rounding per operation.
    c = {r["power"]: float.fromhex(r["hex"]) for r in sine_coefficients()}
    z = x * x
    r = c[11]
    r = r * z + c[9]
    r = r * z + c[7]
    r = r * z + c[5]
    r = r * z + c[3]
    r = r * z + c[1]
    return r * x


def bits(x):
    return "0x" + struct.pack(">d", x).hex()


def sine_coefficients():
    rows = []
    for k in SINE_POWERS:
        sign = -1 if (k // 2) % 2 else 1
        value = sign * binary64(Fraction(1, math.factorial(k)))
        rows.append({
            "power": k,
            "exact": f"{'-' if sign < 0 else '+'}1/{k}!",
            "hex": float.hex(value),
        })
    return rows


EXACT_PHASES = (
    ("0", 0),
    ("2^61", 2**61),
    ("2^62", 2**62),
    ("2^63", 2**63),
    ("3*2^62", 3 * 2**62),
)

# (label, f_hz) carriers and rates from the locked ranges and the starters.
INCREMENT_SIGNALS = (
    ("theta rate, low end", 1.0),
    ("theta rate, Sleep delta", 2.0),
    ("theta rate, Learn", 5.5),
    ("theta rate, high end", 6.0),
    ("gamma rate, low end", 30.0),
    ("gamma rate, default", 40.0),
    ("gamma rate, high end", 60.0),
    ("theta carrier, low end; binaural carrier, Sleep", 100.0),
    ("gamma carrier, low end", 200.0),
    ("gamma carrier, starter", 250.0),
    ("theta carrier, starter", 450.0),
    ("theta and gamma carrier, high end", 500.0),
    ("binaural carrier, high end", 1000.0),
    ("binaural right ear, high end (1000 Hz plus 30 Hz)", 1030.0),
    ("beat rate, high end", 30.0),
)


def band_tie(base, fs):
    """First binary64 f at or above base whose binary64 q is exactly k + 1/2."""
    f = base
    while True:
        q = binary64(Fraction(f) * CYCLE / fs)
        if Fraction(q) - math.floor(q) == Fraction(1, 2):
            return f
        f = math.nextafter(f, math.inf)


def product_at_two_pow_64(fs):
    """(t, t_below): smallest t with binary64(t*fs) == 2^64, and the binary64 below it."""
    t = binary64(Fraction(CYCLE, fs))
    while binary64(Fraction(t) * fs) >= 2.0**64:
        t = math.nextafter(t, 0.0)
    below = t
    t = math.nextafter(t, math.inf)
    assert binary64(Fraction(t) * fs) == 2.0**64
    return t, below


def increment_rows():
    rows = []
    for fs in RATES:
        for label, f in INCREMENT_SIGNALS:
            inc, q = increment(f, fs)
            rows.append({"case": "signal", "label": label, "f_hz": dec(f), "f_hex": hexf(f),
                         "fs": fs, "q_hex": hexf(q), "inc": str(inc)})
    for fs in RATES:
        for k in (1, 3, 5):
            f = binary64(Fraction(k * fs, 2**65))
            inc, q = increment(f, fs)
            rows.append({"case": "tie", "label": f"q = {k}/2 exactly",
                         "f_hz": dec(f), "f_hex": hexf(f), "fs": fs,
                         "q_hex": hexf(q), "inc": str(inc)})
    for fs in RATES:
        for base in (1.5, 5.5):
            f = band_tie(base, fs)
            inc, q = increment(f, fs)
            rows.append({"case": "tie", "label": f"q exactly k + 1/2 near {base:g} Hz (theta rate band)",
                         "f_hz": dec(f), "f_hex": hexf(f), "fs": fs,
                         "q_hex": hexf(q), "inc": str(inc)})
    for fs in RATES:
        below = math.nextafter(fs / 2, 0.0)
        inc, q = increment(below, fs)
        rows.append({"case": "edge", "label": "largest binary64 below fs/2",
                     "f_hz": dec(below), "f_hex": hexf(below), "fs": fs,
                     "q_hex": hexf(q), "inc": str(inc)})
        for label, f in (("zero", 0.0), ("negative zero", -0.0), ("negative", -1.0),
                         ("exactly fs/2", fs / 2), ("above fs/2", float(fs)),
                         ("NaN", math.nan), ("infinity", math.inf),
                         ("negative infinity", -math.inf)):
            inc, q = increment(f, fs)
            rows.append({"case": "edge" if label in ("zero", "negative zero") else "out_of_range",
                         "label": label, "f_hz": dec(f), "f_hex": hexf(f), "fs": fs,
                         "q_hex": hexf(q) if q is not None else "none", "inc": str(inc)})
    return rows


def sample_rows():
    cases = (
        ("zero", 0.0, 48000),
        ("1 s", 1.0, 44100),
        ("1 s", 1.0, 48000),
        ("1.5 s", 1.5, 44100),
        ("1 ms (inexact in binary64)", 0.001, 44100),
        ("1 ms (inexact in binary64)", 0.001, 48000),
        ("10 ms (inexact in binary64)", 0.01, 44100),
        ("2 min", 120.0, 48000),
        ("8 h", 28800.0, 44100),
        ("8 h", 28800.0, 48000),
        ("tie 187.5, up to even", 2.0**-8, 48000),
        ("tie 562.5, down to even", 3 * 2.0**-8, 48000),
        ("tie 5512.5, down to even", 2.0**-3, 44100),
        ("tie 16537.5, up to even", 0.375, 44100),
        ("negative", -1.0, 48000),
        ("NaN", math.nan, 48000),
        ("infinity", math.inf, 48000),
        ("product exactly 2^64", product_at_two_pow_64(48000)[0], 48000),
        ("largest product below 2^64", product_at_two_pow_64(48000)[1], 48000),
    )
    rows = []
    for label, t, fs in cases:
        n, product = samples(t, fs)
        case = "tie" if label.startswith("tie") else (
            "out_of_range" if label in ("negative", "NaN", "infinity", "product exactly 2^64")
            else "time")
        rows.append({"case": case, "label": label, "t_s": dec(t), "t_hex": hexf(t), "fs": fs,
                     "product_hex": hexf(product) if product is not None else "none",
                     "n": str(n)})
    return rows


def phase_step_rows():
    inc450, _ = increment(450.0, 44100)
    cases = (
        ("wrap by one step", CYCLE - 1, 2, 1),
        ("wrap from the top of the cycle", CYCLE - inc450 + 5, inc450, 1),
        ("450 Hz at 44.1 kHz, 98 samples (one nominal cycle)", 0, inc450, 98),
        ("450 Hz at 44.1 kHz, 8 h", 0, inc450, 8 * 3600 * 44100),
    )
    rows = []
    for label, start, inc, steps in cases:
        rows.append({"label": label, "start": str(start), "inc": str(inc), "steps": steps,
                     "phase": str((start + steps * inc) % CYCLE)})
    return rows


CARRIER_SAMPLE_INDICES = (0, 1, 2, 10, 24, 49, 73, 97, 98, 1000, 44100, 8 * 3600 * 44100)


def carrier_rows():
    inc, _ = increment(450.0, 44100)
    rows = []
    for n in CARRIER_SAMPLE_INDICES:
        phase = (n * inc) % CYCLE
        rows.append({"n": n, "phase": str(phase), "sine": ideal_sine(phase)})
    return {"label": "450 Hz carrier, unmodulated, 44.1 kHz, phase 0 at n = 0",
            "f_hz": "450.0", "fs": 44100, "inc": str(inc), "samples": rows}


def engine_sine_rows():
    rows = [{"label": label, "phase": str(p)} for label, p in EXACT_PHASES]
    for label, edge in EXACT_PHASES[0:1] + EXACT_PHASES[2:]:
        rows.append({"label": f"{label} - 1", "phase": str((edge - 1) % CYCLE)})
        rows.append({"label": f"{label} + 1", "phase": str((edge + 1) % CYCLE)})
    inc, _ = increment(450.0, 44100)
    for n in CARRIER_SAMPLE_INDICES:
        rows.append({"label": f"450 Hz carrier at 44.1 kHz, n = {n}",
                     "phase": str((n * inc) % CYCLE)})
    for r in rows:
        r["bits"] = bits(engine_sine(int(r["phase"])))
    return rows


BLOCK_FRAMES = 64
BLOCK_FRAME_INDICES = (0, 37, 63, 64, 65, 127, 128, 1000, 44099, 47999)

# (fixture, theta or None, carrier_left_hz, beat_rate_hz, length_s): the 1 s
# binaural fixtures in recipes/fixtures/valid/. theta is (carrier_hz,
# rate_hz, am_depth_percent, shape), or None when the fixture has no
# theta_reference field. At depth 0 the theta envelope law gives a = 1.0
# exactly, so the theta tap is the unmodulated engine sine (Story 2.1 keeps
# these bytes). tests/python/test_signal_spec_core.py checks that each
# fixture holds these values.
STUB_CHAIN_FIXTURES = (
    ("stub-chain-1s-beat-0.json", None, 400.0, 0.0, 1.0),
    ("stub-chain-1s-beat-6.json", (300.0, 6.0, 0.0, "sine"), 400.0, 6.0, 1.0),
)
STUB_CHAIN_INDICES = (0, 1, 37, 63, 64, 65, 127, 128, 1000)


def block_rows():
    return [{"frame": k, "block": k // BLOCK_FRAMES, "offset": k % BLOCK_FRAMES}
            for k in BLOCK_FRAME_INDICES]


def stub_chain_sample(theta, phase, gain):
    """One channel of the stub chain, spec operation order: (theta, bus, join, master).

    theta is the theta tap value (Theta reference, Per sample), +0.0 without
    a theta_reference field."""
    gamma = 0.0
    bus = theta + gamma
    binaural = gain * engine_sine(phase)
    join = bus + binaural
    master = join * 1.0
    return theta, bus, join, master


def ideal_sum(*phases):
    """Exact sum of the ideal sines of phases, written once at DIGITS digits."""
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        total = sum((ideal_sine_decimal(p) for p in phases), Decimal(0))
    return format_ideal(total)


def stub_chain_rows():
    rows = []
    for fs in RATES:
        for fixture, theta_spec, left_hz, beat_hz, length_s in STUB_CHAIN_FIXTURES:
            right_hz = left_hz + beat_hz  # one binary64 addition
            theta_hz = None if theta_spec is None else theta_spec[0]
            if theta_spec is None:
                inc_t, layer = 0, None
            else:
                layer = ThetaLayer(*theta_spec, fs)
                inc_t = layer.inc_carrier
            inc_l, _ = increment(left_hz, fs)
            inc_r, _ = increment(right_hz, fs)
            frames, _ = samples(length_s, fs)
            for n in STUB_CHAIN_INDICES + (frames - 1, frames, frames + 63):
                past_end = n >= frames
                pt = (n * inc_t) % CYCLE
                pl = (n * inc_l) % CYCLE
                pr = (n * inc_r) % CYCLE
                if past_end:
                    theta = left = right = 0.0
                    ideal_t = ideal_l = ideal_r = "0"
                else:
                    theta_value = 0.0 if layer is None else layer.engine_sample(n)
                    if layer is not None:
                        # Depth 0: a = 1.0 exactly, so the tap is the
                        # unmodulated engine sine, as in Story 1.5.
                        assert bits(theta_value) == bits(1.0 * engine_sine(pt))
                    tl, bl, jl, left = stub_chain_sample(theta_value, pl, 1.0)
                    tr, br, jr, right = stub_chain_sample(theta_value, pr, 1.0)
                    # The theta reference is the same in both channels, the
                    # stereo bus equals it bit for bit, and join, master, and
                    # out agree bit for bit (signal spec, Stub chain).
                    assert bits(tl) == bits(tr) == bits(bl) == bits(br)
                    assert bits(jl) == bits(left) and bits(jr) == bits(right)
                    theta = tl
                    if theta_hz is None:
                        assert bits(theta) == bits(0.0)
                        ideal_t = "0"
                        ideal_l, ideal_r = ideal_sine(pl), ideal_sine(pr)
                    else:
                        ideal_t = ideal_sine(pt)
                        ideal_l, ideal_r = ideal_sum(pt, pl), ideal_sum(pt, pr)
                rows.append({
                    "case": "past_end" if past_end else "signal",
                    "fixture": fixture, "fs": fs,
                    "theta_carrier_hex": "none" if theta_hz is None else hexf(theta_hz),
                    "theta_rate_hex": "none" if theta_spec is None else hexf(theta_spec[1]),
                    "theta_depth_hex": "none" if theta_spec is None else hexf(theta_spec[2]),
                    "theta_shape": "none" if theta_spec is None else theta_spec[3],
                    "carrier_left_hex": hexf(left_hz), "beat_rate_hex": hexf(beat_hz),
                    "carrier_right_hex": hexf(right_hz),
                    "inc_theta": str(inc_t),
                    "inc_left": str(inc_l), "inc_right": str(inc_r),
                    "frames": str(frames), "n": str(n),
                    "phase_theta": str(pt),
                    "phase_left": str(pl), "phase_right": str(pr),
                    "theta_bits": bits(theta),
                    "left_bits": bits(left), "right_bits": bits(right),
                    "ideal_theta": ideal_t,
                    "ideal_left": ideal_l, "ideal_right": ideal_r,
                })
    return rows


# --------------------------------------------------------- theta reference
#
# Story 2.1 (signal spec, Theta reference). The fixed envelope constants are
# written here in their row units, the way the engine and the reference hold
# them; tests/python/test_signal_spec_core.py checks them against the range
# rows theta-on-share (percent) and theta-edge (ms). No study sets them:
# engineering defaults decided by Audio on 2026-11-06.

THETA_SHAPES = ("sine", "smoothed_on_off", "sawtooth", "reverse_saw")
THETA_ON_SHARE_PERCENT = 50.0  # row theta-on-share
THETA_EDGE_MS = 10.0           # row theta-edge
QUARTER = 2**62                # a quarter cycle: sine(p + 2^62) is the cosine of p
HALF = 2**63


def theta_on_share():
    """D, the on share as a fraction of a cycle: one binary64 division."""
    return THETA_ON_SHARE_PERCENT / 100.0


def theta_edge_s():
    """E, the edge length in seconds: one binary64 division."""
    return THETA_EDGE_MS / 1000.0


def nearest_u64(x):
    """Nearest integer to the binary64 x >= 0, ties to even (exact)."""
    return round_half_even(Fraction(x))


def half_on_units():
    """H = D * 2^63 (exact power-of-two scale), nearest integer, ties to even."""
    return nearest_u64(theta_on_share() * 2.0**63)


def edge_units(rate_hz):
    """W: w = E * rate (one rounding), then w * 2^64 (exact), nearest integer."""
    w = theta_edge_s() * rate_hz
    return nearest_u64(w * 2.0**64), w


def ratio_to_phase(r):
    """Spec ratio-to-phase rule: P = r * 2^63 rounded, clamped to [0, 2^63]."""
    if not (r > 0.0):  # NaN, both zeros, negatives
        return 0, None
    if r >= 1.0:
        return HALF, None
    x = r * 2.0**63  # exact: a power-of-two scale
    return nearest_u64(x), x


def engine_raised_cosine(u, w_units):
    """Engine half raised cosine (1 + cos(pi * u / W)) / 2 for 0 <= u <= W."""
    r = float(u) / float(w_units)  # two conversions, one division
    p, _ = ratio_to_phase(r)
    c = engine_sine((p + QUARTER) % CYCLE)
    return (1.0 + c) * 0.5


def engine_saw(p, w_units):
    if p < w_units:
        return engine_raised_cosine(p, w_units)
    return float(p - w_units) / float(CYCLE - w_units)


def theta_region(shape, p, w_units, h_units):
    """Name of the envelope segment phase p lies in (exact integer tests)."""
    if shape == "sine":
        return "zero degree" if p == 0 else "cosine"
    if shape == "smoothed_on_off":
        m = p if p < HALF else CYCLE - p
        if m <= h_units - w_units:
            return "zero degree" if p == 0 else "plateau"
        if m >= h_units:
            return "off"
        return "falling edge" if p < HALF else "rising edge"
    if shape == "sawtooth":
        if p < w_units:
            return "zero degree" if p == 0 else "drop edge"
        return "linear rise"
    if shape == "reverse_saw":
        q = (CYCLE - p) % CYCLE
        if q < w_units:
            return "zero degree" if p == 0 else "rise edge"
        return "linear fall"
    raise ValueError(f"shape not modeled in the signal spec: {shape}")


def engine_envelope(shape, p, w_units, h_units):
    """Spec engine envelope e(phase) in binary64, exact operation order."""
    if shape == "sine":
        c = engine_sine((p + QUARTER) % CYCLE)
        return (1.0 + c) * 0.5
    if shape == "smoothed_on_off":
        m = p if p < HALF else CYCLE - p  # |s|, exact; 2^63 at s = -2^63
        if m <= h_units - w_units:
            return 1.0
        if m >= h_units:
            return 0.0
        return engine_raised_cosine(m - (h_units - w_units), w_units)
    if shape == "sawtooth":
        return engine_saw(p, w_units)
    if shape == "reverse_saw":
        return engine_saw((CYCLE - p) % CYCLE, w_units)
    raise ValueError(f"shape not modeled in the signal spec: {shape}")


def decimal_cos_pi(num, den):
    """cos(pi * num / den) as a Decimal at about PREC digits, 0 <= num <= den."""
    t = Fraction(num, den)
    sign = 1
    if t > Fraction(1, 2):
        t, sign = 1 - t, -1
    if t == Fraction(1, 2):
        return Decimal(0)
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        x = decimal_pi() * Decimal(t.numerator) / Decimal(t.denominator)
        total = Decimal(0)
        term = Decimal(1)
        k = 0
        while abs(term) > Decimal(10) ** -(PREC + 5):
            total += term
            term = -term * x * x / ((k + 1) * (k + 2))
            k += 2
        total += term
        return sign * total


def ideal_envelope_decimal(shape, p, w_units, h_units):
    """Ideal e(phase): the same segments, ideal cosines and exact ratios."""
    half = Decimal(1) / Decimal(2)
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        if shape == "sine":
            return (1 + ideal_sine_decimal((p + QUARTER) % CYCLE)) * half
        if shape == "smoothed_on_off":
            m = p if p < HALF else CYCLE - p
            if m <= h_units - w_units:
                return Decimal(1)
            if m >= h_units:
                return Decimal(0)
            return (1 + decimal_cos_pi(m - (h_units - w_units), w_units)) * half
        if shape in ("sawtooth", "reverse_saw"):
            q = p if shape == "sawtooth" else (CYCLE - p) % CYCLE
            if q < w_units:
                return (1 + decimal_cos_pi(q, w_units)) * half
            return Decimal(q - w_units) / Decimal(CYCLE - w_units)
    raise ValueError(f"shape not modeled in the signal spec: {shape}")


class ThetaLayer:
    """One theta reference layer at one sample rate (signal spec, Theta reference)."""

    def __init__(self, carrier_hz, rate_hz, depth_percent, shape, fs):
        self.carrier_hz, self.rate_hz = carrier_hz, rate_hz
        self.depth_percent, self.shape, self.fs = depth_percent, shape, fs
        self.inc_carrier, _ = increment(carrier_hz, fs)
        self.inc_rate, _ = increment(rate_hz, fs)
        self.w_units, _ = edge_units(rate_hz)
        self.h_units = half_on_units()
        self.depth = depth_percent / 100.0  # d: one binary64 division

    def phases(self, n):
        return (n * self.inc_carrier) % CYCLE, (n * self.inc_rate) % CYCLE

    def engine_parts(self, n):
        """(e, a, theta) in binary64, the spec's per-sample operation order."""
        pc, pe = self.phases(n)
        e = engine_envelope(self.shape, pe, self.w_units, self.h_units)
        a = 1.0 - self.depth * (1.0 - e)
        return e, a, a * engine_sine(pc)

    def engine_sample(self, n):
        return self.engine_parts(n)[2]

    def ideal_parts(self, n):
        """(e, theta) ideal: exact depth law on the binary64 d, ideal sines."""
        pc, pe = self.phases(n)
        with localcontext() as ctx:
            ctx.prec = PREC + 10
            e = ideal_envelope_decimal(self.shape, pe, self.w_units, self.h_units)
            d = Decimal(Fraction(self.depth).numerator) / Decimal(Fraction(self.depth).denominator)
            a = 1 - d * (1 - e)
            return e, a * ideal_sine_decimal(pc)


THETA_RATES_HZ = (1.0, 6.0)
THETA_EDGE_RATES_HZ = (1.0, 2.0, 5.5, 6.0)


def kebab(shape):
    return shape.replace("_", "-")


# (fixture, carrier_hz, rate_hz, am_depth_percent, shape, length_s): the
# Story 2.1 theta fixtures in recipes/fixtures/valid/, each a theta
# reference only (no binaural field), 10 s. In this order they are the hash
# probe's theta-envelopes-<fs> components.
THETA_FIXTURES = tuple(
    (f"theta-{kebab(shape)}-{int(rate)}hz.json", 450.0, rate, 75.0, shape, 10.0)
    for shape in THETA_SHAPES for rate in THETA_RATES_HZ)


def theta_envelope_phases(shape, w, h):
    """Phases of the envelope vector table for one shape (exact integers)."""
    top = CYCLE - 1
    if shape == "sine":
        cases = (0, 1, 2**61, QUARTER, HALF, 3 * QUARTER, top)
    elif shape == "smoothed_on_off":
        cases = (0, h - w - 1, h - w, h - w + 1, h - w + w // 2, h - 1, h, h + 1, HALF,
                 CYCLE - h, CYCLE - h + 1, CYCLE - h + w // 2, CYCLE - (h - w),
                 CYCLE - (h - w) + 1, top)
    elif shape == "sawtooth":
        cases = (0, 1, w // 2, w - 1, w, w + 1, HALF, top)
    else:
        cases = (0, 1, HALF, CYCLE - w - 1, CYCLE - w, CYCLE - w + 1, CYCLE - w // 2, top)
    return cases


def theta_envelope_rows():
    rows = []
    h = half_on_units()
    for shape in THETA_SHAPES:
        for rate in THETA_RATES_HZ:
            w, _ = edge_units(rate)
            for p in theta_envelope_phases(shape, w, h):
                e = engine_envelope(shape, p, w, h)
                assert 0.0 <= e <= 1.0, (shape, rate, p, e)
                rows.append({
                    "shape": shape, "rate_hex": hexf(rate), "w_units": str(w),
                    "h_units": str(h), "phase": str(p),
                    "region": theta_region(shape, p, w, h),
                    "e_bits": bits(e),
                    "ideal_e": format_ideal(ideal_envelope_decimal(shape, p, w, h)),
                })
    return rows


def theta_edge_rows():
    rows = []
    for rate in THETA_EDGE_RATES_HZ:
        w_units, w = edge_units(rate)
        rows.append({"rate_hex": hexf(rate), "edge_s_hex": hexf(theta_edge_s()),
                     "w_hex": hexf(w), "w_units": str(w_units)})
    return rows


RATIO_CASES = (
    ("zero", 0.0),
    ("negative zero", -0.0),
    ("NaN", math.nan),
    ("negative", -0.5),
    ("tie x = 1/2, down to even", 2.0**-64),
    ("tie x = 3/2, up to even", 3 * 2.0**-64),
    ("tie x = 5/2, down to even", 5 * 2.0**-64),
    ("quarter", 0.25),
    ("half", 0.5),
    ("one third (inexact in binary64)", 1.0 / 3.0),
    ("largest binary64 below 1", math.nextafter(1.0, 0.0)),
    ("one", 1.0),
    ("above one", 1.5),
    ("infinity", math.inf),
)


def ratio_rows():
    rows = []
    for label, r in RATIO_CASES:
        p, x = ratio_to_phase(r)
        rows.append({"label": label, "r_hex": hexf(r),
                     "x_hex": "none" if x is None else hexf(x), "phase": str(p)})
    return rows


def first_at_or_above(boundary, inc):
    """Smallest n >= 0 with n * inc >= boundary (no wrap within one cycle)."""
    return -(-boundary // inc)


def theta_sample_indices(layer, frames):
    """Start, block boundaries, segment boundaries of the first cycle, end."""
    w, h, inc = layer.w_units, layer.h_units, layer.inc_rate
    bounds = {
        "sine": (QUARTER, HALF),
        "smoothed_on_off": (h - w, h, CYCLE - h, CYCLE - (h - w)),
        "sawtooth": (w, HALF),
        "reverse_saw": (HALF, CYCLE - w),
    }[layer.shape]
    indices = {0, 1, 63, 64, 65, 1000, frames - 1, frames, frames + 63}
    for b in bounds:
        n = first_at_or_above(b, inc)
        indices.update((n - 1, n))
    return sorted(indices)


def theta_sample_rows():
    rows = []
    for fs in RATES:
        for fixture, carrier, rate, depth, shape, length_s in THETA_FIXTURES:
            layer = ThetaLayer(carrier, rate, depth, shape, fs)
            frames, _ = samples(length_s, fs)
            for n in theta_sample_indices(layer, frames):
                pc, pe = layer.phases(n)
                past_end = n >= frames
                if past_end:
                    e_bits = a_bits = theta_bits = bits(0.0)
                    ideal_e = ideal_theta = "0"
                else:
                    e, a, theta = layer.engine_parts(n)
                    e_bits, a_bits, theta_bits = bits(e), bits(a), bits(theta)
                    ie, it = layer.ideal_parts(n)
                    ideal_e, ideal_theta = format_ideal(ie), format_ideal(it)
                rows.append({
                    "case": "past_end" if past_end else "signal",
                    "fixture": fixture, "fs": fs, "shape": shape,
                    "carrier_hex": hexf(carrier), "rate_hex": hexf(rate),
                    "depth_hex": hexf(depth), "length_hex": hexf(length_s),
                    "inc_carrier": str(layer.inc_carrier), "inc_rate": str(layer.inc_rate),
                    "w_units": str(layer.w_units), "h_units": str(layer.h_units),
                    "frames": str(frames), "n": str(n),
                    "phase_carrier": str(pc), "phase_rate": str(pe),
                    "region": "past end" if past_end else theta_region(
                        shape, pe, layer.w_units, layer.h_units),
                    "e_bits": e_bits, "a_bits": a_bits, "theta_bits": theta_bits,
                    "ideal_e": ideal_e, "ideal_theta": ideal_theta,
                })
    return rows


# ------------------------------------------------------- gamma PAC layer
#
# Story 2.2 (signal spec, Gamma PAC layer): uncoupled only. The AM law is the
# theta sine shape at the gamma rate; the depth is constant for the render.

GAMMA_CARRIER_WAVES = ("sine", "triangle", "softened_square")
GAMMA_MODELED_WAVES = ("sine",)
GAMMA_COUPLINGS = ("uncoupled",)
GAMMA_ENVELOPE_DEPTHS = (0.0, 25.0, 100.0)


def gamma_envelope(p):
    """Engine gamma envelope e = (1 + cos(2 pi p / 2^64)) / 2, spec operation order."""
    c = engine_sine((p + QUARTER) % CYCLE)
    return (1.0 + c) * 0.5


def gamma_envelope_ideal(p):
    """Ideal gamma envelope as a Decimal at about PREC digits."""
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        return (1 + ideal_sine_decimal((p + QUARTER) % CYCLE)) * (Decimal(1) / Decimal(2))


def exact_decimal(x):
    """The exact value of the binary64 x as a Decimal."""
    f = Fraction(x)
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        return Decimal(f.numerator) / Decimal(f.denominator)


class GammaLayer:
    """One uncoupled gamma PAC layer at one sample rate (signal spec, Gamma PAC layer)."""

    def __init__(self, carrier_hz, rate_hz, depth_percent, fs):
        self.carrier_hz, self.rate_hz = carrier_hz, rate_hz
        self.depth_percent, self.fs = depth_percent, fs
        self.inc_carrier, _ = increment(carrier_hz, fs)
        self.inc_rate, _ = increment(rate_hz, fs)
        self.depth = depth_percent / 100.0  # d: one binary64 division

    def phases(self, n):
        return (n * self.inc_carrier) % CYCLE, (n * self.inc_rate) % CYCLE

    def engine_parts(self, n):
        """(e, a, gamma) in binary64, the spec's per-sample operation order."""
        pc, pe = self.phases(n)
        e = gamma_envelope(pe)
        a = 1.0 - self.depth * (1.0 - e)
        return e, a, a * engine_sine(pc)

    def ideal_parts(self, n):
        """(e, gamma) ideal: exact depth law on the binary64 d, ideal sines."""
        pc, pe = self.phases(n)
        with localcontext() as ctx:
            ctx.prec = PREC + 10
            e = gamma_envelope_ideal(pe)
            a = 1 - exact_decimal(self.depth) * (1 - e)
            return e, a * ideal_sine_decimal(pc)


GAMMA_FIXTURE_CARRIER_HZ = 250.0
GAMMA_FIXTURE_LENGTH_S = 10.0

# (fixture, (carrier_hz, rate_hz, am_depth_percent), theta or None,
# length_s): the Story 2.2 fixtures in recipes/fixtures/valid/. theta is
# (carrier_hz, rate_hz, am_depth_percent, shape). Every gamma layer has a
# sine carrier and coupling uncoupled. In this order they are the hash
# probe's gamma-uncoupled-<fs> components.
GAMMA_FIXTURES = tuple(
    (f"gamma-uncoupled-{int(rate)}hz-{int(depth)}pct.json",
     (GAMMA_FIXTURE_CARRIER_HZ, rate, depth), None, GAMMA_FIXTURE_LENGTH_S)
    for rate in (40.0, 60.0) for depth in (25.0, 100.0)) + (
    ("theta-gamma-uncoupled.json", (GAMMA_FIXTURE_CARRIER_HZ, 40.0, 100.0),
     (450.0, 6.0, 75.0, "sine"), GAMMA_FIXTURE_LENGTH_S),
)


def format_trimmed(total):
    """format_ideal, with trailing fractional zeros removed (the same value)."""
    text = format_ideal(total)
    if "." in text and "e" not in text:
        text = text.rstrip("0").rstrip(".")
    return text


def gamma_envelope_phases():
    return (0, 1, 2**61, QUARTER, HALF, 3 * QUARTER, CYCLE - 1)


def gamma_envelope_rows():
    rows = []
    for depth_percent in GAMMA_ENVELOPE_DEPTHS:
        d = depth_percent / 100.0
        for p in gamma_envelope_phases():
            e = gamma_envelope(p)
            a = 1.0 - d * (1.0 - e)
            assert 0.0 < e < 1.0 and 0.0 < a <= 1.0, (depth_percent, p, e, a)
            with localcontext() as ctx:
                ctx.prec = PREC + 10
                ie = gamma_envelope_ideal(p)
                ia = 1 - exact_decimal(d) * (1 - ie)
            rows.append({
                "depth_hex": hexf(depth_percent), "phase": str(p),
                "e_bits": bits(e), "a_bits": bits(a),
                "ideal_e": format_trimmed(ie), "ideal_a": format_trimmed(ia),
            })
    return rows


def gamma_sample_indices(layer, frames):
    """Start, block boundaries, quarter-cycle crossings of the first gamma cycle, end."""
    indices = {0, 1, 63, 64, 65, 127, 128, 1000, frames - 1, frames, frames + 63}
    for b in (QUARTER, HALF, 3 * QUARTER):
        n = first_at_or_above(b, layer.inc_rate)
        indices.update((n - 1, n))
    return sorted(indices)


def _theta_columns(theta_spec):
    if theta_spec is None:
        return {"theta_carrier_hex": "none", "theta_rate_hex": "none",
                "theta_depth_hex": "none", "theta_shape": "none"}
    carrier, rate, depth, shape = theta_spec
    return {"theta_carrier_hex": hexf(carrier), "theta_rate_hex": hexf(rate),
            "theta_depth_hex": hexf(depth), "theta_shape": shape}


def gamma_sample_rows():
    rows = []
    for fs in RATES:
        for fixture, (carrier, rate, depth), theta_spec, length_s in GAMMA_FIXTURES:
            layer = GammaLayer(carrier, rate, depth, fs)
            frames, _ = samples(length_s, fs)
            for n in gamma_sample_indices(layer, frames):
                pc, pe = layer.phases(n)
                past_end = n >= frames
                if past_end:
                    e_bits = a_bits = gamma_bits = bits(0.0)
                    ideal_e = ideal_gamma = "0"
                else:
                    e, a, g = layer.engine_parts(n)
                    # The engine envelope never reaches 0 (the engine sine
                    # stays inside (-1, 1)), so a > 0 and the tap is never -0.0.
                    assert e > 0.0 and a > 0.0 and bits(g) != bits(-0.0), (fixture, fs, n)
                    e_bits, a_bits, gamma_bits = bits(e), bits(a), bits(g)
                    ie, ig = layer.ideal_parts(n)
                    ideal_e, ideal_gamma = format_ideal(ie), format_ideal(ig)
                row = {
                    "case": "past_end" if past_end else "signal",
                    "fixture": fixture, "fs": fs,
                    "carrier_hex": hexf(carrier), "rate_hex": hexf(rate),
                    "depth_hex": hexf(depth), "length_hex": hexf(length_s),
                    "carrier_wave": "sine", "coupling": "uncoupled",
                }
                row.update(_theta_columns(theta_spec))
                row.update({
                    "inc_carrier": str(layer.inc_carrier), "inc_rate": str(layer.inc_rate),
                    "frames": str(frames), "n": str(n),
                    "phase_carrier": str(pc), "phase_rate": str(pe),
                    "e_bits": e_bits, "a_bits": a_bits, "gamma_bits": gamma_bits,
                    "ideal_e": ideal_e, "ideal_gamma": ideal_gamma,
                })
                rows.append(row)
    return rows


def gamma_bus_rows():
    """The theta and gamma fixture: theta tap, gamma tap, and their bus sum."""
    rows = []
    for fs in RATES:
        for fixture, (carrier, rate, depth), theta_spec, length_s in GAMMA_FIXTURES:
            if theta_spec is None:
                continue
            gamma = GammaLayer(carrier, rate, depth, fs)
            theta = ThetaLayer(*theta_spec, fs)
            frames, _ = samples(length_s, fs)
            indices = sorted(set(gamma_sample_indices(gamma, frames))
                             | set(theta_sample_indices(theta, frames)))
            for n in indices:
                past_end = n >= frames
                if past_end:
                    t = g = bus = 0.0
                    ideal_t = ideal_g = ideal_bus = "0"
                else:
                    t = theta.engine_sample(n)
                    g = gamma.engine_parts(n)[2]
                    bus = t + g  # stereo bus: one binary64 addition
                    with localcontext() as ctx:
                        ctx.prec = PREC + 10
                        it = theta.ideal_parts(n)[1]
                        ig = gamma.ideal_parts(n)[1]
                        ideal_t, ideal_g = format_ideal(it), format_ideal(ig)
                        ideal_bus = format_ideal(it + ig)
                rows.append({
                    "case": "past_end" if past_end else "signal",
                    "fixture": fixture, "fs": fs, "n": str(n),
                    "phase_theta": str(theta.phases(n)[0]),
                    "phase_theta_envelope": str(theta.phases(n)[1]),
                    "phase_gamma": str(gamma.phases(n)[0]),
                    "phase_gamma_envelope": str(gamma.phases(n)[1]),
                    "theta_bits": bits(t), "gamma_bits": bits(g), "bus_bits": bits(bus),
                    "ideal_theta": ideal_t, "ideal_gamma": ideal_g, "ideal_bus": ideal_bus,
                })
    return rows


# ------------------------------------------------------------- coupling
#
# Story 2.3 (signal spec, Coupling): the smooth swell. One raised cosine per
# theta cycle, read from the theta envelope phase alone and centered on the
# coupling phase C; it scales the gamma AM depth.

GAMMA_COUPLINGS_2_3 = ("uncoupled", "smooth_swell")
COUPLED = ("smooth_swell",)
# 45 * 2^-62 and 135 * 2^-62 degrees give x * 2^64 exactly 1/2 and 3/2: the
# ties, to even (0 and 2).
COUPLING_PHASE_DEGREES = (0.0, 45.0 * 2.0**-62, 135.0 * 2.0**-62, 0.01, 45.0, 90.0, 180.0,
                          270.0, 359.99, 360.0)
SWELL_TEST_DEGREES = (0.0, 90.0, 180.0, 270.0)
SWELL_OFFSETS = (0, QUARTER, HALF)          # theta envelope phase minus C
SWELL_GAMMA_PHASES = (0, HALF)              # gamma envelope peak and trough


def coupling_phase_units(deg):
    """C: x = deg / 360.0 (one rounding), x * 2^64 (exact), nearest, ties to even, mod 2^64."""
    x = deg / 360.0
    return round_half_even(Fraction(x) * CYCLE) % CYCLE, x


def swell(p_e, c_units):
    """Engine swell s = sine_envelope(p_E - C mod 2^64), spec operation order."""
    return gamma_envelope((p_e - c_units) % CYCLE)


def swell_ideal(p_e, c_units):
    return gamma_envelope_ideal((p_e - c_units) % CYCLE)


def coupled_amplitude(d, s, e):
    """a = 1.0 - (d * s) * (1.0 - e): four binary64 operations, in this order."""
    return 1.0 - (d * s) * (1.0 - e)


class SwellLayer(GammaLayer):
    """One smooth-swell gamma PAC layer at one sample rate (signal spec, Coupling).

    theta_rate is the theta reference rate, or None without a theta reference
    (the theta envelope phase is then 0 for every sample).
    """

    def __init__(self, carrier_hz, rate_hz, depth_percent, phase_deg, theta_rate, fs):
        super().__init__(carrier_hz, rate_hz, depth_percent, fs)
        self.phase_deg = phase_deg
        self.c_units, self.c_ratio = coupling_phase_units(phase_deg)
        self.inc_theta_envelope = increment(theta_rate, fs)[0] if theta_rate is not None else 0

    def theta_envelope_phase(self, n):
        return (n * self.inc_theta_envelope) % CYCLE

    def engine_parts(self, n):
        """(s, e, a, gamma) in binary64, the spec's per-sample operation order."""
        pc, pm = self.phases(n)
        s = swell(self.theta_envelope_phase(n), self.c_units)
        e = gamma_envelope(pm)
        a = coupled_amplitude(self.depth, s, e)
        return s, e, a, a * engine_sine(pc)

    def ideal_parts(self, n):
        """(s, gamma) ideal: exact law on the binary64 d, ideal cosines and sine."""
        pc, pm = self.phases(n)
        with localcontext() as ctx:
            ctx.prec = PREC + 10
            s = swell_ideal(self.theta_envelope_phase(n), self.c_units)
            e = gamma_envelope_ideal(pm)
            a = 1 - exact_decimal(self.depth) * s * (1 - e)
            return s, a * ideal_sine_decimal(pc)


SWELL_LENGTH_S = 5.0
SWELL_THETA = (450.0, 6.0, 75.0)   # theta carrier, rate, depth
SWELL_GAMMA = (250.0, 40.0)        # gamma carrier, rate

# (fixture, theta shape or None, coupling phase in degrees, gamma depth in
# percent): the Story 2.3 smooth-swell fixtures in recipes/fixtures/valid/.
# The first four, in this order, are the hash probe's gamma-swell-<fs>
# components; the last has no theta reference and gamma depth 0.
SWELL_FIXTURES = (
    ("swell-sine-0deg-100pct.json", "sine", 0.0, 100.0),
    ("swell-sawtooth-90deg-25pct.json", "sawtooth", 90.0, 25.0),
    ("swell-smoothed-on-off-180deg-100pct.json", "smoothed_on_off", 180.0, 100.0),
    ("swell-reverse-saw-270deg-25pct.json", "reverse_saw", 270.0, 25.0),
    ("swell-gamma-depth-0-no-theta.json", None, 90.0, 0.0),
)


def coupling_phase_rows():
    rows = []
    for deg in COUPLING_PHASE_DEGREES:
        c, x = coupling_phase_units(deg)
        rows.append({"deg_hex": hexf(deg), "x_hex": hexf(x),
                     "x_times_2_64_hex": hexf(x * 2.0**64), "c_units": str(c)})
    return rows


def swell_rows():
    rows = []
    for depth_percent in GAMMA_ENVELOPE_DEPTHS:
        d = depth_percent / 100.0
        for deg in SWELL_TEST_DEGREES:
            c, _ = coupling_phase_units(deg)
            for offset in SWELL_OFFSETS:
                p_e = (c + offset) % CYCLE
                for p_m in SWELL_GAMMA_PHASES:
                    s = swell(p_e, c)
                    e = gamma_envelope(p_m)
                    a = coupled_amplitude(d, s, e)
                    assert 0.0 < s < 1.0 and 0.0 < a <= 1.0, (depth_percent, deg, offset, p_m)
                    with localcontext() as ctx:
                        ctx.prec = PREC + 10
                        i_s = swell_ideal(p_e, c)
                        i_a = 1 - exact_decimal(d) * i_s * (1 - gamma_envelope_ideal(p_m))
                    rows.append({
                        "depth_hex": hexf(depth_percent), "deg_hex": hexf(deg),
                        "c_units": str(c), "phase_theta_envelope": str(p_e),
                        "phase_gamma_envelope": str(p_m),
                        "s_bits": bits(s), "e_bits": bits(e), "a_bits": bits(a),
                        "ideal_s": format_trimmed(i_s), "ideal_a": format_trimmed(i_a),
                    })
    return rows


def swell_layers(fs):
    carrier, rate = SWELL_GAMMA
    for fixture, shape, deg, depth in SWELL_FIXTURES:
        theta = None if shape is None else ThetaLayer(*SWELL_THETA, shape, fs)
        gamma = SwellLayer(carrier, rate, depth, deg, None if shape is None else SWELL_THETA[1], fs)
        yield fixture, shape, deg, depth, theta, gamma


def swell_sample_indices(gamma, frames):
    """Start, block boundaries, both sides of the first swell peak and swell
    trough, of the first gamma envelope trough, the last sample, past the end."""
    indices = {0, 1, 63, 64, 65, 127, 128, 1000, frames - 1, frames, frames + 63}
    inc = gamma.inc_theta_envelope
    if inc:
        for b in (gamma.c_units, (gamma.c_units + HALF) % CYCLE):
            n = first_at_or_above(b if b else CYCLE, inc)
            indices.update((n - 1, n))
    n = first_at_or_above(HALF, gamma.inc_rate)
    indices.update((n - 1, n))
    return sorted(i for i in indices if i >= 0)


def swell_sample_rows():
    rows = []
    for fs in RATES:
        for fixture, shape, deg, depth, theta, gamma in swell_layers(fs):
            frames, _ = samples(SWELL_LENGTH_S, fs)
            for n in swell_sample_indices(gamma, frames):
                pc, pm = gamma.phases(n)
                pe = gamma.theta_envelope_phase(n)
                past_end = n >= frames
                if past_end:
                    s_bits = e_bits = a_bits = gamma_bits = theta_bits = bus_bits = bits(0.0)
                    ideal_s = ideal_gamma = ideal_bus = "0"
                else:
                    s, e, a, g = gamma.engine_parts(n)
                    # a > 0 (s < 1 and e > 0), so the engine tap is never -0.0.
                    assert a > 0.0 and bits(g) != bits(-0.0), (fixture, fs, n)
                    if depth == 0.0:
                        assert a == 1.0, (fixture, fs, n)
                    t = theta.engine_sample(n) if theta is not None else 0.0
                    bus = t + g  # stereo bus: one binary64 addition
                    s_bits, e_bits, a_bits = bits(s), bits(e), bits(a)
                    gamma_bits, theta_bits, bus_bits = bits(g), bits(t), bits(bus)
                    with localcontext() as ctx:
                        ctx.prec = PREC + 10
                        i_s, i_g = gamma.ideal_parts(n)
                        i_t = theta.ideal_parts(n)[1] if theta is not None else Decimal(0)
                        ideal_s, ideal_gamma = format_ideal(i_s), format_ideal(i_g)
                        ideal_bus = format_ideal(i_t + i_g)
                row = {
                    "case": "past_end" if past_end else "signal",
                    "fixture": fixture, "fs": fs,
                    "carrier_hex": hexf(SWELL_GAMMA[0]), "rate_hex": hexf(SWELL_GAMMA[1]),
                    "depth_hex": hexf(depth), "length_hex": hexf(SWELL_LENGTH_S),
                    "carrier_wave": "sine", "coupling": "smooth_swell", "deg_hex": hexf(deg),
                    "c_units": str(gamma.c_units),
                }
                row.update(_theta_columns(None if shape is None else (*SWELL_THETA, shape)))
                row.update({
                    "inc_carrier": str(gamma.inc_carrier), "inc_rate": str(gamma.inc_rate),
                    "inc_theta_envelope": str(gamma.inc_theta_envelope),
                    "frames": str(frames), "n": str(n),
                    "phase_carrier": str(pc), "phase_rate": str(pm),
                    "phase_theta_envelope": str(pe),
                    "s_bits": s_bits, "e_bits": e_bits, "a_bits": a_bits,
                    "gamma_bits": gamma_bits, "theta_bits": theta_bits, "bus_bits": bus_bits,
                    "ideal_s": ideal_s, "ideal_gamma": ideal_gamma, "ideal_bus": ideal_bus,
                })
                rows.append(row)
    return rows


# ------------------------------------------------- binaural layer and rate curve
#
# Story 2.5 (signal spec, Binaural layer and Rate curve). The right ear plays
# the left carrier plus the beat rate; with a beat rate cycle the beat rate is
# r + s * sin(2 pi t / P + phi0), and the right ear phase is the closed-form
# integral phase_C[n] + U[n] mod 2^64.

BINAURAL_WAVEFORMS = ("sine", "triangle")
BINAURAL_MODELED_WAVEFORMS = ("sine",)
# The binary64 nearest to 1 / (2 pi), as a hex float; checked against
# decimal pi below, so the generator never takes it on trust.
INV_TWO_PI_HEX = "0x1.45f306dc9c883p-3"
TWO_POW_52 = 2.0**52


def inv_two_pi():
    k = float.fromhex(INV_TWO_PI_HEX)
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        exact = 1 / (2 * decimal_pi())
        f = Fraction(exact)
    assert binary64(f) == k, (binary64(f).hex(), INV_TWO_PI_HEX)
    return k


def cycles_to_units(v):
    """Spec cycles-to-units rule: (v mod 1) * 2^64, nearest, ties to even, mod 2^64.

    Returns (units, f) with f = v - trunc(v), the exact fractional part, or
    None where the domain check returns before the reduction."""
    if not (abs(v) < TWO_POW_52):
        return 0, None  # NaN, infinities, and |v| >= 2^52 (an integer, so 0 mod 1)
    w = math.trunc(v)
    f = v - float(w)  # binary64; exact (the fraction bits of v)
    assert Fraction(f) == Fraction(v) - w, v
    return round_half_even(Fraction(f) * CYCLE) % CYCLE, f


def decimal_sin_cycles(x):
    """sin(2 pi x) for a Fraction x of cycles, as a Decimal at about PREC digits."""
    y = Fraction(x) - (Fraction(x).numerator // Fraction(x).denominator)  # [0, 1), exact
    if y >= Fraction(1, 2):
        y -= 1  # [-1/2, 1/2)
    if y > Fraction(1, 4):
        y = Fraction(1, 2) - y
    elif y < -Fraction(1, 4):
        y = -Fraction(1, 2) - y
    if y == 0:
        return Decimal(0)
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        arg = 2 * decimal_pi() * Decimal(y.numerator) / Decimal(y.denominator)
        total = Decimal(0)
        term = arg
        k = 1
        while abs(term) > Decimal(10) ** -(PREC + 5):
            total += term
            term = -term * arg * arg / ((k + 1) * (k + 2))
            k += 2
        total += term
    return total


def decimal_sin_decimal_cycles(x):
    """sin(2 pi x) for a Decimal x of cycles (reduced in decimal arithmetic)."""
    with localcontext() as ctx:
        ctx.prec = PREC + 20
        return decimal_sin_cycles(Fraction(x))


class BinauralLayer:
    """One binaural layer at one sample rate (signal spec, Binaural layer and Rate curve).

    cycle is None (a fixed beat rate) or (swing_hz, period_s, start_phase_deg)."""

    def __init__(self, left_hz, beat_hz, cycle, fs):
        self.left_hz, self.beat_hz, self.cycle, self.fs = left_hz, beat_hz, cycle, fs
        self.center_hz = left_hz + beat_hz  # f_C: one binary64 addition
        self.inc_left, _ = increment(left_hz, fs)
        self.inc_center, _ = increment(self.center_hz, fs)
        if cycle is not None:
            swing, period, start = cycle
            self.p0, self.start_ratio = coupling_phase_units(start)
            self.inv_period = 1.0 / period  # one binary64 division
            self.inc_cycle, self.q_cycle = increment(self.inv_period, fs)
            self.swing_period = swing * period  # one rounding
            self.k = self.swing_period * inv_two_pi()  # one rounding
            self.c0 = engine_sine((self.p0 + QUARTER) % CYCLE)
        else:
            self.p0 = self.inc_cycle = 0
            self.k = 0.0

    def phases(self, n):
        """(phase_L, phase_C, cycle phase or None) at sample n."""
        cycle = None if self.cycle is None else (self.p0 + n * self.inc_cycle) % CYCLE
        return (n * self.inc_left) % CYCLE, (n * self.inc_center) % CYCLE, cycle

    def engine_parts(self, n):
        """(c, v, U, phase_R, left, right) in binary64, the spec's per-sample order."""
        pl, pc, pp = self.phases(n)
        if pp is None:
            c = v = None
            u = 0
        else:
            c = engine_sine((pp + QUARTER) % CYCLE)
            v = self.k * (self.c0 - c)  # c0 - c, then K times it
            u, _ = cycles_to_units(v)
        pr = (pc + u) % CYCLE
        return c, v, u, pr, engine_sine(pl), engine_sine(pr)

    def ideal_beat_cycles(self, n):
        """Ideal U[n] in cycles: K (cos(2 pi P0 / 2^64) - cos(2 pi p_P[n] / 2^64)), K = s P / (2 pi)."""
        if self.cycle is None:
            return Decimal(0)
        swing, period, _ = self.cycle
        _, _, pp = self.phases(n)
        with localcontext() as ctx:
            ctx.prec = PREC + 10
            k = exact_decimal(swing) * exact_decimal(period) / (2 * decimal_pi())
            c0 = ideal_sine_decimal((self.p0 + QUARTER) % CYCLE)
            c = ideal_sine_decimal((pp + QUARTER) % CYCLE)
            return k * (c0 - c)

    def ideal_parts(self, n):
        """(left, right) ideal: ideal sines of phase_L and of phase_C / 2^64 + U."""
        pl, pc, _ = self.phases(n)
        with localcontext() as ctx:
            ctx.prec = PREC + 10
            left = ideal_sine_decimal(pl)
            x = Decimal(pc) / Decimal(CYCLE) + self.ideal_beat_cycles(n)
            right = decimal_sin_decimal_cycles(x)
            return left, right


# (fixture, left carrier, beat rate (the cycle center with a cycle), cycle or
# None, length_s): the Story 2.5 binaural fixtures in recipes/fixtures/valid/.
# binaural-cycle-sleep.json is the hash probe's binaural-cycle-<fs> source.
SLEEP_CYCLE = (1.5, 60.0, 270.0)  # swing, period, start phase: 0 to 3 Hz every 60 s, from 0 Hz rising
BINAURAL_FIXTURES = (
    ("binaural-beat-0.json", 400.0, 0.0, None, 5.0),
    ("binaural-beat-6.json", 400.0, 6.0, None, 5.0),
    ("binaural-beat-29.json", 400.0, 29.0, None, 5.0),
    ("binaural-cycle-sleep.json", 100.0, 1.5, SLEEP_CYCLE, 120.0),
)
SEEK_S = 55.0  # the seek point of the cycle fixture's seek test and probe component

# Cycles-to-units cases: (label, v).
CYCLES_TO_UNITS_CASES = (
    ("zero", 0.0),
    ("negative zero", -0.0),
    ("quarter cycle", 0.25),
    ("minus a quarter cycle", -0.25),
    ("half cycle", 0.5),
    ("minus a half cycle", -0.5),
    ("tie 1/2 unit, to even", 2.0**-65),
    ("tie 3/2 units, to even", 3 * 2.0**-65),
    ("tie -1/2 unit, to even", -(2.0**-65)),
    ("tie -3/2 units, to even", -3 * 2.0**-65),
    ("tiny negative", -1e-30),
    ("largest below 1", 1.0 - 2.0**-53),
    ("smallest above -1", -(1.0 - 2.0**-53)),
    ("one cycle", 1.0),
    ("minus one cycle", -1.0),
    ("Sleep K", 1.5 * 60.0 * float.fromhex(INV_TWO_PI_HEX)),
    ("minus Sleep K", -(1.5 * 60.0 * float.fromhex(INV_TWO_PI_HEX))),
    ("twice Sleep K", 2.0 * (1.5 * 60.0 * float.fromhex(INV_TWO_PI_HEX))),
    ("half above the last fractional binade", 2.0**52 - 0.5),
    ("2^52, no fraction", 2.0**52),
    ("2^63, no fraction", 2.0**63),
    ("+infinity", math.inf),
    ("-infinity", -math.inf),
    ("NaN", math.nan),
)

# Rate cycle constants: the Sleep swing and period at these start phases.
RATE_CYCLE_START_DEGREES = (0.0, 90.0, 180.0, 270.0, 360.0)

# Ideal rate-curve law: (center, swing, period, start phase, times in s).
RATE_CURVE_CASES = (
    (1.5, 1.5, 60.0, 270.0, (0.0, 7.5, 15.0, 30.0, 45.0, 60.0, 75.0, 120.0)),
    (1.5, 1.5, 60.0, 0.0, (0.0, 15.0, 30.0, 45.0, 60.0)),
    (1.5, 1.5, 60.0, 90.0, (0.0, 15.0, 30.0)),
)


def cycles_to_units_rows():
    rows = []
    for label, v in CYCLES_TO_UNITS_CASES:
        u, f = cycles_to_units(v)
        rows.append({"label": label, "v_hex": hexf(v),
                     "f_hex": "none" if f is None else hexf(f),
                     "f_times_2_64_hex": "none" if f is None else hexf(f * 2.0**64),
                     "units": str(u)})
    return rows


def rate_cycle_rows():
    swing, period, _ = SLEEP_CYCLE
    rows = []
    for fs in RATES:
        for deg in RATE_CYCLE_START_DEGREES:
            layer = BinauralLayer(100.0, 1.5, (swing, period, deg), fs)
            with localcontext() as ctx:
                ctx.prec = PREC + 10
                ideal_c0 = ideal_sine_decimal((layer.p0 + QUARTER) % CYCLE)
            rows.append({
                "swing_hex": hexf(swing), "period_hex": hexf(period), "start_hex": hexf(deg),
                "x_hex": hexf(layer.start_ratio), "p0": str(layer.p0),
                "inv_period_hex": hexf(layer.inv_period), "fs": fs,
                "q_hex": hexf(layer.q_cycle), "inc_cycle": str(layer.inc_cycle),
                "swing_period_hex": hexf(layer.swing_period), "k_hex": hexf(layer.k),
                "c0_bits": bits(layer.c0), "ideal_c0": format_ideal(ideal_c0),
            })
    return rows


def rate_curve_rows():
    rows = []
    for center, swing, period, deg, times in RATE_CURVE_CASES:
        for t in times:
            theta = Fraction(t) / Fraction(period) + Fraction(deg) / 360  # cycles
            with localcontext() as ctx:
                ctx.prec = PREC + 10
                sin_t = decimal_sin_cycles(theta)
                cos_t = decimal_sin_cycles(theta + Fraction(1, 4))
                cos_0 = decimal_sin_cycles(Fraction(deg) / 360 + Fraction(1, 4))
                rate = exact_decimal(center) + exact_decimal(swing) * sin_t
                k = exact_decimal(swing) * exact_decimal(period) / (2 * decimal_pi())
                beat = exact_decimal(center) * exact_decimal(t) + k * (cos_0 - cos_t)
            rows.append({"center_hex": hexf(center), "swing_hex": hexf(swing),
                         "period_hex": hexf(period), "start_hex": hexf(deg), "t_hex": hexf(t),
                         "ideal_rate": format_trimmed(rate), "ideal_beat_cycles": format_trimmed(beat)})
    return rows


def binaural_sample_indices(layer, frames, fs):
    """Start, block boundaries, the cycle's quarter points, the seek point, the end."""
    indices = {0, 1, 63, 64, 65, 127, 128, 1000, frames - 1, frames, frames + 63}
    if layer.cycle is not None:
        for k in (1, 2, 3, 4):
            n = first_at_or_above(k * QUARTER, layer.inc_cycle)
            indices.update((n - 1, n))
        seek, _ = samples(SEEK_S, fs)
        indices.update((seek - 1, seek, seek + 1))
    return sorted(i for i in indices if i >= 0)


# Engine against ideal, per sample (signal spec, Binaural layer, Error bound):
# the engine sine error is at most E_T (the polynomial truncation plus
# rounding), so a fixed-beat ear is within E_T of its ideal and a cycle right
# ear within 2 pi (K (|c0 error| + E_T) + 2^-49 K + 2^-64) + E_T.
E_T = 5.7e-8


def binaural_bound(layer):
    if layer.cycle is None:
        return E_T
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        c0_err = abs(Decimal(layer.c0) - ideal_sine_decimal((layer.p0 + QUARTER) % CYCLE))
    k = layer.k
    return 2 * math.pi * (k * (float(c0_err) + E_T) + 2.0**-49 * k + 2.0**-64) + E_T


def binaural_sample_rows():
    rows = []
    for fs in RATES:
        for fixture, left_hz, beat_hz, cycle, length_s in BINAURAL_FIXTURES:
            layer = BinauralLayer(left_hz, beat_hz, cycle, fs)
            frames, _ = samples(length_s, fs)
            bound = binaural_bound(layer)
            for n in binaural_sample_indices(layer, frames, fs):
                pl, pc, pp = layer.phases(n)
                c, v, u, pr, left, right = layer.engine_parts(n)
                past_end = n >= frames
                if past_end:
                    left = right = 0.0
                    ideal_l = ideal_r = "0"
                else:
                    if cycle is None:
                        # A fixed beat: the right ear is the stub's oscillator.
                        assert pr == (n * increment(left_hz + beat_hz, fs)[0]) % CYCLE
                    il, ir = layer.ideal_parts(n)
                    assert abs(Decimal(left) - il) <= Decimal(E_T), (fixture, fs, n)
                    assert abs(Decimal(right) - ir) <= Decimal(bound), (fixture, fs, n)
                    ideal_l, ideal_r = format_ideal(il), format_ideal(ir)
                row = {
                    "case": "past_end" if past_end else "signal",
                    "fixture": fixture, "fs": fs,
                    "left_hex": hexf(left_hz), "beat_hex": hexf(beat_hz),
                    "center_hex": hexf(layer.center_hz),
                    "swing_hex": "none" if cycle is None else hexf(cycle[0]),
                    "period_hex": "none" if cycle is None else hexf(cycle[1]),
                    "start_hex": "none" if cycle is None else hexf(cycle[2]),
                    "length_hex": hexf(length_s),
                    "inc_left": str(layer.inc_left), "inc_center": str(layer.inc_center),
                    "p0": "none" if cycle is None else str(layer.p0),
                    "inc_cycle": "none" if cycle is None else str(layer.inc_cycle),
                    "k_hex": "none" if cycle is None else hexf(layer.k),
                    "frames": str(frames), "n": str(n),
                    "phase_left": str(pl), "phase_center": str(pc),
                    "phase_cycle": "none" if pp is None else str(pp),
                    "c_bits": "none" if c is None else bits(c),
                    "v_bits": "none" if v is None else bits(v),
                    "u_units": str(u), "phase_right": str(pr),
                    "left_bits": bits(left), "right_bits": bits(right),
                    "ideal_left": ideal_l, "ideal_right": ideal_r,
                }
                rows.append(row)
    return rows


# ------------------------------------------------------- 24-bit rounding

Q24_MAX = 8388607   # 2^23 - 1
Q24_MIN = -8388608  # -2^23
LSB = 2.0**-23      # one 24-bit step, as a binary64 sample value


def quantize_24(s):
    """Spec 24-bit rounding of the binary64 sample s, in exact arithmetic."""
    if math.isnan(s):
        return 0
    if math.isinf(s):
        return Q24_MAX if s > 0 else Q24_MIN
    x = Fraction(s) * 2**23
    if x >= Q24_MAX:
        return Q24_MAX
    if x <= Q24_MIN:
        return Q24_MIN
    return round_half_even(x)


def pack_24(v):
    """3 bytes, little-endian two's complement, as lowercase hex."""
    return (v % 2**24).to_bytes(3, "little").hex()


# (rule, label, sample). Rules: clamp (at or past full scale), nan, tie
# (x exactly k + 1/2), round (nearest, not a tie), zero (signed zeros and
# values that round to 0 without a tie).
QUANTIZE_CASES = (
    ("clamp", "+1.0", 1.0),
    ("clamp", "next binary64 above +1.0", math.nextafter(1.0, 2.0)),
    ("clamp", "+2.0", 2.0),
    ("clamp", "+infinity", math.inf),
    ("clamp", "largest binary64 below +1.0 (x above 8388607)", math.nextafter(1.0, 0.0)),
    ("clamp", "x exactly 8388607", Q24_MAX * LSB),
    ("clamp", "-1.0 (x exactly -8388608)", -1.0),
    ("clamp", "next binary64 below -1.0", math.nextafter(-1.0, -2.0)),
    ("clamp", "-2.0", -2.0),
    ("clamp", "-infinity", -math.inf),
    ("nan", "NaN", math.nan),
    ("zero", "+0.0", 0.0),
    ("zero", "-0.0", -0.0),
    ("zero", "smallest positive subnormal", 5e-324),
    ("zero", "smallest negative subnormal", -5e-324),
    ("zero", "just under +0.5 LSB", math.nextafter(0.5 * LSB, 0.0)),
    ("tie", "+0.5 LSB", 0.5 * LSB),
    ("tie", "-0.5 LSB", -0.5 * LSB),
    ("tie", "+1.5 LSB", 1.5 * LSB),
    ("tie", "-1.5 LSB", -1.5 * LSB),
    ("tie", "+2.5 LSB", 2.5 * LSB),
    ("tie", "-2.5 LSB", -2.5 * LSB),
    ("tie", "+8388606.5 LSB (below the clamp)", 8388606.5 * LSB),
    ("tie", "-8388607.5 LSB (above the clamp)", -8388607.5 * LSB),
    ("round", "just over +0.5 LSB", math.nextafter(0.5 * LSB, 1.0)),
    ("round", "just under +1.5 LSB", math.nextafter(1.5 * LSB, 0.0)),
    ("round", "just over -2.5 LSB", math.nextafter(-2.5 * LSB, 0.0)),
    ("round", "+8388606.75 LSB", 8388606.75 * LSB),
    ("round", "+0.5", 0.5),
    ("round", "-0.5", -0.5),
    ("round", "+0.1 (x about 838860.8)", 0.1),
    ("round", "-0.1", -0.1),
    ("round", "stub chain sample (beat 0, 44.1 kHz, n = 37, left)",
     struct.unpack(">d", bytes.fromhex("3feb7b6766e57522"))[0]),
    ("round", "406 Hz binaural sine sample (48 kHz, n = 63)",
     struct.unpack(">d", bytes.fromhex("bfca4084ea41d438"))[0]),
)


def quantize_rows():
    rows = []
    for rule, label, s in QUANTIZE_CASES:
        v = quantize_24(s)
        rows.append({"rule": rule, "label": label, "s_hex": hexf(s),
                     "x_hex": hexf(s * 2.0**23) if not math.isnan(s) else "nan",
                     "value": v, "bytes": pack_24(v)})
    return rows


def build():
    return {
        "spec": "docs/signal-spec.md (sections core, sine, internal block size, stub chain, theta reference, gamma PAC layer, coupling, binaural layer, rate curve, and 24-bit rounding)",
        "generator": "tools/signal_spec_vectors.py",
        "cycle": str(CYCLE),
        "sine_coefficients": sine_coefficients(),
        "exact_phases": [{"label": label, "phase": str(p), "sine": ideal_sine(p)}
                         for label, p in EXACT_PHASES],
        "increments": increment_rows(),
        "samples": sample_rows(),
        "phase_steps": phase_step_rows(),
        "carrier_450_44100": carrier_rows(),
        "engine_sine_bits": engine_sine_rows(),
        "block_frames": BLOCK_FRAMES,
        "blocks": block_rows(),
        "stub_chain": stub_chain_rows(),
        "theta_constants": {
            "shapes": list(THETA_SHAPES),
            "on_share_percent": dec(THETA_ON_SHARE_PERCENT),
            "edge_ms": dec(THETA_EDGE_MS),
            "on_share_hex": hexf(theta_on_share()),
            "edge_s_hex": hexf(theta_edge_s()),
            "h_units": str(half_on_units()),
        },
        "ratio_to_phase": ratio_rows(),
        "theta_edges": theta_edge_rows(),
        "theta_envelopes": theta_envelope_rows(),
        "theta_samples": theta_sample_rows(),
        "gamma_constants": {
            "carrier_waves": list(GAMMA_CARRIER_WAVES),
            "modeled_carrier_waves": list(GAMMA_MODELED_WAVES),
            "couplings": list(GAMMA_COUPLINGS),
        },
        "gamma_envelopes": gamma_envelope_rows(),
        "gamma_samples": gamma_sample_rows(),
        "gamma_bus": gamma_bus_rows(),
        "coupling_constants": {
            "couplings": list(GAMMA_COUPLINGS_2_3),
            "coupled": list(COUPLED),
            "swell_length_s": dec(SWELL_LENGTH_S),
        },
        "coupling_phases": coupling_phase_rows(),
        "swells": swell_rows(),
        "swell_samples": swell_sample_rows(),
        "binaural_constants": {
            "waveforms": list(BINAURAL_WAVEFORMS),
            "modeled_waveforms": list(BINAURAL_MODELED_WAVEFORMS),
            "inv_two_pi_hex": INV_TWO_PI_HEX,
            "seek_s": dec(SEEK_S),
        },
        "cycles_to_units": cycles_to_units_rows(),
        "rate_cycles": rate_cycle_rows(),
        "rate_curve": rate_curve_rows(),
        "binaural_samples": binaural_sample_rows(),
        "quantize_24": quantize_rows(),
    }


def render(data):
    return json.dumps(data, indent=2) + "\n"


# --------------------------------------------------------------- tables


def tables(data):
    out = []
    out.append("| Power | Exact | Binary64 (hex float) |")
    out.append("| --- | --- | --- |")
    for r in data["sine_coefficients"]:
        out.append(f"| {r['power']} | {r['exact']} | `{r['hex']}` |")
    out.append("")
    out.append("| Phase | Ideal sine |")
    out.append("| --- | --- |")
    for r in data["exact_phases"]:
        out.append(f"| {r['label']} | {r['sine']} |")
    out.append("")
    out.append("| Case | Signal | f_hz | fs | q (hex) | inc |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    for r in data["increments"]:
        out.append(f"| {r['case']} | {r['label']} | `{r['f_hex']}` | {r['fs']} | `{r['q_hex']}` | {r['inc']} |")
    out.append("")
    out.append("| Case | Duration | t_s | fs | t_s * fs (hex) | n |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    for r in data["samples"]:
        out.append(f"| {r['case']} | {r['label']} | `{r['t_hex']}` | {r['fs']} | `{r['product_hex']}` | {r['n']} |")
    out.append("")
    out.append("| Steps case | Start phase | inc | Steps | Phase after |")
    out.append("| --- | --- | --- | --- | --- |")
    for r in data["phase_steps"]:
        out.append(f"| {r['label']} | {r['start']} | {r['inc']} | {r['steps']} | {r['phase']} |")
    out.append("")
    c = data["carrier_450_44100"]
    out.append("| n | Phase | Ideal sine |")
    out.append("| --- | --- | --- |")
    for r in c["samples"]:
        out.append(f"| {r['n']} | {r['phase']} | {r['sine']} |")
    out.append("")
    out.append("| Engine sine case | Phase | Engine sine (binary64 bits) |")
    out.append("| --- | --- | --- |")
    for r in data["engine_sine_bits"]:
        out.append(f"| {r['label']} | {r['phase']} | `{r['bits']}` |")
    out.append("")
    out.append("| Frame | Block | Offset in block |")
    out.append("| --- | --- | --- |")
    for r in data["blocks"]:
        out.append(f"| {r['frame']} | {r['block']} | {r['offset']} |")
    out.append("")
    out.append("| Fixture | fs | Theta carrier (hex) | Left carrier (hex) | Beat rate (hex) "
               "| Right carrier (hex) | Theta inc | Left inc | Right inc | Frames |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    seen = set()
    for r in data["stub_chain"]:
        key = (r["fixture"], r["fs"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f"| {r['fixture']} | {r['fs']} | `{r['theta_carrier_hex']}` "
                   f"| `{r['carrier_left_hex']}` | `{r['beat_rate_hex']}` "
                   f"| `{r['carrier_right_hex']}` | {r['inc_theta']} | {r['inc_left']} "
                   f"| {r['inc_right']} | {r['frames']} |")
    out.append("")
    out.append("| Case | Fixture | fs | n | Theta phase | Left phase | Right phase "
               "| Theta (binary64 bits) | Left (binary64 bits) | Right (binary64 bits) "
               "| Theta ideal | Left ideal | Right ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["stub_chain"]:
        out.append(f"| {r['case']} | {r['fixture']} | {r['fs']} | {r['n']} | {r['phase_theta']} "
                   f"| {r['phase_left']} | {r['phase_right']} | `{r['theta_bits']}` "
                   f"| `{r['left_bits']}` | `{r['right_bits']}` "
                   f"| {r['ideal_theta']} | {r['ideal_left']} | {r['ideal_right']} |")
    out.append("")
    out.append("| Ratio case | r (hex) | x = r * 2^63 (hex) | P |")
    out.append("| --- | --- | --- | --- |")
    for r in data["ratio_to_phase"]:
        out.append(f"| {r['label']} | `{r['r_hex']}` | `{r['x_hex']}` | {r['phase']} |")
    out.append("")
    out.append("| Rate (hex) | E (hex) | w = E * rate (hex) | W |")
    out.append("| --- | --- | --- | --- |")
    for r in data["theta_edges"]:
        out.append(f"| `{r['rate_hex']}` | `{r['edge_s_hex']}` | `{r['w_hex']}` | {r['w_units']} |")
    out.append("")
    out.append("| Shape | Rate (hex) | W | H | Envelope phase | Segment | e (binary64 bits) | e ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["theta_envelopes"]:
        out.append(f"| {r['shape']} | `{r['rate_hex']}` | {r['w_units']} | {r['h_units']} "
                   f"| {r['phase']} | {r['region']} | `{r['e_bits']}` | {r['ideal_e']} |")
    out.append("")
    out.append("| Fixture | fs | Carrier (hex) | Rate (hex) | Depth (hex) | Shape "
               "| Carrier inc | Rate inc | W | Frames |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    seen = set()
    for r in data["theta_samples"]:
        key = (r["fixture"], r["fs"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f"| {r['fixture']} | {r['fs']} | `{r['carrier_hex']}` | `{r['rate_hex']}` "
                   f"| `{r['depth_hex']}` | {r['shape']} | {r['inc_carrier']} | {r['inc_rate']} "
                   f"| {r['w_units']} | {r['frames']} |")
    out.append("")
    out.append("| Case | Fixture | fs | n | Carrier phase | Envelope phase | Segment "
               "| e (binary64 bits) | a (binary64 bits) | Theta (binary64 bits) | e ideal | Theta ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["theta_samples"]:
        out.append(f"| {r['case']} | {r['fixture']} | {r['fs']} | {r['n']} | {r['phase_carrier']} "
                   f"| {r['phase_rate']} | {r['region']} | `{r['e_bits']}` | `{r['a_bits']}` "
                   f"| `{r['theta_bits']}` | {r['ideal_e']} | {r['ideal_theta']} |")
    out.append("")
    out.append("| Depth (hex) | Envelope phase | e (binary64 bits) | a (binary64 bits) | e ideal | a ideal |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    for r in data["gamma_envelopes"]:
        out.append(f"| `{r['depth_hex']}` | {r['phase']} | `{r['e_bits']}` | `{r['a_bits']}` "
                   f"| {r['ideal_e']} | {r['ideal_a']} |")
    out.append("")
    out.append("| Fixture | fs | Carrier (hex) | Rate (hex) | Depth (hex) | Carrier wave | Coupling "
               "| Theta carrier (hex) | Theta rate (hex) | Theta depth (hex) | Theta shape "
               "| Carrier inc | Rate inc | Frames |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    seen = set()
    for r in data["gamma_samples"]:
        key = (r["fixture"], r["fs"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f"| {r['fixture']} | {r['fs']} | `{r['carrier_hex']}` | `{r['rate_hex']}` "
                   f"| `{r['depth_hex']}` | {r['carrier_wave']} | {r['coupling']} "
                   f"| `{r['theta_carrier_hex']}` | `{r['theta_rate_hex']}` | `{r['theta_depth_hex']}` "
                   f"| {r['theta_shape']} | {r['inc_carrier']} | {r['inc_rate']} | {r['frames']} |")
    out.append("")
    out.append("| Case | Fixture | fs | n | Carrier phase | Envelope phase "
               "| e (binary64 bits) | a (binary64 bits) | Gamma (binary64 bits) | e ideal | Gamma ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["gamma_samples"]:
        out.append(f"| {r['case']} | {r['fixture']} | {r['fs']} | {r['n']} | {r['phase_carrier']} "
                   f"| {r['phase_rate']} | `{r['e_bits']}` | `{r['a_bits']}` "
                   f"| `{r['gamma_bits']}` | {r['ideal_e']} | {r['ideal_gamma']} |")
    out.append("")
    out.append("| Case | Fixture | fs | n | Theta (binary64 bits) | Gamma (binary64 bits) "
               "| Bus (binary64 bits) | Theta ideal | Gamma ideal | Bus ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["gamma_bus"]:
        out.append(f"| {r['case']} | {r['fixture']} | {r['fs']} | {r['n']} | `{r['theta_bits']}` "
                   f"| `{r['gamma_bits']}` | `{r['bus_bits']}` | {r['ideal_theta']} "
                   f"| {r['ideal_gamma']} | {r['ideal_bus']} |")
    out.append("")
    out.append("| Coupling phase (hex) | x = deg / 360 (hex) | x * 2^64 (hex) | C |")
    out.append("| --- | --- | --- | --- |")
    for r in data["coupling_phases"]:
        out.append(f"| `{r['deg_hex']}` | `{r['x_hex']}` | `{r['x_times_2_64_hex']}` | {r['c_units']} |")
    out.append("")
    out.append("| Depth (hex) | Coupling phase (hex) | C | Theta envelope phase | Gamma envelope phase "
               "| s (binary64 bits) | e (binary64 bits) | a (binary64 bits) | s ideal | a ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["swells"]:
        out.append(f"| `{r['depth_hex']}` | `{r['deg_hex']}` | {r['c_units']} | {r['phase_theta_envelope']} "
                   f"| {r['phase_gamma_envelope']} | `{r['s_bits']}` | `{r['e_bits']}` | `{r['a_bits']}` "
                   f"| {r['ideal_s']} | {r['ideal_a']} |")
    out.append("")
    out.append("| Fixture | fs | Carrier (hex) | Rate (hex) | Depth (hex) | Coupling | Coupling phase (hex) | C "
               "| Theta carrier (hex) | Theta rate (hex) | Theta depth (hex) | Theta shape "
               "| Carrier inc | Rate inc | Theta envelope inc | Frames |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    seen = set()
    for r in data["swell_samples"]:
        key = (r["fixture"], r["fs"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f"| {r['fixture']} | {r['fs']} | `{r['carrier_hex']}` | `{r['rate_hex']}` "
                   f"| `{r['depth_hex']}` | {r['coupling']} | `{r['deg_hex']}` | {r['c_units']} "
                   f"| `{r['theta_carrier_hex']}` | `{r['theta_rate_hex']}` | `{r['theta_depth_hex']}` "
                   f"| {r['theta_shape']} | {r['inc_carrier']} | {r['inc_rate']} "
                   f"| {r['inc_theta_envelope']} | {r['frames']} |")
    out.append("")
    out.append("| Case | Fixture | fs | n | Carrier phase | Envelope phase | Theta envelope phase "
               "| s (binary64 bits) | e (binary64 bits) | a (binary64 bits) | Gamma (binary64 bits) "
               "| Theta (binary64 bits) | Bus (binary64 bits) | s ideal | Gamma ideal | Bus ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["swell_samples"]:
        out.append(f"| {r['case']} | {r['fixture']} | {r['fs']} | {r['n']} | {r['phase_carrier']} "
                   f"| {r['phase_rate']} | {r['phase_theta_envelope']} | `{r['s_bits']}` | `{r['e_bits']}` "
                   f"| `{r['a_bits']}` | `{r['gamma_bits']}` | `{r['theta_bits']}` | `{r['bus_bits']}` "
                   f"| {r['ideal_s']} | {r['ideal_gamma']} | {r['ideal_bus']} |")
    out.append("")
    out.append("| Case | v (hex) | f = v - trunc(v) (hex) | f * 2^64 (hex) | U |")
    out.append("| --- | --- | --- | --- | --- |")
    for r in data["cycles_to_units"]:
        out.append(f"| {r['label']} | `{r['v_hex']}` | `{r['f_hex']}` | `{r['f_times_2_64_hex']}` "
                   f"| {r['units']} |")
    out.append("")
    out.append("| Swing (hex) | Period (hex) | Start phase (hex) | x = deg / 360 (hex) | P0 "
               "| 1 / P (hex) | fs | q (hex) | inc_P | s * P (hex) | K (hex) "
               "| c0 (binary64 bits) | c0 ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["rate_cycles"]:
        out.append(f"| `{r['swing_hex']}` | `{r['period_hex']}` | `{r['start_hex']}` | `{r['x_hex']}` "
                   f"| {r['p0']} | `{r['inv_period_hex']}` | {r['fs']} | `{r['q_hex']}` "
                   f"| {r['inc_cycle']} | `{r['swing_period_hex']}` | `{r['k_hex']}` "
                   f"| `{r['c0_bits']}` | {r['ideal_c0']} |")
    out.append("")
    out.append("| Center (hex) | Swing (hex) | Period (hex) | Start phase (hex) | t (hex) "
               "| Rate ideal (Hz) | Beat phase ideal (cycles) |")
    out.append("| --- | --- | --- | --- | --- | --- | --- |")
    for r in data["rate_curve"]:
        out.append(f"| `{r['center_hex']}` | `{r['swing_hex']}` | `{r['period_hex']}` "
                   f"| `{r['start_hex']}` | `{r['t_hex']}` | {r['ideal_rate']} "
                   f"| {r['ideal_beat_cycles']} |")
    out.append("")
    out.append("| Fixture | fs | Left carrier (hex) | Beat rate (hex) | f_C (hex) | Swing (hex) "
               "| Period (hex) | Start phase (hex) | Left inc | Center inc | P0 | inc_P | K (hex) | Frames |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    seen = set()
    for r in data["binaural_samples"]:
        key = (r["fixture"], r["fs"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f"| {r['fixture']} | {r['fs']} | `{r['left_hex']}` | `{r['beat_hex']}` "
                   f"| `{r['center_hex']}` | `{r['swing_hex']}` | `{r['period_hex']}` "
                   f"| `{r['start_hex']}` | {r['inc_left']} | {r['inc_center']} | {r['p0']} "
                   f"| {r['inc_cycle']} | `{r['k_hex']}` | {r['frames']} |")
    out.append("")
    out.append("| Case | Fixture | fs | n | Left phase | Center phase | Cycle phase "
               "| c (binary64 bits) | v (binary64 bits) | U | Right phase "
               "| Left (binary64 bits) | Right (binary64 bits) | Left ideal | Right ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["binaural_samples"]:
        out.append(f"| {r['case']} | {r['fixture']} | {r['fs']} | {r['n']} | {r['phase_left']} "
                   f"| {r['phase_center']} | {r['phase_cycle']} | `{r['c_bits']}` | `{r['v_bits']}` "
                   f"| {r['u_units']} | {r['phase_right']} | `{r['left_bits']}` | `{r['right_bits']}` "
                   f"| {r['ideal_left']} | {r['ideal_right']} |")
    out.append("")
    out.append("| Rule | Case | s (hex) | x = s * 2^23 (hex) | Value | Bytes (little-endian) |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    for r in data["quantize_24"]:
        out.append(f"| {r['rule']} | {r['label']} | `{r['s_hex']}` | `{r['x_hex']}` "
                   f"| {r['value']} | `{r['bytes']}` |")
    return "\n".join(out) + "\n"


def main(argv):
    parser = argparse.ArgumentParser(description="Write the signal spec worked vectors.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--tables", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv[1:])
    text = render(build())
    if args.tables:
        sys.stdout.write(tables(json.loads(text)))
        return 0
    if args.check:
        try:
            found = args.out.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"signal spec vectors: cannot read {args.out}: {exc}")
            return 1
        if found != text:
            print(f"signal spec vectors: {args.out} differs from a fresh run of {Path(__file__).name}")
            return 1
        print(f"signal spec vectors: {args.out} is current")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"signal spec vectors: wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
