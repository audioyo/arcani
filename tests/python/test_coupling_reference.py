"""Gamma PAC layer, coupled smooth swell: reference, engine match, timing, and frequency (Story 2.3).

The reference renders the coupled gamma PAC layer from docs/signal-spec.md,
Coupling, only, in binary64 with the ideal functions. The engine render
comes from the test-only dump arcani-tapdump (tests/tapdump/, contract in
tests/python/test_reference_match.py). Thresholds and ranges come from
tests/tables/*.tsv through the assertion call `assertions.row`; no
threshold or range is written here as a literal.

Contract with reference/gamma.py (NumPy, the standard library, and
reference/ only):

- `COUPLINGS == ("uncoupled", "smooth_swell", "bursts")` (Story 2.4 adds
  bursts, tested in tests/python/test_bursts_reference.py).
- `coupling_phase_units(deg) -> int`: the coupling phase rule, x = deg /
  360.0 (one rounding), x * 2^64 (exact), the nearest integer with ties to
  even, modulo 2^64; Python ints.
- `swell(theta_envelope_phase, c_units)`: the ideal swell
  s = (1 + cos(2 pi * signed(p_E - C) / 2^64)) / 2 in binary64 with NumPy,
  signed(u) in [-2^63, 2^63); an int in gives a float, a uint64 ndarray in
  gives a float64 ndarray of the same shape.
- `render(gamma_pac, fs, frames, theta_reference=None)`: with coupling
  `smooth_swell`, p_E[n] = n * inc_E mod 2^64 (inc_E =
  ideal.phase_increment(theta_reference["rate_hz"], fs), 0 when
  theta_reference is None), C from coupling_phase_deg, and
  a = 1.0 - (d * s) * (1.0 - e) in that order; smooth_swell without
  coupling_phase_deg raises ValueError. Uncoupled output is unchanged byte
  for byte and reads nothing from theta_reference.
- reference.stub_chain.render passes the recipe's theta_reference to it.

Engine against reference: the harness builds the 32 timing recipes (theta
reference: a 450 Hz carrier amplitude-modulated at 6 Hz by each of the four
shapes, 75 percent AM depth; gamma PAC: a 250 Hz sine carrier
amplitude-modulated at 40 Hz whose AM depth swells to 25 or 100 percent at
coupling phase 0, 90, 180, or 270 degrees; 5 s) in a pytest temp folder and
renders each with arcani-tapdump at 44.1 and 48 kHz. Every swell peak lies
within row `coupling-timing` of its coupling phase (timing tool on the
engine gamma and theta taps, left channel); the gamma tap, bus, and output
pass row `reference-match` per channel against reference.stub_chain.render;
the frequency tool reads the gamma carrier (250 Hz) and the gamma rate
(40 Hz, searched from the row `gamma-rate` minimum up) within row
`frequency-accuracy`. Harness shift: the reference gamma with its swell
1 ms late passes row `coupling-timing`, 3 ms late fails it, at 25 and 100
percent. Every committed swell fixture passes the reference match and holds
the vector bits; the compile-rejected ones are rejected by the dump.

The dump tests skip only when cmake is not on PATH, or when Windows
application control blocks the binary (OSError winerror 4551 or 1260).
"""

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
PHASES = (0, 90, 180, 270)
DEPTHS = (25, 100)
COUPLED = ("swell-sine-0deg-100pct.json", "swell-sawtooth-90deg-25pct.json",
           "swell-smoothed-on-off-180deg-100pct.json", "swell-reverse-saw-270deg-25pct.json")
DEPTH_0_NO_THETA = "swell-gamma-depth-0-no-theta.json"
ACCEPTED = COUPLED + (DEPTH_0_NO_THETA,)
REJECTED = {
    "swell-no-theta.json": ("/gamma_pac/coupling", "coupled gamma needs a theta reference with AM depth"),
    "swell-theta-depth-0.json": ("/gamma_pac/coupling", "coupled gamma needs a theta reference with AM depth"),
    "swell-no-coupling-phase.json": ("/gamma_pac/coupling_phase_deg", "coupled gamma needs a coupling phase"),
    "uncoupled-with-coupling-phase.json": ("/gamma_pac/coupling_phase_deg", "coupling phase needs coupled gamma"),
}
THETA = {"carrier_hz": 450, "rate_hz": 6, "am_depth_percent": 75}
SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
EXTRA_FRAMES = 64
CYCLE = 2**64
IDEAL_TOL = Decimal("1e-15")
LENGTH_S = 5


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def gamma():
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


def ct():
    return importlib.import_module("assertions.coupling_timing")


def bits(x):
    return struct.unpack("<Q", struct.pack("<d", float(x)))[0]


def channel(stereo, c):
    return np.ascontiguousarray(np.asarray(stereo)[c::2])


def close(value, text):
    return abs(Decimal(repr(float(value))) - Decimal(text)) <= IDEAL_TOL


def accuracy_hz():
    r = table_row("frequency-accuracy")
    assert r.unit == "Hz", r
    return r.value


def gamma_rate_floor_hz():
    r = table_row("gamma-rate")
    assert r.kind == "ranges" and r.unit == "Hz", r
    return r.min


def timing_ms():
    r = table_row("coupling-timing")
    assert r.unit == "ms", r
    return r.value


def load_recipe(name):
    path = FIXTURES_VALID / name
    assert path.is_file(), f"missing fixture {path} (Story 2.3)"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def vectors():
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def swell_rows(vectors, fixture, fs):
    rows = [r for r in vectors["swell_samples"] if r["fixture"] == fixture and r["fs"] == fs]
    assert rows, (fixture, fs)
    return rows


def frames_of(vectors, fixture, fs):
    return int(swell_rows(vectors, fixture, fs)[0]["frames"])


def spec_layers(r):
    """(gamma_pac, theta_reference or None) of a swell sample row, from the row's own values."""
    g = {"carrier_hz": float.fromhex(r["carrier_hex"]), "rate_hz": float.fromhex(r["rate_hex"]),
         "am_depth_percent": float.fromhex(r["depth_hex"]), "carrier_wave": r["carrier_wave"],
         "coupling": r["coupling"], "coupling_phase_deg": float.fromhex(r["deg_hex"])}
    if r["theta_carrier_hex"] == "none":
        return g, None
    t = {"carrier_hz": float.fromhex(r["theta_carrier_hex"]), "rate_hz": float.fromhex(r["theta_rate_hex"]),
         "am_depth_percent": float.fromhex(r["theta_depth_hex"]), "shape": r["theta_shape"]}
    return g, t


def timing_recipe(shape, phase, depth, coupling="smooth_swell"):
    gamma_pac = {"carrier_hz": 250, "rate_hz": 40, "am_depth_percent": depth, "carrier_wave": "sine",
                 "coupling": coupling}
    if phase is not None:
        gamma_pac["coupling_phase_deg"] = phase
    return {
        "schema_version": "1.0", "engine_version": "0.0.1", "seed": 42,
        "author": "Arcani test", "date": "2026-11-10",
        "rationale": "Coupling timing recipe, made in the test.",
        "length_s": LENGTH_S, "loudness_target_lufs": -36,
        "theta_reference": dict(THETA, shape=shape),
        "gamma_pac": gamma_pac,
    }


def write_recipe(folder, name, recipe):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")
    return path


# ------------------------------------------------------ fixtures


def test_swell_fixtures_exist_with_the_spec_values(vectors):
    order = []
    for r in vectors["swell_samples"]:
        if r["fixture"] not in order:
            order.append(r["fixture"])
    assert tuple(order) == ACCEPTED
    for name in ACCEPTED:
        recipe = load_recipe(name)
        r = swell_rows(vectors, name, SAMPLE_RATES[0])[0]
        g, t = spec_layers(r)
        assert recipe["gamma_pac"] == {
            "carrier_hz": 250, "rate_hz": 40, "am_depth_percent": int(g["am_depth_percent"]),
            "carrier_wave": "sine", "coupling": "smooth_swell",
            "coupling_phase_deg": int(g["coupling_phase_deg"])}, name
        assert list(recipe["gamma_pac"]) == ["carrier_hz", "rate_hz", "am_depth_percent", "carrier_wave",
                                             "coupling", "coupling_phase_deg"], name
        assert float(recipe["length_s"]) == float(LENGTH_S), name
        assert recipe["seed"] == 42 and recipe["loudness_target_lufs"] == -36, name
        assert "binaural" not in recipe, name
        if t is None:
            assert "theta_reference" not in recipe, name
        else:
            assert recipe["theta_reference"] == dict(THETA, shape=t["shape"]), name
    assert load_recipe(DEPTH_0_NO_THETA)["gamma_pac"]["am_depth_percent"] == 0
    assert load_recipe(DEPTH_0_NO_THETA)["gamma_pac"]["coupling_phase_deg"] == 90


def test_compile_rejected_swell_fixtures_are_schema_valid_with_their_values():
    import jsonschema

    schema = json.loads((REPO_ROOT / "recipes" / "recipe.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    base = load_recipe("swell-sine-0deg-100pct.json")
    for name in REJECTED:
        recipe = load_recipe(name)
        assert not list(validator.iter_errors(recipe)), name
    no_theta = load_recipe("swell-no-theta.json")
    assert "theta_reference" not in no_theta and no_theta["gamma_pac"] == base["gamma_pac"]
    depth_0 = load_recipe("swell-theta-depth-0.json")
    assert depth_0["theta_reference"]["am_depth_percent"] == 0
    assert depth_0["gamma_pac"] == base["gamma_pac"]
    no_phase = load_recipe("swell-no-coupling-phase.json")
    assert no_phase["gamma_pac"]["coupling"] == "smooth_swell"
    assert "coupling_phase_deg" not in no_phase["gamma_pac"]
    assert no_phase["theta_reference"] == base["theta_reference"]
    unc = load_recipe("uncoupled-with-coupling-phase.json")
    assert unc["gamma_pac"]["coupling"] == "uncoupled" and unc["gamma_pac"]["coupling_phase_deg"] == 90


def test_phase_as_text_fixture_is_invalid_with_its_expected_error():
    name = "gamma-coupling-phase-as-string.json"
    path = FIXTURES_INVALID / name
    assert path.is_file(), f"missing fixture {path} (Story 2.3)"
    recipe = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(recipe["gamma_pac"]["coupling_phase_deg"], str), recipe
    entry = json.loads(INVALID_EXPECTED.read_text(encoding="utf-8"))["fixtures"].get(name)
    assert entry is not None, f"{name}: no entry in invalid-expected.json"
    assert entry.get("parameter") == "/gamma_pac/coupling_phase_deg", entry
    assert entry.get("rule") == "type", entry
    assert entry.get("schema_keyword") == "type", entry


# ------------------------------------------------------ reference module


def test_reference_couplings(vectors):
    mod = gamma()
    assert tuple(mod.COUPLINGS) == ("uncoupled", "smooth_swell", "bursts")
    assert tuple(mod.COUPLINGS) == tuple(vectors["burst_constants"]["couplings"])
    # The Story 2.3 record keeps its two couplings.
    assert tuple(vectors["coupling_constants"]["couplings"]) == ("uncoupled", "smooth_swell")


def test_reference_coupling_phase_rule_matches_every_vector(vectors):
    mod = gamma()
    for r in vectors["coupling_phases"]:
        deg = float.fromhex(r["deg_hex"])
        assert deg / 360.0 == float.fromhex(r["x_hex"]), r
        got = mod.coupling_phase_units(deg)
        assert type(got) is int, type(got)
        assert got == int(r["c_units"]), (r["deg_hex"], got, r["c_units"])
    assert mod.coupling_phase_units(360.0) == mod.coupling_phase_units(0.0) == 0


def test_reference_swell_is_within_1e_15_of_every_vector(vectors):
    mod = gamma()
    for r in vectors["swells"]:
        assert mod.coupling_phase_units(float.fromhex(r["deg_hex"])) == int(r["c_units"]), r
        got = mod.swell(int(r["phase_theta_envelope"]), int(r["c_units"]))
        assert np.ndim(got) == 0, r
        assert 0.0 <= float(got) <= 1.0, r
        assert close(got, r["ideal_s"]), (r, float(got))


def test_reference_swell_array_form():
    mod = gamma()
    p = (np.arange(4096, dtype=np.uint64) * np.uint64(2**52)) + np.uint64(98765)
    for c in (0, 1, 2**62, 2**63, 3 * 2**62, CYCLE - 1):
        got = mod.swell(p, c)
        assert isinstance(got, np.ndarray) and got.dtype == np.float64 and got.shape == p.shape
        u = (p - np.uint64(c)).view(np.int64).astype(np.float64)
        want = 0.5 + 0.5 * np.cos(2.0 * np.pi * (u / 2.0**64))
        assert np.max(np.abs(got - want)) <= float(IDEAL_TOL), c
        # Peak at C, trough half a cycle on.
        assert mod.swell(c, c) == 1.0
        assert mod.swell((c + 2**63) % CYCLE, c) <= float(IDEAL_TOL)


def test_reference_render_is_within_1e_15_of_every_swell_vector(vectors):
    mod = gamma()
    renders = {}
    for r in vectors["swell_samples"]:
        key = (r["fixture"], r["fs"])
        if key not in renders:
            g, t = spec_layers(r)
            total = int(r["frames"]) + EXTRA_FRAMES
            out = mod.render(g, r["fs"], total, theta_reference=t)
            assert isinstance(out, np.ndarray) and out.dtype == np.float64 and out.ndim == 1
            assert out.size == total
            renders[key] = out
        if r["case"] != "signal":
            continue
        n = int(r["n"])
        assert close(renders[key][n], r["ideal_gamma"]), (r["fixture"], r["fs"], n)


def test_reference_render_follows_the_spec_operations(vectors):
    mod = gamma()
    idl = ideal()
    seen = set()
    for r in vectors["swell_samples"]:
        key = (r["fixture"], r["fs"])
        if key in seen:
            continue
        seen.add(key)
        fs = r["fs"]
        frames = int(r["frames"])
        g, t = spec_layers(r)
        n = np.arange(frames, dtype=np.uint64)
        inc_g = idl.phase_increment(g["carrier_hz"], fs)
        inc_m = idl.phase_increment(g["rate_hz"], fs)
        inc_e = idl.phase_increment(t["rate_hz"], fs) if t is not None else 0
        assert (inc_g, inc_m, inc_e) == (int(r["inc_carrier"]), int(r["inc_rate"]),
                                         int(r["inc_theta_envelope"])), key
        c = mod.coupling_phase_units(g["coupling_phase_deg"])
        assert c == int(r["c_units"]), key
        d = g["am_depth_percent"] / 100.0
        s = mod.swell(n * np.uint64(inc_e), c)
        e = mod.envelope(n * np.uint64(inc_m))
        want = (1.0 - (d * s) * (1.0 - e)) * idl.ideal_sine(n * np.uint64(inc_g))
        got = mod.render(g, fs, frames, theta_reference=t)
        assert np.array_equal(got.view(np.uint64), want.view(np.uint64)), key


def test_reference_swell_needs_a_coupling_phase():
    g = {"carrier_hz": 250, "rate_hz": 40, "am_depth_percent": 25, "carrier_wave": "sine",
         "coupling": "smooth_swell"}
    t = dict(THETA, shape="sine")
    with pytest.raises(ValueError):
        gamma().render(g, SAMPLE_RATES[0], 64, theta_reference=t)
    # Story 2.4 models bursts (tests/python/test_bursts_reference.py).
    for coupling in ("burst", "swell", "Smooth_swell"):
        with pytest.raises(ValueError):
            gamma().render(dict(g, coupling=coupling, coupling_phase_deg=90), SAMPLE_RATES[0], 64,
                           theta_reference=t)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_uncoupled_reads_nothing_from_the_theta_reference(fs):
    mod = gamma()
    g = {"carrier_hz": 250, "rate_hz": 40, "am_depth_percent": 100, "carrier_wave": "sine",
         "coupling": "uncoupled"}
    alone = mod.render(g, fs, fs)
    for shape in SHAPES:
        with_theta = mod.render(g, fs, fs, theta_reference=dict(THETA, shape=shape))
        assert np.array_equal(alone.view(np.uint64), with_theta.view(np.uint64)), shape


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_coupled_reads_only_the_theta_rate(fs):
    mod = gamma()
    g = {"carrier_hz": 250, "rate_hz": 40, "am_depth_percent": 100, "carrier_wave": "sine",
         "coupling": "smooth_swell", "coupling_phase_deg": 90}
    base = mod.render(g, fs, fs, theta_reference=dict(THETA, shape="sine"))
    for other in ({"carrier_hz": 300, "rate_hz": 6, "am_depth_percent": 25, "shape": "sawtooth"},
                  {"carrier_hz": 100, "rate_hz": 6, "am_depth_percent": 100, "shape": "reverse_saw"}):
        got = mod.render(g, fs, fs, theta_reference=other)
        assert np.array_equal(base.view(np.uint64), got.view(np.uint64)), other
    slower = mod.render(g, fs, fs, theta_reference=dict(THETA, rate_hz=5, shape="sine"))
    assert not np.array_equal(base.view(np.uint64), slower.view(np.uint64))


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_coupled_depth_0_is_the_unmodulated_carrier(fs):
    mod = gamma()
    idl = ideal()
    inc = np.uint64(idl.phase_increment(250.0, fs))
    want = idl.ideal_sine(np.arange(fs, dtype=np.uint64) * inc)
    g = {"carrier_hz": 250, "rate_hz": 40, "am_depth_percent": 0, "carrier_wave": "sine",
         "coupling": "smooth_swell", "coupling_phase_deg": 90}
    for t in (None, dict(THETA, shape="sawtooth")):
        got = mod.render(g, fs, fs, theta_reference=t)
        assert np.array_equal(got.view(np.uint64), want.view(np.uint64)), t


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_phase_0_and_360_render_the_same_bytes(fs):
    mod = gamma()
    g = {"carrier_hz": 250, "rate_hz": 40, "am_depth_percent": 100, "carrier_wave": "sine",
         "coupling": "smooth_swell"}
    t = dict(THETA, shape="sine")
    zero = mod.render(dict(g, coupling_phase_deg=0), fs, fs, theta_reference=t)
    full = mod.render(dict(g, coupling_phase_deg=360), fs, fs, theta_reference=t)
    assert np.array_equal(zero.view(np.uint64), full.view(np.uint64))


def test_stub_chain_passes_the_theta_reference_to_the_gamma_layer(vectors):
    sc = stub_chain()
    mod = gamma()
    th = theta()
    for fixture in ACCEPTED:
        recipe = load_recipe(fixture)
        for fs in SAMPLE_RATES:
            frames = frames_of(vectors, fixture, fs)
            out = sc.render(FIXTURES_VALID / fixture, fs, frames=frames + EXTRA_FRAMES)
            t = recipe.get("theta_reference")
            want = mod.render(recipe["gamma_pac"], fs, frames, theta_reference=t)
            theta_want = th.render(t, fs, frames) if t is not None else np.zeros(frames)
            for c in (0, 1):
                got = channel(out["gamma"], c)
                assert np.array_equal(got[:frames].view(np.uint64), want.view(np.uint64)), (fixture, fs, c)
                assert not got[frames:].view(np.uint64).any(), (fixture, fs, c, "past end")
                bus = channel(out["bus"], c)[:frames]
                assert np.array_equal(bus.view(np.uint64), (theta_want + want).view(np.uint64)), (fixture, fs)
            for key in ("join", "master", "output"):
                assert np.array_equal(out[key].view(np.uint64), out["bus"].view(np.uint64)), (fixture, key)


def test_stub_chain_bus_is_within_1e_15_of_every_ideal_bus(vectors):
    sc = stub_chain()
    renders = {}
    for r in vectors["swell_samples"]:
        if r["case"] != "signal":
            continue
        key = (r["fixture"], r["fs"])
        if key not in renders:
            renders[key] = sc.render(FIXTURES_VALID / r["fixture"], r["fs"])
        n = int(r["n"])
        for c in (0, 1):
            assert close(renders[key]["bus"][2 * n + c], r["ideal_bus"]), (key, n, c)
            assert close(renders[key]["gamma"][2 * n + c], r["ideal_gamma"]), (key, n, c)


# ------------------------------------------------------ harness shift (reference only)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("depth", DEPTHS)
@pytest.mark.parametrize("phase", (0, 270))
def test_reference_swell_shifted_1_ms_passes_and_3_ms_fails(fs, shape, depth, phase):
    # The shift is made in the harness: the reference gamma rendered with its
    # coupling phase moved by the shift's share of a theta cycle, so only the
    # swell moves; the gamma carrier and envelope stay where they were.
    mod = gamma()
    tool = ct()
    frames = ideal().seconds_to_samples(float(LENGTH_S), fs)
    t = dict(THETA, shape=shape)
    theta_tap = theta().render(t, fs, frames)
    g = {"carrier_hz": 250, "rate_hz": 40, "am_depth_percent": depth, "carrier_wave": "sine",
         "coupling": "smooth_swell", "coupling_phase_deg": phase}
    on_time = mod.render(g, fs, frames, theta_reference=t)
    result = tool.check("on time", on_time, theta_tap, fs, float(THETA["rate_hz"]), shape, float(phase))
    assert result["result"] == "pass", result
    for shift_ms, verdict in ((1.0, "pass"), (3.0, "fail")):
        deg = (phase + shift_ms / 1000.0 * THETA["rate_hz"] * 360.0) % 360.0
        moved = mod.render(dict(g, coupling_phase_deg=deg), fs, frames, theta_reference=t)
        result = tool.check(f"shifted {shift_ms} ms", moved, theta_tap, fs, float(THETA["rate_hz"]), shape,
                            float(phase))
        assert result["result"] == verdict, (shift_ms, result)
        assert result["row"] == "coupling-timing" and result["threshold"] == timing_ms()
        assert abs(result["measured"] - shift_ms) < table_row("coupling-timing-calibration").value, result


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
                                capture_output=True, text=True, timeout=300)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the dump (winerror {e.winerror})")
        raise
    if expect_ok:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


def read_f64(path):
    return np.fromfile(path, dtype="<f8").astype(np.float64)


DUMP_KEYS = (("theta", "theta"), ("gamma", "gamma"), ("bus", "bus"), ("output", "out"))


def dump_arrays(exe, recipe, fs, out_dir, extra):
    result = run_dump(exe, recipe, fs, out_dir, extra)
    arrays = {key: read_f64(out_dir / f"{name}.f64") for key, name in DUMP_KEYS}
    shutil.rmtree(out_dir, ignore_errors=True)
    return result.stdout, arrays


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize("depth", DEPTHS)
def test_engine_timing_render(fs, shape, phase, depth, tapdump, tmp_path):
    """One of the 32 timing recipes at one rate: timing, reference match, carrier and rate."""
    recipe = write_recipe(tmp_path / "recipes", f"timing-{shape}-{phase}deg-{depth}pct.json",
                          timing_recipe(shape, phase, depth))
    frames = ideal().seconds_to_samples(float(LENGTH_S), fs)
    stdout, eng = dump_arrays(tapdump, recipe, fs, tmp_path / "dump", 0)
    assert f"frames {frames} total {frames}" in stdout, stdout
    where = (shape, phase, depth, fs)

    # Every swell peak lies at its coupling phase, from the two taps alone.
    gamma_left = channel(eng["gamma"], 0)
    theta_left = channel(eng["theta"], 0)
    timing = ct().check(f"timing {where}", gamma_left, theta_left, fs, float(THETA["rate_hz"]), shape,
                        float(phase))
    assert timing["result"] == "pass", timing
    assert timing["row"] == "coupling-timing"

    # Engine against the reference, per channel.
    ref = stub_chain().render(recipe, fs)
    results = []
    for key in ("gamma", "bus", "output"):
        results += rm().match_stereo(key, eng[key][:2 * frames], ref[key][:2 * frames])
    failed = [r for r in results if r["result"] != "pass"]
    assert not failed, (where, failed)

    # The gamma carrier and the gamma rate read within row frequency-accuracy.
    tool = freq()
    carrier = tool.check(f"gamma carrier {where}", tool.carrier_hz(gamma_left, fs), 250.0)
    rate = tool.check(f"gamma rate {where}", tool.rate_hz(gamma_left, fs, min_hz=gamma_rate_floor_hz()), 40.0)
    assert carrier["result"] == "pass", carrier
    assert rate["result"] == "pass", rate
    assert carrier["threshold"] == rate["threshold"] == accuracy_hz()

    # The coupled gamma tap is never -0.0.
    neg = np.uint64(0x8000000000000000)
    assert not np.any(np.ascontiguousarray(eng["gamma"]).view(np.uint64) == neg), where


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("phase", (359.99, 0.01))
def test_engine_render_at_a_rounded_coupling_phase(fs, phase, tapdump, tmp_path):
    """A coupling phase whose C needs rounding: engine and reference agree, timing holds."""
    # deg / 360 rounds once for both; for 0.01 the product x * 2^64 also has a
    # fraction, so C rounds again. Neither is a multiple of 90 degrees.
    c = gamma().coupling_phase_units(phase)
    assert c % 2**62 != 0, c
    recipe = write_recipe(tmp_path / "recipes", f"timing-sine-{phase}deg-100pct.json",
                          timing_recipe("sine", phase, 100))
    frames = ideal().seconds_to_samples(float(LENGTH_S), fs)
    _, eng = dump_arrays(tapdump, recipe, fs, tmp_path / "dump", 0)
    where = (phase, fs)
    timing = ct().check(f"timing {where}", channel(eng["gamma"], 0), channel(eng["theta"], 0), fs,
                        float(THETA["rate_hz"]), "sine", float(phase))
    assert timing["result"] == "pass", timing
    ref = stub_chain().render(recipe, fs)
    results = []
    for key in ("gamma", "bus", "output"):
        results += rm().match_stereo(key, eng[key][:2 * frames], ref[key][:2 * frames])
    failed = [r for r in results if r["result"] != "pass"]
    assert not failed, (where, failed)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_uncoupled_timing_recipe_fails_the_timing_check(fs, tapdump, tmp_path):
    # Must-fail on engine output: the same layers with an uncoupled gamma
    # (constant AM depth) have no swell peak at the phase.
    recipe = write_recipe(tmp_path / "recipes", "timing-uncoupled.json",
                          timing_recipe("sine", None, 100, coupling="uncoupled"))
    _, eng = dump_arrays(tapdump, recipe, fs, tmp_path / "dump", 0)
    result = ct().check("uncoupled", channel(eng["gamma"], 0), channel(eng["theta"], 0), fs,
                        float(THETA["rate_hz"]), "sine", 90.0)
    assert result["result"] == "fail", result


@pytest.mark.parametrize("fixture", ACCEPTED)
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_swell_fixture_matches_the_reference_and_holds_the_vector_bits(fixture, fs, vectors,
                                                                              tapdump, tmp_path):
    frames = frames_of(vectors, fixture, fs)
    load_recipe(fixture)
    stdout, eng = dump_arrays(tapdump, FIXTURES_VALID / fixture, fs, tmp_path / "dump", EXTRA_FRAMES)
    assert f"frames {frames} total {frames + EXTRA_FRAMES}" in stdout, stdout
    for key, a in eng.items():
        assert a.size == 2 * (frames + EXTRA_FRAMES), (fixture, fs, key, a.size)
    ref = stub_chain().render(FIXTURES_VALID / fixture, fs, frames=frames + EXTRA_FRAMES)
    mod = rm()
    has_theta = fixture != DEPTH_0_NO_THETA
    keys = ("gamma", "bus", "output") + (("theta",) if has_theta else ())
    results = []
    for key in keys:
        results += mod.match_stereo(key, eng[key][:2 * frames], ref[key][:2 * frames])
    failed = [r for r in results if r["result"] != "pass"]
    assert not failed, failed
    if not has_theta:
        assert mod.all_positive_zero(eng["theta"]), (fixture, fs)
    for key, _ in DUMP_KEYS:
        assert mod.all_positive_zero(eng[key][2 * frames:]), (fixture, fs, key, "past end")
    for r in swell_rows(vectors, fixture, fs):
        n = int(r["n"])
        for c in (0, 1):
            w = (fixture, fs, n, c)
            assert bits(eng["gamma"][2 * n + c]) == int(r["gamma_bits"], 16), w
            assert bits(eng["theta"][2 * n + c]) == int(r["theta_bits"], 16), w
            assert bits(eng["bus"][2 * n + c]) == int(r["bus_bits"], 16), w
            assert bits(eng["output"][2 * n + c]) == int(r["bus_bits"], 16), w


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_depth_0_swell_equals_uncoupled_depth_0_bit_for_bit(fs, tapdump, tmp_path):
    recipe = load_recipe(DEPTH_0_NO_THETA)
    uncoupled = dict(recipe, gamma_pac={k: v for k, v in recipe["gamma_pac"].items()
                                        if k != "coupling_phase_deg"})
    uncoupled["gamma_pac"]["coupling"] = "uncoupled"
    path = write_recipe(tmp_path / "recipes", "uncoupled-depth-0.json", uncoupled)
    _, swell = dump_arrays(tapdump, FIXTURES_VALID / DEPTH_0_NO_THETA, fs, tmp_path / "a", 0)
    _, plain = dump_arrays(tapdump, path, fs, tmp_path / "b", 0)
    for key, _ in DUMP_KEYS:
        assert np.array_equal(swell[key].view(np.uint64), plain[key].view(np.uint64)), (fs, key)


@pytest.mark.parametrize("fixture", sorted(REJECTED))
def test_engine_rejects_the_compile_rejected_swell_fixtures(fixture, tapdump, tmp_path):
    load_recipe(fixture)
    parameter, rule = REJECTED[fixture]
    for fs in SAMPLE_RATES:
        result = run_dump(tapdump, FIXTURES_VALID / fixture, fs, tmp_path / f"dump-{fs}", 0, expect_ok=False)
        assert result.returncode == 1, (fixture, fs, result.stdout, result.stderr)
        assert not (tmp_path / f"dump-{fs}" / "gamma.f64").exists(), fixture
        text = result.stdout + result.stderr
        assert rule in text or parameter in text, (fixture, text)
