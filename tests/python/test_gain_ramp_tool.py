"""Ramp tool, calibrated on Python-synthesized signals (Story 4.4;
docs/signal-spec.md, Gain ramps, Ramp tool).

Contract with tests/assertions/gain_ramps.py (imported as
`assertions.gain_ramps`; NumPy and the standard library only):

- HOLD_TOL = 1e-9 (gain units), MIN_DIVISOR = 2**-30.
- `estimate(before, after) -> ndarray`: one channel, float64, after /
  before, NaN where |before| < MIN_DIVISOR.
- `changes(est, fs) -> list[dict]`: every completed change, in time order,
  as {"start": the last frame at the old held value, "end": the first frame
  of the new held value, "from", "to", "frames": end - start}. A value is
  held when every valid (non-NaN) estimate in the next round(0.010 * fs)
  frames (or to the end) is within HOLD_TOL of it.
- `check(name, before, after, fs) -> dict`: the report assertion shape
  (name, row "gain-ramp-min", threshold the row value, unit "ms", measured
  the shortest change in ms or None, result, note): pass when every change
  lasts at least the row (inclusive), or there is none (note "no change");
  a non-finite input fails with note "not finite" and measured None.
- The master is checked with before = join * g (the loudness gain) and
  after = output.

Calibration: a 450 Hz sine times raised-cosine ramps of 441, 480, and
13230000 frames, linear ramps, and steps, each of a known change length,
at both rates; every 10 ms ramp passes. Must-fails: a 5 ms raised-cosine
fade (gain_constants.must_fail_fade_s), a ramp one frame short of 10 ms,
and a step fail. The click tool passes 10 ms raised-cosine fades of a
full-scale tone and fails a step.

Every signal starts and ends in a hold of at least 10 ms, and every ramp
edge is placed off the zero crossings of the 450 Hz tone (where the
estimate is NaN), so its change runs exactly from the ramp's first frame to
its end frame.
"""

import ast
import math
import sys

import numpy as np
import pytest

import gain_common as gc
from assertions import row as table_row

SAMPLE_RATES = gc.sample_rates()
REPORT_KEYS = ["name", "row", "threshold", "unit", "measured", "result", "note"]
N0 = 1000  # off every zero crossing of 450 Hz at both rates (period 98 and 320/3 frames)


def tool():
    return gc.tool()


def ten_ms_frames(fs):
    return gc.seconds_to_samples(gc.ramp_min_ms() / 1000.0, fs)


def signal(fs, initial, segments, total):
    """(before, after): the 450 Hz sine and the sine times the gain curve."""
    before = gc.tone(450, fs, total)
    g = gc.gain_curve(total, initial, segments)
    return before, before * g, g


def hold_frames(fs):
    return 2 * ten_ms_frames(fs) + 17


# ------------------------------------------------------------ the module


def test_module_uses_numpy_and_the_standard_library_only():
    m = tool()
    tree = ast.parse(open(m.__file__, encoding="utf-8").read())
    allowed = set(sys.stdlib_module_names) | {"numpy", "assertions"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] in allowed, a.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            assert node.module.split(".")[0] in allowed, node.module


def test_constants_and_rows():
    m = tool()
    assert m.HOLD_TOL == 1e-9
    assert m.MIN_DIVISOR == 2.0 ** -30
    k = gc.constants()
    assert gc.ramp_min_ms() == float(k["ramp_min_ms"])
    assert gc.ramp_min_ms() / 1000.0 == float.fromhex(k["ramp_min_s_hex"])
    assert float(k["must_fail_fade_s"]) * 1000.0 < gc.ramp_min_ms()
    layer = gc.layer_gain_row()
    assert (layer.min, layer.max, layer.max_bound) == (float(k["layer_gain_min"]), float(k["layer_gain_max"]),
                                                       "inclusive")
    count = gc.ramp_count_row()
    assert (count.min, count.max) == (0.0, float(k["ramp_count_max"]))
    for fs in SAMPLE_RATES:
        assert ten_ms_frames(fs) == fs // 100


# ------------------------------------------------------------ estimate


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_estimate_is_after_over_before_nan_near_zero(fs):
    m = tool()
    before, after, g = signal(fs, 1.0, [(N0, gc.raised_cosine(1.0, 0.25, 441), 0.25)], 4000)
    est = m.estimate(before, after)
    assert isinstance(est, np.ndarray) and est.dtype == np.float64 and est.shape == before.shape
    small = np.abs(before) < m.MIN_DIVISOR
    assert small.any()  # the zero crossings
    assert np.all(np.isnan(est[small]))
    assert not np.any(np.isnan(est[~small]))
    assert np.allclose(est[~small], g[~small], rtol=0, atol=1e-15)


# ------------------------------------------------------------ calibration


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("length", [441, 480])
def test_raised_cosine_ramps_measure_as_constructed(fs, length):
    m = tool()
    tail = hold_frames(fs)
    total = N0 + length + tail
    before, after, _ = signal(fs, 1.0, [(N0, gc.raised_cosine(1.0, 0.25, length), 0.25)], total)
    found = m.changes(m.estimate(before, after), fs)
    assert len(found) == 1, found
    c = found[0]
    assert (c["start"], c["end"], c["frames"]) == (N0, N0 + length, length), c
    assert abs(c["from"] - 1.0) <= m.HOLD_TOL and abs(c["to"] - 0.25) <= m.HOLD_TOL, c


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_several_changes_in_time_order(fs):
    m = tool()
    ten = ten_ms_frames(fs)
    hold = hold_frames(fs)
    n1 = N0 + ten
    n2 = n1 + hold + 3
    n3 = n2 + 3 * ten
    n4 = n3 + hold + 5
    total = n4 + 1 + hold
    segments = [(N0, gc.raised_cosine(1.0, 0.0, ten), 0.0),
                (n2, gc.linear(0.0, 0.5, 3 * ten), 0.5),
                (n4, np.array([0.5]), 0.75)]  # a one-frame ramp: 0.5 at n4, 0.75 from n4 + 1
    before, after, _ = signal(fs, 1.0, segments, total)
    # Every edge is off the NaN frames of the zero crossings.
    est = m.estimate(before, after)
    for frame in (N0, n1, n2, n3, n4, n4 + 1):
        assert not math.isnan(est[frame]), frame
    found = m.changes(est, fs)
    assert [(c["start"], c["end"], c["frames"]) for c in found] == [
        (N0, n1, ten), (n2, n3, 3 * ten), (n4, n4 + 1, 1)], found
    assert [round(c["to"], 6) for c in found] == [0.0, 0.5, 0.75]


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_a_step_is_one_frame(fs):
    m = tool()
    hold = hold_frames(fs)
    before, after, _ = signal(fs, 0.5, [(N0, np.zeros(0), 1.0)], N0 + hold)
    found = m.changes(m.estimate(before, after), fs)
    assert [(c["start"], c["end"], c["frames"]) for c in found] == [(N0 - 1, N0, 1)], found


def test_five_minute_raised_cosine_is_most_of_its_length():
    """13230000 frames (5 min at 44.1 kHz): the ends of the raised cosine
    are within HOLD_TOL of the held values for a few hundred frames, so the
    change runs from the last frame within HOLD_TOL of the old value to the
    first within HOLD_TOL of the new one, both read from the gain curve."""
    m = tool()
    fs = 44100
    length = 13230000
    tail = hold_frames(fs)
    total = N0 + length + tail
    before, after, g = signal(fs, 0.0, [(N0, gc.raised_cosine(0.0, 1.0, length), 1.0)], total)
    est = m.estimate(before, after)
    r = m.check("5 min ramp", before, after, fs)
    assert r["result"] == "pass", r
    del after
    valid = ~np.isnan(est)
    old = np.nonzero(valid & (np.abs(g - 0.0) <= m.HOLD_TOL))[0]
    new = np.nonzero(valid & (np.abs(g - 1.0) <= m.HOLD_TOL))[0]
    start = int(old[old < N0 + length // 2].max())
    end = int(new[new > N0 + length // 2].min())
    del g, before, valid
    found = m.changes(est, fs)
    assert len(found) == 1, found
    c = found[0]
    assert (c["start"], c["end"], c["frames"]) == (start, end, end - start), (c, start, end)
    assert N0 <= start < N0 + 1000 and N0 + length - 1000 < end <= N0 + length, c
    assert r["measured"] == pytest.approx(1000.0 * (end - start) / fs, abs=1e-9), r


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_a_ramp_cut_5_ms_after_its_start_is_no_change(fs):
    """A signal that ends inside a ramp closes no change: a 10 ms raised cosine
    cut 5 ms after n0 gives none, and the check passes with note no change."""
    m = tool()
    ten = ten_ms_frames(fs)
    five = gc.seconds_to_samples(float(gc.constants()["must_fail_fade_s"]), fs)
    total = N0 + five
    ramp = gc.raised_cosine(1.0, 0.0, ten)[:five]
    before, after, _ = signal(fs, 1.0, [(N0, ramp, float(ramp[-1]))], total)
    assert m.changes(m.estimate(before, after), fs) == []
    r = m.check("cut ramp", before, after, fs)
    assert (r["result"], r["measured"], r["note"]) == ("pass", None, "no change"), r


# ------------------------------------------------------------ the assertion


def report_problems(r, name):
    p = []
    if list(r) != REPORT_KEYS:
        p.append(f"keys {list(r)}")
    row = table_row(gc.RAMP_MIN_ROW)
    if r.get("name") != name or r.get("row") != gc.RAMP_MIN_ROW or r.get("threshold") != row.value \
            or r.get("unit") != row.unit:
        p.append(f"shape {r}")
    return p


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_every_10_ms_ramp_passes_at_both_rates(fs):
    m = tool()
    ten = ten_ms_frames(fs)
    for a, b in ((1.0, 0.0), (0.0, 1.0), (0.75, 0.25)):
        before, after, _ = signal(fs, a, [(N0, gc.raised_cosine(a, b, ten), b)], N0 + ten + hold_frames(fs))
        r = m.check("ramp", before, after, fs)
        assert report_problems(r, "ramp") == [], r
        assert r["result"] == "pass", (a, b, r)
        assert r["measured"] == pytest.approx(1000.0 * ten / fs, abs=1e-9), r
        assert r["measured"] >= gc.ramp_min_ms()


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_must_fail_a_5_ms_fade_one_frame_short_and_a_step(fs):
    m = tool()
    hold = hold_frames(fs)
    five = gc.seconds_to_samples(float(gc.constants()["must_fail_fade_s"]), fs)
    short = ten_ms_frames(fs) - 1
    for label, length in (("5 ms fade", five), ("one frame short", short)):
        before, after, _ = signal(fs, 1.0, [(N0, gc.raised_cosine(1.0, 0.0, length), 0.0)], N0 + length + hold)
        r = m.check(label, before, after, fs)
        assert report_problems(r, label) == [], r
        assert r["result"] == "fail", (label, r)
        assert r["measured"] == pytest.approx(1000.0 * length / fs, abs=1e-9), r
    before, after, _ = signal(fs, 1.0, [(N0, np.zeros(0), 0.5)], N0 + hold)
    r = m.check("step", before, after, fs)
    assert r["result"] == "fail" and r["measured"] == pytest.approx(1000.0 / fs, abs=1e-9), r


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_no_change_passes_and_non_finite_fails(fs):
    m = tool()
    before = gc.tone(450, fs, fs // 10)
    r = m.check("hold", before, 0.5 * before, fs)
    assert report_problems(r, "hold") == [], r
    assert (r["result"], r["measured"], r["note"]) == ("pass", None, "no change"), r
    bad = before.copy()
    bad[100] = np.nan
    for b, a in ((bad, before), (before, bad)):
        r = m.check("nan", b, a, fs)
        assert (r["result"], r["measured"], r["note"]) == ("fail", None, "not finite"), r
    inf = before.copy()
    inf[7] = np.inf
    r = m.check("inf", before, inf, fs)
    assert (r["result"], r["note"]) == ("fail", "not finite"), r


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_master_through_join_times_the_loudness_gain(fs):
    m = tool()
    ten = ten_ms_frames(fs)
    hold = hold_frames(fs)
    total = N0 + 2 * ten + hold
    join = gc.tone(450, fs, total) + 0.5 * gc.tone(100, fs, total)
    g = 10.0 ** (-10.0 / 20.0)
    gm = gc.gain_curve(total, 1.0, [(N0, gc.raised_cosine(1.0, 0.0, 2 * ten), 0.0)])
    output = (join * g) * gm
    r = m.check("master", join * g, output, fs)
    assert r["result"] == "pass", r
    assert r["measured"] == pytest.approx(1000.0 * 2 * ten / fs, abs=1e-9), r
    # Must-fail: a 5 ms master fade.
    five = gc.seconds_to_samples(float(gc.constants()["must_fail_fade_s"]), fs)
    gm5 = gc.gain_curve(total, 1.0, [(N0, gc.raised_cosine(1.0, 0.0, five), 0.0)])
    assert m.check("master", join * g, (join * g) * gm5, fs)["result"] == "fail"


# ------------------------------------------------------------ the click tool on ramp edges


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_click_tool_passes_10_ms_raised_cosine_fades_and_fails_a_step(fs):
    clicks = gc.clicks()
    ten = ten_ms_frames(fs)
    n0 = fs // 2 + 17
    total = fs
    x = gc.tone(450, fs, total)
    for a, b in ((1.0, 0.0), (0.0, 1.0)):
        g = gc.gain_curve(total, a, [(n0, gc.raised_cosine(a, b, ten), b)])
        r = clicks.check("fade", x * g, fs)
        assert r["result"] == "pass", (a, b, r)
    step = gc.gain_curve(total, 1.0, [(n0 + 20, np.zeros(0), 0.0)])
    r = clicks.check("step", x * step, fs)
    assert r["result"] == "fail", r
