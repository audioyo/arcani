"""Writes the worked test vectors of docs/signal-spec.md: core, sine, internal block size, stub chain, theta reference, gamma PAC layer, coupling, bursts, binaural layer and rate curve, loop, components, 24-bit rounding.

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
- Bursts (Story 2.4): the burst constants Hb and Wb by the spec's binary64
  products and an exact nearest-integer rounding, the burst gate (the
  smoothed on-off segments on u = p_E - C by exact integer comparisons, the
  engine raised cosine on the edges) and a = 1 - (d * g) * (1 - e) evaluated
  in binary64 in the spec's operation order (engine bits), with the ideal
  values at 25 digits: the ideal cosines and sine in decimal arithmetic and
  the exact law on the binary64 depth. The bus is one binary64 addition of
  the engine theta and gamma taps; its ideal is the exact sum of the ideal taps.
- Binaural layer and rate curve (Story 2.5): the cycle cosine (the engine
  sine's fold of p + 2^62 and an odd Taylor polynomial to x^15, coefficients
  the binary64 nearest +-1/k!), the cycles-to-units rule in
  exact Fraction arithmetic, the rate cycle constants (P0 by the coupling
  phase rule, inc_P by the increment rule on 1.0 / P, K = (s * P) * the
  binary64 nearest 1 / (2 pi), checked against decimal pi), and the right
  ear phase phase_C + U evaluated in binary64 in the spec's operation order
  (engine bits), with ideal values at 25 digits: the exact K = s P / (2 pi),
  ideal cosines of the integer cycle phases, and the ideal sine of
  phase_C / 2^64 + U in decimal arithmetic. The ideal rate-curve law
  (rate and phase at chosen times) is exact in decimal arithmetic.
- Rate curves on the theta and gamma rates (Story 2.6): the same cycle
  constants per curved layer, U by the cycle cosine and the cycles-to-units
  rule, the curved envelope phases n * inc + U mod 2^64, and the theta,
  gamma, and bus taps evaluated in binary64 in the spec's operation order
  (engine bits), with ideal values at 25 digits: the ideal U (exact K, ideal
  cosines) rounded to the nearest phase unit, the ideal envelopes, swell,
  and burst gate of that integer phase, and the ideal carrier sines.
- Components (Story 3.1): the line model of every v0.1 shape. Frequencies
  are exact sums of the binary64 recipe values (Fraction); levels are the
  closed-form Fourier coefficients of the envelopes, the swell, and the burst
  gate in decimal arithmetic at 70 digits (decimal pi, sine, cosine, and
  square root), written with 25 significant digits; coincident burst lines
  are summed as complex amplitudes. Nothing is sampled or transformed.
- Spacing (Story 3.2): per ear, every pair of component rows of different
  layers. The distance c + A sin(theta) + B cos(theta) over the one shared
  rate cycle in decimal arithmetic (exact centers, decimal cosines and
  sines of the start phases, exact at the quarter points), its minimum
  max(0, |c| - H) with H = sqrt(A^2 + B^2), and the first cycle fraction of
  that minimum by exact bisection on the fraction (decimal cosine), with
  the rates there. Rows mirrored below 0 Hz are compared as their listed
  intervals. Nothing is sampled.
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


# ---------------------------------------------------------------- bursts
#
# Story 2.4 (signal spec, Bursts): 50 ms bursts. The burst gate is the
# smoothed on-off segment rule applied to u = p_E - C mod 2^64, with half
# width Hb (25 ms of theta envelope phase) and edge Wb (10 ms); it scales the
# gamma AM depth, a = 1 - (d * g) * (1 - e). The gamma envelope runs free.
# The fixed constants are written here in their row units; the tests check
# them against the range rows burst-width and burst-edge (ms).

BURST_WIDTH_MS = 50.0   # row burst-width: the full width
BURST_EDGE_MS = 10.0    # row burst-edge: each raised-cosine edge, inside the width
GAMMA_COUPLINGS_2_4 = ("uncoupled", "smooth_swell", "bursts")
COUPLED_2_4 = ("smooth_swell", "bursts")
BURST_RATES_HZ = (1.0, 2.0, 5.5, 6.0)       # the theta edge length rates
BURST_GATE_RATES_HZ = (1.0, 6.0)            # both ends of the theta rate range
BURST_GATE_DEGREES = (0.0, 270.0)
BURST_AMPLITUDE_DEPTHS = (0.0, 25.0, 100.0)
BURST_AMPLITUDE_GAMMA_PHASES = (0, HALF)    # gamma envelope peak and trough


def burst_half_width_units(rate_hz):
    """Hb: w = (50.0 / 1000.0 / 2) * rate_hz, then w * 2^64 (exact), nearest, ties to even."""
    w = (BURST_WIDTH_MS / 1000.0 / 2) * rate_hz
    return nearest_u64(w * 2.0**64), w


def burst_edge_units(rate_hz):
    """Wb: w = (10.0 / 1000.0) * rate_hz, then w * 2^64 (exact), nearest, ties to even."""
    w = (BURST_EDGE_MS / 1000.0) * rate_hz
    return nearest_u64(w * 2.0**64), w


def burst_region(u, hb, wb):
    """Name of the burst gate segment of u = p_E - C mod 2^64 (exact integer tests)."""
    m = u if u < HALF else CYCLE - u
    if m <= hb - wb:
        return "center" if u == 0 else "plateau"
    if m >= hb:
        return "off"
    return "falling edge" if u < HALF else "rising edge"


def burst_gate(p_e, c_units, hb, wb):
    """Engine burst gate g in binary64, the spec's segments and operation order."""
    u = (p_e - c_units) % CYCLE
    m = u if u < HALF else CYCLE - u
    if m <= hb - wb:
        return 1.0
    if m >= hb:
        return 0.0
    return engine_raised_cosine(m - (hb - wb), wb)


def burst_gate_ideal(p_e, c_units, hb, wb):
    """Ideal burst gate: the same segments, the ideal raised cosine (Decimal)."""
    u = (p_e - c_units) % CYCLE
    m = u if u < HALF else CYCLE - u
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        if m <= hb - wb:
            return Decimal(1)
        if m >= hb:
            return Decimal(0)
        return (1 + decimal_cos_pi(m - (hb - wb), wb)) * (Decimal(1) / Decimal(2))


class BurstLayer(GammaLayer):
    """One burst gamma PAC layer at one sample rate (signal spec, Bursts)."""

    def __init__(self, carrier_hz, rate_hz, depth_percent, phase_deg, theta_rate, fs):
        super().__init__(carrier_hz, rate_hz, depth_percent, fs)
        self.phase_deg = phase_deg
        self.c_units, self.c_ratio = coupling_phase_units(phase_deg)
        self.inc_theta_envelope = increment(theta_rate, fs)[0]
        self.hb, _ = burst_half_width_units(theta_rate)
        self.wb, _ = burst_edge_units(theta_rate)

    def theta_envelope_phase(self, n):
        return (n * self.inc_theta_envelope) % CYCLE

    def engine_parts(self, n):
        """(g, e, a, gamma) in binary64, the spec's per-sample operation order."""
        pc, pm = self.phases(n)
        g = burst_gate(self.theta_envelope_phase(n), self.c_units, self.hb, self.wb)
        e = gamma_envelope(pm)
        a = coupled_amplitude(self.depth, g, e)
        return g, e, a, a * engine_sine(pc)

    def ideal_parts(self, n):
        """(g, gamma) ideal: exact law on the binary64 d, ideal cosines and sine."""
        pc, pm = self.phases(n)
        with localcontext() as ctx:
            ctx.prec = PREC + 10
            g = burst_gate_ideal(self.theta_envelope_phase(n), self.c_units, self.hb, self.wb)
            e = gamma_envelope_ideal(pm)
            a = 1 - exact_decimal(self.depth) * g * (1 - e)
            return g, a * ideal_sine_decimal(pc)


BURST_LENGTH_S = 5.0
BURST_THETA = (450.0, 6.0, 75.0, "sine")   # theta carrier, rate, depth, shape
BURST_GAMMA = (250.0, 100.0, 0.0)          # gamma carrier, depth, coupling phase

# (fixture, gamma rate in Hz): the Story 2.4 burst fixtures in
# recipes/fixtures/valid/. In this order they are the hash probe's
# gamma-bursts-<fs> components.
BURST_FIXTURES = (
    ("bursts-40hz.json", 40.0),
    ("bursts-45hz.json", 45.0),
    ("bursts-60hz.json", 60.0),
)


def burst_edge_rows():
    rows = []
    for rate in BURST_RATES_HZ:
        hb, wh = burst_half_width_units(rate)
        wb, we = burst_edge_units(rate)
        # Every edge fits inside its half of the burst, and the burst inside
        # half a theta cycle, so bursts never overlap.
        assert wb < hb - wb and hb < HALF, (rate, hb, wb)
        rows.append({
            "rate_hex": hexf(rate),
            "half_width_s_hex": hexf(BURST_WIDTH_MS / 1000.0 / 2),
            "w_half_width_hex": hexf(wh), "hb_units": str(hb),
            "edge_s_hex": hexf(BURST_EDGE_MS / 1000.0),
            "w_edge_hex": hexf(we), "wb_units": str(wb),
            "plateau_end_units": str(hb - wb),
        })
    return rows


def burst_gate_offsets(hb, wb):
    """u values: the center, both sides of every segment boundary, mid-edge,
    the half cycle, and the mirror image of each on the rising side."""
    p_end = hb - wb
    falling = (0, 1, p_end, p_end + 1, p_end + wb // 2, hb - 1, hb, HALF)
    rising = tuple(CYCLE - u for u in (1, p_end, p_end + 1, p_end + wb // 2, hb - 1, hb))
    return falling + rising


def burst_gate_rows():
    rows = []
    for rate in BURST_GATE_RATES_HZ:
        hb, _ = burst_half_width_units(rate)
        wb, _ = burst_edge_units(rate)
        for deg in BURST_GATE_DEGREES:
            c, _ = coupling_phase_units(deg)
            for u in burst_gate_offsets(hb, wb):
                p_e = (c + u) % CYCLE
                g = burst_gate(p_e, c, hb, wb)
                assert 0.0 <= g <= 1.0, (rate, deg, u, g)
                rows.append({
                    "rate_hex": hexf(rate), "deg_hex": hexf(deg), "c_units": str(c),
                    "hb_units": str(hb), "wb_units": str(wb),
                    "phase_theta_envelope": str(p_e), "u": str(u),
                    "region": burst_region(u, hb, wb), "g_bits": bits(g),
                    "ideal_g": format_trimmed(burst_gate_ideal(p_e, c, hb, wb)),
                })
    return rows


def burst_amplitude_rows():
    """a = 1 - (d * g) * (1 - e) at the burst center, mid falling edge, and
    off, at the gamma envelope peak and trough, at 6 Hz and C = 0."""
    rate = BURST_GATE_RATES_HZ[-1]
    hb, _ = burst_half_width_units(rate)
    wb, _ = burst_edge_units(rate)
    rows = []
    for depth_percent in BURST_AMPLITUDE_DEPTHS:
        d = depth_percent / 100.0
        for u in (0, hb - wb + wb // 2, hb):
            for p_m in BURST_AMPLITUDE_GAMMA_PHASES:
                g = burst_gate(u, 0, hb, wb)
                e = gamma_envelope(p_m)
                a = coupled_amplitude(d, g, e)
                assert 0.0 < a <= 1.0, (depth_percent, u, p_m)
                if g == 0.0 or d == 0.0:
                    assert a == 1.0, (depth_percent, u, p_m)   # unmodulated, exactly
                if g == 1.0:
                    assert a == 1.0 - d * (1.0 - e), (depth_percent, u, p_m)  # the uncoupled law
                with localcontext() as ctx:
                    ctx.prec = PREC + 10
                    i_g = burst_gate_ideal(u, 0, hb, wb)
                    i_a = 1 - exact_decimal(d) * i_g * (1 - gamma_envelope_ideal(p_m))
                rows.append({
                    "depth_hex": hexf(depth_percent), "rate_hex": hexf(rate),
                    "phase_theta_envelope": str(u), "region": burst_region(u, hb, wb),
                    "phase_gamma_envelope": str(p_m),
                    "g_bits": bits(g), "e_bits": bits(e), "a_bits": bits(a),
                    "ideal_g": format_trimmed(i_g), "ideal_a": format_trimmed(i_a),
                })
    return rows


def burst_layers(fs):
    carrier, depth, deg = BURST_GAMMA
    for fixture, rate in BURST_FIXTURES:
        theta = ThetaLayer(*BURST_THETA, fs)
        gamma = BurstLayer(carrier, rate, depth, deg, BURST_THETA[1], fs)
        yield fixture, rate, theta, gamma


def burst_sample_indices(gamma, frames):
    """Start, block boundaries, around every segment boundary of the burst at
    sample 0 and of the next burst, both sides of the first gamma envelope
    trough, the last sample, past the end."""
    indices = {0, 1, 63, 64, 65, 127, 128, 1000, frames - 1, frames, frames + 63}
    inc = gamma.inc_theta_envelope
    c, hb, wb = gamma.c_units, gamma.hb, gamma.wb
    for u in (hb - wb, hb, CYCLE - hb, CYCLE - (hb - wb), CYCLE):
        b = (c + u) % CYCLE or CYCLE
        n = first_at_or_above(b, inc)
        # Some boundaries are strict (plateau end, edge start), so the sample
        # after the first one at or above the boundary is kept as well.
        indices.update((n - 1, n, n + 1))
    n = first_at_or_above(HALF, gamma.inc_rate)
    indices.update((n - 1, n))
    return sorted(i for i in indices if i >= 0)


def burst_sample_rows():
    rows = []
    for fs in RATES:
        for fixture, rate, theta, gamma in burst_layers(fs):
            frames, _ = samples(BURST_LENGTH_S, fs)
            for n in burst_sample_indices(gamma, frames):
                pc, pm = gamma.phases(n)
                pe = gamma.theta_envelope_phase(n)
                u = (pe - gamma.c_units) % CYCLE
                past_end = n >= frames
                if past_end:
                    g_bits = e_bits = a_bits = gamma_bits = theta_bits = bus_bits = bits(0.0)
                    ideal_g = ideal_gamma = ideal_bus = "0"
                else:
                    g, e, a, gt = gamma.engine_parts(n)
                    # a > 0 (e > 0 and d * g <= 1), so the engine tap is never -0.0.
                    assert a > 0.0 and bits(gt) != bits(-0.0), (fixture, fs, n)
                    if g == 0.0:
                        assert a == 1.0, (fixture, fs, n)   # off the burst: unmodulated
                    t = theta.engine_sample(n)
                    bus = t + gt  # stereo bus: one binary64 addition
                    g_bits, e_bits, a_bits = bits(g), bits(e), bits(a)
                    gamma_bits, theta_bits, bus_bits = bits(gt), bits(t), bits(bus)
                    with localcontext() as ctx:
                        ctx.prec = PREC + 10
                        i_g, i_gt = gamma.ideal_parts(n)
                        i_t = theta.ideal_parts(n)[1]
                        ideal_g, ideal_gamma = format_ideal(i_g), format_ideal(i_gt)
                        ideal_bus = format_ideal(i_t + i_gt)
                row = {
                    "case": "past_end" if past_end else "signal",
                    "fixture": fixture, "fs": fs,
                    "carrier_hex": hexf(BURST_GAMMA[0]), "rate_hex": hexf(rate),
                    "depth_hex": hexf(BURST_GAMMA[1]), "length_hex": hexf(BURST_LENGTH_S),
                    "carrier_wave": "sine", "coupling": "bursts", "deg_hex": hexf(BURST_GAMMA[2]),
                    "c_units": str(gamma.c_units),
                    "hb_units": str(gamma.hb), "wb_units": str(gamma.wb),
                }
                row.update(_theta_columns(BURST_THETA))
                row.update({
                    "inc_carrier": str(gamma.inc_carrier), "inc_rate": str(gamma.inc_rate),
                    "inc_theta_envelope": str(gamma.inc_theta_envelope),
                    "frames": str(frames), "n": str(n),
                    "phase_carrier": str(pc), "phase_rate": str(pm),
                    "phase_theta_envelope": str(pe),
                    "region": "past end" if past_end else burst_region(u, gamma.hb, gamma.wb),
                    "g_bits": g_bits, "e_bits": e_bits, "a_bits": a_bits,
                    "gamma_bits": gamma_bits, "theta_bits": theta_bits, "bus_bits": bus_bits,
                    "ideal_g": ideal_g, "ideal_gamma": ideal_gamma, "ideal_bus": ideal_bus,
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


CYCLE_COSINE_POWERS = (1, 3, 5, 7, 9, 11, 13, 15)
# Bound on the engine cycle cosine against the ideal cosine (threshold row
# cycle-cosine-error, -200 dBFS): 1e-10.
E_C = 1e-10


def cycle_cosine_coefficients():
    rows = []
    for k in CYCLE_COSINE_POWERS:
        sign = -1 if (k // 2) % 2 else 1
        value = sign * binary64(Fraction(1, math.factorial(k)))
        rows.append({"power": k, "exact": f"{'-' if sign < 0 else '+'}1/{k}!",
                     "hex": float.hex(value)})
    return rows


def cycle_cosine(phase):
    """Spec engine cycle cosine: the engine sine's fold of phase + 2^62, then an
    odd Taylor polynomial to x^15 in fixed Horner order, binary64."""
    p = (phase + QUARTER) % CYCLE
    if CYCLE // 4 < p < CYCLE // 2 + CYCLE // 4:
        p = (CYCLE // 2 - p) % CYCLE
    s = p - CYCLE if p >= CYCLE // 2 else p
    x = float(s) * float.fromhex(RADIANS_PER_UNIT_HEX)
    c = {r["power"]: float.fromhex(r["hex"]) for r in cycle_cosine_coefficients()}
    z = x * x
    r = c[15]
    for k in (13, 11, 9, 7, 5, 3, 1):
        r = r * z + c[k]
    return r * x


CYCLE_COSINE_PHASES = (
    ("0", 0), ("1", 1), ("2^60", 2**60), ("2^61", 2**61), ("2^62 - 1", 2**62 - 1),
    ("2^62", 2**62), ("2^62 + 1", 2**62 + 1), ("3 * 2^61", 3 * 2**61), ("2^63 - 1", 2**63 - 1),
    ("2^63", 2**63), ("2^63 + 1", 2**63 + 1), ("3 * 2^62", 3 * 2**62), ("7 * 2^61", 7 * 2**61),
    ("2^64 - 1", 2**64 - 1), ("Sleep P0 + 1000 * inc_P at 48 kHz", (3 * 2**62 + 1000 * 6405119470038) % 2**64),
)


def cycle_cosine_rows():
    rows = []
    for label, phase in CYCLE_COSINE_PHASES:
        y = cycle_cosine(phase)
        with localcontext() as ctx:
            ctx.prec = PREC + 10
            ideal = ideal_sine_decimal((phase + QUARTER) % CYCLE)
        assert abs(Decimal(y) - ideal) <= Decimal(E_C), label
        rows.append({"label": label, "phase": str(phase), "bits": bits(y),
                     "ideal": format_ideal(ideal)})
    return rows


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
            self.c0 = cycle_cosine(self.p0)
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
            c = cycle_cosine(pp)
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
    # Story 2.6: the theta and gamma cycles of the rate-curve fixtures.
    (3.5, 2.5, 60.0, 0.0, (0.0, 15.0, 30.0, 45.0, 60.0, 120.0)),
    (4.0, 2.0, 60.0, 0.0, (0.0, 15.0, 45.0, 60.0)),
    (45.0, 15.0, 60.0, 0.0, (0.0, 15.0, 45.0, 60.0)),
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
# rounding) and the cycle cosine's at most E_C, so a fixed-beat ear is within
# E_T of its ideal and a cycle right ear within
# 2 pi (K (|c0 error| + E_C) + 2^-49 K + 2^-64) + E_T.
E_T = 5.7e-8


def binaural_bound(layer):
    if layer.cycle is None:
        return E_T
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        c0_err = abs(Decimal(layer.c0) - ideal_sine_decimal((layer.p0 + QUARTER) % CYCLE))
    k = layer.k
    return 2 * math.pi * (k * (float(c0_err) + E_C) + 2.0**-49 * k + 2.0**-64) + E_T


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


# ------------------------------------------ rate curves on theta and gamma
#
# Story 2.6 (signal spec, Rate curve): the Story 2.5 law, integral, cycle
# cosine, and cycles-to-units rule, unchanged, on the theta envelope phase
# and the gamma envelope phase: phase_E[n] = n * inc_E + U_E[n] and
# phase_M[n] = n * inc_M + U_M[n] mod 2^64, each U with its layer's own P0,
# inc_P, K, and c0. The carriers do not change. The swell and the burst gate
# read the curved phase_E. W, Hb, and Wb stay at the center rate_hz.


class LayerCycle:
    """One theta or gamma rate cycle at one sample rate (signal spec, Rate curve, Engine)."""

    def __init__(self, center_hz, cycle, fs):
        swing, period, start = cycle
        self.center_hz, self.swing, self.period, self.start = center_hz, swing, period, start
        self.p0, self.start_ratio = coupling_phase_units(start)
        self.inv_period = 1.0 / period  # one binary64 division
        self.inc_cycle, self.q_cycle = increment(self.inv_period, fs)
        self.swing_period = swing * period  # one rounding
        self.k = self.swing_period * inv_two_pi()  # one rounding
        self.c0 = cycle_cosine(self.p0)
        self.lowest = center_hz - swing   # one rounding (Rate curve, Range checks)
        self.highest = center_hz + swing  # one rounding

    def phase(self, n):
        return (self.p0 + n * self.inc_cycle) % CYCLE

    def engine_units(self, n):
        """U[n] in phase units: cycles_to_units(K * (c0 - cycle_cosine(p_P[n])))."""
        c = cycle_cosine(self.phase(n))
        v = self.k * (self.c0 - c)  # c0 - c, then K times it
        return cycles_to_units(v)[0]

    def ideal_cycles(self, n):
        """Ideal U[n] in cycles, K = s P / (2 pi) exact, ideal cosines of the integer phases."""
        with localcontext() as ctx:
            ctx.prec = PREC + 10
            k = exact_decimal(self.swing) * exact_decimal(self.period) / (2 * decimal_pi())
            c0 = ideal_sine_decimal((self.p0 + QUARTER) % CYCLE)
            c = ideal_sine_decimal((self.phase(n) + QUARTER) % CYCLE)
            return k * (c0 - c)

    def ideal_units(self, n):
        """The ideal U[n] as the nearest integer number of phase units, mod 2^64."""
        with localcontext() as ctx:
            ctx.prec = PREC + 10
            x = self.ideal_cycles(n) * Decimal(CYCLE)
            return int(x.to_integral_value(rounding="ROUND_HALF_EVEN")) % CYCLE


# Largest addition one curved phase makes to a tap's bound (Rate curve,
# Reference): the envelope's largest slope per cycle times the phase error
# delta, at most 3e-7 over every compile-accepted cycle.
CURVE_ADD = 3e-7
B_SINE = 1e-6  # row sine-error, -120 dBFS, as linear full scale

RATE_CURVE_LENGTH_S = 120.0
THETA_CYCLE = (2.5, 60.0, 0.0)          # 3.5 +- 2.5 Hz: the whole theta-rate row, from the center rising
THETA_CYCLE_COUPLED = (2.0, 60.0, 0.0)  # 4 +- 2 Hz
GAMMA_CYCLE = (15.0, 60.0, 0.0)         # 45 +- 15 Hz: the whole gamma-rate row

# (fixture, theta, gamma): the Story 2.6 fixtures in recipes/fixtures/valid/,
# 120 s, no binaural layer. theta is None or (carrier_hz, rate_hz,
# am_depth_percent, shape, cycle or None); gamma is None or (carrier_hz,
# rate_hz, am_depth_percent, coupling, coupling_phase_deg or None, cycle or
# None); a cycle is (swing_hz, period_s, start_phase_deg).
# gamma-cycle-swell-theta-cycle.json and bursts-theta-cycle.json, in this
# order, are the hash probe's rate-curves-<fs> sources.
RATE_CURVE_FIXTURES = (
    ("theta-cycle-sine.json", (450.0, 3.5, 75.0, "sine", THETA_CYCLE), None),
    ("theta-cycle-smoothed-on-off.json", (450.0, 3.5, 75.0, "smoothed_on_off", THETA_CYCLE), None),
    ("gamma-cycle-uncoupled.json", None, (250.0, 45.0, 100.0, "uncoupled", None, GAMMA_CYCLE)),
    ("swell-theta-cycle.json", (450.0, 4.0, 75.0, "sine", THETA_CYCLE_COUPLED),
     (250.0, 40.0, 100.0, "smooth_swell", 0.0, None)),
    ("bursts-theta-cycle.json", (450.0, 4.0, 75.0, "sine", THETA_CYCLE_COUPLED),
     (250.0, 40.0, 100.0, "bursts", 0.0, None)),
    ("gamma-cycle-swell-theta-cycle.json", (450.0, 4.0, 75.0, "sine", THETA_CYCLE_COUPLED),
     (250.0, 45.0, 100.0, "smooth_swell", 0.0, GAMMA_CYCLE)),
)
RATE_CURVE_PROBE_FIXTURES = ("gamma-cycle-swell-theta-cycle.json", "bursts-theta-cycle.json")


class CurvedFixture:
    """The theta and gamma layers of one Story 2.6 fixture at one sample rate."""

    def __init__(self, fixture, theta, gamma, fs):
        self.fixture, self.theta_spec, self.gamma_spec, self.fs = fixture, theta, gamma, fs
        self.theta = self.gamma = self.theta_cycle = self.gamma_cycle = None
        self.coupling, self.c_units, self.hb, self.wb = "none", 0, 0, 0
        if theta is not None:
            carrier, rate, depth, shape, cycle = theta
            self.theta = ThetaLayer(carrier, rate, depth, shape, fs)
            self.theta_cycle = None if cycle is None else LayerCycle(rate, cycle, fs)
        if gamma is not None:
            carrier, rate, depth, coupling, deg, cycle = gamma
            self.gamma = GammaLayer(carrier, rate, depth, fs)
            self.coupling = coupling
            self.c_units = coupling_phase_units(deg)[0] if deg is not None else 0
            if coupling == "bursts":
                theta_rate = theta[1] if theta is not None else 0.0
                self.hb = burst_half_width_units(theta_rate)[0]  # at the center rate
                self.wb = burst_edge_units(theta_rate)[0]
            self.gamma_cycle = None if cycle is None else LayerCycle(rate, cycle, fs)
        self.inc_theta_envelope = self.theta.inc_rate if self.theta is not None else 0

    def theta_phase(self, n, ideal=False):
        """(U_E, phase_E) engine or ideal; U_E = 0 without a theta cycle."""
        base = (n * self.inc_theta_envelope) % CYCLE
        if self.theta_cycle is None:
            return 0, base
        u = self.theta_cycle.ideal_units(n) if ideal else self.theta_cycle.engine_units(n)
        return u, (base + u) % CYCLE

    def gamma_phase(self, n, ideal=False):
        """(U_M, phase_M) engine or ideal; U_M = 0 without a gamma cycle."""
        base = (n * self.gamma.inc_rate) % CYCLE
        if self.gamma_cycle is None:
            return 0, base
        u = self.gamma_cycle.ideal_units(n) if ideal else self.gamma_cycle.engine_units(n)
        return u, (base + u) % CYCLE

    def engine(self, n):
        """(factor, theta, gamma, bus) in binary64; factor is s or g, None uncoupled."""
        t = g = 0.0
        factor = None
        _, pe = self.theta_phase(n)
        if self.theta is not None:
            th = self.theta
            e = engine_envelope(th.shape, pe, th.w_units, th.h_units)
            a = 1.0 - th.depth * (1.0 - e)
            t = a * engine_sine((n * th.inc_carrier) % CYCLE)
        if self.gamma is not None:
            ga = self.gamma
            _, pm = self.gamma_phase(n)
            e = gamma_envelope(pm)
            if self.coupling == "uncoupled":
                a = 1.0 - ga.depth * (1.0 - e)
            else:
                if self.coupling == "smooth_swell":
                    factor = swell(pe, self.c_units)
                else:
                    factor = burst_gate(pe, self.c_units, self.hb, self.wb)
                a = coupled_amplitude(ga.depth, factor, e)
            assert a > 0.0, (self.fixture, n)
            g = a * engine_sine((n * ga.inc_carrier) % CYCLE)
        return factor, t, g, t + g  # stereo bus: one binary64 addition

    def ideal(self, n):
        """(theta, gamma) ideal Decimals: the ideal envelopes at the ideal integer phases."""
        with localcontext() as ctx:
            ctx.prec = PREC + 10
            t = g = Decimal(0)
            _, pe = self.theta_phase(n, ideal=True)
            if self.theta is not None:
                th = self.theta
                e = ideal_envelope_decimal(th.shape, pe, th.w_units, th.h_units)
                a = 1 - exact_decimal(th.depth) * (1 - e)
                t = a * ideal_sine_decimal((n * th.inc_carrier) % CYCLE)
            if self.gamma is not None:
                ga = self.gamma
                _, pm = self.gamma_phase(n, ideal=True)
                e = gamma_envelope_ideal(pm)
                if self.coupling == "uncoupled":
                    a = 1 - exact_decimal(ga.depth) * (1 - e)
                else:
                    if self.coupling == "smooth_swell":
                        f = swell_ideal(pe, self.c_units)
                    else:
                        f = burst_gate_ideal(pe, self.c_units, self.hb, self.wb)
                    a = 1 - exact_decimal(ga.depth) * f * (1 - e)
                g = a * ideal_sine_decimal((n * ga.inc_carrier) % CYCLE)
            return t, g


def curved_fixtures(fs):
    for fixture, theta, gamma in RATE_CURVE_FIXTURES:
        yield CurvedFixture(fixture, theta, gamma, fs)


def _cycle_columns(prefix, cycle):
    if cycle is None:
        return {f"{prefix}_swing_hex": "none", f"{prefix}_period_hex": "none",
                f"{prefix}_start_hex": "none", f"{prefix}_p0": "none",
                f"{prefix}_inc_cycle": "none", f"{prefix}_k_hex": "none"}
    return {f"{prefix}_swing_hex": hexf(cycle.swing), f"{prefix}_period_hex": hexf(cycle.period),
            f"{prefix}_start_hex": hexf(cycle.start), f"{prefix}_p0": str(cycle.p0),
            f"{prefix}_inc_cycle": str(cycle.inc_cycle), f"{prefix}_k_hex": hexf(cycle.k)}


def layer_rate_cycle_rows():
    rows = []
    for fs in RATES:
        frames, _ = samples(RATE_CURVE_LENGTH_S, fs)
        for fx in curved_fixtures(fs):
            for layer, cyc, inc in (("theta", fx.theta_cycle, fx.inc_theta_envelope),
                                    ("gamma", fx.gamma_cycle,
                                     fx.gamma.inc_rate if fx.gamma is not None else 0)):
                if cyc is None:
                    continue
                with localcontext() as ctx:
                    ctx.prec = PREC + 10
                    ideal_c0 = ideal_sine_decimal((cyc.p0 + QUARTER) % CYCLE)
                rows.append({
                    "fixture": fx.fixture, "layer": layer, "fs": fs,
                    "center_hex": hexf(cyc.center_hz), "swing_hex": hexf(cyc.swing),
                    "period_hex": hexf(cyc.period), "start_hex": hexf(cyc.start),
                    "lowest_hex": hexf(cyc.lowest), "highest_hex": hexf(cyc.highest),
                    "inc_rate": str(inc), "p0": str(cyc.p0),
                    "inv_period_hex": hexf(cyc.inv_period), "inc_cycle": str(cyc.inc_cycle),
                    "swing_period_hex": hexf(cyc.swing_period), "k_hex": hexf(cyc.k),
                    "c0_bits": bits(cyc.c0), "ideal_c0": format_ideal(ideal_c0),
                    "frames": str(frames),
                })
    return rows


def rate_curve_sample_indices(fx, frames, fs):
    """Start, block boundaries, each curved cycle's quarter points, the seek point, the end."""
    indices = {0, 1, 63, 64, 65, 127, 128, 1000, frames - 1, frames, frames + 63}
    for cyc in (fx.theta_cycle, fx.gamma_cycle):
        if cyc is None:
            continue
        for k in (1, 2, 3, 4):
            n = first_at_or_above((k * QUARTER - cyc.p0) % CYCLE or CYCLE, cyc.inc_cycle)
            indices.update((n - 1, n, n + 37))  # n + 37: off the whole second, so the carrier is not near 0
    seek, _ = samples(SEEK_S, fs)
    indices.update((seek - 1, seek, seek + 1))
    return sorted(i for i in indices if i >= 0)


def rate_curve_sample_rows():
    rows = []
    for fs in RATES:
        frames, _ = samples(RATE_CURVE_LENGTH_S, fs)
        for fx in curved_fixtures(fs):
            # Engine against ideal, per tap (Rate curve, Reference): the
            # earlier section's bound plus CURVE_ADD for each curved phase
            # the tap reads.
            theta_reads = int(fx.theta_cycle is not None)
            gamma_reads = int(fx.gamma_cycle is not None) + int(
                fx.coupling in COUPLED_2_4 and fx.theta_cycle is not None)
            bound_t = 1.5 * B_SINE + 2.0**-47 + CURVE_ADD * theta_reads
            bound_g = 2 * B_SINE + 2.0**-46 + CURVE_ADD * gamma_reads
            bound_b = bound_t + bound_g + 2.0**-52
            for n in rate_curve_sample_indices(fx, frames, fs):
                ue, pe = fx.theta_phase(n)
                pt = (n * fx.theta.inc_carrier) % CYCLE if fx.theta is not None else 0
                if fx.gamma is not None:
                    um, pm = fx.gamma_phase(n)
                    pg = (n * fx.gamma.inc_carrier) % CYCLE
                else:
                    um = pm = pg = 0
                past_end = n >= frames
                if past_end:
                    t = g = bus = 0.0
                    ideal_t = ideal_g = ideal_bus = "0"
                    factor_bits = "none"
                else:
                    factor, t, g, bus = fx.engine(n)
                    factor_bits = "none" if factor is None else bits(factor)
                    it, ig = fx.ideal(n)
                    assert abs(Decimal(t) - it) <= Decimal(bound_t), (fx.fixture, fs, n)
                    assert abs(Decimal(g) - ig) <= Decimal(bound_g), (fx.fixture, fs, n)
                    with localcontext() as ctx:
                        ctx.prec = PREC + 10
                        ib = it + ig
                    assert abs(Decimal(bus) - ib) <= Decimal(bound_b), (fx.fixture, fs, n)
                    ideal_t, ideal_g, ideal_bus = format_ideal(it), format_ideal(ig), format_ideal(ib)
                row = {
                    "case": "past_end" if past_end else "signal",
                    "fixture": fx.fixture, "fs": fs, "length_hex": hexf(RATE_CURVE_LENGTH_S),
                    "frames": str(frames), "n": str(n),
                }
                row.update(_theta_columns(None if fx.theta_spec is None else fx.theta_spec[:4]))
                row.update(_cycle_columns("theta", fx.theta_cycle))
                if fx.gamma_spec is None:
                    row.update({"gamma_carrier_hex": "none", "gamma_rate_hex": "none",
                                "gamma_depth_hex": "none", "coupling": "none", "deg_hex": "none"})
                else:
                    gc, gr, gd, coupling, deg, _ = fx.gamma_spec
                    row.update({"gamma_carrier_hex": hexf(gc), "gamma_rate_hex": hexf(gr),
                                "gamma_depth_hex": hexf(gd), "coupling": coupling,
                                "deg_hex": "none" if deg is None else hexf(deg)})
                row.update(_cycle_columns("gamma", fx.gamma_cycle))
                row.update({
                    "inc_theta": str(fx.theta.inc_carrier) if fx.theta is not None else "0",
                    "inc_theta_envelope": str(fx.inc_theta_envelope),
                    "inc_gamma": str(fx.gamma.inc_carrier) if fx.gamma is not None else "0",
                    "inc_gamma_envelope": str(fx.gamma.inc_rate) if fx.gamma is not None else "0",
                    "w_units": str(fx.theta.w_units) if fx.theta is not None else "0",
                    "c_units": str(fx.c_units), "hb_units": str(fx.hb), "wb_units": str(fx.wb),
                    "phase_theta": str(pt),
                    "theta_cycle_phase": "none" if fx.theta_cycle is None else str(fx.theta_cycle.phase(n)),
                    "theta_u": str(ue), "phase_theta_envelope": str(pe),
                    "phase_gamma": str(pg),
                    "gamma_cycle_phase": "none" if fx.gamma_cycle is None else str(fx.gamma_cycle.phase(n)),
                    "gamma_u": str(um), "phase_gamma_envelope": str(pm),
                    "factor_bits": factor_bits,
                    "theta_bits": bits(t), "gamma_bits": bits(g), "bus_bits": bits(bus),
                    "ideal_theta": ideal_t, "ideal_gamma": ideal_g, "ideal_bus": ideal_bus,
                })
                rows.append(row)
    return rows


# ------------------------------------------------------------------ loop
#
# Story 2.7 (Loop): a looping recipe's opening, body, seams, and end, and its
# compile rules, in exact Fraction arithmetic. The engine's binary64 tests of
# the spec are evaluated beside the exact ones, and the generator asserts
# they agree on every case.

LOOP_MODES = ("focus", "learn")
LOOP_MODE_ROWS = {"focus": "max-run-time-focus", "learn": "max-run-time-learn"}
MAX_RUN_TIME_MIN = {"focus": 45.0, "learn": 20.0}  # rows max-run-time-focus and max-run-time-learn (min = max)
LOOP_LENGTH_RULE = "loop session ends at the max run time"
LOOP_WHOLE_SAMPLES_RULE = "loop time not whole samples"
LOOP_WHOLE_SAMPLES_LIMIT = "a multiple of 0.25 s (whole samples at 44100 and 48000 Hz)"
LOOP_WHOLE_CYCLES_RULE = "loop body not whole rate cycles"
LOOP_EXCEEDS_RULE = "loop opening and body exceed the session"
LOOP_WINDOW_S = 8.0        # the seam windows of the loop render tests
LOOP_PROBE_SEGMENT_S = 5.0  # each hash probe loop segment
LOOP_PROBE_SEAM = 9         # the probe's second segment is centered on this seam


def js_number(x):
    """The shortest round-trip text of a binary64, as ECMAScript writes it (integers without .0)."""
    if x == int(x) and abs(x) < 1e21:
        return str(int(x))
    return repr(x)


def loop_recipe(mode, opening, body, cap, length, theta, gamma, binaural=None):
    """A looping recipe's values. theta and gamma as in RATE_CURVE_FIXTURES;
    binaural is None or (carrier_left_hz, beat_rate_hz, cycle or None)."""
    return {"loop": (mode, opening, body, cap), "length_s": length,
            "theta": theta, "gamma": gamma, "binaural": binaural}


LOOP_THETA = (450.0, 4.0, 75.0, "sine", THETA_CYCLE_COUPLED)  # 4 +- 2 Hz, from the center rising
LOOP_SWELL = (250.0, 40.0, 100.0, "smooth_swell", 0.0, None)
LOOP_BURSTS = (250.0, 40.0, 100.0, "bursts", 0.0, None)
LOOP_BASE = loop_recipe("learn", 60.0, 120.0, 20.0, 1200.0, LOOP_THETA, LOOP_SWELL)
SLEEP_CYCLE = (1.5, 60.0, 270.0)


def loop_variant(**changes):
    mode, opening, body, cap = LOOP_BASE["loop"]
    values = {"mode": mode, "opening": opening, "body": body, "cap": cap,
              "length": LOOP_BASE["length_s"], "theta": LOOP_BASE["theta"], "gamma": LOOP_BASE["gamma"],
              "binaural": None}
    values.update(changes)
    return loop_recipe(values["mode"], values["opening"], values["body"], values["cap"], values["length"],
                       values["theta"], values["gamma"], values["binaural"])


# The Story 2.7 fixtures in recipes/fixtures/valid/. The first three compile;
# the rest are schema-valid and rejected at compile, one per rule (the cycle
# rule once per cycle path). loop-swell-theta-cycle.json is rendered in full,
# loop-bursts-theta-cycle.json in seam windows only, and
# loop-swell-theta-cycle.json is the hash probe's loop-<fs> source.
LOOP_FIXTURES = (
    ("loop-swell-theta-cycle.json", LOOP_BASE),
    ("loop-bursts-theta-cycle.json", loop_variant(gamma=LOOP_BURSTS)),
    ("loop-focus-no-cycle.json", loop_variant(mode="focus", opening=0.0, body=90.25, cap=45.0, length=2700.0,
                                              theta=(450.0, 4.0, 75.0, "sine", None), gamma=None)),
    ("loop-focus-cap-46.json", loop_variant(mode="focus", cap=46.0, length=2760.0)),
    ("loop-learn-cap-45.json", loop_variant(cap=45.0, length=2700.0)),
    ("loop-learn-cap-19.json", loop_variant(cap=19.0, length=1140.0)),
    ("loop-length-not-cap.json", loop_variant(length=1100.0)),
    ("loop-opening-negative.json", loop_variant(opening=-60.0)),
    ("loop-body-zero.json", loop_variant(body=0.0)),
    ("loop-opening-not-whole-samples.json", loop_variant(opening=60.1)),
    ("loop-body-not-whole-samples.json", loop_variant(body=120.125)),
    ("loop-body-off-cycle.json", loop_variant(body=90.0)),
    ("loop-gamma-body-off-cycle.json", loop_variant(
        body=90.0, theta=(450.0, 4.0, 75.0, "sine", None),
        gamma=(250.0, 45.0, 100.0, "uncoupled", None, GAMMA_CYCLE))),
    ("loop-binaural-body-off-cycle.json", loop_variant(
        body=90.0, theta=(450.0, 4.0, 75.0, "sine", None), gamma=None, binaural=(100.0, 1.5, SLEEP_CYCLE))),
    ("loop-exceeds-session.json", loop_variant(opening=1140.0)),
)
LOOP_FULL_RENDER_FIXTURE = "loop-swell-theta-cycle.json"
LOOP_WINDOW_FIXTURES = ("loop-swell-theta-cycle.json", "loop-bursts-theta-cycle.json")
LOOP_PROBE_FIXTURE = "loop-swell-theta-cycle.json"

LOOP_WHOLE_SAMPLE_TIMES = (0.0, 0.25, 60.0, 90.25, 120.0, 2700.0, 0.125, 0.1, 60.1, 120.125, 1.0 / 3.0)


def whole_samples_exact(t):
    """t * 44100 and t * 48000 both integers, exactly."""
    return all((Fraction(t) * fs).denominator == 1 for fs in RATES)


def is_binary64_integer(x):
    """The engine's integer test of a finite binary64 x >= 0: x >= 2^53, or x equals its truncation."""
    if x >= 2.0**53:
        return True
    return float(int(x)) == x


def whole_samples_engine(t):
    """Loop, Whole-sample rule: x = t * 4.0 (exact scale), an integer."""
    return is_binary64_integer(t * 4.0)


def whole_cycles_exact(body, period):
    return (Fraction(body) / Fraction(period)).denominator == 1


def whole_cycles_engine(body, period):
    """Loop, Cycle rule: q = body / period (one rounding), an integer, and q * period (one rounding) == body."""
    q = body / period
    return is_binary64_integer(q) and q * period == body


def loop_cycles(rec):
    """(parameter path, period_s) of every rate cycle of a recipe, in field order."""
    out = []
    theta, gamma, binaural = rec["theta"], rec["gamma"], rec["binaural"]
    if theta is not None and theta[4] is not None:
        out.append(("/theta_reference/rate_cycle/period_s", theta[4][1]))
    if gamma is not None and gamma[5] is not None:
        out.append(("/gamma_pac/rate_cycle/period_s", gamma[5][1]))
    if binaural is not None and binaural[2] is not None:
        out.append(("/binaural/beat_rate_cycle/period_s", binaural[2][1]))
    return out


def loop_error(rec):
    """The first Loop compile rule fault: (parameter, value, rule, limit), or None."""
    mode, opening, body, cap = rec["loop"]
    length = rec["length_s"]
    row_id = LOOP_MODE_ROWS[mode]
    bound = MAX_RUN_TIME_MIN[mode]
    if not cap >= bound:
        return "/loop/max_run_time_min", js_number(cap), "range.min", f">= {js_number(bound)} min (row {row_id})"
    if not cap <= bound:
        return "/loop/max_run_time_min", js_number(cap), "range.max", f"<= {js_number(bound)} min (row {row_id})"
    end = binary64(Fraction(cap) * 60)
    assert end == cap * 60.0
    if not length == end:
        return "/length_s", js_number(length), LOOP_LENGTH_RULE, f"= {js_number(end)} s ({js_number(cap)} min x 60)"
    if not opening >= 0.0:
        return "/loop/opening_s", js_number(opening), "range.min", ">= 0 s"
    if not body > 0.0:
        return "/loop/body_s", js_number(body), "range.min", "> 0 s"
    for path, t in (("/loop/opening_s", opening), ("/loop/body_s", body)):
        exact = whole_samples_exact(t)
        assert exact == whole_samples_engine(t), t
        if not exact:
            return path, js_number(t), LOOP_WHOLE_SAMPLES_RULE, LOOP_WHOLE_SAMPLES_LIMIT
    for path, period in loop_cycles(rec):
        exact = whole_cycles_exact(body, period)
        assert exact == whole_cycles_engine(body, period), (body, period)
        if not exact:
            return ("/loop/body_s", js_number(body), LOOP_WHOLE_CYCLES_RULE,
                    f"a whole multiple of {js_number(period)} s ({path})")
    total = binary64(Fraction(opening) + Fraction(body))
    assert total == opening + body
    if not total <= length:
        return "/loop/body_s", js_number(total), LOOP_EXCEEDS_RULE, f"<= {js_number(length)} s (length_s)"
    return None


def loop_frames(rec, fs):
    """(O, B, N, seams): the opening end, body length, session end, and seam frames O + k * B < N, k >= 1."""
    _, opening, body, _ = rec["loop"]
    o, _ = samples(opening, fs)
    b, _ = samples(body, fs)
    n, _ = samples(rec["length_s"], fs)
    assert Fraction(opening) * fs == o and Fraction(body) * fs == b  # exact: whole samples
    seams = []
    k = 1
    while o + k * b < n:
        seams.append(o + k * b)
        k += 1
    assert len(seams) == (n - o - 1) // b
    return o, b, n, seams


def loop_whole_sample_rows():
    rows = []
    for t in LOOP_WHOLE_SAMPLE_TIMES:
        exact = whole_samples_exact(t)
        assert exact == whole_samples_engine(t), t
        row = {"t_hex": hexf(t), "t": js_number(t), "four_t_hex": hexf(t * 4.0),
               "whole": "yes" if exact else "no"}
        for fs in RATES:
            n, product = samples(t, fs)
            row[f"product_{fs}_hex"] = hexf(product)
            row[f"exact_{fs}"] = "yes" if (Fraction(t) * fs).denominator == 1 else "no"
            row[f"n_{fs}"] = str(n)
        rows.append(row)
    return rows


def _loop_layers(rec):
    theta, gamma, binaural = rec["theta"], rec["gamma"], rec["binaural"]
    parts = []
    if theta is not None:
        carrier, rate, depth, shape, cycle = theta
        text = f"theta {js_number(carrier)} Hz {shape} {js_number(rate)} Hz"
        if cycle is not None:
            text += f" +- {js_number(cycle[0])} Hz / {js_number(cycle[1])} s"
        parts.append(text)
    if gamma is not None:
        carrier, rate, depth, coupling, _, cycle = gamma
        text = f"gamma {js_number(carrier)} Hz {js_number(rate)} Hz {coupling}"
        if cycle is not None:
            text += f" +- {js_number(cycle[0])} Hz / {js_number(cycle[1])} s"
        parts.append(text)
    if binaural is not None:
        left, beat, cycle = binaural
        text = f"binaural {js_number(left)} Hz beat {js_number(beat)} Hz"
        if cycle is not None:
            text += f" +- {js_number(cycle[0])} Hz / {js_number(cycle[1])} s"
        parts.append(text)
    return "; ".join(parts)


def loop_compile_rows():
    rows = []
    for fixture, rec in LOOP_FIXTURES:
        mode, opening, body, cap = rec["loop"]
        err = loop_error(rec)
        rows.append({
            "fixture": fixture, "mode": mode, "max_run_time_min": js_number(cap),
            "length_s": js_number(rec["length_s"]), "opening_s": js_number(opening), "body_s": js_number(body),
            "layers": _loop_layers(rec),
            "result": "accepted" if err is None else "rejected",
            "parameter": "none" if err is None else err[0],
            "value": "none" if err is None else err[1],
            "rule": "none" if err is None else err[2],
            "limit": "none" if err is None else err[3],
        })
    return rows


def loop_frame_rows():
    rows = []
    for fs in RATES:
        for fixture, rec in LOOP_FIXTURES:
            if loop_error(rec) is not None:
                continue
            mode, opening, body, cap = rec["loop"]
            o, b, n, seams = loop_frames(rec, fs)
            last_start = seams[-1] if seams else o
            rows.append({
                "fixture": fixture, "fs": fs, "mode": mode, "max_run_time_min": js_number(cap),
                "length_hex": hexf(rec["length_s"]), "opening_hex": hexf(opening), "body_hex": hexf(body),
                "opening_end_frame": str(o), "body_frames": str(b), "end_frame": str(n),
                "seam_count": str(len(seams)), "seam_frames": [str(s) for s in seams],
                "last_pass_frames": str(n - last_start),
            })
    return rows


# ------------------------------------------------- components (Story 3.1)
#
# The line model of docs/signal-spec.md, Components, in exact Fraction and
# 60-digit decimal arithmetic. Frequencies are exact sums of the binary64
# recipe values; levels are closed-form Fourier coefficients (decimal sine,
# cosine, pi, and square root). Nothing is sampled, and nothing comes from
# the engine or the reference.

COMPONENT_LEVEL_DB = 40.0          # row spectral-component-level
COMPONENT_LEVEL_ERROR = 1e-6       # row component-level-error (a ratio)
COMPONENT_FREQUENCY_ERROR = 1e-9   # row component-frequency-error (Hz)
COMPONENT_LAYERS = ("theta_reference", "gamma_pac", "binaural")
COMPONENT_NO_MODEL_RULE = "no component model"
THETA_HALF_ON_SHARE = Fraction(1, 4)   # h = H / 2^64 with H = 2^62


def component_threshold():
    """T = 10^(-L / 20) for the row value L in dB, as a Decimal (0.01 for 40 dB)."""
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        return Decimal(10) ** (-exact_decimal(COMPONENT_LEVEL_DB) / 20)


def _frac_decimal(x):
    """The exact value of a Fraction, int, or binary64 as a Decimal at the current precision."""
    f = Fraction(x)
    return Decimal(f.numerator) / Decimal(f.denominator)


def _sin_pi(z):
    """sin(pi z) for a Fraction z, as a Decimal."""
    return decimal_sin_cycles(Fraction(z) / 2)


def _cos_pi(z):
    """cos(pi z) for a Fraction z, as a Decimal."""
    return decimal_sin_cycles(Fraction(z) / 2 + Fraction(1, 4))


def _cos_units(units):
    """cos(2 pi units / 2^64) for an integer phase, as a Decimal."""
    return ideal_sine_decimal((units + QUARTER) % CYCLE)


def _sin_units(units):
    """sin(2 pi units / 2^64) for an integer phase, as a Decimal."""
    return ideal_sine_decimal(units % CYCLE)


def edge_factor(k, w):
    """P(k, w) = cos(pi k w) / (1 - (2 k w)^2), and pi / 4 at 2 k w = 1 (Decimal)."""
    x = 2 * k * Fraction(w)
    if x == 1:
        return decimal_pi() / 4
    return _cos_pi(k * Fraction(w)) / _frac_decimal(1 - x * x)


def edge_factor_bound(k, w):
    """Pb(k, w) >= |P(k, w)|: 1 while (2 k w)^2 <= 2, then 1 / ((2 k w)^2 - 1) (Fraction)."""
    x2 = (2 * k * Fraction(w)) ** 2
    return Fraction(1) if x2 <= 2 else 1 / (x2 - 1)


def on_off_coefficient(k, h, w):
    """The signed Fourier coefficient c_k of the smoothed on-off form with half
    on share h and edge share w (fractions of a cycle): the theta envelope
    (h = 1/4) and the burst gate (h = 0.025 * rate_hz)."""
    h, w = Fraction(h), Fraction(w)
    if k == 0:
        return _frac_decimal(2 * h - w)
    k = abs(k)
    return _sin_pi(k * (2 * h - w)) / (decimal_pi() * k) * edge_factor(k, w)


def on_off_bound(k, w):
    """B(k) >= |c_k| of the smoothed on-off form for k >= 1, never rising with k (Decimal)."""
    return _frac_decimal(edge_factor_bound(k, w)) / (decimal_pi() * k)


def sawtooth_coefficient(k, w):
    """|c_k| of the sawtooth and of the reverse saw with edge share w (Decimal)."""
    w = Fraction(w)
    if k == 0:
        return Decimal(1) / 2
    k = abs(k)
    pk = decimal_pi() * k
    return abs(edge_factor(k, w) + _sin_pi(k * w) / (pk * _frac_decimal(1 - w))) / (2 * pk)


def sawtooth_bound(k, w):
    """B(k) >= |c_k| of the sawtooth and the reverse saw for k >= 1, never rising with k."""
    pk = decimal_pi() * k
    return (_frac_decimal(edge_factor_bound(k, w))
            + 1 / (pk * _frac_decimal(1 - Fraction(w)))) / (2 * pk)


def has_cycle(cycle):
    """For the component model a rate has a cycle when its swing is above 0."""
    return cycle is not None and cycle[0] > 0.0


def twice_whole_ratio(gamma_rate, theta_rate):
    """n2 when twice the gamma rate is a whole multiple of the theta rate by the
    binary64 test of Components (q = (2 f_M) / f_theta is an integer and
    q * f_theta == 2 f_M), else None."""
    two = 2.0 * gamma_rate
    q = two / theta_rate
    if q == math.floor(q) and q * theta_rate == two:
        return int(q)
    return None


class ComponentError(Exception):
    """A shape with no component model (rule `no component model`)."""


def _theta_lines(theta, t):
    """[(theta_mult, amplitude)] of the theta reference, the carrier first."""
    _, rate, depth_percent, shape, _ = theta
    d = _frac_decimal(depth_percent / 100.0)
    w = Fraction(theta_edge_s() * rate)
    if shape == "sine":
        return [(0, 1 - d / 2), (1, d / 4), (-1, d / 4)]
    if shape == "smoothed_on_off":
        c0 = on_off_coefficient(0, THETA_HALF_ON_SHARE, w)

        def coefficient(k):
            return abs(on_off_coefficient(k, THETA_HALF_ON_SHARE, w))

        def bound(k):
            return on_off_bound(k, w)
    elif shape in ("sawtooth", "reverse_saw"):
        c0 = Decimal(1) / 2

        def coefficient(k):
            return sawtooth_coefficient(k, w)

        def bound(k):
            return sawtooth_bound(k, w)
    else:
        raise ComponentError(shape)
    carrier = 1 - d + d * c0
    lines = [(0, carrier)]
    k = 1
    while d * bound(k) >= t * carrier:
        c = coefficient(k)
        assert c <= bound(k), (shape, k)
        lines.append((k, d * c))
        lines.append((-k, d * c))
        k += 1
    return lines


def _gamma_lines(gamma, theta, t):
    """[(gamma_mult, theta_mult, amplitude)] of the gamma PAC layer, the carrier
    first; burst lines at one frequency are already summed."""
    _, rate, depth_percent, coupling, deg, cycle = gamma
    d = _frac_decimal(depth_percent / 100.0)
    if coupling == "uncoupled":
        return [(0, 0, 1 - d / 2), (1, 0, d / 4), (-1, 0, d / 4)]
    if coupling not in ("smooth_swell", "bursts"):
        raise ComponentError(coupling)
    if d == 0 or theta is None:
        # Compile accepts coupled gamma without a theta reference with AM depth
        # only at gamma depth 0: the carrier alone.
        return [(0, 0, Decimal(1))]
    if coupling == "smooth_swell":
        lines = [(0, 0, 1 - d / 4)]
        lines += [(0, j, d / 8) for j in (1, -1)]
        lines += [(i, 0, d / 8) for i in (1, -1)]
        lines += [(i, j, d / 16) for i in (1, -1) for j in (1, -1)]
        return lines
    theta_rate, theta_cycle = theta[1], theta[4]
    h = Fraction((BURST_WIDTH_MS / 1000.0 / 2) * theta_rate)
    w = Fraction((BURST_EDGE_MS / 1000.0) * theta_rate)
    g = functools.lru_cache(maxsize=None)(lambda j: on_off_coefficient(j, h, w))
    c_units = coupling_phase_units(deg)[0]
    n2 = None
    if not has_cycle(cycle) and not has_cycle(theta_cycle):
        n2 = twice_whole_ratio(rate, theta_rate)

    def last_j(scale, carrier):
        """The last j with scale * B(j) >= t * carrier (0 when there is none)."""
        j = 0
        while scale * on_off_bound(j + 1, w) >= t * carrier:
            j += 1
        return j

    def rotated(j, scale):
        """scale * g_j * e^(-2 pi i j C / 2^64) as (real, imaginary)."""
        units = (j * c_units) % CYCLE
        return scale * g(j) * _cos_units(units), -scale * g(j) * _sin_units(units)

    def magnitude(parts):
        re = sum(p[0] for p in parts)
        im = sum(p[1] for p in parts)
        return (re * re + im * im).sqrt()

    if n2 is not None and n2 % 2 == 0:
        # A whole ratio n: every line lies at f_G + m f_theta and sums the
        # members (0, m), (1, m - n), and (-1, m + n).
        n = n2 // 2

        def line(m):
            parts = [rotated(m, -d / 2), rotated(m - n, d / 4), rotated(m + n, d / 4)]
            if m == 0:
                parts.append((Decimal(1), Decimal(0)))
            return magnitude(parts)

        carrier = line(0)
        last = n + last_j(d, carrier)
        return [(0, 0, carrier)] + [(0, m, line(m)) for m in range(-last, last + 1) if m != 0]
    carrier = 1 - d * g(0) / 2
    last = last_j(d / 2, carrier)
    lines = [(0, 0, carrier)]
    for j in range(-last, last + 1):
        if j != 0:
            lines.append((0, j, d * abs(g(j)) / 2))
    if n2 is None:
        for j in range(-last, last + 1):
            for i in (1, -1):
                lines.append((i, j, d * abs(g(j)) / 4))
        return lines
    # A half-whole ratio (n2 odd): the lines (0, j) stand alone, and the line at
    # f_G + f_M + j f_theta sums the members (1, j) and (-1, j + n2).
    for j in range(-n2 - last, last + 1):
        amp = magnitude([rotated(j, d / 4), rotated(j + n2, d / 4)])
        i, jj = (1, j) if abs(j) < abs(j + n2) else (-1, j + n2)
        lines.append((i, jj, amp))
    return lines


def _interval(center, half):
    """(center, low, high) of a line that spans center +- half; a frequency
    below 0 is listed at its absolute value."""
    low, high = center - half, center + half
    if high <= 0:
        return -center, -high, -low
    if low < 0:
        return abs(center), Decimal(0), max(-low, high)
    return center, low, high


def component_table(theta, gamma, binaural, mute="none"):
    """The component table of one recipe (docs/signal-spec.md, Components).

    theta is None or (carrier_hz, rate_hz, am_depth_percent, shape, cycle);
    gamma is None or (carrier_hz, rate_hz, am_depth_percent, coupling,
    coupling_phase_deg or None, cycle); binaural is None or (carrier_left_hz,
    beat_rate_hz, cycle); a cycle is None or (swing_hz, period_s,
    start_phase_deg). Returns the rows in table order with the left and right
    tables merged: ear is `both` where a row is in both. Values are Decimals."""
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        t = component_threshold()
        margin = 2 * Decimal(COMPONENT_LEVEL_ERROR)
        rows = []

        def swing_and_phase(cycle):
            if not has_cycle(cycle):
                return Decimal(0), 0
            return _frac_decimal(cycle[0]), coupling_phase_units(cycle[2])[0]

        def add(layer, ear, mults, center, half, level):
            # No vector line may sit inside the in-or-out band around the threshold.
            assert abs(level - t) > margin, (layer, mults, level)
            if level < t:
                return
            c, lo, hi = _interval(center, half)
            # Story 3.2 reads whether the row is listed mirrored (Frequencies below 0).
            rows.append({"layer": layer, "ear": ear, "gamma_mult": mults[0], "theta_mult": mults[1],
                         "beat_mult": mults[2], "center": c, "low": lo, "high": hi, "level": level,
                         "mirrored": center - half < 0})

        s_t, p_t = swing_and_phase(theta[4]) if theta is not None else (Decimal(0), 0)
        if theta is not None:
            f_t, rate = _frac_decimal(theta[0]), _frac_decimal(theta[1])
            lines = _theta_lines(theta, t)
            carrier = lines[0][1]
            for k, amp in lines:
                add("theta_reference", "both", (0, k, 0), f_t + k * rate, abs(k) * s_t, amp / carrier)
        if gamma is not None:
            f_g, rate = _frac_decimal(gamma[0]), _frac_decimal(gamma[1])
            theta_rate = _frac_decimal(theta[1]) if theta is not None else Decimal(0)
            s_m, p_m = swing_and_phase(gamma[5])
            cos_between = _cos_units((p_m - p_t) % CYCLE)
            lines = _gamma_lines(gamma, theta, t)
            carrier = lines[0][2]
            for i, j, amp in lines:
                a, b = i * s_m, j * s_t
                if a != 0 and b != 0:
                    half = (a * a + b * b + 2 * a * b * cos_between).sqrt()
                else:
                    half = abs(a) + abs(b)
                add("gamma_pac", "both", (i, j, 0), f_g + i * rate + j * theta_rate, half,
                    amp / carrier)
        if binaural is not None:
            left, beat, cycle = binaural
            if mute != "left":
                add("binaural", "left", (0, 0, 0), _frac_decimal(left), Decimal(0), Decimal(1))
            if mute != "right":
                s_b = _frac_decimal(cycle[0]) if has_cycle(cycle) else Decimal(0)
                add("binaural", "right", (0, 0, 1), _frac_decimal(left + beat), s_b, Decimal(1))
        order = {layer: n for n, layer in enumerate(COMPONENT_LAYERS)}
        rows.sort(key=lambda r: (order[r["layer"]], r["center"], r["gamma_mult"], r["theta_mult"],
                                 r["beat_mult"], r["ear"]))
        return rows


def _cycle_member(cycle):
    swing, period, start = cycle
    return {"swing_hz": swing, "period_s": period, "start_phase_deg": start}


def component_layer_objects(theta, gamma, binaural):
    """The three layer objects as a recipe writes them (None where absent)."""
    t = g = b = None
    if theta is not None:
        carrier, rate, depth, shape, cycle = theta
        t = {"carrier_hz": carrier, "rate_hz": rate, "am_depth_percent": depth, "shape": shape}
        if cycle is not None:
            t["rate_cycle"] = _cycle_member(cycle)
    if gamma is not None:
        carrier, rate, depth, coupling, deg, cycle = gamma
        g = {"carrier_hz": carrier, "rate_hz": rate, "am_depth_percent": depth,
             "carrier_wave": "sine", "coupling": coupling}
        if deg is not None:
            g["coupling_phase_deg"] = deg
        if cycle is not None:
            g["rate_cycle"] = _cycle_member(cycle)
    if binaural is not None:
        left, beat, cycle = binaural
        b = {"carrier_left_hz": left, "beat_rate_hz": beat}
        if cycle is not None:
            b["beat_rate_cycle"] = _cycle_member(cycle)
    return t, g, b


def _json_text(value):
    """Compact JSON with every number as its shortest round-trip text."""
    if isinstance(value, dict):
        return "{" + ",".join(f"{json.dumps(k)}:{_json_text(v)}" for k, v in value.items()) + "}"
    if isinstance(value, float):
        return js_number(value)
    return json.dumps(value)


COMPONENT_CASE_LENGTH_S = 10.0


def component_recipe_text(case, theta, gamma, binaural):
    """A schema-valid recipe text for one component case: the case's layers
    and nothing else that could change the table."""
    recipe = {"schema_version": "1.0", "engine_version": "0.0.1", "seed": 42,
              "author": "Arcani test fixtures", "date": "2026-11-16",
              "rationale": f"Component vector case {case} (Story 3.1). A test recipe, not for listening.",
              "length_s": COMPONENT_CASE_LENGTH_S, "loudness_target_lufs": -36.0}
    t, g, b = component_layer_objects(theta, gamma, binaural)
    if t is not None:
        recipe["theta_reference"] = t
    if g is not None:
        recipe["gamma_pac"] = g
    if b is not None:
        recipe["binaural"] = b
    return _json_text(recipe)


_SINE_THETA = (450.0, 6.0, 75.0, "sine", None)
_SINE_THETA_CYCLE = (450.0, 4.0, 75.0, "sine", THETA_CYCLE_COUPLED)


def component_cases():
    """(case, fixture or None, mute, theta, gamma, binaural): every Epic 2
    shape fixture, then cases no fixture has. A fixture case is named after
    its file, and its layers equal the file's."""
    cases = []
    for fixture, carrier, rate, depth, shape, _ in THETA_FIXTURES:
        cases.append((fixture, "none", (carrier, rate, depth, shape, None), None, None))
    for fixture, (carrier, rate, depth), theta, _ in GAMMA_FIXTURES:
        cases.append((fixture, "none", None if theta is None else theta + (None,),
                      (carrier, rate, depth, "uncoupled", None, None), None))
    for fixture, shape, deg, depth in SWELL_FIXTURES:
        theta = None if shape is None else SWELL_THETA + (shape, None)
        cases.append((fixture, "none", theta, SWELL_GAMMA + (depth, "smooth_swell", deg, None), None))
    for fixture, rate in BURST_FIXTURES:
        cases.append((fixture, "none", BURST_THETA + (None,),
                      (BURST_GAMMA[0], rate, BURST_GAMMA[1], "bursts", BURST_GAMMA[2], None), None))
    for fixture, left, beat, cycle, _ in BINAURAL_FIXTURES:
        cases.append((fixture, "none", None, None, (left, beat, cycle)))
    for fixture, theta, gamma in RATE_CURVE_FIXTURES:
        cases.append((fixture, "none", theta, gamma, None))
    cases.append(("both-layers.json", "none", (200.0, 6.0, 0.0, "sine", None), None, (400.0, 6.0, None)))
    out = [(fixture[:-len(".json")], fixture) + tuple(rest) for fixture, *rest in cases]
    beat_6 = (400.0, 6.0, None)
    out += [
        # A muted ear has no binaural component.
        ("binaural-beat-6-mute-left", "binaural-beat-6.json", "left", None, None, beat_6),
        ("binaural-beat-6-mute-right", "binaural-beat-6.json", "right", None, None, beat_6),
        # The edge factor at 2 k w = 1 within one rounding (k = 10 at 5 Hz).
        ("theta-smoothed-on-off-5hz", None, "none", (450.0, 5.0, 75.0, "smoothed_on_off", None), None, None),
        ("theta-sawtooth-5hz", None, "none", (450.0, 5.0, 75.0, "sawtooth", None), None, None),
        # Lines below 0 Hz, listed at their absolute value; with a cycle, intervals that cross 0.
        ("theta-100hz-smoothed-on-off-100pct", None, "none",
         (100.0, 6.0, 100.0, "smoothed_on_off", None), None, None),
        ("theta-100hz-smoothed-on-off-cycle-100pct", None, "none",
         (100.0, 5.0, 100.0, "smoothed_on_off", (1.0, 60.0, 0.0)), None, None),
        # A swell whose outer lines are under the threshold.
        ("swell-10pct", None, "none", _SINE_THETA, (250.0, 40.0, 10.0, "smooth_swell", 0.0, None), None),
        # Both cycles, 60 degrees apart: the square-root half width.
        ("swell-cycles-60deg-apart", None, "none", _SINE_THETA_CYCLE,
         (250.0, 45.0, 100.0, "smooth_swell", 0.0, (15.0, 60.0, 60.0)), None),
        ("bursts-cycles-60deg-apart", None, "none", _SINE_THETA_CYCLE,
         (250.0, 45.0, 100.0, "bursts", 0.0, (15.0, 60.0, 60.0)), None),
        # Summed lines with a coupling phase that turns the gate phase.
        ("bursts-60hz-135deg", None, "none", _SINE_THETA, (250.0, 60.0, 100.0, "bursts", 135.0, None), None),
        ("bursts-45hz-45deg", None, "none", _SINE_THETA, (250.0, 45.0, 100.0, "bursts", 45.0, None), None),
        # Whole by the binary64 test, though 10 times the binary64 5.7 is not exactly 57.
        ("bursts-57hz-theta-5.7hz", None, "none", (450.0, 5.7, 75.0, "sine", None),
         (250.0, 57.0, 100.0, "bursts", 0.0, None), None),
        # Cycles of swing 0 count as no cycle: summed as bursts-60hz is.
        ("bursts-60hz-zero-swing", None, "none", (450.0, 6.0, 75.0, "sine", (0.0, 60.0, 0.0)),
         (250.0, 60.0, 100.0, "bursts", 0.0, (0.0, 60.0, 90.0)), None),
        # All three layers, the binaural beat rate on the Sleep cycle.
        ("three-layers", None, "none", _SINE_THETA, (250.0, 40.0, 100.0, "smooth_swell", 0.0, None),
         (100.0, 1.5, SLEEP_CYCLE)),
    ]
    names = [c[0] for c in out]
    assert len(set(names)) == len(names), names
    return out


# The hash probe's `components` source, in this order.
COMPONENT_PROBE_CASES = ("theta-smoothed-on-off-1hz", "theta-sawtooth-6hz", "bursts-45hz", "bursts-60hz",
                         "gamma-cycle-swell-theta-cycle", "binaural-cycle-sleep")


@functools.lru_cache(maxsize=None)
def _component_tables():
    return tuple((case, fixture, mute, theta, gamma, binaural,
                  tuple(component_table(theta, gamma, binaural, mute)))
                 for case, fixture, mute, theta, gamma, binaural in component_cases())


def component_case_rows():
    rows = []
    for case, fixture, mute, theta, gamma, binaural, table in _component_tables():
        t, g, b = component_layer_objects(theta, gamma, binaural)
        rows.append({
            "case": case, "fixture": "none" if fixture is None else fixture, "mute": mute,
            "theta_reference": "none" if t is None else _json_text(t),
            "gamma_pac": "none" if g is None else _json_text(g),
            "binaural": "none" if b is None else _json_text(b),
            "recipe": component_recipe_text(case, theta, gamma, binaural),
            "components": sum(2 if r["ear"] == "both" else 1 for r in table),
        })
    assert set(COMPONENT_PROBE_CASES) <= {r["case"] for r in rows}
    return rows


def component_rows():
    rows = []
    for case, _, _, _, _, _, table in _component_tables():
        for r in table:
            rows.append({
                "case": case, "ear": r["ear"], "layer": r["layer"],
                "gamma_mult": r["gamma_mult"], "theta_mult": r["theta_mult"], "beat_mult": r["beat_mult"],
                "center": format_trimmed(r["center"]), "low": format_trimmed(r["low"]),
                "high": format_trimmed(r["high"]), "level": format_trimmed(r["level"]),
            })
    return rows


COMPONENT_COEFFICIENT_RATES_HZ = (1.0, 5.0, 6.0)
COMPONENT_COEFFICIENT_K = (0, 1, 2, 3, 7, 10, 20, 40)


def component_coefficient_rows():
    """P(k, w), the coefficient, and its bound B(k) per form, theta rate, and k.
    The coefficient is signed for the smoothed on-off envelope and the burst
    gate, and a magnitude for the sawtooth (the reverse saw has the same)."""
    rows = []
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        for form in ("smoothed_on_off", "sawtooth", "burst_gate"):
            for rate in COMPONENT_COEFFICIENT_RATES_HZ:
                if form == "burst_gate":
                    h = (BURST_WIDTH_MS / 1000.0 / 2) * rate
                    w = (BURST_EDGE_MS / 1000.0) * rate
                else:
                    h = float(THETA_HALF_ON_SHARE)
                    w = theta_edge_s() * rate
                for k in COMPONENT_COEFFICIENT_K:
                    if form == "sawtooth":
                        c = sawtooth_coefficient(k, w)
                        b = sawtooth_bound(k, w) if k else None
                    else:
                        c = on_off_coefficient(k, h, w)
                        b = on_off_bound(k, w) if k else None
                    assert b is None or abs(c) <= b, (form, rate, k)
                    rows.append({
                        "form": form, "rate_hex": hexf(rate),
                        "h_hex": "none" if form == "sawtooth" else hexf(h), "w_hex": hexf(w), "k": k,
                        "p": "none" if k == 0 else format_trimmed(edge_factor(k, w)),
                        "c": format_trimmed(c), "bound": "none" if b is None else format_trimmed(b),
                    })
    return rows


def component_constants():
    t = component_threshold()
    return {
        "level_db": dec(COMPONENT_LEVEL_DB),
        "threshold": format_trimmed(t),
        "threshold_hex": hexf(binary64(Fraction(t))),
        "level_error": dec(COMPONENT_LEVEL_ERROR),
        "frequency_error": dec(COMPONENT_FREQUENCY_ERROR),
        "layers": list(COMPONENT_LAYERS),
        "ears": ["left", "right"],
        "no_model_rule": COMPONENT_NO_MODEL_RULE,
        "case_length_s": dec(COMPONENT_CASE_LENGTH_S),
        "probe_cases": list(COMPONENT_PROBE_CASES),
    }


# --------------------------------------------------------------- spacing
#
# Story 3.2: the spacing rule on the component table (docs/signal-spec.md,
# Spacing). Every pair of rows of different layers in one ear; the distance
# of two lines is c + H sin(theta + psi) over the one shared rate cycle, so
# the minimum over a whole cycle is max(0, |c| - H) in closed form. Ideal
# values in 70-digit decimal arithmetic; the first time of the minimum by
# exact bisection on the cycle fraction (100 halvings), never by sampling.

SPACING_RULE_HZ = 50.0               # row spacing-rule
SPACING_TIME_ERROR_S = 0.001         # row spacing-time-error
SPACING_RULE = "spacing_rule"
SPACING_LIMIT = ">= 50 Hz (row spacing-rule)"
SPACING_WHOLE_SESSION = "whole session"
SPACING_LISTED_INTERVALS = "listed intervals, a row mirrored below 0 Hz"
SPACING_CARRIER_FIELDS = {"gamma_pac": "/gamma_pac/carrier_hz", "binaural": "/binaural/carrier_left_hz"}
SPACING_BISECTIONS = 100
EARS = ("left", "right")


def _cos_units_exact(units):
    """cos(2 pi units / 2^64) as a Decimal, exact at the quarter points."""
    units %= CYCLE
    if units % QUARTER == 0:
        return Decimal((1, 0, -1, 0)[units // QUARTER])
    return _cos_units(units)


def _sin_units_exact(units):
    """sin(2 pi units / 2^64) as a Decimal, exact at the quarter points."""
    return _cos_units_exact(units - QUARTER)


def _cos_cycles(x):
    """cos(2 pi x) for a Fraction x of cycles, as a Decimal."""
    return decimal_sin_cycles(Fraction(x) + Fraction(1, 4))


def acos_cycles(v):
    """The x in [0, 1/2] cycles with cos(2 pi x) = v (v in [-1, 1]), by exact
    bisection on x: the smallest x where the cosine is at or below v, within 2^-100."""
    if v >= 1:
        return Fraction(0)
    if v <= -1:
        return Fraction(1, 2)
    lo, hi = Fraction(0), Fraction(1, 2)
    for _ in range(SPACING_BISECTIONS):
        mid = (lo + hi) / 2
        if _cos_cycles(mid) <= v:
            hi = mid
        else:
            lo = mid
    return hi


def _spacing_cycles(theta, gamma, binaural):
    """{rate: (center, swing, P0 units, period)} for the gamma, theta, and beat
    rates (None where the layer is absent). A rate without a cycle has swing 0."""
    out = {"gamma": None, "theta": None, "beat": None}

    def one(center, cycle):
        if has_cycle(cycle):
            return (_frac_decimal(center), _frac_decimal(cycle[0]), coupling_phase_units(cycle[2])[0],
                    _frac_decimal(cycle[1]))
        return (_frac_decimal(center), Decimal(0), 0, None)

    if theta is not None:
        out["theta"] = one(theta[1], theta[4])
    if gamma is not None:
        out["gamma"] = one(gamma[1], gamma[5])
    if binaural is not None:
        out["beat"] = one(binaural[1], binaural[2])
    return out


def _sweeps(row, cycles):
    """A row sweeps when it has a nonzero multiplier on a rate with a cycle."""
    for key, rate in (("gamma_mult", "gamma"), ("theta_mult", "theta"), ("beat_mult", "beat")):
        if row[key] != 0 and cycles[rate] is not None and cycles[rate][1] > 0:
            return True
    return False


def spacing_pair(r1, r2, cycles):
    """The closed-form minimum distance of two rows over a whole rate cycle
    (docs/signal-spec.md, Spacing), and where it first occurs. r1 is the
    earlier row in table order. Returns a dict of Decimals and Fractions."""
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        sweeps = _sweeps(r1, cycles) or _sweeps(r2, cycles)
        out = {"sweeps": sweeps, "mirrored": r1["mirrored"] or r2["mirrored"]}
        if out["mirrored"]:
            out["distance"] = max(Decimal(0), r2["low"] - r1["high"], r1["low"] - r2["high"])
            out["where"] = "whole" if not sweeps else "intervals"
            return out
        c = r1["center"] - r2["center"]
        terms = []
        for key, rate in (("gamma_mult", "gamma"), ("theta_mult", "theta"), ("beat_mult", "beat")):
            d = r1[key] - r2[key]
            cyc = cycles[rate]
            if d != 0 and cyc is not None and cyc[1] > 0:
                terms.append((d * cyc[1], cyc[2]))
        big_a = sum((amp * _cos_units_exact(p0) for amp, p0 in terms), Decimal(0))
        big_b = sum((amp * _sin_units_exact(p0) for amp, p0 in terms), Decimal(0))
        h = (big_a * big_a + big_b * big_b).sqrt()
        out.update({"c": c, "A": big_a, "B": big_b, "H": h, "distance": max(Decimal(0), abs(c) - h)})
        if not sweeps:
            out["where"] = "whole"
            return out
        if h == 0:
            x = Fraction(0)
        else:
            sigma = 1 if c >= 0 else -1
            alpha = acos_cycles(-sigma * big_b / h)
            m = alpha if -sigma * big_a >= 0 else (1 - alpha) % 1
            if abs(c) >= h:
                x = m
            else:
                beta = acos_cycles(abs(c) / h)
                roots = ((m - beta) % 1, (m + beta) % 1)
                # No vector root lies within 10 ms of the cycle start, where the
                # first of the two roots is not well conditioned.
                assert all(min(r, 1 - r) > Fraction(1, 6000) for r in roots), roots
                x = min(roots)
        out["where"] = "time"
        out["x"] = x
        period = next(cyc[3] for cyc in cycles.values() if cyc is not None and cyc[3] is not None)
        out["time"] = _frac_decimal(x) * period
        rates = {}
        for rate, cyc in cycles.items():
            if cyc is None:
                rates[rate] = None
            elif cyc[1] == 0:
                rates[rate] = cyc[0]
            else:
                rates[rate] = cyc[0] + cyc[1] * decimal_sin_cycles(x + Fraction(cyc[2], CYCLE))
        out["rates"] = rates
        return out


def _ear_rows(table):
    """The left and right ear tables, each in table order, with global indices
    (the left ear's rows first)."""
    left = [r for r in table if r["ear"] in ("both", "left")]
    right = [r for r in table if r["ear"] in ("both", "right")]
    return {"left": list(enumerate(left)), "right": [(len(left) + k, r) for k, r in enumerate(right)]}


def spacing_result(theta, gamma, binaural, mute="none"):
    """Per ear the pair count and the worst pair, and the reported failure
    (docs/signal-spec.md, Spacing). Each pair is (distance, index_1, index_2,
    row_1, row_2, pair dict)."""
    table = component_table(theta, gamma, binaural, mute)
    cycles = _spacing_cycles(theta, gamma, binaural)
    limit = exact_decimal(SPACING_RULE_HZ)
    ears, failing = {}, []
    for e, ear in enumerate(EARS):
        rows = _ear_rows(table)[ear]
        pairs = []
        for a in range(len(rows)):
            for b in range(a + 1, len(rows)):
                (i1, r1), (i2, r2) = rows[a], rows[b]
                if r1["layer"] == r2["layer"]:
                    continue
                pairs.append((spacing_pair(r1, r2, cycles), i1, i2, r1, r2))
        worst = min(pairs, key=lambda p: (p[0]["distance"], p[1], p[2])) if pairs else None
        ears[ear] = {"pairs": len(pairs), "worst": worst, "all": pairs}
        failing += [(p[0]["distance"], e, p[1], p[2], ear, p) for p in pairs if p[0]["distance"] < limit]
    failure = min(failing, key=lambda f: f[:4])[4:] if failing else None
    return {"table": table, "cycles": cycles, "ears": ears, "failure": failure}


def _mults(row):
    return f"({row['gamma_mult']}, {row['theta_mult']}, {row['beat_mult']})"


def spacing_where_text(pair):
    """The where part of the detail, ideal values at 25 digits."""
    if pair["where"] == "whole":
        return SPACING_WHOLE_SESSION
    if pair["where"] == "intervals":
        return SPACING_LISTED_INTERVALS
    parts = [f"first at {format_trimmed(pair['time'])} s"]
    for rate in ("gamma", "theta", "beat"):
        v = pair["rates"][rate]
        parts.append(f"{rate} rate " + ("none" if v is None else f"{format_trimmed(v)} Hz"))
    return ", ".join(parts)


def spacing_detail(ear, r1, r2, pair):
    return (f"{ear} ear: {r1['layer']} {_mults(r1)} at {format_trimmed(r1['center'])} Hz and "
            f"{r2['layer']} {_mults(r2)} at {format_trimmed(r2['center'])} Hz; {spacing_where_text(pair)}")


SPACING_CASE_LENGTH_S = 10.0
STARTER_LOOP_OPENING_S = 60.0
STARTER_LOOP_BODY_S = 120.0
AD5_THETA = (450.0, 6.0, 75.0, "sine", None)
AD5_BINAURAL = (
    ("no-binaural", None),
    ("beat-0", (100.0, 0.0, None)),
    ("beat-4", (100.0, 4.0, None)),
    ("beat-10", (100.0, 10.0, None)),
    ("cycle-0deg", (100.0, 1.5, (1.5, 60.0, 0.0))),
    ("cycle-90deg", (100.0, 1.5, (1.5, 60.0, 90.0))),
    ("cycle-270deg", (100.0, 1.5, (1.5, 60.0, 270.0))),
)

# (fixture, rationale, length_s, loop or None, theta, gamma, binaural): the
# four starter layer configurations (starter-recipes.md; design log (m), (n))
# and the must-fail fixture. No ramps or fades (Epic 4); not the Epic 6
# starter recipes.
SPACING_FIXTURES = (
    ("starter-focus-layers.json",
     "Starter layer configuration (Story 3.2): Focus, from starter-recipes.md and design log 2026-10-27 (m). "
     "Theta reference: a 450 Hz carrier amplitude-modulated by the sine envelope at 6 Hz, 75 percent AM depth. "
     "Gamma PAC layer: a 250 Hz sine carrier amplitude-modulated at 40 Hz, its AM depth opening to 100 percent "
     "for 50 ms bursts centered on the 0 degree coupling phase. No binaural layer. Loops at the 45 min cap, "
     "opening 60 s, body 120 s. No ramps or fades (Epic 4). Not the Epic 6 starter recipe.",
     2700.0, ("focus", 60.0, 120.0, 45.0), (450.0, 6.0, 75.0, "sine", None),
     (250.0, 40.0, 100.0, "bursts", 0.0, None), None),
    ("starter-learn-layers.json",
     "Starter layer configuration (Story 3.2): Learn, from starter-recipes.md and design log 2026-10-27 (m). "
     "Theta reference: a 450 Hz carrier amplitude-modulated by the sine envelope at 5.5 Hz, 75 percent AM depth. "
     "Gamma PAC layer: a 250 Hz sine carrier amplitude-modulated at 40 Hz, its AM depth swelling to 100 percent "
     "at the 0 degree coupling phase (smooth swell). No binaural layer. Loops at the 20 min cap, opening 60 s, "
     "body 120 s. No ramps or fades (Epic 4). Not the Epic 6 starter recipe.",
     1200.0, ("learn", 60.0, 120.0, 20.0), (450.0, 5.5, 75.0, "sine", None),
     (250.0, 40.0, 100.0, "smooth_swell", 0.0, None), None),
    ("starter-relax-layers.json",
     "Starter layer configuration (Story 3.2): Relax, from starter-recipes.md and design log 2026-10-27 (m). "
     "Theta reference: a 450 Hz carrier amplitude-modulated by the sine envelope at 6 Hz, 75 percent AM depth. "
     "Gamma PAC layer: a 250 Hz sine carrier amplitude-modulated at 40 Hz, its AM depth swelling to 25 percent "
     "at the 0 degree coupling phase (smooth swell). No binaural layer. 30 min, no loop. No level ramps or "
     "fades (Epic 4). Not the Epic 6 starter recipe.",
     1800.0, None, (450.0, 6.0, 75.0, "sine", None),
     (250.0, 40.0, 25.0, "smooth_swell", 0.0, None), None),
    ("starter-sleep-layers.json",
     "Starter layer configuration (Story 3.2): Sleep, from starter-recipes.md and design log 2026-10-27 (m), (n). "
     "Theta reference: a 450 Hz carrier amplitude-modulated by the sine envelope at a steady 2 Hz, 75 percent "
     "AM depth. Binaural layer: a 100 Hz pure sine in the left ear and a pure sine in the right ear whose "
     "binaural beat rate cycles sinusoidally over 0 to 3 Hz every 60 s, starting at 0 Hz and rising. No gamma "
     "PAC layer. 45 min, no loop. No fade (Epic 4). Not the Epic 6 starter recipe.",
     2700.0, None, (450.0, 2.0, 75.0, "sine", None), None, (100.0, 1.5, SLEEP_CYCLE)),
    ("spacing-binaural-250-256-gamma-260.json",
     "Spacing must-fail fixture (Story 3.2): a binaural layer of two pure sines, 250 Hz in the left ear and "
     "256 Hz in the right ear, beside a gamma PAC layer: a 300 Hz sine carrier amplitude-modulated at 40 Hz, "
     "uncoupled, 100 percent AM depth, whose lower side frequency sits at 260 Hz, 4 Hz from the right "
     "binaural carrier. Rejected at compile by the spacing rule in the right ear. A test fixture, not for "
     "listening.",
     SPACING_CASE_LENGTH_S, None, None, (300.0, 40.0, 100.0, "uncoupled", None, None), (250.0, 6.0, None)),
)


def spacing_recipe(rationale, length, loop, theta, gamma, binaural, date="2026-11-16"):
    """A schema-valid recipe dict (numbers as binary64) with the given layers."""
    recipe = {"schema_version": "1.0", "engine_version": "0.0.1", "seed": 42,
              "author": "Arcani test fixtures", "date": date, "rationale": rationale,
              "length_s": length, "loudness_target_lufs": -36.0}
    t, g, b = component_layer_objects(theta, gamma, binaural)
    if t is not None:
        recipe["theta_reference"] = t
    if g is not None:
        recipe["gamma_pac"] = g
    if b is not None:
        recipe["binaural"] = b
    if loop is not None:
        mode, opening, body, cap = loop
        recipe["loop"] = {"mode": mode, "opening_s": opening, "body_s": body, "max_run_time_min": cap}
    return recipe


def _plain_numbers(value):
    """The recipe with every integral binary64 written as an integer, as the fixture files are."""
    if isinstance(value, dict):
        return {k: _plain_numbers(v) for k, v in value.items()}
    if isinstance(value, float) and value == int(value) and abs(value) < 2**53:
        return int(value)
    return value


def spacing_fixture_text(fixture):
    """The text of one Story 3.2 fixture file in recipes/fixtures/valid/."""
    for name, rationale, length, loop, theta, gamma, binaural in SPACING_FIXTURES:
        if name == fixture:
            recipe = spacing_recipe(rationale, length, loop, theta, gamma, binaural)
            return json.dumps(_plain_numbers(recipe), indent=2, ensure_ascii=False) + "\n"
    raise KeyError(fixture)


def spacing_cases():
    """(case, fixture or None, mute, theta, gamma, binaural, recipe text): every
    component case, the Story 3.2 fixtures, the AD-5 sweep recipes, then cases
    no fixture has."""
    cases = []
    for case, fixture, mute, theta, gamma, binaural in component_cases():
        cases.append((case, fixture, mute, theta, gamma, binaural,
                      component_recipe_text(case, theta, gamma, binaural)))
    for name, rationale, length, loop, theta, gamma, binaural in SPACING_FIXTURES:
        cases.append((name[:-len(".json")], name, "none", theta, gamma, binaural,
                      _json_text(spacing_recipe(rationale, length, loop, theta, gamma, binaural))))
    for coupling in ("smooth_swell", "bursts"):
        gamma = (250.0, 40.0, 100.0, coupling, 0.0, None)
        for setting, binaural in AD5_BINAURAL:
            name = f"ad5-{'swell' if coupling == 'smooth_swell' else 'bursts'}-{setting}"
            cases.append((name, None, "none", AD5_THETA, gamma, binaural,
                          _json_text(spacing_recipe(f"Spacing vector case {name} (Story 3.2): the AD-5 sweep "
                                                    "recipe of tests/python/test_binaural_ad5.py. A test recipe, "
                                                    "not for listening.", SPACING_CASE_LENGTH_S, None,
                                                    AD5_THETA, gamma, binaural))))
    extra = (
        # Exactly 50 Hz passes with margin 0; 49.99 Hz fails.
        ("spacing-exactly-50hz", (450.0, 6.0, 0.0, "sine", None), None, (400.0, 0.0, None)),
        ("spacing-49.99hz", (450.0, 6.0, 0.0, "sine", None), None, (400.01, 0.0, None)),
        # A beat rate cycle that comes within 50 Hz only at its turning point (beat rate 3 Hz at 30 s).
        ("spacing-turning-point", (154.5, 2.0, 75.0, "sine", None), None, (100.0, 1.5, SLEEP_CYCLE)),
        # A gamma rate cycle that crosses the left binaural carrier: distance 0, first at gamma rate 50 Hz.
        ("spacing-gamma-cycle-crossing", None, (250.0, 45.0, 100.0, "uncoupled", None, (15.0, 60.0, 0.0)),
         (200.0, 6.0, None)),
        # Lines that sweep together: theta (0, 1) and gamma (-1, 0) move as one (H = 0); their intervals
        # are 46.5 Hz apart, their distance is 51.5 Hz at every moment.
        ("spacing-sweep-together", (200.0, 3.5, 75.0, "sine", (2.5, 60.0, 0.0)),
         (300.0, 45.0, 100.0, "uncoupled", None, (2.5, 60.0, 180.0)), None),
        # Sweeping together in part: both cycles 60 degrees apart (the three-term law).
        ("spacing-cycles-60deg-apart", (330.0, 4.0, 75.0, "sine", (2.0, 60.0, 0.0)),
         (250.0, 45.0, 100.0, "smooth_swell", 0.0, (15.0, 60.0, 60.0)), None),
        # All three cycles at once: the swell row (-1, -1) against the right binaural carrier.
        ("spacing-three-cycles", (450.0, 4.0, 75.0, "sine", (2.0, 60.0, 0.0)),
         (250.0, 45.0, 100.0, "smooth_swell", 0.0, (15.0, 60.0, 30.0)), (150.0, 1.5, SLEEP_CYCLE)),
        # A theta row listed mirrored from below 0 Hz (its interval crosses 0 along the theta
        # cycle), against a 1 Hz binaural carrier: compared as listed intervals.
        ("spacing-mirrored-row", (100.0, 5.0, 100.0, "smoothed_on_off", (1.0, 60.0, 0.0)), None,
         (1.0, 0.0, None)),
        # One layer: no pair.
        ("spacing-one-layer", (450.0, 6.0, 75.0, "sine", None), None, None),
    )
    for name, theta, gamma, binaural in extra:
        cases.append((name, None, "none", theta, gamma, binaural,
                      _json_text(spacing_recipe(f"Spacing vector case {name} (Story 3.2). A test recipe, not "
                                                "for listening.", SPACING_CASE_LENGTH_S, None, theta, gamma,
                                                binaural))))
    names = [c[0] for c in cases]
    assert len(set(names)) == len(names), names
    return cases


@functools.lru_cache(maxsize=None)
def _spacing_results():
    return tuple((case, fixture, mute, theta, gamma, binaural, text,
                  spacing_result(theta, gamma, binaural, mute))
                 for case, fixture, mute, theta, gamma, binaural, text in spacing_cases())


def _decimal_text(x):
    return format_trimmed(x)


def spacing_case_rows():
    rows = []
    for case, fixture, mute, theta, gamma, binaural, text, res in _spacing_results():
        t, g, b = component_layer_objects(theta, gamma, binaural)
        row = {
            "case": case, "fixture": "none" if fixture is None else fixture, "mute": mute,
            "theta_reference": "none" if t is None else _json_text(t),
            "gamma_pac": "none" if g is None else _json_text(g),
            "binaural": "none" if b is None else _json_text(b),
            "recipe": text,
            "components": sum(2 if r["ear"] == "both" else 1 for r in res["table"]),
        }
        if res["failure"] is None:
            row.update({"result": "pass", "parameter": "none", "value": "none", "rule": "none",
                        "limit": "none", "detail": "none"})
        else:
            ear, (pair, i1, i2, r1, r2) = res["failure"]
            row.update({"result": "rejected", "parameter": SPACING_CARRIER_FIELDS[r2["layer"]],
                        "value": _decimal_text(pair["distance"]), "rule": SPACING_RULE,
                        "limit": SPACING_LIMIT, "detail": spacing_detail(ear, r1, r2, pair)})
        rows.append(row)
    return rows


def acos_units_engine(v):
    """Spec engine step: the smallest integer x in [0, 2^63] with
    cycle_cosine(x) <= v, by integer bisection."""
    if cycle_cosine(0) <= v:
        return 0
    lo, hi = 0, HALF
    while hi - lo > 1:
        mid = lo + (hi - lo) // 2
        if cycle_cosine(mid) <= v:
            hi = mid
        else:
            lo = mid
    return hi


def engine_spacing_pair(r1, r2, theta, gamma, binaural, timed):
    """The spec's binary64 steps for one pair (Spacing, Engine): the minimum
    distance and, when timed and a row sweeps, the first time in seconds.
    Used here only to check that the steps meet the error rows on every vector."""
    def one(center, cycle):
        if has_cycle(cycle):
            p0 = coupling_phase_units(cycle[2])[0]
            return center, cycle[0], p0, cycle_cosine(p0), cycle_cosine((p0 - QUARTER) % CYCLE), cycle[1]
        return center, 0.0, 0, 0.0, 0.0, None

    cyc = {"gamma": None if gamma is None else one(gamma[1], gamma[5]),
           "theta": None if theta is None else one(theta[1], theta[4]),
           "beat": None if binaural is None else one(binaural[1], binaural[2])}
    keys = (("gamma_mult", "gamma"), ("theta_mult", "theta"), ("beat_mult", "beat"))
    if r1["mirrored"] or r2["mirrored"]:
        lo1, hi1, lo2, hi2 = (float(r1["low"]), float(r1["high"]), float(r2["low"]), float(r2["high"]))
        return max(0.0, lo2 - hi1, lo1 - hi2), None
    terms = []
    for key, rate in keys:
        v = cyc[rate]
        swing, cos_p, sin_p = (0.0, 0.0, 0.0) if v is None else (v[1], v[3], v[4])
        terms.append((float(r1[key] - r2[key]) * swing, cos_p, sin_p))
    (a, ca, sa), (b, cb, sb), (e, ce, se) = terms
    x = (a * ca + b * cb) + e * ce
    y = (a * sa + b * sb) + e * se
    h = math.sqrt(x * x + y * y)
    c = float(r1["center"]) - float(r2["center"])
    dist = abs(c) - h
    if dist < 0:
        dist = 0.0
    sweeps = any(r[key] != 0 and cyc[rate] is not None and cyc[rate][1] > 0
                 for r in (r1, r2) for key, rate in keys)
    if not timed or not sweeps:
        return dist, None
    if h == 0:
        u = 0
    else:
        sigma = 1.0 if c >= 0 else -1.0
        alpha = acos_units_engine((-sigma * y) / h)
        m = alpha if -sigma * x >= 0 else (CYCLE - alpha) % CYCLE
        if abs(c) >= h:
            u = m
        else:
            beta = acos_units_engine(abs(c) / h)
            u = min((m - beta) % CYCLE, (m + beta) % CYCLE)
    period = next(v[5] for v in cyc.values() if v is not None and v[5] is not None)
    return dist, (float(u) * 2.0**-64) * period


SPACING_ENGINE_TIME_CHECK = Decimal("1e-6")   # s, far inside row spacing-time-error


def _check_engine_spacing():
    """Every vector pair: the spec's binary64 steps are within row
    component-frequency-error of the ideal distance; every worst or failing
    pair's time within SPACING_ENGINE_TIME_CHECK of the ideal, around the cycle."""
    worst = Decimal(0)
    for _, _, _, theta, gamma, binaural, _, res in _spacing_results():
        timed = {(p[1], p[2]) for p in (res["ears"][ear]["worst"] for ear in EARS) if p is not None}
        for ear in EARS:
            for ideal, i1, i2, r1, r2 in res["ears"][ear]["all"]:
                dist, t = engine_spacing_pair(r1, r2, theta, gamma, binaural, (i1, i2) in timed)
                err = abs(Decimal(dist) - ideal["distance"])
                assert err <= Decimal(COMPONENT_FREQUENCY_ERROR), (r1, r2, err)
                worst = max(worst, err)
                if t is not None and ideal["where"] == "time":
                    diff = abs(Decimal(t) - ideal["time"]) % 60
                    assert min(diff, 60 - diff) <= SPACING_ENGINE_TIME_CHECK, (r1, r2, t, ideal["time"])
    return worst


def spacing_margin_rows():
    """Per case and ear: the pair count, and the worst pair with its minimum
    distance, margin, rows, and where it first occurs."""
    _check_engine_spacing()
    rows = []
    limit = exact_decimal(SPACING_RULE_HZ)
    for case, _, _, _, _, _, _, res in _spacing_results():
        for ear in EARS:
            info = res["ears"][ear]
            row = {"case": case, "ear": ear, "pairs": info["pairs"]}
            if info["worst"] is None:
                row.update({"distance": "none", "margin": "none", "index_1": "none", "row_1": "none",
                            "index_2": "none", "row_2": "none", "where": "none"})
            else:
                pair, i1, i2, r1, r2 = info["worst"]
                row.update({
                    "distance": _decimal_text(pair["distance"]),
                    "margin": _decimal_text(pair["distance"] - limit),
                    "index_1": str(i1), "row_1": f"{r1['layer']} {_mults(r1)}",
                    "index_2": str(i2), "row_2": f"{r2['layer']} {_mults(r2)}",
                    "where": spacing_where_text(pair),
                })
            rows.append(row)
    return rows


# (label, c, di, dj, db, (s_M, deg_M), (s_theta, deg_theta), (s_B, deg_B)):
# the closed form on its own, for an engine helper and the reference. A
# swing of 0 is no cycle. Rates are not given here (centers 0), so the pair
# rows carry the first cycle fraction x = t / P instead of the time.
SPACING_PAIR_CASES = (
    ("static", 4.0, 0, 0, 0, (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)),
    ("static negative", -51.5, 0, 0, 0, (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)),
    ("one cycle, turning point", 51.0, 0, 0, -1, (0.0, 0.0), (0.0, 0.0), (1.5, 270.0)),
    ("one cycle, crossing", 5.0, -1, 0, 0, (15.0, 0.0), (0.0, 0.0), (0.0, 0.0)),
    ("one cycle, crossing, c negative", -5.0, -1, 0, 0, (15.0, 0.0), (0.0, 0.0), (0.0, 0.0)),
    ("one cycle, touching", 15.0, 1, 0, 0, (15.0, 0.0), (0.0, 0.0), (0.0, 0.0)),
    ("one cycle, c zero", 0.0, 1, 0, 0, (15.0, 90.0), (0.0, 0.0), (0.0, 0.0)),
    ("sweep together", -51.5, 1, 1, 0, (2.5, 180.0), (2.5, 0.0), (0.0, 0.0)),
    ("two cycles, 60 degrees apart", 60.0, -1, 2, 0, (15.0, 60.0), (2.0, 0.0), (0.0, 0.0)),
    ("three cycles", 52.5, 1, -2, 1, (15.0, 90.0), (2.0, 0.0), (1.5, 270.0)),
    ("three cycles, crossing", 7.25, 1, -3, -1, (15.0, 45.0), (2.5, 300.0), (1.5, 10.0)),
    ("multiplier on a rate without a cycle", 55.0, 1, 0, 0, (0.0, 0.0), (2.0, 0.0), (0.0, 0.0)),
)


def spacing_pair_rows():
    rows = []
    with localcontext() as ctx:
        ctx.prec = PREC + 10
        for label, c, di, dj, db, gm, th, bt in SPACING_PAIR_CASES:
            cycles = {"gamma": (Decimal(0), _frac_decimal(gm[0]), coupling_phase_units(gm[1])[0],
                                Decimal(60) if gm[0] > 0 else None),
                      "theta": (Decimal(0), _frac_decimal(th[0]), coupling_phase_units(th[1])[0],
                                Decimal(60) if th[0] > 0 else None),
                      "beat": (Decimal(0), _frac_decimal(bt[0]), coupling_phase_units(bt[1])[0],
                               Decimal(60) if bt[0] > 0 else None)}
            r1 = {"gamma_mult": di, "theta_mult": dj, "beat_mult": db, "center": _frac_decimal(c),
                  "mirrored": False}
            r2 = {"gamma_mult": 0, "theta_mult": 0, "beat_mult": 0, "center": Decimal(0), "mirrored": False}
            p = spacing_pair(r1, r2, cycles)
            rows.append({
                "label": label, "c_hex": hexf(c), "di": di, "dj": dj, "db": db,
                "swing_gamma_hex": hexf(gm[0]), "start_gamma_hex": hexf(gm[1]),
                "swing_theta_hex": hexf(th[0]), "start_theta_hex": hexf(th[1]),
                "swing_beat_hex": hexf(bt[0]), "start_beat_hex": hexf(bt[1]),
                "x": _decimal_text(p["A"]), "y": _decimal_text(p["B"]), "h": _decimal_text(p["H"]),
                "distance": _decimal_text(p["distance"]),
                "first": "none" if p["where"] != "time" else _decimal_text(_frac_decimal(p["x"])),
            })
    return rows


def spacing_constants():
    return {
        "rule_hz": dec(SPACING_RULE_HZ),
        "time_error_s": dec(SPACING_TIME_ERROR_S),
        "rule": SPACING_RULE,
        "limit": SPACING_LIMIT,
        "whole_session": SPACING_WHOLE_SESSION,
        "listed_intervals": SPACING_LISTED_INTERVALS,
        "carrier_fields": dict(SPACING_CARRIER_FIELDS),
        "fixtures": [f[0] for f in SPACING_FIXTURES],
        "must_fail_fixture": "spacing-binaural-250-256-gamma-260.json",
        "starter_fixtures": [f[0] for f in SPACING_FIXTURES if f[0].startswith("starter-")],
    }


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
        "spec": "docs/signal-spec.md (sections core, sine, internal block size, stub chain, theta reference, gamma PAC layer, coupling, bursts, binaural layer, rate curve (the beat rate, Story 2.5; the theta and gamma rates, Story 2.6), loop (Story 2.7), components (Story 3.1), spacing (Story 3.2), and 24-bit rounding)",
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
        "burst_constants": {
            "couplings": list(GAMMA_COUPLINGS_2_4),
            "coupled": list(COUPLED_2_4),
            "width_ms": dec(BURST_WIDTH_MS),
            "edge_ms": dec(BURST_EDGE_MS),
            "burst_length_s": dec(BURST_LENGTH_S),
        },
        "burst_edges": burst_edge_rows(),
        "burst_gates": burst_gate_rows(),
        "burst_amplitudes": burst_amplitude_rows(),
        "burst_samples": burst_sample_rows(),
        "binaural_constants": {
            "waveforms": list(BINAURAL_WAVEFORMS),
            "modeled_waveforms": list(BINAURAL_MODELED_WAVEFORMS),
            "inv_two_pi_hex": INV_TWO_PI_HEX,
            "seek_s": dec(SEEK_S),
        },
        "cycle_cosine_coefficients": cycle_cosine_coefficients(),
        "cycle_cosines": cycle_cosine_rows(),
        "cycles_to_units": cycles_to_units_rows(),
        "rate_cycles": rate_cycle_rows(),
        "rate_curve": rate_curve_rows(),
        "binaural_samples": binaural_sample_rows(),
        "rate_curve_constants": {
            "length_s": dec(RATE_CURVE_LENGTH_S),
            "curve_add": dec(CURVE_ADD),
            "probe_fixtures": list(RATE_CURVE_PROBE_FIXTURES),
        },
        "layer_rate_cycles": layer_rate_cycle_rows(),
        "rate_curve_samples": rate_curve_sample_rows(),
        "loop_constants": {
            "modes": list(LOOP_MODES),
            "mode_rows": dict(LOOP_MODE_ROWS),
            "max_run_time_min": {m: dec(v) for m, v in MAX_RUN_TIME_MIN.items()},
            "length_rule": LOOP_LENGTH_RULE,
            "whole_samples_rule": LOOP_WHOLE_SAMPLES_RULE,
            "whole_samples_limit": LOOP_WHOLE_SAMPLES_LIMIT,
            "whole_cycles_rule": LOOP_WHOLE_CYCLES_RULE,
            "exceeds_rule": LOOP_EXCEEDS_RULE,
            "full_render_fixture": LOOP_FULL_RENDER_FIXTURE,
            "window_fixtures": list(LOOP_WINDOW_FIXTURES),
            "window_s": dec(LOOP_WINDOW_S),
            "probe_fixture": LOOP_PROBE_FIXTURE,
            "probe_segment_s": dec(LOOP_PROBE_SEGMENT_S),
            "probe_seam": LOOP_PROBE_SEAM,
        },
        "loop_whole_samples": loop_whole_sample_rows(),
        "loop_compile_cases": loop_compile_rows(),
        "loop_frames": loop_frame_rows(),
        "component_constants": component_constants(),
        "component_coefficients": component_coefficient_rows(),
        "component_cases": component_case_rows(),
        "components": component_rows(),
        "spacing_constants": spacing_constants(),
        "spacing_cases": spacing_case_rows(),
        "spacing_margins": spacing_margin_rows(),
        "spacing_pairs": spacing_pair_rows(),
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
    out.append("| Rate (hex) | Half width seconds (hex) | w = 0.025 * rate (hex) | Hb "
               "| Edge seconds (hex) | w = 0.01 * rate (hex) | Wb | Hb - Wb |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["burst_edges"]:
        out.append(f"| `{r['rate_hex']}` | `{r['half_width_s_hex']}` | `{r['w_half_width_hex']}` "
                   f"| {r['hb_units']} | `{r['edge_s_hex']}` | `{r['w_edge_hex']}` "
                   f"| {r['wb_units']} | {r['plateau_end_units']} |")
    out.append("")
    out.append("| Theta rate (hex) | Coupling phase (hex) | C | Hb | Wb | Theta envelope phase | u "
               "| Segment | g (binary64 bits) | g ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["burst_gates"]:
        out.append(f"| `{r['rate_hex']}` | `{r['deg_hex']}` | {r['c_units']} | {r['hb_units']} "
                   f"| {r['wb_units']} | {r['phase_theta_envelope']} | {r['u']} | {r['region']} "
                   f"| `{r['g_bits']}` | {r['ideal_g']} |")
    out.append("")
    out.append("| Depth (hex) | Theta rate (hex) | Theta envelope phase | Segment | Gamma envelope phase "
               "| g (binary64 bits) | e (binary64 bits) | a (binary64 bits) | g ideal | a ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["burst_amplitudes"]:
        out.append(f"| `{r['depth_hex']}` | `{r['rate_hex']}` | {r['phase_theta_envelope']} "
                   f"| {r['region']} | {r['phase_gamma_envelope']} | `{r['g_bits']}` | `{r['e_bits']}` "
                   f"| `{r['a_bits']}` | {r['ideal_g']} | {r['ideal_a']} |")
    out.append("")
    out.append("| Fixture | fs | Carrier (hex) | Rate (hex) | Depth (hex) | Coupling | Coupling phase (hex) | C "
               "| Theta carrier (hex) | Theta rate (hex) | Theta depth (hex) | Theta shape "
               "| Carrier inc | Rate inc | Theta envelope inc | Hb | Wb | Frames |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- "
               "| --- | --- | --- |")
    seen = set()
    for r in data["burst_samples"]:
        key = (r["fixture"], r["fs"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f"| {r['fixture']} | {r['fs']} | `{r['carrier_hex']}` | `{r['rate_hex']}` "
                   f"| `{r['depth_hex']}` | {r['coupling']} | `{r['deg_hex']}` | {r['c_units']} "
                   f"| `{r['theta_carrier_hex']}` | `{r['theta_rate_hex']}` | `{r['theta_depth_hex']}` "
                   f"| {r['theta_shape']} | {r['inc_carrier']} | {r['inc_rate']} "
                   f"| {r['inc_theta_envelope']} | {r['hb_units']} | {r['wb_units']} | {r['frames']} |")
    out.append("")
    out.append("| Case | Fixture | fs | n | Carrier phase | Envelope phase | Theta envelope phase | Segment "
               "| g (binary64 bits) | e (binary64 bits) | a (binary64 bits) | Gamma (binary64 bits) "
               "| Theta (binary64 bits) | Bus (binary64 bits) | g ideal | Gamma ideal | Bus ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- "
               "| --- | --- |")
    for r in data["burst_samples"]:
        out.append(f"| {r['case']} | {r['fixture']} | {r['fs']} | {r['n']} | {r['phase_carrier']} "
                   f"| {r['phase_rate']} | {r['phase_theta_envelope']} | {r['region']} | `{r['g_bits']}` "
                   f"| `{r['e_bits']}` | `{r['a_bits']}` | `{r['gamma_bits']}` | `{r['theta_bits']}` "
                   f"| `{r['bus_bits']}` | {r['ideal_g']} | {r['ideal_gamma']} | {r['ideal_bus']} |")
    out.append("")
    out.append("| Term | Exact | Binary64 (hex float) |")
    out.append("| --- | --- | --- |")
    for r in data["cycle_cosine_coefficients"]:
        out.append(f"| x^{r['power']} | {r['exact']} | `{r['hex']}` |")
    out.append("")
    out.append("| Cycle cosine case | Phase | Cycle cosine (binary64 bits) | Cosine ideal |")
    out.append("| --- | --- | --- | --- |")
    for r in data["cycle_cosines"]:
        out.append(f"| {r['label']} | {r['phase']} | `{r['bits']}` | {r['ideal']} |")
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
               "| Rate ideal (Hz) | Phase ideal (cycles) |")
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
    out.append("| Fixture | Layer | fs | Center (hex) | Swing (hex) | Period (hex) | Start phase (hex) "
               "| Lowest rate (hex) | Highest rate (hex) | Rate inc | P0 | inc_P | K (hex) "
               "| c0 (binary64 bits) | Frames |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["layer_rate_cycles"]:
        out.append(f"| {r['fixture']} | {r['layer']} | {r['fs']} | `{r['center_hex']}` "
                   f"| `{r['swing_hex']}` | `{r['period_hex']}` | `{r['start_hex']}` "
                   f"| `{r['lowest_hex']}` | `{r['highest_hex']}` | {r['inc_rate']} | {r['p0']} "
                   f"| {r['inc_cycle']} | `{r['k_hex']}` | `{r['c0_bits']}` | {r['frames']} |")
    out.append("")
    out.append("| Case | Fixture | fs | n | Theta cycle phase | Theta U | Theta envelope phase "
               "| Gamma cycle phase | Gamma U | Gamma envelope phase | s or g (binary64 bits) "
               "| Theta (binary64 bits) | Gamma (binary64 bits) | Bus (binary64 bits) "
               "| Theta ideal | Gamma ideal | Bus ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- "
               "| --- | --- |")
    for r in data["rate_curve_samples"]:
        factor = r["factor_bits"] if r["factor_bits"] == "none" else f"`{r['factor_bits']}`"
        out.append(f"| {r['case']} | {r['fixture']} | {r['fs']} | {r['n']} | {r['theta_cycle_phase']} "
                   f"| {r['theta_u']} | {r['phase_theta_envelope']} | {r['gamma_cycle_phase']} "
                   f"| {r['gamma_u']} | {r['phase_gamma_envelope']} | {factor} "
                   f"| `{r['theta_bits']}` | `{r['gamma_bits']}` | `{r['bus_bits']}` "
                   f"| {r['ideal_theta']} | {r['ideal_gamma']} | {r['ideal_bus']} |")
    out.append("")
    out.append("| t_s (hex) | t_s | 4 * t_s (hex) | t_s * 44100 (hex) | Exact at 44100 | n at 44100 "
               "| t_s * 48000 (hex) | Exact at 48000 | n at 48000 | Whole samples |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["loop_whole_samples"]:
        out.append(f"| `{r['t_hex']}` | {r['t']} | `{r['four_t_hex']}` | `{r['product_44100_hex']}` "
                   f"| {r['exact_44100']} | {r['n_44100']} | `{r['product_48000_hex']}` | {r['exact_48000']} "
                   f"| {r['n_48000']} | {r['whole']} |")
    out.append("")
    out.append("| Fixture | Mode | Max run time (min) | length_s | opening_s | body_s | Layers | Result "
               "| Parameter | Value | Rule | Limit |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["loop_compile_cases"]:
        out.append(f"| {r['fixture']} | {r['mode']} | {r['max_run_time_min']} | {r['length_s']} "
                   f"| {r['opening_s']} | {r['body_s']} | {r['layers']} | {r['result']} | {r['parameter']} "
                   f"| {r['value']} | {r['rule']} | {r['limit']} |")
    out.append("")
    out.append("| Fixture | fs | Mode | Max run time (min) | length_s (hex) | opening_s (hex) | body_s (hex) "
               "| Opening end O | Body B | End N | Seams | Seam frames | Last pass frames |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["loop_frames"]:
        out.append(f"| {r['fixture']} | {r['fs']} | {r['mode']} | {r['max_run_time_min']} | `{r['length_hex']}` "
                   f"| `{r['opening_hex']}` | `{r['body_hex']}` | {r['opening_end_frame']} | {r['body_frames']} "
                   f"| {r['end_frame']} | {r['seam_count']} | {', '.join(r['seam_frames'])} "
                   f"| {r['last_pass_frames']} |")
    out.append("")
    out.append("| Form | Theta rate (hex) | h (hex) | w (hex) | k | P(k, w) | Coefficient | Bound B(k) |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["component_coefficients"]:
        h = r["h_hex"] if r["h_hex"] == "none" else f"`{r['h_hex']}`"
        out.append(f"| {r['form']} | `{r['rate_hex']}` | {h} | `{r['w_hex']}` | {r['k']} | {r['p']} "
                   f"| {r['c']} | {r['bound']} |")
    out.append("")
    out.append("| Case | Fixture | Muted ear | theta_reference | gamma_pac | binaural | Components |")
    out.append("| --- | --- | --- | --- | --- | --- | --- |")
    for r in data["component_cases"]:
        layers = [r[key] if r[key] == "none" else f"`{r[key]}`"
                  for key in ("theta_reference", "gamma_pac", "binaural")]
        out.append(f"| {r['case']} | {r['fixture']} | {r['mute']} | {layers[0]} | {layers[1]} | {layers[2]} "
                   f"| {r['components']} |")
    out.append("")
    out.append("| Component case | Ear | Layer | gamma_mult | theta_mult | beat_mult | center_hz | low_hz "
               "| high_hz | level |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["components"]:
        out.append(f"| {r['case']} | {r['ear']} | {r['layer']} | {r['gamma_mult']} | {r['theta_mult']} "
                   f"| {r['beat_mult']} | {r['center']} | {r['low']} | {r['high']} | {r['level']} |")
    out.append("")
    out.append("| Case | Fixture | Muted ear | theta_reference | gamma_pac | binaural | Components | Result "
               "| Parameter | Value | Rule | Limit | Detail |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["spacing_cases"]:
        layers = [r[key] if r[key] == "none" else f"`{r[key]}`"
                  for key in ("theta_reference", "gamma_pac", "binaural")]
        cells = [r[key] if r[key] == "none" else f"`{r[key]}`" for key in ("parameter", "limit")]
        out.append(f"| {r['case']} | {r['fixture']} | {r['mute']} | {layers[0]} | {layers[1]} | {layers[2]} "
                   f"| {r['components']} | {r['result']} | {cells[0]} | {r['value']} | {r['rule']} "
                   f"| {cells[1]} | {r['detail']} |")
    out.append("")
    out.append("| Spacing case | Ear | Pairs | Min distance (Hz) | Margin (Hz) | Row 1 | Index 1 | Row 2 | Index 2 "
               "| Where |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["spacing_margins"]:
        out.append(f"| {r['case']} | {r['ear']} | {r['pairs']} | {r['distance']} | {r['margin']} | {r['row_1']} "
                   f"| {r['index_1']} | {r['row_2']} | {r['index_2']} | {r['where']} |")
    out.append("")
    out.append("| Pair case | c (hex) | di | dj | db | Gamma swing (hex) | Gamma start (hex) | Theta swing (hex) "
               "| Theta start (hex) | Beat swing (hex) | Beat start (hex) | X | Y | H | Min distance "
               "| First cycle fraction |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["spacing_pairs"]:
        out.append(f"| {r['label']} | `{r['c_hex']}` | {r['di']} | {r['dj']} | {r['db']} "
                   f"| `{r['swing_gamma_hex']}` | `{r['start_gamma_hex']}` | `{r['swing_theta_hex']}` "
                   f"| `{r['start_theta_hex']}` | `{r['swing_beat_hex']}` | `{r['start_beat_hex']}` "
                   f"| {r['x']} | {r['y']} | {r['h']} | {r['distance']} | {r['first']} |")
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
