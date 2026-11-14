"""Gamma PAC layer, uncoupled: Python reference, engine match, frequency, and AM depth (Story 2.2).

The reference renders the gamma PAC layer from docs/signal-spec.md, Gamma
PAC layer, only, in binary64 with the ideal functions. The engine render
comes from the test-only dump arcani-tapdump (tests/tapdump/, contract in
tests/python/test_reference_match.py). Thresholds and ranges come from
tests/tables/*.tsv through the assertion call `assertions.row`; no threshold
or range is written here as a literal.

Contract with reference/gamma.py (NumPy, the standard library, and
reference/ only; imported as `reference.gamma` with the repo root on
sys.path; implemented from the signal spec, not from reference/theta.py
code; it renders ideal functions, never the engine polynomial):

- `CARRIER_WAVES == ("sine",)`: the carrier waves the spec models.
- `COUPLINGS == ("uncoupled", "smooth_swell", "bursts")`: the couplings the
  spec models (Story 2.2 modeled "uncoupled"; Story 2.3 adds "smooth_swell",
  tested in tests/python/test_coupling_reference.py; Story 2.4 adds "bursts",
  tested in tests/python/test_bursts_reference.py).
- `envelope(phase)`: the ideal gamma envelope e = (1 + cos(2 pi p / 2^64)) / 2
  of an envelope phase, the cosine of the signed phase in binary64 with
  NumPy; phase an int (returns a float) or a uint64 ndarray (returns a
  float64 ndarray of the same shape).
- `render(gamma_pac: dict, fs: int, frames: int) -> ndarray`: the gamma tap
  of one channel for n in [0, frames): a[n] * ideal_sine(phase_G[n]) with
  a = 1.0 - d * (1.0 - e[n]), d = am_depth_percent / 100.0, e = envelope(
  phase_M[n]); phase_G[n] = n * inc_G and phase_M[n] = n * inc_M mod 2^64,
  each increment from ideal.phase_increment (carrier_hz and rate_hz); 1-D
  float64. A carrier_wave other than "sine" or a coupling other than
  "uncoupled" raises ValueError.

reference.stub_chain.render takes its gamma tap, both channels, from
reference.gamma.render when the recipe has `gamma_pac`, else +0.0; the
stereo bus is theta + gamma, one binary64 addition.

Engine against reference, for each gamma fixture (signal spec, Vectors:
gamma fixtures) at 44.1 and 48 kHz: the gamma tap, the stereo bus, and the
output pass the reference match (row `reference-match`, per channel), and
the theta tap too for theta-gamma-uncoupled.json (the gamma-only fixtures
get the exact-zero check on the theta tap); past the end (64 extra frames)
both sides are +0.0; the dump holds the vector bits. The frequency tool
reads the engine gamma tap's carrier (250 Hz) and AM rate (40 or 60 Hz)
within row `frequency-accuracy`; the AM depth tool (assertions.am_depth)
finds the engine gamma tap's depth constant at the recipe value.

Must-fail (doctored here, in the harness): an unmodulated 250 Hz carrier
fails the match against the reference on every fixture; a gamma rendered by
the reference at a depth 1 percent off fails the AM depth check; the engine
25 percent tap checked against 100 percent fails it.

The dump tests skip only when cmake is not on PATH, or when Windows
application control blocks the binary (OSError winerror 4551 or 1260).
"""

import ast
import importlib
import json
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
FIXTURES_INVALID = REPO_ROOT / "recipes" / "fixtures" / "invalid"
INVALID_EXPECTED = REPO_ROOT / "recipes" / "fixtures" / "invalid-expected.json"
GAMMA_MODULE = REPO_ROOT / "reference" / "gamma.py"
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
EXE_NAME = "arcani-tapdump.exe" if sys.platform == "win32" else "arcani-tapdump"
TAPDUMP = REPO_ROOT / "build" / PRESET / "tests" / "tapdump" / EXE_NAME

THETA_GAMMA = "theta-gamma-uncoupled.json"
GAMMA_ONLY = tuple(f"gamma-uncoupled-{rate}hz-{depth}pct.json" for rate in (40, 60) for depth in (25, 100))
FIXTURES = GAMMA_ONLY + (THETA_GAMMA,)
REJECTED = {
    "gamma-carrier-rule-200hz-60hz.json": {"carrier_hz": 200, "rate_hz": 60, "carrier_wave": "sine"},
    "gamma-carrier-wave-triangle.json": {"carrier_wave": "triangle"},
    "gamma-carrier-wave-softened-square.json": {"carrier_wave": "softened_square"},
}
NOT_IN_ENUM = {
    "gamma-coupling-not-in-enum.json": ("/gamma_pac/coupling", "swell"),
    "gamma-carrier-wave-not-in-enum.json": ("/gamma_pac/carrier_wave", "square"),
}
SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
EXTRA_FRAMES = 64
CYCLE = 2**64
IDEAL_TOL = Decimal("1e-15")


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def gamma():
    assert GAMMA_MODULE.is_file(), f"missing {GAMMA_MODULE} (Story 2.2 reference gamma layer)"
    _repo_on_path()
    return importlib.import_module("reference.gamma")


def theta():
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


def am_depth():
    return importlib.import_module("assertions.am_depth")


def accuracy_hz():
    r = table_row("frequency-accuracy")
    assert r.unit == "Hz", r
    return r.value


def bits(x):
    return struct.unpack("<Q", struct.pack("<d", float(x)))[0]


def channel(stereo, c):
    return np.ascontiguousarray(np.asarray(stereo)[c::2])


def stereo(mono):
    s = np.empty(2 * mono.size, dtype=np.float64)
    s[0::2] = mono
    s[1::2] = mono
    return s


def close(value, text):
    return abs(Decimal(repr(float(value))) - Decimal(text)) <= IDEAL_TOL


def load_recipe(name):
    path = FIXTURES_VALID / name
    assert path.is_file(), f"missing fixture {path} (Story 2.2)"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def vectors():
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def rows_of(vectors, fixture, fs):
    rows = [r for r in vectors["gamma_samples"] if r["fixture"] == fixture and r["fs"] == fs]
    assert rows, (fixture, fs)
    return rows


def frames_of(vectors, fixture, fs):
    return int(rows_of(vectors, fixture, fs)[0]["frames"])


def spec_gamma_pac(r):
    """The gamma_pac dict of a gamma sample vector row, from the vector's own values."""
    return {"carrier_hz": float.fromhex(r["carrier_hex"]), "rate_hz": float.fromhex(r["rate_hex"]),
            "am_depth_percent": float.fromhex(r["depth_hex"]), "carrier_wave": r["carrier_wave"],
            "coupling": r["coupling"]}


def signed_ideal_envelope(phases):
    """(1 + cos(2 pi p / 2^64)) / 2 of the signed phase, made here with NumPy."""
    p = np.asarray(phases, dtype=np.uint64).astype(np.int64).astype(np.float64)
    return 0.5 + 0.5 * np.cos(2.0 * np.pi * (p / 2.0**64))


# ------------------------------------------------------ fixtures


def test_gamma_fixtures_exist_with_the_spec_values(vectors):
    order = []
    for r in vectors["gamma_samples"]:
        if r["fixture"] not in order:
            order.append(r["fixture"])
    assert tuple(order) == FIXTURES
    for name in FIXTURES:
        recipe = load_recipe(name)
        r = rows_of(vectors, name, SAMPLE_RATES[0])[0]
        assert recipe["gamma_pac"] == {
            "carrier_hz": 250, "rate_hz": int(float.fromhex(r["rate_hex"])),
            "am_depth_percent": int(float.fromhex(r["depth_hex"])),
            "carrier_wave": "sine", "coupling": "uncoupled"}, name
        assert float(recipe["length_s"]) == 10.0, name
        assert "binaural" not in recipe, name
        assert ("theta_reference" in recipe) == (name == THETA_GAMMA), name
    assert load_recipe(THETA_GAMMA)["theta_reference"] == {
        "carrier_hz": 450, "rate_hz": 6, "am_depth_percent": 75, "shape": "sine"}


def test_compile_rejected_gamma_fixtures_are_schema_valid_with_their_values():
    for name, values in REJECTED.items():
        recipe = load_recipe(name)
        g = recipe["gamma_pac"]
        assert set(g) == {"carrier_hz", "rate_hz", "am_depth_percent", "carrier_wave", "coupling"}, name
        for key, want in values.items():
            assert g[key] == want, (name, key)
        assert g["coupling"] == "uncoupled", name


def test_gamma_enum_fixtures_are_invalid_with_expected_errors():
    expected = json.loads(INVALID_EXPECTED.read_text(encoding="utf-8"))["fixtures"]
    for name, (parameter, text) in NOT_IN_ENUM.items():
        path = FIXTURES_INVALID / name
        assert path.is_file(), f"missing fixture {path} (Story 2.2)"
        recipe = json.loads(path.read_text(encoding="utf-8"))
        field = parameter.rsplit("/", 1)[1]
        assert recipe["gamma_pac"][field] == text, name
        entry = expected.get(name)
        assert entry is not None, f"{name}: no entry in invalid-expected.json"
        assert entry.get("parameter") == parameter, entry
        assert entry.get("rule") == "enum", entry
        assert entry.get("schema_keyword") == "enum", entry


# ------------------------------------------------------ reference module


def test_reference_constants(vectors):
    mod = gamma()
    assert tuple(mod.CARRIER_WAVES) == ("sine",)
    # Story 2.3 adds smooth_swell (signal spec, Coupling); Story 2.4 adds bursts (Bursts).
    assert tuple(mod.COUPLINGS) == ("uncoupled", "smooth_swell", "bursts")
    c = vectors["gamma_constants"]
    assert tuple(mod.CARRIER_WAVES) == tuple(c["modeled_carrier_waves"])
    assert tuple(mod.COUPLINGS) == tuple(vectors["burst_constants"]["couplings"])


def test_reference_envelope_is_within_1e_15_of_every_vector(vectors):
    mod = gamma()
    for r in vectors["gamma_envelopes"]:
        got = mod.envelope(int(r["phase"]))
        assert np.ndim(got) == 0, r
        assert 0.0 <= float(got) <= 1.0, r
        assert close(got, r["ideal_e"]), (r["phase"], float(got), r["ideal_e"])


def test_reference_envelope_array_form(vectors):
    mod = gamma()
    phases = np.array(sorted({int(r["phase"]) for r in vectors["gamma_envelopes"]}), dtype=np.uint64)
    got = mod.envelope(phases)
    assert isinstance(got, np.ndarray) and got.dtype == np.float64 and got.shape == phases.shape
    want = {int(r["phase"]): r["ideal_e"] for r in vectors["gamma_envelopes"]}
    for p, value in zip(phases, got):
        assert close(value, want[int(p)]), int(p)
    # The cosine of the signed phase, made here, within 1e-15 across the cycle.
    sweep = (np.arange(4096, dtype=np.uint64) * np.uint64(2**52)) + np.uint64(12345)
    assert np.max(np.abs(mod.envelope(sweep) - signed_ideal_envelope(sweep))) <= float(IDEAL_TOL)


def test_reference_render_is_within_1e_15_of_every_sample_vector(vectors):
    mod = gamma()
    renders = {}
    for r in vectors["gamma_samples"]:
        key = (r["fixture"], r["fs"])
        if key not in renders:
            total = int(r["frames"]) + EXTRA_FRAMES
            out = mod.render(spec_gamma_pac(r), r["fs"], total)
            assert isinstance(out, np.ndarray) and out.dtype == np.float64 and out.ndim == 1
            assert out.size == total
            renders[key] = out
        if r["case"] != "signal":
            continue
        assert close(renders[key][int(r["n"])], r["ideal_gamma"]), (r["fixture"], r["fs"], r["n"])


def test_reference_render_follows_the_spec_operations(vectors):
    # gamma = a * ideal_sine(phase_G), a = 1.0 - d * (1.0 - e), e from the
    # module's own envelope, in binary64, bit for bit.
    mod = gamma()
    idl = ideal()
    seen = set()
    for r in vectors["gamma_samples"]:
        key = (r["fixture"], r["fs"])
        if key in seen:
            continue
        seen.add(key)
        fs = r["fs"]
        frames = int(r["frames"])
        g = spec_gamma_pac(r)
        n = np.arange(frames, dtype=np.uint64)
        inc_g = idl.phase_increment(g["carrier_hz"], fs)
        inc_m = idl.phase_increment(g["rate_hz"], fs)
        assert inc_g == int(r["inc_carrier"]) and inc_m == int(r["inc_rate"]), key
        d = g["am_depth_percent"] / 100.0
        e = mod.envelope(n * np.uint64(inc_m))
        want = (1.0 - d * (1.0 - e)) * idl.ideal_sine(n * np.uint64(inc_g))
        got = mod.render(g, fs, frames)
        assert np.array_equal(got.view(np.uint64), want.view(np.uint64)), key


def test_reference_render_at_depth_0_is_the_unmodulated_carrier():
    mod = gamma()
    idl = ideal()
    for fs in SAMPLE_RATES:
        g = {"carrier_hz": 250, "rate_hz": 40, "am_depth_percent": 0, "carrier_wave": "sine",
             "coupling": "uncoupled"}
        got = mod.render(g, fs, fs)
        inc = np.uint64(idl.phase_increment(250.0, fs))
        want = idl.ideal_sine(np.arange(fs, dtype=np.uint64) * inc)
        assert np.array_equal(got.view(np.uint64), want.view(np.uint64)), fs


@pytest.mark.parametrize("wave, coupling", [
    ("triangle", "uncoupled"), ("softened_square", "uncoupled"), ("square", "uncoupled"),
    # smooth_swell or bursts without coupling_phase_deg is not a modeled
    # recipe either (Stories 2.3 and 2.4: render raises ValueError for it).
    ("sine", "smooth_swell"), ("sine", "bursts"), ("sine", "swell"),
])
def test_reference_rejects_what_the_spec_does_not_model(wave, coupling):
    g = {"carrier_hz": 250, "rate_hz": 40, "am_depth_percent": 25, "carrier_wave": wave,
         "coupling": coupling}
    with pytest.raises(ValueError):
        gamma().render(g, SAMPLE_RATES[0], 64)


def test_reference_gamma_does_not_implement_the_engine_polynomial(vectors):
    source = GAMMA_MODULE.read_text(encoding="utf-8").lower() if GAMMA_MODULE.is_file() else None
    assert source is not None, f"missing {GAMMA_MODULE}"
    for c in vectors["sine_coefficients"]:
        if c["power"] < 3:
            continue
        mantissa = c["hex"].lstrip("-").lower()
        assert mantissa not in source and mantissa.replace("0x", "") not in source, c["power"]
    assert "factorial" not in source
    # Implemented from the spec, not from the theta layer's code: it imports
    # no theta module.
    tree = ast.parse(GAMMA_MODULE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""] + [a.name for a in node.names]
        else:
            continue
        assert not any(n == "theta" or n.endswith(".theta") for n in names), names


def test_stub_chain_takes_its_gamma_tap_from_the_gamma_layer(vectors):
    sc = stub_chain()
    mod = gamma()
    th = theta()
    for fixture in FIXTURES:
        recipe = load_recipe(fixture)
        for fs in SAMPLE_RATES:
            frames = frames_of(vectors, fixture, fs)
            out = sc.render(FIXTURES_VALID / fixture, fs, frames=frames + EXTRA_FRAMES)
            want = mod.render(recipe["gamma_pac"], fs, frames)
            if "theta_reference" in recipe:
                theta_want = th.render(recipe["theta_reference"], fs, frames)
            else:
                theta_want = np.zeros(frames)
            where = (fixture, fs)
            for c in (0, 1):
                got = channel(out["gamma"], c)
                assert np.array_equal(got[:frames].view(np.uint64), want.view(np.uint64)), (where, c)
                assert not got[frames:].view(np.uint64).any(), (where, c, "past end")
                t = channel(out["theta"], c)[:frames]
                assert np.array_equal(t.view(np.uint64), theta_want.view(np.uint64)), (where, c)
                bus = channel(out["bus"], c)[:frames]
                assert np.array_equal(bus.view(np.uint64), (theta_want + want).view(np.uint64)), (where, c)
            # No binaural layer: join, master, and output equal the bus.
            for key in ("join", "master", "output"):
                assert np.array_equal(out[key].view(np.uint64), out["bus"].view(np.uint64)), (where, key)


def test_stub_chain_without_gamma_pac_keeps_a_zero_gamma_tap():
    sc = stub_chain()
    for name in ("stub-chain-1s-beat-6.json", "theta-sine-6hz.json", "both-layers.json"):
        out = sc.render(FIXTURES_VALID / name, SAMPLE_RATES[0], frames=SAMPLE_RATES[0])
        assert not out["gamma"].view(np.uint64).any(), name


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


DUMP_KEYS = (("theta", "theta"), ("gamma", "gamma"), ("bus", "bus"), ("output", "out"))


@pytest.fixture(scope="module")
def engine_dumps(tapdump, tmp_path_factory, vectors):
    """(fixture, fs) -> {"theta", "gamma", "bus", "output"} arrays, N + 64 frames each."""
    out = {}
    root = tmp_path_factory.mktemp("gamma-dump")
    for fixture in FIXTURES:
        load_recipe(fixture)
        for fs in SAMPLE_RATES:
            frames = frames_of(vectors, fixture, fs)
            d = root / f"{fixture}-{fs}"
            stdout = run_dump(tapdump, FIXTURES_VALID / fixture, fs, d, EXTRA_FRAMES)
            assert f"frames {frames} total {frames + EXTRA_FRAMES}" in stdout, stdout
            arrays = {key: read_f64(d / f"{name}.f64") for key, name in DUMP_KEYS}
            for key, a in arrays.items():
                assert a.size == 2 * (frames + EXTRA_FRAMES), (fixture, fs, key, a.size)
            out[(fixture, fs)] = arrays
    return out


@pytest.fixture(scope="module")
def reference_renders(vectors):
    """(fixture, fs) -> the reference stub chain render, N + 64 frames."""
    sc = stub_chain()
    out = {}
    for fixture in FIXTURES:
        load_recipe(fixture)
        for fs in SAMPLE_RATES:
            frames = frames_of(vectors, fixture, fs)
            out[(fixture, fs)] = sc.render(FIXTURES_VALID / fixture, fs, frames=frames + EXTRA_FRAMES)
    return out


@pytest.mark.parametrize("fixture", FIXTURES)
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_gamma_matches_the_reference(fixture, fs, vectors, engine_dumps, reference_renders):
    mod = rm()
    frames = frames_of(vectors, fixture, fs)
    eng = engine_dumps[(fixture, fs)]
    ref = reference_renders[(fixture, fs)]
    keys = ("gamma", "bus", "output") + (("theta",) if fixture == THETA_GAMMA else ())
    results = []
    for key in keys:
        results += mod.match_stereo(key, eng[key][:2 * frames], ref[key][:2 * frames])
    assert [r["name"] for r in results] == [f"reference match {k} {side}" for k in keys
                                             for side in ("left", "right")]
    failed = [r for r in results if r["result"] != "pass"]
    assert not failed, failed
    if fixture != THETA_GAMMA:
        assert mod.all_positive_zero(eng["theta"]), (fixture, fs)
        assert mod.all_positive_zero(ref["theta"]), (fixture, fs)
    for key, _ in DUMP_KEYS:
        assert mod.all_positive_zero(eng[key][2 * frames:]), (fixture, fs, key, "past end")


# Theta, gamma, and binaural together, made here (no stored fixture): the
# 5-sine output of the spec's error bound. A 450 Hz carrier
# amplitude-modulated at 6 Hz by the sine envelope at 75 percent depth, a
# 250 Hz sine carrier amplitude-modulated at 40 Hz at 100 percent depth
# (uncoupled), and a 400 Hz unmodulated sine in the left ear with a 406 Hz
# unmodulated sine in the right ear (a 6 Hz binaural beat), 1 s.
THETA_GAMMA_BINAURAL = {
    "schema_version": "1.0", "engine_version": "0.0.1", "seed": 42,
    "author": "Arcani test", "date": "2026-11-07",
    "rationale": "Theta, gamma, and binaural layers together, made in the test.",
    "length_s": 1, "loudness_target_lufs": -36,
    "theta_reference": {"carrier_hz": 450, "rate_hz": 6, "am_depth_percent": 75, "shape": "sine"},
    "gamma_pac": {"carrier_hz": 250, "rate_hz": 40, "am_depth_percent": 100,
                  "carrier_wave": "sine", "coupling": "uncoupled"},
    "binaural": {"carrier_left_hz": 400, "beat_rate_hz": 6},
}


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_output_with_a_binaural_layer_matches_the_reference(fs, tapdump, tmp_path):
    recipe = tmp_path / "theta-gamma-binaural.json"
    recipe.write_text(json.dumps(THETA_GAMMA_BINAURAL), encoding="utf-8")
    frames = ideal().seconds_to_samples(1.0, fs)
    d = tmp_path / "dump"
    stdout = run_dump(tapdump, recipe, fs, d, EXTRA_FRAMES)
    assert f"frames {frames} total {frames + EXTRA_FRAMES}" in stdout, stdout
    ref = stub_chain().render(recipe, fs, frames=frames + EXTRA_FRAMES)
    mod = rm()
    results = []
    for key, name in DUMP_KEYS:
        eng = read_f64(d / f"{name}.f64")
        results += mod.match_stereo(key, eng[:2 * frames], ref[key][:2 * frames])
        assert mod.all_positive_zero(eng[2 * frames:]), (fs, key, "past end")
    failed = [r for r in results if r["result"] != "pass"]
    assert not failed, failed
    # The binaural layer is really in the output: left and right differ.
    out = read_f64(d / "out.f64")[:2 * frames]
    assert not np.array_equal(channel(out, 0), channel(out, 1))


def test_engine_dump_holds_the_vector_bits(vectors, engine_dumps):
    for r in vectors["gamma_samples"]:
        e = engine_dumps[(r["fixture"], r["fs"])]
        n = int(r["n"])
        gamma_only = r["theta_carrier_hex"] == "none"
        for c in (0, 1):
            where = (r["fixture"], r["fs"], n, c)
            assert bits(e["gamma"][2 * n + c]) == int(r["gamma_bits"], 16), where
            if gamma_only:
                assert bits(e["bus"][2 * n + c]) == int(r["gamma_bits"], 16), where
                assert bits(e["output"][2 * n + c]) == int(r["gamma_bits"], 16), where
    for r in vectors["gamma_bus"]:
        e = engine_dumps[(r["fixture"], r["fs"])]
        n = int(r["n"])
        for c in (0, 1):
            where = (r["fixture"], r["fs"], n, c)
            assert bits(e["theta"][2 * n + c]) == int(r["theta_bits"], 16), where
            assert bits(e["gamma"][2 * n + c]) == int(r["gamma_bits"], 16), where
            assert bits(e["bus"][2 * n + c]) == int(r["bus_bits"], 16), where
            assert bits(e["output"][2 * n + c]) == int(r["bus_bits"], 16), where


def test_engine_gamma_tap_is_never_negative_zero(vectors, engine_dumps):
    neg = np.uint64(0x8000000000000000)
    for (fixture, fs), e in engine_dumps.items():
        assert not np.any(np.ascontiguousarray(e["gamma"]).view(np.uint64) == neg), (fixture, fs)


@pytest.mark.parametrize("fixture", FIXTURES)
def test_unmodulated_carrier_fails_the_match(fixture, vectors, reference_renders):
    # Must-fail: a 250 Hz unmodulated carrier (the ideal sine at unit
    # amplitude) against the reference gamma tap fails on every fixture.
    mod = rm()
    idl = ideal()
    for fs in SAMPLE_RATES:
        frames = frames_of(vectors, fixture, fs)
        inc = np.uint64(idl.phase_increment(250.0, fs))
        stub = idl.ideal_sine(np.arange(frames, dtype=np.uint64) * inc)
        ref = channel(reference_renders[(fixture, fs)]["gamma"], 0)[:frames]
        result = mod.match("unmodulated", stub, ref)
        assert result["result"] == "fail", (fixture, fs, result)


@pytest.mark.parametrize("fixture", FIXTURES)
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_gamma_carrier_and_rate_are_accurate(fixture, fs, vectors, engine_dumps):
    tool = freq()
    frames = frames_of(vectors, fixture, fs)
    g = load_recipe(fixture)["gamma_pac"]
    tap = channel(engine_dumps[(fixture, fs)]["gamma"], 0)[:frames]
    carrier = tool.check(f"{fixture} gamma carrier", tool.carrier_hz(tap, fs), float(g["carrier_hz"]))
    rate = tool.check(f"{fixture} gamma rate", tool.rate_hz(tap, fs), float(g["rate_hz"]))
    assert carrier["result"] == "pass", carrier
    assert rate["result"] == "pass", rate
    assert carrier["threshold"] == rate["threshold"] == accuracy_hz()


@pytest.mark.parametrize("fixture", FIXTURES)
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_gamma_depth_is_constant_at_the_recipe_value(fixture, fs, vectors, engine_dumps):
    tool = am_depth()
    frames = frames_of(vectors, fixture, fs)
    g = load_recipe(fixture)["gamma_pac"]
    for c in (0, 1):
        tap = channel(engine_dumps[(fixture, fs)]["gamma"], c)[:frames]
        result = tool.check(f"{fixture} gamma depth", tap, fs, float(g["rate_hz"]),
                            float(g["am_depth_percent"]))
        assert result["result"] == "pass", result
        assert result["row"] == "reference-match"


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_wrong_depth_fails_the_am_depth_check(fs, vectors, engine_dumps):
    # Must-fail: the reference gamma rendered 1 percent off the recipe depth,
    # and the engine 25 percent tap checked against 100 percent.
    tool = am_depth()
    mod = gamma()
    fixture = "gamma-uncoupled-40hz-25pct.json"
    frames = frames_of(vectors, fixture, fs)
    g = load_recipe(fixture)["gamma_pac"]
    off = dict(g, am_depth_percent=g["am_depth_percent"] + 1)
    doctored = mod.render(off, fs, frames)
    result = tool.check("1 percent off", doctored, fs, float(g["rate_hz"]), float(g["am_depth_percent"]))
    assert result["result"] == "fail", result
    tap = channel(engine_dumps[(fixture, fs)]["gamma"], 0)[:frames]
    result = tool.check("wrong recipe depth", tap, fs, float(g["rate_hz"]), 100.0)
    assert result["result"] == "fail", result
