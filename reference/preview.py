"""Reference listening preview (docs/signal-spec.md, Preview; Story 3.3).

Implemented from the signal spec only, never from engine code, engine
binaries, or engine output (AD-16, AD-19). Binary64 Python floats, each
operation one correctly rounded IEEE 754 operation in the spec's order; the
square root is the correctly rounded math.sqrt. Nothing is rendered.

- `PREVIEW_LENGTH_S`, `PREVIEW_SEAM_TAIL_S`, `PREVIEW_PEAK_DBFS`: rows
  preview-length, preview-seam-tail, preview-peak-level.
- `PreviewRowError(ValueError)`: a peak level that is not a whole multiple
  of 10 dB from -440 to 0 dB.
- `seconds_to_samples(t_s, fs)`: the Core rule.
- `peak_valid(peak_dbfs)`, `amplitude(peak_dbfs)` (10^(P/20) by the Gain
  steps), `gain(peak_dbfs, layers_max)` (n_max 0 counts as 1).
- `layers_per_ear(recipe, mute="none")`: {"left": n, "right": n} from the
  recipe fields (Layers).
- `preview_frames(recipe, fs, length_s=..., seam_tail_s=...)`: F (Frames).
- `seams_heard(recipe, fs)`: (O, O + B) of a looping recipe, else None.
- `report_member(recipe, fs, peak_dbfs=...)`: the report's preview member.

The standard library only.
"""

import math

PREVIEW_LENGTH_S = 180.0      # row preview-length
PREVIEW_SEAM_TAIL_S = 30.0    # row preview-seam-tail
PREVIEW_PEAK_DBFS = -30.0     # row preview-peak-level

_PEAK_MIN_DBFS = -440.0       # 10^22, the largest power of ten binary64 holds exactly
_PEAK_MAX_DBFS = 0.0          # full scale
_TWO_TO_64 = math.ldexp(1.0, 64)
EARS = ("left", "right")


class PreviewRowError(ValueError):
    """Row preview-peak-level holds a value the Preview, Gain steps refuse."""


def seconds_to_samples(t_s, fs):
    """x = t_s * fs (one rounding), then the nearest integer, ties to even; 0 outside the domain."""
    t_s = float(t_s)
    if not (t_s >= 0.0) or math.isinf(t_s):
        return 0
    x = t_s * float(fs)
    if not (x < _TWO_TO_64):
        return 0
    return int(round(x))  # round() on a float is exact, ties to even


def peak_valid(peak_dbfs):
    """-440 <= P <= 0, m = P / 10.0 an integer, and m * 10.0 == P."""
    p = float(peak_dbfs)
    if not (_PEAK_MIN_DBFS <= p <= _PEAK_MAX_DBFS):
        return False
    m = p / 10.0
    return float(int(m)) == m and m * 10.0 == p


def amplitude(peak_dbfs):
    """10^(P / 20) by the Preview, Gain steps."""
    p = float(peak_dbfs)
    if not peak_valid(p):
        raise PreviewRowError(f"row preview-peak-level: value {p!r} is not a whole multiple of 10 dB "
                              "from -440 to 0 dB")
    k = int(-(p / 10.0))
    x = 1.0
    for _ in range(k // 2):
        x = x * 10.0
    if k % 2:
        x = x * math.sqrt(10.0)
    return 1.0 / x


def gain(peak_dbfs, layers_max):
    """g = 10^(P / 20) / max(n_max, 1)."""
    return amplitude(peak_dbfs) / float(max(int(layers_max), 1))


def layers_per_ear(recipe, mute="none"):
    """Per ear the theta reference, the gamma PAC layer, and that ear's binaural carrier."""
    shared = int("theta_reference" in recipe) + int("gamma_pac" in recipe)
    binaural = "binaural" in recipe
    return {ear: shared + (1 if binaural and mute != ear else 0) for ear in EARS}


def _loop_frames(recipe, fs):
    loop = recipe.get("loop")
    if loop is None:
        return None
    return seconds_to_samples(loop["opening_s"], fs), seconds_to_samples(loop["body_s"], fs)


def preview_frames(recipe, fs, length_s=PREVIEW_LENGTH_S, seam_tail_s=PREVIEW_SEAM_TAIL_S):
    """F = min(L, N) without a loop, min(O + B + T, N) with one."""
    n = seconds_to_samples(recipe["length_s"], fs)
    loop = _loop_frames(recipe, fs)
    if loop is None:
        return min(seconds_to_samples(length_s, fs), n)
    o, b = loop
    return min(o + b + seconds_to_samples(seam_tail_s, fs), n)


def seams_heard(recipe, fs):
    """(O, O + B): the opening end and the first body seam of a looping recipe.

    Both lie inside the preview only when O + B < F; a session capped at or
    before the first body seam has O + B at or past F."""
    loop = _loop_frames(recipe, fs)
    if loop is None:
        return None
    o, b = loop
    return o, o + b


def report_member(recipe, fs, peak_dbfs=PREVIEW_PEAK_DBFS):
    """The report's preview member: signed, peak_dbfs, layers_per_ear, gain, seconds (F / fs)."""
    n_max = max(layers_per_ear(recipe).values())
    f = preview_frames(recipe, fs)
    return {"signed": False, "peak_dbfs": float(peak_dbfs), "layers_per_ear": n_max,
            "gain": gain(peak_dbfs, n_max), "seconds": f / fs}
