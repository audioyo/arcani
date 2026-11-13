"""Gamma PAC layer, coupled 50 ms bursts: reference, engine match, spectrum, clicks, and timing (Story 2.4).

The reference renders the burst gamma PAC layer from docs/signal-spec.md,
Bursts, only, in binary64 with the ideal functions. The engine render comes
from the test-only dump arcani-tapdump (tests/tapdump/, contract in
tests/python/test_reference_match.py). Thresholds and ranges come from
tests/tables/*.tsv through the assertion call `assertions.row`; no threshold
or range is written here as a literal.

Contract with reference/gamma.py (Story 2.4 spec, Implementation Notes;
NumPy, the standard library, and reference/ only):

- `COUPLINGS == ("uncoupled", "smooth_swell", "bursts")`, the vectors'
  `burst_constants.couplings`.
- `BURST_WIDTH_MS` and `BURST_EDGE_MS`: 50.0 and 10.0, the vectors'
  `burst_constants` and rows `burst-width` and `burst-edge`.
- `burst_half_width_units(rate_hz)` (Hb) and `burst_edge_units(rate_hz)`
  (Wb), Python ints: w = (50.0 / 1000.0 / 2) * rate_hz (binary64), then
  w * 2^64 (exact), the nearest integer, ties to even; Wb likewise with
  10.0 / 1000.0.
- `burst(theta_envelope_phase, c_units, hb_units, wb_units)`: the ideal
  gate. u = p_E - C mod 2^64, m = u when u < 2^63 else 2^64 - u; g = 1.0
  when m <= Hb - Wb, (1 + cos(pi * r)) / 2 with r = double(m - (Hb - Wb)) /
  double(Wb) when m < Hb, else 0.0; segments by exact integer comparisons.
  An int phase gives a float, a uint64 ndarray a float64 ndarray of the
  same shape.
- `render(gamma_pac, fs, frames, theta_reference=None)` with coupling
  `bursts`: p_E = n * inc_E mod 2^64 from theta_reference["rate_hz"] as for
  the swell, C by the coupling phase rule, Hb and Wb at the theta rate
  (without a theta reference p_E = 0 and Hb = Wb = 0), and
  a = 1.0 - (d * g) * (1.0 - e) in that order with e the free-running gamma
  envelope; bursts without coupling_phase_deg raises ValueError.

Fixtures (recipes/fixtures/valid/): bursts-40hz.json, bursts-45hz.json,
bursts-60hz.json: a 450 Hz carrier amplitude-modulated at 6 Hz by the sine
envelope, 75 percent AM depth, and a 250 Hz sine carrier amplitude-modulated
at 40, 45, or 60 Hz, 100 percent AM depth, coupling bursts at 0 degrees; 5 s.
Schema-valid, compile-rejected: bursts-no-theta.json (no theta reference)
and bursts-no-coupling-phase.json (no coupling_phase_deg).

Spectrum (research figure match, Audio 2026-11-13): the worst gamma line at
or above 394 Hz (the 444 Hz theta line less the 50 Hz spacing placeholder)
equals the research run's -51.3 dB within row `spectrum-level` at 60 Hz, and
is no louder than -51.3 dB at 40 and 45 Hz; the research run's figure
(-57.2, -58.1, -51.3 dB) is printed beside each measured one. Must-fail made
here with NumPy: a carrier-gated rectangular 40 Hz burst (the carrier silent
between bursts, no edges) shows about -21 dB there and fails the click tool.

Engine against reference: every burst fixture at 44.1 and 48 kHz passes row
`reference-match` per channel (gamma tap, theta tap, bus, output), holds the
vector bits, passes the click tool, and meets the research figure match on
its gamma tap. The timing set (4 theta shapes x coupling phase 0, 90, 180,
270 degrees x gamma depth 25, 100 percent, gamma 40 Hz, theta 450 Hz 6 Hz 75
percent, 5 s) is built in a pytest temp folder; every burst center lies
within row `coupling-timing`.

The dump tests skip only when cmake is not on PATH, or when Windows
application control blocks the binary (OSError winerror 4551 or 1260).
"""

import importlib
import json
import math
import os
import re
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
SIGNAL_SPEC = REPO_ROOT / "docs" / "signal-spec.md"
FIXTURES_VALID = REPO_ROOT / "recipes" / "fixtures" / "valid"
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
GAMMA_RATES = (40, 45, 60)
ACCEPTED = ("bursts-40hz.json", "bursts-45hz.json", "bursts-60hz.json")
REJECTED = {
    "bursts-no-theta.json": ("/gamma_pac/coupling", "coupled gamma needs a theta reference with AM depth",
                             "theta_reference present with am_depth_percent > 0"),
    "bursts-no-coupling-phase.json": ("/gamma_pac/coupling_phase_deg", "coupled gamma needs a coupling phase",
                                      "present with coupling bursts"),
}
THETA = {"carrier_hz": 450, "rate_hz": 6, "am_depth_percent": 75}
SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
EXTRA_FRAMES = 64
CYCLE = 2**64
IDEAL_TOL = Decimal("1e-15")
LENGTH_S = 5
GAMMA_CARRIER_HZ = 250.0

# Research run burst-edge-taper-2026-10-28 (signal spec, Bursts, Spectrum):
# its worst gamma line at or above the band edge, gamma restarted at each
# burst, per gamma rate. Printed beside each measured figure; the 60 Hz one
# is the figure the match decision holds every rate to.
RESEARCH_DB = {40: -57.2, 45: -58.1, 60: -51.3}
RESEARCH_MATCH_RATE = 60
# Research run: a carrier-gated rectangular 40 Hz burst reaches about -21 dB.
RECTANGULAR_DB = -21.0


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


def ct():
    return importlib.import_module("assertions.coupling_timing")


def clicks():
    return importlib.import_module("assertions.clicks")


def spectrum():
    tool = REPO_ROOT / "tests" / "assertions" / "spectrum.py"
    assert tool.is_file(), f"missing {tool} (Story 2.4 spectrum tool)"
    return importlib.import_module("assertions.spectrum")


def bits(x):
    return struct.unpack("<Q", struct.pack("<d", float(x)))[0]


def channel(stereo, c):
    return np.ascontiguousarray(np.asarray(stereo)[c::2])


def close(value, text):
    return abs(Decimal(repr(float(value))) - Decimal(text)) <= IDEAL_TOL


def timing_ms():
    r = table_row("coupling-timing")
    assert r.unit == "ms", r
    return r.value


def level_tol_db():
    r = table_row("spectrum-level")
    assert r.unit == "dB", r
    return r.value


def band_low_hz():
    """The lowest gamma line that would collide first with the theta reference (signal spec, Bursts, Spectrum).

    The nearest theta line is the 450 Hz carrier less the 6 Hz rate, 444 Hz;
    less the 50 Hz spacing placeholder of row spacing-rule, 394 Hz. The row is
    read from the table file without recording a use: it is pending on Story
    3.2, and this is a band edge, not the spacing assertion. A line exactly
    at 394 Hz is read within row spectrum-frequency of it, so the edge is
    lowered by that row.
    """
    spacing = load_tables()["spacing-rule"]
    assert spacing.unit == "Hz", spacing
    lo = float(THETA["carrier_hz"]) - float(THETA["rate_hz"]) - spacing.value
    assert lo == 394.0, lo   # the spec's figure
    r = table_row("spectrum-frequency")
    assert r.unit == "Hz", r
    return lo - r.value


def load_recipe(name):
    path = FIXTURES_VALID / name
    assert path.is_file(), f"missing fixture {path} (Story 2.4)"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def vectors():
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def burst_rows(vectors, fixture, fs):
    rows = [r for r in vectors["burst_samples"] if r["fixture"] == fixture and r["fs"] == fs]
    assert rows, (fixture, fs)
    return rows


def frames_of(vectors, fixture, fs):
    return int(burst_rows(vectors, fixture, fs)[0]["frames"])


def spec_layers(r):
    """(gamma_pac, theta_reference) of a burst sample row, from the row's own values."""
    g = {"carrier_hz": float.fromhex(r["carrier_hex"]), "rate_hz": float.fromhex(r["rate_hex"]),
         "am_depth_percent": float.fromhex(r["depth_hex"]), "carrier_wave": r["carrier_wave"],
         "coupling": r["coupling"], "coupling_phase_deg": float.fromhex(r["deg_hex"])}
    t = {"carrier_hz": float.fromhex(r["theta_carrier_hex"]), "rate_hz": float.fromhex(r["theta_rate_hex"]),
         "am_depth_percent": float.fromhex(r["theta_depth_hex"]), "shape": r["theta_shape"]}
    return g, t


def burst_gamma(rate=40, depth=100, phase=0, coupling="bursts"):
    g = {"carrier_hz": 250, "rate_hz": rate, "am_depth_percent": depth, "carrier_wave": "sine",
         "coupling": coupling}
    if phase is not None:
        g["coupling_phase_deg"] = phase
    return g


def timing_recipe(shape, phase, depth, coupling="bursts", rate=40, with_theta=True):
    recipe = {
        "schema_version": "1.0", "engine_version": "0.0.1", "seed": 42,
        "author": "Arcani test", "date": "2026-11-13",
        "rationale": "Burst timing recipe, made in the test.",
        "length_s": LENGTH_S, "loudness_target_lufs": -36,
    }
    if with_theta:
        recipe["theta_reference"] = dict(THETA, shape=shape)
    recipe["gamma_pac"] = burst_gamma(rate, depth, phase, coupling)
    return recipe


def write_recipe(folder, name, recipe):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")
    return path


def gamma_rate_of(fixture):
    return int(re.fullmatch(r"bursts-(\d+)hz\.json", fixture).group(1))


def research_match(where, gamma_left, fs, rate):
    """The research figure match decision on one gamma tap channel; returns the measured figure."""
    worst = spectrum().worst_line(gamma_left, fs, band_low_hz())
    research = RESEARCH_DB[rate]
    print(f"{where}: worst gamma line at or above 394 Hz {worst:.2f} dB, research run {research:.1f} dB")
    bound = RESEARCH_DB[RESEARCH_MATCH_RATE]
    if rate == RESEARCH_MATCH_RATE:
        assert abs(worst - research) < level_tol_db(), (where, worst, research)
    else:
        assert worst <= bound, (where, worst, bound, research)
    return worst


# ------------------------------------------------------ fixtures and records


def test_burst_fixtures_exist_with_the_spec_values(vectors):
    order = []
    for r in vectors["burst_samples"]:
        if r["fixture"] not in order:
            order.append(r["fixture"])
    assert tuple(order) == ACCEPTED
    for name in ACCEPTED:
        recipe = load_recipe(name)
        r = burst_rows(vectors, name, SAMPLE_RATES[0])[0]
        g, t = spec_layers(r)
        assert recipe["gamma_pac"] == {
            "carrier_hz": 250, "rate_hz": gamma_rate_of(name), "am_depth_percent": 100,
            "carrier_wave": "sine", "coupling": "bursts", "coupling_phase_deg": 0}, name
        assert g["rate_hz"] == float(gamma_rate_of(name)) and g["am_depth_percent"] == 100.0, name
        assert g["carrier_hz"] == GAMMA_CARRIER_HZ and g["coupling_phase_deg"] == 0.0, name
        assert list(recipe["gamma_pac"]) == ["carrier_hz", "rate_hz", "am_depth_percent", "carrier_wave",
                                             "coupling", "coupling_phase_deg"], name
        assert recipe["theta_reference"] == dict(THETA, shape="sine"), name
        assert t == {"carrier_hz": 450.0, "rate_hz": 6.0, "am_depth_percent": 75.0, "shape": "sine"}, name
        assert float(recipe["length_s"]) == float(LENGTH_S), name
        assert recipe["seed"] == 42 and recipe["loudness_target_lufs"] == -36, name
        assert "binaural" not in recipe, name


def test_compile_rejected_burst_fixtures_are_schema_valid_with_their_values():
    import jsonschema

    schema = json.loads((REPO_ROOT / "recipes" / "recipe.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for name in REJECTED:
        recipe = load_recipe(name)
        assert not list(validator.iter_errors(recipe)), name
    base = load_recipe("bursts-40hz.json")
    no_theta = load_recipe("bursts-no-theta.json")
    assert "theta_reference" not in no_theta
    assert no_theta["gamma_pac"]["coupling"] == "bursts"
    assert no_theta["gamma_pac"]["am_depth_percent"] > 0
    assert "coupling_phase_deg" in no_theta["gamma_pac"]
    no_phase = load_recipe("bursts-no-coupling-phase.json")
    assert no_phase["gamma_pac"]["coupling"] == "bursts"
    assert "coupling_phase_deg" not in no_phase["gamma_pac"]
    assert no_phase["theta_reference"] == base["theta_reference"]


def test_research_figures_are_the_spec_figures():
    # The figures above are the signal spec's table (Bursts, Spectrum), not new values.
    text = SIGNAL_SPEC.read_text(encoding="utf-8")
    start = text.index("## Bursts")
    section = text[start:text.index("### Vectors: burst constants", start)]
    for rate, figure in RESEARCH_DB.items():
        assert re.search(rf"\|\s*{rate} Hz\s*\|\s*{figure:.1f} dB\s*\|", section), (rate, figure)
    assert "394 Hz" in section and "-21 dB" in section


def test_rows_burst_width_and_burst_edge_are_no_longer_pending():
    for row_id in ("burst-width", "burst-edge"):
        r = table_row(row_id)
        assert r.kind == "ranges" and r.unit == "ms" and r.min == r.max, r
        assert r.pending == "", f"row {row_id} is still pending on {r.pending}"


# ------------------------------------------------------ reference module


def test_reference_couplings_and_constants(vectors):
    mod = gamma()
    c = vectors["burst_constants"]
    assert tuple(mod.COUPLINGS) == ("uncoupled", "smooth_swell", "bursts")
    assert tuple(mod.COUPLINGS) == tuple(c["couplings"])
    assert mod.BURST_WIDTH_MS == float(c["width_ms"]) == table_row("burst-width").min
    assert mod.BURST_EDGE_MS == float(c["edge_ms"]) == table_row("burst-edge").min


def test_reference_half_width_and_edge_match_every_vector(vectors):
    mod = gamma()
    for r in vectors["burst_edges"]:
        rate = float.fromhex(r["rate_hex"])
        hb = mod.burst_half_width_units(rate)
        wb = mod.burst_edge_units(rate)
        assert type(hb) is int and type(wb) is int, (type(hb), type(wb))
        assert hb == int(r["hb_units"]), (r["rate_hex"], hb)
        assert wb == int(r["wb_units"]), (r["rate_hex"], wb)
        assert hb - wb == int(r["plateau_end_units"])
        assert wb < hb - wb


def test_reference_gate_is_within_1e_15_of_every_vector(vectors):
    mod = gamma()
    for r in vectors["burst_gates"]:
        rate = float.fromhex(r["rate_hex"])
        assert mod.coupling_phase_units(float.fromhex(r["deg_hex"])) == int(r["c_units"]), r
        assert mod.burst_half_width_units(rate) == int(r["hb_units"]), r
        got = mod.burst(int(r["phase_theta_envelope"]), int(r["c_units"]), int(r["hb_units"]),
                        int(r["wb_units"]))
        assert np.ndim(got) == 0, r
        assert 0.0 <= float(got) <= 1.0, r
        assert close(got, r["ideal_g"]), (r, float(got))
        if r["region"] in ("center", "plateau"):
            assert bits(got) == bits(1.0), r
        elif r["region"] == "off":
            assert bits(got) == 0, r   # +0.0


def test_reference_gate_array_form_matches_the_scalar_form():
    mod = gamma()
    for rate in (1.0, 6.0):
        hb = mod.burst_half_width_units(rate)
        wb = mod.burst_edge_units(rate)
        for c in (0, 1, 2**62, 2**63, CYCLE - 1):
            offsets = np.arange(-4096, 4097, dtype=np.int64) * np.int64(hb // 3000)
            p = (np.uint64(c) + offsets.astype(np.uint64))   # wraps modulo 2^64
            got = mod.burst(p, c, hb, wb)
            assert isinstance(got, np.ndarray) and got.dtype == np.float64 and got.shape == p.shape
            want = np.array([mod.burst(int(v), c, hb, wb) for v in p[::97]])
            assert np.array_equal(got[::97].view(np.uint64), want.view(np.uint64)), (rate, c)
            # Centered on C and mirror-symmetric; 0 half a cycle on.
            assert mod.burst(c, c, hb, wb) == 1.0
            assert mod.burst((c + 2**63) % CYCLE, c, hb, wb) == 0.0
            assert np.array_equal(got, got[::-1]), (rate, c)


def test_reference_amplitude_is_within_1e_15_of_every_vector(vectors):
    mod = gamma()
    for r in vectors["burst_amplitudes"]:
        rate = float.fromhex(r["rate_hex"])
        hb, wb = mod.burst_half_width_units(rate), mod.burst_edge_units(rate)
        g = mod.burst(int(r["phase_theta_envelope"]), 0, hb, wb)
        e = mod.envelope(int(r["phase_gamma_envelope"]))
        d = float.fromhex(r["depth_hex"]) / 100.0
        a = 1.0 - (d * g) * (1.0 - e)
        assert close(g, r["ideal_g"]), r
        assert close(a, r["ideal_a"]), (r, a)
        if r["region"] == "off" or d == 0.0:
            assert a == 1.0, r


def test_reference_render_is_within_1e_15_of_every_burst_vector(vectors):
    mod = gamma()
    renders = {}
    for r in vectors["burst_samples"]:
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
    for r in vectors["burst_samples"]:
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
        inc_e = idl.phase_increment(t["rate_hz"], fs)
        assert (inc_g, inc_m, inc_e) == (int(r["inc_carrier"]), int(r["inc_rate"]),
                                         int(r["inc_theta_envelope"])), key
        c = mod.coupling_phase_units(g["coupling_phase_deg"])
        hb = mod.burst_half_width_units(t["rate_hz"])
        wb = mod.burst_edge_units(t["rate_hz"])
        assert (c, hb, wb) == (int(r["c_units"]), int(r["hb_units"]), int(r["wb_units"])), key
        d = g["am_depth_percent"] / 100.0
        gate = mod.burst(n * np.uint64(inc_e), c, hb, wb)
        e = mod.envelope(n * np.uint64(inc_m))   # free running: never restarted at a burst
        carrier = idl.ideal_sine(n * np.uint64(inc_g))
        want = (1.0 - (d * gate) * (1.0 - e)) * carrier
        got = mod.render(g, fs, frames, theta_reference=t)
        assert np.array_equal(got.view(np.uint64), want.view(np.uint64)), key
        # Off the burst the carrier plays unmodulated, bit for bit.
        off = gate == 0.0
        assert off.any() and np.array_equal(got[off].view(np.uint64), carrier[off].view(np.uint64)), key
        # On the plateau the uncoupled law, bit for bit.
        on = gate == 1.0
        assert on.any()
        plateau = (1.0 - d * (1.0 - e[on])) * carrier[on]
        assert np.array_equal(got[on].view(np.uint64), plateau.view(np.uint64)), key


def test_reference_bursts_need_a_coupling_phase():
    t = dict(THETA, shape="sine")
    with pytest.raises(ValueError):
        gamma().render(burst_gamma(phase=None), SAMPLE_RATES[0], 64, theta_reference=t)
    for coupling in ("burst", "Bursts", "swell"):
        with pytest.raises(ValueError):
            gamma().render(burst_gamma(coupling=coupling), SAMPLE_RATES[0], 64, theta_reference=t)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_bursts_read_only_the_theta_rate(fs):
    mod = gamma()
    g = burst_gamma(phase=90)
    base = mod.render(g, fs, fs, theta_reference=dict(THETA, shape="sine"))
    for other in ({"carrier_hz": 300, "rate_hz": 6, "am_depth_percent": 25, "shape": "sawtooth"},
                  {"carrier_hz": 100, "rate_hz": 6, "am_depth_percent": 100, "shape": "reverse_saw"}):
        got = mod.render(g, fs, fs, theta_reference=other)
        assert np.array_equal(base.view(np.uint64), got.view(np.uint64)), other
    slower = mod.render(g, fs, fs, theta_reference=dict(THETA, rate_hz=5, shape="sine"))
    assert not np.array_equal(base.view(np.uint64), slower.view(np.uint64))
    swell = mod.render(dict(g, coupling="smooth_swell"), fs, fs, theta_reference=dict(THETA, shape="sine"))
    assert not np.array_equal(base.view(np.uint64), swell.view(np.uint64))


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_burst_depth_0_is_the_unmodulated_carrier(fs):
    mod = gamma()
    idl = ideal()
    inc = np.uint64(idl.phase_increment(250.0, fs))
    want = idl.ideal_sine(np.arange(fs, dtype=np.uint64) * inc)
    for t in (None, dict(THETA, shape="sawtooth")):
        got = mod.render(burst_gamma(depth=0, phase=90), fs, fs, theta_reference=t)
        assert np.array_equal(got.view(np.uint64), want.view(np.uint64)), t


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_burst_phase_0_and_360_render_the_same_bytes(fs):
    mod = gamma()
    t = dict(THETA, shape="sine")
    zero = mod.render(burst_gamma(phase=0), fs, fs, theta_reference=t)
    full = mod.render(burst_gamma(phase=360), fs, fs, theta_reference=t)
    assert np.array_equal(zero.view(np.uint64), full.view(np.uint64))


def test_stub_chain_passes_the_theta_reference_to_the_burst_layer(vectors):
    sc = stub_chain()
    mod = gamma()
    th = theta()
    for fixture in ACCEPTED:
        recipe = load_recipe(fixture)
        for fs in SAMPLE_RATES:
            frames = frames_of(vectors, fixture, fs)
            out = sc.render(FIXTURES_VALID / fixture, fs, frames=frames + EXTRA_FRAMES)
            t = recipe["theta_reference"]
            want = mod.render(recipe["gamma_pac"], fs, frames, theta_reference=t)
            theta_want = th.render(t, fs, frames)
            for c in (0, 1):
                got = channel(out["gamma"], c)
                assert np.array_equal(got[:frames].view(np.uint64), want.view(np.uint64)), (fixture, fs, c)
                assert not got[frames:].view(np.uint64).any(), (fixture, fs, c, "past end")
                bus = channel(out["bus"], c)[:frames]
                assert np.array_equal(bus.view(np.uint64), (theta_want + want).view(np.uint64)), (fixture, fs)


def test_stub_chain_bus_is_within_1e_15_of_every_ideal_bus(vectors):
    sc = stub_chain()
    renders = {}
    for r in vectors["burst_samples"]:
        if r["case"] != "signal":
            continue
        key = (r["fixture"], r["fs"])
        if key not in renders:
            renders[key] = sc.render(FIXTURES_VALID / r["fixture"], r["fs"])
        n = int(r["n"])
        for c in (0, 1):
            assert close(renders[key]["bus"][2 * n + c], r["ideal_bus"]), (key, n, c)
            assert close(renders[key]["gamma"][2 * n + c], r["ideal_gamma"]), (key, n, c)


# ------------------------------------------------------ spectrum and clicks (reference renders)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("fixture", ACCEPTED)
def test_reference_burst_spectrum_meets_the_research_figure_match(fixture, fs):
    out = stub_chain().render(FIXTURES_VALID / fixture, fs)
    research_match(f"reference {fixture} {fs}", channel(out["gamma"], 0), fs, gamma_rate_of(fixture))


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("fixture", ACCEPTED)
def test_reference_burst_renders_pass_the_click_tool(fixture, fs):
    out = stub_chain().render(FIXTURES_VALID / fixture, fs)
    for key in ("gamma", "output"):
        result = clicks().check(f"{fixture} {key} {fs}", channel(out[key], 0), fs)
        assert result["result"] == "pass", result


def rectangular_burst(fs, rate_hz=40.0):
    """Must-fail, made here: a carrier-gated rectangular burst, the research run's hard-edged burst.

    The 250 Hz carrier sounds only inside each 50 ms burst (no edges) and is
    silent between bursts; inside, it is amplitude-modulated at the gamma
    rate at 100 percent depth, the gamma envelope restarted at each burst
    center (on a peak there), bursts centered at 0 degrees of a 6 Hz theta
    cycle. Never an engine signal.
    """
    t = np.arange(ideal().seconds_to_samples(float(LENGTH_S), fs), dtype=np.float64) / fs
    period = 1.0 / float(THETA["rate_hz"])
    offset = np.mod(t + period / 2.0, period) - period / 2.0
    half = table_row("burst-width").min / 1000.0 / 2.0
    on = (np.abs(offset) < half).astype(np.float64)
    e = 0.5 + 0.5 * np.cos(2.0 * np.pi * rate_hz * offset)
    return on * e * np.sin(2.0 * np.pi * GAMMA_CARRIER_HZ * t)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_must_fail_rectangular_burst_shows_about_minus_21_db_and_fails_the_click_tool(fs):
    x = rectangular_burst(fs)
    worst = spectrum().worst_line(x, fs, band_low_hz())
    print(f"rectangular 40 Hz burst {fs}: worst line at or above 394 Hz {worst:.2f} dB, "
          f"research run about {RECTANGULAR_DB:.0f} dB")
    assert abs(worst - RECTANGULAR_DB) < level_tol_db(), worst
    # It fails the research figure match decision by far.
    assert worst > RESEARCH_DB[RESEARCH_MATCH_RATE] + level_tol_db(), worst
    result = clicks().check(f"rectangular burst {fs}", x, fs)
    assert result["result"] == "fail", result


# ------------------------------------------------------ harness shift (reference only)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("shape", ("sine", "sawtooth"))
@pytest.mark.parametrize("depth", DEPTHS)
@pytest.mark.parametrize("phase", (0, 270))
def test_reference_bursts_shifted_1_ms_pass_and_3_ms_fail(fs, shape, depth, phase):
    # The shift is made in the harness: the reference gamma rendered with its
    # coupling phase moved by the shift's share of a theta cycle, so only the
    # bursts move; the gamma carrier and envelope stay where they were.
    mod = gamma()
    tool = ct()
    frames = ideal().seconds_to_samples(float(LENGTH_S), fs)
    t = dict(THETA, shape=shape)
    theta_tap = theta().render(t, fs, frames)
    g = burst_gamma(40, depth, phase)
    on_time = mod.render(g, fs, frames, theta_reference=t)
    result = tool.check("on time", on_time, theta_tap, fs, float(THETA["rate_hz"]), shape, float(phase),
                        coupling="bursts", gamma_rate_hz=40.0)
    assert result["result"] == "pass", result
    for shift_ms, verdict in ((1.0, "pass"), (3.0, "fail")):
        deg = (phase + shift_ms / 1000.0 * THETA["rate_hz"] * 360.0) % 360.0
        moved = mod.render(dict(g, coupling_phase_deg=deg), fs, frames, theta_reference=t)
        result = tool.check(f"shifted {shift_ms} ms", moved, theta_tap, fs, float(THETA["rate_hz"]), shape,
                            float(phase), coupling="bursts", gamma_rate_hz=40.0)
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


@pytest.mark.parametrize("fixture", ACCEPTED)
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_burst_fixture_matches_the_reference_spectrum_and_clicks(fixture, fs, vectors, tapdump,
                                                                        tmp_path):
    frames = frames_of(vectors, fixture, fs)
    load_recipe(fixture)
    stdout, eng = dump_arrays(tapdump, FIXTURES_VALID / fixture, fs, tmp_path / "dump", EXTRA_FRAMES)
    assert f"frames {frames} total {frames + EXTRA_FRAMES}" in stdout, stdout
    for key, a in eng.items():
        assert a.size == 2 * (frames + EXTRA_FRAMES), (fixture, fs, key, a.size)
    ref = stub_chain().render(FIXTURES_VALID / fixture, fs, frames=frames + EXTRA_FRAMES)
    mod = rm()
    results = []
    for key in ("gamma", "theta", "bus", "output"):
        results += mod.match_stereo(key, eng[key][:2 * frames], ref[key][:2 * frames])
    failed = [r for r in results if r["result"] != "pass"]
    assert not failed, failed
    for key, _ in DUMP_KEYS:
        assert mod.all_positive_zero(eng[key][2 * frames:]), (fixture, fs, key, "past end")
    for r in burst_rows(vectors, fixture, fs):
        n = int(r["n"])
        for c in (0, 1):
            w = (fixture, fs, n, c)
            assert bits(eng["gamma"][2 * n + c]) == int(r["gamma_bits"], 16), w
            assert bits(eng["theta"][2 * n + c]) == int(r["theta_bits"], 16), w
            assert bits(eng["bus"][2 * n + c]) == int(r["bus_bits"], 16), w
            assert bits(eng["output"][2 * n + c]) == int(r["bus_bits"], 16), w
    # The burst gamma tap is never -0.0.
    neg = np.uint64(0x8000000000000000)
    assert not np.any(np.ascontiguousarray(eng["gamma"]).view(np.uint64) == neg), (fixture, fs)
    # No edge discontinuity over row click-level, gamma tap and output.
    for key in ("gamma", "output"):
        for c in (0, 1):
            result = clicks().check(f"{fixture} {key} {fs} {c}", channel(eng[key][:2 * frames], c), fs)
            assert result["result"] == "pass", result
    # The research figure match on the engine gamma tap.
    research_match(f"engine {fixture} {fs}", channel(eng["gamma"][:2 * frames], 0), fs, gamma_rate_of(fixture))
    # Burst centers within row coupling-timing on the fixture too.
    timing = ct().check(f"timing {fixture} {fs}", channel(eng["gamma"][:2 * frames], 0),
                        channel(eng["theta"][:2 * frames], 0), fs, float(THETA["rate_hz"]), "sine", 0.0,
                        coupling="bursts", gamma_rate_hz=float(gamma_rate_of(fixture)))
    assert timing["result"] == "pass", timing


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize("depth", DEPTHS)
def test_engine_burst_timing_render(fs, shape, phase, depth, tapdump, tmp_path):
    """One of the 32 burst timing recipes at one rate: burst centers and reference match."""
    recipe = write_recipe(tmp_path / "recipes", f"bursts-{shape}-{phase}deg-{depth}pct.json",
                          timing_recipe(shape, phase, depth))
    frames = ideal().seconds_to_samples(float(LENGTH_S), fs)
    stdout, eng = dump_arrays(tapdump, recipe, fs, tmp_path / "dump", 0)
    assert f"frames {frames} total {frames}" in stdout, stdout
    where = (shape, phase, depth, fs)
    timing = ct().check(f"burst timing {where}", channel(eng["gamma"], 0), channel(eng["theta"], 0), fs,
                        float(THETA["rate_hz"]), shape, float(phase), coupling="bursts", gamma_rate_hz=40.0)
    assert timing["result"] == "pass", timing
    assert timing["row"] == "coupling-timing"
    ref = stub_chain().render(recipe, fs)
    results = []
    for key in ("gamma", "bus", "output"):
        results += rm().match_stereo(key, eng[key][:2 * frames], ref[key][:2 * frames])
    failed = [r for r in results if r["result"] != "pass"]
    assert not failed, (where, failed)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_uncoupled_recipe_fails_the_burst_timing_check(fs, tapdump, tmp_path):
    # Must-fail on engine output: the same layers with an uncoupled gamma
    # (constant AM depth) have no burst to time.
    recipe = write_recipe(tmp_path / "recipes", "bursts-uncoupled.json",
                          timing_recipe("sine", None, 100, coupling="uncoupled"))
    _, eng = dump_arrays(tapdump, recipe, fs, tmp_path / "dump", 0)
    result = ct().check("uncoupled", channel(eng["gamma"], 0), channel(eng["theta"], 0), fs,
                        float(THETA["rate_hz"]), "sine", 0.0, coupling="bursts", gamma_rate_hz=40.0)
    assert result["result"] == "fail", result


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_burst_depth_0_without_theta_equals_uncoupled_depth_0(fs, tapdump, tmp_path):
    bursts = write_recipe(tmp_path / "recipes", "bursts-depth-0.json",
                          timing_recipe("sine", 90, 0, with_theta=False))
    plain = write_recipe(tmp_path / "recipes", "uncoupled-depth-0.json",
                         timing_recipe("sine", None, 0, coupling="uncoupled", with_theta=False))
    _, a = dump_arrays(tapdump, bursts, fs, tmp_path / "a", 0)
    _, b = dump_arrays(tapdump, plain, fs, tmp_path / "b", 0)
    for key, _ in DUMP_KEYS:
        assert np.array_equal(a[key].view(np.uint64), b[key].view(np.uint64)), (fs, key)
    assert rm().all_positive_zero(a["theta"]), fs


@pytest.mark.parametrize("fixture", sorted(REJECTED))
def test_engine_rejects_the_compile_rejected_burst_fixtures(fixture, tapdump, tmp_path):
    load_recipe(fixture)
    parameter, rule, limit = REJECTED[fixture]
    for fs in SAMPLE_RATES:
        result = run_dump(tapdump, FIXTURES_VALID / fixture, fs, tmp_path / f"dump-{fs}", 0, expect_ok=False)
        assert result.returncode == 1, (fixture, fs, result.stdout, result.stderr)
        assert not (tmp_path / f"dump-{fs}" / "gamma.f64").exists(), fixture
        text = result.stdout + result.stderr
        for word in (parameter, rule, limit):
            assert word in text, (fixture, word, text)
