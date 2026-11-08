"""AM depth tool, calibrated on Python-synthesized signals (Story 2.2).

Every signal here is made in the harness with NumPy at a known carrier, AM
rate, and depth; none comes from the engine or the reference. Rows come from
tests/tables/*.tsv through the assertion call `assertions.row`; no threshold
is written here as a literal.

Contract with tests/assertions/am_depth.py (imported as
`assertions.am_depth`; NumPy and the standard library only):

- `TRIM_S = 0.5`: the first and last 0.5 s of the signal are left out
  (session onset and end).
- `ROW = "reference-match"`: the row the verdict reads. No new row.
- `envelope(x, fs) -> ndarray`: the analytic envelope |analytic(x)| of one
  channel (x a 1-D float64 array), FFT method, same length as x.
- `cycle_extrema(x, fs, rate_hz) -> (peaks, troughs)`: two float64 arrays,
  one value per full gamma cycle. The envelope with the first and last
  TRIM_S seconds trimmed is cut into consecutive windows of fs / rate_hz
  samples from the trim start (window k spans [round(start + k * fs /
  rate_hz), round(start + (k + 1) * fs / rate_hz)), start = the first kept
  sample), only full windows inside the kept part; per window the largest
  and the smallest envelope value.
- `check(name, x, fs, rate_hz, depth_percent) -> dict`: reads row
  `reference-match` through `assertions.row` on every call. With d =
  depth_percent / 100, the deviation is the worst of max |peak - 1| and
  max |trough - (1 - d)| over every full cycle. Returns the Story 1.4 report
  assertion shape: {"name": name, "row": "reference-match", "threshold":
  <row value, dBFS>, "unit": "dBFS", "measured": 20 * log10(deviation),
  "result": "pass" when the deviation is strictly below 10^(row / 20) (the
  row as a linear full-scale amplitude), else "fail", "note": ""}. A signal
  with a NaN or infinite sample, or with no full cycle after the trim,
  fails with a note and measured None.

Constant depth means every cycle's peak is within the row of 1 and every
trough within it of 1 - d (signal spec, Gamma PAC layer, Uncoupled).

Calibration: a 250 Hz carrier amplitude-modulated at 40 and 60 Hz with 25
and 100 percent depth (the sine envelope, peak 1, trough 1 - d), 10 s, at
44.1 and 48 kHz, passes at its own depth. Must-fail: the depth stepped by
1 percent mid-render fails; a slow linear depth drift (25 to 26 percent over
the render, and a drift 100 times smaller) fails; the steady tone checked
against a depth 1 percent off fails; a non-finite sample and a signal too
short for one full cycle after the trim fail with a note.
"""

import dataclasses
import importlib
import math

import numpy as np
import pytest

import assertions
from assertions import row as table_row
from assertions.tables import load_tables

SECONDS = 10.0
CARRIER_HZ = 250.0
RATES_HZ = (40.0, 60.0)
DEPTHS_PERCENT = (25.0, 100.0)
STEP_PERCENT = 1.0   # the spec's must-fail step
SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]


def am():
    return importlib.import_module("assertions.am_depth")


def match_row():
    r = table_row("reference-match")
    assert r.unit == "dBFS", r
    return r


def linear_limit():
    return 10.0 ** (match_row().value / 20.0)


def times(fs, seconds=SECONDS):
    return np.arange(int(round(seconds * fs)), dtype=np.float64) / fs


def am_tone(fs, rate_hz, depth, seconds=SECONDS, carrier_hz=CARRIER_HZ):
    """250 Hz carrier amplitude-modulated at rate_hz by the sine envelope.

    depth is a fraction, a scalar or one value per sample. Both phases start
    at 0, like the engine layer (peak of the envelope at sample 0).
    """
    t = times(fs, seconds)
    e = 0.5 + 0.5 * np.cos(2.0 * np.pi * rate_hz * t)
    a = 1.0 - np.asarray(depth) * (1.0 - e)
    return a * np.sin(2.0 * np.pi * carrier_hz * t)


# ------------------------------------------------------------ contract


def test_module_constants():
    mod = am()
    assert mod.TRIM_S == 0.5
    assert mod.ROW == "reference-match"


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_envelope_of_an_am_tone_is_its_amplitude(fs):
    mod = am()
    x = am_tone(fs, 40.0, 0.25)
    env = mod.envelope(x, fs)
    assert isinstance(env, np.ndarray) and env.dtype == np.float64 and env.shape == x.shape
    t = times(fs)
    a = 1.0 - 0.25 * (0.5 - 0.5 * np.cos(2.0 * np.pi * 40.0 * t))
    k = int(round(mod.TRIM_S * fs))
    assert np.max(np.abs(env[k:-k] - a[k:-k])) < linear_limit()


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("rate_hz", RATES_HZ)
def test_cycle_extrema_cut_full_cycles_after_the_trim(fs, rate_hz):
    mod = am()
    x = am_tone(fs, rate_hz, 0.25)
    peaks, troughs = mod.cycle_extrema(x, fs, rate_hz)
    for arr in (peaks, troughs):
        assert isinstance(arr, np.ndarray) and arr.dtype == np.float64 and arr.ndim == 1
    k = int(round(mod.TRIM_S * fs))
    kept = x.size - 2 * k
    want = int(math.floor(kept / (fs / rate_hz)))
    # Only full windows inside the kept part; the rounding of window edges
    # can drop the last one.
    assert peaks.size == troughs.size
    assert want - 1 <= peaks.size <= want, (peaks.size, want)
    assert peaks.size >= int(rate_hz)  # at least 1 s of cycles in a 10 s signal
    assert np.max(np.abs(peaks - 1.0)) < linear_limit()
    assert np.max(np.abs(troughs - 0.75)) < linear_limit()


def test_cycle_extrema_follow_the_window_rule():
    # Each window spans [round(start + k * fs / rate), round(start + (k + 1) *
    # fs / rate)) of the tool's own envelope, and lies inside the kept part.
    mod = am()
    fs = SAMPLE_RATES[0]
    rate_hz = 40.0
    x = am_tone(fs, rate_hz, 0.25)
    env = mod.envelope(x, fs)
    k = int(round(mod.TRIM_S * fs))
    stop = x.size - k
    peaks, troughs = mod.cycle_extrema(x, fs, rate_hz)
    period = fs / rate_hz
    for i in range(peaks.size):
        a = int(round(k + i * period))
        b = int(round(k + (i + 1) * period))
        assert b <= stop
        assert peaks[i] == np.max(env[a:b]), i
        assert troughs[i] == np.min(env[a:b]), i


# ------------------------------------------------------------ calibration


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("rate_hz", RATES_HZ)
@pytest.mark.parametrize("depth_percent", DEPTHS_PERCENT)
def test_steady_tone_passes_at_its_depth(fs, rate_hz, depth_percent):
    mod = am()
    x = am_tone(fs, rate_hz, depth_percent / 100.0)
    result = mod.check(f"steady {rate_hz} Hz {depth_percent} percent", x, fs, rate_hz, depth_percent)
    assert set(result) == {"name", "row", "threshold", "unit", "measured", "result", "note"}
    assert result["row"] == "reference-match"
    assert result["threshold"] == match_row().value
    assert result["unit"] == "dBFS"
    assert result["result"] == "pass" and result["note"] == "", result
    assert result["measured"] < match_row().value


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("rate_hz", RATES_HZ)
@pytest.mark.parametrize("depth_percent", DEPTHS_PERCENT)
def test_depth_stepped_1_percent_mid_render_fails(fs, rate_hz, depth_percent):
    mod = am()
    d = np.full(times(fs).size, depth_percent / 100.0)
    # Step toward the inside of the range: 25 to 24 percent, 100 to 99.
    d[d.size // 2:] -= STEP_PERCENT / 100.0
    result = mod.check("stepped", am_tone(fs, rate_hz, d), fs, rate_hz, depth_percent)
    assert result["result"] == "fail", result
    # The trough moves by the step, 0.01 of full scale (-40 dBFS).
    assert abs(result["measured"] - 20.0 * math.log10(STEP_PERCENT / 100.0)) < 1.0, result


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("rate_hz", RATES_HZ)
@pytest.mark.parametrize("drift_percent", (1.0, 0.01))
def test_slow_depth_drift_fails(fs, rate_hz, drift_percent):
    mod = am()
    n = times(fs).size
    d = (25.0 + drift_percent * np.arange(n, dtype=np.float64) / n) / 100.0
    result = mod.check("drift", am_tone(fs, rate_hz, d), fs, rate_hz, 25.0)
    assert result["result"] == "fail", result
    assert result["measured"] >= match_row().value


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_steady_tone_against_the_wrong_depth_fails(fs):
    mod = am()
    x = am_tone(fs, 40.0, 0.25)
    for wrong in (24.0, 26.0, 100.0, 0.0):
        result = mod.check("wrong depth", x, fs, 40.0, wrong)
        assert result["result"] == "fail", (wrong, result)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_unmodulated_carrier_fails_a_nonzero_depth(fs):
    mod = am()
    x = am_tone(fs, 40.0, 0.0)
    assert mod.check("depth 0", x, fs, 40.0, 0.0)["result"] == "pass"
    assert mod.check("unmodulated", x, fs, 40.0, 25.0)["result"] == "fail"


# ------------------------------------------------------------ verdicts


def test_check_reads_the_row_on_every_call(monkeypatch):
    # The row is looked up through assertions.row at call time: a doctored
    # table (row reference-match raised to 0 dBFS) changes the verdict of the
    # stepped tone and the reported threshold.
    mod = am()
    fs = SAMPLE_RATES[0]
    d = np.full(times(fs).size, 0.25)
    d[d.size // 2:] -= 0.01
    x = am_tone(fs, 40.0, d)
    assert mod.check("stepped", x, fs, 40.0, 25.0)["result"] == "fail"
    real = assertions._table()
    doctored = dict(real)
    doctored["reference-match"] = dataclasses.replace(real["reference-match"], values=(0.0,),
                                                      value_text="0")
    monkeypatch.setattr(assertions, "_rows", doctored)
    result = mod.check("stepped", x, fs, 40.0, 25.0)
    assert result["threshold"] == 0.0, result
    assert result["result"] == "pass", result


def test_verdict_on_each_side_of_the_row():
    # Troughs 4 times and a quarter of the row (as linear amplitude) off.
    mod = am()
    fs = SAMPLE_RATES[1]
    limit = linear_limit()
    x = am_tone(fs, 40.0, 0.25 - 4.0 * limit)
    result = mod.check("four times the row off", x, fs, 40.0, 25.0)
    assert result["result"] == "fail", result
    y = am_tone(fs, 40.0, 0.25 - 0.25 * limit)
    result = mod.check("a quarter of the row off", y, fs, 40.0, 25.0)
    assert result["result"] == "pass", result


def test_not_finite_fails_with_a_note():
    mod = am()
    fs = SAMPLE_RATES[0]
    for bad in (math.nan, math.inf, -math.inf):
        x = am_tone(fs, 40.0, 0.25, seconds=2.0)
        x[fs] = bad
        result = mod.check("bad", x, fs, 40.0, 25.0)
        assert result["result"] == "fail", bad
        assert result["note"] != "", bad
        assert result["measured"] is None, bad


def test_signal_with_no_full_cycle_fails_with_a_note():
    mod = am()
    for fs in SAMPLE_RATES:
        # 1.01 s: after 0.5 s at each end, 10 ms remain, under one 25 ms cycle at 40 Hz.
        x = am_tone(fs, 40.0, 0.25, seconds=1.01)
        result = mod.check("short", x, fs, 40.0, 25.0)
        assert result["result"] == "fail", result
        assert result["note"] != "", result
        assert result["measured"] is None, result
        x = am_tone(fs, 40.0, 0.25, seconds=0.5)
        result = mod.check("shorter than the trim", x, fs, 40.0, 25.0)
        assert result["result"] == "fail" and result["note"] != "" and result["measured"] is None
