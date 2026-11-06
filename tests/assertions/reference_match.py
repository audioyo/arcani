"""Reference match assertion (Story 1.5, AD-16).

Compares engine pre-quantization output or a tap with the Python reference
(reference/stub_chain.py) sample by sample, per channel. Thresholds come from
tests/tables/thresholds.tsv through `row`: `reference-match` (the match line)
and `reference-match-min-level` (the silent floor).

- level_dbfs(x): 20 log10(max |x|), -inf when every sample is zero or x is
  empty.
- difference_dbfs(engine, reference): 20 log10(max |engine - reference|) in
  binary64, -inf for an exact match; different shapes raise ValueError.
- match(name, engine, reference): one channel, in this order: a non-finite
  sample fails ("not finite"); either side below the floor fails ("silent");
  an exact match passes ("exact", measured None); otherwise pass when
  measured < threshold (strictly). Returns the report assertion shape.
- match_stereo(signal, engine, reference): both channels of interleaved
  stereo arrays, named "reference match <signal> left|right".
- all_positive_zero(x): every sample has the bit pattern of +0.0.

NumPy and the standard library only.
"""

from __future__ import annotations

import math

import numpy as np

from . import row

MATCH_ROW = "reference-match"
MIN_LEVEL_ROW = "reference-match-min-level"


def _array(x) -> np.ndarray:
    return np.asarray(x, dtype=np.float64)


def _dbfs(peak: float) -> float:
    return -math.inf if peak == 0.0 else 20.0 * math.log10(peak)


def level_dbfs(x) -> float:
    a = _array(x)
    if a.size == 0:
        return -math.inf
    return _dbfs(float(np.max(np.abs(a))))


def difference_dbfs(engine, reference) -> float:
    e = _array(engine)
    r = _array(reference)
    if e.shape != r.shape:
        raise ValueError(f"shape mismatch: engine {e.shape}, reference {r.shape}")
    if e.size == 0:
        return -math.inf
    return _dbfs(float(np.max(np.abs(e - r))))


def match(name, engine, reference) -> dict:
    threshold_row = row(MATCH_ROW)
    floor = row(MIN_LEVEL_ROW).value
    threshold = threshold_row.value
    e = _array(engine)
    r = _array(reference)
    if e.shape != r.shape:
        raise ValueError(f"shape mismatch: engine {e.shape}, reference {r.shape}")
    result = {"name": name, "row": MATCH_ROW, "threshold": threshold, "unit": threshold_row.unit,
              "measured": None, "result": "fail", "note": ""}
    if not (np.all(np.isfinite(e)) and np.all(np.isfinite(r))):
        result["note"] = "not finite"
        return result
    diff = difference_dbfs(e, r)
    if level_dbfs(e) < floor or level_dbfs(r) < floor:
        result["note"] = "silent"
        result["measured"] = None if diff == -math.inf else diff
        return result
    if diff == -math.inf:
        result["result"] = "pass"
        result["note"] = "exact"
        return result
    result["measured"] = diff
    result["result"] = "pass" if diff < threshold else "fail"
    return result


def match_stereo(signal, engine, reference) -> list[dict]:
    e = _array(engine)
    r = _array(reference)
    if e.ndim != 1 or r.ndim != 1 or e.shape != r.shape:
        raise ValueError(f"interleaved stereo arrays differ: engine {e.shape}, reference {r.shape}")
    if e.size % 2 != 0:
        raise ValueError(f"interleaved stereo needs an even length, got {e.size}")
    return [match(f"reference match {signal} {side}", e[c::2], r[c::2])
            for c, side in ((0, "left"), (1, "right"))]


def all_positive_zero(x) -> bool:
    a = np.ascontiguousarray(_array(x))
    return not a.view(np.uint64).any()
