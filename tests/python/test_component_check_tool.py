"""Component cross-check tool, calibrated on Python-synthesized signals (Story 3.1).

Every signal here is made in the harness with NumPy in closed form: sums of
sines of known frequencies and levels, and swept tones of known power whose
frequency follows a sinusoidal cycle. None comes from the engine or the
reference. Rows come from tests/tables/*.tsv through the assertion call
`assertions.row`; no threshold is written here as a literal.

Contract with tests/assertions/component_check.py (imported as
`assertions.component_check`; NumPy and the standard library only, plus the
assertions package for `row` and `spectrum.lines`; Story 3.1 spec,
Implementation Notes). `table` is a list of rows with attributes
`center_hz`, `low_hz`, `high_hz`, `level` (a linear ratio re the layer's
carrier line) for one layer in one ear.

- `threshold_db()`: the value of row `spectral-component-level`.
- `check_static(name, x, fs, table)`: three report assertion dicts (Story
  1.4 shape, as `spectrum.check` returns), rows `spectrum-frequency`,
  `spectrum-level`, `spectral-component-level` in that order. The first two
  hold the worst error over every table row against the nearest measured
  line (levels in dB, 20 * log10(level)). The third holds the count of
  unmatched lines: a measured line within the threshold of the tap's
  strongest line that no table row matches, or a table row with no measured
  line; a line or row within row `spectrum-level` of the threshold is exempt.
  It passes only at count 0.
- `band_power_db(x, fs, lo_hz, hi_hz)`: the power in the band re the tap's
  total power, in dB.
- `bands(table, resolution_hz)`: each row's interval widened by
  `resolution_hz` at each end, overlapping intervals merged; a list of
  `(lo_hz, hi_hz, expected_power_db)`, the expected power from the sum of
  the band's `level^2`.
- `check_bands(name, x, fs, table)`: report assertion dicts on rows
  `spectrum-level` (each band's measured power against its expected power)
  and `spectral-component-level` (the count of measured lines at or above
  the threshold outside every band). Each interval is widened by the
  spectrum tool's resolution, `8 * fs / len(x)` Hz, plus the row's sweep
  edge: a row swept sinusoidally with half width A over period P has the
  Bessel line spectrum of modulation index A * P, lines 1 / P apart, and the
  edge is the closed-form distance past A at which those lines fall below
  row `spectral-component-level` re the row's strongest line (spec
  amendment 2026-11-16). `bands(table, resolution_hz)` itself widens by
  `resolution_hz` only, as the bands tests here use it.

The spectrum tool itself (tests/assertions/spectrum.py) is not changed by
Story 3.1: its bytes are pinned here.

Calibration signals. Static: a 450 Hz tone with side tones 6 Hz apart, as a
carrier amplitude-modulated at 6 Hz has, 5 s. Swept: a tone whose frequency
is `f0 + swing * sin(2 * pi * t / P + phase)`, of constant amplitude, over a
whole number of cycles, so its power is its amplitude squared over 2 and
lies inside `[f0 - swing, f0 + swing]` but for the sweep's own skirts.
"""

import ast
import hashlib
import importlib
import inspect
import math
from collections import namedtuple
from pathlib import Path

import numpy as np
import pytest

from assertions import row as table_row
from assertions.tables import load_tables

SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
ASSERTIONS = Path(__file__).resolve().parents[1] / "assertions"
TOOL = ASSERTIONS / "component_check.py"
SPECTRUM_TOOL = ASSERTIONS / "spectrum.py"
# sha256 of tests/assertions/spectrum.py as Story 2.4 left it (LF line ends).
SPECTRUM_SHA256 = "0492528f08ec6315829545d57e9e24eb16765503172db7034edaabfbaacd29c1"
REPORT_KEYS = {"name", "row", "threshold", "unit", "measured", "result", "note"}
STATIC_ROWS = ["spectrum-frequency", "spectrum-level", "spectral-component-level"]
COMPONENT_ROW = "spectral-component-level"

Row = namedtuple("Row", "center_hz low_hz high_hz level")

STATIC_SECONDS = 5.0
# Swept calibration: two whole cycles of a 10 s sweep.
SWEEP_SECONDS = 20.0
SWEEP_PERIOD_S = 10.0


def cc():
    assert TOOL.is_file(), f"missing {TOOL} (Story 3.1 cross-check tool)"
    return importlib.import_module("assertions.component_check")


def frequency_tol():
    r = table_row("spectrum-frequency")
    assert r.kind == "thresholds" and r.unit == "Hz", r
    return r.value


def level_tol():
    r = table_row("spectrum-level")
    assert r.kind == "thresholds" and r.unit == "dB", r
    return r.value


def component_db():
    r = table_row(COMPONENT_ROW)
    assert r.kind == "thresholds" and r.unit.startswith("dB"), r
    return r.value


def ratio(db):
    return 10.0 ** (db / 20.0)


def line(f, db):
    """A table row of a line that does not move."""
    return Row(f, f, f, ratio(db))


def tones(fs, spec, seconds=STATIC_SECONDS, scale=0.5):
    """A sum of sines at the given (Hz, dB) lines, the 0 dB line at amplitude `scale`."""
    t = np.arange(int(round(seconds * fs)), dtype=np.float64) / fs
    x = np.zeros_like(t)
    for i, (f, level) in enumerate(spec):
        x += scale * ratio(level) * np.sin(2.0 * math.pi * f * t + 0.37 * i + 0.1)
    return x


def swept(fs, f0, swing, amplitude, phase=0.0, seconds=SWEEP_SECONDS, period=SWEEP_PERIOD_S, theta=0.3):
    """A tone of constant amplitude at the frequency f0 + swing * sin(2 pi t / period + phase)."""
    t = np.arange(int(round(seconds * fs)), dtype=np.float64) / fs
    w = 2.0 * math.pi * t / period + phase
    return amplitude * np.sin(2.0 * math.pi * f0 * t - swing * period * (np.cos(w) - math.cos(phase)) + theta)


def by_row(reports):
    out = {}
    for r in reports:
        out.setdefault(r["row"], []).append(r)
    return out


def all_pass(reports):
    return all(r["result"] == "pass" for r in reports)


# The static table: (Hz, dB re the 450 Hz line). The side lines 6 Hz apart
# are the lines of a 450 Hz carrier amplitude-modulated at 6 Hz.
STATIC_LINES = [(450.0, 0.0), (444.0, -10.5), (456.0, -10.5), (438.0, -30.0), (462.0, -30.0),
                (250.0, -6.0), (1234.567, -20.0), (3000.3, -36.0)]


def static_table():
    return [line(f, db) for f, db in STATIC_LINES]


# ------------------------------------------------------------ source and rows


def test_the_spectrum_tool_is_unchanged():
    data = SPECTRUM_TOOL.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == SPECTRUM_SHA256, "Story 3.1 never changes spectrum.py"


def test_must_fail_a_changed_spectrum_tool_is_caught():
    data = SPECTRUM_TOOL.read_bytes().replace(b"\r\n", b"\n") + b"\n"
    assert hashlib.sha256(data).hexdigest() != SPECTRUM_SHA256


def test_tool_signatures():
    mod = cc()
    assert list(inspect.signature(mod.threshold_db).parameters) == []
    assert list(inspect.signature(mod.check_static).parameters) == ["name", "x", "fs", "table"]
    assert list(inspect.signature(mod.band_power_db).parameters) == ["x", "fs", "lo_hz", "hi_hz"]
    assert list(inspect.signature(mod.bands).parameters) == ["table", "resolution_hz"]
    assert list(inspect.signature(mod.check_bands).parameters) == ["name", "x", "fs", "table"]


def test_tool_imports_only_numpy_the_standard_library_and_the_assertions_package():
    assert TOOL.is_file(), f"missing {TOOL}"
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    allowed = ("numpy", "math", "cmath", "typing", "functools", "collections", "bisect", "itertools",
               "__future__")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] in allowed, a.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                top = (node.module or "").split(".")[0]
                assert top in allowed or top == "assertions", node.module
                if top == "assertions":
                    assert (node.module or "") in ("assertions", "assertions.spectrum"), node.module
            else:
                assert node.level == 1, ast.dump(node)
                assert (node.module or "") in ("", "spectrum"), node.module
                if not node.module:
                    for a in node.names:
                        assert a.name in ("row", "spectrum"), a.name
        if isinstance(node, (ast.Name, ast.Attribute, ast.FunctionDef, ast.ClassDef)):
            n = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else node.name
            low = n.lower()
            assert "recipe" not in low and low not in ("plan", "open"), f"the cross-check tool reads {n}"
            assert "tapdump" not in low and "arc_" not in low, n


def test_threshold_is_row_spectral_component_level_and_no_longer_pending():
    r = table_row(COMPONENT_ROW)
    assert r.pending == "", (COMPONENT_ROW, r.pending)
    assert r.value > 0.0, r
    assert cc().threshold_db() == r.value
    assert cc().threshold_db() == load_tables()[COMPONENT_ROW].value


# ------------------------------------------------------------ static check


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_static_check_passes_a_signal_that_has_exactly_the_table(fs):
    mod = cc()
    reports = mod.check_static("calibration", tones(fs, STATIC_LINES), fs, static_table())
    assert [r["row"] for r in reports] == STATIC_ROWS, reports
    for r in reports:
        assert set(r) == REPORT_KEYS, r
        assert r["name"] == "calibration", r
        row = table_row(r["row"])
        assert r["threshold"] == row.value and r["unit"] == row.unit, r
        assert r["result"] == "pass", r
    freq, level, count = reports
    assert 0.0 <= freq["measured"] < frequency_tol(), freq
    assert 0.0 <= level["measured"] < level_tol(), level
    assert count["measured"] == 0, count


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_static_check_does_not_depend_on_the_signal_scale_or_the_table_order(fs):
    mod = cc()
    table = static_table()
    for scale in (1.0, 0.01):
        assert all_pass(mod.check_static("scale", tones(fs, STATIC_LINES, scale=scale), fs, table)), scale
    assert all_pass(mod.check_static("order", tones(fs, STATIC_LINES), fs, table[::-1]))


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("sign", (1.0, -1.0))
def test_must_fail_a_line_moved_past_the_frequency_row(fs, sign):
    mod = cc()
    moved = [(f + sign * 2.0 * frequency_tol(), db) if f == 1234.567 else (f, db) for f, db in STATIC_LINES]
    freq, level, _ = mod.check_static("moved", tones(fs, moved), fs, static_table())
    assert freq["result"] == "fail", freq
    assert abs(freq["measured"] - 2.0 * frequency_tol()) < frequency_tol() / 10.0, freq
    assert level["result"] == "pass", level
    inside = [(f + sign * 0.5 * frequency_tol(), db) if f == 1234.567 else (f, db) for f, db in STATIC_LINES]
    assert all_pass(mod.check_static("inside", tones(fs, inside), fs, static_table()))


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("sign", (1.0, -1.0))
def test_must_fail_a_level_changed_past_the_level_row(fs, sign):
    mod = cc()
    for target in (444.0, 1234.567):
        changed = [(f, db + sign * 2.0 * level_tol()) if f == target else (f, db) for f, db in STATIC_LINES]
        freq, level, count = mod.check_static("changed", tones(fs, changed), fs, static_table())
        assert level["result"] == "fail", (target, level)
        assert abs(level["measured"] - 2.0 * level_tol()) < level_tol() / 10.0, level
        assert freq["result"] == "pass" and count["result"] == "pass", (target, freq, count)
        inside = [(f, db + sign * 0.5 * level_tol()) if f == target else (f, db) for f, db in STATIC_LINES]
        assert all_pass(mod.check_static("inside", tones(fs, inside), fs, static_table())), target


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_must_fail_a_measured_line_within_the_threshold_that_no_row_matches(fs):
    """A tone above the component threshold that the table lacks is counted; one under it is not."""
    mod = cc()
    L, tol = component_db(), level_tol()
    table = static_table()
    counted = STATIC_LINES + [(700.0, -(L - 4.0 * tol))]
    freq, level, count = mod.check_static("extra", tones(fs, counted), fs, table)
    assert count["result"] == "fail" and count["measured"] == 1, count
    assert freq["result"] == "pass" and level["result"] == "pass", (freq, level)
    # Two of them count two.
    two = counted + [(820.5, -6.0)]
    assert mod.check_static("two", tones(fs, two), fs, table)[2]["measured"] == 2
    # Under the threshold the tone is no component: not counted.
    under = STATIC_LINES + [(700.0, -(L + 4.0 * tol))]
    assert all_pass(mod.check_static("under", tones(fs, under), fs, table))
    # Within row spectrum-level of the threshold, on either side, it is exempt.
    for offset in (-0.5 * tol, 0.5 * tol):
        near = STATIC_LINES + [(700.0, -(L + offset))]
        assert all_pass(mod.check_static("near", tones(fs, near), fs, table)), offset


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_must_fail_a_table_row_dropped_or_never_measured(fs):
    mod = cc()
    x = tones(fs, STATIC_LINES)
    # The harness drops one side-frequency row: its measured line has no row.
    for dropped in (444.0, 462.0, 1234.567):
        table = [r for r in static_table() if r.center_hz != dropped]
        count = mod.check_static("dropped", x, fs, table)[2]
        assert count["result"] == "fail" and count["measured"] == 1, (dropped, count)
    # A table row whose line the signal does not have.
    table = static_table() + [line(700.0, -20.0)]
    reports = mod.check_static("unmeasured", x, fs, table)
    assert reports[2]["result"] == "fail" and reports[2]["measured"] >= 1, reports[2]
    assert not all_pass(reports)


def test_must_fail_silence_and_an_empty_table():
    """Silence is not evidence, and a real signal is never matched by an empty table."""
    mod = cc()
    fs = SAMPLE_RATES[0]
    silent = np.zeros(int(STATIC_SECONDS * fs))
    reports = mod.check_static("silence", silent, fs, static_table())
    assert [r["row"] for r in reports] == STATIC_ROWS, reports
    assert not any(r["result"] == "pass" for r in reports), reports
    reports = mod.check_static("empty table", tones(fs, STATIC_LINES), fs, [])
    assert [r["row"] for r in reports] == STATIC_ROWS, reports
    assert reports[2]["result"] == "fail", reports
    bad = tones(fs, STATIC_LINES)
    bad[100] = math.nan
    reports = mod.check_static("not finite", bad, fs, static_table())
    assert not any(r["result"] == "pass" for r in reports), reports


# ------------------------------------------------------------ band power


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_band_power_of_swept_tones_of_known_power(fs):
    """Two swept tones of amplitudes a and b: each band holds a^2 or b^2 of a^2 + b^2."""
    mod = cc()
    a, b = 0.5, 0.2
    x = swept(fs, 1000.0, 6.0, a) + swept(fs, 1500.0, 15.0, b, phase=1.0)
    total = a * a + b * b
    tol = level_tol()
    low = mod.band_power_db(x, fs, 990.0, 1010.0)
    high = mod.band_power_db(x, fs, 1480.0, 1520.0)
    assert abs(low - 10.0 * math.log10(a * a / total)) < tol / 10.0, low
    assert abs(high - 10.0 * math.log10(b * b / total)) < tol / 10.0, high
    # The whole spectrum is the reference; a band with no tone holds nearly nothing.
    assert abs(mod.band_power_db(x, fs, 0.0, fs / 2.0)) < tol / 10.0
    assert mod.band_power_db(x, fs, 2000.0, 3000.0) < -component_db()
    # The scale of the signal changes nothing.
    assert abs(mod.band_power_db(0.01 * x, fs, 990.0, 1010.0) - low) < tol / 100.0


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_band_power_of_static_tones_of_known_power(fs):
    mod = cc()
    x = tones(fs, [(450.0, 0.0), (444.0, -10.0), (456.0, -10.0), (250.0, -20.0)])
    total = 1.0 + 2.0 * ratio(-10.0) ** 2 + ratio(-20.0) ** 2
    tol = level_tol()
    for lo, hi, power in ((448.0, 452.0, 1.0), (442.0, 446.0, ratio(-10.0) ** 2),
                          (440.0, 460.0, 1.0 + 2.0 * ratio(-10.0) ** 2), (240.0, 260.0, ratio(-20.0) ** 2)):
        got = mod.band_power_db(x, fs, lo, hi)
        assert abs(got - 10.0 * math.log10(power / total)) < tol / 10.0, (lo, hi, got)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_a_sinusoidal_sweep_spends_half_its_power_on_each_side_of_its_center(fs):
    mod = cc()
    x = swept(fs, 1000.0, 20.0, 0.5)
    half = 10.0 * math.log10(0.5)
    for lo, hi in ((970.0, 1000.0), (1000.0, 1030.0)):
        assert abs(mod.band_power_db(x, fs, lo, hi) - half) < level_tol(), (lo, hi)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("sign", (1.0, -1.0))
def test_must_fail_band_power_reads_a_changed_amplitude(fs, sign):
    """A swept tone doctored by twice row spectrum-level moves its band's reading past the row."""
    mod = cc()
    a, b = 0.1, 0.5
    want = 10.0 * math.log10(a * a / (a * a + b * b))
    tol = level_tol()
    good = swept(fs, 1000.0, 6.0, a) + swept(fs, 1500.0, 15.0, b, phase=1.0)
    assert abs(mod.band_power_db(good, fs, 990.0, 1010.0) - want) < tol / 10.0
    doctored = swept(fs, 1000.0, 6.0, a * ratio(sign * 2.0 * tol)) + swept(fs, 1500.0, 15.0, b, phase=1.0)
    assert abs(mod.band_power_db(doctored, fs, 990.0, 1010.0) - want) > tol
    # A band that misses half the sweep reads half the power: past the row.
    assert abs(mod.band_power_db(good, fs, 1000.0, 1010.0) - want) > tol


# ------------------------------------------------------------ bands


def sorted_bands(mod, table, resolution_hz):
    out = sorted((float(lo), float(hi), float(p)) for lo, hi, p in mod.bands(table, resolution_hz))
    for lo, hi, _ in out:
        assert lo <= hi, out
    return out


def test_bands_widen_each_interval_and_merge_the_overlapping_ones():
    mod = cc()
    res = 0.25
    table = [
        Row(1000.0, 1000.0, 1000.0, 1.0),      # a line that does not move
        Row(1040.0, 1034.0, 1046.0, 0.3),      # overlaps the next interval
        Row(1050.0, 1044.0, 1056.0, 0.2),
        Row(960.0, 954.0, 966.0, 0.3),         # alone
        Row(1056.4, 1056.4, 1056.4, 0.1),      # 0.4 Hz above 1056: joined only through the widening
        Row(1060.0, 1056.8, 1063.0, 0.05),     # 0.4 Hz above 1056.4: joined to it by the widening too
        Row(1070.0, 1063.6, 1076.4, 0.04),     # 0.6 Hz above 1063: not reached by twice the widening
    ]
    got = sorted_bands(mod, table, res)
    want = [(954.0 - res, 966.0 + res, 0.3 ** 2),
            (1000.0 - res, 1000.0 + res, 1.0),
            (1034.0 - res, 1063.0 + res, 0.3 ** 2 + 0.2 ** 2 + 0.1 ** 2 + 0.05 ** 2),
            (1063.6 - res, 1076.4 + res, 0.04 ** 2)]
    assert len(got) == len(want), got
    for (lo, hi, _), (want_lo, want_hi, _) in zip(got, want):
        assert math.isclose(lo, want_lo, rel_tol=0.0, abs_tol=1e-9), (lo, want_lo)
        assert math.isclose(hi, want_hi, rel_tol=0.0, abs_tol=1e-9), (hi, want_hi)
    # Expected powers: each band's sum of level^2, all against one reference,
    # so the difference of two bands is the ratio of their sums.
    carrier = got[1][2]
    for (_, _, power_db), (_, _, power) in zip(got, want):
        assert math.isclose(power_db - carrier, 10.0 * math.log10(power), rel_tol=0.0, abs_tol=1e-9), power_db
    # The table order changes nothing.
    again = sorted_bands(mod, table[::-1], res)
    assert len(again) == len(got), again
    for one, other in zip(again, got):
        assert all(math.isclose(u, v, rel_tol=0.0, abs_tol=1e-9) for u, v in zip(one, other)), (one, other)


def test_must_fail_bands_follow_the_resolution_and_the_table():
    mod = cc()
    table = [Row(1000.0, 1000.0, 1000.0, 1.0), Row(1010.0, 1004.0, 1016.0, 0.3),
             Row(1020.0, 1016.5, 1023.5, 0.2)]
    # 0.5 Hz apart: separate at a 0.2 Hz widening, one band at 0.3 Hz.
    assert len(sorted_bands(mod, table, 0.2)) == 3
    merged = sorted_bands(mod, table, 0.3)
    assert len(merged) == 2
    # A dropped row drops its band, or its share of a merged band.
    assert len(sorted_bands(mod, table[:2], 0.2)) == 2
    less = sorted_bands(mod, table[:2], 0.3)
    drop = (merged[1][2] - merged[0][2]) - (less[1][2] - less[0][2])
    assert math.isclose(drop, 10.0 * math.log10((0.3 ** 2 + 0.2 ** 2) / 0.3 ** 2), rel_tol=0.0, abs_tol=1e-9)


# ------------------------------------------------------------ band check

# A 1000 Hz tone that does not move and four swept lines about it, as a
# carrier whose amplitude modulation rate follows a cycle has: lines at
# 1000 +- (40 + 6 sin) Hz and 1000 +- (80 + 12 sin) Hz. (center offset Hz,
# swing Hz, level re the 1000 Hz line.)
SWEPT_LINES = [(-40.0, 6.0, 0.1), (40.0, 6.0, 0.1), (-80.0, 12.0, 0.05), (80.0, 12.0, 0.05)]
SWEEP_CARRIER_HZ = 1000.0


def sweep_table():
    table = [Row(SWEEP_CARRIER_HZ, SWEEP_CARRIER_HZ, SWEEP_CARRIER_HZ, 1.0)]
    for offset, swing, level in SWEPT_LINES:
        c = SWEEP_CARRIER_HZ + offset
        table.append(Row(c, c - swing, c + swing, level))
    return table


def sweep_signal(fs, gains=None, scale=0.5):
    """The signal of sweep_table(); gains scales the swept lines by index (the harness's doctoring)."""
    t = np.arange(int(round(SWEEP_SECONDS * fs)), dtype=np.float64) / fs
    x = scale * np.sin(2.0 * math.pi * SWEEP_CARRIER_HZ * t + 0.2)
    for i, (offset, swing, level) in enumerate(SWEPT_LINES):
        gain = 1.0 if gains is None else gains.get(i, 1.0)
        sign = 1.0 if offset > 0 else -1.0
        x += swept(fs, SWEEP_CARRIER_HZ + offset, sign * swing, scale * level * gain, theta=0.5 + i)
    return x


def band_reports(mod, name, x, fs, table):
    reports = mod.check_bands(name, x, fs, table)
    rows = by_row(reports)
    assert set(rows) == {"spectrum-level", COMPONENT_ROW}, reports
    for r in reports:
        assert set(r) == REPORT_KEYS, r
        row = table_row(r["row"])
        assert r["threshold"] == row.value and r["unit"] == row.unit, r
        assert r["result"] in ("pass", "fail"), r
    return rows


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_band_check_passes_swept_lines_of_the_table_powers(fs):
    mod = cc()
    rows = band_reports(mod, "swept", sweep_signal(fs), fs, sweep_table())
    for reports in rows.values():
        assert all_pass(reports), reports
    for r in rows["spectrum-level"]:
        assert 0.0 <= r["measured"] < level_tol(), r
    for r in rows[COMPONENT_ROW]:
        assert r["measured"] == 0, r
    # The scale of the signal changes nothing.
    scaled = band_reports(mod, "scaled", sweep_signal(fs, scale=0.01), fs, sweep_table())
    assert all(all_pass(reports) for reports in scaled.values()), scaled


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("sign", (1.0, -1.0))
def test_must_fail_band_check_a_swept_line_of_the_wrong_power(fs, sign):
    """One swept line doctored by four times row spectrum-level: its band power is off."""
    mod = cc()
    gain = ratio(sign * 4.0 * level_tol())
    rows = band_reports(mod, "power", sweep_signal(fs, gains={1: gain}), fs, sweep_table())
    assert not all_pass(rows["spectrum-level"]), rows
    worst = max(r["measured"] for r in rows["spectrum-level"])
    assert worst > level_tol(), rows
    # Doctored by a quarter of the row it still passes.
    rows = band_reports(mod, "inside", sweep_signal(fs, gains={1: ratio(sign * 0.25 * level_tol())}), fs,
                        sweep_table())
    assert all(all_pass(reports) for reports in rows.values()), rows


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_must_fail_band_check_a_line_outside_every_band(fs):
    mod = cc()
    L, tol = component_db(), level_tol()
    t = np.arange(int(round(SWEEP_SECONDS * fs)), dtype=np.float64) / fs
    extra = 0.5 * ratio(-(L - 4.0 * tol)) * np.sin(2.0 * math.pi * 1200.0 * t)
    rows = band_reports(mod, "outside", sweep_signal(fs) + extra, fs, sweep_table())
    assert not all_pass(rows[COMPONENT_ROW]), rows
    assert max(r["measured"] for r in rows[COMPONENT_ROW]) >= 1, rows
    assert all_pass(rows["spectrum-level"]), rows
    # The same tone under the threshold is no component.
    quiet = 0.5 * ratio(-(L + 4.0 * tol)) * np.sin(2.0 * math.pi * 1200.0 * t)
    rows = band_reports(mod, "under", sweep_signal(fs) + quiet, fs, sweep_table())
    assert all(all_pass(reports) for reports in rows.values()), rows


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_must_fail_band_check_a_table_with_a_row_dropped_or_a_narrowed_interval(fs):
    mod = cc()
    x = sweep_signal(fs)
    table = sweep_table()
    # The harness drops the row of one swept side line: its power lies outside every band.
    dropped = [r for r in table if r.center_hz != SWEEP_CARRIER_HZ + 40.0]
    rows = band_reports(mod, "dropped", x, fs, dropped)
    assert not all(all_pass(reports) for reports in rows.values()), rows
    # An interval half as wide as the sweep: the band holds too little power.
    narrowed = [Row(r.center_hz, r.center_hz - 3.0, r.center_hz + 3.0, r.level)
                if r.center_hz == SWEEP_CARRIER_HZ + 40.0 else r for r in table]
    rows = band_reports(mod, "narrowed", x, fs, narrowed)
    assert not all(all_pass(reports) for reports in rows.values()), rows
    # A row whose line the signal does not have: an expected band with no power.
    added = table + [Row(1300.0, 1295.0, 1305.0, 0.1)]
    rows = band_reports(mod, "added", x, fs, added)
    assert not all_pass(rows["spectrum-level"]), rows


def test_must_fail_band_check_silence():
    mod = cc()
    fs = SAMPLE_RATES[0]
    reports = mod.check_bands("silence", np.zeros(int(SWEEP_SECONDS * fs)), fs, sweep_table())
    assert reports and not all_pass(reports), reports
    assert not all_pass([r for r in reports if r["row"] == "spectrum-level"]), reports
