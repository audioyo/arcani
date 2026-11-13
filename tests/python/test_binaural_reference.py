"""Binaural layer and rate curve: fixtures, reference, engine match, isolation, and frequency (Story 2.5).

The reference renders the binaural layer from docs/signal-spec.md, Binaural
layer and Rate curve, only, in binary64 with the ideal functions. The engine
render comes from the test-only dump arcani-tapdump (tests/tapdump/, contract
in tests/python/test_reference_match.py). Thresholds and ranges come from
tests/tables/*.tsv through the assertion call `assertions.row`; no threshold
or range is written here as a literal.

Contract with reference/binaural.py (NumPy, the standard library, and
reference/ only):

- `WAVEFORMS == ("sine",)`: the modeled waveforms.
- `cycle_constants(cycle, fs) -> (p0, inc_cycle, k)`: for a beat_rate_cycle
  dict, P0 by the coupling phase rule on start_phase_deg and inc_P =
  ideal.phase_increment(1.0 / period_s, fs) (Python ints), and
  K = swing_hz * period_s / (2 * math.pi) (a float).
- `beat_offset_cycles(binaural, fs, frames) -> ndarray`: the ideal U[n] in
  cycles, K * (cos(2 pi signed(P0) / 2^64) - cos(2 pi signed(p_P[n]) / 2^64)),
  p_P[n] = P0 + n * inc_P mod 2^64; zeros without a cycle. float64, length
  frames.
- `render(binaural, fs, frames) -> (left, right)`: float64 arrays of length
  frames. Left: the ideal sine of n * inc_L. Right without a cycle: the ideal
  sine of n * inc_C (the stub's bits). Right with a cycle: y = phase_C[n] /
  2^64 + U[n] in binary64, reduced to [-1/2, 1/2) by subtracting the nearest
  integer, then the NumPy sine of 2 pi y. Any waveform other than sine
  (absent means sine) raises ValueError.
- reference.stub_chain.render takes both ears from it (same output keys).

Engine against reference: every committed binaural fixture
(binaural-beat-0, -6, -29: a 400 Hz pure sine in the left ear and a pure sine
at 400 Hz plus 0, 6, or 29 Hz in the right ear, 5 s; binaural-cycle-sleep: a
100 Hz pure sine in the left ear and a pure sine in the right ear whose beat
rate cycles over 0 to 3 Hz every 60 s from 0 Hz rising, 120 s) rendered with
arcani-tapdump at 44.1 and 48 kHz passes row `reference-match` per channel
for the join tap and the output, holds the vector bits, and is +0.0 past the
end. The frequency tool reads the fixed carriers within row
`frequency-accuracy`, and its phase mode reads the cycle fixture's right ear
within the row against the closed-form schedule. The compile-rejected
fixtures are rejected by the dump.

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
SCHEMA = REPO_ROOT / "recipes" / "recipe.schema.json"
FIXTURES_VALID = REPO_ROOT / "recipes" / "fixtures" / "valid"
FIXTURES_INVALID = REPO_ROOT / "recipes" / "fixtures" / "invalid"
INVALID_EXPECTED = REPO_ROOT / "recipes" / "fixtures" / "invalid-expected.json"
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
EXE_NAME = "arcani-tapdump.exe" if sys.platform == "win32" else "arcani-tapdump"
TAPDUMP = REPO_ROOT / "build" / PRESET / "tests" / "tapdump" / EXE_NAME

FIXED = {"binaural-beat-0.json": 0, "binaural-beat-6.json": 6, "binaural-beat-29.json": 29}
CYCLE_FIXTURE = "binaural-cycle-sleep.json"
ACCEPTED = tuple(FIXED) + (CYCLE_FIXTURE,)
SLEEP_CYCLE = {"swing_hz": 1.5, "period_s": 60, "start_phase_deg": 270}
REJECTED = {
    "binaural-waveform-triangle.json": ("/binaural/waveform", "non-sine binaural not modeled"),
    "binaural-cycle-below-0.json": ("/binaural/beat_rate_cycle/swing_hz", "range.min"),
    "binaural-cycle-above-30.json": ("/binaural/beat_rate_cycle/swing_hz", "range.max"),
}
MISSING_PERIOD = "binaural-cycle-missing-period.json"
SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
EXTRA_FRAMES = 64
CYCLE = 2**64
LEFT_TOL = Decimal("1e-15")
# The reference right ear with a cycle: y = phase_C / 2^64 + U carries U's
# binary64 rounding (U up to 2K, about 29 cycles, so about 4e-15 cycles),
# times 2 pi.
RIGHT_TOL = Decimal("1e-13")


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def binaural():
    _repo_on_path()
    return importlib.import_module("reference.binaural")


def stub_chain():
    _repo_on_path()
    return importlib.import_module("reference.stub_chain")


def ideal():
    _repo_on_path()
    return importlib.import_module("reference.ideal")


def gamma():
    _repo_on_path()
    return importlib.import_module("reference.gamma")


def rm():
    return importlib.import_module("assertions.reference_match")


def freq():
    return importlib.import_module("assertions.frequency")


def bits(x):
    return struct.unpack("<Q", struct.pack("<d", float(x)))[0]


def channel(stereo, c):
    return np.ascontiguousarray(np.asarray(stereo)[c::2])


def close(value, text, tol):
    return abs(Decimal(repr(float(value))) - Decimal(text)) <= tol


def accuracy_hz():
    r = table_row("frequency-accuracy")
    assert r.unit == "Hz", r
    return r.value


def sine_error_linear():
    r = table_row("sine-error")
    assert r.unit == "dBFS", r
    return 10.0 ** (r.value / 20.0)


def load_recipe(name, folder=FIXTURES_VALID):
    path = folder / name
    assert path.is_file(), f"missing fixture {path} (Story 2.5)"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def vectors():
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def binaural_rows(vectors, fixture, fs):
    rows = [r for r in vectors["binaural_samples"] if r["fixture"] == fixture and r["fs"] == fs]
    assert rows, (fixture, fs)
    return rows


def frames_of(vectors, fixture, fs):
    return int(binaural_rows(vectors, fixture, fs)[0]["frames"])


def spec_binaural(r):
    """The binaural dict of a binaural sample row, from the row's own values."""
    b = {"carrier_left_hz": float.fromhex(r["left_hex"]), "beat_rate_hz": float.fromhex(r["beat_hex"])}
    if r["swing_hex"] != "none":
        b["beat_rate_cycle"] = {"swing_hz": float.fromhex(r["swing_hex"]),
                                "period_s": float.fromhex(r["period_hex"]),
                                "start_phase_deg": float.fromhex(r["start_hex"])}
    return b


def sleep_binaural(start_phase_deg=270, waveform=None):
    b = {"carrier_left_hz": 100, "beat_rate_hz": 1.5, "beat_rate_cycle": dict(SLEEP_CYCLE, start_phase_deg=start_phase_deg)}
    if waveform is not None:
        b["waveform"] = waveform
    return b


def signed(u):
    """uint64 array as signed 64-bit values, float64."""
    return np.asarray(u, dtype=np.uint64).view(np.int64).astype(np.float64)


# ------------------------------------------------------ fixtures


def test_binaural_fixtures_exist_with_the_spec_values(vectors):
    order = []
    for r in vectors["binaural_samples"]:
        if r["fixture"] not in order:
            order.append(r["fixture"])
    assert tuple(order) == ACCEPTED
    for name, beat in FIXED.items():
        recipe = load_recipe(name)
        assert recipe["binaural"] == {"carrier_left_hz": 400, "beat_rate_hz": beat}, name
        assert list(recipe["binaural"]) == ["carrier_left_hz", "beat_rate_hz"], name
        assert float(recipe["length_s"]) == 5.0, name
    sleep = load_recipe(CYCLE_FIXTURE)
    assert sleep["binaural"] == {"carrier_left_hz": 100, "beat_rate_hz": 1.5, "beat_rate_cycle": SLEEP_CYCLE}
    assert list(sleep["binaural"]) == ["carrier_left_hz", "beat_rate_hz", "beat_rate_cycle"]
    assert list(sleep["binaural"]["beat_rate_cycle"]) == ["swing_hz", "period_s", "start_phase_deg"]
    assert float(sleep["length_s"]) == 120.0
    for name in ACCEPTED:
        recipe = load_recipe(name)
        assert "theta_reference" not in recipe and "gamma_pac" not in recipe, name
        assert recipe["seed"] == 42 and recipe["loudness_target_lufs"] == -36, name
        for fs in SAMPLE_RATES:
            r = binaural_rows(vectors, name, fs)[0]
            b = spec_binaural(r)
            assert float(recipe["binaural"]["carrier_left_hz"]) == b["carrier_left_hz"], (name, fs)
            assert float(recipe["binaural"]["beat_rate_hz"]) == b["beat_rate_hz"], (name, fs)
            assert float(recipe["length_s"]) == float.fromhex(r["length_hex"]), (name, fs)


def test_compile_rejected_binaural_fixtures_are_schema_valid_with_their_values():
    import jsonschema

    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    for name in REJECTED:
        recipe = load_recipe(name)
        assert not list(validator.iter_errors(recipe)), name
        assert "theta_reference" not in recipe and "gamma_pac" not in recipe, name
    tri = load_recipe("binaural-waveform-triangle.json")["binaural"]
    assert tri["waveform"] == "triangle", tri
    below = load_recipe("binaural-cycle-below-0.json")["binaural"]
    assert below["beat_rate_hz"] == 1.5 and below["beat_rate_cycle"]["swing_hz"] == 1.51, below
    assert below["beat_rate_hz"] - below["beat_rate_cycle"]["swing_hz"] < 0
    above = load_recipe("binaural-cycle-above-30.json")["binaural"]
    assert above["beat_rate_hz"] == 15 and above["beat_rate_cycle"]["swing_hz"] == 15, above
    for b in (below, above):
        assert b["beat_rate_cycle"]["period_s"] == 60, b
        assert "waveform" not in b, b


def test_missing_period_fixture_is_invalid_with_its_expected_error():
    import jsonschema

    recipe = load_recipe(MISSING_PERIOD, FIXTURES_INVALID)
    cycle = recipe["binaural"]["beat_rate_cycle"]
    assert "period_s" not in cycle and {"swing_hz", "start_phase_deg"} <= set(cycle), cycle
    entry = json.loads(INVALID_EXPECTED.read_text(encoding="utf-8"))["fixtures"].get(MISSING_PERIOD)
    assert entry is not None, f"{MISSING_PERIOD}: no entry in invalid-expected.json"
    assert entry.get("parameter") == "/binaural/beat_rate_cycle/period_s", entry
    assert entry.get("rule") == "required", entry
    assert entry.get("schema_keyword") == "required", entry
    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    assert {e.validator for e in validator.iter_errors(recipe)} == {"required"}


# ------------------------------------------------------ reference module


def test_reference_waveforms(vectors):
    mod = binaural()
    assert tuple(mod.WAVEFORMS) == ("sine",)
    assert tuple(mod.WAVEFORMS) == tuple(vectors["binaural_constants"]["modeled_waveforms"])


def test_reference_cycle_constants_match_every_rate_cycle_vector(vectors):
    mod = binaural()
    for r in vectors["rate_cycles"]:
        cycle = {"swing_hz": float.fromhex(r["swing_hex"]), "period_s": float.fromhex(r["period_hex"]),
                 "start_phase_deg": float.fromhex(r["start_hex"])}
        p0, inc, k = mod.cycle_constants(cycle, r["fs"])
        assert type(p0) is int and type(inc) is int, (type(p0), type(inc))
        assert p0 == int(r["p0"]), r
        assert inc == int(r["inc_cycle"]), r
        assert p0 == gamma().coupling_phase_units(cycle["start_phase_deg"]), r
        assert inc == ideal().phase_increment(1.0 / cycle["period_s"], r["fs"]), r
        assert k == cycle["swing_hz"] * cycle["period_s"] / (2.0 * math.pi), r
        # The engine K (two roundings with the binary64 1 / (2 pi)) is within an ulp or two.
        assert abs(k - float.fromhex(r["k_hex"])) <= 4 * math.ulp(k), (k, r["k_hex"])
        assert close(math.cos(2.0 * math.pi * signed(np.uint64(p0)) / 2.0**64), r["ideal_c0"], LEFT_TOL), r


def test_reference_beat_offset_follows_the_rate_curve_vectors(vectors):
    # Phi(t) = r t + U(t): the ideal beat phase at the vector times, where
    # t * fs is a whole sample.
    mod = binaural()
    by_cycle = {}
    for r in vectors["rate_curve"]:
        key = (r["center_hex"], r["swing_hex"], r["period_hex"], r["start_hex"])
        by_cycle.setdefault(key, []).append(r)
    assert len(by_cycle) == 3, sorted(by_cycle)
    for fs in SAMPLE_RATES:
        for (center, swing, period, start), rows in by_cycle.items():
            b = {"carrier_left_hz": 100.0, "beat_rate_hz": float.fromhex(center),
                 "beat_rate_cycle": {"swing_hz": float.fromhex(swing), "period_s": float.fromhex(period),
                                     "start_phase_deg": float.fromhex(start)}}
            ns = [round(float.fromhex(r["t_hex"]) * fs) for r in rows]
            u = mod.beat_offset_cycles(b, fs, max(ns) + 1)
            assert isinstance(u, np.ndarray) and u.dtype == np.float64 and u.size == max(ns) + 1
            assert u[0] == 0.0
            for r, n in zip(rows, ns):
                t = float.fromhex(r["t_hex"])
                assert n == t * fs
                got = b["beat_rate_hz"] * t + float(u[n])
                assert abs(Decimal(repr(got)) - Decimal(r["ideal_beat_cycles"])) <= Decimal("1e-9"), (
                    fs, start, t, got, r["ideal_beat_cycles"])


def test_reference_beat_offset_is_zero_without_a_cycle():
    mod = binaural()
    for fs in SAMPLE_RATES:
        u = mod.beat_offset_cycles({"carrier_left_hz": 400, "beat_rate_hz": 6}, fs, 1000)
        assert isinstance(u, np.ndarray) and u.dtype == np.float64 and u.shape == (1000,)
        assert not u.any()


def test_reference_beat_offset_is_near_the_engine_units_of_every_vector(vectors):
    # The engine U (phase units) and the ideal U (cycles) are the same point of
    # the cycle within the cycle bound: K * (2 b) + 2^-49 K + 2^-64, b the
    # sine error bound of row sine-error.
    mod = binaural()
    b = sine_error_linear()
    for fs in SAMPLE_RATES:
        rows = [r for r in binaural_rows(vectors, CYCLE_FIXTURE, fs) if r["case"] == "signal"]
        spec = spec_binaural(rows[0])
        u = mod.beat_offset_cycles(spec, fs, max(int(r["n"]) for r in rows) + 1)
        k = float.fromhex(rows[0]["k_hex"])
        bound = k * 2.0 * b + 2.0**-49 * k + 2.0**-64
        for r in rows:
            n = int(r["n"])
            engine = int(r["u_units"]) / 2.0**64
            d = (float(u[n]) - engine) % 1.0
            d = min(d, 1.0 - d)
            assert d <= bound, (fs, n, d, bound)


def test_reference_render_is_within_tolerance_of_every_ideal_vector(vectors):
    mod = binaural()
    renders = {}
    for r in vectors["binaural_samples"]:
        if r["case"] != "signal":
            continue
        key = (r["fixture"], r["fs"])
        if key not in renders:
            frames = int(r["frames"])
            left, right = mod.render(spec_binaural(r), r["fs"], frames)
            for a in (left, right):
                assert isinstance(a, np.ndarray) and a.dtype == np.float64 and a.shape == (frames,)
            renders[key] = (left, right)
        n = int(r["n"])
        left, right = renders[key]
        assert close(left[n], r["ideal_left"], LEFT_TOL), (key, n, float(left[n]), r["ideal_left"])
        assert close(right[n], r["ideal_right"], RIGHT_TOL), (key, n, float(right[n]), r["ideal_right"])


def test_reference_render_follows_the_spec_operations(vectors):
    mod = binaural()
    idl = ideal()
    seen = set()
    for r in vectors["binaural_samples"]:
        key = (r["fixture"], r["fs"])
        if key in seen:
            continue
        seen.add(key)
        fs = r["fs"]
        frames = min(int(r["frames"]), 20 * fs)
        b = spec_binaural(r)
        n = np.arange(frames, dtype=np.uint64)
        inc_l = idl.phase_increment(b["carrier_left_hz"], fs)
        inc_c = idl.phase_increment(b["carrier_left_hz"] + b["beat_rate_hz"], fs)
        assert (inc_l, inc_c) == (int(r["inc_left"]), int(r["inc_center"])), key
        left, right = mod.render(b, fs, frames)
        assert np.array_equal(left.view(np.uint64), idl.ideal_sine(n * np.uint64(inc_l)).view(np.uint64)), key
        phase_c = n * np.uint64(inc_c)
        if "beat_rate_cycle" not in b:
            # The stub's right ear, bit for bit.
            assert np.array_equal(right.view(np.uint64), idl.ideal_sine(phase_c).view(np.uint64)), key
            continue
        c = b["beat_rate_cycle"]
        p0 = int(r["p0"])
        inc_p = int(r["inc_cycle"])
        k = c["swing_hz"] * c["period_s"] / (2.0 * math.pi)
        p = np.uint64(p0) + n * np.uint64(inc_p)
        c0 = math.cos(float(signed(np.uint64(p0))) * (2.0 * math.pi / 2.0**64))
        u = k * (c0 - np.cos(signed(p) * (2.0 * math.pi / 2.0**64)))
        assert np.max(np.abs(mod.beat_offset_cycles(b, fs, frames) - u)) <= 1e-12, key
        y = phase_c.astype(np.float64) / 2.0**64 + u
        y = y - np.rint(y)
        want = np.sin(2.0 * np.pi * y)
        assert np.max(np.abs(right - want)) <= 1e-12, key


def test_reference_rejects_any_waveform_but_sine():
    mod = binaural()
    fs = SAMPLE_RATES[0]
    base = mod.render(sleep_binaural(), fs, 4800)
    same = mod.render(sleep_binaural(waveform="sine"), fs, 4800)
    for a, b in zip(base, same):
        assert np.array_equal(a.view(np.uint64), b.view(np.uint64))
    for wave in ("triangle", "square", "Sine", ""):
        with pytest.raises(ValueError):
            mod.render(sleep_binaural(waveform=wave), fs, 4800)
        with pytest.raises(ValueError):
            mod.render({"carrier_left_hz": 400, "beat_rate_hz": 6, "waveform": wave}, fs, 4800)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_start_phase_0_and_360_render_the_same_bytes(fs):
    mod = binaural()
    zero = mod.render(sleep_binaural(0), fs, 2 * fs)
    full = mod.render(sleep_binaural(360), fs, 2 * fs)
    for a, b in zip(zero, full):
        assert np.array_equal(a.view(np.uint64), b.view(np.uint64))
    near = mod.render(sleep_binaural(359.99), fs, 2 * fs)
    assert not np.array_equal(near[1].view(np.uint64), zero[1].view(np.uint64))


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_swing_0_is_the_fixed_beat(fs):
    mod = binaural()
    fixed = mod.render({"carrier_left_hz": 100, "beat_rate_hz": 1.5}, fs, fs)
    zero = mod.render({"carrier_left_hz": 100, "beat_rate_hz": 1.5,
                       "beat_rate_cycle": {"swing_hz": 0, "period_s": 60, "start_phase_deg": 270}}, fs, fs)
    for a, b in zip(fixed, zero):
        assert np.max(np.abs(a - b)) <= 1e-12


def test_stub_chain_takes_both_ears_from_the_binaural_reference(vectors):
    sc = stub_chain()
    mod = binaural()
    for fixture in ACCEPTED:
        recipe = load_recipe(fixture)
        for fs in SAMPLE_RATES:
            frames = frames_of(vectors, fixture, fs)
            out = sc.render(FIXTURES_VALID / fixture, fs, frames=frames + EXTRA_FRAMES)
            assert set(out) == {"output", "theta", "gamma", "bus", "join", "master"}
            left, right = mod.render(recipe["binaural"], fs, frames)
            for c, want in ((0, left), (1, right)):
                for key in ("join", "master", "output"):
                    got = channel(out[key], c)
                    assert np.array_equal(got[:frames].view(np.uint64), want.view(np.uint64)), (fixture, fs, key, c)
                    assert not got[frames:].view(np.uint64).any(), (fixture, fs, key, c, "past end")
            for key in ("theta", "gamma", "bus"):
                assert not out[key].view(np.uint64).any(), (fixture, fs, key)


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


def run_dump(exe, recipe, fs, out_dir, extra, expect_ok=True):
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run([str(exe), str(recipe), str(fs), str(out_dir), str(extra)],
                                capture_output=True, text=True, timeout=600)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the dump (winerror {e.winerror})")
        raise
    if expect_ok:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


DUMP_KEYS = (("theta", "theta"), ("gamma", "gamma"), ("bus", "bus"), ("join", "join"), ("master", "master"),
             ("output", "out"))


def dump_arrays(exe, recipe, fs, out_dir, extra):
    result = run_dump(exe, recipe, fs, out_dir, extra)
    arrays = {key: np.fromfile(out_dir / f"{name}.f64", dtype="<f8").astype(np.float64) for key, name in DUMP_KEYS}
    shutil.rmtree(out_dir, ignore_errors=True)
    return result.stdout, arrays


def closed_form_cycles(b, fs, frames):
    """The right-ear phase in cycles by the ideal law: (f_L + r) t + K (cos phi0 - cos(2 pi t / P + phi0))."""
    t = np.arange(frames, dtype=np.float64) / fs
    f_c = float(b["carrier_left_hz"]) + float(b["beat_rate_hz"])
    c = b.get("beat_rate_cycle")
    if c is None:
        return f_c * t
    phi0 = math.radians(float(c["start_phase_deg"]))
    k = float(c["swing_hz"]) * float(c["period_s"]) / (2.0 * math.pi)
    return f_c * t + k * (math.cos(phi0) - np.cos(2.0 * math.pi * t / float(c["period_s"]) + phi0))


@pytest.mark.parametrize("fixture", ACCEPTED)
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_binaural_fixture_matches_the_reference_and_holds_the_vector_bits(fixture, fs, vectors,
                                                                                 tapdump, tmp_path):
    frames = frames_of(vectors, fixture, fs)
    recipe = load_recipe(fixture)
    stdout, eng = dump_arrays(tapdump, FIXTURES_VALID / fixture, fs, tmp_path / "dump", EXTRA_FRAMES)
    assert f"frames {frames} total {frames + EXTRA_FRAMES}" in stdout, stdout
    for key, a in eng.items():
        assert a.size == 2 * (frames + EXTRA_FRAMES), (fixture, fs, key, a.size)
    ref = stub_chain().render(FIXTURES_VALID / fixture, fs, frames=frames + EXTRA_FRAMES)
    mod = rm()
    table_row("reference-match")
    results = []
    for key in ("join", "output"):
        results += mod.match_stereo(f"{fixture} {fs} {key}", eng[key][:2 * frames], ref[key][:2 * frames])
    failed = [r for r in results if r["result"] != "pass"]
    assert not failed, failed
    for key in ("theta", "gamma", "bus"):
        assert mod.all_positive_zero(eng[key]), (fixture, fs, key)
    for key, _ in DUMP_KEYS:
        assert mod.all_positive_zero(eng[key][2 * frames:]), (fixture, fs, key, "past end")
    assert np.array_equal(eng["output"].view(np.uint64), eng["join"].view(np.uint64))
    assert np.array_equal(eng["master"].view(np.uint64), eng["join"].view(np.uint64))
    for r in binaural_rows(vectors, fixture, fs):
        n = int(r["n"])
        for c, col in ((0, "left_bits"), (1, "right_bits")):
            w = (fixture, fs, n, c)
            assert bits(eng["join"][2 * n + c]) == int(r[col], 16), w
            assert bits(eng["output"][2 * n + c]) == int(r[col], 16), w

    # Frequency: each fixed carrier reads within row frequency-accuracy; with
    # the cycle, the phase mode reads the right ear against the schedule.
    tool = freq()
    left = channel(eng["join"], 0)[:frames]
    right = channel(eng["join"], 1)[:frames]
    b = recipe["binaural"]
    f_left = float(b["carrier_left_hz"])
    carrier = tool.check(f"left carrier {fixture} {fs}", tool.carrier_hz(left, fs), f_left)
    assert carrier["result"] == "pass", carrier
    if "beat_rate_cycle" not in b:
        f_right = f_left + float(b["beat_rate_hz"])
        right_carrier = tool.check(f"right carrier {fixture} {fs}", tool.carrier_hz(right, fs), f_right)
        assert right_carrier["result"] == "pass", right_carrier
        assert right_carrier["threshold"] == accuracy_hz()
    else:
        result = tool.check_phase(f"right ear {fixture} {fs}", right, fs, closed_form_cycles(b, fs, frames))
        assert result["result"] == "pass", result
        assert result["row"] == "frequency-accuracy" and result["threshold"] == accuracy_hz()
        left_phase = tool.check_phase(f"left ear {fixture} {fs}", left, fs, f_left * np.arange(frames) / fs)
        assert left_phase["result"] == "pass", left_phase
        # Must-fail on engine output: the right ear judged against the same
        # cycle at another start phase, or without the cycle.
        wrong = dict(b, beat_rate_cycle=dict(b["beat_rate_cycle"], start_phase_deg=90))
        miss = tool.check_phase("wrong start phase", right, fs, closed_form_cycles(wrong, fs, frames))
        assert miss["result"] == "fail", miss
        fixed = {k: v for k, v in b.items() if k != "beat_rate_cycle"}
        flat = tool.check_phase("no cycle", right, fs, closed_form_cycles(fixed, fs, frames))
        assert flat["result"] == "fail", flat


@pytest.mark.parametrize("fixture", sorted(REJECTED))
def test_engine_rejects_the_compile_rejected_binaural_fixtures(fixture, tapdump, tmp_path):
    load_recipe(fixture)
    parameter, rule = REJECTED[fixture]
    for fs in SAMPLE_RATES:
        result = run_dump(tapdump, FIXTURES_VALID / fixture, fs, tmp_path / f"dump-{fs}", 0, expect_ok=False)
        assert result.returncode == 1, (fixture, fs, result.stdout, result.stderr)
        assert not (tmp_path / f"dump-{fs}" / "join.f64").exists(), fixture
        text = result.stdout + result.stderr
        assert rule in text and parameter in text, (fixture, text)


def test_engine_rejects_the_missing_period_fixture(tapdump, tmp_path):
    load_recipe(MISSING_PERIOD, FIXTURES_INVALID)
    result = run_dump(tapdump, FIXTURES_INVALID / MISSING_PERIOD, SAMPLE_RATES[0], tmp_path / "dump", 0,
                      expect_ok=False)
    assert result.returncode == 1, (result.stdout, result.stderr)
    text = result.stdout + result.stderr
    assert "required" in text and "/binaural/beat_rate_cycle/period_s" in text, text


# ------------------------------------------------------------ clicks


def clicks():
    return importlib.import_module("assertions.clicks")


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_sleep_cycle_passes_the_click_test(fs, tapdump, tmp_path):
    # The beat rate cycle moves the right ear's phase every sample; the click
    # tool (row click-level after the row click-highpass high-pass) finds no
    # discontinuity in either ear of the engine output.
    _, arrays = dump_arrays(tapdump, FIXTURES_VALID / "binaural-cycle-sleep.json", fs, tmp_path / "dump", 0)
    for c, ear in ((0, "left"), (1, "right")):
        result = clicks().check(f"binaural-cycle-sleep {fs} {ear}", channel(arrays["output"], c), fs)
        assert result["result"] == "pass", result
