"""Frequency accuracy tool, calibrated on Python-synthesized signals (Story 2.1, FR-1).

Every signal here is made in the harness with NumPy at a known carrier and
rate; none comes from the engine or the reference. Rows come from
tests/tables/*.tsv through the assertion call `assertions.row`; no threshold
is written here as a literal.

Contract with tests/assertions/frequency.py (imported as
`assertions.frequency`; NumPy and the standard library only):

- `TRIM_S = 0.5`: the first and last 0.5 s of the signal are left out of
  both measurements (session onset and end).
- `carrier_hz(x, fs) -> float`: x is one channel, a 1-D float64 array; fs
  44100 or 48000. The analytic signal of x (FFT method), trimmed; its phase
  unwrapped; the carrier is the slope of a weighted least-squares line
  through (t, phase) with weights |analytic|^2, divided by 2 pi.
- `rate_hz(x, fs) -> float`: the AM rate. The analytic envelope |analytic|,
  trimmed and mean-removed, times a 4-term Blackman-Harris window
  (a0..a3 = 0.35875, 0.48829, 0.14128, 0.01168); the strongest DFT peak
  above 0 Hz, refined by golden-section search on the windowed DTFT
  magnitude to well under the calibration row.
- `check(name, measured_hz, expected_hz) -> dict`: reads row
  `frequency-accuracy` through `assertions.row` on every call and returns the
  Story 1.4 report assertion shape: {"name": name, "row":
  "frequency-accuracy", "threshold": <row value>, "unit": "Hz", "measured":
  |measured_hz - expected_hz|, "result": "pass" when measured is strictly
  below the threshold, else "fail", "note": ""}. A NaN or infinite measured
  value fails with note "not finite" and measured None.

Calibration (row `frequency-accuracy-calibration`, in Hz): pure tones at
known carriers, and AM tones of every theta shape (sine, smoothed on-off,
sawtooth, reverse saw, each made here) at known carriers and rates, read
within the calibration row at both sample rates. Must-fail: a tone moved
0.02 Hz fails row `frequency-accuracy`; an AM rate moved 0.02 Hz fails it;
a coarse FFT bin peak misses an off-bin tone by more than the calibration
row (so the row catches a tool without refinement); a signal whose first
and last 0.4 s are another frequency still reads the main carrier (the trim
works).
"""

import importlib
import math

import numpy as np
import pytest

from assertions import row as table_row
from assertions.tables import load_tables

SECONDS = 10.0
CARRIERS_HZ = (100.0, 450.0, 451.237, 999.9)
AM_CARRIER_HZ = 450.0
AM_RATES_HZ = (1.0, 2.75, 6.0)
AM_DEPTH = 0.75
EDGE_S = 0.010   # harness shapes only; the engine's edge is row theta-edge
ON_SHARE = 0.5   # harness shapes only; the engine's share is row theta-on-share
MOVE_HZ = 0.02   # the spec's must-fail offset
SHAPES = ("sine", "smoothed_on_off", "sawtooth", "reverse_saw")

SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]


def freq():
    return importlib.import_module("assertions.frequency")


def accuracy_hz():
    r = table_row("frequency-accuracy")
    assert r.unit == "Hz", r
    return r.value


def calibration_hz():
    r = table_row("frequency-accuracy-calibration")
    assert r.unit == "Hz", r
    assert r.value < accuracy_hz(), "the calibration row must be tighter than the accuracy row"
    return r.value


# ------------------------------------------------------- harness signals


def harness_envelope(shape, phi, rate_hz):
    """Envelope in [0, 1] with its peak at phi = 0 (made here, not the spec code)."""
    phi = np.mod(phi, 1.0)
    w = EDGE_S * rate_hz
    if shape == "sine":
        return 0.5 + 0.5 * np.cos(2.0 * np.pi * phi)
    if shape == "smoothed_on_off":
        m = np.minimum(phi, 1.0 - phi)
        h = ON_SHARE / 2.0
        out = np.where(m <= h - w, 1.0, 0.0)
        edge = (m > h - w) & (m < h)
        out[edge] = 0.5 + 0.5 * np.cos(np.pi * (m[edge] - (h - w)) / w)
        return out
    q = phi if shape == "sawtooth" else np.mod(1.0 - phi, 1.0)
    drop = 0.5 + 0.5 * np.cos(np.pi * np.minimum(q, w) / w)
    return np.where(q < w, drop, (q - w) / (1.0 - w))


def tone(fs, f_hz, phase=1.1, seconds=SECONDS):
    t = np.arange(int(seconds * fs), dtype=np.float64) / fs
    return 0.5 * np.sin(2.0 * np.pi * f_hz * t + phase)


def am_tone(fs, carrier_hz, rate_hz, shape, depth=AM_DEPTH, seconds=SECONDS):
    t = np.arange(int(seconds * fs), dtype=np.float64) / fs
    a = 1.0 - depth * (1.0 - harness_envelope(shape, rate_hz * t, rate_hz))
    return a * np.sin(2.0 * np.pi * carrier_hz * t + 0.3)


# ------------------------------------------------------------ calibration


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("f_hz", CARRIERS_HZ)
def test_pure_tone_carrier_reads_within_calibration(fs, f_hz):
    got = freq().carrier_hz(tone(fs, f_hz), fs)
    assert abs(got - f_hz) < calibration_hz(), (fs, f_hz, got)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("rate_hz", AM_RATES_HZ)
def test_am_tone_carrier_and_rate_read_within_calibration(fs, shape, rate_hz):
    x = am_tone(fs, AM_CARRIER_HZ, rate_hz, shape)
    mod = freq()
    carrier = mod.carrier_hz(x, fs)
    rate = mod.rate_hz(x, fs)
    assert abs(carrier - AM_CARRIER_HZ) < calibration_hz(), (fs, shape, rate_hz, carrier)
    assert abs(rate - rate_hz) < calibration_hz(), (fs, shape, rate_hz, rate)


def test_trim_leaves_out_the_first_and_last_half_second():
    mod = freq()
    assert mod.TRIM_S == 0.5
    for fs in SAMPLE_RATES:
        x = tone(fs, AM_CARRIER_HZ)
        k = int(0.4 * fs)
        t = np.arange(x.size, dtype=np.float64) / fs
        x[:k] = 0.5 * np.sin(2.0 * np.pi * 300.0 * t[:k])
        x[-k:] = 0.5 * np.sin(2.0 * np.pi * 300.0 * t[-k:])
        got = mod.carrier_hz(x, fs)
        assert abs(got - AM_CARRIER_HZ) < calibration_hz(), (fs, got)


def test_coarse_fft_peak_misses_the_calibration_row():
    # Must-fail for the calibration: a bin peak without refinement (0.1 Hz
    # bins over 10 s) misses an off-bin tone by more than the row.
    for fs in SAMPLE_RATES:
        f = 450.05
        x = tone(fs, f)
        spectrum = np.abs(np.fft.rfft(x))
        coarse = float(np.argmax(spectrum)) * fs / x.size
        assert abs(coarse - f) >= calibration_hz(), (fs, coarse)


# ------------------------------------------------------------ verdicts


def test_check_report_shape_and_pass():
    mod = freq()
    result = mod.check("carrier", 450.0 + accuracy_hz() / 2.0, 450.0)
    assert set(result) == {"name", "row", "threshold", "unit", "measured", "result", "note"}
    assert result["name"] == "carrier"
    assert result["row"] == "frequency-accuracy"
    assert result["threshold"] == accuracy_hz()
    assert result["unit"] == "Hz"
    assert result["result"] == "pass" and result["note"] == ""
    assert abs(result["measured"] - accuracy_hz() / 2.0) < 1e-12


def test_check_is_strict_at_the_threshold():
    mod = freq()
    exact = mod.check("exact", 450.0, 450.0)
    assert exact["result"] == "pass" and exact["measured"] == 0.0
    # An error exactly at the row fails (strictly below passes).
    result = mod.check("at threshold", accuracy_hz(), 0.0)
    assert result["measured"] == accuracy_hz() and result["result"] == "fail", result


def test_check_not_finite_fails():
    mod = freq()
    for bad in (math.nan, math.inf, -math.inf):
        result = mod.check("bad", bad, 450.0)
        assert result["result"] == "fail" and result["note"] == "not finite", bad
        assert result["measured"] is None


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_tone_moved_0_02_hz_fails(fs):
    mod = freq()
    moved = AM_CARRIER_HZ + MOVE_HZ
    result = mod.check("moved carrier", mod.carrier_hz(tone(fs, moved), fs), AM_CARRIER_HZ)
    assert result["result"] == "fail", result
    assert abs(result["measured"] - MOVE_HZ) < calibration_hz(), result
    inside = mod.check("carrier", mod.carrier_hz(tone(fs, AM_CARRIER_HZ), fs), AM_CARRIER_HZ)
    assert inside["result"] == "pass", inside


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_am_rate_moved_0_02_hz_fails(fs):
    mod = freq()
    x = am_tone(fs, AM_CARRIER_HZ, 6.0 + MOVE_HZ, "sawtooth")
    result = mod.check("moved rate", mod.rate_hz(x, fs), 6.0)
    assert result["result"] == "fail", result
    assert abs(result["measured"] - MOVE_HZ) < calibration_hz(), result
