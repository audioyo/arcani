"""Signal spec core, sine, internal blocks, and stub chain: vectors, spec tables, Python ideal, quantization and drift.

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
from decimal import Decimal
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
    # Core and sine (7), internal blocks (1), stub chain increments and samples (2).
    assert len(generated) == 10, generated
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
    for r in rows:
        path = FIXTURES_VALID / r["fixture"]
        assert path.is_file(), f"missing fixture {path}"
        recipe = json.loads(path.read_text(encoding="utf-8"))
        assert float(recipe["binaural"]["carrier_left_hz"]) == float.fromhex(r["carrier_left_hex"]), r
        assert float(recipe["binaural"]["beat_rate_hz"]) == float.fromhex(r["beat_rate_hex"]), r
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
        n = int(r["n"])
        assert int(r["phase_left"]) == n * int(r["inc_left"]) % CYCLE, r
        assert int(r["phase_right"]) == n * int(r["inc_right"]) % CYCLE, r
        assert r["case"] == ("past_end" if n >= int(r["frames"]) else "signal"), r
        cases.add((r["fixture"], fs, r["case"]))
    for fixture in ("stub-chain-1s-beat-0.json", "stub-chain-1s-beat-6.json"):
        for fs in listed_sample_rates():
            assert (fixture, fs, "signal") in cases and (fixture, fs, "past_end") in cases


def test_stub_chain_bits_are_within_the_sine_bound_of_the_ideal(vectors):
    bound = 10.0 ** (sine_bound_dbfs() / 20.0)
    for r in vectors["stub_chain"]:
        for side in ("left", "right"):
            got = bits_value(r[f"{side}_bits"])
            if r["case"] == "past_end":
                assert r[f"{side}_bits"] == "0x0000000000000000", r
                continue
            assert abs(Decimal(repr(got)) - Decimal(r[f"ideal_{side}"])) <= Decimal(repr(bound)), (
                r["fixture"], r["fs"], r["n"], side)


def test_stub_chain_doctored_bits_fail_the_bound(vectors):
    bound = 10.0 ** (sine_bound_dbfs() / 20.0)
    r = next(v for v in vectors["stub_chain"] if v["case"] == "signal" and v["n"] == "37")
    got = bits_value(r["left_bits"]) + 1e-5
    assert abs(Decimal(repr(got)) - Decimal(r["ideal_left"])) > Decimal(repr(bound))


def test_stub_chain_ideal_matches_the_reference_ideal_sine(vectors):
    mod = ideal()
    for r in vectors["stub_chain"]:
        if r["case"] != "signal":
            continue
        for side in ("left", "right"):
            assert close_to_decimal(mod.ideal_sine(int(r[f"phase_{side}"])), r[f"ideal_{side}"]), (
                r["fixture"], r["fs"], r["n"], side)
