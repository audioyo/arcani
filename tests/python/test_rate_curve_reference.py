"""Rate curves on the theta and gamma rates: fixtures, reference, engine match, frequency, timing (Story 2.6).

The reference renders the curved theta and gamma envelope phases from
docs/signal-spec.md, Rate curve (Reference, theta and gamma), only, in
binary64 with the ideal functions. The engine render comes from the
test-only dump arcani-tapdump (tests/tapdump/, contract in
tests/python/test_reference_match.py). Thresholds and ranges come from
tests/tables/*.tsv through the assertion call `assertions.row`; no threshold
or range is written here as a literal.

Contract with reference/rate_curve.py (NumPy, the standard library, and
reference/ only), shared by the beat rate cycle and the theta and gamma
cycles:

- `start_units(deg) -> int`: P0 by the coupling phase rule (x = deg / 360.0,
  x * 2^64 rounded to the nearest integer, ties to even, mod 2^64).
- `cycle_constants(cycle, fs) -> (p0, inc_p, k)`: P0, inc_P =
  ideal.phase_increment(1.0 / period_s, fs) (Python ints), and
  K = swing_hz * period_s / (2 * math.pi) (a float).
- `offset_cycles(cycle, fs, frames) -> ndarray`: the ideal U[n] in cycles,
  K * (cos(2 pi signed(P0) / 2^64) - cos(2 pi signed(p_P[n]) / 2^64)), float64
  of length frames; zeros when cycle is None.
- `cycles_to_units(v) -> ndarray`: float64 ndarray to uint64 ndarray by the
  spec's cycles-to-units rule (numpy.trunc, numpy.rint of the fraction times
  2^64, negatives wrapped modulo 2^64, 0 outside |v| < 2^52 and for NaN).
- `offset_units(cycle, fs, frames) -> ndarray`: cycles_to_units of
  offset_cycles, uint64; zeros when cycle is None.

reference/binaural.py keeps cycle_constants and beat_offset_cycles, now from
rate_curve, with unchanged output. reference/theta.py render reads
theta_reference.get("rate_cycle"); reference/gamma.py render reads
gamma_pac.get("rate_cycle") for the gamma envelope phase and
theta_reference.get("rate_cycle") for the coupled theta envelope phase:
phase = n * inc + offset_units mod 2^64.

Fixtures (recipes/fixtures/valid/, 120 s, no binaural layer; signal spec
Vectors: theta and gamma rate cycles): theta-cycle-sine.json and
theta-cycle-smoothed-on-off.json (a 450 Hz carrier amplitude-modulated by the
sine or smoothed on-off envelope at a theta rate that cycles over 1 to 6 Hz
every 60 s, 75 percent depth), gamma-cycle-uncoupled.json (a 250 Hz sine
carrier amplitude-modulated at a gamma rate that cycles over 30 to 60 Hz
every 60 s, 100 percent depth), swell-theta-cycle.json and
bursts-theta-cycle.json (a 450 Hz carrier amplitude-modulated by the sine
envelope at a theta rate of 4 +- 2 Hz, 75 percent, and a 250 Hz sine carrier
amplitude-modulated at 40 Hz with a smooth swell or 50 ms bursts at 0
degrees, 100 percent), gamma-cycle-swell-theta-cycle.json (the swell fixture
with the gamma rate cycling too, 45 +- 15 Hz). Compile-rejected:
theta-cycle-below-1, theta-cycle-above-6, gamma-cycle-below-30,
gamma-cycle-above-60, gamma-cycle-carrier-rule. Invalid:
theta-cycle-missing-start-phase.

Engine against reference, for every curved fixture at 44.1 and 48 kHz: the
theta, gamma, bus taps and the output pass row `reference-match` per
channel, hold the vector bits, and are +0.0 past the end. The frequency
tool's envelope phase mode reads the curved theta (sine shape) and gamma
(uncoupled) envelope rates within row `frequency-accuracy`, no phase step;
the coupling timing tool's rate-curve mode reads every swell peak and burst
center within row `coupling-timing`.

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

ACCEPTED = ("theta-cycle-sine.json", "theta-cycle-smoothed-on-off.json", "gamma-cycle-uncoupled.json",
            "swell-theta-cycle.json", "bursts-theta-cycle.json", "gamma-cycle-swell-theta-cycle.json")
CYCLE_MEMBERS = ["swing_hz", "period_s", "start_phase_deg"]
THETA_SWING = "/theta_reference/rate_cycle/swing_hz"
GAMMA_SWING = "/gamma_pac/rate_cycle/swing_hz"
# fixture -> (parameter, rule, value) of the compile rejection
REJECTED = {
    "theta-cycle-below-1.json": (THETA_SWING, "range.min", "0.99"),
    "theta-cycle-above-6.json": (THETA_SWING, "range.max", "6.01"),
    "gamma-cycle-below-30.json": (GAMMA_SWING, "range.min", "29.990000000000002"),
    "gamma-cycle-above-60.json": (GAMMA_SWING, "range.max", "60.01"),
    "gamma-cycle-carrier-rule.json": ("/gamma_pac/carrier_hz", "carrier_rule", "200"),
}
# fixture -> (layer, center, swing) of the rejected cycle (spec Implementation Notes)
REJECTED_CYCLES = {
    "theta-cycle-below-1.json": ("theta_reference", 2.0, 1.01),
    "theta-cycle-above-6.json": ("theta_reference", 4.0, 2.01),
    "gamma-cycle-below-30.json": ("gamma_pac", 40.0, 10.01),
    "gamma-cycle-above-60.json": ("gamma_pac", 50.0, 10.01),
    "gamma-cycle-carrier-rule.json": ("gamma_pac", 45.0, 10.0),
}
MISSING_START = "theta-cycle-missing-start-phase.json"
SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
EXTRA_FRAMES = 64
CYCLE = 2**64


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def rate_curve():
    _repo_on_path()
    return importlib.import_module("reference.rate_curve")


def binaural():
    _repo_on_path()
    return importlib.import_module("reference.binaural")


def theta_ref():
    _repo_on_path()
    return importlib.import_module("reference.theta")


def gamma_ref():
    _repo_on_path()
    return importlib.import_module("reference.gamma")


def ideal():
    _repo_on_path()
    return importlib.import_module("reference.ideal")


def stub_chain():
    _repo_on_path()
    return importlib.import_module("reference.stub_chain")


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


def signed(u):
    return np.asarray(u, dtype=np.uint64).view(np.int64).astype(np.float64)


def linear(row_id):
    r = table_row(row_id)
    assert r.unit == "dBFS", r
    return 10.0 ** (r.value / 20.0)


def hexf(text):
    return float.fromhex(text)


def load_recipe(name, folder=FIXTURES_VALID):
    path = folder / name
    assert path.is_file(), f"missing fixture {path} (Story 2.6)"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def vectors():
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def sample_rows(vectors, fixture, fs):
    rows = [r for r in vectors["rate_curve_samples"] if r["fixture"] == fixture and r["fs"] == fs]
    assert rows, (fixture, fs)
    return rows


def frames_of(vectors, fixture, fs):
    return int(sample_rows(vectors, fixture, fs)[0]["frames"])


def spec_layers(r):
    """(theta_reference, gamma_pac) dicts of a rate curve sample row, from the row's own values."""
    theta = None
    if r["theta_carrier_hex"] != "none":
        theta = {"carrier_hz": hexf(r["theta_carrier_hex"]), "rate_hz": hexf(r["theta_rate_hex"]),
                 "am_depth_percent": hexf(r["theta_depth_hex"]), "shape": r["theta_shape"]}
        if r["theta_swing_hex"] != "none":
            theta["rate_cycle"] = {"swing_hz": hexf(r["theta_swing_hex"]), "period_s": hexf(r["theta_period_hex"]),
                                   "start_phase_deg": hexf(r["theta_start_hex"])}
    gamma = None
    if r["gamma_carrier_hex"] != "none":
        gamma = {"carrier_hz": hexf(r["gamma_carrier_hex"]), "rate_hz": hexf(r["gamma_rate_hex"]),
                 "am_depth_percent": hexf(r["gamma_depth_hex"]), "carrier_wave": "sine",
                 "coupling": r["coupling"]}
        if r["coupling"] != "uncoupled":
            gamma["coupling_phase_deg"] = hexf(r["deg_hex"])
        if r["gamma_swing_hex"] != "none":
            gamma["rate_cycle"] = {"swing_hz": hexf(r["gamma_swing_hex"]), "period_s": hexf(r["gamma_period_hex"]),
                                   "start_phase_deg": hexf(r["gamma_start_hex"])}
    return theta, gamma


def same_values(got, want):
    """Recipe JSON values against spec values: the same keys in the same order, equal numbers."""
    assert list(got) == list(want), (list(got), list(want))
    for key, value in want.items():
        if isinstance(value, dict):
            same_values(got[key], value)
        elif isinstance(value, str):
            assert got[key] == value, (key, got[key], value)
        else:
            assert float(got[key]) == value, (key, got[key], value)


def tap_bounds(vectors):
    """(theta, gamma, bus) linear bounds of Rate curve, Error bound, theta and gamma."""
    b = linear("sine-error")
    add = float(vectors["rate_curve_constants"]["curve_add"])
    return (1.5 * b + 2.0**-47 + add,
            2.0 * b + 2.0**-46 + 2.0 * add,
            3.5 * b + 2.0**-45 + 3.0 * add)


def close(value, text, tol):
    return abs(Decimal(repr(float(value))) - Decimal(text)) <= Decimal(repr(float(tol)))


def unit_distance_cycles(a, b):
    """|a - b| of two phase-unit values as a point of the cycle, in cycles."""
    d = (int(a) - int(b)) % CYCLE
    return min(d, CYCLE - d) / 2.0**64


# ------------------------------------------------------ fixtures


def test_rate_curve_fixtures_exist_with_the_spec_values(vectors):
    order = []
    for r in vectors["rate_curve_samples"]:
        if r["fixture"] not in order:
            order.append(r["fixture"])
    assert tuple(order) == ACCEPTED
    assert vectors["rate_curve_constants"]["length_s"] == "120.0"
    for name in ACCEPTED:
        recipe = load_recipe(name)
        assert "binaural" not in recipe, name
        assert recipe["seed"] == 42 and recipe["loudness_target_lufs"] == -36, name
        assert float(recipe["length_s"]) == float(vectors["rate_curve_constants"]["length_s"]), name
        for fs in SAMPLE_RATES:
            theta, gamma = spec_layers(sample_rows(vectors, name, fs)[0])
            if theta is None:
                assert "theta_reference" not in recipe, name
            else:
                same_values(recipe["theta_reference"], theta)
            if gamma is None:
                assert "gamma_pac" not in recipe, name
            else:
                same_values(recipe["gamma_pac"], gamma)
        # rate_cycle is the last member of its layer, its members in schema order.
        for layer in ("theta_reference", "gamma_pac"):
            if layer in recipe and "rate_cycle" in recipe[layer]:
                assert list(recipe[layer])[-1] == "rate_cycle", (name, layer)
                assert list(recipe[layer]["rate_cycle"]) == CYCLE_MEMBERS, (name, layer)
    # The layer rate cycle vectors name the same curved layers.
    curved = {(r["fixture"], r["layer"]) for r in vectors["layer_rate_cycles"]}
    want = set()
    for name in ACCEPTED:
        recipe = load_recipe(name)
        for layer, short in (("theta_reference", "theta"), ("gamma_pac", "gamma")):
            if layer in recipe and "rate_cycle" in recipe[layer]:
                want.add((name, short))
    assert curved == want


def test_fixture_cycles_are_the_spec_cycles():
    # The frozen decision and Implementation Notes: theta 3.5 +- 2.5 Hz,
    # gamma 45 +- 15 Hz, coupled theta 4 +- 2 Hz, every cycle 60 s from 0 degrees.
    def cycle(name, layer):
        return load_recipe(name)[layer].get("rate_cycle")

    for name in ("theta-cycle-sine.json", "theta-cycle-smoothed-on-off.json"):
        assert load_recipe(name)["theta_reference"]["rate_hz"] == 3.5, name
        assert cycle(name, "theta_reference") == {"swing_hz": 2.5, "period_s": 60, "start_phase_deg": 0}, name
    assert load_recipe("theta-cycle-sine.json")["theta_reference"]["shape"] == "sine"
    assert load_recipe("theta-cycle-smoothed-on-off.json")["theta_reference"]["shape"] == "smoothed_on_off"
    assert cycle("gamma-cycle-uncoupled.json", "gamma_pac") == {"swing_hz": 15, "period_s": 60,
                                                                "start_phase_deg": 0}
    for name in ("swell-theta-cycle.json", "bursts-theta-cycle.json", "gamma-cycle-swell-theta-cycle.json"):
        assert load_recipe(name)["theta_reference"]["rate_hz"] == 4, name
        assert cycle(name, "theta_reference") == {"swing_hz": 2, "period_s": 60, "start_phase_deg": 0}, name
    for name in ("swell-theta-cycle.json", "bursts-theta-cycle.json"):
        assert "rate_cycle" not in load_recipe(name)["gamma_pac"], name
    assert cycle("gamma-cycle-swell-theta-cycle.json", "gamma_pac") == {"swing_hz": 15, "period_s": 60,
                                                                        "start_phase_deg": 0}


def test_compile_rejected_rate_curve_fixtures_are_schema_valid_with_their_values():
    import jsonschema

    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    for name, (layer, center, swing) in REJECTED_CYCLES.items():
        recipe = load_recipe(name)
        assert not list(validator.iter_errors(recipe)), name
        assert float(recipe["length_s"]) == 5.0, name
        node = recipe[layer]
        assert float(node["rate_hz"]) == center, name
        assert node["rate_cycle"] == {"swing_hz": swing, "period_s": 60, "start_phase_deg": 0}, name
        if layer == "theta_reference":
            assert (node["carrier_hz"], node["am_depth_percent"], node["shape"]) == (450, 75, "sine"), name
        else:
            carrier = 200 if name == "gamma-cycle-carrier-rule.json" else 250
            assert (node["carrier_hz"], node["am_depth_percent"], node["carrier_wave"], node["coupling"]) == (
                carrier, 100, "sine", "uncoupled"), name
    # The binary64 worst-case rates are past their rows; the carrier-rule
    # fixture's center passes and its maximum does not.
    theta, gamma = table_row("theta-rate"), table_row("gamma-rate")
    assert 2.0 - 1.01 < theta.min and repr(2.0 - 1.01) == REJECTED["theta-cycle-below-1.json"][2]
    assert 4.0 + 2.01 > theta.max and repr(4.0 + 2.01) == REJECTED["theta-cycle-above-6.json"][2]
    assert 40.0 - 10.01 < gamma.min and repr(40.0 - 10.01) == REJECTED["gamma-cycle-below-30.json"][2]
    assert 50.0 + 10.01 > gamma.max and repr(50.0 + 10.01) == REJECTED["gamma-cycle-above-60.json"][2]
    ratio = table_row("carrier-rule").value
    assert 200 >= ratio * 45.0 and 200 < ratio * (45.0 + 10.0)


def test_missing_start_phase_fixture_is_invalid_with_its_expected_error():
    import jsonschema

    recipe = load_recipe(MISSING_START, FIXTURES_INVALID)
    cycle = recipe["theta_reference"]["rate_cycle"]
    assert "start_phase_deg" not in cycle and {"swing_hz", "period_s"} <= set(cycle), cycle
    entry = json.loads(INVALID_EXPECTED.read_text(encoding="utf-8"))["fixtures"].get(MISSING_START)
    assert entry is not None, f"{MISSING_START}: no entry in invalid-expected.json"
    assert entry.get("parameter") == "/theta_reference/rate_cycle/start_phase_deg", entry
    assert entry.get("rule") == "required", entry
    assert entry.get("schema_keyword") == "required", entry
    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    assert {e.validator for e in validator.iter_errors(recipe)} == {"required"}


# ------------------------------------------------------ reference/rate_curve.py


def test_start_units_is_the_coupling_phase_rule(vectors):
    mod = rate_curve()
    for deg in (0, 0.01, 45, 90, 137.5, 180, 270, 359.99, 360):
        got = mod.start_units(deg)
        assert type(got) is int, type(got)
        assert got == gamma_ref().coupling_phase_units(deg), deg
    assert mod.start_units(360) == mod.start_units(0) == 0
    assert mod.start_units(90) == 2**62
    for r in vectors["layer_rate_cycles"]:
        assert mod.start_units(hexf(r["start_hex"])) == int(r["p0"]), r


def test_cycle_constants_match_every_rate_cycle_vector(vectors):
    mod = rate_curve()
    rows = list(vectors["rate_cycles"]) + list(vectors["layer_rate_cycles"])
    for r in rows:
        cycle = {"swing_hz": hexf(r["swing_hex"]), "period_s": hexf(r["period_hex"]),
                 "start_phase_deg": hexf(r["start_hex"])}
        p0, inc, k = mod.cycle_constants(cycle, r["fs"])
        assert type(p0) is int and type(inc) is int, (type(p0), type(inc))
        assert p0 == int(r["p0"]), r
        assert inc == int(r["inc_cycle"]), r
        assert inc == ideal().phase_increment(1.0 / cycle["period_s"], r["fs"]), r
        assert k == cycle["swing_hz"] * cycle["period_s"] / (2.0 * math.pi), r
        # The engine K (two roundings with the binary64 1 / (2 pi)) is within an ulp or two.
        assert abs(k - hexf(r["k_hex"])) <= 4 * math.ulp(k), (k, r["k_hex"])


def test_cycles_to_units_reproduces_every_vector_row(vectors):
    mod = rate_curve()
    rows = vectors["cycles_to_units"]
    v = np.array([float(r["v_hex"]) if r["v_hex"] in ("inf", "-inf", "nan") else hexf(r["v_hex"]) for r in rows],
                 dtype=np.float64)
    got = mod.cycles_to_units(v)
    assert isinstance(got, np.ndarray) and got.dtype == np.uint64 and got.shape == v.shape, got
    for r, u in zip(rows, got):
        assert int(u) == int(r["units"]), (r["label"], int(u), r["units"])
    # Whole cycles and v + 1 are the same point of the cycle.
    assert not mod.cycles_to_units(np.array([1.0, -1.0, 2.0, 2.0**52, 2.0**63])).any()
    a = mod.cycles_to_units(np.array([0.25, 0.125, -0.375]))
    b = mod.cycles_to_units(np.array([1.25, 1.125, 0.625]))
    assert np.array_equal(a, b)


def test_offsets_are_zero_without_a_cycle():
    mod = rate_curve()
    for fs in SAMPLE_RATES:
        u = mod.offset_cycles(None, fs, 1000)
        assert isinstance(u, np.ndarray) and u.dtype == np.float64 and u.shape == (1000,)
        assert not u.view(np.uint64).any()
        units = mod.offset_units(None, fs, 1000)
        assert isinstance(units, np.ndarray) and units.dtype == np.uint64 and units.shape == (1000,)
        assert not units.any()
        assert mod.offset_cycles(None, fs, 0).shape == (0,)


def test_offset_cycles_follow_the_rate_curve_vectors(vectors):
    # Phi(t) = r t + U(t) at the vector times, where t * fs is a whole sample:
    # the Story 2.5 Sleep cycles and the Story 2.6 theta and gamma cycles, one law.
    mod = rate_curve()
    by_cycle = {}
    for r in vectors["rate_curve"]:
        key = (r["center_hex"], r["swing_hex"], r["period_hex"], r["start_hex"])
        by_cycle.setdefault(key, []).append(r)
    assert len(by_cycle) == 6, sorted(by_cycle)
    for fs in SAMPLE_RATES:
        for (center, swing, period, start), rows in by_cycle.items():
            cycle = {"swing_hz": hexf(swing), "period_s": hexf(period), "start_phase_deg": hexf(start)}
            ns = [round(hexf(r["t_hex"]) * fs) for r in rows]
            u = mod.offset_cycles(cycle, fs, max(ns) + 1)
            assert isinstance(u, np.ndarray) and u.dtype == np.float64 and u.size == max(ns) + 1
            assert u[0] == 0.0
            for r, n in zip(rows, ns):
                t = hexf(r["t_hex"])
                assert n == t * fs
                got = hexf(center) * t + float(u[n])
                assert abs(Decimal(repr(got)) - Decimal(r["ideal_beat_cycles"])) <= Decimal("1e-9"), (
                    fs, center, swing, t, got, r["ideal_beat_cycles"])


def test_offset_units_are_the_units_of_the_offset_cycles():
    mod = rate_curve()
    for fs in SAMPLE_RATES:
        for cycle in ({"swing_hz": 2.5, "period_s": 60, "start_phase_deg": 0},
                      {"swing_hz": 15, "period_s": 60, "start_phase_deg": 270},
                      {"swing_hz": 1.5, "period_s": 60, "start_phase_deg": 90}):
            frames = 3 * fs
            want = mod.cycles_to_units(mod.offset_cycles(cycle, fs, frames))
            got = mod.offset_units(cycle, fs, frames)
            assert got.dtype == np.uint64 and np.array_equal(got, want), (fs, cycle)
            assert int(got[0]) == 0


def test_offset_cycles_follow_the_spec_operations():
    mod = rate_curve()
    for fs in SAMPLE_RATES:
        for cycle in ({"swing_hz": 2.5, "period_s": 60, "start_phase_deg": 0},
                      {"swing_hz": 15, "period_s": 60, "start_phase_deg": 137.5}):
            frames = 2 * fs
            p0, inc_p, k = mod.cycle_constants(cycle, fs)
            n = np.arange(frames, dtype=np.uint64)
            p = np.uint64(p0) + n * np.uint64(inc_p)
            c0 = math.cos(float(signed(np.uint64(p0))) * (2.0 * math.pi / 2.0**64))
            want = k * (c0 - np.cos(signed(p) * (2.0 * math.pi / 2.0**64)))
            assert np.max(np.abs(mod.offset_cycles(cycle, fs, frames) - want)) <= 1e-12, (fs, cycle)


def test_reference_offset_units_are_near_the_engine_units_of_every_vector(vectors):
    # Engine and reference U are the same point of the cycle within the
    # engine's delta = K (eps_0 + e_c) + 2^-49 K + 2^-64 plus the reference's
    # own 2^-52 K + 2^-64 (Rate curve, Error bound, theta and gamma), with
    # eps_0 <= e_c and e_c the row cycle-cosine-error read as linear.
    mod = rate_curve()
    e_c = linear("cycle-cosine-error")
    for name in ACCEPTED:
        for fs in SAMPLE_RATES:
            rows = [r for r in sample_rows(vectors, name, fs) if r["case"] == "signal"]
            theta, gamma = spec_layers(rows[0])
            frames = max(int(r["n"]) for r in rows) + 1
            for layer, key in ((theta, "theta"), (gamma, "gamma")):
                cycle = None if layer is None else layer.get("rate_cycle")
                units = mod.offset_units(cycle, fs, frames)
                if cycle is None:
                    assert all(int(r[f"{key}_u"]) == 0 for r in rows), (name, key)
                    continue
                k = hexf(rows[0][f"{key}_k_hex"])
                bound = k * 2.0 * e_c + 2.0**-49 * k + 2.0**-52 * k + 2.0**-63
                for r in rows:
                    n = int(r["n"])
                    d = unit_distance_cycles(units[n], r[f"{key}_u"])
                    assert d <= bound, (name, fs, key, n, d, bound)


# ------------------------------------------------------ reference/binaural.py unchanged


def test_binaural_takes_its_cycle_from_rate_curve_with_unchanged_output(vectors):
    rc = rate_curve()
    mod = binaural()
    for r in vectors["rate_cycles"]:
        cycle = {"swing_hz": hexf(r["swing_hex"]), "period_s": hexf(r["period_hex"]),
                 "start_phase_deg": hexf(r["start_hex"])}
        assert mod.cycle_constants(cycle, r["fs"]) == rc.cycle_constants(cycle, r["fs"]), r
    for fs in SAMPLE_RATES:
        for start in (0, 90, 270):
            b = {"carrier_left_hz": 100, "beat_rate_hz": 1.5,
                 "beat_rate_cycle": {"swing_hz": 1.5, "period_s": 60, "start_phase_deg": start}}
            frames = 2 * fs
            got = mod.beat_offset_cycles(b, fs, frames)
            assert np.array_equal(got.view(np.uint64), rc.offset_cycles(b["beat_rate_cycle"], fs, frames).view(np.uint64))
            # Bit-identical to the direct Story 2.5 computation.
            p0 = gamma_ref().coupling_phase_units(start)
            inc_p = ideal().phase_increment(1.0 / 60.0, fs)
            k = 1.5 * 60.0 / (2.0 * math.pi)
            n = np.arange(frames, dtype=np.uint64)
            p = np.uint64(p0) + n * np.uint64(inc_p)
            radians = 2.0 * math.pi / 2.0**64
            c0 = float(np.cos(signed(np.array([p0], dtype=np.uint64)) * radians)[0])
            want = k * (c0 - np.cos(signed(p) * radians))
            assert np.array_equal(got.view(np.uint64), want.view(np.uint64)), (fs, start)
            # The right ear follows from it, as in Story 2.5.
            left, right = mod.render(b, fs, frames)
            phase_c = n * np.uint64(ideal().phase_increment(101.5, fs))
            y = phase_c.astype(np.float64) / 2.0**64 + want
            y = y - np.rint(y)
            assert np.array_equal(right.view(np.uint64), np.sin(2.0 * np.pi * y).view(np.uint64)), (fs, start)


# ------------------------------------------------------ reference theta and gamma


def theta_direct(theta, fs, frames):
    """The theta tap by the spec's reference steps: phase_E = n * inc_E + offset_units."""
    rc = rate_curve()
    th = theta_ref()
    n = np.arange(frames, dtype=np.uint64)
    inc_t = np.uint64(ideal().phase_increment(float(theta["carrier_hz"]), fs))
    inc_e = np.uint64(ideal().phase_increment(float(theta["rate_hz"]), fs))
    phase_e = n * inc_e + rc.offset_units(theta.get("rate_cycle"), fs, frames)
    e = th.envelope(theta["shape"], phase_e, float(theta["rate_hz"]))
    d = float(theta["am_depth_percent"]) / 100.0
    a = 1.0 - d * (1.0 - e)
    return a * ideal().ideal_sine(n * inc_t)


def gamma_direct(gamma, theta, fs, frames):
    """The gamma tap by the spec's reference steps, both envelope phases curved."""
    rc = rate_curve()
    g = gamma_ref()
    n = np.arange(frames, dtype=np.uint64)
    inc_g = np.uint64(ideal().phase_increment(float(gamma["carrier_hz"]), fs))
    inc_m = np.uint64(ideal().phase_increment(float(gamma["rate_hz"]), fs))
    phase_m = n * inc_m + rc.offset_units(gamma.get("rate_cycle"), fs, frames)
    e = g.envelope(phase_m)
    d = float(gamma["am_depth_percent"]) / 100.0
    coupling = gamma["coupling"]
    if coupling == "uncoupled":
        a = 1.0 - d * (1.0 - e)
    else:
        rate = float(theta["rate_hz"])
        inc_e = np.uint64(ideal().phase_increment(rate, fs))
        phase_e = n * inc_e + rc.offset_units(theta.get("rate_cycle"), fs, frames)
        c = g.coupling_phase_units(gamma["coupling_phase_deg"])
        if coupling == "smooth_swell":
            s = g.swell(phase_e, c)
        else:
            # Hb and Wb at the center theta rate (Audio, 2026-11-14).
            s = g.burst(phase_e, c, g.burst_half_width_units(rate), g.burst_edge_units(rate))
        a = 1.0 - (d * s) * (1.0 - e)
    return a * ideal().ideal_sine(n * inc_g)


@pytest.mark.parametrize("fixture", ACCEPTED)
def test_reference_taps_follow_the_spec_steps(fixture, vectors):
    # 20 s of each curved fixture: the reference theta and gamma taps are the
    # spec's steps bit for bit.
    for fs in SAMPLE_RATES:
        theta, gamma = spec_layers(sample_rows(vectors, fixture, fs)[0])
        frames = 20 * fs
        if theta is not None:
            got = theta_ref().render(theta, fs, frames)
            assert np.array_equal(got.view(np.uint64), theta_direct(theta, fs, frames).view(np.uint64)), (fixture, fs)
        if gamma is not None:
            got = gamma_ref().render(gamma, fs, frames, theta)
            want = gamma_direct(gamma, theta, fs, frames)
            assert np.array_equal(got.view(np.uint64), want.view(np.uint64)), (fixture, fs)


@pytest.mark.parametrize("fixture", ACCEPTED)
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_taps_are_within_the_rate_curve_bounds_of_every_ideal_vector(fixture, fs, vectors):
    theta_bound, gamma_bound, bus_bound = tap_bounds(vectors)
    match = linear("reference-match")
    assert max(theta_bound, gamma_bound, bus_bound) < match, (theta_bound, gamma_bound, bus_bound, match)
    rows = sample_rows(vectors, fixture, fs)
    frames = frames_of(vectors, fixture, fs)
    # One channel per layer (the stub chain copies it to both channels and
    # adds the bus; tests/python/test_reference_match.py covers the chain).
    theta, gamma = spec_layers(rows[0])
    th = theta_ref().render(theta, fs, frames) if theta is not None else np.zeros(frames)
    ga = gamma_ref().render(gamma, fs, frames, theta) if gamma is not None else np.zeros(frames)
    for a in (th, ga):
        assert isinstance(a, np.ndarray) and a.dtype == np.float64 and a.shape == (frames,)
    for r in rows:
        n = int(r["n"])
        where = (fixture, fs, n)
        if r["case"] == "past_end":
            assert n >= frames, where
            continue
        assert close(th[n], r["ideal_theta"], theta_bound), (where, float(th[n]), r["ideal_theta"])
        assert close(ga[n], r["ideal_gamma"], gamma_bound), (where, float(ga[n]), r["ideal_gamma"])
        assert close(th[n] + ga[n], r["ideal_bus"], bus_bound), where
        if r["case"] == "signal":
            # The engine vector bits are within the same bounds of the ideal.
            assert close(struct.unpack("<d", struct.pack("<Q", int(r["theta_bits"], 16)))[0], r["ideal_theta"],
                         theta_bound), (fixture, fs, n)
            assert close(struct.unpack("<d", struct.pack("<Q", int(r["gamma_bits"], 16)))[0], r["ideal_gamma"],
                         gamma_bound), (fixture, fs, n)
            assert close(struct.unpack("<d", struct.pack("<Q", int(r["bus_bits"], 16)))[0], r["ideal_bus"],
                         bus_bound), (fixture, fs, n)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_swing_0_and_no_cycle_render_the_same_bytes(fs):
    # Without a cycle every layer is its earlier self: a zero swing gives
    # K = 0, U = 0, and the same bytes.
    frames = 2 * fs
    zero = {"swing_hz": 0, "period_s": 60, "start_phase_deg": 270}
    for shape in ("sine", "smoothed_on_off", "sawtooth", "reverse_saw"):
        theta = {"carrier_hz": 450, "rate_hz": 4, "am_depth_percent": 75, "shape": shape}
        a = theta_ref().render(theta, fs, frames)
        b = theta_ref().render(dict(theta, rate_cycle=zero), fs, frames)
        assert np.array_equal(a.view(np.uint64), b.view(np.uint64)), (fs, shape)
    theta = {"carrier_hz": 450, "rate_hz": 4, "am_depth_percent": 75, "shape": "sine"}
    for coupling in ("uncoupled", "smooth_swell", "bursts"):
        gamma = {"carrier_hz": 250, "rate_hz": 45, "am_depth_percent": 100, "carrier_wave": "sine",
                 "coupling": coupling}
        if coupling != "uncoupled":
            gamma["coupling_phase_deg"] = 0
        a = gamma_ref().render(gamma, fs, frames, theta)
        b = gamma_ref().render(dict(gamma, rate_cycle=zero), fs, frames, dict(theta, rate_cycle=zero))
        assert np.array_equal(a.view(np.uint64), b.view(np.uint64)), (fs, coupling)
        # A real cycle moves the gamma tap; a theta cycle moves only a coupled one.
        moved = gamma_ref().render(dict(gamma, rate_cycle=dict(zero, swing_hz=15)), fs, frames, theta)
        assert not np.array_equal(a.view(np.uint64), moved.view(np.uint64)), (fs, coupling)
        dragged = gamma_ref().render(gamma, fs, frames, dict(theta, rate_cycle=dict(zero, swing_hz=2)))
        assert np.array_equal(a.view(np.uint64), dragged.view(np.uint64)) == (coupling == "uncoupled"), (fs, coupling)


def test_reference_without_a_cycle_is_the_story_2_1_and_2_2_law():
    # The no-cycle path is n * inc mod 2^64, bit for bit.
    fs = SAMPLE_RATES[0]
    frames = fs
    n = np.arange(frames, dtype=np.uint64)
    theta = {"carrier_hz": 450, "rate_hz": 6, "am_depth_percent": 75, "shape": "sine"}
    e = theta_ref().envelope("sine", n * np.uint64(ideal().phase_increment(6.0, fs)), 6.0)
    want = (1.0 - 0.75 * (1.0 - e)) * ideal().ideal_sine(n * np.uint64(ideal().phase_increment(450.0, fs)))
    got = theta_ref().render(theta, fs, frames)
    assert np.array_equal(got.view(np.uint64), want.view(np.uint64))


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_start_phase_0_and_360_render_the_same_bytes(fs):
    frames = 2 * fs
    theta = {"carrier_hz": 450, "rate_hz": 3.5, "am_depth_percent": 75, "shape": "sine"}
    gamma = {"carrier_hz": 250, "rate_hz": 45, "am_depth_percent": 100, "carrier_wave": "sine",
             "coupling": "uncoupled"}
    for deg_a, deg_b, same in ((0, 360, True), (0, 359.99, False)):
        ta = theta_ref().render(dict(theta, rate_cycle={"swing_hz": 2.5, "period_s": 60, "start_phase_deg": deg_a}),
                                fs, frames)
        tb = theta_ref().render(dict(theta, rate_cycle={"swing_hz": 2.5, "period_s": 60, "start_phase_deg": deg_b}),
                                fs, frames)
        assert np.array_equal(ta.view(np.uint64), tb.view(np.uint64)) == same, (fs, deg_a, deg_b)
        ga = gamma_ref().render(dict(gamma, rate_cycle={"swing_hz": 15, "period_s": 60, "start_phase_deg": deg_a}),
                                fs, frames)
        gb = gamma_ref().render(dict(gamma, rate_cycle={"swing_hz": 15, "period_s": 60, "start_phase_deg": deg_b}),
                                fs, frames)
        assert np.array_equal(ga.view(np.uint64), gb.view(np.uint64)) == same, (fs, deg_a, deg_b)


@pytest.mark.parametrize("fixture", ("theta-sine-6hz.json", "gamma-uncoupled-40hz-25pct.json",
                                     "swell-sine-0deg-100pct.json", "bursts-40hz.json", "theta-gamma-uncoupled.json"))
def test_no_cycle_fixtures_keep_their_reference_bits(fixture):
    # Every earlier fixture has no rate_cycle, so its reference taps are the
    # n * inc law of Stories 2.1 to 2.4 bit for bit.
    recipe = load_recipe(fixture)
    for layer in ("theta_reference", "gamma_pac"):
        assert "rate_cycle" not in recipe.get(layer, {}), (fixture, layer)
    fs = SAMPLE_RATES[-1]
    frames = 2 * fs
    theta = recipe.get("theta_reference")
    gamma = recipe.get("gamma_pac")
    if theta is not None:
        got = theta_ref().render(theta, fs, frames)
        assert np.array_equal(got.view(np.uint64), theta_direct(theta, fs, frames).view(np.uint64)), fixture
    if gamma is not None:
        got = gamma_ref().render(gamma, fs, frames, theta)
        if gamma["coupling"] != "uncoupled" and theta is None:
            return
        assert np.array_equal(got.view(np.uint64), gamma_direct(gamma, theta, fs, frames).view(np.uint64)), fixture


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


DUMP_KEYS = (("theta", "theta"), ("gamma", "gamma"), ("bus", "bus"), ("output", "out"))


def dump_arrays(exe, recipe, fs, out_dir, extra):
    result = run_dump(exe, recipe, fs, out_dir, extra)
    arrays = {key: np.fromfile(out_dir / f"{name}.f64", dtype="<f8").astype(np.float64) for key, name in DUMP_KEYS}
    shutil.rmtree(out_dir, ignore_errors=True)
    return result.stdout, arrays


def expected_envelope_cycles(rate_hz, cycle, frames, fs):
    t = np.arange(frames, dtype=np.float64) / fs
    return freq().curve_phase(t, rate_hz, cycle)


@pytest.mark.parametrize("fixture", ACCEPTED)
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_rate_curve_fixture_matches_the_reference_and_holds_the_vector_bits(fixture, fs, vectors,
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
    keys = [k for k in ("theta", "gamma", "bus", "output")
            if not (k == "theta" and "theta_reference" not in recipe) and not (k == "gamma" and "gamma_pac" not in recipe)]
    results = []
    for key in keys:
        results += mod.match_stereo(f"{fixture} {fs} {key}", eng[key][:2 * frames], ref[key][:2 * frames])
    failed = [r for r in results if r["result"] != "pass"]
    assert not failed, failed
    if "theta_reference" not in recipe:
        assert mod.all_positive_zero(eng["theta"]), (fixture, fs)
    if "gamma_pac" not in recipe:
        assert mod.all_positive_zero(eng["gamma"]), (fixture, fs)
    for key, _ in DUMP_KEYS:
        assert mod.all_positive_zero(eng[key][2 * frames:]), (fixture, fs, key, "past end")
    for r in sample_rows(vectors, fixture, fs):
        n = int(r["n"])
        for c in (0, 1):
            w = (fixture, fs, n, c)
            assert bits(eng["theta"][2 * n + c]) == int(r["theta_bits"], 16), w
            assert bits(eng["gamma"][2 * n + c]) == int(r["gamma_bits"], 16), w
            assert bits(eng["bus"][2 * n + c]) == int(r["bus_bits"], 16), w
            assert bits(eng["output"][2 * n + c]) == int(r["bus_bits"], 16), w
    neg = np.uint64(0x8000000000000000)
    assert not np.any(np.ascontiguousarray(eng["gamma"]).view(np.uint64) == neg), (fixture, fs)


def frequency_case(fixture):
    """(tap key, recipe layer) of the envelope phase check, or None."""
    return {"theta-cycle-sine.json": ("theta", "theta_reference"),
            "gamma-cycle-uncoupled.json": ("gamma", "gamma_pac")}.get(fixture)


@pytest.mark.parametrize("fixture", ("theta-cycle-sine.json", "gamma-cycle-uncoupled.json"))
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_envelope_rate_follows_the_schedule(fixture, fs, vectors, tapdump, tmp_path):
    # The frequency tool's envelope phase mode on the engine tap of a sine-shape
    # theta or an uncoupled gamma: within row frequency-accuracy, no phase step.
    key, layer = frequency_case(fixture)
    frames = frames_of(vectors, fixture, fs)
    recipe = load_recipe(fixture)
    _, eng = dump_arrays(tapdump, FIXTURES_VALID / fixture, fs, tmp_path / "dump", 0)
    tap = channel(eng[key], 0)[:frames]
    node = recipe[layer]
    tool = freq()
    expected = expected_envelope_cycles(float(node["rate_hz"]), node["rate_cycle"], frames, fs)
    result = tool.check_envelope_phase(f"{fixture} {fs} {key} envelope", tap, fs, expected)
    assert result["row"] == "frequency-accuracy" and result["threshold"] == table_row("frequency-accuracy").value
    assert result["result"] == "pass" and result["note"] == "", result
    # Must-fail on engine output: judged without the cycle, or at another start phase.
    flat = tool.check_envelope_phase("no cycle", tap, fs,
                                     expected_envelope_cycles(float(node["rate_hz"]), None, frames, fs))
    assert flat["result"] == "fail", flat
    wrong = dict(node["rate_cycle"], start_phase_deg=90)
    miss = tool.check_envelope_phase("wrong start phase", tap, fs,
                                     expected_envelope_cycles(float(node["rate_hz"]), wrong, frames, fs))
    assert miss["result"] == "fail", miss


TIMING_CASES = {
    "swell-theta-cycle.json": ("smooth_swell", None),
    "bursts-theta-cycle.json": ("bursts", 40.0),
    "gamma-cycle-swell-theta-cycle.json": ("smooth_swell", None),
}


@pytest.mark.parametrize("fixture", sorted(TIMING_CASES))
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_coupling_follows_the_theta_curve(fixture, fs, vectors, tapdump, tmp_path):
    coupling, gamma_rate = TIMING_CASES[fixture]
    frames = frames_of(vectors, fixture, fs)
    recipe = load_recipe(fixture)
    theta = recipe["theta_reference"]
    gamma = recipe["gamma_pac"]
    assert gamma["coupling"] == coupling
    if gamma_rate is not None:
        assert float(gamma["rate_hz"]) == gamma_rate
    _, eng = dump_arrays(tapdump, FIXTURES_VALID / fixture, fs, tmp_path / "dump", 0)
    g = channel(eng["gamma"], 0)[:frames]
    th = channel(eng["theta"], 0)[:frames]
    tool = ct()
    result = tool.check(f"timing {fixture} {fs}", g, th, fs, float(theta["rate_hz"]), theta["shape"],
                        float(gamma["coupling_phase_deg"]), coupling=coupling, gamma_rate_hz=gamma_rate,
                        cycle=theta["rate_cycle"])
    assert result["row"] == "coupling-timing" and result["threshold"] == table_row("coupling-timing").value
    assert result["result"] == "pass", result
    errors = tool.timing_errors(g, th, fs, float(theta["rate_hz"]), theta["shape"],
                                float(gamma["coupling_phase_deg"]), coupling=coupling, gamma_rate_hz=gamma_rate,
                                cycle=theta["rate_cycle"])
    # About one peak per theta cycle: Phi(120 s) = 4 * 120 = 480 cycles, less the trims.
    assert errors.size >= 400, errors.size
    # Must-fail on engine output: the constant-rate mode cannot time a curved theta.
    flat = tool.check("no cycle", g, th, fs, float(theta["rate_hz"]), theta["shape"],
                      float(gamma["coupling_phase_deg"]), coupling=coupling, gamma_rate_hz=gamma_rate)
    assert flat["result"] == "fail", flat


@pytest.mark.parametrize("fixture", sorted(REJECTED))
def test_engine_rejects_the_compile_rejected_rate_curve_fixtures(fixture, tapdump, tmp_path):
    load_recipe(fixture)
    parameter, rule, value = REJECTED[fixture]
    for fs in SAMPLE_RATES:
        result = run_dump(tapdump, FIXTURES_VALID / fixture, fs, tmp_path / f"dump-{fs}", 0, expect_ok=False)
        assert result.returncode == 1, (fixture, fs, result.stdout, result.stderr)
        assert not (tmp_path / f"dump-{fs}" / "out.f64").exists(), fixture
        text = result.stdout + result.stderr
        assert f"parameter={parameter}" in text and f"rule={rule}" in text and f"value={value}" in text, (fixture, text)


def test_engine_rejects_the_missing_start_phase_fixture(tapdump, tmp_path):
    load_recipe(MISSING_START, FIXTURES_INVALID)
    result = run_dump(tapdump, FIXTURES_INVALID / MISSING_START, SAMPLE_RATES[0], tmp_path / "dump", 0,
                      expect_ok=False)
    assert result.returncode == 1, (result.stdout, result.stderr)
    text = result.stdout + result.stderr
    assert "required" in text and "/theta_reference/rate_cycle/start_phase_deg" in text, text
