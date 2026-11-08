"""Click tool, calibrated on Python-synthesized signals (Story 2.1).

Every signal here is made in the harness with NumPy; none comes from the
engine or the reference. Rows come from tests/tables/*.tsv through the
assertion call `assertions.row`; no threshold is written here as a literal.

Contract with tests/assertions/clicks.py (imported as `assertions.clicks`;
NumPy and the standard library only):

- `EXCLUDE_S = 0.05`: the first and last 50 ms of a session are left out of
  the peak. Session onset and end belong to the gain ramps (Story 4.4).
  The excluded count at each end is round(EXCLUDE_S * fs) samples.
- `highpass(x, fs) -> ndarray`: zero-phase high-pass of one channel (a 1-D
  float64 array), same length. A 4th-order Butterworth at the corner of row
  `click-highpass` (read in kHz through `assertions.row`), applied forward and
  backward, done as one FFT-domain magnitude on a zero-padded signal:
  |H(f)|^2 = 1 / (1 + (f_c / f)^8), and 0 at DC.
- `peak_dbfs(x, fs, exclude_s=EXCLUDE_S) -> float`: 20 * log10 of the
  largest |highpass(x, fs)| outside the first and last exclude_s seconds;
  -inf when that part is all zero.
- `check(name, x, fs) -> dict`: reads rows `click-level` and
  `click-highpass` through `assertions.row` on every call and returns the
  Story 1.4 report assertion shape: {"name": name, "row": "click-level",
  "threshold": <row value>, "unit": "dBFS", "measured": peak_dbfs(x, fs),
  "result": "pass" when measured is strictly below the threshold, else
  "fail", "note": ""}. A NaN or infinite sample fails with note "not
  finite" and measured None.

Calibration: the filter's gain at tones on both sides of the corner equals
the Butterworth magnitude within 0.1 dB; its impulse response is symmetric
(zero phase); a smooth AM tone (450 Hz carrier amplitude-modulated at 6 Hz
by a sine envelope, 100 percent depth) passes; the same tone with a known
0.01 step fails; a step inside the excluded 50 ms at either end passes and
one just past it fails; a hard session onset passes only because of the
exclusion. Must-fail: a 450 Hz carrier amplitude-modulated at 1 and 6 Hz by
an unsmoothed sawtooth (instant drop) fails, and the same sawtooth with a
10 ms raised-cosine drop passes.
"""

import importlib
import math

import numpy as np
import pytest

from assertions import row as table_row
from assertions.tables import load_tables

SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
GAIN_TOLERANCE_DB = 0.1
STEP = 0.01
EDGE_S = 0.010  # harness raised-cosine drop; the engine's edge is row theta-edge


def clicks():
    return importlib.import_module("assertions.clicks")


def level_row():
    r = table_row("click-level")
    assert r.unit == "dBFS", r
    return r


def corner_hz():
    r = table_row("click-highpass")
    assert r.unit == "kHz", r
    return r.value * 1000.0


def smooth_am(fs, seconds=10.0, rate_hz=6.0):
    t = np.arange(int(seconds * fs), dtype=np.float64) / fs
    envelope = 0.5 + 0.5 * np.cos(2.0 * np.pi * rate_hz * t)
    return envelope * np.sin(2.0 * np.pi * 450.0 * t)


def sawtooth_am(fs, rate_hz, smoothed, seconds=10.0):
    t = np.arange(int(seconds * fs), dtype=np.float64) / fs
    phi = np.mod(rate_hz * t, 1.0)
    if smoothed:
        w = EDGE_S * rate_hz
        envelope = np.where(phi < w, 0.5 + 0.5 * np.cos(np.pi * np.minimum(phi, w) / w),
                            (phi - w) / (1.0 - w))
    else:
        envelope = phi  # linear rise, instant drop at every cycle start
    return envelope * np.sin(2.0 * np.pi * 450.0 * t)


# ------------------------------------------------------------ filter


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_highpass_gain_is_the_butterworth_magnitude(fs):
    mod = clicks()
    fc = corner_hz()
    n = fs
    t = np.arange(n, dtype=np.float64) / fs
    mid = slice(fs // 10, n - fs // 10)
    for ratio in (0.5, 0.75, 1.0, 1.5, 2.0):
        f = fc * ratio
        if f >= fs / 2:
            continue
        x = 0.5 * np.cos(2.0 * np.pi * f * t)
        y = mod.highpass(x, fs)
        assert y.shape == x.shape and y.dtype == np.float64
        # RMS of the steady part, so sample-peak position does not matter.
        gain = math.sqrt(2.0) * float(np.sqrt(np.mean(y[mid] ** 2))) / 0.5
        want_db = 20.0 * math.log10(1.0 / (1.0 + (fc / f) ** 8))
        assert abs(20.0 * math.log10(gain) - want_db) <= GAIN_TOLERANCE_DB, (fs, f, gain)


def test_highpass_is_zero_phase():
    mod = clicks()
    for fs in SAMPLE_RATES:
        x = np.zeros(4001)
        x[2000] = 1.0
        y = mod.highpass(x, fs)
        k = np.arange(1, 2000)
        assert np.max(np.abs(y[2000 + k] - y[2000 - k])) < 1e-12, fs


def test_highpass_removes_dc_and_the_theta_band():
    mod = clicks()
    for fs in SAMPLE_RATES:
        y = mod.highpass(np.full(fs, 0.5), fs)
        assert np.max(np.abs(y[fs // 10:-fs // 10])) < 1e-9
        assert mod.peak_dbfs(smooth_am(fs, seconds=1.0), fs) < level_row().value - 60.0


# ------------------------------------------------------------ verdicts


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_smooth_am_tone_passes(fs):
    result = clicks().check("smooth", smooth_am(fs), fs)
    assert set(result) == {"name", "row", "threshold", "unit", "measured", "result", "note"}
    assert result["row"] == "click-level" and result["unit"] == "dBFS"
    assert result["threshold"] == level_row().value
    assert result["result"] == "pass" and result["note"] == "", result
    assert result["measured"] < level_row().value


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_known_step_fails(fs):
    x = smooth_am(fs)
    x[5 * fs:] += STEP
    result = clicks().check("step", x, fs)
    assert result["result"] == "fail", result
    assert result["measured"] >= level_row().value


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_exclusion_covers_50_ms_at_each_end(fs):
    mod = clicks()
    assert mod.EXCLUDE_S == 0.05
    threshold = level_row().value
    for start_s, inside in ((0.02, True), (0.06, False), (9.97, True), (9.94, False)):
        x = smooth_am(fs)
        x[int(start_s * fs):] += STEP
        result = mod.check("step", x, fs)
        assert (result["result"] == "pass") == inside, (fs, start_s, result)
        assert (result["measured"] < threshold) == inside, (fs, start_s, result)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_hard_onset_passes_only_through_the_exclusion(fs):
    mod = clicks()
    t = np.arange(10 * fs, dtype=np.float64) / fs
    x = np.cos(2.0 * np.pi * 450.0 * t)  # starts and ends at a jump from zero padding
    assert mod.check("onset", x, fs)["result"] == "pass"
    assert mod.peak_dbfs(x, fs, exclude_s=0.0) >= level_row().value


def test_not_finite_fails():
    mod = clicks()
    fs = SAMPLE_RATES[0]
    for bad in (math.nan, math.inf, -math.inf):
        x = smooth_am(fs, seconds=1.0)
        x[fs // 2] = bad
        result = mod.check("bad", x, fs)
        assert result["result"] == "fail" and result["note"] == "not finite", bad
        assert result["measured"] is None


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("rate_hz", (1.0, 6.0))
def test_unsmoothed_sawtooth_fails_and_smoothed_passes(fs, rate_hz):
    mod = clicks()
    hard = mod.check("unsmoothed sawtooth", sawtooth_am(fs, rate_hz, smoothed=False), fs)
    assert hard["result"] == "fail", hard
    soft = mod.check("smoothed sawtooth", sawtooth_am(fs, rate_hz, smoothed=True), fs)
    assert soft["result"] == "pass", soft


def test_signal_shorter_than_the_exclusions_raises():
    mod = clicks()
    for fs in SAMPLE_RATES:
        x = smooth_am(fs, seconds=0.09)  # under 2 x 50 ms: nothing left to inspect
        with pytest.raises(ValueError, match="too short"):
            mod.peak_dbfs(x, fs)
        with pytest.raises(ValueError, match="too short"):
            mod.check("short", x, fs)
