"""Writes the worked test vectors of docs/signal-spec.md: core, sine, internal block size, stub chain, 24-bit rounding.

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
- Stub chain: the spec's stub chain (Story 1.2) for the 1 s binaural
  fixtures, in binary64 in the spec's operation order, from the engine sine
  bits above, written as 64-bit patterns, plus the ideal sine of the same
  phases at 25 digits for the Python reference.
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
    phase %= CYCLE
    # Exact reduction to [-2^62, 2^62] with sin symmetry, so the series argument
    # is at most pi/2 in size.
    s = phase - CYCLE if phase >= CYCLE // 2 else phase
    if s > CYCLE // 4:
        s = CYCLE // 2 - s
    elif s < -(CYCLE // 4):
        s = -(CYCLE // 2) - s
    if s == 0:
        return "0"
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

# (fixture, carrier_left_hz, beat_rate_hz, length_s): the 1 s binaural fixtures
# in recipes/fixtures/valid/. tests/python/test_signal_spec_core.py checks
# that each fixture holds these values.
STUB_CHAIN_FIXTURES = (
    ("stub-chain-1s-beat-0.json", 400.0, 0.0, 1.0),
    ("stub-chain-1s-beat-6.json", 400.0, 6.0, 1.0),
)
STUB_CHAIN_INDICES = (0, 1, 37, 63, 64, 65, 127, 128, 1000)


def block_rows():
    return [{"frame": k, "block": k // BLOCK_FRAMES, "offset": k % BLOCK_FRAMES}
            for k in BLOCK_FRAME_INDICES]


def stub_chain_sample(phase, gain):
    """One channel of the stub chain at the master tap, spec operation order."""
    theta = 0.0
    gamma = 0.0
    bus = theta + gamma
    binaural = gain * engine_sine(phase)
    join = bus + binaural
    master = join * 1.0
    return join, master


def stub_chain_rows():
    rows = []
    for fs in RATES:
        for fixture, left_hz, beat_hz, length_s in STUB_CHAIN_FIXTURES:
            right_hz = left_hz + beat_hz  # one binary64 addition
            inc_l, _ = increment(left_hz, fs)
            inc_r, _ = increment(right_hz, fs)
            frames, _ = samples(length_s, fs)
            for n in STUB_CHAIN_INDICES + (frames - 1, frames, frames + 63):
                past_end = n >= frames
                pl = (n * inc_l) % CYCLE
                pr = (n * inc_r) % CYCLE
                if past_end:
                    left = right = 0.0
                    ideal_l = ideal_r = "0"
                else:
                    jl, left = stub_chain_sample(pl, 1.0)
                    jr, right = stub_chain_sample(pr, 1.0)
                    assert bits(jl) == bits(left) and bits(jr) == bits(right)
                    ideal_l, ideal_r = ideal_sine(pl), ideal_sine(pr)
                rows.append({
                    "case": "past_end" if past_end else "signal",
                    "fixture": fixture, "fs": fs,
                    "carrier_left_hex": hexf(left_hz), "beat_rate_hex": hexf(beat_hz),
                    "carrier_right_hex": hexf(right_hz),
                    "inc_left": str(inc_l), "inc_right": str(inc_r),
                    "frames": str(frames), "n": str(n),
                    "phase_left": str(pl), "phase_right": str(pr),
                    "left_bits": bits(left), "right_bits": bits(right),
                    "ideal_left": ideal_l, "ideal_right": ideal_r,
                })
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
    ("round", "stub chain sample (beat 6, 44.1 kHz, n = 37, left)",
     struct.unpack(">d", bytes.fromhex("3feb7b6766e57522"))[0]),
    ("round", "stub chain sample (beat 6, 48 kHz, n = 63, right)",
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
        "spec": "docs/signal-spec.md (sections core, sine, internal block size, stub chain, and 24-bit rounding)",
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
    out.append("| Fixture | fs | Left carrier (hex) | Beat rate (hex) | Right carrier (hex) "
               "| Left inc | Right inc | Frames |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    seen = set()
    for r in data["stub_chain"]:
        key = (r["fixture"], r["fs"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f"| {r['fixture']} | {r['fs']} | `{r['carrier_left_hex']}` | `{r['beat_rate_hex']}` "
                   f"| `{r['carrier_right_hex']}` | {r['inc_left']} | {r['inc_right']} | {r['frames']} |")
    out.append("")
    out.append("| Case | Fixture | fs | n | Left phase | Right phase | Left (binary64 bits) "
               "| Right (binary64 bits) | Left ideal | Right ideal |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in data["stub_chain"]:
        out.append(f"| {r['case']} | {r['fixture']} | {r['fs']} | {r['n']} | {r['phase_left']} "
                   f"| {r['phase_right']} | `{r['left_bits']}` | `{r['right_bits']}` "
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
