"""AD-5 sweep: the gamma PAC layer ignores the binaural layer (Story 2.5).

The gamma PAC layer couples to the theta reference only; the binaural beat has
no waveform in the file, so nothing about the binaural layer may move the
gamma tap or its swell peaks.

Harness recipes, made here in a pytest temp folder, 5 s each:

- theta reference: a 450 Hz carrier amplitude-modulated at 6 Hz by the sine
  envelope, 75 percent AM depth;
- gamma PAC layer: a 250 Hz sine carrier amplitude-modulated at 40 Hz whose
  AM depth swells to 100 percent at coupling phase 0 degrees (smooth swell);
- binaural layer, one of seven settings: a 100 Hz left carrier with a fixed
  beat of 0, 4, or 10 Hz; the same carrier with a beat rate cycle (center
  1.5 Hz, swing 1.5 Hz, 60 s period) at start phase 0, 90, or 270 degrees;
  or no binaural field.

Hand-checked spacing (spec, Decisions): the binaural carriers stay at or
below 110 Hz and the gamma side frequencies start at 204 Hz.

Each recipe is rendered with arcani-tapdump at 44.1 and 48 kHz. The gamma tap
is byte-identical across all seven, and the swell peak times read by the
coupling timing tool (tests/assertions/coupling_timing.py, unchanged) are
equal across all seven: the allowed change, in samples, is row
`coupling-independence`, read through the assertion call. Must-fail made
here: a gamma tap with one swell shifted by one sample is caught by both the
byte comparison and the peak-time comparison.

Story 2.4 adds a burst fixture to the sweep: the same recipes with the gamma
AM depth gated by 50 ms bursts (coupling bursts, 100 percent, coupling phase
0 degrees, gamma 40 Hz). Its gamma tap is byte-identical across all seven
binaural settings and its burst centers (coupling timing tool,
coupling="bursts" with the recipe's gamma rate) are equal within row
`coupling-independence`; a whole burst shifted by one sample in the harness
is caught.

The dump tests skip only when cmake is not on PATH, or when Windows
application control blocks the binary (OSError winerror 4551 or 1260).
"""

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from assertions import row as table_row
from assertions.tables import load_tables

REPO_ROOT = Path(__file__).resolve().parents[2]
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
EXE_NAME = "arcani-tapdump.exe" if sys.platform == "win32" else "arcani-tapdump"
TAPDUMP = REPO_ROOT / "build" / PRESET / "tests" / "tapdump" / EXE_NAME

SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
LENGTH_S = 5
THETA = {"carrier_hz": 450, "rate_hz": 6, "am_depth_percent": 75, "shape": "sine"}
GAMMA = {"carrier_hz": 250, "rate_hz": 40, "am_depth_percent": 100, "carrier_wave": "sine",
         "coupling": "smooth_swell", "coupling_phase_deg": 0}
COUPLING_PHASE_DEG = 0.0


def cycle(start_phase_deg):
    return {"carrier_left_hz": 100, "beat_rate_hz": 1.5,
            "beat_rate_cycle": {"swing_hz": 1.5, "period_s": 60, "start_phase_deg": start_phase_deg}}


SETTINGS = {
    "no-binaural": None,
    "beat-0": {"carrier_left_hz": 100, "beat_rate_hz": 0},
    "beat-4": {"carrier_left_hz": 100, "beat_rate_hz": 4},
    "beat-10": {"carrier_left_hz": 100, "beat_rate_hz": 10},
    "cycle-0deg": cycle(0),
    "cycle-90deg": cycle(90),
    "cycle-270deg": cycle(270),
}
BASE = "no-binaural"


def ct():
    return importlib.import_module("assertions.coupling_timing")


def channel(stereo, c):
    return np.ascontiguousarray(np.asarray(stereo)[c::2])


def independence_samples():
    r = table_row("coupling-independence")
    assert r.unit == "samples of gamma peak time change", r
    return r.value


def ad5_recipe(binaural):
    recipe = {
        "schema_version": "1.0", "engine_version": "0.0.1", "seed": 42,
        "author": "Arcani test", "date": "2026-11-12",
        "rationale": "AD-5 sweep recipe, made in the test.",
        "length_s": LENGTH_S, "loudness_target_lufs": -36,
        "theta_reference": dict(THETA),
        "gamma_pac": dict(GAMMA),
    }
    if binaural is not None:
        recipe["binaural"] = binaural
    return recipe


def peak_times(gamma_left, theta_left, fs):
    """Every swell peak time in seconds: the theta 0 degree times, the coupling phase, and the tool's error."""
    tool = ct()
    rate = float(THETA["rate_hz"])
    zeros = tool.zero_degree_times(theta_left, fs, rate, THETA["shape"])
    errors = tool.timing_errors(gamma_left, theta_left, fs, rate, THETA["shape"], COUPLING_PHASE_DEG)
    assert zeros.size == errors.size and zeros.size > 0, (zeros.size, errors.size)
    return zeros + (COUPLING_PHASE_DEG / 360.0) / rate + errors


# ------------------------------------------------------ without a build


def test_the_row_reads_through_the_assertion_call_and_is_no_longer_pending():
    r = table_row("coupling-independence")
    assert r.unit == "samples of gamma peak time change", r
    assert r.value == 0, r
    assert r.pending == "", f"row coupling-independence is still pending on {r.pending}"


def test_the_sweep_covers_fixed_beats_cycle_start_phases_and_no_binaural():
    beats = sorted(b["beat_rate_hz"] for b in SETTINGS.values() if b and "beat_rate_cycle" not in b)
    phases = sorted(b["beat_rate_cycle"]["start_phase_deg"] for b in SETTINGS.values()
                    if b and "beat_rate_cycle" in b)
    assert beats == [0, 4, 10] and phases == [0, 90, 270]
    assert SETTINGS[BASE] is None


def test_the_sweep_recipes_are_schema_valid():
    import jsonschema

    schema = json.loads((REPO_ROOT / "recipes" / "recipe.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for name, b in SETTINGS.items():
        errors = list(validator.iter_errors(ad5_recipe(b)))
        assert not errors, (name, [e.message for e in errors])


# ------------------------------------------------------------- engine dumps


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


def dump(exe, recipe_path, fs, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run([str(exe), str(recipe_path), str(fs), str(out_dir), "0"],
                                capture_output=True, text=True, timeout=300)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the dump (winerror {e.winerror})")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    arrays = {key: np.fromfile(out_dir / f"{key}.f64", dtype="<f8").astype(np.float64)
              for key in ("gamma", "theta", "join")}
    shutil.rmtree(out_dir, ignore_errors=True)
    return arrays


@pytest.fixture(scope="module")
def sweep(tapdump, tmp_path_factory):
    """fs -> setting -> {"gamma", "theta", "join"} engine taps."""
    root = tmp_path_factory.mktemp("ad5")
    out = {}
    for fs in SAMPLE_RATES:
        out[fs] = {}
        for name, b in SETTINGS.items():
            path = root / f"ad5-{name}.json"
            path.write_text(json.dumps(ad5_recipe(b), indent=2), encoding="utf-8")
            out[fs][name] = dump(tapdump, path, fs, root / f"dump-{name}-{fs}")
    return out


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_gamma_tap_is_byte_identical_across_every_binaural_setting(sweep, fs):
    base = sweep[fs][BASE]["gamma"]
    assert base.size == 2 * LENGTH_S * fs
    assert np.any(base != 0.0)
    for name, taps in sweep[fs].items():
        assert np.array_equal(taps["gamma"].view(np.uint64), base.view(np.uint64)), (fs, name)
        assert np.array_equal(taps["theta"].view(np.uint64), sweep[fs][BASE]["theta"].view(np.uint64)), (fs, name)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_the_binaural_settings_really_differ(sweep, fs):
    joins = {name: taps["join"] for name, taps in sweep[fs].items()}
    names = sorted(joins)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert not np.array_equal(joins[a].view(np.uint64), joins[b].view(np.uint64)), (fs, a, b)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_swell_peak_times_are_equal_across_every_binaural_setting(sweep, fs):
    allowed = independence_samples()
    base = sweep[fs][BASE]
    want = peak_times(channel(base["gamma"], 0), channel(base["theta"], 0), fs)
    timing = ct().check("ad5 base", channel(base["gamma"], 0), channel(base["theta"], 0), fs,
                        float(THETA["rate_hz"]), THETA["shape"], COUPLING_PHASE_DEG)
    assert timing["result"] == "pass", timing
    for name, taps in sweep[fs].items():
        for c in (0, 1):
            got = peak_times(channel(taps["gamma"], c), channel(taps["theta"], c), fs)
            assert got.shape == want.shape, (fs, name, c)
            change = float(np.max(np.abs(got - want))) * fs
            assert change <= allowed, (fs, name, c, change, allowed)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_one_swell_shifted_by_a_sample_is_caught(sweep, fs):
    # Must-fail made here: inside one theta cycle in the middle of the
    # render, the gamma tap is replaced by itself one sample later.
    allowed = independence_samples()
    base = sweep[fs][BASE]
    gamma_left = channel(base["gamma"], 0)
    theta_left = channel(base["theta"], 0)
    period = int(round(fs / THETA["rate_hz"]))
    start = gamma_left.size // 2
    doctored = gamma_left.copy()
    doctored[start:start + period] = gamma_left[start - 1:start + period - 1]
    assert not np.array_equal(doctored.view(np.uint64), gamma_left.view(np.uint64))
    want = peak_times(gamma_left, theta_left, fs)
    got = peak_times(doctored, theta_left, fs)
    change = float(np.max(np.abs(got - want))) * fs
    assert change > allowed, (fs, change, allowed)


# ------------------------------------------------------------- burst fixture (Story 2.4)

BURST_GAMMA = dict(GAMMA, coupling="bursts")


def burst_recipe(binaural):
    recipe = ad5_recipe(binaural)
    recipe["gamma_pac"] = dict(BURST_GAMMA)
    return recipe


def burst_centers(gamma_left, theta_left, fs):
    """Every burst center time in seconds: the theta 0 degree times, the coupling phase, and the tool's error."""
    tool = ct()
    rate = float(THETA["rate_hz"])
    zeros = tool.zero_degree_times(theta_left, fs, rate, THETA["shape"])
    errors = tool.timing_errors(gamma_left, theta_left, fs, rate, THETA["shape"], COUPLING_PHASE_DEG,
                                coupling="bursts", gamma_rate_hz=float(BURST_GAMMA["rate_hz"]))
    assert zeros.size == errors.size and zeros.size > 0, (zeros.size, errors.size)
    return zeros + (COUPLING_PHASE_DEG / 360.0) / rate + errors


def test_the_burst_sweep_recipes_are_schema_valid():
    import jsonschema

    schema = json.loads((REPO_ROOT / "recipes" / "recipe.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for name, b in SETTINGS.items():
        errors = list(validator.iter_errors(burst_recipe(b)))
        assert not errors, (name, [e.message for e in errors])


@pytest.fixture(scope="module")
def burst_sweep(tapdump, tmp_path_factory):
    """fs -> setting -> {"gamma", "theta", "join"} engine taps of the burst recipes."""
    root = tmp_path_factory.mktemp("ad5-bursts")
    out = {}
    for fs in SAMPLE_RATES:
        out[fs] = {}
        for name, b in SETTINGS.items():
            path = root / f"ad5-bursts-{name}.json"
            path.write_text(json.dumps(burst_recipe(b), indent=2), encoding="utf-8")
            out[fs][name] = dump(tapdump, path, fs, root / f"dump-{name}-{fs}")
    return out


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_burst_gamma_tap_is_byte_identical_across_every_binaural_setting(burst_sweep, sweep, fs):
    base = burst_sweep[fs][BASE]["gamma"]
    assert base.size == 2 * LENGTH_S * fs
    # The bursts really differ from the swell.
    assert not np.array_equal(base.view(np.uint64), sweep[fs][BASE]["gamma"].view(np.uint64))
    for name, taps in burst_sweep[fs].items():
        assert np.array_equal(taps["gamma"].view(np.uint64), base.view(np.uint64)), (fs, name)
        assert np.array_equal(taps["theta"].view(np.uint64),
                              burst_sweep[fs][BASE]["theta"].view(np.uint64)), (fs, name)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_burst_centers_are_equal_across_every_binaural_setting(burst_sweep, fs):
    allowed = independence_samples()
    base = burst_sweep[fs][BASE]
    want = burst_centers(channel(base["gamma"], 0), channel(base["theta"], 0), fs)
    timing = ct().check("ad5 bursts base", channel(base["gamma"], 0), channel(base["theta"], 0), fs,
                        float(THETA["rate_hz"]), THETA["shape"], COUPLING_PHASE_DEG, coupling="bursts",
                        gamma_rate_hz=float(BURST_GAMMA["rate_hz"]))
    assert timing["result"] == "pass", timing
    for name, taps in burst_sweep[fs].items():
        for c in (0, 1):
            got = burst_centers(channel(taps["gamma"], c), channel(taps["theta"], c), fs)
            assert got.shape == want.shape, (fs, name, c)
            change = float(np.max(np.abs(got - want))) * fs
            assert change <= allowed, (fs, name, c, change, allowed)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_one_burst_shifted_by_a_sample_is_caught(burst_sweep, fs):
    # Must-fail made here: one whole theta cycle around a burst center in the
    # middle of the render is replaced by itself one sample later, so that
    # burst moves by one sample.
    allowed = independence_samples()
    base = burst_sweep[fs][BASE]
    gamma_left = channel(base["gamma"], 0)
    theta_left = channel(base["theta"], 0)
    period = int(round(fs / THETA["rate_hz"]))
    start = gamma_left.size // 2 + period // 2   # between two burst centers
    doctored = gamma_left.copy()
    doctored[start:start + period] = gamma_left[start - 1:start + period - 1]
    assert not np.array_equal(doctored.view(np.uint64), gamma_left.view(np.uint64))
    want = burst_centers(gamma_left, theta_left, fs)
    got = burst_centers(doctored, theta_left, fs)
    change = float(np.max(np.abs(got - want))) * fs
    assert change > allowed, (fs, change, allowed)
