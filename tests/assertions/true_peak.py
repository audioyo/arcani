"""True-peak meter (Story 4.3): ITU-R BS.1770-5 Annex 2, 4x oversampling.

Implements docs/signal-spec.md, True peak, on its own (the command-line
meter in cli/true_peak.cpp is the second meter). Calibrated on EBU Tech 3341
v4.0 cases 15 to 19 and closed-form fs/4 sines, synthesized in the harness
(tests/python/test_true_peak_tool.py), before it judges an engine render.

- PHASES: the 48 coefficients Annex 2 prints, as integers n_p[k] (each
  coefficient is n_p[k] * 2^-13), phase 0 to 3, taps in printed order.
- true_peak(x24, fs): TP, the linear true peak of the 24-bit integers x24
  (shape (frames, 2), or (frames,) for one channel). Per channel the full
  convolution of the int64 samples with each phase's integers (zero state at
  the start, the 11 trailing outputs included), max |.| over phases and
  channels, then one division by 2^36: exact, so it equals the command-line
  meter bit for bit. ValueError on a non-integer dtype, another shape, or a
  value outside [-2^23, 2^23 - 1]. No frames gives 0.0. The reading does not
  depend on fs (True peak, Filter).
- check_true_peak(x24, fs): the report assertion shape (Story 1.4) against
  row true-peak: measured 20 log10(TP) in dBTP, pass when at or below the
  row; TP = 0 gives measured None, pass, note "silent".

NumPy and the standard library only.
"""

from __future__ import annotations

import math

import numpy as np

from . import row

CEILING_ROW = "true-peak"

# docs/signal-spec.md, True peak, Vectors: true-peak filter (printed * 2^13).
PHASES = np.array([
    [14, 90, -161, 272, -487, 1125, 7964, -838, 390, -218, 122, -68],
    [-239, 240, -424, 730, -1364, 3810, 6388, -1641, 832, -477, 271, -155],
    [-155, 271, -477, 832, -1641, 6388, 3810, -1364, 730, -424, 240, -239],
    [-68, 122, -218, 390, -838, 7964, 1125, -487, 272, -161, 90, 14],
], dtype=np.int64)
SCALE = float(1 << 36)          # 2^13 (coefficients) times 2^23 (samples)
V_MIN, V_MAX = -(1 << 23), (1 << 23) - 1


def _channels(x24):
    x = np.asarray(x24)
    if not np.issubdtype(x.dtype, np.integer):
        raise ValueError(f"true peak: samples must be integers, not {x.dtype}")
    if x.ndim == 1:
        x = x[:, None]
    elif x.ndim != 2 or x.shape[1] not in (1, 2):
        raise ValueError(f"true peak: shape {x.shape} is not (frames, 2) or (frames,)")
    x = x.astype(np.int64)
    if x.size and (int(x.min()) < V_MIN or int(x.max()) > V_MAX):
        raise ValueError("true peak: a sample is outside the 24-bit range")
    return x


def true_peak(x24, fs) -> float:
    x = _channels(x24)
    if x.shape[0] == 0:
        return 0.0
    best = 0
    for c in range(x.shape[1]):
        for p in range(PHASES.shape[0]):
            y = np.convolve(x[:, c], PHASES[p])          # full: frames + 11 outputs
            best = max(best, int(np.abs(y).max()))
    return best / SCALE


def check_true_peak(x24, fs) -> dict:
    ceiling = row(CEILING_ROW)
    tp = true_peak(x24, fs)
    result = {"name": "true_peak", "row": CEILING_ROW, "threshold": ceiling.value, "unit": ceiling.unit,
              "measured": None, "result": "pass", "note": ""}
    if tp == 0.0:
        result["note"] = "silent"
        return result
    measured = 20.0 * math.log10(tp)
    result["measured"] = measured
    result["result"] = "pass" if measured <= ceiling.value else "fail"
    return result
