"""Spectrum tool (Story 2.4; reused unchanged by Story 3.1).

Finds the spectral lines of one tap: their frequencies and levels relative
to the strongest line. It reads one channel of samples and the sample rate
only, never an engine plan or any engine internal. Calibrated on
Python-synthesized multi-tone signals of known lines and levels first
(tests/python/test_spectrum_tool.py); every check reads rows
`spectrum-frequency` (Hz) and `spectrum-level` (dB) through `row` on every
call.

- PAD_FACTOR: the windowed signal is zero-padded to the smallest power of two
  at least PAD_FACTOR times its length, so the FFT samples each line's main
  lobe at PAD_FACTOR or more points per bin of the unpadded length.
- FLOOR_DB: a local maximum below FLOOR_DB re the strongest line is not a
  line. It sits above the window's highest sidelobe (about -92 dB), so no
  sidelobe of a line is read as a line of its own.
- RESOLUTION_BINS: lines closer than RESOLUTION_BINS / T Hz (T the signal
  length in seconds, the window's main lobe width) are not resolved.
- lines(x, fs, band=None): every spectral line (frequency_hz, level_db),
  sorted by frequency, with band[0] <= frequency_hz <= band[1] (every line
  when band is None). Method: the 4-term Blackman-Harris window over the
  whole signal, the zero-padded real FFT, every local maximum of the
  magnitude at least FLOOR_DB re the strongest, each refined by a parabola
  through the dB magnitudes of the peak bin and its two neighbours (the
  vertex gives the frequency and the level). level_db is relative to the
  strongest line of the whole spectrum, 0 to fs / 2 (0 dB), so a band never
  moves the reference. ValueError for anything but one channel of at least
  2 finite samples, or a band outside [0, fs / 2] or with band[0] > band[1].
- worst_line(x, fs, lo_hz, hi_hz=None): the level_db of the loudest line in
  [lo_hz, hi_hz] (hi_hz None means fs / 2); -inf when there is none.
- match(found, expected): each expected (frequency_hz, level_db) paired with
  the found line nearest in frequency; returns (worst |frequency error| in
  Hz, worst |level error| in dB), or None when nothing was found.
- check(name, x, fs, band, expected): two report assertion dicts (Story
  1.4), rows `spectrum-frequency` then `spectrum-level`. measured is the
  worst error over the expected lines; each passes when strictly below its
  row. A non-finite or unusable input, or no line found in the band, fails
  both with a note and measured None.

NumPy and the standard library only.
"""

from __future__ import annotations

import math

import numpy as np

from . import row

FREQUENCY_ROW = "spectrum-frequency"
LEVEL_ROW = "spectrum-level"
PAD_FACTOR = 8
FLOOR_DB = -90.0
RESOLUTION_BINS = 8

_BH = (0.35875, 0.48829, 0.14128, 0.01168)


def _window(n) -> np.ndarray:
    k = np.arange(n, dtype=np.float64)
    x = 2.0 * math.pi * k / n
    return _BH[0] - _BH[1] * np.cos(x) + _BH[2] * np.cos(2.0 * x) - _BH[3] * np.cos(3.0 * x)


def _samples(x) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    if a.ndim != 1 or a.size < 2:
        raise ValueError(f"need one channel of at least 2 samples, got shape {a.shape}")
    if not np.all(np.isfinite(a)):
        raise ValueError("not finite")
    return a


def _band(band, fs):
    nyquist = float(fs) / 2.0
    if band is None:
        return 0.0, nyquist
    lo, hi = float(band[0]), float(band[1])
    if not (0.0 <= lo <= hi <= nyquist):
        raise ValueError(f"band {band!r} is not inside [0, {nyquist}] in increasing order")
    return lo, hi


def _all_lines(x, fs):
    """Every line of the whole spectrum as (frequency_hz, level_db re the strongest)."""
    a = _samples(x)
    fs = float(fs)
    if not (math.isfinite(fs) and fs > 0.0):
        raise ValueError(f"fs must be positive and finite, got {fs!r}")
    size = 1
    while size < PAD_FACTOR * a.size:
        size *= 2
    mag = np.abs(np.fft.rfft(a * _window(a.size), n=size))
    peak = float(np.max(mag))
    if not peak > 0.0:
        return []
    with np.errstate(divide="ignore"):
        db = 20.0 * np.log10(mag / peak)
    floor = FLOOR_DB
    inner = db[1:-1]
    is_max = (inner >= db[:-2]) & (inner > db[2:]) & (inner >= floor)
    idx = np.nonzero(is_max)[0] + 1
    bin_hz = fs / size
    found = []
    for k in idx:
        y0, y1, y2 = float(db[k - 1]), float(db[k]), float(db[k + 1])
        denom = y0 - 2.0 * y1 + y2
        delta = 0.5 * (y0 - y2) / denom if denom < 0.0 else 0.0
        level = y1 - 0.25 * (y0 - y2) * delta
        found.append(((k + delta) * bin_hz, level))
    # Edge bins: a line at DC or at fs / 2 has no neighbour on one side.
    for k in (0, mag.size - 1):
        nb = 1 if k == 0 else mag.size - 2
        if db[k] >= floor and db[k] > db[nb]:
            found.append((k * bin_hz, float(db[k])))
    if not found:
        return []
    top = max(level for _, level in found)
    return sorted((f, level - top) for f, level in found)


def lines(x, fs, band=None) -> list:
    lo, hi = _band(band, fs)
    return [(f, level) for f, level in _all_lines(x, fs) if lo <= f <= hi]


def worst_line(x, fs, lo_hz, hi_hz=None) -> float:
    found = lines(x, fs, (lo_hz, float(fs) / 2.0 if hi_hz is None else hi_hz))
    if not found:
        return -math.inf
    return max(level for _, level in found)


def match(found, expected):
    if not found:
        return None
    freqs = np.asarray([f for f, _ in found], dtype=np.float64)
    worst_f = worst_l = 0.0
    for f, level in expected:
        k = int(np.argmin(np.abs(freqs - float(f))))
        worst_f = max(worst_f, abs(float(found[k][0]) - float(f)))
        worst_l = max(worst_l, abs(float(found[k][1]) - float(level)))
    return worst_f, worst_l


def check(name, x, fs, band, expected) -> list:
    results = []
    for row_id in (FREQUENCY_ROW, LEVEL_ROW):
        r = row(row_id)
        results.append({"name": name, "row": row_id, "threshold": r.value, "unit": r.unit,
                        "measured": None, "result": "fail", "note": ""})
    try:
        found = lines(x, fs, band)
    except ValueError as exc:
        for res in results:
            res["note"] = str(exc)
        return results
    worst = match(found, expected)
    if worst is None:
        for res in results:
            res["note"] = "no line found in the band"
        return results
    for res, value in zip(results, worst):
        res["measured"] = float(value)
        res["result"] = "pass" if value < res["threshold"] else "fail"
    return results
