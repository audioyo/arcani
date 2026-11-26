"""Looping body and seams: engine and reference around the join, every seam, and the end (Story 2.7).

A looping recipe repeats its parameter schedule, never stored samples: every
oscillator phase keeps running on the one engine clock (docs/signal-spec.md,
Loop), so a seam is only a frame number. Thresholds and ranges come from
tests/tables/*.tsv through the assertion call `assertions.row`; no threshold
or range is written here as a literal. Seam frames come from the spec vectors
(tests/data/signal_spec_vectors.json, loop_frames and loop_constants).

Contract with reference/stub_chain.py (spec Implementation Notes, Reference):

- `render(recipe_path, fs, frames=None, start=0)`: the window
  [start, start + T), T = frames when given, else max(N - start, 0); every
  frame at or past N is +0.0; start < 0 raises ValueError. Each value is
  2 * T samples, interleaved stereo, as before.
- `loop_frames(recipe, fs)`: None without `loop`, else a dict with
  `opening_end_frame`, `body_frames`, `seam_frames` (a list), and
  `end_frame`, by the spec's rules from the recipe dict.
- theta.render, gamma.render, binaural.render, and rate_curve.offset_cycles /
  offset_units take `frames` as an int (frames 0 to frames - 1, unchanged)
  or a 1-D integer ndarray of frame indices (output in that order).

Contract with the tap dump (tests/tapdump/main.cpp, target arcani-tapdump):

- `arcani-tapdump RECIPE RATE OUT_DIR --window START FRAMES`: compiles in
  measure mode, seeks to START, renders FRAMES frames in one call with every
  tap, writes the same ten files (Story 4.4: the six plus theta_gained,
  gamma_gained, binaural, binaural_gained), and prints
  `arcani-tapdump: frames N start S total T` (T the frames rendered).
- `arcani-tapdump RECIPE RATE OUT_DIR --output-only`: renders the whole
  session in calls of 65536 frames without taps, writes out.f64 only, and
  prints `arcani-tapdump: frames N total N`.

Seam windows (loop_constants.window_s, 8 s): the join and seam windows are
centered on O or seam k, the end window on N - 4 s. Each window starts at the
frame nearest the last time at or before center - 4 s where the ideal theta
phase frequency.curve_phase(t, rate_hz, cycle) is an integer (a theta 0
degree point), and the timing tools get the recipe's cycle with
start_phase_deg moved to the window start
(start_phase_deg + 360 * (start / fs) / period_s, mod 360), so they predict
each 0 degree point within a frame.

Checks, loop-swell-theta-cycle.json (a 450 Hz carrier amplitude-modulated by
the sine envelope at a theta rate of 4 +- 2 Hz cycling every 60 s, 75 percent
depth, and a 250 Hz sine carrier amplitude-modulated at 40 Hz with a smooth
swell peaking at the 0 degree coupling phase, 100 percent depth), both rates:
the whole render's slice of each window equals the window render byte for
byte; the click tool on the whole render in overlapping chunks per channel;
per window, the theta, gamma, bus, and output match the reference (row
`reference-match`); coupling timing within row `coupling-timing`; the
recovered theta envelope phase (0 degree times) within row
`coupling-timing-calibration` of the schedule, with points on both sides of
the join or seam; the recovered gamma envelope phase (demodulated by the
scheduled gamma envelope phase), each side's mean and their difference as
time at the gamma rate, within row `coupling-timing-calibration`.
loop-bursts-theta-cycle.json (the same with 50 ms bursts at 0 degrees), both
rates: reference match and coupling timing in every window. Must-fail,
doctored in the harness: a 1-sample gap at a seam fails the click tool; a
1 ms phase step at a seam fails the reference match, the click tool, and the
theta and gamma phase checks.

The dump tests skip only when cmake is not on PATH, or when Windows
application control blocks the binary (OSError winerror 4551 or 1260).
"""

import copy
import importlib
import json
import math
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
VECTORS_PATH = REPO_ROOT / "tests" / "data" / "signal_spec_vectors.json"
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

VECTORS = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
LOOP = VECTORS["loop_constants"]
FULL_FIXTURE = LOOP["full_render_fixture"]
WINDOW_FIXTURES = tuple(LOOP["window_fixtures"])
WINDOW_S = float(LOOP["window_s"])
SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
# The doctored phase step of the must-fail case: the window continues from
# the seam with the engine render from seam + round(PHASE_STEP_S * fs).
PHASE_STEP_S = 0.001
CLICK_CHUNK_S = 20.0
DUMP_FILES = ("out", "theta", "gamma", "bus", "join", "master", "theta_gained", "gamma_gained", "binaural",
              "binaural_gained")  # Story 4.4: ten files
TAP_KEYS = (("theta", "theta"), ("gamma", "gamma"), ("bus", "bus"), ("output", "out"))
# Fixtures written before Story 2.7, short and with every layer kind and cycle.
OLDER_FIXTURES = ("gamma-cycle-swell-theta-cycle.json", "binaural-cycle-sleep.json", "bursts-theta-cycle.json")


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def ref(name):
    _repo_on_path()
    return importlib.import_module(f"reference.{name}")


def tool(name):
    return importlib.import_module(f"assertions.{name}")


def load_recipe(name):
    path = FIXTURES_VALID / name
    assert path.is_file(), f"missing fixture {path} (Story 2.7)"
    return json.loads(path.read_text(encoding="utf-8"))


def frame_row(fixture, fs):
    rows = [r for r in VECTORS["loop_frames"] if r["fixture"] == fixture and r["fs"] == fs]
    assert len(rows) == 1, (fixture, fs)
    return rows[0]


def window_count(fixture):
    counts = {int(frame_row(fixture, fs)["seam_count"]) + 2 for fs in SAMPLE_RATES}
    assert len(counts) == 1, counts
    return counts.pop()


def calibration_s():
    r = table_row("coupling-timing-calibration")
    assert r.unit == "ms", r
    return r.value / 1000.0


def channel(stereo, c):
    return np.ascontiguousarray(np.asarray(stereo)[c::2])


def bits_equal(a, b):
    a = np.ascontiguousarray(a, dtype=np.float64)
    b = np.ascontiguousarray(b, dtype=np.float64)
    return a.shape == b.shape and np.array_equal(a.view(np.uint64), b.view(np.uint64))


def seconds_to_samples(t, fs):
    return ref("ideal").seconds_to_samples(float(t), fs)


# ------------------------------------------------------------ window plan


def local_rate(t, rate, cycle):
    if cycle is None:
        return rate
    return rate + float(cycle["swing_hz"]) * math.sin(
        2.0 * math.pi * t / float(cycle["period_s"]) + math.radians(float(cycle["start_phase_deg"])))


def phase_at(t, rate, cycle):
    return float(tool("frequency").curve_phase(t, rate, cycle))


def last_zero_degree_time(t_c, rate, cycle):
    """The last time at or before t_c where the ideal theta phase is an integer."""
    k = math.floor(phase_at(t_c, rate, cycle))
    lowest = rate - (float(cycle["swing_hz"]) if cycle is not None else 0.0)
    lo, hi = t_c - 1.0 / lowest - 0.01, t_c
    assert phase_at(lo, rate, cycle) <= k
    if phase_at(hi, rate, cycle) == k:
        return hi
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if phase_at(mid, rate, cycle) <= k:
            lo = mid
        else:
            hi = mid
    return lo


def moved_cycle(cycle, start, fs):
    if cycle is None:
        return None
    out = dict(cycle)
    out["start_phase_deg"] = (float(cycle["start_phase_deg"])
                              + 360.0 * (start / fs) / float(cycle["period_s"])) % 360.0
    return out


def windows(fixture, fs):
    """[(label, start, frames, split)]: the join, every seam, and the end; split is the
    window-relative frame of the join or seam (the window middle for the end)."""
    recipe = load_recipe(fixture)
    theta = recipe["theta_reference"]
    rate = float(theta["rate_hz"])
    cycle = theta.get("rate_cycle")
    r = frame_row(fixture, fs)
    o, n = int(r["opening_end_frame"]), int(r["end_frame"])
    seams = [int(s) for s in r["seam_frames"]]
    t_frames = seconds_to_samples(WINDOW_S, fs)
    half = seconds_to_samples(WINDOW_S / 2.0, fs)
    centers = [("join", o)] + [(f"seam {k}", s) for k, s in enumerate(seams, start=1)] + [("end", n - half)]
    out = []
    for label, center in centers:
        t_star = last_zero_degree_time(center / fs - WINDOW_S / 2.0, rate, cycle)
        start = int(round(t_star * fs))
        assert 0 <= start and start + t_frames <= n, (fixture, fs, label, start)
        split = center - start if label != "end" else t_frames // 2
        out.append((label, start, t_frames, split))
    return out


# ------------------------------------------------------------ phase checks


def theta_zero_errors(theta_left, fs, rate, cycle_w):
    """(recovered 0 degree times, their errors against the scheduled ones), seconds."""
    z = tool("coupling_timing").zero_degree_times(theta_left, fs, rate, "sine", cycle=cycle_w)
    errors = []
    for t in z:
        k = round(phase_at(float(t), rate, cycle_w))
        s = float(t)
        for _ in range(4):
            s -= (phase_at(s, rate, cycle_w) - k) / local_rate(s, rate, cycle_w)
        errors.append(float(t) - s)
    return np.asarray(z), np.asarray(errors)


def theta_phase_check(theta_left, fs, rate, cycle_w, split):
    z, errors = theta_zero_errors(theta_left, fs, rate, cycle_w)
    worst = float(np.max(np.abs(errors))) if errors.size else math.inf
    split_s = split / fs
    return {"times": z, "errors": errors, "worst_s": worst,
            "both_sides": bool(np.any(z < split_s) and np.any(z > split_s)),
            "pass": errors.size > 0 and worst < calibration_s()}


def gamma_phase_check(gamma_left, fs, start, gamma_rate, gamma_cycle, split):
    """Each side's mean gamma envelope phase against the schedule, and their difference, in seconds."""
    env = tool("coupling_timing").envelope(gamma_left)
    n = env.size
    f = np.fft.fftfreq(n, d=1.0 / fs)
    theta_top = table_row("theta-rate").max
    g = table_row("gamma-rate")
    band = (f >= g.min - theta_top) & (f <= g.max + theta_top)
    z = np.fft.ifft(np.fft.fft(env) * np.where(band, 2.0, 0.0))
    t_abs = (start + np.arange(n, dtype=np.float64)) / fs
    phase = np.asarray(tool("frequency").curve_phase(t_abs, gamma_rate, gamma_cycle))
    demod = z * np.exp(-2j * math.pi * (phase - np.rint(phase)))
    trim = int(round(0.5 * fs))
    left = demod[trim:split]
    right = demod[split:n - trim]
    p_left = math.atan2(float(np.sum(left).imag), float(np.sum(left).real)) / (2.0 * math.pi)
    p_right = math.atan2(float(np.sum(right).imag), float(np.sum(right).real)) / (2.0 * math.pi)
    diff = math.remainder(p_right - p_left, 1.0)
    times = {"left_s": p_left / gamma_rate, "right_s": p_right / gamma_rate, "difference_s": diff / gamma_rate}
    times["pass"] = all(abs(v) < calibration_s() for v in times.values())
    return times


def clicks_pass(stereo, fs):
    results = [tool("clicks").check(f"clicks {side}", channel(stereo, c), fs)
               for c, side in ((0, "left"), (1, "right"))]
    return all(r["result"] == "pass" for r in results), results


def match_failures(eng, refw, keys=("theta", "gamma", "bus", "output")):
    mod = tool("reference_match")
    results = []
    for key in keys:
        results += mod.match_stereo(key, eng[key], refw[key])
    return [r for r in results if r["result"] != "pass"]


def timing_check(eng, fs, recipe, cycle_w, label):
    g = recipe["gamma_pac"]
    t = recipe["theta_reference"]
    return tool("coupling_timing").check(
        f"coupling timing {label}", channel(eng["gamma"], 0), channel(eng["theta"], 0), fs,
        float(t["rate_hz"]), t["shape"], float(g["coupling_phase_deg"]), coupling=g["coupling"],
        gamma_rate_hz=float(g["rate_hz"]), cycle=cycle_w)


# ------------------------------------------------------------ without the engine


def test_loop_constants_name_the_window_and_full_render_fixtures():
    assert FULL_FIXTURE == "loop-swell-theta-cycle.json"
    assert WINDOW_FIXTURES == ("loop-swell-theta-cycle.json", "loop-bursts-theta-cycle.json")
    assert WINDOW_S > 0.0
    for name in WINDOW_FIXTURES:
        recipe = load_recipe(name)
        assert recipe["theta_reference"]["shape"] == "sine", name
        assert recipe["theta_reference"].get("rate_cycle") is not None, name
        assert "loop" in recipe, name
        for fs in SAMPLE_RATES:
            assert int(frame_row(name, fs)["seam_count"]) >= 1, (name, fs)


def test_both_max_run_time_rows_are_landed_and_match_the_spec_vectors():
    for mode, row_id in LOOP["mode_rows"].items():
        r = table_row(row_id)
        assert r.kind == "ranges" and r.unit == "min", r
        assert r.pending == "", f"row {row_id} is still pending on {r.pending}"
        assert r.min == r.max == float(LOOP["max_run_time_min"][mode]), (row_id, r)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_loop_frames_equal_the_vectors(fs):
    sc = ref("stub_chain")
    rows = [r for r in VECTORS["loop_frames"] if r["fs"] == fs]
    assert rows
    for r in rows:
        got = sc.loop_frames(load_recipe(r["fixture"]), fs)
        assert isinstance(got, dict), (r["fixture"], got)
        assert set(got) == {"opening_end_frame", "body_frames", "seam_frames", "end_frame"}, got
        assert got["opening_end_frame"] == int(r["opening_end_frame"]), r["fixture"]
        assert got["body_frames"] == int(r["body_frames"]), r["fixture"]
        assert list(got["seam_frames"]) == [int(s) for s in r["seam_frames"]], r["fixture"]
        assert got["end_frame"] == int(r["end_frame"]), r["fixture"]
        assert all(isinstance(s, int) for s in got["seam_frames"])
    for name in OLDER_FIXTURES:
        assert sc.loop_frames(load_recipe(name), fs) is None, name


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_layers_render_frame_arrays_as_the_contiguous_render(fs):
    theta, gamma, binaural, rc = ref("theta"), ref("gamma"), ref("binaural"), ref("rate_curve")
    swell = load_recipe("gamma-cycle-swell-theta-cycle.json")
    sleep = load_recipe("binaural-cycle-sleep.json")
    span = 2 * fs
    rng = np.random.default_rng(27)
    picked = rng.integers(0, span, size=4000)
    idx = np.concatenate([picked, np.arange(span - 1, span - 300, -1), [0, 0, 1, 63, 64, span - 1]]).astype(np.int64)
    t = swell["theta_reference"]
    g = swell["gamma_pac"]
    want = theta.render(t, fs, span)
    assert bits_equal(theta.render(t, fs, idx), want[idx])
    want = gamma.render(g, fs, span, theta_reference=t)
    assert bits_equal(gamma.render(g, fs, idx, theta_reference=t), want[idx])
    left, right = binaural.render(sleep["binaural"], fs, span)
    got_left, got_right = binaural.render(sleep["binaural"], fs, idx)
    assert bits_equal(got_left, left[idx]) and bits_equal(got_right, right[idx])
    for cycle in (t["rate_cycle"], g["rate_cycle"], sleep["binaural"]["beat_rate_cycle"], None):
        c = rc.offset_cycles(cycle, fs, span)
        assert bits_equal(rc.offset_cycles(cycle, fs, idx), c[idx]), cycle
        u = rc.offset_units(cycle, fs, span)
        got = rc.offset_units(cycle, fs, idx)
        assert got.dtype == np.uint64 and np.array_equal(got, u[idx]), cycle
    # An int keeps its meaning: frames 0 to frames - 1.
    assert bits_equal(theta.render(t, fs, np.arange(span, dtype=np.int64)), theta.render(t, fs, span))
    # Indices far into a session, past where the contiguous render reaches here.
    far = np.array([50_000_000, 7, 50_000_001], dtype=np.int64)
    got = theta.render(t, fs, far)
    assert got.shape == (3,) and bits_equal(got[1:2], theta.render(t, fs, 8)[7:8])


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("name", OLDER_FIXTURES)
def test_reference_window_render_equals_the_slice_of_the_full_render(name, fs):
    sc = ref("stub_chain")
    path = FIXTURES_VALID / name
    full = sc.render(path, fs)
    n = full["output"].size // 2
    assert n == seconds_to_samples(float(load_recipe(name)["length_s"]), fs)
    padded = sc.render(path, fs, frames=n + 128)
    cases = ((0, None), (0, 1000), (fs * 55 + 37, 3 * fs), (n - fs, fs + 128), (n, 64), (n + 5, 10), (n - 1, None))
    for start, frames in cases:
        got = sc.render(path, fs, frames=frames, start=start)
        t = max(n - start, 0) if frames is None else frames
        for key in sc.KEYS:
            assert got[key].size == 2 * t, (name, start, frames, key)
            a, b = 2 * start, 2 * (start + t)
            if b <= padded[key].size:
                want = padded[key][a:b]
            else:
                want = np.zeros(2 * t)
                live = max(min(padded[key].size, b) - a, 0)
                want[:live] = padded[key][a:a + live]
            assert bits_equal(got[key], want), (name, start, frames, key)
            past = max(min(b, 2 * (start + t)) - max(a, 2 * n), 0)
            if past:
                assert not np.ascontiguousarray(got[key][-past:]).view(np.uint64).any(), (name, start, key)
    # Start 0, frames None is the whole session as before.
    again = sc.render(path, fs, start=0)
    for key in sc.KEYS:
        assert bits_equal(again[key], full[key]), (name, key)
    with pytest.raises(ValueError):
        sc.render(path, fs, frames=10, start=-1)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("fixture", WINDOW_FIXTURES)
def test_reference_looping_windows_equal_the_same_recipe_without_loop(fixture, fs, tmp_path):
    sc = ref("stub_chain")
    recipe = load_recipe(fixture)
    plain = {k: v for k, v in recipe.items() if k != "loop"}
    plain_path = tmp_path / "plain.json"
    plain_path.write_text(json.dumps(plain, indent=2), encoding="utf-8")
    assert sc.loop_frames(plain, fs) is None
    r = frame_row(fixture, fs)
    for start in (int(r["opening_end_frame"]) - 100, int(r["seam_frames"][0]) - 37,
                  int(r["seam_frames"][-1]) - 1000, int(r["end_frame"]) - 500):
        a = sc.render(FIXTURES_VALID / fixture, fs, start=start, frames=1200)
        b = sc.render(plain_path, fs, start=start, frames=1200)
        for key in sc.KEYS:
            assert bits_equal(a[key], b[key]), (fixture, fs, start, key)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("fixture", WINDOW_FIXTURES)
def test_window_plan_starts_each_window_on_a_theta_0_degree_point(fixture, fs):
    recipe = load_recipe(fixture)
    rate = float(recipe["theta_reference"]["rate_hz"])
    cycle = recipe["theta_reference"]["rate_cycle"]
    ws = windows(fixture, fs)
    assert len(ws) == window_count(fixture)
    assert [w[0] for w in ws][0] == "join" and ws[-1][0] == "end"
    top = rate + float(cycle["swing_hz"])
    for label, start, frames, split in ws:
        assert frames == seconds_to_samples(WINDOW_S, fs)
        phi = phase_at(start / fs, rate, cycle)
        # Within half a frame of an integer theta phase.
        assert abs(phi - round(phi)) <= 0.5 / fs * top + 1e-9, (label, phi)
        # The moved cycle gives the window's own phase from 0.
        w = moved_cycle(cycle, start, fs)
        for tau in (0.0, 1.25, 7.5):
            whole = phase_at(start / fs + tau, rate, cycle) - phi
            assert abs(phase_at(tau, rate, w) - whole) < 1e-7, (label, tau)
        assert 0 < split < frames, (label, split)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_join_window_passes_the_phase_checks(fs):
    # Calibration of the harness on the reference alone: the checks pass on
    # an undoctored window and fail on the doctored ones.
    sc = ref("stub_chain")
    recipe = load_recipe(FULL_FIXTURE)
    label, start, frames, split = windows(FULL_FIXTURE, fs)[1]  # seam 1
    d = int(round(PHASE_STEP_S * fs))
    w = sc.render(FIXTURES_VALID / FULL_FIXTURE, fs, start=start, frames=frames + d)
    rate = float(recipe["theta_reference"]["rate_hz"])
    cycle_w = moved_cycle(recipe["theta_reference"]["rate_cycle"], start, fs)
    g = recipe["gamma_pac"]
    theta_left = channel(w["theta"], 0)[:frames]
    gamma_left = channel(w["gamma"], 0)[:frames]
    th = theta_phase_check(theta_left, fs, rate, cycle_w, split)
    assert th["pass"] and th["both_sides"], th["worst_s"]
    gm = gamma_phase_check(gamma_left, fs, start, float(g["rate_hz"]), g.get("rate_cycle"), split)
    assert gm["pass"], gm
    ok, results = clicks_pass(w["output"][:2 * frames], fs)
    assert ok, results
    stepped_theta = np.concatenate([channel(w["theta"], 0)[:split], channel(w["theta"], 0)[split + d:]])
    stepped_gamma = np.concatenate([channel(w["gamma"], 0)[:split], channel(w["gamma"], 0)[split + d:]])
    assert not theta_phase_check(stepped_theta, fs, rate, cycle_w, split)["pass"]
    assert not gamma_phase_check(stepped_gamma, fs, start, float(g["rate_hz"]), g.get("rate_cycle"), split)["pass"]
    gap = np.delete(w["output"][:2 * frames], [2 * split, 2 * split + 1])
    assert not clicks_pass(gap, fs)[0]


# ------------------------------------------------------------ engine dumps


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


def run_dump(exe, args, timeout=300):
    try:
        result = subprocess.run([str(exe), *[str(a) for a in args]], capture_output=True, text=True,
                                timeout=timeout)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the dump (winerror {e.winerror})")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def engine_window(exe, fixture, fs, start, frames, out_dir, row_fixture=None):
    """The ten dump files of a --window render, as interleaved stereo arrays by tap key.
    row_fixture names the loop fixture whose frame vectors hold the session end (a harness
    copy of a fixture gives the original's name)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    result = run_dump(exe, [FIXTURES_VALID / fixture, fs, out_dir, "--window", start, frames])
    n = int(frame_row(row_fixture or fixture, fs)["end_frame"])
    assert f"arcani-tapdump: frames {n} start {start} total {frames}" in result.stdout, result.stdout
    arrays = {}
    for name in DUMP_FILES:
        arrays[name] = np.fromfile(out_dir / f"{name}.f64", dtype="<f8").astype(np.float64)
        assert arrays[name].size == 2 * frames, (name, arrays[name].size)
    shutil.rmtree(out_dir, ignore_errors=True)
    arrays["output"] = arrays["out"]
    return arrays


class FullRender:
    def __init__(self, fs, path, frames):
        self.fs = fs
        self.path = path
        self.frames = frames

    def read(self, start, count):
        """Interleaved stereo frames [start, start + count) of the whole render's output."""
        return np.fromfile(self.path, dtype="<f8", count=2 * count, offset=16 * start).astype(np.float64)


@pytest.fixture(scope="module", params=SAMPLE_RATES, ids=lambda fs: f"fs{fs}")
def full(request, tapdump, tmp_path_factory):
    """The whole swell loop render at one rate, output only, removed after its tests."""
    fs = request.param
    out_dir = tmp_path_factory.mktemp(f"loop-full-{fs}")
    load_recipe(FULL_FIXTURE)
    n = int(frame_row(FULL_FIXTURE, fs)["end_frame"])
    result = run_dump(tapdump, [FIXTURES_VALID / FULL_FIXTURE, fs, out_dir, "--output-only"], timeout=1200)
    assert f"arcani-tapdump: frames {n} total {n}" in result.stdout, result.stdout
    assert sorted(p.name for p in out_dir.iterdir()) == ["out.f64"], sorted(p.name for p in out_dir.iterdir())
    path = out_dir / "out.f64"
    assert path.stat().st_size == 16 * n
    yield FullRender(fs, path, n)
    shutil.rmtree(out_dir, ignore_errors=True)


def click_chunks(n, length, k):
    """Chunk starts so that every sample outside the first and last k lies in some chunk's checked part."""
    step = length - 2 * k
    starts = list(range(0, max(n - length, 0) + 1, step))
    if starts[-1] + length < n:
        starts.append(n - length)
    return starts


def test_click_chunks_cover_every_checked_sample():
    for n, length, k in ((1000, 100, 5), (52_920_000, 882_000, 2205), (57_600_000, 960_000, 2400), (1000, 1000, 5)):
        starts = click_chunks(n, length, k)
        covered_to = k
        for s in starts:
            assert s + k <= covered_to, (n, s)
            covered_to = max(covered_to, s + length - k)
        assert covered_to == n - k and starts[-1] + length == n, (n, length, k)


def test_whole_swell_render_has_no_click_anywhere(full):
    fs = full.fs
    length = seconds_to_samples(CLICK_CHUNK_S, fs)
    k = int(round(tool("clicks").EXCLUDE_S * fs))
    worst = -math.inf
    failed = []
    for s in click_chunks(full.frames, length, k):
        part = full.read(s, length)
        for c, side in ((0, "left"), (1, "right")):
            r = tool("clicks").check(f"clicks {side} from frame {s}", channel(part, c), fs)
            if r["measured"] is not None:
                worst = max(worst, r["measured"])
            if r["result"] != "pass":
                failed.append(r)
    assert not failed, failed[:4]
    assert worst > -math.inf


@pytest.mark.parametrize("index", range(window_count(FULL_FIXTURE)))
def test_swell_window_matches_the_reference_and_keeps_every_phase(full, index, tapdump, tmp_path):
    fs = full.fs
    recipe = load_recipe(FULL_FIXTURE)
    label, start, frames, split = windows(FULL_FIXTURE, fs)[index]
    where = (FULL_FIXTURE, fs, label)
    eng = engine_window(tapdump, FULL_FIXTURE, fs, start, frames, tmp_path / "dump")
    # The whole render's slice of the window equals the window render.
    assert bits_equal(full.read(start, frames), eng["output"]), where
    refw = ref("stub_chain").render(FIXTURES_VALID / FULL_FIXTURE, fs, start=start, frames=frames)
    failed = match_failures(eng, refw)
    assert not failed, (where, failed)
    cycle_w = moved_cycle(recipe["theta_reference"]["rate_cycle"], start, fs)
    timing = timing_check(eng, fs, recipe, cycle_w, label)
    assert timing["result"] == "pass", (where, timing)
    assert timing["row"] == "coupling-timing"
    rate = float(recipe["theta_reference"]["rate_hz"])
    th = theta_phase_check(channel(eng["theta"], 0), fs, rate, cycle_w, split)
    assert th["pass"], (where, th["worst_s"], th["errors"])
    if label != "end":
        assert th["both_sides"], (where, th["times"])
    g = recipe["gamma_pac"]
    gm = gamma_phase_check(channel(eng["gamma"], 0), fs, start, float(g["rate_hz"]), g.get("rate_cycle"), split)
    assert gm["pass"], (where, gm)
    ok, results = clicks_pass(eng["output"], fs)
    assert ok, (where, results)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("index", range(window_count("loop-bursts-theta-cycle.json")))
def test_bursts_window_matches_the_reference_and_keeps_its_timing(fs, index, tapdump, tmp_path):
    fixture = "loop-bursts-theta-cycle.json"
    assert fixture in WINDOW_FIXTURES
    recipe = load_recipe(fixture)
    assert recipe["gamma_pac"]["coupling"] == "bursts"
    label, start, frames, _ = windows(fixture, fs)[index]
    where = (fixture, fs, label)
    eng = engine_window(tapdump, fixture, fs, start, frames, tmp_path / "dump")
    refw = ref("stub_chain").render(FIXTURES_VALID / fixture, fs, start=start, frames=frames)
    failed = match_failures(eng, refw)
    assert not failed, (where, failed)
    cycle_w = moved_cycle(recipe["theta_reference"]["rate_cycle"], start, fs)
    timing = timing_check(eng, fs, recipe, cycle_w, label)
    assert timing["result"] == "pass", (where, timing)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_must_fail_a_doctored_seam_fails_the_checks(fs, tapdump, tmp_path):
    """Doctored in the harness, never in the engine: a 1-sample gap and a 1 ms phase step at seam 1."""
    recipe = load_recipe(FULL_FIXTURE)
    label, start, frames, split = windows(FULL_FIXTURE, fs)[1]
    assert label == "seam 1"
    d = int(round(PHASE_STEP_S * fs))
    eng = engine_window(tapdump, FULL_FIXTURE, fs, start, frames + d, tmp_path / "dump")
    refw = ref("stub_chain").render(FIXTURES_VALID / FULL_FIXTURE, fs, start=start, frames=frames)
    plain = {key: eng[key][:2 * frames] for key, _ in TAP_KEYS}
    # The undoctored window passes, so the failures below are the doctoring's.
    assert not match_failures(plain, refw)
    assert clicks_pass(plain["output"], fs)[0]

    # A 1-sample gap: the seam frame dropped.
    gap = np.delete(plain["output"], [2 * split, 2 * split + 1])
    ok, results = clicks_pass(gap, fs)
    assert not ok, results

    # A phase step: from the seam on, the engine render from seam + d.
    def stepped(stereo):
        return np.concatenate([stereo[:2 * split], stereo[2 * (split + d):2 * (frames + d)]])

    step = {key: stepped(eng[key]) for key, _ in TAP_KEYS}
    for key in step:
        assert step[key].size == 2 * frames, key
    assert match_failures(step, refw, keys=("output",)), "the phase step passed the reference match"
    assert not clicks_pass(step["output"], fs)[0], "the phase step passed the click tool"
    rate = float(recipe["theta_reference"]["rate_hz"])
    cycle_w = moved_cycle(recipe["theta_reference"]["rate_cycle"], start, fs)
    th = theta_phase_check(channel(step["theta"], 0), fs, rate, cycle_w, split)
    assert not th["pass"], th["worst_s"]
    g = recipe["gamma_pac"]
    gm = gamma_phase_check(channel(step["gamma"], 0), fs, start, float(g["rate_hz"]), g.get("rate_cycle"), split)
    assert not gm["pass"], gm


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_must_fail_a_replay_from_the_opening_end_at_a_seam(fs, tapdump, tmp_path):
    """Doctored in the harness, never in the engine: from seam 1 on, the samples of the
    render that starts at the opening end O (sample replay, or every phase restarted per pass).

    On the swell loop fixture every rate (450 Hz and 250 Hz carriers, 40 Hz gamma rate,
    4 +- 2 Hz theta rate over 60 s) completes whole cycles in the 120 s body, so the replay
    equals the continuous render within row reference-match: there it is no defect and no
    check can see it. The must-fail runs on a harness copy whose carriers are 450.004 Hz and
    250.004 Hz (0.48 of a carrier cycle left over per body), where a replay is a phase reset."""
    recipe = load_recipe(FULL_FIXTURE)
    label, start, frames, split = windows(FULL_FIXTURE, fs)[1]
    assert label == "seam 1"
    o = ref("stub_chain").loop_frames(recipe, fs)["opening_end_frame"]
    seam = start + split

    def replayed(eng_seam, eng_open):
        return {key: np.concatenate([eng_seam[key][:2 * split], eng_open[key][:2 * (frames - split)]])
                for key, _ in TAP_KEYS}

    # The swell fixture itself: the replay is the continuous render, within reference-match.
    eng = engine_window(tapdump, FULL_FIXTURE, fs, start, frames, tmp_path / "seam")
    eng_o = engine_window(tapdump, FULL_FIXTURE, fs, o, frames - split, tmp_path / "open")
    assert not match_failures(replayed(eng, eng_o), eng), "a replay on whole-cycle rates differs"

    # The harness copy with off-cycle carriers: the replay is caught.
    variant = json.loads(json.dumps(recipe))
    variant["theta_reference"]["carrier_hz"] = 450.004
    variant["gamma_pac"]["carrier_hz"] = 250.004
    path = tmp_path / "loop-swell-off-cycle-carriers.json"
    path.write_text(json.dumps(variant, indent=2), encoding="utf-8")
    eng = engine_window(tapdump, path, fs, start, frames, tmp_path / "v-seam", FULL_FIXTURE)
    eng_o = engine_window(tapdump, path, fs, o, frames - split, tmp_path / "v-open", FULL_FIXTURE)
    assert clicks_pass(eng["output"], fs)[0], "the undoctored variant window clicks"
    refw = ref("stub_chain").render(path, fs, start=start, frames=frames)
    assert not match_failures(eng, refw)
    replay = replayed(eng, eng_o)
    assert seam == o + int(ref("stub_chain").loop_frames(variant, fs)["body_frames"])
    assert not clicks_pass(replay["output"], fs)[0], "the replay passed the click tool"
    assert match_failures(replay, refw, keys=("output",)), "the replay passed the reference match"
