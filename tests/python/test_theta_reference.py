"""Theta reference envelopes: Python reference, engine match, frequency, and clicks (Story 2.1).

The reference renders the theta reference from docs/signal-spec.md, Theta
reference, only, in binary64 with the ideal functions. The engine render
comes from the test-only dump arcani-tapdump (tests/tapdump/, contract in
tests/python/test_reference_match.py). Thresholds and ranges come from
tests/tables/*.tsv through the assertion call `assertions.row`; no threshold
or range is written here as a literal.

Contract with reference/theta.py (NumPy, the standard library, and
reference/ only; imported as `reference.theta` with the repo root on
sys.path; it renders ideal functions, never the engine polynomial):

- `SHAPES == ("sine", "smoothed_on_off", "sawtooth", "reverse_saw")`.
- `ON_SHARE_PERCENT == 50.0` and `EDGE_MS == 10.0`, equal to range rows
  `theta-on-share` and `theta-edge` (each min equal to max).
- `half_on_units() -> int`: H, per the spec (2^62).
- `edge_units(rate_hz: float) -> int`: W, per the spec's edge rule.
- `envelope(shape, phase, rate_hz)`: the ideal envelope e of an envelope
  phase, by the spec's segments; phase an int (returns a float) or a uint64
  ndarray (returns a float64 ndarray of the same shape). Any shape outside
  SHAPES, "custom" included, raises ValueError.
- `render(theta_reference: dict, fs: int, frames: int) -> ndarray`: the
  theta tap of one channel for n in [0, frames): a[n] * ideal_sine(phase_T[n])
  with a = 1.0 - d * (1.0 - e) and d = am_depth_percent / 100.0, both
  phases n * inc mod 2^64 from ideal.phase_increment; 1-D float64.

reference.stub_chain.render (Story 1.5 contract, unchanged otherwise) takes
its theta tap, both channels, from reference.theta.render; a recipe without
`theta_reference` keeps a theta tap of +0.0.

Engine against reference, for each theta fixture (signal spec, Vectors:
theta fixtures) at 44.1 and 48 kHz: the theta tap and the output (the same,
since the fixtures have no binaural layer) pass the reference match
(row `reference-match`, per channel), and the count of samples whose
difference reaches the row is at most row `envelope-shape`; past the end
(64 extra frames) both sides are +0.0. The frequency tool reads the engine
theta tap's carrier and rate within row `frequency-accuracy` of the recipe.
The click tool passes the 100 percent depth variants (made here from the
fixtures, `am_depth_percent` set to 100) of the smoothed on-off, sawtooth,
and reverse saw at both rates and both sample rates; the harness's unsmoothed
sawtooth (a 450 Hz carrier times a linear rise with an instant drop) fails.

Must-fail (doctored here, in the harness): the Story 1.5 unmodulated theta
against the reference fails the match on every fixture; the engine sawtooth
against the reference reverse saw fails the envelope count.

The dump tests skip only when cmake is not on PATH, or when Windows
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
from assertions.tables import load_tables

REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS = REPO_ROOT / "tests" / "data" / "signal_spec_vectors.json"
FIXTURES_VALID = REPO_ROOT / "recipes" / "fixtures" / "valid"
THETA_MODULE = REPO_ROOT / "reference" / "theta.py"
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
EXE_NAME = "arcani-tapdump.exe" if sys.platform == "win32" else "arcani-tapdump"
TAPDUMP = REPO_ROOT / "build" / PRESET / "tests" / "tapdump" / EXE_NAME

SHAPES = ("sine", "smoothed_on_off", "sawtooth", "reverse_saw")
HARD_EDGED = ("smoothed_on_off", "sawtooth", "reverse_saw")
RATES_HZ = (1, 6)
FIXTURES = tuple(f"theta-{s.replace('_', '-')}-{r}hz.json" for s in SHAPES for r in RATES_HZ)
SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
EXTRA_FRAMES = 64
CYCLE = 2**64
IDEAL_TOL = Decimal("1e-15")


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def theta():
    assert THETA_MODULE.is_file(), f"missing {THETA_MODULE} (Story 2.1 reference theta layer)"
    _repo_on_path()
    return importlib.import_module("reference.theta")


def stub_chain():
    _repo_on_path()
    return importlib.import_module("reference.stub_chain")


def ideal():
    _repo_on_path()
    return importlib.import_module("reference.ideal")


def rm():
    return importlib.import_module("assertions.reference_match")


def freq():
    return importlib.import_module("assertions.frequency")


def clicks():
    return importlib.import_module("assertions.clicks")


def fixed_range(row_id, unit):
    r = table_row(row_id)
    assert r.kind == "ranges" and r.unit == unit and r.min == r.max, r
    return r


def match_row():
    r = table_row("reference-match")
    assert r.unit == "dBFS", r
    return r


def envelope_row():
    r = table_row("envelope-shape")
    assert r.unit == "envelope samples failing the reference match", r
    return r


def accuracy_hz():
    r = table_row("frequency-accuracy")
    assert r.unit == "Hz", r
    return r.value


def bits(x):
    return struct.unpack("<Q", struct.pack("<d", float(x)))[0]


def channel(stereo, c):
    return np.ascontiguousarray(np.asarray(stereo)[c::2])


def close(value, text):
    return abs(Decimal(repr(float(value))) - Decimal(text)) <= IDEAL_TOL


def load_recipe(name):
    return json.loads((FIXTURES_VALID / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def vectors():
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def frames_of(vectors, fixture, fs):
    rows = [r for r in vectors["theta_samples"] if r["fixture"] == fixture and r["fs"] == fs]
    assert rows, (fixture, fs)
    return int(rows[0]["frames"])


def failing_samples(engine, reference):
    """Samples whose difference reaches row reference-match (row envelope-shape counts them)."""
    limit = 10.0 ** (match_row().value / 20.0)
    return int(np.count_nonzero(np.abs(np.asarray(engine) - np.asarray(reference)) >= limit))


# ------------------------------------------------------ reference module


def test_reference_constants_equal_the_rows():
    mod = theta()
    assert tuple(mod.SHAPES) == SHAPES
    assert mod.ON_SHARE_PERCENT == fixed_range("theta-on-share", "percent").min
    assert mod.EDGE_MS == fixed_range("theta-edge", "ms").min


def test_reference_edge_and_half_units_follow_the_vectors(vectors):
    mod = theta()
    assert mod.half_on_units() == int(vectors["theta_constants"]["h_units"])
    for r in vectors["theta_edges"]:
        got = mod.edge_units(float.fromhex(r["rate_hex"]))
        assert isinstance(got, int) and got == int(r["w_units"]), r


def test_reference_envelope_is_within_1e_15_of_every_vector(vectors):
    mod = theta()
    for r in vectors["theta_envelopes"]:
        rate = float.fromhex(r["rate_hex"])
        got = mod.envelope(r["shape"], int(r["phase"]), rate)
        assert np.ndim(got) == 0, r
        assert 0.0 <= float(got) <= 1.0, r
        assert close(got, r["ideal_e"]), (r["shape"], rate, r["phase"], float(got), r["ideal_e"])


def test_reference_envelope_array_form(vectors):
    mod = theta()
    for shape in SHAPES:
        for rate_hex in sorted({r["rate_hex"] for r in vectors["theta_envelopes"]}):
            rows = [r for r in vectors["theta_envelopes"]
                    if r["shape"] == shape and r["rate_hex"] == rate_hex]
            phases = np.array([int(r["phase"]) for r in rows], dtype=np.uint64)
            got = mod.envelope(shape, phases, float.fromhex(rate_hex))
            assert isinstance(got, np.ndarray) and got.dtype == np.float64 and got.shape == phases.shape
            for r, value in zip(rows, got):
                assert close(value, r["ideal_e"]), (shape, rate_hex, r["phase"])


@pytest.mark.parametrize("shape", ("custom", "square", ""))
def test_reference_rejects_a_shape_the_spec_does_not_model(shape):
    with pytest.raises(ValueError):
        theta().envelope(shape, 0, 6.0)


def test_reference_render_is_within_1e_15_of_every_sample_vector(vectors):
    mod = theta()
    renders = {}
    for r in vectors["theta_samples"]:
        key = (r["fixture"], r["fs"])
        if key not in renders:
            spec = load_recipe(r["fixture"])["theta_reference"]
            renders[key] = mod.render(spec, r["fs"], int(r["frames"]) + EXTRA_FRAMES)
            out = renders[key]
            assert isinstance(out, np.ndarray) and out.dtype == np.float64 and out.ndim == 1
            assert out.size == int(r["frames"]) + EXTRA_FRAMES
        if r["case"] != "signal":
            continue
        assert close(renders[key][int(r["n"])], r["ideal_theta"]), (r["fixture"], r["fs"], r["n"])


def test_reference_render_at_depth_0_is_the_unmodulated_carrier():
    mod = theta()
    idl = ideal()
    for fs in SAMPLE_RATES:
        spec = {"carrier_hz": 300, "rate_hz": 6, "am_depth_percent": 0, "shape": "sawtooth"}
        got = mod.render(spec, fs, fs)
        inc = np.uint64(idl.phase_increment(300.0, fs))
        want = idl.ideal_sine(np.arange(fs, dtype=np.uint64) * inc)
        assert np.array_equal(got.view(np.uint64), want.view(np.uint64)), fs


def test_stub_chain_takes_its_theta_tap_from_the_theta_layer(vectors):
    sc = stub_chain()
    mod = theta()
    for fixture in FIXTURES:
        for fs in SAMPLE_RATES:
            frames = frames_of(vectors, fixture, fs)
            out = sc.render(FIXTURES_VALID / fixture, fs, frames=frames + EXTRA_FRAMES)
            want = mod.render(load_recipe(fixture)["theta_reference"], fs, frames)
            for c in (0, 1):
                got = channel(out["theta"], c)
                assert np.array_equal(got[:frames].view(np.uint64), want.view(np.uint64)), (fixture, fs, c)
                assert not got[frames:].view(np.uint64).any(), (fixture, fs, c, "past end")
            # No binaural layer: the output equals the theta tap.
            assert np.array_equal(out["output"].view(np.uint64), out["theta"].view(np.uint64)), (fixture, fs)


def test_reference_theta_does_not_implement_the_engine_polynomial(vectors):
    source = THETA_MODULE.read_text(encoding="utf-8").lower() if THETA_MODULE.is_file() else None
    assert source is not None, f"missing {THETA_MODULE}"
    for c in vectors["sine_coefficients"]:
        if c["power"] < 3:
            continue
        mantissa = c["hex"].lstrip("-").lower()
        assert mantissa not in source and mantissa.replace("0x", "") not in source, c["power"]
    assert "factorial" not in source


# ------------------------------------------------------ engine dumps


def cmake_command(args):
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-File", str(REPO_ROOT / "tools" / "dev.ps1"), "cmake", *args]
    return [CMAKE, *args]


@pytest.fixture(scope="module")
def tapdump():
    if CMAKE is None:
        pytest.skip("cmake is not on PATH")
    result = subprocess.run(cmake_command(["--build", "--preset", PRESET, "--target", "arcani-tapdump"]),
                            cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
                            env=os.environ.copy())
    assert result.returncode == 0, (
        f"building arcani-tapdump failed (configure the {PRESET} preset first):\n"
        f"{result.stdout}{result.stderr}")
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


def read_f64(path):
    return np.fromfile(path, dtype="<f8").astype(np.float64)


@pytest.fixture(scope="module")
def engine_dumps(tapdump, tmp_path_factory, vectors):
    """(fixture, fs) -> {"theta", "output", "gamma"} arrays, N + 64 frames each."""
    out = {}
    root = tmp_path_factory.mktemp("theta-dump")
    for fixture in FIXTURES:
        for fs in SAMPLE_RATES:
            frames = frames_of(vectors, fixture, fs)
            d = root / f"{fixture}-{fs}"
            stdout = run_dump(tapdump, FIXTURES_VALID / fixture, fs, d, EXTRA_FRAMES)
            assert f"frames {frames} total {frames + EXTRA_FRAMES}" in stdout, stdout
            arrays = {key: read_f64(d / f"{name}.f64")
                      for key, name in (("theta", "theta"), ("output", "out"), ("gamma", "gamma"))}
            for key, a in arrays.items():
                assert a.size == 2 * (frames + EXTRA_FRAMES), (fixture, fs, key, a.size)
            out[(fixture, fs)] = arrays
    return out


@pytest.fixture(scope="module")
def reference_taps(vectors):
    mod = theta()
    out = {}
    for fixture in FIXTURES:
        for fs in SAMPLE_RATES:
            frames = frames_of(vectors, fixture, fs)
            out[(fixture, fs)] = mod.render(load_recipe(fixture)["theta_reference"], fs, frames)
    return out


def stereo(mono):
    s = np.empty(2 * mono.size, dtype=np.float64)
    s[0::2] = mono
    s[1::2] = mono
    return s


@pytest.mark.parametrize("fixture", FIXTURES)
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_theta_matches_the_reference(fixture, fs, vectors, engine_dumps, reference_taps):
    mod = rm()
    frames = frames_of(vectors, fixture, fs)
    eng = engine_dumps[(fixture, fs)]
    ref = stereo(reference_taps[(fixture, fs)])
    results = []
    for key in ("theta", "output"):
        results += mod.match_stereo(key, eng[key][:2 * frames], ref)
        assert failing_samples(eng[key][:2 * frames], ref) <= envelope_row().value, (fixture, fs, key)
    failed = [r for r in results if r["result"] != "pass"]
    assert not failed, failed
    assert mod.all_positive_zero(eng["gamma"]), (fixture, fs)
    for key in ("theta", "output"):
        assert mod.all_positive_zero(eng[key][2 * frames:]), (fixture, fs, key, "past end")


def test_engine_dump_holds_the_vector_bits(vectors, engine_dumps):
    for r in vectors["theta_samples"]:
        e = engine_dumps[(r["fixture"], r["fs"])]
        n = int(r["n"])
        for c in (0, 1):
            assert bits(e["theta"][2 * n + c]) == int(r["theta_bits"], 16), (r["fixture"], r["fs"], n, c)
            assert bits(e["output"][2 * n + c]) == int(r["theta_bits"], 16), (r["fixture"], r["fs"], n, c)


def test_unmodulated_theta_fails_the_match(vectors, reference_taps):
    # Must-fail: the Story 1.5 stub (the carrier at unit amplitude) against
    # the reference fails on every fixture.
    mod = rm()
    idl = ideal()
    for fixture in FIXTURES:
        for fs in SAMPLE_RATES:
            frames = frames_of(vectors, fixture, fs)
            inc = np.uint64(idl.phase_increment(450.0, fs))
            stub = idl.ideal_sine(np.arange(frames, dtype=np.uint64) * inc)
            result = mod.match("stub", stub, reference_taps[(fixture, fs)])
            assert result["result"] == "fail", (fixture, fs, result)
            assert failing_samples(stub, reference_taps[(fixture, fs)]) > envelope_row().value


def test_mirrored_shape_fails_the_envelope_count(vectors, engine_dumps):
    # Must-fail: the engine sawtooth against the reference reverse saw.
    mod = theta()
    for fs in SAMPLE_RATES:
        for rate in RATES_HZ:
            fixture = f"theta-sawtooth-{rate}hz.json"
            frames = frames_of(vectors, fixture, fs)
            spec = dict(load_recipe(fixture)["theta_reference"], shape="reverse_saw")
            mirrored = mod.render(spec, fs, frames)
            eng = channel(engine_dumps[(fixture, fs)]["theta"], 0)[:frames]
            assert failing_samples(eng, mirrored) > envelope_row().value, (fs, rate)


@pytest.mark.parametrize("fixture", FIXTURES)
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_theta_carrier_and_rate_are_accurate(fixture, fs, vectors, engine_dumps):
    tool = freq()
    frames = frames_of(vectors, fixture, fs)
    spec = load_recipe(fixture)["theta_reference"]
    tap = channel(engine_dumps[(fixture, fs)]["theta"], 0)[:frames]
    carrier = tool.check(f"{fixture} carrier", tool.carrier_hz(tap, fs), float(spec["carrier_hz"]))
    rate = tool.check(f"{fixture} rate", tool.rate_hz(tap, fs), float(spec["rate_hz"]))
    assert carrier["result"] == "pass", carrier
    assert rate["result"] == "pass", rate
    assert carrier["threshold"] == rate["threshold"] == accuracy_hz()


# ------------------------------------------------------------ clicks


@pytest.fixture(scope="module")
def full_depth_dumps(tapdump, tmp_path_factory, vectors):
    """The 100 percent depth variants of the hard-edged fixtures, made here."""
    out = {}
    root = tmp_path_factory.mktemp("theta-full-depth")
    for shape in HARD_EDGED:
        for rate in RATES_HZ:
            fixture = f"theta-{shape.replace('_', '-')}-{rate}hz.json"
            recipe = load_recipe(fixture)
            recipe["theta_reference"]["am_depth_percent"] = 100
            path = root / f"full-depth-{fixture}"
            path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")
            for fs in SAMPLE_RATES:
                frames = frames_of(vectors, fixture, fs)
                d = root / f"{fixture}-{fs}"
                run_dump(tapdump, path, fs, d, 0)
                tap = read_f64(d / "theta.f64")
                assert tap.size == 2 * frames, (fixture, fs)
                out[(shape, rate, fs)] = channel(tap, 0)
    return out


@pytest.mark.parametrize("shape", HARD_EDGED)
@pytest.mark.parametrize("rate", RATES_HZ)
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_full_depth_hard_edged_shapes_pass_the_click_test(shape, rate, fs, full_depth_dumps):
    tap = full_depth_dumps[(shape, rate, fs)]
    result = clicks().check(f"{shape} {rate} Hz full depth", tap, fs)
    assert result["result"] == "pass", result


@pytest.mark.parametrize("rate", RATES_HZ)
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_unsmoothed_sawtooth_fails_the_click_test(rate, fs, vectors):
    frames = frames_of(vectors, f"theta-sawtooth-{rate}hz.json", fs)
    t = np.arange(frames, dtype=np.float64) / fs
    envelope = np.mod(rate * t, 1.0)  # linear rise, instant drop: no edge smoothing
    x = envelope * np.sin(2.0 * np.pi * 450.0 * t)
    result = clicks().check(f"unsmoothed sawtooth {rate} Hz", x, fs)
    assert result["result"] == "fail", result
