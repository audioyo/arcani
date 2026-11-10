"""Coupling timing tool, calibrated on Python-synthesized signals (Story 2.3, FR-3).

Every signal here is made in the harness with NumPy in closed form, at a
known theta 0 degree time and a known swell peak time; none comes from the
engine or the reference. Rows come from tests/tables/*.tsv through the
assertion call `assertions.row`; no threshold is written here as a literal.

Contract with tests/assertions/coupling_timing.py (imported as
`assertions.coupling_timing`; NumPy and the standard library only, plus the
assertions package for `row`):

- `ROW = "coupling-timing"` (ms), `CALIBRATION_ROW =
  "coupling-timing-calibration"` (ms, a tenth of ROW), `TRIM_S = 0.5`.
- `zero_degree_times(theta, fs, theta_rate_hz, shape) -> ndarray`: float64
  seconds (sample 0 is t = 0) of every theta 0 degree point inside the
  trimmed span, from the theta tap's analytic envelope fitted per cycle to
  the signal spec ideal shape template (docs/signal-spec.md, Theta
  reference), sub-sample.
- `swell_curve(gamma, fs) -> ndarray`: 1 - |analytic envelope| of the gamma
  tap, zero-phase low-passed below every gamma rate of row `gamma-rate` (no
  delay); same length as the input.
- `timing_errors(gamma, theta, fs, theta_rate_hz, shape, coupling_phase_deg)
  -> ndarray`: float64 seconds, one per full theta cycle: the measured swell
  peak (a theta-rate cosine fit per cycle of the swell curve) minus (0 degree
  time + coupling_phase_deg / 360 / theta_rate_hz), wrapped into
  [-T/2, T/2) with T = 1 / theta_rate_hz, the first and last TRIM_S seconds
  left out. Positive means the swell peak is late.
- `check(name, gamma, theta, fs, theta_rate_hz, shape, coupling_phase_deg,
  row_id=ROW) -> dict`: the report assertion shape {"name", "row",
  "threshold", "unit", "measured", "result", "note"}; measured is the
  largest |error| in ms; "pass" when strictly below the row value. A
  non-finite input fails with note "not finite" and measured None; a signal
  with no full cycle after the trim fails with measured None.
- The tool reads only the two taps (one channel each, 1-D) plus fs, the
  theta rate, the shape, and the coupling phase: no recipe, plan, depth, or
  engine internal.

Calibration (row `coupling-timing-calibration`): a 450 Hz carrier
amplitude-modulated at 6 Hz by each theta shape with 75 percent depth, and a
250 Hz sine carrier amplitude-modulated at 40 Hz whose AM depth swells once
per theta cycle (a raised cosine at the theta rate) to 25 or 100 percent at
0, 90, 180, or 270 degrees, 5 s, at 44.1 and 48 kHz; reported within the
calibration row, with deliberate shifts of 0.1 ms and 1.5 ms (and a theta
0 degree point away from t = 0) measured within the calibration row of the
shift. Must-fail: a shift past the calibration row fails the calibration
check; a shift past row `coupling-timing` fails it; a constant-depth
(uncoupled) gamma and a swell at the wrong phase fail it; non-finite and
too-short inputs fail.
"""

import ast
import importlib
import inspect
import math
from pathlib import Path

import numpy as np
import pytest

from assertions import row as table_row
from assertions.tables import load_tables

SECONDS = 5.0
THETA_CARRIER_HZ = 450.0
THETA_RATE_HZ = 6.0
THETA_DEPTH = 0.75
GAMMA_CARRIER_HZ = 250.0
GAMMA_RATE_HZ = 40.0
DEPTHS = (0.25, 1.0)
PHASES_DEG = (0.0, 90.0, 180.0, 270.0)
SHAPES = ("sine", "smoothed_on_off", "sawtooth", "reverse_saw")
EDGE_S = 0.010   # harness shapes only; the engine's edge is row theta-edge
ON_SHARE = 0.5   # harness shapes only; the engine's share is row theta-on-share
SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
TOOL = Path(__file__).resolve().parents[1] / "assertions" / "coupling_timing.py"


def ct():
    assert TOOL.is_file(), f"missing {TOOL} (Story 2.3 coupling timing tool)"
    return importlib.import_module("assertions.coupling_timing")


def timing_s():
    r = table_row("coupling-timing")
    assert r.unit == "ms", r
    return r.value / 1000.0


def calibration_s():
    r = table_row("coupling-timing-calibration")
    assert r.unit == "ms", r
    assert r.value < table_row("coupling-timing").value, "the calibration row must be tighter"
    return r.value / 1000.0


# ------------------------------------------------------- harness signals


def harness_envelope(shape, phi, rate_hz):
    """Theta envelope in [0, 1] with its 0 degree point (peak) at phi = 0, made here."""
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


def times(fs, seconds=SECONDS):
    return np.arange(int(round(seconds * fs)), dtype=np.float64) / fs


def theta_tap(fs, shape, zero_s=0.0, seconds=SECONDS):
    """450 Hz carrier amplitude-modulated at 6 Hz by `shape`, 0 degree points at zero_s + k / 6."""
    t = times(fs, seconds)
    e = harness_envelope(shape, THETA_RATE_HZ * (t - zero_s), THETA_RATE_HZ)
    a = 1.0 - THETA_DEPTH * (1.0 - e)
    return a * np.sin(2.0 * np.pi * THETA_CARRIER_HZ * t)


def gamma_tap(fs, depth, phase_deg, zero_s=0.0, shift_s=0.0, seconds=SECONDS, coupled=True):
    """250 Hz sine carrier amplitude-modulated at 40 Hz; the AM depth swells to `depth`.

    The swell is a raised cosine at the theta rate whose peaks are at
    zero_s + phase_deg / 360 / 6 + shift_s + k / 6. Uncoupled: the depth is
    `depth` throughout.
    """
    t = times(fs, seconds)
    peak = zero_s + phase_deg / 360.0 / THETA_RATE_HZ + shift_s
    s = 0.5 + 0.5 * np.cos(2.0 * np.pi * THETA_RATE_HZ * (t - peak)) if coupled else np.ones_like(t)
    e = 0.5 + 0.5 * np.cos(2.0 * np.pi * GAMMA_RATE_HZ * t)
    a = 1.0 - (depth * s) * (1.0 - e)
    return a * np.sin(2.0 * np.pi * GAMMA_CARRIER_HZ * t)


def errors_of(fs, shape, depth, phase_deg, zero_s=0.0, shift_s=0.0, theta_zero_s=None):
    theta = theta_tap(fs, shape, zero_s if theta_zero_s is None else theta_zero_s)
    gamma = gamma_tap(fs, depth, phase_deg, zero_s, shift_s)
    got = ct().timing_errors(gamma, theta, fs, THETA_RATE_HZ, shape, phase_deg)
    assert isinstance(got, np.ndarray) and got.dtype == np.float64 and got.ndim == 1, got
    return got


def full_cycles(seconds=SECONDS):
    """Full theta cycles in the trimmed span, give or take the two edge cycles."""
    return int((seconds - 2 * 0.5) * THETA_RATE_HZ)


# ------------------------------------------------------------ constants


def test_tool_constants_and_rows():
    mod = ct()
    assert mod.ROW == "coupling-timing"
    assert mod.CALIBRATION_ROW == "coupling-timing-calibration"
    assert mod.TRIM_S == 0.5
    assert calibration_s() < timing_s()
    # The calibration row is a tenth of the timing row (design log (nn)).
    assert math.isclose(table_row("coupling-timing-calibration").value * 10.0,
                        table_row("coupling-timing").value)


def test_tool_signatures_take_only_the_taps_and_the_named_settings():
    mod = ct()
    assert list(inspect.signature(mod.zero_degree_times).parameters) == [
        "theta", "fs", "theta_rate_hz", "shape"]
    assert list(inspect.signature(mod.swell_curve).parameters) == ["gamma", "fs"]
    assert list(inspect.signature(mod.timing_errors).parameters) == [
        "gamma", "theta", "fs", "theta_rate_hz", "shape", "coupling_phase_deg"]
    params = inspect.signature(mod.check).parameters
    assert list(params) == ["name", "gamma", "theta", "fs", "theta_rate_hz", "shape",
                            "coupling_phase_deg", "row_id"]
    assert params["row_id"].default == mod.ROW


FORBIDDEN_MODULES = {"json", "pickle", "subprocess", "ctypes", "importlib", "os", "pathlib", "io",
                     "shutil", "reference", "recipe", "tools"}


def test_tool_reads_no_recipe_plan_depth_or_engine_internal():
    assert TOOL.is_file(), f"missing {TOOL}"
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                assert top in ("numpy", "math", "cmath", "typing", "functools", "__future__"), a.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                top = (node.module or "").split(".")[0]
                assert top in ("numpy", "math", "typing", "functools", "__future__"), node.module
            else:
                # Inside the assertions package only.
                assert node.level == 1, ast.dump(node)
                assert (node.module or "") not in FORBIDDEN_MODULES, node.module
        if isinstance(node, ast.arg):
            # No function takes a depth: the swell is read from the gamma tap.
            assert "depth" not in node.arg.lower(), f"the timing tool takes a depth: {node.arg}"
        names = []
        if isinstance(node, ast.Name):
            names = [node.id]
        elif isinstance(node, ast.arg):
            names = [node.arg]
        elif isinstance(node, ast.Attribute):
            names = [node.attr]
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names = [node.name]
        for n in names:
            low = n.lower()
            assert "recipe" not in low, f"the timing tool names a recipe: {n}"
            assert low not in ("plan", "open", "am_depth_percent", "coupling_phase_units"), \
                f"the timing tool reads {n}"
            assert "tapdump" not in low and "arc_" not in low, n


# ------------------------------------------------------------ 0 degree times


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("zero_s", (0.0, 0.0001, 0.0015, 0.05))
def test_zero_degree_times_read_within_calibration(fs, shape, zero_s):
    mod = ct()
    got = mod.zero_degree_times(theta_tap(fs, shape, zero_s), fs, THETA_RATE_HZ, shape)
    assert isinstance(got, np.ndarray) and got.dtype == np.float64 and got.ndim == 1
    assert got.size >= full_cycles() - 1, got
    # Every point lies inside the trimmed span, in order, one theta period apart.
    assert np.all(got >= mod.TRIM_S) and np.all(got <= SECONDS - mod.TRIM_S), got
    k = np.round((got - zero_s) * THETA_RATE_HZ)
    assert np.all(np.diff(k) == 1), k
    want = zero_s + k / THETA_RATE_HZ
    assert np.max(np.abs(got - want)) < calibration_s(), (fs, shape, zero_s, got - want)


# ------------------------------------------------------------ swell curve


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("depth", DEPTHS)
def test_swell_curve_has_no_delay(fs, depth):
    mod = ct()
    gamma = gamma_tap(fs, depth, 90.0, zero_s=0.0123)
    curve = mod.swell_curve(gamma, fs)
    assert isinstance(curve, np.ndarray) and curve.shape == gamma.shape
    t = times(fs)
    peak = 0.0123 + 90.0 / 360.0 / THETA_RATE_HZ
    s = 0.5 + 0.5 * np.cos(2.0 * np.pi * THETA_RATE_HZ * (t - peak))
    k = int(round(ct().TRIM_S * fs))
    a = curve[k:-k] - np.mean(curve[k:-k])
    b = s[k:-k] - np.mean(s[k:-k])
    lags = range(-64, 65)
    corr = [float(np.dot(a[64:-64], b[64 + lag:b.size - 64 + lag])) for lag in lags]
    assert list(lags)[int(np.argmax(corr))] == 0, "the swell curve is delayed"
    # The swell curve rises where the AM depth is largest: it follows s.
    assert corr[64] > 0.0


# ------------------------------------------------------------ calibration


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("phase_deg", PHASES_DEG)
@pytest.mark.parametrize("depth", DEPTHS)
def test_swell_peaks_read_within_calibration(fs, shape, phase_deg, depth):
    got = errors_of(fs, shape, depth, phase_deg)
    assert full_cycles() - 2 <= got.size <= full_cycles() + 1, got.size
    assert np.max(np.abs(got)) < calibration_s(), (fs, shape, phase_deg, depth, got)
    result = ct().check("calibration", gamma_tap(fs, depth, phase_deg), theta_tap(fs, shape), fs,
                        THETA_RATE_HZ, shape, phase_deg, row_id=ct().CALIBRATION_ROW)
    assert result["result"] == "pass", result


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("phase_deg", (0.0, 270.0))
@pytest.mark.parametrize("depth", DEPTHS)
@pytest.mark.parametrize("shift_s", (0.0001, 0.0015, -0.0015))
def test_known_shift_is_measured_within_calibration(fs, shape, phase_deg, depth, shift_s):
    # Positive means the swell peak is late.
    got = errors_of(fs, shape, depth, phase_deg, shift_s=shift_s)
    assert got.size >= full_cycles() - 2
    assert np.max(np.abs(got - shift_s)) < calibration_s(), (fs, shape, phase_deg, depth, shift_s, got)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("shape", SHAPES)
def test_zero_degree_point_comes_from_the_theta_tap(fs, shape):
    # Theta and swell moved together: no error. Theta moved alone: the swell
    # reads early by that much.
    together = errors_of(fs, shape, 1.0, 90.0, zero_s=0.0515)
    assert np.max(np.abs(together)) < calibration_s(), together
    theta_late = errors_of(fs, shape, 1.0, 90.0, zero_s=0.0, theta_zero_s=0.0015)
    assert np.max(np.abs(theta_late + 0.0015)) < calibration_s(), theta_late


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_errors_wrap_into_half_a_theta_period(fs):
    period = 1.0 / THETA_RATE_HZ
    # A whole period later reads as no error.
    whole = errors_of(fs, "sine", 1.0, 0.0, shift_s=period)
    assert np.max(np.abs(whole)) < calibration_s(), whole
    # Just past half a period reads as just under half a period early.
    past_half = errors_of(fs, "sine", 1.0, 0.0, shift_s=period / 2.0 + 0.001)
    assert np.all(past_half >= -period / 2.0) and np.all(past_half < period / 2.0), past_half
    assert np.max(np.abs(past_half - (-period / 2.0 + 0.001))) < calibration_s(), past_half


# ------------------------------------------------------------ verdicts


def test_check_report_shape_and_pass():
    mod = ct()
    fs = SAMPLE_RATES[0]
    gamma = gamma_tap(fs, 0.25, 90.0, shift_s=0.001)
    theta = theta_tap(fs, "sawtooth")
    result = mod.check("timing", gamma, theta, fs, THETA_RATE_HZ, "sawtooth", 90.0)
    assert set(result) == {"name", "row", "threshold", "unit", "measured", "result", "note"}
    assert result["name"] == "timing"
    assert result["row"] == "coupling-timing"
    assert result["threshold"] == table_row("coupling-timing").value
    assert result["unit"] == "ms"
    assert result["result"] == "pass", result
    assert abs(result["measured"] - 1.0) < calibration_s() * 1000.0, result
    errs = mod.timing_errors(gamma, theta, fs, THETA_RATE_HZ, "sawtooth", 90.0)
    assert math.isclose(result["measured"], 1000.0 * float(np.max(np.abs(errs))), rel_tol=1e-12)
    cal = mod.check("timing", gamma, theta, fs, THETA_RATE_HZ, "sawtooth", 90.0,
                    row_id=mod.CALIBRATION_ROW)
    assert cal["row"] == "coupling-timing-calibration"
    assert cal["threshold"] == table_row("coupling-timing-calibration").value
    assert cal["result"] == "fail", cal  # 1 ms is past the calibration row


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("shape", SHAPES)
def test_shift_past_the_calibration_row_fails_the_calibration_check(fs, shape):
    mod = ct()
    shift = 2.0 * calibration_s()
    for depth in DEPTHS:
        result = mod.check("moved", gamma_tap(fs, depth, 180.0, shift_s=shift), theta_tap(fs, shape), fs,
                           THETA_RATE_HZ, shape, 180.0, row_id=mod.CALIBRATION_ROW)
        assert result["result"] == "fail", result
        assert abs(result["measured"] / 1000.0 - shift) < calibration_s(), result


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("depth", DEPTHS)
def test_shift_past_the_timing_row_fails(fs, depth):
    mod = ct()
    for shape in SHAPES:
        inside = mod.check("inside", gamma_tap(fs, depth, 90.0, shift_s=0.5 * timing_s()),
                           theta_tap(fs, shape), fs, THETA_RATE_HZ, shape, 90.0)
        assert inside["result"] == "pass", inside
        for shift in (1.5 * timing_s(), -1.5 * timing_s()):
            past = mod.check("past", gamma_tap(fs, depth, 90.0, shift_s=shift), theta_tap(fs, shape), fs,
                             THETA_RATE_HZ, shape, 90.0)
            assert past["result"] == "fail", past


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("depth", DEPTHS)
def test_constant_depth_gamma_fails(fs, depth):
    # Must-fail: an uncoupled gamma has no swell, so no peak at the phase.
    mod = ct()
    for shape in SHAPES:
        for phase in PHASES_DEG:
            gamma = gamma_tap(fs, depth, phase, coupled=False)
            result = mod.check("uncoupled", gamma, theta_tap(fs, shape), fs, THETA_RATE_HZ, shape, phase)
            assert result["result"] == "fail", (shape, phase, result)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("depth", DEPTHS)
def test_swell_at_the_wrong_phase_fails(fs, depth):
    mod = ct()
    for shape in SHAPES:
        for made, judged in ((90.0, 0.0), (180.0, 0.0), (0.0, 270.0), (270.0, 255.0)):
            gamma = gamma_tap(fs, depth, made)
            result = mod.check("wrong phase", gamma, theta_tap(fs, shape), fs, THETA_RATE_HZ, shape, judged)
            assert result["result"] == "fail", (shape, made, judged, result)


def test_non_finite_input_fails():
    mod = ct()
    fs = SAMPLE_RATES[-1]
    for which in ("gamma", "theta"):
        for bad in (math.nan, math.inf, -math.inf):
            gamma = gamma_tap(fs, 1.0, 0.0)
            theta = theta_tap(fs, "sine")
            (gamma if which == "gamma" else theta)[fs * 2 + 17] = bad
            result = mod.check("bad", gamma, theta, fs, THETA_RATE_HZ, "sine", 0.0)
            assert result["result"] == "fail", (which, bad, result)
            assert result["note"] == "not finite", (which, bad, result)
            assert result["measured"] is None


def test_signal_with_no_full_cycle_fails():
    mod = ct()
    fs = SAMPLE_RATES[0]
    for seconds in (1.0, 1.1):
        gamma = gamma_tap(fs, 1.0, 0.0, seconds=seconds)
        theta = theta_tap(fs, "sine", seconds=seconds)
        result = mod.check("short", gamma, theta, fs, THETA_RATE_HZ, "sine", 0.0)
        assert result["result"] == "fail", result
        assert result["measured"] is None, result
