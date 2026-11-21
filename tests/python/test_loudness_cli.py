"""arcani-render --loudness against the Python loudness meter on the engine
output (Story 4.1; docs/signal-spec.md, Loudness, Window, Report).

Contract with arcani-render (spec Implementation Notes, Report and CLI):
`--loudness` (no value) adds the report member `loudness` after `spacing`
(or `loop`, or `frames`) and before `determinism_key`, with exactly
window_start_frame (O, 0 without a loop), window_body_frames (B, N without
a loop), window_repeats (k, 1 without a loop), window_frames (k * B),
window_lufs_i and whole_lufs_i (shortest round-trip numbers, null for
-inf), in that order. The WAV and every other report member are the render
without `--loudness`, byte for byte. A non-looping recipe shorter than row
loudness-window-min is refused: exit 1, one stderr line
"rejected: parameter=/length_s value=<N / fs> rule=loudness_window_rule
limit=>= 60 s (row loudness-window-min)", nothing written.

The Python meter (tests/assertions/loudness.py) reads the same engine
output from arcani-tapdump: `--output-only` without a loop (the window is
the whole session), `--window O B` repeated k times as one signal with one.
Every agreement fixture (Vectors: loudness windows, result accepted) is
checked at both rates within row loudness-meter-agreement. Fixtures that
share a recipe hash (the same determinism key, so the same output by rule
1) share one tap dump: each is still rendered and read by the command-line
meter, and their command-line readings must be bit-equal. For the
whole-render fixtures (loudness_constants.whole_fixtures) the whole render
is compared too; for every non-looping fixture whole_lufs_i equals
window_lufs_i.

Must-fails, doctored here: the command-line reading moved by 0.2 LU fails
the agreement check; both rejected fixtures are refused.

Cost: every large file (WAV, out.f64) is deleted as soon as it is read;
the tap dump is read through np.memmap. The tests skip only when cmake is
not on PATH, or when Windows application control blocks a binary.
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest

import loudness_common as lc
import preview_common as common
import spacing_common

SAMPLE_RATES = lc.sample_rates()
HASHES = json.loads((lc.REPO_ROOT / "tests" / "data" / "recipe_hash_vectors.json").read_text(encoding="utf-8"))
DOCTOR_LU = 0.2


def _groups():
    """Agreement fixtures grouped by recipe hash, in vector order."""
    groups = {}
    for name in lc.constants()["agreement_fixtures"]:
        groups.setdefault(HASHES.get(name, name), []).append(name)
    return list(groups.values())


GROUPS = _groups()
GROUP_CASES = [pytest.param(g, fs, id=f"{g[0]}-{fs}") for g in GROUPS for fs in SAMPLE_RATES]
REJECTED_CASES = [pytest.param(f, fs, id=f"{f}-{fs}") for f in lc.constants()["rejected_fixtures"]
                  for fs in SAMPLE_RATES]


@pytest.fixture(scope="module")
def render():
    return common.build("arcani-render", common.RENDER)


@pytest.fixture(scope="module")
def tapdump():
    return common.build("arcani-tapdump", common.TAPDUMP)


def python_window(meter, tapdump_exe, recipe, fs, v, out_dir):
    """The Python meter's reading of the window of vector v."""
    start, body, k = int(v["start_frame"]), int(v["body_frames"]), int(v["repeats"])
    if v["looping"] == "no":
        assert (start, k) == (0, 1), v
        path = lc.tapdump(tapdump_exe, recipe, fs, out_dir)
    else:
        path = lc.tapdump(tapdump_exe, recipe, fs, out_dir, window=(start, body))
    with lc.f64_frames(path, frames=body) as mm:
        if k == 1:
            return meter.integrated_lufs(mm, fs)
        return meter.integrated_lufs(np.concatenate([np.asarray(mm)] * k), fs)


def python_whole(meter, tapdump_exe, recipe, fs, frames, out_dir):
    path = lc.tapdump(tapdump_exe, recipe, fs, out_dir)
    with lc.f64_frames(path, frames=frames) as mm:
        return meter.integrated_lufs(mm, fs)


def loudness_report(render, recipe, fs, out_dir):
    """Renders with --loudness, deletes the WAV, returns (report text, report)."""
    r, wav, report_path = lc.render_cli(render, recipe, fs, out_dir)
    assert r.returncode == 0, r.stdout + r.stderr
    assert wav.is_file()
    lc.unlink(wav)
    text = report_path.read_text(encoding="utf-8")
    return text, json.loads(text)


def placement_problems(report):
    keys = list(report)
    if "loudness" not in keys:
        return [f"no loudness member: {keys}"]
    p = []
    if "preview" in keys:
        p.append("a loudness report with a preview member")
    if keys.index("loudness") != keys.index("determinism_key") - 1:
        p.append(f"loudness is not right before determinism_key: {keys}")
    before = keys[keys.index("frames") + 1:keys.index("loudness")]
    if [k for k in before if k not in ("loop", "spacing")] or before not in (
            [], ["loop"], ["spacing"], ["loop", "spacing"]):
        p.append(f"members between frames and loudness: {before}")
    return p


# ------------------------------------------------------------ agreement set


def test_agreement_set_is_the_accepted_windows():
    accepted = {r["fixture"] for r in lc.vectors()["loudness_windows"] if r["result"] == "accepted"}
    rejected = {r["fixture"] for r in lc.vectors()["loudness_windows"] if r["result"] == "rejected"}
    assert set(lc.constants()["agreement_fixtures"]) == accepted
    assert set(lc.constants()["rejected_fixtures"]) == rejected
    assert set(lc.constants()["whole_fixtures"]) <= accepted
    for name in lc.constants()["whole_fixtures"]:
        assert all(lc.window_row(name, fs)["looping"] == "yes" for fs in SAMPLE_RATES), name
    for g in GROUPS:
        for fs in SAMPLE_RATES:
            assert len({json.dumps({k: lc.window_row(f, fs)[k] for k in ("end_frame", "start_frame", "body_frames",
                                                                             "repeats", "window_frames")})
                        for f in g}) == 1, g


@pytest.mark.parametrize("group,fs", GROUP_CASES)
def test_cli_and_python_meters_agree(render, tapdump, tmp_path, group, fs):
    meter = lc.meter()
    tol = lc.agreement_lu()
    whole_fixtures = set(lc.constants()["whole_fixtures"])
    readings = []
    # One determinism key, one output: only the group's first fixture is
    # rendered (the rest of the group renders the same samples).
    for i, fixture in enumerate(group[:1]):
        v = lc.window_row(fixture, fs)
        assert v["result"] == "accepted", v
        text, report = loudness_report(render, lc.FIXTURES_VALID / fixture, fs, tmp_path / f"cli-{i}")
        assert report["frames"] == int(v["end_frame"]), (fixture, report["frames"])
        assert placement_problems(report) == [], fixture
        assert ("loop" in report) == (v["looping"] == "yes"), fixture
        member = report["loudness"]
        assert lc.member_problems(member, v) == [], (fixture, member)
        if v["looping"] == "yes":
            assert member["window_start_frame"] == report["loop"]["opening_end_frame"]
        else:
            # A non-looping window meter is the whole-render meter.
            assert member["whole_lufs_i"] == member["window_lufs_i"], (fixture, member)
            if member["window_lufs_i"] is not None:
                assert common.bits(member["whole_lufs_i"]) == common.bits(member["window_lufs_i"])
        readings.append((fixture, member["window_lufs_i"], member["whole_lufs_i"]))

    fixture = group[0]
    v = lc.window_row(fixture, fs)
    recipe = lc.FIXTURES_VALID / fixture
    py = python_window(meter, tapdump, recipe, fs, v, tmp_path / "dump")
    assert isinstance(py, float)
    cpp_window, cpp_whole = readings[0][1], readings[0][2]
    assert lc.agreement_problems(cpp_window, py, tol) == [], (fixture, fs, cpp_window, py)
    if math.isfinite(py):
        # Must-fail: the command-line reading moved by 0.2 LU.
        assert lc.agreement_problems(cpp_window + DOCTOR_LU, py, tol), (fixture, fs)
        assert lc.agreement_problems(cpp_window - DOCTOR_LU, py, tol), (fixture, fs)
        assert lc.agreement_problems(None, py, tol)
    else:
        assert lc.agreement_problems(-120.0, py, tol)

    if fixture in whole_fixtures:
        py_whole = python_whole(meter, tapdump, recipe, fs, int(v["end_frame"]), tmp_path / "whole")
        assert math.isfinite(py_whole)
        assert lc.agreement_problems(cpp_whole, py_whole, tol) == [], (fixture, fs, cpp_whole, py_whole)
        assert lc.agreement_problems(cpp_whole + DOCTOR_LU, py_whole, tol)


# ------------------------------------------------------------ a body repeated k times


def body_25_recipe(path):
    """A harness looping recipe for window case `loop, body 25 s`: the
    loop-focus-no-cycle.json layers (no rate cycle, so any whole-sample body)
    in learn mode, 20 min cap, opening 10 s, body 25 s."""
    recipe = json.loads((lc.FIXTURES_VALID / "loop-focus-no-cycle.json").read_text(encoding="utf-8"))
    case = lc.window_case("loop, body 25 s", SAMPLE_RATES[0])
    recipe["rationale"] = ("Story 4.1 harness recipe: loudness window case loop, body 25 s. Theta reference: a 450 Hz "
                           "carrier amplitude-modulated by the sine envelope at a fixed 4 Hz theta rate, 75 percent "
                           "AM depth. A test recipe, not for listening.")
    recipe["length_s"] = float(case["length_s"])
    recipe["loop"] = {"mode": "learn", "opening_s": float(case["opening_s"]), "body_s": float(case["body_s"]),
                      "max_run_time_min": 20}
    path.write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_body_25_s_is_measured_three_times_and_agrees(render, tapdump, tmp_path, fs):
    meter = lc.meter()
    case = lc.window_case("loop, body 25 s", fs)
    assert case["repeats"] == "3", case
    recipe = body_25_recipe(tmp_path / "body-25.json")
    r, wav, report_path = lc.render_cli(render, recipe, fs, tmp_path / "with")
    assert r.returncode == 0, r.stdout + r.stderr
    with_text = report_path.read_text(encoding="utf-8")
    report = json.loads(with_text)
    assert report["frames"] == int(case["end_frame"])
    assert placement_problems(report) == []
    member = report["loudness"]
    assert lc.member_problems(member, case) == [], member
    assert member["window_frames"] == 3 * member["window_body_frames"]

    # The WAV with --loudness is the WAV without; the report without has no
    # loudness member and is the report with it, that block removed.
    r2, wav2, report2_path = lc.render_cli(render, recipe, fs, tmp_path / "without", loudness=False)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert lc.file_digest(wav) == lc.file_digest(wav2)
    lc.unlink(wav)
    lc.unlink(wav2)
    without_text = report2_path.read_text(encoding="utf-8")
    assert "loudness" not in json.loads(without_text)
    assert '"loudness"' not in without_text
    block, rest = lc.loudness_block(with_text)
    assert rest == without_text
    assert block.startswith('  "loudness": {\n    "window_start_frame": ')

    py = python_window(meter, tapdump, recipe, fs, case, tmp_path / "dump")
    tol = lc.agreement_lu()
    assert lc.agreement_problems(member["window_lufs_i"], py, tol) == [], (member, py)
    assert lc.agreement_problems(member["window_lufs_i"] + DOCTOR_LU, py, tol)


@pytest.mark.parametrize("fs", SAMPLE_RATES[:1])
def test_non_looping_wav_and_report_unchanged_by_loudness(render, tmp_path, fs):
    fixture = "gamma-cycle-swell-theta-cycle.json"
    v = lc.window_row(fixture, fs)
    assert v["looping"] == "no" and v["result"] == "accepted"
    recipe = lc.FIXTURES_VALID / fixture
    r, wav, report_path = lc.render_cli(render, recipe, fs, tmp_path / "with")
    assert r.returncode == 0, r.stdout + r.stderr
    r2, wav2, report2_path = lc.render_cli(render, recipe, fs, tmp_path / "without", loudness=False)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert lc.file_digest(wav) == lc.file_digest(wav2)
    lc.unlink(wav)
    lc.unlink(wav2)
    with_text = report_path.read_text(encoding="utf-8")
    without_text = report2_path.read_text(encoding="utf-8")
    assert "loudness" not in json.loads(without_text)
    block, rest = lc.loudness_block(with_text)
    assert rest == without_text
    member = json.loads(with_text)["loudness"]
    assert lc.member_problems(member, v) == []
    assert member["window_lufs_i"] is not None and member["whole_lufs_i"] == member["window_lufs_i"]


# ------------------------------------------------------------ the window rule


@pytest.mark.parametrize("fixture,fs", REJECTED_CASES)
def test_short_fixture_is_refused_and_nothing_is_written(render, tmp_path, fixture, fs):
    v = lc.window_row(fixture, fs)
    assert v["result"] == "rejected" and v["looping"] == "no", v
    assert int(v["end_frame"]) < lc.seconds_to_samples(lc.window_min_s(), fs)
    assert v["parameter"] == lc.constants()["window_parameter"]
    assert v["rule"] == lc.constants()["window_rule"]
    assert v["limit"] == lc.constants()["window_limit"]
    assert v["value"] == spacing_common.shortest(int(v["end_frame"]) / fs)
    out_dir = tmp_path / "with"
    r, wav, report_path = lc.render_cli(render, lc.FIXTURES_VALID / fixture, fs, out_dir)
    assert r.returncode == 1, r.stdout + r.stderr
    lines = r.stderr.splitlines()
    assert lines == [lc.rejected_line(v)], r.stderr
    assert list(Path(out_dir).iterdir()) == []
    # Without --loudness the same short fixture renders as before.
    r2, wav2, report2_path = lc.render_cli(render, lc.FIXTURES_VALID / fixture, fs, tmp_path / "without",
                                           loudness=False)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert wav2.is_file() and report2_path.is_file()
    assert "loudness" not in json.loads(report2_path.read_text(encoding="utf-8"))
    _, frames, rate = common.wav_layout(wav2)
    assert (frames, rate) == (int(v["end_frame"]), fs)
