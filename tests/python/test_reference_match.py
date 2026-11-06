"""Python reference renderer of the stub chain and the reference match (Story 1.5, AD-16).

The reference (`reference/stub_chain.py`) renders a recipe from the signal
spec only (docs/signal-spec.md, Core, Sine, Stub chain), in binary64, with
the ideal sine of reference/ideal.py. The reference match assertion
(`tests/assertions/reference_match.py`) compares the engine's
pre-quantization output and taps with it sample by sample, per signal and
per channel. Thresholds come from tests/tables/thresholds.tsv through the
assertion call `assertions.row`; no threshold is written here as a literal.

Contract with reference/stub_chain.py (standard library, NumPy, and
reference/ only; imported as `reference.stub_chain` with the repo root on
sys.path, so it may import `from reference import ideal` or `from . import
ideal`):

- `render(recipe_path, fs, frames=None) -> dict[str, numpy.ndarray]`.
  `recipe_path` is a str or os.PathLike naming a recipe JSON file, read with
  the standard library `json` module; `fs` is 44100 or 48000. The dict has
  exactly the keys "output", "theta", "gamma", "bus", "join", "master". Each
  value is a 1-D C-contiguous float64 array of 2 * T samples, interleaved
  stereo (left, right per frame), where T = `frames` when given (any int
  >= 0) and else N = ideal.seconds_to_samples(length_s, fs). Every sample at
  frame n >= N is +0.0 in every array.
- For 0 <= n < N, per the signal spec (Stub chain, Per sample), in binary64:
  inc_T = ideal.phase_increment(theta_reference.carrier_hz, fs) and a_T = 1.0
  when the recipe has `theta_reference`, else inc_T = 0 and a_T = 0.0;
  f_R = carrier_left_hz + beat_rate_hz (one binary64 addition); inc_c =
  ideal.phase_increment(f_c, fs) and a_c = 1.0 when the recipe has
  `binaural`, else 0 and 0.0; phase[n] = n * inc mod 2^64 (uint64
  wraparound); theta = a_T * ideal.ideal_sine(phase_T) (the same value in
  both channels); gamma = +0.0; bus = theta + gamma; bin_c = a_c *
  ideal.ideal_sine(phase_c); join = bus + bin_c; master = join * 1.0;
  output = master. So theta and bus agree bit for bit, and join, master,
  and output agree bit for bit.
- It renders the ideal sine, never the engine polynomial, and reads no
  engine code, engine binary, or engine output (test_reference_independent.py).

Contract with tests/assertions/reference_match.py (imported as
`assertions.reference_match`; NumPy and the standard library):

- `level_dbfs(x) -> float`: 20 * log10(max |x|) over a 1-D array; -inf when
  every sample is zero or the array is empty.
- `difference_dbfs(engine, reference) -> float`: 20 * log10(max |engine -
  reference|) in binary64; -inf when every difference is zero. Arrays of
  different shapes raise ValueError.
- `match(name, engine, reference) -> dict`: one channel, two 1-D float64
  arrays of the same length. Reads rows `reference-match` and
  `reference-match-min-level` through `assertions.row` on every call.
  Returns the Story 1.4 report assertion shape: {"name": name, "row":
  "reference-match", "threshold": <row reference-match value>, "unit": <its
  unit>, "measured": float or None, "result": "pass" or "fail", "note":
  str}. In this order:
  1. a NaN or infinite sample on either side: "fail", note "not finite",
     measured None;
  2. level_dbfs of either side below (strictly) row
     `reference-match-min-level`: "fail", note "silent", measured the
     difference_dbfs (None when it is -inf);
  3. difference_dbfs is -inf: "pass", note "exact", measured None;
  4. otherwise measured = difference_dbfs, "pass" when measured < threshold
     (strictly), else "fail"; note "".
- `match_stereo(signal, engine, reference) -> list[dict]`: interleaved
  stereo arrays of the same even length; returns [match(f"reference match
  {signal} left", ...), match(f"reference match {signal} right", ...)] in
  that order. Odd or different lengths raise ValueError.
- `all_positive_zero(x) -> bool`: True when every sample's bit pattern is
  that of +0.0 (so -0.0 and the smallest subnormal are False); True for an
  empty array.

Contract with the test-only engine dump (tests/tapdump/, target
arcani-tapdump, built here with the platform preset's own build directory:
`cmake --build --preset <preset> --target arcani-tapdump`, on Windows through
tools/dev.ps1; binary at build/<preset>/tests/tapdump/arcani-tapdump[.exe]):

- `arcani-tapdump RECIPE RATE OUT_DIR [EXTRA_FRAMES]` compiles RECIPE in
  measure mode at RATE, renders N + EXTRA_FRAMES frames in one call with
  every tap, writes OUT_DIR/{out,theta,gamma,bus,join,master}.f64 (raw
  little-endian binary64, interleaved stereo), prints
  "arcani-tapdump: frames N total T" and exits 0.

Signals compared with the reference match: output, theta, bus, join, master,
over the N session frames, at 44.1 and 48 kHz, for stub-chain-1s-beat-6.json
and stub-chain-1s-beat-0.json. A signal the spec makes all +0.0 (gamma
always; theta and bus without `theta_reference`, so for beat-0) gets the
exact-zero check on both sides instead, since a reference match of zeros
fails as silent. Past the session end (64 extra frames) every array is +0.0
on both sides.

Must-fail cases (doctored here, in the harness): the match measure is
calibrated on synthesized pairs with known errors at row reference-match
-10, -0.5, +0.5, and +10 dB (with the table's -100 dBFS: -110, -100.5,
-99.5, -90 dBFS), each read within 0.1 dB; an engine output with an error
10 dB above the row at one sample fails and reads within 0.1 dB of it; both
sides scaled 10 dB below row reference-match-min-level fail as silent; an
engine side of zeros against a real reference fails as silent; one nonzero
sample in a spec-zero tap fails the exact-zero check.

The dump test skips only when cmake is not on PATH, or when Windows
application control blocks the binary (OSError winerror 4551 or 1260).
"""

import importlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from assertions import row as table_row

REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS = REPO_ROOT / "tests" / "data" / "signal_spec_vectors.json"
FIXTURES_VALID = REPO_ROOT / "recipes" / "fixtures" / "valid"
STUB_CHAIN = REPO_ROOT / "reference" / "stub_chain.py"
MATCH_MODULE = REPO_ROOT / "tests" / "assertions" / "reference_match.py"
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
EXE_NAME = "arcani-tapdump.exe" if sys.platform == "win32" else "arcani-tapdump"
TAPDUMP = REPO_ROOT / "build" / PRESET / "tests" / "tapdump" / EXE_NAME

BEAT_0 = "stub-chain-1s-beat-0.json"
BEAT_6 = "stub-chain-1s-beat-6.json"
FIXTURES = (BEAT_0, BEAT_6)
RATES = (44100, 48000)
KEYS = ("output", "theta", "gamma", "bus", "join", "master")
DUMP_FILES = {"output": "out", "theta": "theta", "gamma": "gamma", "bus": "bus", "join": "join",
              "master": "master"}
MATCHED = ("output", "theta", "bus", "join", "master")
EXTRA_FRAMES = 64
CYCLE = 2**64

# Acceptance criteria: the reference at a vector row is within 1e-15 of the
# vector's ideal value (25 digits), and the calibration reads each known
# error within 0.1 dB. Calibration offsets from row reference-match, in dB.
IDEAL_TOL = Decimal("1e-15")
CALIBRATION_TOLERANCE_DB = 0.1
CALIBRATION_OFFSETS_DB = (-10.0, -0.5, 0.5, 10.0)
CALIBRATION_VERDICTS = ("pass", "pass", "fail", "fail")
DOCTOR_OFFSET_DB = 10.0  # the doctored and silent must-fail cases sit 10 dB past their row


# ------------------------------------------------------------- loading


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def stub_chain():
    """reference.stub_chain; a missing module fails the calling test."""
    assert STUB_CHAIN.is_file(), f"missing {STUB_CHAIN} (Story 1.5 reference renderer)"
    _repo_on_path()
    return importlib.import_module("reference.stub_chain")


def ideal():
    _repo_on_path()
    return importlib.import_module("reference.ideal")


def rm():
    """assertions.reference_match; a missing module fails the calling test."""
    assert MATCH_MODULE.is_file(), f"missing {MATCH_MODULE} (Story 1.5 reference match assertion)"
    return importlib.import_module("assertions.reference_match")


def match_row():
    row = table_row("reference-match")
    assert row.unit == "dBFS", row
    return row


def min_level_row():
    row = table_row("reference-match-min-level")
    assert row.unit == "dBFS", row
    return row


def amplitude(dbfs):
    return 10.0 ** (dbfs / 20.0)


def bits(x):
    return struct.unpack("<Q", struct.pack("<d", float(x)))[0]


def bits_value(text):
    return struct.unpack(">d", bytes.fromhex(text[2:]))[0]


def channel(stereo, c):
    return np.ascontiguousarray(np.asarray(stereo)[c::2])


@pytest.fixture(scope="module")
def vectors():
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def fixture_frames(vectors, fixture, fs):
    rows = [r for r in vectors["stub_chain"] if r["fixture"] == fixture and r["fs"] == fs]
    assert rows, (fixture, fs)
    return int(rows[0]["frames"]), rows[0]["theta_carrier_hex"] != "none"


# ---------------------------------------------------------- calibration


def synth_reference(fs=48000):
    """A 400 Hz unmodulated sine at 0.5 peak, 1 s (test signal only)."""
    n = np.arange(fs, dtype=np.float64)
    return 0.5 * np.sin(2.0 * math.pi * 400.0 * n / fs)


def test_rows_are_dbfs_and_the_minimum_level_sits_above_the_match_line():
    # A signal at the minimum level can still show an error at the match
    # line; the rows' relation, not their values, is checked here.
    assert min_level_row().value > match_row().value


def test_calibration_reads_each_known_error_within_tolerance():
    mod = rm()
    threshold = match_row().value
    reference = synth_reference()
    verdicts = []
    for offset in CALIBRATION_OFFSETS_DB:
        level = threshold + offset
        # One-sample error, and an error spread as a 1234 Hz sine.
        spike = reference.copy()
        spike[12345] += amplitude(level)
        n = np.arange(reference.size, dtype=np.float64)
        spread = reference + amplitude(level) * np.sin(2.0 * math.pi * 1234.0 * n / 48000.0)
        for engine in (spike, spread):
            measured = mod.difference_dbfs(engine, reference)
            assert abs(measured - level) <= CALIBRATION_TOLERANCE_DB, (offset, measured, level)
        result = mod.match("calibration", spike, reference)
        assert result["row"] == "reference-match"
        assert result["threshold"] == threshold
        assert result["unit"] == "dBFS"
        assert result["note"] == ""
        assert abs(result["measured"] - level) <= CALIBRATION_TOLERANCE_DB
        verdicts.append(result["result"])
    assert tuple(verdicts) == CALIBRATION_VERDICTS


def test_calibration_levels_are_the_spec_levels():
    # With the table's reference-match row the offsets give the levels the
    # spec names (-110, -100.5, -99.5, -90 dBFS); computed, never copied.
    threshold = match_row().value
    levels = [threshold + o for o in CALIBRATION_OFFSETS_DB]
    assert levels[1] < threshold < levels[2]
    assert levels[0] < levels[1] and levels[2] < levels[3]


def naive_rms_dbfs(engine, reference):
    d = np.asarray(engine) - np.asarray(reference)
    return 20.0 * math.log10(float(np.sqrt(np.mean(d * d))))


def test_calibration_catches_a_wrong_measure():
    # Must-fail for the calibration: an RMS measure reads a one-sample error
    # far below its peak, outside the tolerance.
    reference = synth_reference()
    level = match_row().value + 10.0
    engine = reference.copy()
    engine[100] += amplitude(level)
    assert abs(naive_rms_dbfs(engine, reference) - level) > CALIBRATION_TOLERANCE_DB


def test_exact_match_passes_with_null_measured():
    mod = rm()
    reference = synth_reference()
    result = mod.match("exact", reference.copy(), reference)
    assert result["result"] == "pass"
    assert result["measured"] is None
    assert result["note"] == "exact"
    assert mod.difference_dbfs(reference, reference) == -math.inf


def test_pass_is_strictly_below_the_threshold():
    mod = rm()
    threshold = match_row().value
    reference = synth_reference()
    k = 0  # sin(0) = 0, so the difference at k is exactly e
    assert reference[k] == 0.0
    e = amplitude(threshold)
    candidates = [e]
    for _ in range(4):
        candidates.append(math.nextafter(candidates[-1], 1.0))
    exact = next((c for c in candidates if 20.0 * math.log10(c) == threshold), None)
    for c in candidates:
        engine = reference.copy()
        engine[k] = c
        result = mod.match("boundary", engine, reference)
        assert (result["result"] == "pass") == (result["measured"] < threshold), result
    if exact is not None:
        engine = reference.copy()
        engine[k] = exact
        assert mod.match("at threshold", engine, reference)["result"] == "fail"


def test_level_dbfs():
    mod = rm()
    assert mod.level_dbfs(np.zeros(16)) == -math.inf
    assert mod.level_dbfs(np.zeros(0)) == -math.inf
    x = np.zeros(16)
    x[5] = -0.5
    assert abs(mod.level_dbfs(x) - 20.0 * math.log10(0.5)) < 1e-12


def test_silent_both_sides_scaled_below_the_minimum_level_fails():
    mod = rm()
    floor = min_level_row().value
    reference = synth_reference()
    scale = amplitude(floor - DOCTOR_OFFSET_DB - mod.level_dbfs(reference))
    quiet = reference * scale
    result = mod.match("scaled", quiet.copy(), quiet)
    assert result["result"] == "fail"
    assert result["note"] == "silent"


def test_minimum_level_boundary():
    mod = rm()
    floor = min_level_row().value
    reference = synth_reference()
    peak = mod.level_dbfs(reference)
    above = reference * amplitude(floor + 0.1 - peak)
    below = reference * amplitude(floor - 0.1 - peak)
    assert mod.match("above", above.copy(), above)["note"] == "exact"
    assert mod.match("above", above.copy(), above)["result"] == "pass"
    assert mod.match("below", below.copy(), below)["note"] == "silent"
    assert mod.match("below", below.copy(), below)["result"] == "fail"


def test_one_side_silent_fails():
    mod = rm()
    reference = synth_reference()
    for engine, ref in ((np.zeros_like(reference), reference), (reference, np.zeros_like(reference))):
        result = mod.match("one side", engine, ref)
        assert result["result"] == "fail"
        assert result["note"] == "silent"
    both = mod.match("both", np.zeros(64), np.zeros(64))
    assert both["result"] == "fail" and both["note"] == "silent"


def test_not_finite_fails():
    mod = rm()
    reference = synth_reference()
    for bad in (math.nan, math.inf, -math.inf):
        engine = reference.copy()
        engine[7] = bad
        result = mod.match("bad", engine, reference)
        assert result["result"] == "fail", bad
        assert result["note"] == "not finite", bad
        assert result["measured"] is None
        flipped = mod.match("bad", reference, engine)
        assert flipped["result"] == "fail" and flipped["note"] == "not finite"


def test_shape_mismatch_raises():
    mod = rm()
    with pytest.raises(ValueError):
        mod.difference_dbfs(np.zeros(4), np.zeros(5))
    with pytest.raises(ValueError):
        mod.match_stereo("odd", np.zeros(5), np.zeros(5))
    with pytest.raises(ValueError):
        mod.match_stereo("lengths", np.zeros(4), np.zeros(6))


def test_match_stereo_judges_each_channel():
    mod = rm()
    threshold = match_row().value
    mono = synth_reference()
    stereo = np.empty(2 * mono.size)
    stereo[0::2] = mono
    stereo[1::2] = -mono
    engine = stereo.copy()
    engine[2 * 300] += amplitude(threshold + DOCTOR_OFFSET_DB)  # left channel only
    left, right = mod.match_stereo("output", engine, stereo)
    assert left["name"] == "reference match output left"
    assert right["name"] == "reference match output right"
    assert left["result"] == "fail"
    assert right["result"] == "pass" and right["note"] == "exact"


def test_all_positive_zero():
    mod = rm()
    assert mod.all_positive_zero(np.zeros(8))
    assert mod.all_positive_zero(np.zeros(0))
    x = np.zeros(8)
    x[3] = -0.0
    assert not mod.all_positive_zero(x)
    x[3] = 5e-324
    assert not mod.all_positive_zero(x)


# ------------------------------------------------- reference vs vectors


def close(value, text):
    return abs(Decimal(repr(float(value))) - Decimal(text)) <= IDEAL_TOL


@pytest.fixture(scope="module")
def reference_renders(vectors):
    """reference.stub_chain renders of both fixtures at both rates, plus 64
    frames past the end."""
    sc = stub_chain()
    out = {}
    for fixture in FIXTURES:
        for fs in RATES:
            frames, _ = fixture_frames(vectors, fixture, fs)
            out[(fixture, fs)] = sc.render(FIXTURES_VALID / fixture, fs, frames=frames + EXTRA_FRAMES)
    return out


def test_reference_returns_the_contract_shape(vectors, reference_renders):
    for (fixture, fs), r in reference_renders.items():
        frames, _ = fixture_frames(vectors, fixture, fs)
        assert set(r) == set(KEYS), (fixture, fs, sorted(r))
        for key in KEYS:
            a = r[key]
            assert isinstance(a, np.ndarray) and a.dtype == np.float64 and a.ndim == 1, (fixture, fs, key)
            assert a.flags["C_CONTIGUOUS"], (fixture, fs, key)
            assert a.size == 2 * (frames + EXTRA_FRAMES), (fixture, fs, key)


def test_reference_default_length_is_the_session(vectors):
    sc = stub_chain()
    for fs in RATES:
        frames, _ = fixture_frames(vectors, BEAT_6, fs)
        r = sc.render(str(FIXTURES_VALID / BEAT_6), fs)
        assert all(r[k].size == 2 * frames for k in KEYS)


def test_reference_is_within_1e_15_of_every_vector_ideal(vectors, reference_renders):
    for v in vectors["stub_chain"]:
        r = reference_renders[(v["fixture"], v["fs"])]
        n = int(v["n"])
        where = (v["fixture"], v["fs"], n)
        if v["case"] == "past_end":
            for key in KEYS:
                assert bits(r[key][2 * n]) == 0 and bits(r[key][2 * n + 1]) == 0, (where, key)
            continue
        for c, side in ((0, "left"), (1, "right")):
            assert close(r["output"][2 * n + c], v[f"ideal_{side}"]), (where, side)
            assert close(r["theta"][2 * n + c], v["ideal_theta"]), (where, side, "theta")


def test_vector_check_catches_the_engine_sine_and_a_zero_theta(vectors):
    # Must-fail for the 1e-15 check: the engine bits (polynomial sine) miss
    # the ideal on some row, and a theta left at zeros misses every beat-6
    # signal row where the ideal theta is not tiny.
    engine_misses = [v for v in vectors["stub_chain"] if v["case"] == "signal"
                     and not close(bits_value(v["left_bits"]), v["ideal_left"])]
    assert engine_misses
    zero_theta_misses = [v for v in vectors["stub_chain"] if v["case"] == "signal"
                         and v["theta_carrier_hex"] != "none" and not close(0.0, v["ideal_theta"])]
    assert zero_theta_misses


def test_reference_follows_the_spec_operations(vectors, reference_renders):
    # The spec's per-sample lines in binary64, with ideal.py's increment rule
    # and ideal sine: bus = theta + gamma, join = bus + bin, master = join,
    # output = master, bit for bit; theta the same in both channels; gamma
    # +0.0; zeros past the end.
    idl = ideal()
    for (fixture, fs), r in reference_renders.items():
        recipe = json.loads((FIXTURES_VALID / fixture).read_text(encoding="utf-8"))
        frames, has_theta = fixture_frames(vectors, fixture, fs)
        n = np.arange(frames, dtype=np.uint64)
        if has_theta:
            inc_t = np.uint64(idl.phase_increment(float(recipe["theta_reference"]["carrier_hz"]), fs))
            theta = 1.0 * idl.ideal_sine(n * inc_t)
        else:
            theta = np.zeros(frames)
        left_hz = float(recipe["binaural"]["carrier_left_hz"])
        right_hz = left_hz + float(recipe["binaural"]["beat_rate_hz"])
        where = (fixture, fs)
        for c, f_hz in ((0, left_hz), (1, right_hz)):
            inc = np.uint64(idl.phase_increment(f_hz, fs))
            binaural = 1.0 * idl.ideal_sine(n * inc)
            bus = theta + 0.0
            join = bus + binaural
            got = {key: channel(r[key], c) for key in KEYS}
            assert np.array_equal(got["theta"][:frames].view(np.uint64), theta.view(np.uint64)), where
            assert np.array_equal(got["bus"][:frames].view(np.uint64), bus.view(np.uint64)), where
            assert np.array_equal(got["join"][:frames].view(np.uint64), join.view(np.uint64)), where
            for key in ("master", "output"):
                assert np.array_equal(got[key].view(np.uint64), got["join"].view(np.uint64)), (where, key)
            assert not got["gamma"].view(np.uint64).any(), where
            for key in KEYS:
                assert not got[key][frames:].view(np.uint64).any(), (where, key, "past end")


def test_reference_reads_the_recipe_json(tmp_path, vectors):
    # A changed theta carrier changes the theta tap; no theta_reference field
    # gives a theta tap of zeros and an output that is the binaural sine.
    sc = stub_chain()
    idl = ideal()
    base = json.loads((FIXTURES_VALID / BEAT_6).read_text(encoding="utf-8"))
    changed = dict(base, theta_reference={"carrier_hz": 250})
    path = tmp_path / "theta-250.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    r = sc.render(path, 48000)
    frames = r["theta"].size // 2
    inc = np.uint64(idl.phase_increment(250.0, 48000))
    want = idl.ideal_sine(np.arange(frames, dtype=np.uint64) * inc)
    assert np.array_equal(channel(r["theta"], 0), want)
    without = {k: v for k, v in base.items() if k != "theta_reference"}
    path2 = tmp_path / "no-theta.json"
    path2.write_text(json.dumps(without), encoding="utf-8")
    r2 = sc.render(path2, 48000)
    assert not r2["theta"].view(np.uint64).any()
    assert np.array_equal(r2["output"], r2["join"])
    longer = dict(base, length_s=0.5)
    path3 = tmp_path / "half.json"
    path3.write_text(json.dumps(longer), encoding="utf-8")
    assert sc.render(path3, 44100)["output"].size == 2 * idl.seconds_to_samples(0.5, 44100)


# ------------------------------------------------- engine vs reference


def cmake_command(args):
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-File", str(REPO_ROOT / "tools" / "dev.ps1"), "cmake", *args]
    return [CMAKE, *args]


@pytest.fixture(scope="module")
def tapdump():
    """Builds arcani-tapdump in the preset's build directory; returns its path."""
    if CMAKE is None:
        pytest.skip("cmake is not on PATH")
    result = subprocess.run(cmake_command(["--build", "--preset", PRESET, "--target", "arcani-tapdump"]),
                            cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
                            env=os.environ.copy())
    assert result.returncode == 0, (
        f"building arcani-tapdump failed (configure the {PRESET} preset first, e.g. with the cmake "
        f"workflow):\n{result.stdout}{result.stderr}")
    assert TAPDUMP.is_file(), f"dump binary not at {TAPDUMP}"
    return TAPDUMP


def run_dump(exe, recipe, fs, out_dir, extra):
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run([str(exe), str(recipe), str(fs), str(out_dir), str(extra)],
                                capture_output=True, text=True, timeout=300)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the dump (winerror {e.winerror})")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.fixture(scope="module")
def engine_dumps(tapdump, tmp_path_factory, vectors):
    out = {}
    root = tmp_path_factory.mktemp("tapdump")
    for fixture in FIXTURES:
        for fs in RATES:
            frames, _ = fixture_frames(vectors, fixture, fs)
            d = root / f"{fixture}-{fs}"
            stdout = run_dump(tapdump, FIXTURES_VALID / fixture, fs, d, EXTRA_FRAMES)
            assert f"frames {frames} total {frames + EXTRA_FRAMES}" in stdout, stdout
            arrays = {}
            for key, name in DUMP_FILES.items():
                a = np.fromfile(d / f"{name}.f64", dtype="<f8").astype(np.float64)
                assert a.size == 2 * (frames + EXTRA_FRAMES), (fixture, fs, key, a.size)
                arrays[key] = a
            out[(fixture, fs)] = arrays
    return out


def spec_zero_keys(has_theta):
    return ("gamma",) if has_theta else ("gamma", "theta", "bus")


@pytest.mark.parametrize("fixture", FIXTURES)
@pytest.mark.parametrize("fs", RATES)
def test_engine_matches_the_reference(fixture, fs, vectors, engine_dumps, reference_renders):
    mod = rm()
    frames, has_theta = fixture_frames(vectors, fixture, fs)
    eng = engine_dumps[(fixture, fs)]
    ref = reference_renders[(fixture, fs)]
    zero = spec_zero_keys(has_theta)
    results = []
    for key in MATCHED:
        if key in zero:
            continue
        results += mod.match_stereo(key, eng[key][:2 * frames], ref[key][:2 * frames])
    names = [r["name"] for r in results]
    want = [f"reference match {k} {side}" for k in MATCHED if k not in zero for side in ("left", "right")]
    assert names == want
    failed = [r for r in results if r["result"] != "pass"]
    assert not failed, failed
    for key in zero:
        assert mod.all_positive_zero(eng[key]), (fixture, fs, key, "engine")
        assert mod.all_positive_zero(ref[key]), (fixture, fs, key, "reference")


@pytest.mark.parametrize("fixture", FIXTURES)
@pytest.mark.parametrize("fs", RATES)
def test_engine_and_reference_are_zero_past_the_end(fixture, fs, vectors, engine_dumps, reference_renders):
    mod = rm()
    frames, _ = fixture_frames(vectors, fixture, fs)
    for key in KEYS:
        assert mod.all_positive_zero(engine_dumps[(fixture, fs)][key][2 * frames:]), (key, "engine")
        assert mod.all_positive_zero(reference_renders[(fixture, fs)][key][2 * frames:]), (key, "reference")


def test_engine_dump_follows_the_spec_vectors(vectors, engine_dumps):
    # The dump is the engine render: its output and theta tap hold the
    # vector bits (the C++ vector test checks the same through the C API).
    for v in vectors["stub_chain"]:
        e = engine_dumps[(v["fixture"], v["fs"])]
        n = int(v["n"])
        assert bits(e["output"][2 * n]) == int(v["left_bits"], 16), (v["fixture"], v["fs"], n)
        assert bits(e["output"][2 * n + 1]) == int(v["right_bits"], 16), (v["fixture"], v["fs"], n)
        assert bits(e["theta"][2 * n]) == int(v["theta_bits"], 16), (v["fixture"], v["fs"], n)
        assert bits(e["theta"][2 * n + 1]) == int(v["theta_bits"], 16), (v["fixture"], v["fs"], n)


def test_doctored_engine_output_fails(vectors, engine_dumps, reference_renders):
    # Must-fail: an error 10 dB above row reference-match at one sample.
    mod = rm()
    level = match_row().value + DOCTOR_OFFSET_DB
    for fs in RATES:
        frames, _ = fixture_frames(vectors, BEAT_6, fs)
        eng = engine_dumps[(BEAT_6, fs)]["output"][:2 * frames].copy()
        ref = reference_renders[(BEAT_6, fs)]["output"][:2 * frames]
        eng[2 * 1000] += amplitude(level)
        left, right = mod.match_stereo("output", eng, ref)
        assert left["result"] == "fail", left
        assert abs(left["measured"] - level) <= CALIBRATION_TOLERANCE_DB, left
        assert right["result"] == "pass", right


def test_scaled_down_signals_fail_as_silent(vectors, engine_dumps, reference_renders):
    # Must-fail: both sides scaled 10 dB below row reference-match-min-level.
    mod = rm()
    floor = min_level_row().value
    for fixture in FIXTURES:
        frames, _ = fixture_frames(vectors, fixture, 48000)
        eng = engine_dumps[(fixture, 48000)]["join"][:2 * frames]
        ref = reference_renders[(fixture, 48000)]["join"][:2 * frames]
        scale = amplitude(floor - DOCTOR_OFFSET_DB - mod.level_dbfs(ref))
        for r in mod.match_stereo("join", eng * scale, ref * scale):
            assert r["result"] == "fail" and r["note"] == "silent", (fixture, r)


def test_engine_side_silent_fails(vectors, reference_renders):
    # Must-fail: engine zeros against a real reference.
    mod = rm()
    frames, _ = fixture_frames(vectors, BEAT_6, 44100)
    ref = reference_renders[(BEAT_6, 44100)]["theta"][:2 * frames]
    for r in mod.match_stereo("theta", np.zeros_like(ref), ref):
        assert r["result"] == "fail" and r["note"] == "silent", r


def test_nonzero_sample_in_a_spec_zero_tap_fails(vectors, engine_dumps):
    # Must-fail for the exact-zero check: gamma, and beat-0 theta.
    mod = rm()
    for fixture, key in ((BEAT_6, "gamma"), (BEAT_0, "theta"), (BEAT_0, "bus")):
        a = engine_dumps[(fixture, 48000)][key].copy()
        assert mod.all_positive_zero(a), (fixture, key)
        a[2 * 37 + 1] = 5e-324
        assert not mod.all_positive_zero(a), (fixture, key)
