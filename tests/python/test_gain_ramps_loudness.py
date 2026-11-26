"""Loudness of the gain ramp fixtures (Story 4.4; docs/signal-spec.md,
Loudness, Window, Report, Agreement set; Loudness gain, Final-mode checks).

Contract with arcani-render `--loudness`: without a loop the window is the
longest stretch with no layer or master ramp active (ties to the earliest),
reported as window_start_frame s, window_body_frames e - s, window_repeats
1, window_frames e - s, and metered in its own pass by arc_seek; the whole
meter still reads [0, N). A non-looping window shorter than row
loudness-window-min is refused: exit 1, one stderr line "rejected:
parameter=/length_s value=<steady_frames / fs> rule=loudness_window_rule
limit=>= 60 s (row loudness-window-min)", nothing written. A looping
recipe keeps [O, O + kB).

Checks:
- every render fixture at both rates: the report member equals the
  gain_windows vector, and both meters agree on the window within row
  loudness-meter-agreement (the Python meter on the tap dump of the window);
- gain-layer-ramp-10min-stored.json (its gain stored with --store-gain on
  the dev PC) in final mode with --loudness: window [600 s, 720 s), the
  loudness assertion within row loudness-tolerance and loudness_whole never
  above target + the row;
- superseded-window must-fail: a gain computed here from the reading over
  [0, O + B) of gain-ramp-in-loop.json, applied to the body, reads above
  target + the row (check_loudness fails), while the gain from the body
  window passes; and the reading over [O, O + B) differs from [0, B) by more
  than row loudness-meter-agreement;
- a harness recipe whose steady stretch is 50 s is refused with value 50;
  one of exactly 60 s is accepted.

Cost: each WAV and dump is deleted as soon as it is read; the 20 min
fixtures are read through windows, the superseded window through one
output-only dump read with np.memmap (44.1 kHz only).
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest

import gain_common as gc
import loudness_common as lc
import preview_common as common
import spacing_common

SAMPLE_RATES = gc.sample_rates()
RENDER_FIXTURES = gc.constants()["render_fixtures"]
CASES = [pytest.param(f, fs, id=f"{f}-{fs}") for f in RENDER_FIXTURES for fs in SAMPLE_RATES]
DOCTOR_LU = 0.2


@pytest.fixture(scope="module")
def render():
    return common.build("arcani-render", common.RENDER)


@pytest.fixture(scope="module")
def tapdump():
    return common.build("arcani-tapdump", common.TAPDUMP)


def report_of(render, recipe, fs, out_dir, extra=()):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / "x.wav"
    r = common.run(render, [recipe, "--out", wav, "--rate", fs, "--loudness", *extra], timeout=900,
                   env=lc.clean_env())
    return r, wav, out_dir / "x.report.json"


def python_window(meter, tapdump_exe, recipe, fs, start, frames, out_dir):
    path = lc.tapdump(tapdump_exe, recipe, fs, out_dir, window=(start, frames))
    with lc.f64_frames(path, frames=frames) as mm:
        return meter.integrated_lufs(mm, fs)


@pytest.mark.parametrize("fixture,fs", CASES)
def test_both_meters_agree_on_every_gain_fixture_window(render, tapdump, tmp_path, fixture, fs):
    meter = lc.meter()
    v = gc.window(fixture, fs)
    recipe = gc.FIXTURES_VALID / fixture
    r, wav, report_path = report_of(render, recipe, fs, tmp_path / "cli")
    assert r.returncode == 0, r.stdout + r.stderr
    lc.unlink(wav)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["frames"] == int(v["end_frame"])
    member = report["loudness"]
    assert list(member) == lc.MEMBERS, member
    assert member["window_start_frame"] == int(v["start_frame"])
    assert member["window_body_frames"] == int(v["body_frames"])
    assert member["window_repeats"] == int(v["repeats"])
    assert member["window_frames"] == int(v["window_frames"])
    assert int(v["repeats"]) == 1
    py = python_window(meter, tapdump, recipe, fs, int(v["start_frame"]), int(v["body_frames"]), tmp_path / "dump")
    tol = lc.agreement_lu()
    assert lc.agreement_problems(member["window_lufs_i"], py, tol) == [], (member, py)
    assert lc.agreement_problems(member["window_lufs_i"] + DOCTOR_LU, py, tol)
    if v["looping"] == "no" and int(v["start_frame"]) > 0:
        # The window is not the whole render, so the two readings differ.
        assert member["whole_lufs_i"] != member["window_lufs_i"], member


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_stored_10_min_ramp_fixture_passes_loudness_in_final_mode(render, tmp_path, fs):
    name = gc.constants()["stored_fixture"]
    recipe = gc.FIXTURES_VALID / name
    assert recipe.is_file(), f"missing {name}: store it with --store-gain on the dev PC (Story 4.4)"
    stored = json.loads(recipe.read_text(encoding="utf-8"))
    source = gc.load_recipe(gc.constants()["stored_source"])
    for key in ("loudness_gain_db", "loudness_hash"):
        assert key in stored, key
    assert {k: v for k, v in stored.items() if k not in ("loudness_gain_db", "loudness_hash")} == source
    r, wav, report_path = report_of(render, recipe, fs, tmp_path / "final", extra=("--mode", "final"))
    assert r.returncode in (0, 4), r.stdout + r.stderr
    lc.unlink(wav)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    v = gc.window(gc.constants()["stored_source"], fs)
    member = report["loudness"]
    assert member["window_start_frame"] == int(v["start_frame"]) == lc.seconds_to_samples(600, fs)
    assert member["window_body_frames"] == int(v["body_frames"]) == lc.seconds_to_samples(120, fs)
    by_name = {a["name"]: a for a in report["assertions"]}
    tol = lc.tolerance_lu()
    target = float(stored["loudness_target_lufs"])
    assert by_name["loudness"]["result"] == "pass", by_name["loudness"]
    assert abs(member["window_lufs_i"] - target) <= tol, member
    assert by_name["loudness_whole"]["result"] == "pass", by_name["loudness_whole"]
    assert member["whole_lufs_i"] <= target + tol, member
    # The 10 min ramp-in makes the whole render quieter than the window.
    assert member["whole_lufs_i"] < member["window_lufs_i"], member


def test_superseded_window_must_fail_and_the_window_starts_at_O(tapdump, tmp_path):
    meter = lc.meter()
    fs = SAMPLE_RATES[0]
    fixture = gc.constants()["loop_window_fixture"]
    recipe = gc.FIXTURES_VALID / fixture
    target = float(gc.load_recipe(fixture)["loudness_target_lufs"])
    v = gc.window(fixture, fs)
    o, b, end = int(v["start_frame"]), int(v["body_frames"]), int(v["end_frame"])
    assert v["looping"] == "yes" and o > 0
    path = lc.tapdump(tapdump, recipe, fs, tmp_path / "dump")
    with lc.f64_frames(path, frames=end) as mm:
        body = np.array(mm[o:o + b])
        superseded = meter.integrated_lufs(mm[0:o + b], fs)
        first = meter.integrated_lufs(mm[0:b], fs)
    window = meter.integrated_lufs(body, fs)
    tol = lc.tolerance_lu()
    # The gain from the body window plays the body at the target.
    good = 10.0 ** ((target - window) / 20.0)
    ok = meter.check_loudness(body * good, fs, target)
    assert ok["result"] == "pass", ok
    # Must-fail: the gain from the superseded window [0, O + B), which takes
    # in the ramp-in, plays the body above target + the row.
    bad = 10.0 ** ((target - superseded) / 20.0)
    r = meter.check_loudness(body * bad, fs, target)
    assert r["result"] == "fail", (r, superseded, window)
    assert r["measured"] > tol, r
    # The reading over [O, O + B) differs from [0, B) by more than the
    # agreement row: the opening is not the body.
    assert abs(window - first) > lc.agreement_lu(), (window, first)


def short_steady_recipe(path, theta_ramp_s):
    """A harness recipe: gain-layer-ramp-10min.json shortened to 120 s, the
    theta ramp-in over theta_ramp_s, the gamma ramp-in over 10 s, so the
    steady stretch is [theta_ramp_s, 120 s)."""
    recipe = gc.load_recipe(gc.constants()["stored_source"])
    recipe["rationale"] = ("Story 4.4 harness recipe: a short steady stretch for the loudness window rule. "
                           "A test recipe, not for listening.")
    recipe["length_s"] = 120
    recipe["theta_reference"]["gain"]["ramps"][0]["duration_s"] = theta_ramp_s
    recipe["gamma_pac"]["gain"]["ramps"][0]["duration_s"] = 10
    path.write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_a_steady_stretch_shorter_than_60_s_is_refused(render, tmp_path, fs):
    recipe = short_steady_recipe(tmp_path / "short.json", 70)
    out_dir = tmp_path / "short-out"
    r, wav, report_path = report_of(render, recipe, fs, out_dir)
    assert r.returncode == 1, r.stdout + r.stderr
    steady = lc.seconds_to_samples(120, fs) - lc.seconds_to_samples(70, fs)
    value = spacing_common.shortest(steady / fs)
    assert value == "50"
    want = (f"rejected: parameter={lc.constants()['window_parameter']} value={value} "
            f"rule={lc.constants()['window_rule']} limit={lc.constants()['window_limit']}")
    assert r.stderr.splitlines() == [want], r.stderr
    assert list(out_dir.iterdir()) == []
    # Without --loudness it renders as before.
    out2 = tmp_path / "plain"
    out2.mkdir()
    r2 = common.run(render, [recipe, "--out", out2 / "x.wav", "--rate", fs], timeout=900, env=lc.clean_env())
    assert r2.returncode == 0, r2.stdout + r2.stderr
    lc.unlink(out2 / "x.wav")
    # Exactly 60 s of steady stretch is accepted, measured over [60 s, 120 s).
    recipe60 = short_steady_recipe(tmp_path / "sixty.json", 60)
    r3, wav3, report3 = report_of(render, recipe60, fs, tmp_path / "sixty-out")
    assert r3.returncode == 0, r3.stdout + r3.stderr
    lc.unlink(wav3)
    member = json.loads(report3.read_text(encoding="utf-8"))["loudness"]
    assert member["window_start_frame"] == lc.seconds_to_samples(60, fs)
    assert member["window_body_frames"] == lc.seconds_to_samples(60, fs)
    assert math.isfinite(member["window_lufs_i"])
