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

Story 2.2 (gamma PAC layer): the tool is reused unchanged. Calibration adds a
250 Hz carrier amplitude-modulated at 40 and 60 Hz by the sine envelope with
25 and 100 percent depth (both phases 0 at the first sample, and the
envelope trough at the engine's nonzero floor from the spec vectors, like
the engine layer), read within the calibration row at both sample rates;
must-fail: a gamma AM rate moved 0.02 Hz fails row `frequency-accuracy`.
"""

import importlib
import json
import math
import struct
from pathlib import Path

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
VECTORS = Path(__file__).resolve().parents[2] / "tests" / "data" / "signal_spec_vectors.json"


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


# ------------------------------------------------- gamma rates (Story 2.2)

GAMMA_CARRIER_HZ = 250.0
GAMMA_RATES_HZ = (40.0, 60.0)
GAMMA_DEPTHS = (0.25, 1.0)


def engine_envelope_trough():
    """The engine gamma envelope at its trough, from the spec vectors.

    The engine envelope is never 0 (signal spec, Gamma PAC layer, Uncoupled):
    the engine sine stays inside (-1, 1). The harness tone below keeps the
    same floor, so at 100 percent depth it never reaches exact zero either.
    """
    rows = json.loads(VECTORS.read_text(encoding="utf-8"))["gamma_envelopes"]
    e = {struct.unpack(">d", bytes.fromhex(r["e_bits"][2:]))[0] for r in rows if int(r["phase"]) == 2**63}
    assert len(e) == 1 and 0.0 < min(e) < 1e-6, e
    return e.pop()


def gamma_am_tone(fs, rate_hz, depth, seconds=SECONDS):
    """A 250 Hz carrier amplitude-modulated at rate_hz by the sine envelope.

    Made here; both phases are 0 at the first sample, like the engine layer,
    and the envelope spans [trough, 1 - trough] with the engine's trough.
    """
    t = np.arange(int(seconds * fs), dtype=np.float64) / fs
    floor = engine_envelope_trough()
    e = 0.5 + (0.5 - floor) * np.cos(2.0 * np.pi * rate_hz * t)
    a = 1.0 - depth * (1.0 - e)
    return a * np.sin(2.0 * np.pi * GAMMA_CARRIER_HZ * t)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("rate_hz", GAMMA_RATES_HZ)
@pytest.mark.parametrize("depth", GAMMA_DEPTHS)
def test_gamma_am_tone_carrier_and_rate_read_within_calibration(fs, rate_hz, depth):
    x = gamma_am_tone(fs, rate_hz, depth)
    mod = freq()
    carrier = mod.carrier_hz(x, fs)
    rate = mod.rate_hz(x, fs)
    assert abs(carrier - GAMMA_CARRIER_HZ) < calibration_hz(), (fs, rate_hz, depth, carrier)
    assert abs(rate - rate_hz) < calibration_hz(), (fs, rate_hz, depth, rate)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("rate_hz", GAMMA_RATES_HZ)
def test_gamma_am_rate_moved_0_02_hz_fails(fs, rate_hz):
    mod = freq()
    x = gamma_am_tone(fs, rate_hz + MOVE_HZ, 0.25)
    result = mod.check("moved gamma rate", mod.rate_hz(x, fs), rate_hz)
    assert result["result"] == "fail", result
    assert abs(result["measured"] - MOVE_HZ) < calibration_hz(), result


# ------------------------------------------- coupled gamma (Story 2.3)
#
# rate_hz(x, fs, min_hz=None): with min_hz the AM-rate peak search starts at
# the larger of the window's main-lobe floor and min_hz, because a coupled
# gamma envelope carries a theta-rate swell line as strong as the gamma-rate
# line. Without min_hz the tool is unchanged.

THETA_RATE_HZ = 6.0


def gamma_rate_floor_hz():
    r = table_row("gamma-rate")
    assert r.kind == "ranges" and r.unit == "Hz", r
    return r.min


def swell_tone(fs, rate_hz, depth, phase_deg, seconds=SECONDS):
    """A 250 Hz carrier amplitude-modulated at rate_hz whose AM depth swells at 6 Hz.

    Made here: the depth is depth * s, s a raised cosine at the theta rate
    peaking at phase_deg of the theta cycle (the smooth swell).
    """
    t = np.arange(int(seconds * fs), dtype=np.float64) / fs
    s = 0.5 + 0.5 * np.cos(2.0 * np.pi * THETA_RATE_HZ * t - np.deg2rad(phase_deg))
    e = 0.5 + 0.5 * np.cos(2.0 * np.pi * rate_hz * t)
    a = 1.0 - (depth * s) * (1.0 - e)
    return a * np.sin(2.0 * np.pi * GAMMA_CARRIER_HZ * t)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("depth", GAMMA_DEPTHS)
@pytest.mark.parametrize("phase_deg", (0.0, 90.0, 180.0, 270.0))
def test_swell_tone_rate_reads_within_calibration_with_min_hz(fs, depth, phase_deg):
    mod = freq()
    for seconds in (5.0, SECONDS):
        x = swell_tone(fs, 40.0, depth, phase_deg, seconds=seconds)
        rate = mod.rate_hz(x, fs, min_hz=gamma_rate_floor_hz())
        carrier = mod.carrier_hz(x, fs)
        assert abs(rate - 40.0) < calibration_hz(), (fs, depth, phase_deg, seconds, rate)
        assert abs(carrier - GAMMA_CARRIER_HZ) < calibration_hz(), (fs, depth, phase_deg, seconds, carrier)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_swell_tone_rate_moved_0_02_hz_fails_with_min_hz(fs):
    mod = freq()
    x = swell_tone(fs, 40.0 + MOVE_HZ, 0.25, 90.0)
    result = mod.check("moved swell gamma rate", mod.rate_hz(x, fs, min_hz=gamma_rate_floor_hz()), 40.0)
    assert result["result"] == "fail", result
    assert abs(result["measured"] - MOVE_HZ) < calibration_hz(), result


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_min_hz_none_or_below_the_main_lobe_leaves_the_tool_unchanged(fs):
    mod = freq()
    for x in (am_tone(fs, AM_CARRIER_HZ, 6.0, "sawtooth"), gamma_am_tone(fs, 40.0, 0.25)):
        default = mod.rate_hz(x, fs)
        assert mod.rate_hz(x, fs, min_hz=None) == default
        assert mod.rate_hz(x, fs, min_hz=0.0) == default


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_min_hz_skips_a_stronger_line_below_it(fs):
    # A theta-rate AM tone read from the gamma-rate floor up does not report
    # the 6 Hz line.
    mod = freq()
    x = am_tone(fs, AM_CARRIER_HZ, THETA_RATE_HZ, "sine")
    assert abs(mod.rate_hz(x, fs) - THETA_RATE_HZ) < calibration_hz()
    got = mod.rate_hz(x, fs, min_hz=gamma_rate_floor_hz())
    assert abs(got - THETA_RATE_HZ) > 1.0, got


# ------------------------------------------- phase mode (Story 2.5)
#
# Contract with tests/assertions/frequency.py:
#
# - `PHASE_STEP_CYCLES = 1e-4`.
# - `phase_track(x, fs, expected_cycles) -> dict`: expected_cycles is a
#   float64 array the length of x, the closed-form phase in cycles (any
#   constant offset). Keys:
#   "residual_cycles": the unwrapped phase of the FFT analytic signal of x
#     minus 2 pi times expected_cycles, in cycles, trimmed by TRIM_S at each
#     end, its first trimmed value subtracted;
#   "rate_error_hz": the instantaneous rate error, from the derivative of the
#     residual, in Hz (finite where x is);
#   "max_rate_error_hz": max abs of rate_error_hz;
#   "max_step_cycles": max abs of np.diff(residual_cycles).
# - `check_phase(name, x, fs, expected_cycles) -> dict`: the Story 1.4 report
#   assertion shape of check(), row frequency-accuracy read on every call;
#   measured = max_rate_error_hz; "pass" only when measured is strictly below
#   the row and max_step_cycles is below PHASE_STEP_CYCLES; note "phase step"
#   when the step test fails; note "not finite" and measured None for a NaN
#   or infinite measure.
#
# The per-sample difference of the residual alone, times fs, carries the
# edge ripple of the FFT analytic signal at twice the carrier (about 0.19 Hz
# half a second in from the ends, on a perfect tone), so these tests pin
# rate_error_hz only through the calibration: every Python-synthesized swept
# tone below reads within row frequency-accuracy-calibration, and the
# must-fails read outside row frequency-accuracy.
#
# Calibration: swept tones made here with NumPy from the closed form
# Phi(t) = (f_L + r) t + K (cos phi0 - cos(2 pi t / P + phi0)),
# K = s P / (2 pi) (signal spec, Rate curve), sine of 2 pi Phi plus a phase
# offset. Must-fail: a schedule whose center is off by 0.02 Hz fails row
# frequency-accuracy; a tone with a 0.01 cycle phase step fails with note
# "phase step".

PHASE_SECONDS = 10.0
# (left carrier, center, swing, period, start phase degrees, seconds)
SWEPT_TONES = (
    (100.0, 1.5, 1.5, 60.0, 270.0, PHASE_SECONDS),  # the Sleep cycle on a 100 Hz left carrier
    (100.0, 1.5, 1.5, 60.0, 0.0, 12.0),
    (100.0, 1.5, 1.5, 60.0, 90.0, PHASE_SECONDS),
    (400.0, 6.0, 3.0, 60.0, 180.0, PHASE_SECONDS),
    (250.0, 10.0, 5.0, 60.0, 45.0, 20.0),
)


def swept_cycles(fs, left_hz, center_hz, swing_hz, period_s, start_deg, seconds):
    """The closed-form right-ear phase in cycles at each sample (made here)."""
    t = np.arange(int(round(seconds * fs)), dtype=np.float64) / fs
    phi0 = math.radians(start_deg)
    k = swing_hz * period_s / (2.0 * math.pi)
    return (left_hz + center_hz) * t + k * (math.cos(phi0) - np.cos(2.0 * math.pi * t / period_s + phi0))


def swept_tone(cycles, phase=0.4):
    return 0.9 * np.sin(2.0 * np.pi * cycles + phase)


def own_residual(x, fs, expected_cycles):
    """The residual by its definition, made here with NumPy."""
    n = x.size
    spectrum = np.fft.fft(np.asarray(x, dtype=np.float64))
    h = np.zeros(n)
    h[0] = 1.0
    if n % 2 == 0:
        h[n // 2] = 1.0
        h[1:n // 2] = 2.0
    else:
        h[1:(n + 1) // 2] = 2.0
    z = np.fft.ifft(spectrum * h)
    k = int(round(freq().TRIM_S * fs))
    residual = (np.unwrap(np.angle(z)) - 2.0 * np.pi * expected_cycles) / (2.0 * np.pi)
    residual = residual[k:n - k]
    return residual - residual[0]


def test_phase_step_constant():
    assert freq().PHASE_STEP_CYCLES == 1e-4


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_phase_track_keys_and_definitions(fs):
    mod = freq()
    cycles = swept_cycles(fs, *SWEPT_TONES[0])
    x = swept_tone(cycles)
    got = mod.phase_track(x, fs, cycles)
    assert set(got) == {"residual_cycles", "rate_error_hz", "max_rate_error_hz", "max_step_cycles"}
    residual = np.asarray(got["residual_cycles"])
    k = int(round(mod.TRIM_S * fs))
    assert residual.shape == (x.size - 2 * k,)
    assert residual[0] == 0.0
    assert np.max(np.abs(residual - own_residual(x, fs, cycles))) < 1e-9
    rate = np.asarray(got["rate_error_hz"], dtype=np.float64)
    assert rate.ndim == 1 and rate.size > 0 and np.all(np.isfinite(rate))
    assert got["max_rate_error_hz"] == float(np.max(np.abs(rate)))
    assert got["max_step_cycles"] == float(np.max(np.abs(np.diff(residual))))
    # Any constant offset in expected_cycles gives the same residual.
    shifted = mod.phase_track(x, fs, cycles + 123.25)
    assert np.max(np.abs(np.asarray(shifted["residual_cycles"]) - residual)) < 1e-9
    assert abs(shifted["max_rate_error_hz"] - got["max_rate_error_hz"]) < 1e-6


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("tone", SWEPT_TONES)
def test_swept_tone_reads_within_calibration(fs, tone):
    mod = freq()
    cycles = swept_cycles(fs, *tone)
    got = mod.phase_track(swept_tone(cycles), fs, cycles)
    assert got["max_rate_error_hz"] < calibration_hz(), (fs, tone, got["max_rate_error_hz"])
    assert got["max_step_cycles"] < mod.PHASE_STEP_CYCLES, (fs, tone, got["max_step_cycles"])
    result = mod.check_phase(f"swept {tone}", swept_tone(cycles), fs, cycles)
    assert result["result"] == "pass" and result["note"] == "", result


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_fixed_tone_reads_within_calibration_in_phase_mode(fs):
    mod = freq()
    t = np.arange(int(PHASE_SECONDS * fs), dtype=np.float64) / fs
    for f in (100.0, 451.237):
        got = mod.phase_track(swept_tone(f * t), fs, f * t)
        assert got["max_rate_error_hz"] < calibration_hz(), (fs, f, got["max_rate_error_hz"])


def test_check_phase_report_shape():
    mod = freq()
    fs = SAMPLE_RATES[0]
    cycles = swept_cycles(fs, *SWEPT_TONES[0])
    result = mod.check_phase("sleep", swept_tone(cycles), fs, cycles)
    assert set(result) == {"name", "row", "threshold", "unit", "measured", "result", "note"}
    assert result["name"] == "sleep"
    assert result["row"] == "frequency-accuracy"
    assert result["threshold"] == accuracy_hz()
    assert result["unit"] == "Hz"
    track = mod.phase_track(swept_tone(cycles), fs, cycles)
    assert result["measured"] == track["max_rate_error_hz"]


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("start_deg", (270.0, 0.0))
def test_swept_center_off_by_0_02_hz_fails(fs, start_deg):
    mod = freq()
    left, center, swing, period, _, seconds = SWEPT_TONES[0]
    want = swept_cycles(fs, left, center, swing, period, start_deg, seconds)
    moved = swept_cycles(fs, left, center + MOVE_HZ, swing, period, start_deg, seconds)
    result = mod.check_phase("moved center", swept_tone(moved), fs, want)
    assert result["result"] == "fail", result
    assert result["note"] == "", result
    assert result["measured"] > accuracy_hz(), result
    assert abs(result["measured"] - MOVE_HZ) < calibration_hz(), result


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_swept_tone_with_a_phase_step_fails_with_note(fs):
    mod = freq()
    cycles = swept_cycles(fs, *SWEPT_TONES[0])
    stepped = cycles.copy()
    stepped[stepped.size // 2:] += 0.01
    result = mod.check_phase("phase step", swept_tone(stepped), fs, cycles)
    assert result["result"] == "fail", result
    assert result["note"] == "phase step", result
    track = mod.phase_track(swept_tone(stepped), fs, cycles)
    assert track["max_step_cycles"] >= mod.PHASE_STEP_CYCLES, track["max_step_cycles"]


def test_check_phase_not_finite_fails():
    mod = freq()
    fs = SAMPLE_RATES[0]
    cycles = swept_cycles(fs, *SWEPT_TONES[0])
    for bad in (math.nan, math.inf):
        x = swept_tone(cycles)
        x[x.size // 2] = bad
        result = mod.check_phase("bad", x, fs, cycles)
        assert result["result"] == "fail" and result["note"] == "not finite", (bad, result)
        assert result["measured"] is None


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_wrong_start_phase_schedule_fails(fs):
    # Must-fail: the Sleep tone judged against the same cycle at 90 degrees.
    mod = freq()
    left, center, swing, period, _, seconds = SWEPT_TONES[0]
    x = swept_tone(swept_cycles(fs, left, center, swing, period, 270.0, seconds))
    wrong = swept_cycles(fs, left, center, swing, period, 90.0, seconds)
    result = mod.check_phase("wrong start phase", x, fs, wrong)
    assert result["result"] == "fail", result
