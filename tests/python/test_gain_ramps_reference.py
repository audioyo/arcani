"""Gain ramps: Python reference, engine match, ramp tool, and clicks (Story 4.4;
docs/signal-spec.md, Gain ramps).

Contract with reference/gain.py (imported as `reference.gain`; NumPy, the
standard library, and reference/ only):

- `frames(gain, fs) -> list[tuple]`: [(n0, L, n1, a, b)] per ramp of one
  gain member (Gain ramps, Ramp frames), integers and binary64 floats.
- `values(gain, fs, n) -> ndarray`: the binary64 gains of a uint64 frame
  index array by the reference law (r = k / L, h = (1.0 -
  numpy.cos(numpy.pi * r)) * 0.5, g = a + (b - a) * h); 1.0 for every frame
  when `gain` is None.

Contract with reference/stub_chain.py: `render` returns KEYS = ("output",
"theta", "gamma", "bus", "join", "master", "theta_gained", "gamma_gained",
"binaural", "binaural_gained"), each interleaved stereo; theta and gamma
stay before gain.

Contract with arcani-tapdump: every form that writes taps writes ten files,
the six of before plus theta_gained.f64, gamma_gained.f64, binaural.f64,
binaural_gained.f64.

Engine against reference: every render fixture at both rates, 1 s windows
around every ramp edge (the hash probe windows) and around the loop join
and the first and last seams of the looping fixtures: every tap and the
output within row reference-match (max difference, and the match
assertion wherever both sides are above row reference-match-min-level).
The ramp tool on every layer tap pair and the master, and the click tool on
every after-gain tap and the output, in every window. A harness recipe made
here with 10 ms to 1 s ramps on all four schedules (12 s) gives completed
changes to every tool on the whole render. Must-fail, doctored here: a 5 ms
fade spliced into a layer tap fails the ramp tool.

Cost: windows only for the long fixtures; each tap file is deleted as soon
as it is read. The tests skip only when cmake is not on PATH, or when
Windows application control blocks a binary.
"""

import json
import math

import numpy as np
import pytest

import gain_common as gc
import preview_common as common
from assertions import row as table_row

SAMPLE_RATES = gc.sample_rates()
RENDER_FIXTURES = gc.constants()["render_fixtures"]
CASES = [pytest.param(f, fs, id=f"{f}-{fs}") for f in RENDER_FIXTURES for fs in SAMPLE_RATES]


@pytest.fixture(scope="module")
def tapdump():
    return common.build("arcani-tapdump", common.TAPDUMP)


def loop_windows(recipe, fs, end):
    """Window starts around the loop join O and the first and last seams."""
    loop = recipe.get("loop")
    if loop is None:
        return []
    o = gc.seconds_to_samples(float(loop["opening_s"]), fs)
    b = gc.seconds_to_samples(float(loop["body_s"]), fs)
    seams = list(range(o + b, end, b))
    edges = ([o] if o > 0 else []) + seams[:1] + seams[-1:]
    return [gc.window_start(e, fs, end)[0] for e in edges]


def windows_of(fixture, fs):
    v = gc.window(fixture, fs)
    end = int(v["end_frame"])
    starts = [int(s) for s in v["probe_starts"]]
    starts += loop_windows(gc.load_recipe(fixture), fs, end)
    return sorted(set(starts)), int(v["probe_window_frames"])


def match_problems(name, eng, ref):
    """Every key within row reference-match: the max difference always, the
    match assertion where both sides are above the silent floor."""
    mod = gc.reference_match()
    threshold = table_row("reference-match").value
    floor = table_row("reference-match-min-level").value
    p = []
    for key in gc.TAP_KEYS:
        e, r = eng[key], ref[key]
        if e.shape != r.shape:
            p.append(f"{name} {key}: shape {e.shape} vs {r.shape}")
            continue
        if not (np.all(np.isfinite(e)) and np.all(np.isfinite(r))):
            p.append(f"{name} {key}: not finite")
            continue
        d = mod.difference_dbfs(e, r)
        if not d < threshold:
            p.append(f"{name} {key}: difference {d} dBFS")
        for c, side in ((0, "left"), (1, "right")):
            ec, rc = gc.channel(e, c), gc.channel(r, c)
            if mod.level_dbfs(ec) >= floor and mod.level_dbfs(rc) >= floor:
                a = mod.match(f"{name} {key} {side}", ec, rc)
                if a["result"] != "pass":
                    p.append(str(a))
    return p


def ramp_problems(name, taps, fs, g=1.0):
    """The ramp tool on every layer pair and the master, both channels."""
    m = gc.tool()
    p = []
    for before, after, _ in gc.LAYER_PAIRS:
        for c in (0, 1):
            r = m.check(f"{name} {after} {c}", gc.channel(taps[before], c), gc.channel(taps[after], c), fs)
            if r["result"] != "pass":
                p.append(str(r))
    for c in (0, 1):
        r = m.check(f"{name} master {c}", gc.channel(taps["join"], c) * g, gc.channel(taps["output"], c), fs)
        if r["result"] != "pass":
            p.append(str(r))
    return p


def click_problems(name, taps, fs):
    clicks = gc.clicks()
    p = []
    for key in ("theta_gained", "gamma_gained", "binaural_gained", "output"):
        for c in (0, 1):
            r = clicks.check(f"{name} {key} {c}", gc.channel(taps[key], c), fs)
            if r["result"] != "pass":
                p.append(str(r))
    return p


# ------------------------------------------------------------ reference/gain.py


def test_reference_keys_are_the_ten_taps():
    sc = gc.stub_chain()
    assert tuple(sc.KEYS) == gc.TAP_KEYS
    assert tuple(gc.constants()["new_taps"]) == gc.TAP_KEYS[6:]


@pytest.mark.parametrize("fixture,fs", CASES)
def test_reference_gain_frames_are_the_fixture_ramp_vectors(fixture, fs):
    rg = gc.reference_gain()
    recipe = gc.load_recipe(fixture)
    got = []
    for schedule, gain in gc.schedules(recipe).items():
        for n0, length, n1, a, b in rg.frames(gain, fs):
            got.append((schedule, int(n0), int(length), int(n1), float(a), float(b)))
    want = [(r["schedule"], int(r["start_frame"]), int(r["length_frames"]), int(r["end_frame"]), float(r["from"]),
             float(r["to"])) for r in gc.fixture_ramps(fixture, fs)]
    assert got == want


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_gain_values_follow_the_law(fs):
    rg = gc.reference_gain()
    gain = {"initial": 1.0, "ramps": [{"start_s": 1.0, "duration_s": 0.01, "to": 0.5},
                                      {"start_s": 2.0, "duration_s": 0.5, "to": 0.0}]}
    ten = gc.seconds_to_samples(0.01, fs)
    half = gc.seconds_to_samples(0.5, fs)
    n = np.arange(3 * fs, dtype=np.uint64)
    v = rg.values(gain, fs, n)
    assert isinstance(v, np.ndarray) and v.dtype == np.float64 and v.size == n.size
    want = gc.gain_curve(3 * fs, 1.0, [(fs, gc.raised_cosine(1.0, 0.5, ten), 0.5),
                                       (2 * fs, gc.raised_cosine(0.5, 0.0, half), 0.0)])
    assert np.array_equal(v.view(np.uint64), want.view(np.uint64))
    # Ends exact: a at n0, b from n1 on.
    assert v[fs] == 1.0 and v[fs + ten] == 0.5 and v[2 * fs] == 0.5 and v[2 * fs + half] == 0.0
    assert np.all(rg.values(None, fs, n) == 1.0)
    # Must-fail: one frame of the doctored law differs.
    doctored = want.copy()
    doctored[fs + 3] = np.nextafter(doctored[fs + 3], 2.0)
    assert not np.array_equal(v.view(np.uint64), doctored.view(np.uint64))


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_reference_gained_taps_equal_their_partners_without_gain(fs):
    sc = gc.stub_chain()
    path = gc.FIXTURES_VALID / "both-layers.json"
    r = sc.render(path, fs, frames=4096)
    for before, after, _ in gc.LAYER_PAIRS:
        assert np.array_equal(r[before].view(np.uint64), r[after].view(np.uint64)), after
    assert np.array_equal(r["bus"].view(np.uint64), (r["theta_gained"] + r["gamma_gained"]).view(np.uint64))
    assert np.array_equal(r["join"].view(np.uint64), (r["bus"] + r["binaural_gained"]).view(np.uint64))


# ------------------------------------------------------------ engine against reference


@pytest.mark.parametrize("fixture,fs", CASES)
def test_engine_matches_the_reference_around_every_edge(tapdump, tmp_path, fixture, fs):
    sc = gc.stub_chain()
    path = gc.FIXTURES_VALID / fixture
    starts, length = windows_of(fixture, fs)
    problems = []
    for start in starts:
        eng = gc.dump_window(tapdump, path, fs, start, length, tmp_path / f"w{start}")
        ref = sc.render(path, fs, frames=length, start=start)
        name = f"{fixture} {fs} from {start}"
        problems += match_problems(name, eng, ref)
        problems += ramp_problems(name, eng, fs)
        problems += click_problems(name, eng, fs)
    assert problems == []


def test_gain_master_fade_window_ends_in_exact_zeros(tapdump, tmp_path):
    fixture = gc.constants()["fade_fixture"]
    for fs in SAMPLE_RATES:
        ramp = [r for r in gc.fixture_ramps(fixture, fs) if r["schedule"] == "master"][-1]
        n1 = int(ramp["end_frame"])
        start, length = gc.window_start(n1, fs, int(gc.window(fixture, fs)["end_frame"]))
        eng = gc.dump_window(tapdump, gc.FIXTURES_VALID / fixture, fs, start, length, tmp_path / str(fs))
        tail = eng["output"][2 * (n1 - start):]
        assert tail.size > 0 and np.all(tail == 0.0), fs
        assert np.any(eng["output"][:2 * (n1 - start)] != 0.0), fs
        assert np.all(common.quantize_24(tail) == 0), fs


# ------------------------------------------------------------ every schedule, completed changes


def short_ramps_recipe(path):
    """A harness recipe: the gain compile base recipe (a 450 Hz carrier
    amplitude-modulated by the sine envelope at a fixed 4 Hz theta rate, 75
    percent depth; a 250 Hz sine carrier amplitude-modulated at 40 Hz with a
    smooth swell peaking at the 0 degree coupling phase, 100 percent depth;
    a 100 Hz pure sine in the left ear and a 102 Hz pure sine in the right
    ear), 12 s, with ramps of 10 ms to 1 s on all four schedules."""
    recipe = json.loads(gc.compile_case("unity schedule")["recipe"])
    recipe["rationale"] = "Story 4.4 harness recipe: short gain ramps on every schedule. A test recipe, not for listening."
    recipe["length_s"] = 12
    recipe["theta_reference"]["gain"] = {"initial": 1, "ramps": [{"start_s": 2, "duration_s": 0.01, "to": 0.5},
                                                                 {"start_s": 6, "duration_s": 0.02, "to": 1}]}
    recipe["gamma_pac"]["gain"] = {"initial": 1, "ramps": [{"start_s": 3, "duration_s": 0.01, "to": 0.25},
                                                           {"start_s": 7, "duration_s": 0.01, "to": 1}]}
    recipe["binaural"]["gain"] = {"initial": 0, "ramps": [{"start_s": 1, "duration_s": 0.01, "to": 1},
                                                          {"start_s": 8, "duration_s": 0.01, "to": 0.5}]}
    recipe["master"] = {"gain": {"initial": 1, "ramps": [{"start_s": 4, "duration_s": 0.01, "to": 0.5},
                                                         {"start_s": 9, "duration_s": 1, "to": 1}]}}
    path.write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
    return path, recipe


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_short_ramps_on_every_schedule_complete_and_last_at_least_10_ms(tapdump, tmp_path, fs):
    m = gc.tool()
    sc = gc.stub_chain()
    path, recipe = short_ramps_recipe(tmp_path / "short-ramps.json")
    total = gc.seconds_to_samples(float(recipe["length_s"]), fs)
    eng = gc.dump_window(tapdump, path, fs, 0, total, tmp_path / "dump")
    ref = sc.render(path, fs, frames=total, start=0)
    assert match_problems(f"short ramps {fs}", eng, ref) == []
    gains = gc.schedules(recipe)
    pairs = [(b, a, s) for b, a, s in gc.LAYER_PAIRS] + [("join", "output", "master")]
    for before, after, schedule in pairs:
        ramps = gains[schedule]["ramps"]
        for c in (0, 1):
            est = m.estimate(gc.channel(eng[before], c), gc.channel(eng[after], c))
            found = m.changes(est, fs)
            assert len(found) == len(ramps), (schedule, c, found)
            for change, ramp in zip(found, ramps):
                n0 = gc.seconds_to_samples(float(ramp["start_s"]), fs)
                length = gc.seconds_to_samples(float(ramp["duration_s"]), fs)
                # The engine gain at n0 is a + (b - a) * 2.8e-8 (Gain ramps, Law),
                # so the change starts one frame early.
                assert n0 - 2 <= change["start"] <= n0, (schedule, change)
                assert n0 + length - 1 <= change["end"] <= n0 + length + 1, (schedule, change)
                assert abs(change["to"] - float(ramp["to"])) <= m.HOLD_TOL, (schedule, change)
            r = m.check(f"short ramps {schedule} {c}", gc.channel(eng[before], c), gc.channel(eng[after], c), fs)
            assert r["result"] == "pass", r
            assert r["measured"] >= gc.ramp_min_ms(), r
    # Clicks around every edge of every schedule.
    edges = []
    for gain in gains.values():
        for ramp in gain["ramps"]:
            n0 = gc.seconds_to_samples(float(ramp["start_s"]), fs)
            edges += [n0, n0 + gc.seconds_to_samples(float(ramp["duration_s"]), fs)]
    for edge in sorted(edges):
        start, length = gc.window_start(edge, fs, total)
        part = {k: v[2 * start:2 * (start + length)] for k, v in eng.items()}
        assert click_problems(f"short ramps {fs} edge {edge}", part, fs) == []

    # Must-fail: a 5 ms fade spliced into the theta after-gain tap, in its
    # hold at 0.5 between 2 s and 6 s, fails the ramp tool.
    five = gc.seconds_to_samples(float(gc.constants()["must_fail_fade_s"]), fs)
    at = 4 * fs + 123
    before = gc.channel(eng["theta"], 0)
    after = gc.channel(eng["theta_gained"], 0).copy()
    fade = gc.gain_curve(after.size, 1.0, [(at, gc.raised_cosine(1.0, 0.5, five), 0.5)])
    doctored = after * fade
    r = m.check("doctored 5 ms theta fade", before, doctored, fs)
    assert r["result"] == "fail", r
    assert r["measured"] == pytest.approx(1000.0 * five / fs, abs=1000.0 * 2 / fs), r
