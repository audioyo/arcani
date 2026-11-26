"""arcani-render final-mode true peak against the Python true-peak meter on
the WAV's 24-bit samples (Story 4.3; docs/signal-spec.md, True peak,
Report).

Contract with arcani-render (spec Implementation Notes, Report and
cli/main.cpp): every final-mode render (`--mode final`, with or without
`--loudness`) adds the report member `true_peak` {"linear": TP, "dbtp":
20 log10(TP) or null at 0} after `loudness` (or `spacing`, `loop`,
`frames`) and before `determinism_key`, and the last assertion `true_peak`
(row true-peak, measured dbtp, pass when at or below the row value; a
failure exits 4 with the WAV and the report written). A measure-mode
render has neither. Both meters read the same integers exactly, so the
report's `linear` (the shortest round-trip text, parsed with `float`)
equals the Python meter's TP bit for bit.

Final renders read here at 44.1 and 48 kHz: the 1 s final fixture
(stub-chain-1s-beat-6.json), the committed stored fixture
(theta-cycle-sine-stored.json), and a temp copy of theta-cycle-sine.json
stored with --store-gain. The 45 min looping store fixture is read only by
the command-line test (its WAV is about 777 MB).

Must-fails, doctored here: the 1 s final fixture's samples scaled above the
ceiling fail `check_true_peak`; a temp copy of it whose stored gain is
raised to -6.50 dB renders above the ceiling, exits 4, and both meters
fail it. Every large file is deleted as soon as it is read; every store
works on a temp copy. The tests skip only when cmake is not on PATH, or
when Windows application control blocks a binary.
"""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

import loudness_common as lc
import preview_common as common
import true_peak_common as tc

SAMPLE_RATES = tc.sample_rates()
FINAL_FIXTURE = tc.constants()["final_fixture"]
STORED_FIXTURE = "theta-cycle-sine-stored.json"
STORE_COPY = "theta-cycle-sine.json"
RAISED_GAIN = "-6.50"


@pytest.fixture(scope="module")
def render():
    return common.build("arcani-render", common.RENDER)


def final_render(render, recipe, fs, out_dir, want_exit=0):
    """arcani-render RECIPE --out out_dir/x.wav --rate fs --mode final: (samples (frames, 2) int32, report)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / "x.wav"
    r = common.run(render, [recipe, "--out", wav, "--rate", fs, "--mode", "final"], env=lc.clean_env(), timeout=900)
    assert r.returncode == want_exit, r.stdout + r.stderr
    _, frames, rate = common.wav_layout(wav)
    assert rate == fs
    samples = common.read_frames(wav, 0, frames).reshape(-1, 2)
    lc.unlink(wav)
    report_path = out_dir / "x.report.json"
    text = report_path.read_text(encoding="utf-8")
    return samples, text, json.loads(text)


def agreement_problems(meter, samples, fs, text, report):
    """The report's true_peak member and assertion against the Python meter."""
    p = []
    keys = list(report)
    if "true_peak" not in keys:
        return [f"no true_peak member: {keys}"]
    if keys.index("true_peak") != keys.index("determinism_key") - 1:
        p.append(f"true_peak is not right before determinism_key: {keys}")
    member = report["true_peak"]
    if list(member) != tc.MEMBERS:
        return p + [f"true_peak members {list(member)}, want {tc.MEMBERS}"]
    linear = member["linear"]
    py = meter.true_peak(samples, fs)
    if not isinstance(linear, (int, float)) or isinstance(linear, bool):
        return p + [f"linear {linear!r} is not a number"]
    if float(linear).hex() != py.hex():
        p.append(f"report linear {float(linear).hex()} differs from the Python meter {py.hex()}")
    if py != tc.harness_true_peak(samples):
        p.append("the Python meter differs from the harness meter")
    a = report["assertions"][-1]
    if a["name"] != "true_peak":
        return p + [f"last assertion is {a['name']}, not true_peak"]
    want = meter.check_true_peak(samples, fs)
    for key in ("name", "row", "threshold", "unit", "result", "note"):
        if a[key] != want[key]:
            p.append(f"assertion {key} {a[key]!r}, Python {want[key]!r}")
    if want["measured"] is None:
        if a["measured"] is not None or member["dbtp"] is not None:
            p.append("silent: the report measured or dbtp is not null")
    elif a["measured"] is None or not abs(a["measured"] - want["measured"]) <= 1e-12:
        p.append(f"assertion measured {a['measured']!r}, Python {want['measured']!r}")
    elif a["measured"] != member["dbtp"]:
        p.append(f"assertion measured {a['measured']!r} is not the member dbtp {member['dbtp']!r}")
    return p


def with_gain_text(src, dst, text):
    """A copy of recipe src with the value text of loudness_gain_db replaced, other bytes kept."""
    raw = Path(src).read_bytes().decode("utf-8")
    key = '"loudness_gain_db": '
    at = raw.find(key)
    assert at >= 0, src
    start = at + len(key)
    end = start
    while raw[end] not in ",\r\n}":
        end += 1
    Path(dst).write_bytes((raw[:start] + text + raw[end:]).encode("utf-8"))
    return Path(dst)


# ------------------------------------------------------------ agreement


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_final_fixture_true_peak_agrees_and_passes(render, tmp_path, fs):
    meter = tc.meter()
    samples, text, report = final_render(render, tc.FIXTURES_VALID / FINAL_FIXTURE, fs, tmp_path)
    assert report["mode"] == "final"
    assert agreement_problems(meter, samples, fs, text, report) == []
    a = tc.true_peak_assertion(report)
    assert a["result"] == "pass", a
    assert a["measured"] <= tc.ceiling_dbtp()
    # The text: the member block right before determinism_key.
    assert '  "true_peak": {\n    "linear": ' in text
    assert text.index('"true_peak"') < text.index('"determinism_key"')
    # Must fail: the samples scaled in the harness until the true peak is
    # 0.5 dB above the ceiling fail check_true_peak.
    over = 10.0 ** ((tc.ceiling_dbtp() + 0.5 - a["measured"]) / 20.0)
    doctored = np.clip(np.rint(samples.astype(np.float64) * over), -(1 << 23), (1 << 23) - 1).astype(np.int64)
    bad = meter.check_true_peak(doctored, fs)
    assert bad["result"] == "fail", bad
    assert bad["measured"] > tc.ceiling_dbtp()


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_committed_stored_fixture_true_peak_agrees(render, tmp_path, fs):
    meter = tc.meter()
    samples, text, report = final_render(render, tc.FIXTURES_VALID / STORED_FIXTURE, fs, tmp_path)
    assert agreement_problems(meter, samples, fs, text, report) == []
    assert tc.true_peak_assertion(report)["result"] == "pass"


def test_stored_temp_copy_true_peak_agrees_at_both_rates(render, tmp_path):
    meter = tc.meter()
    recipe = tmp_path / STORE_COPY
    shutil.copyfile(tc.FIXTURES_VALID / STORE_COPY, recipe)
    r = common.run(render, [recipe, "--store-gain"], env=lc.clean_env(), timeout=900)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.startswith("stored: loudness_gain_db="), r.stdout
    for fs in SAMPLE_RATES:
        samples, text, report = final_render(render, recipe, fs, tmp_path / f"final-{fs}")
        assert agreement_problems(meter, samples, fs, text, report) == [], fs
        assert tc.true_peak_assertion(report)["result"] == "pass"


# ------------------------------------------------------------ must-fail


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_raised_gain_copy_fails_true_peak_exit_4(render, tmp_path, fs):
    meter = tc.meter()
    recipe = with_gain_text(tc.FIXTURES_VALID / FINAL_FIXTURE, tmp_path / FINAL_FIXTURE, RAISED_GAIN)
    samples, text, report = final_render(render, recipe, fs, tmp_path / "out", want_exit=4)
    assert agreement_problems(meter, samples, fs, text, report) == []
    a = tc.true_peak_assertion(report)
    assert a["result"] == "fail", a
    assert a["measured"] > tc.ceiling_dbtp()
    # Every other assertion passes or is not applicable: true_peak alone fails.
    assert [x["name"] for x in report["assertions"] if x["result"] == "fail"] == ["true_peak"]


@pytest.mark.parametrize("fs", SAMPLE_RATES[:1])
def test_measure_render_has_no_true_peak(render, tmp_path, fs):
    out = tmp_path / "m"
    out.mkdir()
    wav = out / "x.wav"
    r = common.run(render, [tc.FIXTURES_VALID / FINAL_FIXTURE, "--out", wav, "--rate", fs], env=lc.clean_env())
    assert r.returncode == 0, r.stdout + r.stderr
    lc.unlink(wav)
    text = (out / "x.report.json").read_text(encoding="utf-8")
    report = json.loads(text)
    assert "true_peak" not in report and "true_peak" not in text
    assert [a["name"] for a in report["assertions"]] == ["render speed"]
