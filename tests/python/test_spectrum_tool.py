"""Spectrum tool, calibrated on Python-synthesized signals (Story 2.4).

Every signal here is made in the harness with NumPy in closed form, a sum of
sines of known frequencies and levels; none comes from the engine or the
reference. Rows come from tests/tables/*.tsv through the assertion call
`assertions.row`; no threshold is written here as a literal.

Contract with tests/assertions/spectrum.py (imported as
`assertions.spectrum`; NumPy, math, and the standard library only, plus the
assertions package for `row`; it reads no engine internal), from the Story
2.4 spec, Implementation Notes:

- `PAD_FACTOR = 8`, `FLOOR_DB = -90.0`.
- `lines(x, fs, band=None)`: `(frequency_hz, level_db)` pairs sorted by
  frequency, for every spectral line with `band[0] <= f <= band[1]` (all
  lines when band is None), the level relative to the strongest line of the
  whole spectrum (0 dB), whatever the band. Method: a 4-term Blackman-Harris
  window over the whole signal, zero-padded to at least PAD_FACTOR times its
  length, local maxima of the magnitude at least FLOOR_DB re the strongest,
  each refined by a parabola through the dB magnitudes of the peak bin and
  its two neighbours. Lines closer than 8 / T Hz (T the length in seconds)
  are not resolved. ValueError for anything but one channel of finite
  samples at least 2 long.
- `worst_line(x, fs, lo_hz, hi_hz=None)`: the level of the loudest line in
  [lo_hz, hi_hz] (to fs / 2 when None); -inf when there is none.
- `check(name, x, fs, band, expected)`: `expected` a list of
  `(frequency_hz, level_db)`; each expected line is matched to the nearest
  found line in the band. Returns two report dicts (Story 1.4 assertion
  shape), row `spectrum-frequency` (measured the worst frequency error, Hz)
  then row `spectrum-level` (the worst level error, dB), each "pass" when
  strictly below its row. No found line, or a non-finite input, fails both
  with a note and measured None.

Calibration (rows `spectrum-frequency` and `spectrum-level`, Audio
2026-11-13): multi-tone signals, several lines, some off the FFT bin grid,
levels down to -80 dB, 5 s, at 44.1 and 48 kHz: every known line is found
within both rows. Must-fail: a line moved past the frequency row fails it;
a level changed past the level row fails it.
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
SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
TOOL = Path(__file__).resolve().parents[1] / "assertions" / "spectrum.py"
REPORT_KEYS = {"name", "row", "threshold", "unit", "measured", "result", "note"}

# Known lines (frequency in Hz, level in dB re the strongest line). Some lie on
# the 0.2 Hz bin grid of a 5 s signal, most do not; levels down to -80 dB.
TONE_SETS = {
    "spread": [(100.0, 0.0), (250.0, -6.0), (401.13, -50.0), (444.0, -30.0), (998.1, -10.0),
               (1234.567, -20.0), (3000.3, -40.0), (5555.55, -60.0), (7777.77, -80.0),
               (12000.04, -70.0), (19000.5, -75.0)],
    "octaves": [(110.0, 0.0), (523.25, -3.0), (1046.5, -25.0), (2093.0, -45.0), (4186.0, -65.0),
                (8372.0, -80.0), (15000.75, -55.5)],
    # Lines 2 Hz apart, the closest spacing of a burst spectrum at a 6 Hz
    # theta rate (resolved: 8 / T is 1.6 Hz at 5 s).
    "close": [(1000.0, 0.0), (1002.0, 0.0), (1500.3, -20.0), (1502.3, -20.0), (250.0, -12.0),
              (256.0, -30.0)],
}


def sp():
    assert TOOL.is_file(), f"missing {TOOL} (Story 2.4 spectrum tool)"
    return importlib.import_module("assertions.spectrum")


def frequency_tol():
    r = table_row("spectrum-frequency")
    assert r.kind == "thresholds" and r.unit == "Hz", r
    return r.value


def level_tol():
    r = table_row("spectrum-level")
    assert r.kind == "thresholds" and r.unit == "dB", r
    return r.value


def tones(fs, spec, seconds=SECONDS, scale=0.5):
    """A sum of sines at the given (Hz, dB) lines, the 0 dB line at amplitude `scale`."""
    t = np.arange(int(round(seconds * fs)), dtype=np.float64) / fs
    x = np.zeros_like(t)
    for i, (f, level) in enumerate(spec):
        x += scale * 10.0 ** (level / 20.0) * np.sin(2.0 * math.pi * f * t + 0.37 * i + 0.1)
    return x


def nearest(found, f):
    return min(found, key=lambda p: abs(p[0] - f))


# ------------------------------------------------------------ constants and source


def test_rows_exist_and_are_no_longer_pending():
    for row_id in ("spectrum-frequency", "spectrum-level"):
        r = table_row(row_id)
        assert r.pending == "", (row_id, r.pending)
        assert r.value > 0.0, r
    assert frequency_tol() == load_tables()["spectrum-frequency"].value
    assert level_tol() == load_tables()["spectrum-level"].value


def test_tool_constants_and_signatures():
    mod = sp()
    assert mod.PAD_FACTOR == 8
    assert mod.FLOOR_DB == -90.0
    params = inspect.signature(mod.lines).parameters
    assert list(params) == ["x", "fs", "band"]
    assert params["band"].default is None
    params = inspect.signature(mod.worst_line).parameters
    assert list(params) == ["x", "fs", "lo_hz", "hi_hz"]
    assert params["hi_hz"].default is None
    assert list(inspect.signature(mod.check).parameters) == ["name", "x", "fs", "band", "expected"]


FORBIDDEN_MODULES = {"json", "pickle", "subprocess", "ctypes", "importlib", "os", "pathlib", "io",
                     "shutil", "reference", "recipe", "tools", "coupling_timing"}


def test_tool_imports_only_numpy_math_and_the_assertions_package():
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
                assert node.level == 1, ast.dump(node)
                assert (node.module or "") not in FORBIDDEN_MODULES, node.module
        names = []
        if isinstance(node, ast.Name):
            names = [node.id]
        elif isinstance(node, ast.Attribute):
            names = [node.attr]
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names = [node.name]
        for n in names:
            low = n.lower()
            assert "recipe" not in low and low not in ("plan", "open"), f"the spectrum tool reads {n}"
            assert "tapdump" not in low and "arc_" not in low, n


# ------------------------------------------------------------ calibration


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("set_name", sorted(TONE_SETS))
def test_every_known_line_is_found_within_both_rows(fs, set_name):
    mod = sp()
    spec = TONE_SETS[set_name]
    x = tones(fs, spec)
    found = mod.lines(x, fs)
    assert isinstance(found, list) and found, found
    freqs = [f for f, _ in found]
    assert freqs == sorted(freqs), "lines are not sorted by frequency"
    for f, level in found:
        assert isinstance(f, float) and isinstance(level, float), (f, level)
        assert 0.0 <= f <= fs / 2.0, f
        assert level >= mod.FLOOR_DB - level_tol(), level
        assert level <= level_tol(), level
    worst_f = worst_l = 0.0
    for f, level in spec:
        got_f, got_l = nearest(found, f)
        worst_f = max(worst_f, abs(got_f - f))
        worst_l = max(worst_l, abs(got_l - level))
    assert worst_f < frequency_tol(), (fs, set_name, worst_f)
    assert worst_l < level_tol(), (fs, set_name, worst_l)
    freq_report, level_report = mod.check(f"calibration {set_name}", x, fs, None, spec)
    assert freq_report["result"] == "pass", freq_report
    assert level_report["result"] == "pass", level_report
    assert math.isclose(freq_report["measured"], worst_f, rel_tol=1e-9, abs_tol=1e-12), freq_report
    assert math.isclose(level_report["measured"], worst_l, rel_tol=1e-9, abs_tol=1e-12), level_report


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_the_strongest_line_is_0_db_whatever_its_amplitude(fs):
    mod = sp()
    spec = TONE_SETS["spread"]
    for scale in (1.0, 0.5, 0.01):
        found = mod.lines(tones(fs, spec, scale=scale), fs)
        top = max(found, key=lambda p: p[1])
        assert abs(top[0] - 100.0) < frequency_tol(), top
        assert abs(top[1]) < level_tol(), (scale, top)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_both_rates_and_the_length_change_nothing(fs):
    # A 3 s signal and a 7.3 s signal read the same lines.
    mod = sp()
    spec = TONE_SETS["octaves"]
    for seconds in (3.0, 7.3):
        x = tones(fs, spec, seconds=seconds)
        freq_report, level_report = mod.check("length", x, fs, None, spec)
        assert freq_report["result"] == "pass" and level_report["result"] == "pass", (
            seconds, freq_report, level_report)


# ------------------------------------------------------------ band and level reference


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_band_selects_lines_and_keeps_the_whole_spectrum_reference(fs):
    mod = sp()
    spec = TONE_SETS["spread"]
    x = tones(fs, spec)
    whole = mod.lines(x, fs)
    band = (390.0, 1300.0)
    part = mod.lines(x, fs, band)
    assert part, part
    assert all(band[0] <= f <= band[1] for f, _ in part), part
    assert part == [p for p in whole if band[0] <= p[0] <= band[1]], "the band changed the lines"
    # The strongest line (100 Hz, 0 dB) is outside the band: levels in the band
    # stay relative to it, so the loudest in-band line reads -10 dB (998.1 Hz),
    # not 0 dB.
    loudest = max(part, key=lambda p: p[1])
    assert abs(loudest[0] - 998.1) < frequency_tol(), loudest
    assert abs(loudest[1] - (-10.0)) < level_tol(), loudest
    # Band edges are inclusive.
    edge = mod.lines(x, fs, (nearest(whole, 444.0)[0], nearest(whole, 998.1)[0]))
    assert [round(f, 6) for f, _ in edge][0] == round(nearest(whole, 444.0)[0], 6), edge
    assert [round(f, 6) for f, _ in edge][-1] == round(nearest(whole, 998.1)[0], 6), edge


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_worst_line_is_the_loudest_in_the_band_and_minus_inf_when_none(fs):
    mod = sp()
    spec = TONE_SETS["spread"]
    x = tones(fs, spec)
    got = mod.worst_line(x, fs, 2000.0, 9000.0)
    assert abs(got - (-40.0)) < level_tol(), got
    # hi_hz defaults to fs / 2.
    assert abs(mod.worst_line(x, fs, 10000.0) - (-70.0)) < level_tol()
    assert abs(mod.worst_line(x, fs, 10000.0, fs / 2.0) - mod.worst_line(x, fs, 10000.0)) == 0.0
    # The whole spectrum: 0 dB.
    assert abs(mod.worst_line(x, fs, 0.0)) < level_tol()
    # No line in the band.
    none = mod.worst_line(x, fs, 1300.0, 2900.0)
    assert none == -math.inf, none


# ------------------------------------------------------------ must-fail


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("sign", (1.0, -1.0))
def test_a_line_moved_past_the_frequency_row_fails(fs, sign):
    mod = sp()
    spec = TONE_SETS["spread"]
    moved = [(f + sign * 2.0 * frequency_tol(), level) if f == 1234.567 else (f, level) for f, level in spec]
    x = tones(fs, moved)
    freq_report, level_report = mod.check("moved", x, fs, None, spec)
    assert freq_report["result"] == "fail", freq_report
    assert abs(freq_report["measured"] - 2.0 * frequency_tol()) < frequency_tol() / 10.0, freq_report
    assert level_report["result"] == "pass", level_report
    # Inside the row it passes.
    inside = [(f + sign * 0.5 * frequency_tol(), level) if f == 1234.567 else (f, level) for f, level in spec]
    freq_report, _ = mod.check("inside", tones(fs, inside), fs, None, spec)
    assert freq_report["result"] == "pass", freq_report


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("sign", (1.0, -1.0))
def test_a_level_changed_past_the_level_row_fails(fs, sign):
    mod = sp()
    spec = TONE_SETS["octaves"]
    for target in (1046.5, 8372.0):   # -25 dB and the -80 dB line
        changed = [(f, level + sign * 2.0 * level_tol()) if f == target else (f, level) for f, level in spec]
        x = tones(fs, changed)
        freq_report, level_report = mod.check("changed", x, fs, None, spec)
        assert level_report["result"] == "fail", (target, level_report)
        assert abs(level_report["measured"] - 2.0 * level_tol()) < level_tol() / 10.0, level_report
        assert freq_report["result"] == "pass", (target, freq_report)
        inside = [(f, level + sign * 0.5 * level_tol()) if f == target else (f, level) for f, level in spec]
        _, level_report = mod.check("inside", tones(fs, inside), fs, None, spec)
        assert level_report["result"] == "pass", (target, level_report)


# ------------------------------------------------------------ report shape and faults


def test_report_shape_and_rows():
    mod = sp()
    fs = SAMPLE_RATES[0]
    spec = TONE_SETS["spread"]
    freq_report, level_report = mod.check("shape", tones(fs, spec), fs, (90.0, 500.0),
                                          [(100.0, 0.0), (250.0, -6.0), (444.0, -30.0)])
    for report, row_id in ((freq_report, "spectrum-frequency"), (level_report, "spectrum-level")):
        assert set(report) == REPORT_KEYS, report
        assert report["name"] == "shape"
        assert report["row"] == row_id
        r = table_row(row_id)
        assert report["threshold"] == r.value and report["unit"] == r.unit, report
        assert report["result"] == "pass", report
        assert report["measured"] < report["threshold"], report


def test_an_expected_line_outside_the_band_is_not_found_there():
    # Each expected line is matched to the nearest found line in the band, so
    # a band that leaves out the expected line matches it to a wrong line.
    mod = sp()
    fs = SAMPLE_RATES[-1]
    x = tones(fs, TONE_SETS["spread"])
    freq_report, _ = mod.check("wrong band", x, fs, (900.0, 1300.0), [(444.0, -30.0)])
    assert freq_report["result"] == "fail", freq_report


def test_an_empty_expected_list_fails_both_with_a_note():
    mod = sp()
    fs = SAMPLE_RATES[0]
    for report in mod.check("no expected", tones(fs, TONE_SETS["spread"]), fs, None, []):
        assert report["result"] == "fail", report
        assert report["measured"] is None, report
        assert report["note"] == "no expected lines", report


# A weak line next to a strong one, as in a burst spectrum: a -55 dB line
# 6 Hz from a 0 dB line (the theta-rate spacing) and one 2 Hz away (the
# closest burst line spacing).
WEAK_NEXT_TO_STRONG = [(400.0, 0.0), (406.0, -55.0), (398.0, -55.0)]


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_a_weak_line_next_to_a_strong_one_is_found_within_both_rows(fs):
    mod = sp()
    x = tones(fs, WEAK_NEXT_TO_STRONG)
    freq_report, level_report = mod.check("weak", x, fs, None, WEAK_NEXT_TO_STRONG)
    assert freq_report["result"] == "pass", freq_report
    assert level_report["result"] == "pass", level_report
    for target in (406.0, 398.0):
        changed = [(f, level + 2.0 * level_tol()) if f == target else (f, level)
                   for f, level in WEAK_NEXT_TO_STRONG]
        _, level_report = mod.check("weak moved", tones(fs, changed), fs, None, WEAK_NEXT_TO_STRONG)
        assert level_report["result"] == "fail", (target, level_report)


def test_a_peak_next_to_a_zero_bin_has_a_finite_line():
    mod = sp()
    x = np.zeros(4096)
    x[0] = 1.0   # an impulse: a flat spectrum, its DC and edge bins included
    for f, level in mod.lines(x, 48000):
        assert math.isfinite(f) and math.isfinite(level), (f, level)


def test_no_line_in_the_band_fails_both_with_a_note():
    mod = sp()
    fs = SAMPLE_RATES[0]
    x = tones(fs, TONE_SETS["spread"])
    for report in mod.check("empty", x, fs, (1300.0, 2900.0), [(2000.0, -40.0)]):
        assert report["result"] == "fail", report
        assert report["measured"] is None, report
        assert report["note"], report


@pytest.mark.parametrize("bad", (math.nan, math.inf, -math.inf))
def test_non_finite_input_fails_both_and_lines_raises(bad):
    mod = sp()
    fs = SAMPLE_RATES[-1]
    x = tones(fs, TONE_SETS["octaves"])
    x[fs + 17] = bad
    for report in mod.check("bad", x, fs, None, TONE_SETS["octaves"]):
        assert report["result"] == "fail", report
        assert report["measured"] is None, report
        assert report["note"], report
    with pytest.raises(ValueError):
        mod.lines(x, fs)
    with pytest.raises(ValueError):
        mod.worst_line(x, fs, 0.0)


def test_lines_needs_one_channel_at_least_2_long():
    mod = sp()
    fs = SAMPLE_RATES[0]
    x = tones(fs, TONE_SETS["octaves"], seconds=1.0)
    with pytest.raises(ValueError):
        mod.lines(np.stack([x, x]), fs)
    with pytest.raises(ValueError):
        mod.lines(np.stack([x, x], axis=1), fs)
    with pytest.raises(ValueError):
        mod.lines(np.zeros(1), fs)
    with pytest.raises(ValueError):
        mod.lines(np.zeros(0), fs)
