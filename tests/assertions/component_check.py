"""Component cross-check tool (Story 3.1; docs/signal-spec.md, Components, Cross-check).

Holds the measured spectrum of one layer tap to that layer's rows of the
component table in one ear. It reads one channel of samples, the sample
rate, and the table rows only. Every check reads its rows through `row` on
every call: `spectral-component-level` (the threshold L, dB below the tap's
strongest line), `spectrum-frequency` and `spectrum-level` (the spectrum
tool's rows, Story 2.4), and range row `rate-cycle-period` (the period P of
every rate cycle). Lines are found by the spectrum tool
(tests/assertions/spectrum.py, unchanged). Calibrated on Python-synthesized
static and swept tones first (tests/python/test_component_check_tool.py).

`table` is a list of rows with the attributes `center_hz`, `low_hz`,
`high_hz`, and `level` (a linear ratio re the layer's carrier line).

- threshold_db(): the value of row `spectral-component-level`.
- check_static(name, x, fs, table): for a tap whose lines do not move. Three
  report assertion dicts (the shape `spectrum.check` returns), rows
  `spectrum-frequency`, `spectrum-level`, `spectral-component-level`. The
  first two hold the worst error over every table row against the nearest
  measured line (`spectrum.match`; levels compared in dB, 20 * log10(level)).
  The third holds the count of unmatched lines: a measured line at or above
  the threshold re the tap's strongest line with no table row within half
  the tool's resolution (`8 * fs / len(x)` Hz, the window's main lobe), plus
  a table row with no measured line within it, plus every extra table row
  that claims a measured line another row already claims (each row claims
  the nearest measured line within that radius, so matching is one to one:
  a duplicated row, or two rows on one line, is a mismatch). A line or a row whose level is
  within row `spectrum-level` of the threshold is exempt from the count (it
  may be in or out). It passes only at count 0. A non-finite or silent tap,
  or an empty table, fails all three with a note.
- band_power_db(x, fs, lo_hz, hi_hz): the power in [lo_hz, hi_hz] re the
  tap's total power, in dB, from the unwindowed real FFT of the whole tap (a
  rate-cycle tap holds whole cycles of every rate, so its lines fall on FFT
  bins); -inf for a band with no power.
- bands(table, resolution_hz): each row's interval [low_hz, high_hz]
  widened by resolution_hz at each end, overlapping intervals merged; a list
  of (lo_hz, hi_hz, expected_power_db) in ascending frequency, the expected
  power 10 * log10 of the band's sum of level^2 over the whole table's sum,
  so it reads on the scale of band_power_db.
- sweep_edge_hz(half_width_hz, period_s): the sweep edge allowance. A row
  swept sinusoidally with half width A over period P sounds as the Bessel
  line spectrum of modulation index beta = A * P: lines 1 / P apart with
  amplitudes |J_n(beta)|, which reach past A near the turning points. The
  allowance is the smallest d >= 0 such that every line with n > (A + d) * P
  is below the threshold re that row's strongest line: d = n_last / P - A,
  n_last the largest |n| with |J_n(beta)| at least 10^(-L/20) of the
  largest. J_n(beta) comes in closed form from the FFT of exp(i beta sin t)
  over one period, sampled finely enough that no line aliases. 0 for a
  static row (A = 0). It depends on A, P, and L only, never on a fixture.
- check_bands(name, x, fs, table): for a tap whose lines move along rate
  cycles over a whole number of cycles. Each row is widened by its sweep
  edge (A from its interval, P from row rate-cycle-period), then the rows go
  through bands() with the tool's resolution, `8 * fs / len(x)` Hz. One
  `spectrum-level` report per band (measured: |band_power_db - expected| in
  dB) and one `spectral-component-level` report (measured: the count of
  measured lines at or above the threshold re the tap's strongest line
  outside every band; a line within row `spectrum-level` of the threshold is
  exempt). A swept line keeps its power, so a band is judged by its power
  and never by peak height.
  Limit: a band check cannot see a missing weak row inside a merged band
  whose loss changes the band's power by less than row `spectrum-level`
  (a 0.01 row in a band of power 1 moves it by 0.0004 dB). Per-row presence
  is carried by check_static on the static fixtures, which share every
  shape's line model with the rate-cycle fixtures; the band check carries
  the intervals and the total power.

NumPy and the standard library only, plus `row` and the spectrum tool.
"""

from __future__ import annotations

import functools
import math

import numpy as np

from . import row, spectrum

COMPONENT_ROW = "spectral-component-level"
FREQUENCY_ROW = "spectrum-frequency"
LEVEL_ROW = "spectrum-level"
PERIOD_ROW = "rate-cycle-period"
MAIN_LOBE_BINS = 8.0  # the spectrum tool's window main lobe, in bins of the unpadded length


def threshold_db() -> float:
    return row(COMPONENT_ROW).value


def _report(name, row_id):
    r = row(row_id)
    return {"name": name, "row": row_id, "threshold": r.value, "unit": r.unit,
            "measured": None, "result": "fail", "note": ""}


def _fail_all(reports, note):
    for r in reports:
        r["note"] = note
        r["measured"] = None
        r["result"] = "fail"
    return reports


def _resolution_hz(n, fs):
    return MAIN_LOBE_BINS * float(fs) / float(n)


def _db(level):
    return 20.0 * math.log10(float(level)) if level > 0.0 else -math.inf


def check_static(name, x, fs, table) -> list:
    reports = [_report(name, FREQUENCY_ROW), _report(name, LEVEL_ROW), _report(name, COMPONENT_ROW)]
    threshold = threshold_db()
    level_tol = row(LEVEL_ROW).value
    try:
        found = spectrum.lines(x, fs)
    except ValueError as exc:
        return _fail_all(reports, str(exc))
    if not found:
        return _fail_all(reports, "no line found (silence)")
    rows = list(table)
    if not rows:
        return _fail_all(reports, "no table rows")
    expected = [(float(r.center_hz), _db(r.level)) for r in rows]
    worst_f, worst_l = spectrum.match(found, expected)
    for report, value in zip(reports[:2], (worst_f, worst_l)):
        report["measured"] = float(value)
        report["result"] = "pass" if value < report["threshold"] else "fail"
    radius = _resolution_hz(np.asarray(x).size, fs) / 2.0
    centers = np.asarray([f for f, _ in expected], dtype=np.float64)
    freqs = np.asarray([f for f, _ in found], dtype=np.float64)
    count = 0
    for f, level in found:
        if level < -threshold or abs(level + threshold) <= level_tol:
            continue
        if not np.any(np.abs(centers - f) <= radius):
            count += 1
    claims = {}
    for f, level in expected:
        distance = np.abs(freqs - f)
        k = int(np.argmin(distance))
        if distance[k] <= radius:
            claims[k] = claims.get(k, 0) + 1
        elif abs(level + threshold) > level_tol:
            count += 1
    count += sum(c - 1 for c in claims.values())
    reports[2]["measured"] = count
    reports[2]["result"] = "pass" if count == 0 else "fail"
    return reports


def _power(x, fs):
    """(bin frequencies, one-sided power per bin) of the unwindowed real FFT."""
    a = np.asarray(x, dtype=np.float64)
    if a.ndim != 1 or a.size < 2:
        raise ValueError(f"need one channel of at least 2 samples, got shape {a.shape}")
    if not np.all(np.isfinite(a)):
        raise ValueError("not finite")
    spec = np.fft.rfft(a)
    p = spec.real * spec.real + spec.imag * spec.imag
    p[1:] *= 2.0
    if a.size % 2 == 0:
        p[-1] /= 2.0
    return np.fft.rfftfreq(a.size, d=1.0 / float(fs)), p


def _band_db(freqs, power, total, lo_hz, hi_hz):
    inside = float(np.sum(power[(freqs >= lo_hz) & (freqs <= hi_hz)]))
    if not total > 0.0:
        return math.nan
    return 10.0 * math.log10(inside / total) if inside > 0.0 else -math.inf


def band_power_db(x, fs, lo_hz, hi_hz) -> float:
    freqs, power = _power(x, fs)
    return _band_db(freqs, power, float(np.sum(power)), float(lo_hz), float(hi_hz))


def bands(table, resolution_hz) -> list:
    spans = sorted((float(r.low_hz) - resolution_hz, float(r.high_hz) + resolution_hz, float(r.level) ** 2)
                   for r in table)
    total = sum(p for _, _, p in spans)
    merged = []
    for lo, hi, p in spans:
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
            merged[-1][2] += p
        else:
            merged.append([lo, hi, p])
    return [(lo, hi, 10.0 * math.log10(p / total) if p > 0.0 else -math.inf) for lo, hi, p in merged]


@functools.lru_cache(maxsize=512)
def _sweep_edge(half_width_hz, period_s, threshold):
    beta = half_width_hz * period_s
    size = 64
    while size < 4.0 * (beta + 64.0):
        size *= 2
    t = 2.0 * math.pi * np.arange(size, dtype=np.float64) / size
    j = np.abs(np.fft.fft(np.exp(1j * beta * np.sin(t)))) / size  # |J_n(beta)|, n in FFT order
    n = np.fft.fftfreq(size, d=1.0 / size)
    strong = np.abs(n[j >= 10.0 ** (-threshold / 20.0) * float(np.max(j))])
    return max(0.0, float(np.max(strong)) / period_s - half_width_hz)


def sweep_edge_hz(half_width_hz, period_s) -> float:
    half_width_hz, period_s = float(half_width_hz), float(period_s)
    if not half_width_hz > 0.0:
        return 0.0
    return _sweep_edge(half_width_hz, period_s, threshold_db())


class _Row:
    __slots__ = ("center_hz", "low_hz", "high_hz", "level")

    def __init__(self, center_hz, low_hz, high_hz, level):
        self.center_hz, self.low_hz, self.high_hz, self.level = center_hz, low_hz, high_hz, level


def check_bands(name, x, fs, table) -> list:
    threshold = threshold_db()
    level_tol = row(LEVEL_ROW).value
    period = row(PERIOD_ROW).min
    rows = list(table)
    try:
        freqs, power = _power(x, fs)
        found = spectrum.lines(x, fs)
    except ValueError as exc:
        return _fail_all([_report(name, LEVEL_ROW), _report(name, COMPONENT_ROW)], str(exc))
    total = float(np.sum(power))
    if not rows or not found or not total > 0.0:
        note = "no table rows" if not rows else "no line found (silence)"
        return _fail_all([_report(name, LEVEL_ROW), _report(name, COMPONENT_ROW)], note)
    widened = []
    for r in rows:
        low, high = float(r.low_hz), float(r.high_hz)
        # One period for every row: row rate-cycle-period is a single value, so a row swept by two
        # cycles is one sinusoid of that period.
        edge = sweep_edge_hz((high - low) / 2.0, period)
        widened.append(_Row(float(r.center_hz), max(0.0, low - edge), high + edge, float(r.level)))
    resolution = _resolution_hz(np.asarray(x).size, fs)
    reports = []
    merged = bands(widened, resolution)
    for lo, hi, expected in merged:
        report = _report(f"{name} band {lo:.3f} to {hi:.3f} Hz", LEVEL_ROW)
        measured = _band_db(freqs, power, total, lo, hi)
        error = abs(measured - expected) if math.isfinite(measured) else math.inf
        report["measured"] = error
        report["result"] = "pass" if error < report["threshold"] else "fail"
        reports.append(report)
    count = 0
    for f, level in found:
        if level < -threshold or abs(level + threshold) <= level_tol:
            continue
        if not any(lo <= f <= hi for lo, hi, _ in merged):
            count += 1
    report = _report(f"{name} lines outside the bands", COMPONENT_ROW)
    report["measured"] = count
    report["result"] = "pass" if count == 0 else "fail"
    reports.append(report)
    return reports
