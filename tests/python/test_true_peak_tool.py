"""Python true-peak meter, calibrated on harness-synthesized signals (Story 4.3;
docs/signal-spec.md, True peak).

Every calibration signal is made here with NumPy by the spec's synthesis
rule (True peak, Calibration, Signal) in binary64; its 24-bit stereo bytes
must hash to the vector's SHA-256, which proves the harness built the same
integers. No EBU file is read. Rows come from tests/tables/*.tsv through
the assertion call `assertions.row`; the vector constants are cross-checked
against them, never used in their place.

Contract with tests/assertions/true_peak.py (imported as
`assertions.true_peak`; NumPy and the standard library only):

- `true_peak(x24, fs) -> float`: TP, the linear true peak of BS.1770-5
  Annex 2 (True peak, Meter): per channel the full convolution, from zero
  state with the 11 trailing outputs, of the int64 samples with each
  phase's integers n_p, max |.| over phases and channels, then one division
  by 2^36. x24 holds integers of shape (frames, 2) or (frames,); a
  non-integer dtype, any other shape, or a value outside [-2^23, 2^23 - 1]
  raises ValueError. No frames gives 0.0.
- `check_true_peak(x24, fs) -> dict`: {"name": "true_peak", "row":
  "true-peak", "threshold": <row value>, "unit": <row unit>, "measured":
  20 log10(TP), "result": "pass" when measured <= threshold else "fail",
  "note": ""}; TP = 0: measured None, result "pass", note "silent". The
  row is read through `assertions.row("true-peak")`.

Calibration: Tech 3341 v4.0 Table 1 cases 15 to 19 and the closed-form fs/4
sines at 44.1 and 48 kHz, TP equal to the vector bit for bit, within rows
true-peak-meter-over and true-peak-meter-under of the expected reading.
Must-fails (doctored here): the hidden overshoot fails the assertion while
the harness sample-peak check passes; a meter without oversampling (phase 0
only, or the sample peak) reads the hidden overshoot at or below the
ceiling; a meter that drops the 11 trailing outputs, or the first 11,
misreads a signal cut short; a reading moved past either tolerance fails
calibration.
"""

import ast
import math
import sys
from decimal import Decimal

import numpy as np
import pytest

import loudness_common as lc
import true_peak_common as tc
from assertions import row as table_row

SAMPLE_RATES = tc.sample_rates()
SIGNALS = [pytest.param(r["signal"], r["fs"], id=f"{r['signal']}-{r['fs']}") for r in tc.signals()]
TWO_23 = 1 << 23


def tp_module():
    return tc.meter()


# ------------------------------------------------------------ the module


def test_module_uses_numpy_and_the_standard_library_only():
    m = tp_module()
    tree = ast.parse(open(m.__file__, encoding="utf-8").read())
    allowed = set(sys.stdlib_module_names) | {"numpy", "assertions"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] in allowed, a.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            assert node.module.split(".")[0] in allowed, node.module


# ------------------------------------------------------------ rows and constants


def test_rows_and_constants():
    k = tc.constants()
    ceiling = table_row(tc.CEILING_ROW)
    assert tc.ceiling_dbtp() == float(k["ceiling_dbtp"])
    assert tc.over_db() == float(k["over_db"]) and tc.over_db() > 0.0
    assert tc.under_db() == float(k["under_db"]) and tc.under_db() > 0.0
    assert k["row"] == tc.CEILING_ROW
    assert k["over_row"] == tc.OVER_ROW and k["under_row"] == tc.UNDER_ROW
    assert k["limit"] == f"<= {ceiling.value_text} {ceiling.unit} (row {tc.CEILING_ROW})"
    assert k["rule"] == "true_peak"
    assert k["parameter"] == "/loudness_gain_db"
    assert int(k["oversampling"]) == 4 and int(k["taps"]) == 12
    assert int(k["trailing_zeros"]) == int(k["taps"]) - 1
    assert int(k["sample_bits"]) == 23 and int(k["coefficient_bits"]) == 13
    assert k["tech3341_cases"] == [15, 16, 17, 18, 19]
    assert k["out_of_scope_cases"] == [20, 21, 22, 23]
    assert {r["fs"] for r in tc.signals()} == set(SAMPLE_RATES)
    cases = sorted({int(r["source"].split()[-1]) for r in tc.signals() if r["source"].startswith("Tech 3341")})
    assert cases == k["tech3341_cases"]


def test_final_fixture_gain_is_a_stored_gain_vector():
    k = tc.constants()
    assert k["final_fixture"] == "stub-chain-1s-beat-6.json"
    found = [r for r in lc.vectors()["loudness_gain_values"] if r["text"] == k["final_fixture_gain"]]
    assert len(found) == 1, k["final_fixture_gain"]
    assert int(found[0]["k"]) == -1000 and found[0]["two_decimals"] == "yes", found[0]


# ------------------------------------------------------------ filter


def test_filter_vectors_are_the_printed_coefficients():
    k = tc.constants()
    rows = tc.vectors()["true_peak_filter"]
    assert len(rows) == int(k["oversampling"]) * int(k["taps"])
    scale = 1 << int(k["coefficient_bits"])
    for r in rows:
        # Each printed coefficient is exactly the integer times 2^-13.
        assert Decimal(r["printed"]) == Decimal(int(r["integer"])) / Decimal(scale), r
        assert float.fromhex(r["hex"]) == int(r["integer"]) / float(scale), r
        assert float(r["printed"]) == float.fromhex(r["hex"]), r


def test_filter_phases_are_reversals_and_sum_as_stated():
    n = tc.filter_integers()
    assert n.shape == (4, 12)
    assert np.array_equal(n[2], n[1][::-1])
    assert np.array_equal(n[3], n[0][::-1])
    assert [int(s) for s in n.sum(axis=1)] == tc.constants()["phase_sums"]
    # Exactness premise (True peak, Meter, Exact): sum |n_p[k]| * 2^23 < 2^38.
    assert int(np.abs(n).sum(axis=1).max()) * TWO_23 < 1 << 38


# ------------------------------------------------------------ calibration


@pytest.mark.parametrize("name,fs", SIGNALS)
def test_signal_vector_and_meter_reading(name, fs):
    v = tc.signal(name, fs)
    x = tc.synthesize(v)
    assert x.shape == (int(v["frames"]), 2)
    assert tc.samples_sha256(x) == v["samples_sha256"], (name, fs)
    assert int(np.max(np.abs(x))) == int(v["sample_peak"])
    # The harness meter gives the vector's exact peak.
    assert tc.harness_peak_integer(x) == int(v["peak_integer"])
    want = float.fromhex(v["true_peak_hex"])
    assert tc.harness_true_peak(x) == want
    # The meter under test: bit for bit, as int64 and as int32 samples.
    got = tp_module().true_peak(x, fs)
    assert isinstance(got, float)
    assert got.hex() == want.hex(), (name, fs, got.hex(), want.hex())
    assert tp_module().true_peak(x.astype(np.int32), fs).hex() == want.hex()
    # Calibration against rows true-peak-meter-over and -under.
    if v["expected_dbtp"] != "none":
        reading = tc.dbtp(got)
        problems = tc.calibration_problems(reading, float(v["expected_dbtp"]), tc.over_db(), tc.under_db())
        assert problems == [], (name, fs, problems)
        assert v["calibration"] == "pass"
        assert abs((reading - float(v["expected_dbtp"])) - float(v["reading_minus_expected_db"])) <= 1e-9
    # The assertion and the harness sample-peak check give the vector's results.
    a = tp_module().check_true_peak(x, fs)
    assert a["result"] == v["assertion"], (name, fs, a)
    assert tc.sample_peak_check(x) == v["sample_peak_check"], (name, fs)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_calibration_moved_past_either_tolerance_fails(fs):
    for v in tc.signals(fs):
        if v["expected_dbtp"] == "none":
            continue
        want = float(v["expected_dbtp"])
        reading = tc.dbtp(float.fromhex(v["true_peak_hex"]))
        assert tc.calibration_problems(want + tc.over_db() + 1e-6, want, tc.over_db(), tc.under_db())
        assert tc.calibration_problems(want - tc.under_db() - 1e-6, want, tc.over_db(), tc.under_db())
        assert tc.calibration_problems(want + tc.over_db() - 1e-6, want, tc.over_db(), tc.under_db()) == []
        assert tc.calibration_problems(want - tc.under_db() + 1e-6, want, tc.over_db(), tc.under_db()) == []
        assert tc.calibration_problems(reading, want, tc.over_db(), tc.under_db()) == [], v["signal"]


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_meter_is_the_same_on_one_channel_and_on_swapped_channels(fs):
    m = tp_module()
    v = tc.signal("case 17", fs)
    x = tc.synthesize(v)
    want = float.fromhex(v["true_peak_hex"])
    assert m.true_peak(x[:, 0], fs).hex() == want.hex()
    # A channel only louder on the right still reads the max of both channels.
    quiet = np.column_stack((x[:, 0] // 2, x[:, 1]))
    assert m.true_peak(quiet, fs).hex() == want.hex()
    assert m.true_peak(quiet[:, ::-1].copy(), fs).hex() == want.hex()


# ------------------------------------------------------------ assertion


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_assertion_shape_and_row(fs):
    r = table_row(tc.CEILING_ROW)
    for name, want in (("under the ceiling", "pass"), ("hidden overshoot", "fail"), ("low level", "pass")):
        v = tc.signal(name, fs)
        x = tc.synthesize(v)
        a = tp_module().check_true_peak(x, fs)
        assert list(a) == ["name", "row", "threshold", "unit", "measured", "result", "note"], a
        assert a["name"] == "true_peak" and a["row"] == tc.CEILING_ROW
        assert a["threshold"] == r.value and a["unit"] == r.unit == "dBTP"
        assert isinstance(a["measured"], float)
        assert a["measured"] == tc.dbtp(tp_module().true_peak(x, fs))
        assert a["result"] == want and a["note"] == "", (name, a)
        assert (a["measured"] <= r.value) == (want == "pass")


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_hidden_overshoot_fails_while_a_sample_peak_check_passes(fs):
    v = tc.signal("hidden overshoot", fs)
    assert v["role"] == "must-fail" and v["assertion"] == "fail", v
    x = tc.synthesize(v)
    assert tc.sample_peak_dbfs(x) <= tc.ceiling_dbtp() - 2.0
    assert tc.sample_peak_check(x) == "pass"
    a = tp_module().check_true_peak(x, fs)
    assert a["result"] == "fail", a
    assert a["measured"] > tc.ceiling_dbtp()


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_silent_signal_passes_with_measured_null(fs):
    v = tc.signal("silent", fs)
    x = tc.synthesize(v)
    assert not x.any()
    assert tp_module().true_peak(x, fs) == 0.0
    a = tp_module().check_true_peak(x, fs)
    assert a["measured"] is None and a["result"] == "pass" and a["note"] == "silent", a
    empty = np.zeros((0, 2), dtype=np.int64)
    assert tp_module().true_peak(empty, fs) == 0.0
    assert tp_module().check_true_peak(empty, fs)["note"] == "silent"


# ------------------------------------------------------------ must-fail meters


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_meters_without_oversampling_read_the_hidden_overshoot_under_the_ceiling(fs):
    v = tc.signal("hidden overshoot", fs)
    x = tc.synthesize(v)
    ceiling = tc.ceiling_dbtp()
    phase0 = tc.harness_true_peak(x, phases=[0])
    assert tc.dbtp(phase0) <= ceiling, phase0
    assert tc.sample_peak_dbfs(x) <= ceiling
    # The full meter reads it above the ceiling.
    assert tc.dbtp(tc.harness_true_peak(x)) > ceiling
    assert tc.dbtp(tp_module().true_peak(x, fs)) > ceiling


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_meters_dropping_the_edge_outputs_misread_a_signal_cut_short(fs):
    m = tp_module()
    trailing = int(tc.constants()["trailing_zeros"])
    for name in ("case 15", "hidden overshoot"):
        v = tc.signal(name, fs)
        # With both fades the edge outputs hold no peak: the vector's reading.
        faded = tc.synthesize(v)
        assert tc.harness_true_peak(faded, drop_tail=trailing) == float.fromhex(v["true_peak_hex"])
        # Cut short at the end: dropping the 11 trailing outputs misreads it.
        cut = tc.synthesize(v, fade_out=False)
        full = tc.harness_true_peak(cut)
        assert tc.harness_true_peak(cut, drop_tail=trailing) != full, name
        assert m.true_peak(cut, fs).hex() == full.hex(), name
        # An abrupt start: dropping the first 11 outputs misreads it.
        abrupt = tc.synthesize(v, fade_in=False)
        full = tc.harness_true_peak(abrupt)
        assert tc.harness_true_peak(abrupt, drop_head=trailing) != full, name
        assert m.true_peak(abrupt, fs).hex() == full.hex(), name


def test_single_impulses_at_either_end_read_the_largest_tap():
    m = tp_module()
    n = tc.filter_integers()
    fs = SAMPLE_RATES[-1]
    top = TWO_23 - 1
    for at in (0, 99):
        x = np.zeros((100, 2), dtype=np.int64)
        x[at, 1] = top
        assert m.true_peak(x, fs) == int(np.abs(n).max()) * top / float(1 << 36), at
        x[at, 1] = -TWO_23
        assert m.true_peak(x, fs) == int(np.abs(n).max()) * TWO_23 / float(1 << 36), at
    # One frame alone: every output is a tap times the sample.
    one = np.array([[top, -TWO_23]], dtype=np.int64)
    assert m.true_peak(one, fs) == int(np.abs(n).max()) * TWO_23 / float(1 << 36)


# ------------------------------------------------------------ input checks


def test_bad_input_raises():
    m = tp_module()
    fs = SAMPLE_RATES[-1]
    ok = np.zeros((10, 2), dtype=np.int64)
    ok[0] = (TWO_23 - 1, -TWO_23)
    m.true_peak(ok, fs)  # the range ends are accepted
    for bad in (ok.astype(np.float64), ok.astype(np.float32), np.zeros((10, 3), dtype=np.int64),
                np.zeros((2, 5, 2), dtype=np.int64)):
        with pytest.raises(ValueError):
            m.true_peak(bad, fs)
    for value in (TWO_23, -TWO_23 - 1, 1 << 40):
        x = np.zeros((10, 2), dtype=np.int64)
        x[3, 0] = value
        with pytest.raises(ValueError):
            m.true_peak(x, fs)
        with pytest.raises(ValueError):
            m.check_true_peak(x, fs)


# ------------------------------------------------------------ store step vectors


def test_store_step_vectors_follow_the_rule():
    k = tc.constants()
    ceiling = tc.ceiling_dbtp()
    for v in tc.vectors()["true_peak_steps"]:
        tp = float.fromhex(v["true_peak_hex"])
        reading = tc.dbtp(tp)
        if v["dbtp_text"] == "-inf":
            assert reading == -math.inf
        else:
            assert abs(float(v["dbtp_text"]) - reading) <= 1e-12, v
        assert (v["result"] == "stored") == (reading <= ceiling), v
        if v["result"] == "stored":
            assert v["line"] == "none"
        else:
            assert v["line"] == (f"rejected: parameter={k['parameter']} value={v['gain_text']} rule={k['rule']} "
                                 f"limit={k['limit']} target_lufs={v['target_lufs']} "
                                 f"true_peak_dbtp={v['dbtp_text']}"), v
