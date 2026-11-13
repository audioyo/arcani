"""Signal spec core, sine, internal blocks, stub chain, and 24-bit rounding: vectors, spec tables, Python ideal, quantization and drift.

Contract with tools/signal_spec_vectors.py (exists, Story 0.2 spec commit):

- `--check` exits 0 when tests/data/signal_spec_vectors.json equals a fresh
  run, 1 otherwise (`--out FILE` selects another file).
- `tables(data)` renders the vector tables of docs/signal-spec.md from the
  JSON data. Every vector table in the spec (each "### Vectors: ..." section
  and the coefficient table) equals one of them.

Contract with reference/ideal.py (numpy and stdlib; loaded by path):

- `phase_increment(f_hz: float, fs: int) -> int` and
  `seconds_to_samples(t_s: float, fs: int) -> int`, exactly per the spec
  (out of domain gives 0).
- `ideal_sine(phase)`: int, or numpy uint64 array; returns float64 (or a
  float64 array) of sin(2*pi*phase/2^64).
- `render_probe_segment(f_hz: float, fs: int, n: int) -> np.ndarray`:
  float64 ideal sine, phase 0 at sample 0, phase[k] = k*inc mod 2^64.
- `probe_sine_component(fs: int) -> np.ndarray`: float64, 1 s each of the
  1 Hz, 450 Hz, and 1000 Hz carriers, unmodulated, in that order, each
  segment from phase 0 (3*fs samples). `PROBE_CARRIERS_HZ == (1.0, 450.0,
  1000.0)`.
- It renders the ideal sine, never the engine polynomial.

Internal block size and stub chain (Story 1.2): `block_frames`, `blocks`,
and `stub_chain` in the vectors file. Each stub chain row names a fixture in
recipes/fixtures/valid/ whose binaural carrier, beat rate, and length equal
the row's; increments and frame counts follow the core rules; each signal
row's bits are within the sine-error bound of its ideal value; past-end rows
are +0.0.

Theta reference oscillator (Story 1.5): each stub chain row also has
`theta_carrier_hex` (`none` when the fixture has no theta_reference field),
`inc_theta`, `phase_theta`, `theta_bits` (the theta tap, the same in both
channels), and `ideal_theta`; `left_bits` and `right_bits` are the output
(theta plus binaural, one rounding) and `ideal_left` and `ideal_right` the
exact sum of the ideal theta and binaural sines. The theta bits are within
the sine-error bound of the ideal theta, and the output bits within twice
the bound plus one rounding (two sines, each within the bound).

Gamma PAC layer, uncoupled (Story 2.2): `gamma_constants`,
`gamma_envelopes`, `gamma_samples`, and `gamma_bus` in the vectors file. The
envelope and amplitude bits follow the AM law from the engine sine, the
sample rows name the gamma fixtures with their values, increments and phases
follow the core rules, the gamma tap bits are within 1.5 * b + 2^-47 of the
ideal and the theta and gamma bus within 3 * b + 2^-45 (b the sine-error
bound), and the bus bits are the binary64 sum of the two taps.

24-bit rounding (Story 1.4): `quantize_24` in the vectors file, one row per
case with `rule`, `label`, `s_hex`, `x_hex`, `value`, and `bytes`. The
generator's `quantize_24(s)` (exact Fraction arithmetic) and an independent
binary64 rule here (Python `round` on a float is exact, ties to even) both
reproduce every value; the bytes are `value` as 3 bytes, little-endian two's
complement. Each naive conversion below (no clamp, no NaN rule, truncation,
ties away from zero) differs from the vectors on at least one row of the rule
it breaks. The rows cover every case of the spec's rounding matrix row.

Quantization and drift are checked exactly with fractions at every range
endpoint, plus an analytic worst-case bound. Bounds and ranges come from
tests/tables/*.tsv through the assertion call `assertions.row`, which records
each row id for the coverage check; no value here is a literal copy of a
table row (the table format and md mapping tests are in test_tables_loader.py).
"""

import importlib.util
import json
import math
import re
import struct
import subprocess
import sys
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from assertions import row as table_row
from assertions.tables import load_tables

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "tools" / "signal_spec_vectors.py"
VECTORS = REPO_ROOT / "tests" / "data" / "signal_spec_vectors.json"
SPEC_DOC = REPO_ROOT / "docs" / "signal-spec.md"
IDEAL = REPO_ROOT / "reference" / "ideal.py"
CYCLE = 2**64

# The ideal sine must agree with the 25-digit decimal vectors to 1e-15
# absolute. binary64 has a unit in the last place of 2.2e-16 at 1.0; a
# reference that reduces the phase exactly in integers and converts once
# lands within a few units of that. 1e-15 is also 9 orders below the
# -120 dBFS (1e-6) engine bound the ideal is the yardstick for, so the ideal
# never hides an engine error.
IDEAL_TOL = 1e-15

# Grid step of the C++ quantization test, used here as the smallest positive
# frequency of a range whose floor is 0 Hz in the analytic drift bound.
GRID_STEP_HZ = Fraction(1, 1000)

HZ_RANGE_IDS = ["theta-rate", "theta-carrier", "gamma-rate", "gamma-carrier",
                "binaural-carrier", "binaural-carrier-right", "beat-rate"]


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(name, path):
    assert path.is_file(), f"missing {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_IDEAL = []


def ideal():
    """reference/ideal.py, loaded once; a missing file fails the calling test."""
    if not _IDEAL:
        _IDEAL.append(load_module("arcani_reference_ideal", IDEAL))
    return _IDEAL[0]


@pytest.fixture(scope="module")
def vectors():
    return load_json(VECTORS)


def fraction_of(text):
    """Exact Fraction of a table number as written (0.01 is 1/100, not its binary64)."""
    return Fraction(text)


def seconds(value, unit):
    factor = {"s": Fraction(1), "ms": Fraction(1, 1000), "h": Fraction(3600)}
    assert unit in factor, f"not a time unit: {unit}"
    return fraction_of(value) * factor[unit]


def accuracy_hz():
    row = table_row("frequency-accuracy")
    assert row.unit == "Hz", row
    return fraction_of(row.value_text)


def drift_bound_s():
    row = table_row("drift-8h")
    return seconds(row.value_text, row.unit)


def session_s():
    row = table_row("session-length")
    return seconds(row.max_text, row.unit)


def sine_bound_dbfs():
    row = table_row("sine-error")
    assert row.unit == "dBFS", row
    return row.value


def sample_rates():
    row = table_row("sample-rates")
    assert row.unit == "Hz", row
    return [int(v) for v in row.values]


def hz_ranges():
    """Every locked-range row in Hz, each read through the assertion call."""
    return [table_row(r.id) for r in listed_hz_ranges()]


# Parameter lists are built at collection from the loader without recording a
# use, so a skipped or deselected test never counts its rows as used; the
# test bodies read their rows through the assertion call when they run.
def listed_hz_ranges():
    return [r for r in load_tables().values() if r.kind == "ranges" and r.unit == "Hz"]


def listed_sample_rates():
    return [int(v) for v in load_tables()["sample-rates"].values]


def record_rows(*row_ids):
    """Reads each row through the assertion call; the sample rates row always."""
    for row_id in row_ids:
        table_row(row_id)
    sample_rates()


def spec_increment(f_hz, fs):
    """The spec increment rule in exact arithmetic (f_hz is a binary64 float)."""
    if not (f_hz >= 0.0 and f_hz < fs / 2):
        return 0
    if f_hz == 0.0:
        return 0
    q = float(Fraction(f_hz) * CYCLE / fs)  # correctly rounded: one binary64 division
    return round(Fraction(q))  # Fraction rounds half to even


def run(*args):
    result = subprocess.run([sys.executable, *map(str, args)], capture_output=True,
                            text=True, timeout=300)
    return result.returncode, result.stdout + result.stderr


# ------------------------------------------------------------ generator


def test_generator_check_passes_on_repo_file():
    code, out = run(GENERATOR, "--check")
    assert code == 0, out


def test_generator_check_fails_on_tampered_copy(tmp_path, monkeypatch, capsys):
    # In process, with build() returning the repo file's data: a fresh build
    # takes about 14 s, and the test above already proves the file equals one.
    gen = load_module("signal_spec_vectors", GENERATOR)
    monkeypatch.setattr(gen, "build", lambda: load_json(VECTORS))
    untouched = tmp_path / "untouched.json"
    untouched.write_text(VECTORS.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    assert gen.main(["signal_spec_vectors.py", "--check", "--out", str(untouched)]) == 0
    data = load_json(VECTORS)
    data["increments"][0]["inc"] = str(int(data["increments"][0]["inc"]) + 1)
    tampered = tmp_path / "signal_spec_vectors.json"
    tampered.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert gen.main(["signal_spec_vectors.py", "--check", "--out", str(tampered)]) == 1
    assert "differs" in capsys.readouterr().out


# ------------------------------------------------------ spec doc vs JSON


def table_blocks(text):
    """Every Markdown table in text, as a tuple of its stripped lines."""
    blocks, current = [], []
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            current.append(line.strip())
        elif current:
            blocks.append(tuple(current))
            current = []
    if current:
        blocks.append(tuple(current))
    return blocks


def doc_vector_tables(text):
    """Tables of each '### Vectors: ...' section, plus the coefficient table."""
    tables, heading = [], None
    section = []
    for line in text.splitlines() + ["### end"]:
        if line.startswith("#"):
            if heading is not None and heading.startswith("### Vectors:"):
                found = table_blocks("\n".join(section))
                assert found, f"no table under {heading}"
                tables.extend(found)
            heading, section = line.strip(), []
        else:
            section.append(line)
    tables.extend(b for b in table_blocks(text) if b[0].startswith("| Power | Exact |"))
    return tables


def doc_table_problems(text, data):
    gen = load_module("signal_spec_vectors", GENERATOR)
    generated = table_blocks(gen.tables(data))
    in_doc = doc_vector_tables(text)
    problems = []
    for block in generated:
        if block not in in_doc:
            problems.append(f"generated table missing from the spec: {block[0]} ... {block[-1]}")
    for block in in_doc:
        if block not in generated:
            problems.append(f"spec table not in the JSON: {block[0]} ... {block[-1]}")
    return generated, in_doc, problems


def test_spec_tables_equal_json(vectors):
    generated, in_doc, problems = doc_table_problems(SPEC_DOC.read_text(encoding="utf-8"),
                                                     vectors)
    # Core and sine (7), internal blocks (1), stub chain increments and samples (2),
    # theta reference (5: ratio to phase, edge length, envelopes, fixtures,
    # samples), gamma PAC layer (4: envelope, fixtures, samples, theta and
    # gamma bus), coupling (4: coupling phase, swell, swell fixtures, swell
    # samples), binaural layer and rate curve (7: cycle cosine coefficients,
    # cycle cosine, cycles to units, rate cycle, rate curve, binaural
    # fixtures, binaural samples), 24-bit rounding (1).
    assert len(generated) == 31, generated
    assert len(in_doc) == len(generated), [b[0] for b in in_doc]
    assert not problems, "\n".join(problems)


def test_spec_table_mismatch_is_caught(vectors):
    text = SPEC_DOC.read_text(encoding="utf-8")
    inc = vectors["increments"][0]["inc"]
    doctored = text.replace(f"| {inc} |", f"| {int(inc) + 1} |", 1)
    assert doctored != text
    _, _, problems = doc_table_problems(doctored, vectors)
    assert problems


# ------------------------------------------------------- reference ideal


def test_ideal_phase_increment_vectors(vectors):
    mod = ideal()
    for v in vectors["increments"]:
        f = float.fromhex(v["f_hex"])
        got = mod.phase_increment(f, v["fs"])
        assert isinstance(got, int), (v["label"], type(got))
        assert got == int(v["inc"]), (v["case"], v["label"], v["fs"], got)


def test_ideal_seconds_to_samples_vectors(vectors):
    mod = ideal()
    for v in vectors["samples"]:
        t = float.fromhex(v["t_hex"])
        got = mod.seconds_to_samples(t, v["fs"])
        assert isinstance(got, int), (v["label"], type(got))
        assert got == int(v["n"]), (v["case"], v["label"], v["fs"], got)


def close_to_decimal(value, text, tol=IDEAL_TOL):
    return abs(Decimal(repr(float(value))) - Decimal(text)) <= Decimal(repr(tol))


def sine_vectors(vectors):
    rows = [(f"phase {v['label']}", int(v["phase"]), v["sine"]) for v in vectors["exact_phases"]]
    rows += [(f"450 Hz carrier, unmodulated, sample {v['n']}", int(v["phase"]), v["sine"])
             for v in vectors["carrier_450_44100"]["samples"]]
    return rows


def test_ideal_sine_scalar_vectors(vectors):
    mod = ideal()
    for label, phase, sine in sine_vectors(vectors):
        got = mod.ideal_sine(phase)
        assert np.ndim(got) == 0, label
        assert close_to_decimal(got, sine), (label, float(got), sine)


def test_ideal_sine_array_vectors(vectors):
    mod = ideal()
    rows = sine_vectors(vectors)
    phases = np.array([p for _, p, _ in rows], dtype=np.uint64)
    got = mod.ideal_sine(phases)
    assert isinstance(got, np.ndarray) and got.dtype == np.float64, type(got)
    assert got.shape == phases.shape
    for (label, _, sine), value in zip(rows, got):
        assert close_to_decimal(value, sine), (label, float(value), sine)


def test_ideal_sine_mismatch_is_caught(vectors):
    for label, _, sine in sine_vectors(vectors):
        assert not close_to_decimal(float(Decimal(sine)) + 4 * IDEAL_TOL, sine), label


def test_render_probe_segment(vectors):
    mod = ideal()
    carrier = vectors["carrier_450_44100"]
    fs = carrier["fs"]
    f = float(carrier["f_hz"])
    inc = int(carrier["inc"])
    n = 44101
    seg = mod.render_probe_segment(f, fs, n)
    assert isinstance(seg, np.ndarray) and seg.dtype == np.float64
    assert seg.shape == (n,)
    phases = (np.arange(n, dtype=np.uint64) * np.uint64(inc))  # wraps mod 2^64
    assert np.array_equal(seg, mod.ideal_sine(phases))
    for v in carrier["samples"]:
        if v["n"] < n:
            assert close_to_decimal(seg[v["n"]], v["sine"]), v["n"]


def test_probe_sine_component():
    mod = ideal()
    assert tuple(mod.PROBE_CARRIERS_HZ) == (1.0, 450.0, 1000.0)
    for fs in sample_rates():
        comp = mod.probe_sine_component(fs)
        assert isinstance(comp, np.ndarray) and comp.dtype == np.float64
        assert comp.shape == (3 * fs,), comp.shape
        assert np.all(np.isfinite(comp))
        for i, f in enumerate(mod.PROBE_CARRIERS_HZ):
            seg = comp[i * fs:(i + 1) * fs]
            assert seg[0] == 0.0, (fs, f)  # each segment starts at phase 0
            assert np.array_equal(seg, mod.render_probe_segment(f, fs, fs)), (fs, f)


def test_ideal_does_not_implement_the_engine_polynomial(vectors):
    assert IDEAL.is_file(), f"missing {IDEAL}"
    source = IDEAL.read_text(encoding="utf-8").lower()
    for c in vectors["sine_coefficients"]:
        if c["power"] < 3:
            continue
        mantissa = c["hex"].lstrip("-").lower()
        assert mantissa not in source, f"engine coefficient C{c['power']} in {IDEAL.name}"
        assert mantissa.replace("0x", "") not in source, c["power"]
        exact = float.fromhex(c["hex"])
        assert repr(abs(exact)) not in source, f"engine coefficient C{c['power']} in decimal"
    for k in (3, 5, 7, 9, 11):
        factorial = str(math.factorial(k))
        assert not re.search(rf"(?<![0-9.]){factorial}(?![0-9])", source), (
            f"{k}! = {factorial} in {IDEAL.name}: Taylor code")
    assert "factorial" not in source


# --------------------------------------------- quantization and drift


def quantization(f_hz, fs, inc):
    """Exact played-frequency error in Hz and drift in seconds over the session."""
    f = Fraction(f_hz)
    err = abs(Fraction(inc * fs, CYCLE) - f)
    drift = err * session_s() / f if f > 0 else Fraction(0)
    return err, drift


def range_endpoints():
    for row in listed_hz_ranges():
        for end in ("min", "max"):
            for fs in listed_sample_rates():
                yield row.id, end, getattr(row, end), fs


def test_hz_range_rows_present():
    found = {row.id for row in hz_ranges()}
    assert set(HZ_RANGE_IDS) <= found, sorted(found)


@pytest.mark.parametrize("row_id, end, f_hz, fs", list(range_endpoints()))
def test_endpoint_quantization_and_drift_exact(row_id, end, f_hz, fs):
    record_rows(row_id)
    inc = spec_increment(f_hz, fs)
    if f_hz == 0.0:
        assert inc == 0
        return
    err, drift = quantization(f_hz, fs, inc)
    assert err < accuracy_hz(), (row_id, end, fs, float(err))
    assert drift < drift_bound_s(), (row_id, end, fs, float(drift))


@pytest.mark.parametrize("row_id, end, f_hz, fs", list(range_endpoints()))
def test_ideal_increment_matches_exact_rule_at_endpoints(row_id, end, f_hz, fs):
    record_rows(row_id)
    assert ideal().phase_increment(f_hz, fs) == spec_increment(f_hz, fs), (row_id, end, fs)


def test_endpoint_doctored_increment_fails():
    hz_ranges()
    sample_rates()
    acc = accuracy_hz()
    for row_id, end, f_hz, fs in range_endpoints():
        if f_hz == 0.0:
            continue
        offset = math.ceil(2 * acc * CYCLE / fs)
        err, drift = quantization(f_hz, fs, spec_increment(f_hz, fs) + offset)
        assert err >= acc, (row_id, end, fs)
        assert drift >= drift_bound_s(), (row_id, end, fs)


def analytic_bounds(f_lo, f_hi, fs, cycle=CYCLE):
    """Worst case over (0 <) f_lo <= f <= f_hi of the error and drift of the rule.

    |inc - f*cycle/fs| <= 1/2 (integer rounding) + ulp(q)/2 (division
    rounding), and ulp(q)/2 <= q * 2^-53. Error in Hz is that times fs/cycle;
    drift is error * T / f. The 1/2 term is worst at f_lo, the ulp term is at
    most 2^-53 * T for every f.
    """
    q_hi = Fraction(f_hi) * cycle / fs
    half_ulp_hi = Fraction(math.ulp(float(q_hi))) / 2
    err = (Fraction(1, 2) + half_ulp_hi) * fs / cycle
    drift = Fraction(1, 2) * fs / cycle * session_s() / Fraction(f_lo) + session_s() * Fraction(1, 2**53)
    return err, drift


def analytic_rows():
    for row in listed_hz_ranges():
        lo = fraction_of(row.min_text)
        hi = fraction_of(row.max_text)
        f_lo = lo if lo > 0 else GRID_STEP_HZ
        for fs in listed_sample_rates():
            yield row.id, f_lo, hi, fs


@pytest.mark.parametrize("row_id, f_lo, f_hi, fs", list(analytic_rows()))
def test_analytic_worst_case_bound(row_id, f_lo, f_hi, fs):
    record_rows(row_id)
    err, drift = analytic_bounds(f_lo, f_hi, fs)
    assert err < accuracy_hz(), (row_id, fs, float(err))
    assert drift < drift_bound_s(), (row_id, fs, float(drift))


def test_analytic_bound_fails_for_a_32_bit_accumulator():
    """Must fail: with a 2^32 cycle the 8-hour drift at the grid floor exceeds the bound."""
    hz_ranges()
    sample_rates()
    failed = False
    for row_id, f_lo, f_hi, fs in analytic_rows():
        _, drift = analytic_bounds(f_lo, f_hi, fs, cycle=2**32)
        failed = failed or drift >= drift_bound_s()
    assert failed

# ------------------------------------------------------- derived table row


def test_right_carrier_row_is_carrier_max_plus_beat_max():
    """binaural-carrier-right is derived: right carrier = left carrier + beat rate."""
    right = table_row("binaural-carrier-right")
    left = table_row("binaural-carrier")
    beat = table_row("beat-rate")
    assert right.unit == left.unit == beat.unit == "Hz"
    assert Fraction(right.max_text) == Fraction(left.max_text) + Fraction(beat.max_text)
    assert Fraction(right.min_text) == Fraction(left.min_text) + Fraction(beat.min_text)
    assert right.max_bound == "exclusive"


# ------------------------------------------- internal blocks and stub chain

FIXTURES_VALID = REPO_ROOT / "recipes" / "fixtures" / "valid"


def bits_value(text):
    """The binary64 value of a big-endian 64-bit pattern written as 0x... hex."""
    return struct.unpack(">d", bytes.fromhex(text[2:]))[0]


def test_block_vectors(vectors):
    assert vectors["block_frames"] == 64
    assert vectors["blocks"], "no block vectors"
    for v in vectors["blocks"]:
        assert v["block"] == v["frame"] // vectors["block_frames"], v
        assert v["offset"] == v["frame"] % vectors["block_frames"], v
    frames = {v["frame"] for v in vectors["blocks"]}
    assert {0, 63, 64, 65} <= frames, frames


def test_stub_chain_rows_name_fixtures_with_their_values(vectors):
    rows = vectors["stub_chain"]
    assert {r["fixture"] for r in rows} == {"stub-chain-1s-beat-0.json", "stub-chain-1s-beat-6.json"}
    # One fixture with a theta reference and one without.
    assert {r["theta_carrier_hex"] == "none" for r in rows} == {True, False}
    for r in rows:
        path = FIXTURES_VALID / r["fixture"]
        assert path.is_file(), f"missing fixture {path}"
        recipe = json.loads(path.read_text(encoding="utf-8"))
        assert float(recipe["binaural"]["carrier_left_hz"]) == float.fromhex(r["carrier_left_hex"]), r
        assert float(recipe["binaural"]["beat_rate_hz"]) == float.fromhex(r["beat_rate_hex"]), r
        if r["theta_carrier_hex"] == "none":
            assert "theta_reference" not in recipe, r
            assert r["theta_rate_hex"] == r["theta_depth_hex"] == r["theta_shape"] == "none", r
        else:
            theta = recipe["theta_reference"]
            assert float(theta["carrier_hz"]) == float.fromhex(r["theta_carrier_hex"]), r
            # Story 2.1: a stub chain theta reference is the real layer at
            # depth 0, which keeps the Story 1.5 bytes.
            assert float(theta["rate_hz"]) == float.fromhex(r["theta_rate_hex"]), r
            assert float(theta["am_depth_percent"]) == float.fromhex(r["theta_depth_hex"]), r
            assert theta["shape"] == r["theta_shape"], r
            assert float.fromhex(r["theta_depth_hex"]) == 0.0, r
        assert int(r["frames"]) == round(Fraction(float(recipe["length_s"])) * r["fs"]), r


def test_stub_chain_rows_follow_the_core_rules(vectors):
    record_rows("binaural-carrier-right")
    cases = set()
    for r in vectors["stub_chain"]:
        fs = r["fs"]
        left = float.fromhex(r["carrier_left_hex"])
        right = float.fromhex(r["carrier_right_hex"])
        assert right == left + float.fromhex(r["beat_rate_hex"]), r
        assert int(r["inc_left"]) == spec_increment(left, fs), r
        assert int(r["inc_right"]) == spec_increment(right, fs), r
        if r["theta_carrier_hex"] == "none":
            assert r["inc_theta"] == "0", r
        else:
            assert int(r["inc_theta"]) == spec_increment(float.fromhex(r["theta_carrier_hex"]), fs), r
        n = int(r["n"])
        assert int(r["phase_theta"]) == n * int(r["inc_theta"]) % CYCLE, r
        assert int(r["phase_left"]) == n * int(r["inc_left"]) % CYCLE, r
        assert int(r["phase_right"]) == n * int(r["inc_right"]) % CYCLE, r
        assert r["case"] == ("past_end" if n >= int(r["frames"]) else "signal"), r
        cases.add((r["fixture"], fs, r["case"]))
    for fixture in ("stub-chain-1s-beat-0.json", "stub-chain-1s-beat-6.json"):
        for fs in listed_sample_rates():
            assert (fixture, fs, "signal") in cases and (fixture, fs, "past_end") in cases


def engine_sine_value(phase):
    """The spec engine sine of phase, from the generator (binary64)."""
    return load_module("signal_spec_vectors", GENERATOR).engine_sine(phase)


def output_bound(r, bound):
    """Bound on |out - ideal out|: one sine without a theta reference, else two
    sines each within the bound plus one binary64 rounding of the sum (at most
    2^-52 for |out| below 2)."""
    if r["theta_carrier_hex"] == "none":
        return Decimal(repr(bound))
    return 2 * Decimal(repr(bound)) + Decimal(repr(2.0**-52))


def test_stub_chain_bits_are_within_the_sine_bound_of_the_ideal(vectors):
    bound = 10.0 ** (sine_bound_dbfs() / 20.0)
    for r in vectors["stub_chain"]:
        theta = bits_value(r["theta_bits"])
        if r["case"] == "past_end" or r["theta_carrier_hex"] == "none":
            assert r["theta_bits"] == "0x0000000000000000", r
        else:
            assert abs(Decimal(repr(theta)) - Decimal(r["ideal_theta"])) <= Decimal(repr(bound)), (
                r["fixture"], r["fs"], r["n"], "theta")
        for side in ("left", "right"):
            got = bits_value(r[f"{side}_bits"])
            if r["case"] == "past_end":
                assert r[f"{side}_bits"] == "0x0000000000000000", r
                continue
            assert abs(Decimal(repr(got)) - Decimal(r[f"ideal_{side}"])) <= output_bound(r, bound), (
                r["fixture"], r["fs"], r["n"], side)


def test_stub_chain_doctored_bits_fail_the_bound(vectors):
    bound = 10.0 ** (sine_bound_dbfs() / 20.0)
    r = next(v for v in vectors["stub_chain"] if v["case"] == "signal" and v["n"] == "37")
    got = bits_value(r["left_bits"]) + 1e-5
    assert abs(Decimal(repr(got)) - Decimal(r["ideal_left"])) > Decimal(repr(bound))
    # A theta reference left at zeros (the Story 1.2 stub) fails the theta
    # bound and the output bound of the beat-6 rows.
    t = next(v for v in vectors["stub_chain"]
             if v["case"] == "signal" and v["n"] == "37" and v["theta_carrier_hex"] != "none")
    assert abs(Decimal(0) - Decimal(t["ideal_theta"])) > Decimal(repr(bound))
    binaural_only = engine_sine_value(int(t["phase_left"]))
    assert abs(Decimal(repr(binaural_only)) - Decimal(t["ideal_left"])) > output_bound(t, bound)


def test_stub_chain_ideal_matches_the_reference_ideal_sine(vectors):
    mod = ideal()
    for r in vectors["stub_chain"]:
        if r["case"] != "signal":
            continue
        if r["theta_carrier_hex"] == "none":
            assert r["ideal_theta"] == "0", r
            theta = 0.0
        else:
            theta = mod.ideal_sine(int(r["phase_theta"]))
            assert close_to_decimal(theta, r["ideal_theta"]), (r["fixture"], r["fs"], r["n"], "theta")
        for side in ("left", "right"):
            value = theta + mod.ideal_sine(int(r[f"phase_{side}"]))  # one binary64 rounding
            assert close_to_decimal(value, r[f"ideal_{side}"]), (
                r["fixture"], r["fs"], r["n"], side)


# ---------------------------------------------------------- 24-bit rounding

Q24_MAX = 2**23 - 1
Q24_MIN = -(2**23)


def sample_of(text):
    """The binary64 sample of an s_hex cell (hex float, nan, inf, or -inf)."""
    return {"nan": math.nan, "inf": math.inf, "-inf": -math.inf}.get(text) or float.fromhex(text)


def rule_q24(s):
    """The spec rule in binary64, independent of the generator's Fraction path."""
    if math.isnan(s):
        return 0
    x = s * 8388608.0  # exact: a power-of-two scale
    if x >= Q24_MAX:
        return Q24_MAX
    if x <= Q24_MIN:
        return Q24_MIN
    return int(round(x))  # round() on a float is exact, ties to even


def round_even(x):
    return int(round(x))


def naive_no_clamp(s):
    """Rounds ties to even but wraps to 24 bits instead of clamping."""
    if math.isnan(s):
        return 0
    x = s * 8388608.0
    if math.isinf(x):
        return 0
    return (round_even(x) + 2**23) % 2**24 - 2**23


def naive_no_nan_rule(s):
    """Clamps with `not (x < max)`, so NaN lands on full scale."""
    x = s * 8388608.0
    if not (x < Q24_MAX):
        return Q24_MAX
    if x <= Q24_MIN:
        return Q24_MIN
    return round_even(x)


def naive_truncate(s):
    """Spec clamp and NaN rule, truncation toward zero instead of ties to even."""
    if math.isnan(s):
        return 0
    x = s * 8388608.0
    if x >= Q24_MAX:
        return Q24_MAX
    if x <= Q24_MIN:
        return Q24_MIN
    return math.trunc(x)


def naive_half_away(s):
    """Spec clamp and NaN rule, ties away from zero instead of ties to even."""
    if math.isnan(s):
        return 0
    x = s * 8388608.0
    if x >= Q24_MAX:
        return Q24_MAX
    if x <= Q24_MIN:
        return Q24_MIN
    f = math.floor(x)
    if x - f == 0.5:
        return f + 1 if x > 0 else f
    return round_even(x)


def le24(v):
    return (v % 2**24).to_bytes(3, "little").hex()


def test_quantize_vectors_follow_the_rule(vectors):
    rows = vectors["quantize_24"]
    assert rows, "no 24-bit rounding vectors"
    for r in rows:
        s = sample_of(r["s_hex"])
        assert Q24_MIN <= r["value"] <= Q24_MAX, r
        assert rule_q24(s) == r["value"], r
        assert le24(r["value"]) == r["bytes"], r
        if r["s_hex"] != "nan":
            assert sample_of(r["x_hex"]) == s * 8388608.0, r


def test_generator_quantizer_matches_vectors(vectors):
    gen = load_module("signal_spec_vectors", GENERATOR)
    for r in vectors["quantize_24"]:
        s = sample_of(r["s_hex"])
        assert gen.quantize_24(s) == r["value"], r
        assert gen.pack_24(r["value"]) == r["bytes"], r


def test_quantize_vectors_cover_the_matrix_row(vectors):
    lsb = 2.0**-23
    wanted = {
        "+1.0": 1.0, "above +1": math.nextafter(1.0, 2.0), "-1.0": -1.0,
        "below -1": math.nextafter(-1.0, -2.0), "+inf": math.inf, "-inf": -math.inf,
        "+0.5 LSB": 0.5 * lsb, "-0.5 LSB": -0.5 * lsb, "+1.5 LSB": 1.5 * lsb,
        "-1.5 LSB": -1.5 * lsb, "+2.5 LSB": 2.5 * lsb, "-2.5 LSB": -2.5 * lsb,
    }
    rows = vectors["quantize_24"]
    have = [sample_of(r["s_hex"]) for r in rows]
    for name, s in wanted.items():
        assert any(h == s for h in have), f"no 24-bit rounding vector for {name}"
    assert any(r["s_hex"] == "nan" for r in rows), "no NaN vector"
    assert any(r["s_hex"] == "-0x0.0p+0" for r in rows), "no -0.0 vector"
    assert {r["rule"] for r in rows} == {"clamp", "nan", "tie", "round", "zero"}


@pytest.mark.parametrize("naive, rule", [
    (naive_no_clamp, "clamp"),
    (naive_no_nan_rule, "nan"),
    (naive_truncate, "tie"),
    (naive_half_away, "tie"),
])
def test_naive_conversion_fails_a_vector_of_its_rule(vectors, naive, rule):
    caught = [r["label"] for r in vectors["quantize_24"]
              if r["rule"] == rule and naive(sample_of(r["s_hex"])) != r["value"]]
    assert caught, f"{naive.__name__} passes every {rule} vector"


# ------------------------------------------------- theta reference (Story 2.1)
#
# Vectors file keys: `theta_constants` (shapes, on_share_percent, edge_ms,
# on_share_hex, edge_s_hex, h_units), `ratio_to_phase` (label, r_hex, x_hex,
# phase), `theta_edges` (rate_hex, edge_s_hex, w_hex, w_units),
# `theta_envelopes` (shape, rate_hex, w_units, h_units, phase, region,
# e_bits, ideal_e), and `theta_samples` (case, fixture, fs, shape,
# carrier_hex, rate_hex, depth_hex, length_hex, inc_carrier, inc_rate,
# w_units, h_units, frames, n, phase_carrier, phase_rate, region, e_bits,
# a_bits, theta_bits, ideal_e, ideal_theta). The checks below re-derive every
# integer and segment from the spec rules here, with Fraction arithmetic and
# the standard library, independent of the generator's code paths. The fixed
# constants come from range rows theta-on-share (percent) and theta-edge (ms),
# each min equal to max.

THETA_SHAPES = ("sine", "smoothed_on_off", "sawtooth", "reverse_saw")
SEGMENTS = {
    "sine": {"zero degree", "cosine"},
    "smoothed_on_off": {"zero degree", "plateau", "falling edge", "off", "rising edge"},
    "sawtooth": {"zero degree", "drop edge", "linear rise"},
    "reverse_saw": {"zero degree", "linear fall", "rise edge"},
}
HALF = 2**63
THETA_FIXTURE_NAMES = tuple(f"theta-{s.replace('_', '-')}-{rate}hz.json"
                            for s in THETA_SHAPES for rate in (1, 6))


def range_in(row_id, unit):
    r = table_row(row_id)
    assert r.kind == "ranges" and r.unit == unit, r
    return r


def fixed_range(row_id, unit):
    r = range_in(row_id, unit)
    assert r.min == r.max, f"{row_id} is a fixed value: min equals max"
    return r


def on_share_fraction():
    return Fraction(fixed_range("theta-on-share", "percent").min_text) / 100


def edge_seconds():
    return seconds(fixed_range("theta-edge", "ms").min_text, "ms")


def spec_h_units():
    d = float(on_share_fraction())  # D: exact in binary64 for 50 percent
    assert Fraction(d) == on_share_fraction()
    return round(Fraction(d) * 2**63)


def spec_w_units(rate_hz):
    e = float(edge_seconds())  # the binary64 of 10 / 1000, as one division gives
    w = float(Fraction(e) * Fraction(rate_hz))  # one binary64 rounding
    return round(Fraction(w) * CYCLE), w


def spec_segment(shape, p, w, h):
    if shape == "sine":
        return "zero degree" if p == 0 else "cosine"
    if shape == "smoothed_on_off":
        m = p if p < HALF else CYCLE - p
        if m <= h - w:
            return "zero degree" if p == 0 else "plateau"
        if m >= h:
            return "off"
        return "falling edge" if p < HALF else "rising edge"
    if shape == "sawtooth":
        return ("zero degree" if p == 0 else "drop edge") if p < w else "linear rise"
    q = (CYCLE - p) % CYCLE
    return ("zero degree" if p == 0 else "rise edge") if q < w else "linear fall"


def float_ideal_envelope(shape, p, w, h):
    """The ideal envelope in binary64 (math.cos, exact ratios rounded once)."""
    if shape == "sine":
        return (1.0 + ideal().ideal_sine((p + 2**62) % CYCLE)) / 2.0
    if shape == "smoothed_on_off":
        m = p if p < HALF else CYCLE - p
        if m <= h - w:
            return 1.0
        if m >= h:
            return 0.0
        return (1.0 + math.cos(math.pi * float(Fraction(m - (h - w), w)))) / 2.0
    q = p if shape == "sawtooth" else (CYCLE - p) % CYCLE
    if q < w:
        return (1.0 + math.cos(math.pi * float(Fraction(q, w)))) / 2.0
    return float(Fraction(q - w, CYCLE - w))


def sine_bound_decimal():
    return Decimal(repr(10.0 ** (sine_bound_dbfs() / 20.0)))


def envelope_bound():
    """|e - e_ideal| <= b / 2 + 2^-48 (signal spec, Theta reference, Error bound)."""
    return sine_bound_decimal() / 2 + Decimal(repr(2.0**-48))


def theta_bound():
    """|theta - theta_ideal| <= 1.5 * b + 2^-47."""
    return Decimal("1.5") * sine_bound_decimal() + Decimal(repr(2.0**-47))


def bits_text(x):
    return "0x" + struct.pack(">d", x).hex()


def generator():
    return load_module("signal_spec_vectors", GENERATOR)


def test_theta_constants_equal_the_fixed_range_rows(vectors):
    c = vectors["theta_constants"]
    assert tuple(c["shapes"]) == THETA_SHAPES
    on_share = fixed_range("theta-on-share", "percent")
    edge = fixed_range("theta-edge", "ms")
    assert Fraction(c["on_share_percent"]) == Fraction(on_share.min_text)
    assert Fraction(c["edge_ms"]) == Fraction(edge.min_text)
    assert float.fromhex(c["on_share_hex"]) == float(on_share_fraction())
    assert float.fromhex(c["edge_s_hex"]) == float(edge_seconds())
    assert int(c["h_units"]) == spec_h_units()
    gen = generator()
    assert gen.THETA_ON_SHARE_PERCENT == on_share.min
    assert gen.THETA_EDGE_MS == edge.min


def test_theta_fixture_values_lie_in_the_locked_ranges(vectors):
    record_rows("theta-rate", "theta-carrier")
    rate = range_in("theta-rate", "Hz")
    carrier = range_in("theta-carrier", "Hz")
    depth = range_in("theta-depth", "percent")
    for r in vectors["theta_samples"]:
        assert rate.min <= float.fromhex(r["rate_hex"]) <= rate.max, r["fixture"]
        assert carrier.min <= float.fromhex(r["carrier_hex"]) <= carrier.max, r["fixture"]
        assert depth.min <= float.fromhex(r["depth_hex"]) <= depth.max, r["fixture"]


def test_edges_fit_inside_every_segment_across_the_rate_range():
    rate = range_in("theta-rate", "Hz")
    h = spec_h_units()
    w_low, _ = spec_w_units(rate.min)
    w_top, _ = spec_w_units(rate.max)
    assert 0 < w_low < w_top
    assert w_top < h - w_top, "the smoothed on-off edges overlap at the top theta rate"
    assert w_top < CYCLE - w_top


def test_ratio_to_phase_vectors_follow_the_rule(vectors):
    rows = vectors["ratio_to_phase"]
    assert rows
    for r in rows:
        x = sample_of(r["r_hex"])
        if not (x > 0.0):
            want = 0
            assert r["x_hex"] == "none", r
        elif x >= 1.0:
            want = HALF
            assert r["x_hex"] == "none", r
        else:
            want = round(Fraction(x) * 2**63)  # exact scale; Fraction rounds half to even
            assert sample_of(r["x_hex"]) == x * 2.0**63, r
        assert int(r["phase"]) == want, r
    labels = " ".join(r["label"] for r in rows)
    for word in ("NaN", "tie", "one", "negative zero", "infinity"):
        assert word in labels, word


def test_ratio_to_phase_ties_go_to_even(vectors):
    ties = [r for r in vectors["ratio_to_phase"] if r["label"].startswith("tie")]
    assert len(ties) >= 2
    for r in ties:
        x = Fraction(sample_of(r["x_hex"]))
        assert x - math.floor(x) == Fraction(1, 2), r
        assert int(r["phase"]) % 2 == 0, r


def test_theta_edge_vectors_follow_the_rule(vectors):
    rows = vectors["theta_edges"]
    rate = range_in("theta-rate", "Hz")
    rates = {float.fromhex(r["rate_hex"]) for r in rows}
    assert {rate.min, rate.max} <= rates, rates
    for r in rows:
        w_units, w = spec_w_units(float.fromhex(r["rate_hex"]))
        assert float.fromhex(r["edge_s_hex"]) == float(edge_seconds()), r
        assert float.fromhex(r["w_hex"]) == w, r
        assert int(r["w_units"]) == w_units, r


def test_theta_envelope_vectors(vectors):
    rows = vectors["theta_envelopes"]
    rate = range_in("theta-rate", "Hz")
    seen = {shape: set() for shape in THETA_SHAPES}
    bound = envelope_bound()
    rates = set()
    h = spec_h_units()
    for r in rows:
        shape, p = r["shape"], int(r["phase"])
        f = float.fromhex(r["rate_hex"])
        rates.add(f)
        w, _ = spec_w_units(f)
        assert int(r["w_units"]) == w and int(r["h_units"]) == h, r
        assert r["region"] == spec_segment(shape, p, w, h), r
        seen[shape].add(r["region"])
        e = bits_value(r["e_bits"])
        assert 0.0 <= e <= 1.0, r
        assert abs(Decimal(repr(e)) - Decimal(r["ideal_e"])) <= bound, (shape, f, p)
        assert close_to_decimal(float_ideal_envelope(shape, p, w, h), r["ideal_e"]), (shape, f, p)
        if r["region"] == "plateau":
            assert e == 1.0, r
        if r["region"] == "off":
            assert r["e_bits"] == "0x0000000000000000", r
        if p == 0:
            assert Decimal(r["ideal_e"]) == 1, r  # the 0 degree point is the peak
    assert {rate.min, rate.max} <= rates
    for shape in THETA_SHAPES:
        assert seen[shape] == SEGMENTS[shape], (shape, seen[shape])


def test_theta_envelope_bound_catches_a_mirrored_shape(vectors):
    # Must-fail: the sawtooth vectors read through the reverse saw miss the
    # bound on some row.
    gen = generator()
    bound = envelope_bound()
    rows = [r for r in vectors["theta_envelopes"] if r["shape"] == "sawtooth"]
    misses = [r for r in rows if abs(Decimal(repr(gen.engine_envelope(
        "reverse_saw", int(r["phase"]), int(r["w_units"]), int(r["h_units"]))))
        - Decimal(r["ideal_e"])) > bound]
    assert misses


def test_generator_engine_envelope_stays_in_range_and_bound():
    gen = generator()
    bound = float(envelope_bound())
    h = spec_h_units()
    rate = range_in("theta-rate", "Hz")
    for f in (rate.min, rate.max):
        w, _ = spec_w_units(f)
        phases = [k * 2**52 + 12345 for k in range(4096)] + [w - 1, w, h - w, h, CYCLE - w]
        for shape in THETA_SHAPES:
            for p in phases:
                p %= CYCLE
                e = gen.engine_envelope(shape, p, w, h)
                assert 0.0 <= e <= 1.0, (shape, f, p, e)
                assert abs(e - float_ideal_envelope(shape, p, w, h)) <= bound, (shape, f, p)


def test_theta_sample_rows_name_fixtures_with_their_values(vectors):
    rows = vectors["theta_samples"]
    names = []
    for r in rows:
        if r["fixture"] not in names:
            names.append(r["fixture"])
    assert tuple(names) == THETA_FIXTURE_NAMES
    checked = set()
    for r in rows:
        if r["fixture"] in checked:
            continue
        checked.add(r["fixture"])
        path = FIXTURES_VALID / r["fixture"]
        assert path.is_file(), f"missing fixture {path}"
        recipe = json.loads(path.read_text(encoding="utf-8"))
        assert "binaural" not in recipe, r["fixture"]
        theta = recipe["theta_reference"]
        assert set(theta) == {"carrier_hz", "rate_hz", "am_depth_percent", "shape"}, r["fixture"]
        assert float(theta["carrier_hz"]) == float.fromhex(r["carrier_hex"]) == 450.0, r["fixture"]
        assert float(theta["rate_hz"]) == float.fromhex(r["rate_hex"]), r["fixture"]
        assert float(theta["am_depth_percent"]) == float.fromhex(r["depth_hex"]) == 75.0, r["fixture"]
        assert theta["shape"] == r["shape"], r["fixture"]
        assert float(recipe["length_s"]) == float.fromhex(r["length_hex"]) == 10.0, r["fixture"]
    for r in rows:
        assert int(r["frames"]) == round(Fraction(float.fromhex(r["length_hex"])) * r["fs"]), r


def test_theta_sample_rows_follow_the_rules(vectors):
    cases = set()
    h = spec_h_units()
    for r in vectors["theta_samples"]:
        fs = r["fs"]
        assert int(r["inc_carrier"]) == spec_increment(float.fromhex(r["carrier_hex"]), fs), r
        assert int(r["inc_rate"]) == spec_increment(float.fromhex(r["rate_hex"]), fs), r
        w, _ = spec_w_units(float.fromhex(r["rate_hex"]))
        assert int(r["w_units"]) == w and int(r["h_units"]) == h, r
        n = int(r["n"])
        assert int(r["phase_carrier"]) == n * int(r["inc_carrier"]) % CYCLE, r
        assert int(r["phase_rate"]) == n * int(r["inc_rate"]) % CYCLE, r
        past = n >= int(r["frames"])
        assert r["case"] == ("past_end" if past else "signal"), r
        cases.add((r["fixture"], fs, r["case"]))
        if past:
            assert r["theta_bits"] == r["e_bits"] == r["a_bits"] == "0x0000000000000000", r
            assert r["ideal_theta"] == "0", r
            continue
        assert r["region"] == spec_segment(r["shape"], int(r["phase_rate"]), w, h), r
    for name in THETA_FIXTURE_NAMES:
        for fs in listed_sample_rates():
            assert (name, fs, "signal") in cases and (name, fs, "past_end") in cases, (name, fs)
    for shape in THETA_SHAPES:
        found = {r["region"] for r in vectors["theta_samples"]
                 if r["shape"] == shape and r["case"] == "signal"}
        assert SEGMENTS[shape] <= found, (shape, found)


def test_theta_sample_bits_follow_the_depth_law_and_bound(vectors):
    gen = generator()
    for r in vectors["theta_samples"]:
        if r["case"] != "signal":
            continue
        e = bits_value(r["e_bits"])
        assert e == gen.engine_envelope(r["shape"], int(r["phase_rate"]), int(r["w_units"]),
                                        int(r["h_units"])), r
        d = float.fromhex(r["depth_hex"]) / 100.0
        a = 1.0 - d * (1.0 - e)
        assert a == bits_value(r["a_bits"]), r
        theta = bits_value(r["theta_bits"])
        assert theta == a * engine_sine_value(int(r["phase_carrier"])), r
        assert abs(Decimal(repr(e)) - Decimal(r["ideal_e"])) <= envelope_bound(), r
        assert abs(Decimal(repr(theta)) - Decimal(r["ideal_theta"])) <= theta_bound(), (
            r["fixture"], r["fs"], r["n"])


def test_theta_sample_ideal_matches_the_reference_ideal_sine(vectors):
    mod = ideal()
    for r in vectors["theta_samples"]:
        if r["case"] != "signal":
            continue
        d = float.fromhex(r["depth_hex"]) / 100.0
        a = 1.0 - d * (1.0 - float(Decimal(r["ideal_e"])))
        value = a * mod.ideal_sine(int(r["phase_carrier"]))
        assert close_to_decimal(value, r["ideal_theta"]), (r["fixture"], r["fs"], r["n"])


def test_theta_bound_catches_the_unmodulated_stub(vectors):
    # Must-fail: the Story 1.5 stub (a = 1, no envelope) misses the theta
    # bound on every 75 percent depth fixture.
    bound = theta_bound()
    misses = {r["fixture"] for r in vectors["theta_samples"] if r["case"] == "signal"
              and abs(Decimal(repr(engine_sine_value(int(r["phase_carrier"]))))
                      - Decimal(r["ideal_theta"])) > bound}
    assert misses == set(THETA_FIXTURE_NAMES)


def test_stub_chain_theta_is_the_depth_0_layer(vectors):
    # At depth 0 the theta layer is the unmodulated carrier bit for bit.
    gen = generator()
    rows = [r for r in vectors["stub_chain"] if r["case"] == "signal" and r["theta_carrier_hex"] != "none"]
    assert rows
    for r in rows:
        layer = gen.ThetaLayer(float.fromhex(r["theta_carrier_hex"]), float.fromhex(r["theta_rate_hex"]),
                               float.fromhex(r["theta_depth_hex"]), r["theta_shape"], r["fs"])
        assert bits_text(layer.engine_sample(int(r["n"]))) == r["theta_bits"], r


# ------------------------------------------------- gamma PAC layer (Story 2.2)
#
# Vectors file keys: `gamma_constants` (carrier_waves, modeled_carrier_waves,
# couplings), `gamma_envelopes` (depth_hex, phase, e_bits, a_bits, ideal_e,
# ideal_a), `gamma_samples` (case, fixture, fs, carrier_hex, rate_hex,
# depth_hex, length_hex, carrier_wave, coupling, theta_carrier_hex,
# theta_rate_hex, theta_depth_hex, theta_shape, inc_carrier, inc_rate,
# frames, n, phase_carrier, phase_rate, e_bits, a_bits, gamma_bits, ideal_e,
# ideal_gamma), and `gamma_bus` (case, fixture, fs, n, phase_theta,
# phase_theta_envelope, phase_gamma, phase_gamma_envelope, theta_bits,
# gamma_bits, bus_bits, ideal_theta, ideal_gamma, ideal_bus). The checks
# below re-derive every integer from the spec rules here, recompute the
# engine bits from the engine sine in the spec's operation order (signal
# spec, Gamma PAC layer, AM law), and hold each tap to its stated margin:
# the gamma tap 2 sines, |gamma - ideal| <= 1.5 * b + 2^-47; the bus with a
# theta reference 4 sines, within 3 * b + 2^-45.

GAMMA_CARRIER_WAVES = ("sine", "triangle", "softened_square")
GAMMA_MODELED_WAVES = ("sine",)
GAMMA_COUPLINGS = ("uncoupled",)
GAMMA_THETA_FIXTURE = "theta-gamma-uncoupled.json"
GAMMA_FIXTURE_NAMES = tuple(f"gamma-uncoupled-{rate}hz-{depth}pct.json"
                            for rate in (40, 60) for depth in (25, 100)) + (GAMMA_THETA_FIXTURE,)
QUARTER = 2**62


def gamma_engine_envelope(p):
    """c = sine(p + 2^62 mod 2^64), e = (1.0 + c) * 0.5, from the engine sine."""
    c = engine_sine_value((p + QUARTER) % CYCLE)
    return (1.0 + c) * 0.5


def gamma_amplitude(d, e):
    return 1.0 - d * (1.0 - e)


def gamma_envelope_bound():
    """|e - e_ideal| <= b / 2 + 2^-52 (signal spec, Gamma PAC layer, Error bound)."""
    return sine_bound_decimal() / 2 + Decimal(repr(2.0**-52))


def gamma_amplitude_bound(d):
    """|a - a_ideal| <= d * (b / 2 + 2^-52) + 2^-52."""
    return Decimal(repr(d)) * gamma_envelope_bound() + Decimal(repr(2.0**-52))


def gamma_bound():
    """Gamma tap, 2 sines: |gamma - gamma_ideal| <= 1.5 * b + 2^-47."""
    return Decimal("1.5") * sine_bound_decimal() + Decimal(repr(2.0**-47))


def gamma_bus_bound():
    """Bus with a theta reference, 4 sines: within 3 * b + 2^-45."""
    return 3 * sine_bound_decimal() + Decimal(repr(2.0**-45))


def exact(x):
    """The exact value of the binary64 x as a Decimal."""
    f = Fraction(x)
    return Decimal(f.numerator) / Decimal(f.denominator)


def test_gamma_constants(vectors):
    c = vectors["gamma_constants"]
    assert tuple(c["carrier_waves"]) == GAMMA_CARRIER_WAVES
    assert tuple(c["modeled_carrier_waves"]) == GAMMA_MODELED_WAVES
    assert tuple(c["couplings"]) == GAMMA_COUPLINGS
    gen = generator()
    assert tuple(gen.GAMMA_CARRIER_WAVES) == GAMMA_CARRIER_WAVES
    assert tuple(gen.GAMMA_MODELED_WAVES) == GAMMA_MODELED_WAVES
    assert tuple(gen.GAMMA_COUPLINGS) == GAMMA_COUPLINGS


def test_gamma_fixture_values_lie_in_the_locked_ranges_and_pass_the_carrier_rule(vectors):
    record_rows("gamma-rate", "gamma-carrier")
    rate = range_in("gamma-rate", "Hz")
    carrier = range_in("gamma-carrier", "Hz")
    depth = range_in("coupling-depth", "percent")
    ratio = table_row("carrier-rule").value
    for r in vectors["gamma_samples"]:
        f_rate = float.fromhex(r["rate_hex"])
        f_carrier = float.fromhex(r["carrier_hex"])
        assert rate.min <= f_rate <= rate.max, r["fixture"]
        assert carrier.min <= f_carrier <= carrier.max, r["fixture"]
        assert depth.min <= float.fromhex(r["depth_hex"]) <= depth.max, r["fixture"]
        assert f_carrier >= ratio * f_rate, r["fixture"]
    # Not every in-range pair passes the carrier rule (signal spec, Gamma PAC
    # layer, Recipe fields): the carrier floor is under 4 x the top rate.
    assert carrier.min < ratio * rate.max


def test_gamma_envelope_vectors(vectors):
    rows = vectors["gamma_envelopes"]
    depth = range_in("coupling-depth", "percent")
    gen = generator()
    depths = set()
    phases = set()
    with localcontext() as ctx:
        ctx.prec = 60
        for r in rows:
            p = int(r["phase"])
            depth_percent = float.fromhex(r["depth_hex"])
            d = depth_percent / 100.0
            depths.add(depth_percent)
            phases.add(p)
            e = bits_value(r["e_bits"])
            a = bits_value(r["a_bits"])
            where = (depth_percent, p)
            # Engine bits: recomputed here and by the generator.
            assert e == gamma_engine_envelope(p), where
            assert e == gen.gamma_envelope(p), where
            assert a == gamma_amplitude(d, e), where
            assert 0.0 < e < 1.0 and 0.0 < a <= 1.0, where
            # Within the stated margins of the ideal.
            assert abs(exact(e) - Decimal(r["ideal_e"])) <= gamma_envelope_bound(), where
            assert abs(exact(a) - Decimal(r["ideal_a"])) <= gamma_amplitude_bound(d), where
            # The ideal is the exact depth law on the binary64 d.
            ideal_a = 1 - exact(d) * (1 - Decimal(r["ideal_e"]))
            assert abs(ideal_a - Decimal(r["ideal_a"])) <= Decimal("1e-24"), where
            ideal_e = (1.0 + ideal().ideal_sine((p + QUARTER) % CYCLE)) / 2.0
            assert close_to_decimal(ideal_e, r["ideal_e"]), where
            if p == 0:
                assert Decimal(r["ideal_e"]) == 1 and Decimal(r["ideal_a"]) == 1, where
    assert {depth.min, depth.max} <= depths
    assert {0, QUARTER, HALF, 3 * QUARTER, CYCLE - 1} <= phases
    # The trough is never 0 in the engine (signal spec, Gamma PAC layer, Uncoupled).
    troughs = {r["e_bits"] for r in rows if int(r["phase"]) == HALF}
    assert len(troughs) == 1 and bits_value(troughs.pop()) > 0.0


def test_gamma_engine_envelope_stays_positive_and_within_bound():
    bound = float(gamma_envelope_bound())
    for k in range(4096):
        p = (k * 2**52 + 98765) % CYCLE
        e = gamma_engine_envelope(p)
        assert 0.0 < e <= 1.0, (p, e)
        signed = ((p + HALF) % CYCLE) - HALF
        ideal_e = 0.5 + 0.5 * math.cos(2.0 * math.pi * signed / CYCLE)
        assert abs(e - ideal_e) <= bound, p
    for p in (HALF - 1, HALF, HALF + 1):
        assert gamma_engine_envelope(p) > 0.0, p


def test_gamma_sample_rows_name_fixtures_with_their_values(vectors):
    rows = vectors["gamma_samples"]
    names = []
    for r in rows:
        if r["fixture"] not in names:
            names.append(r["fixture"])
    assert tuple(names) == GAMMA_FIXTURE_NAMES
    checked = set()
    for r in rows:
        assert r["carrier_wave"] == "sine" and r["coupling"] == "uncoupled", r["fixture"]
        if r["fixture"] in checked:
            continue
        checked.add(r["fixture"])
        path = FIXTURES_VALID / r["fixture"]
        assert path.is_file(), f"missing fixture {path}"
        recipe = json.loads(path.read_text(encoding="utf-8"))
        assert "binaural" not in recipe, r["fixture"]
        g = recipe["gamma_pac"]
        assert set(g) == {"carrier_hz", "rate_hz", "am_depth_percent", "carrier_wave", "coupling"}, r["fixture"]
        assert float(g["carrier_hz"]) == float.fromhex(r["carrier_hex"]) == 250.0, r["fixture"]
        assert float(g["rate_hz"]) == float.fromhex(r["rate_hex"]), r["fixture"]
        assert float(g["am_depth_percent"]) == float.fromhex(r["depth_hex"]), r["fixture"]
        assert g["carrier_wave"] == r["carrier_wave"] and g["coupling"] == r["coupling"], r["fixture"]
        assert float(recipe["length_s"]) == float.fromhex(r["length_hex"]) == 10.0, r["fixture"]
        if r["theta_carrier_hex"] == "none":
            assert "theta_reference" not in recipe, r["fixture"]
            assert r["theta_rate_hex"] == r["theta_depth_hex"] == r["theta_shape"] == "none", r
        else:
            theta = recipe["theta_reference"]
            assert float(theta["carrier_hz"]) == float.fromhex(r["theta_carrier_hex"]), r["fixture"]
            assert float(theta["rate_hz"]) == float.fromhex(r["theta_rate_hex"]), r["fixture"]
            assert float(theta["am_depth_percent"]) == float.fromhex(r["theta_depth_hex"]), r["fixture"]
            assert theta["shape"] == r["theta_shape"], r["fixture"]
    assert {(float.fromhex(r["rate_hex"]), float.fromhex(r["depth_hex"])) for r in rows} == {
        (40.0, 25.0), (40.0, 100.0), (60.0, 25.0), (60.0, 100.0)}
    for r in rows:
        assert int(r["frames"]) == round(Fraction(float.fromhex(r["length_hex"])) * r["fs"]), r


def test_gamma_sample_rows_follow_the_rules(vectors):
    cases = set()
    by_key = {}
    for r in vectors["gamma_samples"]:
        fs = r["fs"]
        assert int(r["inc_carrier"]) == spec_increment(float.fromhex(r["carrier_hex"]), fs), r
        assert int(r["inc_rate"]) == spec_increment(float.fromhex(r["rate_hex"]), fs), r
        n = int(r["n"])
        assert int(r["phase_carrier"]) == n * int(r["inc_carrier"]) % CYCLE, r
        assert int(r["phase_rate"]) == n * int(r["inc_rate"]) % CYCLE, r
        past = n >= int(r["frames"])
        assert r["case"] == ("past_end" if past else "signal"), r
        cases.add((r["fixture"], fs, r["case"]))
        by_key.setdefault((r["fixture"], fs), set()).add(n)
        if past:
            assert r["gamma_bits"] == r["e_bits"] == r["a_bits"] == "0x0000000000000000", r
            assert r["ideal_gamma"] == "0", r
    for name in GAMMA_FIXTURE_NAMES:
        for fs in listed_sample_rates():
            assert (name, fs, "signal") in cases and (name, fs, "past_end") in cases, (name, fs)
    # Indices: the start, both sides of the first two block boundaries, 1000,
    # both sides of the quarter, half, and three-quarter points of the first
    # gamma envelope cycle, the last sample, and two past the end.
    for r in vectors["gamma_samples"]:
        indices = by_key[(r["fixture"], r["fs"])]
        frames = int(r["frames"])
        inc = int(r["inc_rate"])
        want = {0, 63, 64, 65, 127, 128, 1000, frames - 1, frames, frames + 63}
        for b in (QUARTER, HALF, 3 * QUARTER):
            k = -(-b // inc)
            want.update((k - 1, k))
        assert want <= indices, (r["fixture"], r["fs"], sorted(want - indices))


def test_gamma_sample_bits_follow_the_am_law_and_bound(vectors):
    with localcontext() as ctx:
        ctx.prec = 60
        for r in vectors["gamma_samples"]:
            if r["case"] != "signal":
                continue
            where = (r["fixture"], r["fs"], r["n"])
            e = bits_value(r["e_bits"])
            assert e == gamma_engine_envelope(int(r["phase_rate"])), where
            d = float.fromhex(r["depth_hex"]) / 100.0
            a = gamma_amplitude(d, e)
            assert a == bits_value(r["a_bits"]), where
            g = bits_value(r["gamma_bits"])
            assert g == a * engine_sine_value(int(r["phase_carrier"])), where
            assert r["gamma_bits"] != "0x8000000000000000", where  # never -0.0
            assert e > 0.0 and a > 0.0, where
            assert abs(exact(e) - Decimal(r["ideal_e"])) <= gamma_envelope_bound(), where
            assert abs(exact(g) - Decimal(r["ideal_gamma"])) <= gamma_bound(), where


def test_gamma_sample_bits_match_the_generator_layer(vectors):
    gen = generator()
    layers = {}
    for r in vectors["gamma_samples"]:
        if r["case"] != "signal":
            continue
        key = (r["fixture"], r["fs"])
        if key not in layers:
            layers[key] = gen.GammaLayer(float.fromhex(r["carrier_hex"]), float.fromhex(r["rate_hex"]),
                                         float.fromhex(r["depth_hex"]), r["fs"])
        e, a, g = layers[key].engine_parts(int(r["n"]))
        assert (bits_text(e), bits_text(a), bits_text(g)) == (r["e_bits"], r["a_bits"], r["gamma_bits"]), key


def test_gamma_sample_ideal_matches_the_reference_ideal_sine(vectors):
    mod = ideal()
    for r in vectors["gamma_samples"]:
        if r["case"] != "signal":
            continue
        d = float.fromhex(r["depth_hex"]) / 100.0
        a = 1.0 - d * (1.0 - float(Decimal(r["ideal_e"])))
        value = a * mod.ideal_sine(int(r["phase_carrier"]))
        assert close_to_decimal(value, r["ideal_gamma"]), (r["fixture"], r["fs"], r["n"])


def test_gamma_bound_catches_the_unmodulated_stub_and_the_zero_stub(vectors):
    # Must-fail: an unmodulated carrier (a = 1) and the Story 1.2 stub
    # (gamma = 0) each miss the gamma bound on every fixture.
    bound = gamma_bound()
    rows = [r for r in vectors["gamma_samples"] if r["case"] == "signal"]
    unmodulated = {r["fixture"] for r in rows
                   if abs(Decimal(repr(engine_sine_value(int(r["phase_carrier"]))))
                          - Decimal(r["ideal_gamma"])) > bound}
    zero = {r["fixture"] for r in rows if abs(Decimal(r["ideal_gamma"])) > bound}
    assert unmodulated == set(GAMMA_FIXTURE_NAMES)
    assert zero == set(GAMMA_FIXTURE_NAMES)


def theta_gamma_recipe():
    path = FIXTURES_VALID / GAMMA_THETA_FIXTURE
    assert path.is_file(), f"missing fixture {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_gamma_bus_rows_follow_the_rules(vectors):
    rows = vectors["gamma_bus"]
    assert {r["fixture"] for r in rows} == {GAMMA_THETA_FIXTURE}
    recipe = theta_gamma_recipe()
    theta, g = recipe["theta_reference"], recipe["gamma_pac"]
    cases = set()
    for r in rows:
        fs = r["fs"]
        n = int(r["n"])
        inc = {key: spec_increment(float(value), fs) for key, value in (
            ("theta", theta["carrier_hz"]), ("theta_envelope", theta["rate_hz"]),
            ("gamma", g["carrier_hz"]), ("gamma_envelope", g["rate_hz"]))}
        for key, step in inc.items():
            assert int(r[f"phase_{key}"]) == n * step % CYCLE, (key, r)
        frames = round(Fraction(float(recipe["length_s"])) * fs)
        assert r["case"] == ("past_end" if n >= frames else "signal"), r
        cases.add((fs, r["case"]))
    for fs in listed_sample_rates():
        assert (fs, "signal") in cases and (fs, "past_end") in cases, fs


def test_gamma_bus_bits_are_the_one_rounding_sum_within_the_bus_bound(vectors):
    gen = generator()
    rows = [r for r in vectors["gamma_samples"] if r["fixture"] == GAMMA_THETA_FIXTURE]
    assert rows
    first = {r["fs"]: r for r in rows}
    by_n = {(r["fs"], r["n"]): r for r in rows}
    with localcontext() as ctx:
        ctx.prec = 60
        for r in vectors["gamma_bus"]:
            where = (r["fs"], r["n"])
            t = bits_value(r["theta_bits"])
            g = bits_value(r["gamma_bits"])
            bus = bits_value(r["bus_bits"])
            if r["case"] == "past_end":
                assert r["theta_bits"] == r["gamma_bits"] == r["bus_bits"] == "0x0000000000000000", where
                continue
            assert bus == t + g, where  # stereo bus: one binary64 addition
            s = first[r["fs"]]
            layer = gen.ThetaLayer(float.fromhex(s["theta_carrier_hex"]), float.fromhex(s["theta_rate_hex"]),
                                   float.fromhex(s["theta_depth_hex"]), s["theta_shape"], r["fs"])
            assert bits_text(layer.engine_sample(int(r["n"]))) == r["theta_bits"], where
            d = float.fromhex(s["depth_hex"]) / 100.0
            e = gamma_engine_envelope(int(r["phase_gamma_envelope"]))
            assert g == gamma_amplitude(d, e) * engine_sine_value(int(r["phase_gamma"])), where
            if where in by_n:
                assert by_n[where]["gamma_bits"] == r["gamma_bits"], where
            assert abs(exact(g) - Decimal(r["ideal_gamma"])) <= gamma_bound(), where
            assert abs(exact(t) - Decimal(r["ideal_theta"])) <= theta_bound(), where
            assert abs(exact(bus) - Decimal(r["ideal_bus"])) <= gamma_bus_bound(), where
            total = Decimal(r["ideal_theta"]) + Decimal(r["ideal_gamma"])
            assert abs(total - Decimal(r["ideal_bus"])) <= Decimal("1e-24"), where


def test_gamma_bus_bound_catches_a_bus_without_gamma(vectors):
    # Must-fail: the theta tap alone (gamma left at +0.0) misses the bus bound.
    bound = gamma_bus_bound()
    misses = [r for r in vectors["gamma_bus"] if r["case"] == "signal"
              and abs(Decimal(repr(bits_value(r["theta_bits"]))) - Decimal(r["ideal_bus"])) > bound]
    assert misses


def test_no_stub_chain_or_theta_fixture_has_a_gamma_layer(vectors):
    # Their bytes stay unchanged (signal spec, Stub chain: gamma is +0.0).
    names = {r["fixture"] for r in vectors["stub_chain"]} | {r["fixture"] for r in vectors["theta_samples"]}
    for name in names:
        recipe = json.loads((FIXTURES_VALID / name).read_text(encoding="utf-8"))
        assert "gamma_pac" not in recipe, name
