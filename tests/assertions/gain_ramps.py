"""Ramp tool (Story 4.4; docs/signal-spec.md, Gain ramps, Ramp tool).

Measures a gain schedule from a render: a layer's gain is its after-gain
tap over its before-gain tap; the master gain is the output over the join
times the loudness gain. Calibrated on Python-synthesized signals first
(tests/python/test_gain_ramp_tool.py).

- HOLD_TOL: an estimate within this of a value (gain units) is at that value.
- MIN_DIVISOR: samples whose before-gain value is smaller in magnitude are
  not read (the zero crossings of a carrier).
- HOLD_S: a value is held when every valid estimate in the next
  round(HOLD_S * fs) frames (or to the end of the signal) is within HOLD_TOL
  of it.
- estimate(before, after): one channel, float64, after / before, NaN where
  |before| < MIN_DIVISOR.
- changes(est, fs): every completed change in time order, as {"start": the
  last frame at the old held value, "end": the first frame of the new held
  value, "from", "to", "frames": end - start}. A change is measured only
  between two held values: a signal that starts inside a change (a window
  that opens mid-ramp, or a ramp at the very first frames of a session,
  where the before-gain carrier is 0) reads from its first held value, and
  a change still running at the signal end is not completed, so neither is
  counted. A change no larger than the engine sine error bound (row
  sine-error, -120 dBFS, 1e-6 as a gain) is not a gain change: the engine
  ramp starts and ends about 2.8e-8 of its height off its end values (the
  engine cosine at 0 and pi is sine(2^62), not 1; signal spec, Gain ramps,
  Law), so a long ramp creeps within HOLD_TOL of a value 2.8e-8 short of
  `to` and then steps onto it; that step is read as part of the hold.
- check(name, before, after, fs): the report assertion shape (Story 1.4)
  against row gain-ramp-min: measured the shortest completed change in ms
  (None when there is none, note "no change"), pass when every change lasts
  at least the row, inclusive; a NaN or infinite input fails with note
  "not finite" and measured None.

NumPy and the standard library only.
"""

from __future__ import annotations

import numpy as np

from . import row

ROW = "gain-ramp-min"
FLOOR_ROW = "sine-error"
HOLD_TOL = 1e-9
MIN_DIVISOR = 2.0 ** -30
HOLD_S = 0.010


def estimate(before, after) -> np.ndarray:
    b = np.asarray(before, dtype=np.float64)
    a = np.asarray(after, dtype=np.float64)
    if b.ndim != 1 or a.shape != b.shape:
        raise ValueError(f"need two channels of the same 1-D shape, got {b.shape} and {a.shape}")
    out = np.full(b.shape, np.nan, dtype=np.float64)
    ok = np.abs(b) >= MIN_DIVISOR
    out[ok] = a[ok] / b[ok]
    return out


def _forward_window(x, width, op, fill):
    """op over x[j:j + width] for every j (cut at the end), by block prefix and suffix scans."""
    n = x.size
    if n == 0:
        return x.copy()
    blocks = -(-(n + width) // width)
    padded = np.full(blocks * width, fill, dtype=np.float64)
    padded[:n] = x
    grid = padded.reshape(blocks, width)
    prefix = op.accumulate(grid, axis=1).reshape(-1)
    suffix = op.accumulate(grid[:, ::-1], axis=1)[:, ::-1].reshape(-1)
    j = np.arange(n)
    return op(suffix[j], prefix[j + width - 1])


def _held(est, fs):
    valid = ~np.isnan(est)
    width = max(1, int(round(HOLD_S * fs)))
    hi = _forward_window(np.where(valid, est, -np.inf), width, np.maximum, -np.inf)
    lo = _forward_window(np.where(valid, est, np.inf), width, np.minimum, np.inf)
    with np.errstate(invalid="ignore"):
        return valid & (hi - est <= HOLD_TOL) & (est - lo <= HOLD_TOL), valid


def _floor():
    """The smallest change counted: the engine sine error bound (row sine-error) as a linear gain."""
    r = row(FLOOR_ROW)
    if r.unit != "dBFS":
        raise ValueError(f"row {FLOOR_ROW} unit is {r.unit}, expected dBFS")
    return 10.0 ** (r.value / 20.0)


def changes(est, fs) -> list:
    e = np.asarray(est, dtype=np.float64)
    held, valid = _held(e, fs)
    held_at = np.flatnonzero(held)
    valid_at = np.flatnonzero(valid)
    out = []
    if held_at.size == 0:
        return out
    width = max(1, int(round(HOLD_S * fs)))
    floor = _floor()

    def reference(at):
        """The held value the next change is judged from: the last valid
        estimate of the hold window that starts at `at` (within HOLD_TOL of
        e[at] by the hold rule, and nearest the value a converging ramp ends
        on, so a ramp whose end creeps within HOLD_TOL is not counted twice)."""
        k = np.searchsorted(valid_at, at + width) - 1
        return float(e[int(valid_at[k])])

    pos = int(held_at[0])
    value = reference(pos)
    while True:
        rest = e[pos + 1:]
        with np.errstate(invalid="ignore"):
            moved = np.flatnonzero(np.abs(rest - value) > HOLD_TOL)
        if moved.size == 0:
            return out
        q = pos + 1 + int(moved[0])
        start = int(valid_at[np.searchsorted(valid_at, q) - 1])
        k = np.searchsorted(held_at, q)
        if k >= held_at.size:
            return out
        end = int(held_at[k])
        if abs(float(e[end]) - value) > floor:
            out.append({"start": start, "end": end, "from": value, "to": float(e[end]), "frames": end - start})
        pos, value = end, reference(end)


def check(name, before, after, fs) -> dict:
    r = row(ROW)
    result = {"name": name, "row": ROW, "threshold": r.value, "unit": r.unit, "measured": None,
              "result": "fail", "note": ""}
    b = np.asarray(before, dtype=np.float64)
    a = np.asarray(after, dtype=np.float64)
    if not (np.all(np.isfinite(b)) and np.all(np.isfinite(a))):
        result["note"] = "not finite"
        return result
    found = changes(estimate(b, a), fs)
    if not found:
        result["result"] = "pass"
        result["note"] = "no change"
        return result
    shortest = min(c["frames"] for c in found)
    result["measured"] = 1000.0 * shortest / fs
    result["result"] = "pass" if result["measured"] >= r.value else "fail"
    return result
