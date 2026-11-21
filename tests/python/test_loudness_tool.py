"""Python loudness meter, calibrated on harness-synthesized signals (Story 4.1;
docs/signal-spec.md, Loudness).

Every calibration signal is made here with NumPy by the spec's synthesis
rule (Loudness, Calibration, Signal); no EBU file is read. Rows come from
tests/tables/*.tsv through the assertion call `assertions.row`; the vector
constants are cross-checked against them, never used in their place.

Contract with tests/assertions/loudness.py (imported as
`assertions.loudness`; NumPy and the standard library only):

- `PROTOTYPE`: {"shelf": {"f0", "Q", "Vh", "Vb"}, "highpass": {"f0", "Q",
  "G"}}, binary64, bit-equal to the hex column of Vectors: K-weighting
  prototype.
- `kweighting(fs) -> (shelf, highpass)`: each a tuple (b0, b1, b2, a1, a2)
  of floats by the spec's binary64 formulas (K-weighting, Coefficients at
  any rate). ValueError unless fs is a positive multiple of 10.
- `block_energies(x, fs) -> np.ndarray`: z[j] for every 400 ms block
  (Integrated loudness), from zero filter state. x is a float64 array-like
  of shape (frames, 2) (an np.memmap works) or (frames,) for one channel;
  ValueError on any other shape, on a non-finite sample, or on a bad fs.
- `integrated_lufs(x, fs, gating=True) -> float`: L in LUFS-I, -inf when no
  block passes or no block exists; gating=False takes every block.
- `check_loudness(x, fs, target) -> dict`: {"name": "loudness", "row":
  "loudness-tolerance", "threshold": <row value>, "unit": <row unit>,
  "measured": L - target, "result": "pass" when |measured| <= threshold
  else "fail", "note": ""}; a NaN or infinite sample: measured None, note
  "not finite", fail; L = -inf: measured None, note "silent", fail.

Calibration: Tech 3341 v4.0 Table 1 cases 1 to 5 at 44.1 and 48 kHz within
row loudness-meter-calibration of the expected value and of the ideal
column. Must-fails: gating off fails cases 3 and 4 (case 5 reads within the
row either way); a reading moved 0.2 LU fails the comparison; a coefficient
off by 1e-13 fails the coefficient bound; the assertion fails a render
scaled to must_fail_lu above (and below) the target.

The engine render (the assertion fixture's window) needs arcani-tapdump;
those tests skip only when cmake is not on PATH, or when Windows
application control blocks a binary.
"""

import ast
import json
import math
import sys
from decimal import Decimal

import numpy as np
import pytest

import loudness_common as lc
import preview_common as common
from assertions import row as table_row

SAMPLE_RATES = lc.sample_rates()
CASES = [(r["case"], r["fs"]) for r in lc.tech3341_cases()]
STAGE_ORDER = ("b0", "b1", "b2", "a1", "a2")


def loud():
    return lc.meter()


def coefficient_problems(got, fs, rows, bound):
    """Every coefficient of (shelf, highpass) within bound of the ideal and,
    where BS.1770 prints one, of the published value."""
    p = []
    stages = {"shelf": got[0], "highpass": got[1]}
    for r in rows:
        if r["fs"] != fs:
            continue
        value = stages[r["stage"]][STAGE_ORDER.index(r["coefficient"])]
        if not abs(value - lc.ideal(r["ideal"])) <= bound:
            p.append(f"{fs} {r['stage']} {r['coefficient']} {value!r} vs ideal {r['ideal']}")
        if r["published"] != "none" and not abs(value - float(r["published"])) <= bound:
            p.append(f"{fs} {r['stage']} {r['coefficient']} {value!r} vs published {r['published']}")
    return p


# ------------------------------------------------------------ the module


def test_module_uses_numpy_and_the_standard_library_only():
    m = loud()
    tree = ast.parse(open(m.__file__, encoding="utf-8").read())
    allowed = set(sys.stdlib_module_names) | {"numpy", "assertions"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] in allowed, a.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            assert node.module.split(".")[0] in allowed, node.module


# ------------------------------------------------------------ rows and constants


def test_rows_and_constants():
    k = lc.constants()
    assert lc.calibration_lu() > 0.0
    assert lc.agreement_lu() > 0.0
    assert lc.tolerance_lu() == float(k["tolerance_lu"])
    assert float(k["must_fail_lu"]) > lc.tolerance_lu()
    assert lc.window_min_s() == float(k["window_min_s"])
    assert k["window_min_row"] == lc.WINDOW_MIN_ROW
    assert k["window_limit"] == f">= {table_row(lc.WINDOW_MIN_ROW).value_text} s (row {lc.WINDOW_MIN_ROW})"
    assert k["gating_cases"] == sorted({r["case"] for r in lc.tech3341_cases() if r["gating_case"] == "yes"})
    assert sorted({r["case"] for r in lc.tech3341_cases()}) == [1, 2, 3, 4, 5]
    assert {r["fs"] for r in lc.tech3341_cases()} == set(SAMPLE_RATES)


def test_window_min_row_is_one_rate_cycle_period():
    w = table_row(lc.WINDOW_MIN_ROW)
    p = table_row(lc.CYCLE_PERIOD_ROW)
    assert w.unit == "s" and p.unit == "s", (w, p)
    assert p.kind == "ranges" and p.min == p.max, p
    assert w.value == p.min == p.max


# ------------------------------------------------------------ K-weighting


def test_prototype_constants_are_the_vector_bits():
    proto = loud().PROTOTYPE
    want = {}
    for r in lc.vectors()["loudness_prototype"]:
        want.setdefault(r["stage"], {})[r["parameter"]] = float.fromhex(r["hex"])
    assert {s: set(v) for s, v in proto.items()} == {"shelf": {"f0", "Q", "Vh", "Vb"}, "highpass": {"f0", "Q", "G"}}
    for stage, params in want.items():
        for name, value in params.items():
            got = proto[stage][name]
            assert isinstance(got, float), (stage, name, got)
            assert got.hex() == value.hex(), (stage, name, got.hex(), value.hex())
            # The hex is the binary64 nearest the 25-digit ideal.
            assert float(Decimal(next(r["ideal"] for r in lc.vectors()["loudness_prototype"]
                                      if r["stage"] == stage and r["parameter"] == name))) == value


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_kweighting_coefficients_within_the_printed_precision(fs):
    got = loud().kweighting(fs)
    assert len(got) == 2 and all(len(s) == 5 for s in got), got
    for stage in got:
        for c in stage:
            assert isinstance(c, float), stage
    rows = lc.vectors()["loudness_coefficients"]
    assert sum(1 for r in rows if r["fs"] == fs) == 10
    if fs == int(lc.constants()["published_fs"]):
        assert all(r["published"] != "none" for r in rows if r["fs"] == fs)
    assert coefficient_problems(got, fs, rows, lc.coefficient_bound()) == []


def test_kweighting_must_fail_a_coefficient_off_by_1e_13():
    fs = int(lc.constants()["published_fs"])
    shelf, highpass = loud().kweighting(fs)
    rows = lc.vectors()["loudness_coefficients"]
    for which in range(5):
        bad = list(shelf)
        bad[which] += 1e-13
        assert coefficient_problems((tuple(bad), highpass), fs, rows, lc.coefficient_bound()), which
        bad = list(highpass)
        bad[which] -= 1e-13
        assert coefficient_problems((shelf, tuple(bad)), fs, rows, lc.coefficient_bound()), which


@pytest.mark.parametrize("fs", [0, -48000, 44105, 48001, 7])
def test_kweighting_refuses_a_rate_that_is_not_a_positive_multiple_of_10(fs):
    with pytest.raises(ValueError):
        loud().kweighting(fs)


def test_kweighting_accepts_any_positive_multiple_of_10():
    for fs in (10, 8000, 96000):
        shelf, highpass = loud().kweighting(fs)
        assert all(math.isfinite(c) for c in shelf + highpass)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_one_khz_gain_is_the_vector(fs):
    """|H| at 1 kHz from the coefficients against Vectors: gating blocks (a
    cross-check that the cascade is the K-weighting filter)."""
    shelf, highpass = loud().kweighting(fs)
    w = 2.0 * math.pi * int(lc.constants()["test_hz"]) / fs
    z1, z2 = np.exp(-1j * w), np.exp(-2j * w)
    h = 1.0
    for b0, b1, b2, a1, a2 in (shelf, highpass):
        h *= (b0 + b1 * z1 + b2 * z2) / (1.0 + a1 * z1 + a2 * z2)
    gain_db = 20.0 * math.log10(abs(h))
    want = lc.ideal(next(r["gain_1khz_db"] for r in lc.vectors()["loudness_blocks"] if r["fs"] == fs))
    # Coefficients within 5e-15 move the gain by far less than 1e-9 dB; a
    # wrong stage or a swapped coefficient moves it by more than 0.01 dB.
    assert abs(gain_db - want) < 1e-9, (gain_db, want)


# ------------------------------------------------------------ blocks


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_block_count_is_floor_t_over_s_minus_3(fs):
    v = next(r for r in lc.vectors()["loudness_blocks"] if r["fs"] == fs)
    b, s = int(v["block_frames"]), int(v["step_frames"])
    k = lc.constants()
    assert b == lc.seconds_to_samples(float(k["block_s"]), fs)
    assert s * 100 == b * (100 - int(k["overlap_percent"]))
    rng = np.random.default_rng(41)
    for t in (0, 1, b - 1, b, b + s - 1, b + s, b + 3 * s + 7, 10 * fs):
        x = rng.uniform(-0.5, 0.5, size=(t, 2))
        z = loud().block_energies(x, fs)
        want = max(t // s - 3, 0)
        assert isinstance(z, np.ndarray) and z.shape == (want,), (t, z.shape, want)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_block_energies_one_channel_and_two(fs):
    x = lc.tech3341_signal(lc.tech3341_case(1, fs))[: 3 * fs]
    z2 = loud().block_energies(x, fs)
    z1 = loud().block_energies(np.ascontiguousarray(x[:, 0]), fs)
    assert z1.shape == z2.shape
    # Weights 1.0: two equal channels hold twice the energy of one.
    np.testing.assert_allclose(z2, 2.0 * z1, rtol=1e-12, atol=0.0)
    # A block of the steady tone: z = A^2 |H(1 kHz)|^2 for both channels together
    # (each channel's mean square A^2 / 2 times the K-weighting power gain).
    v = next(r for r in lc.vectors()["loudness_blocks"] if r["fs"] == fs)
    a = 10.0 ** (-23.0 / 20.0)
    ideal_z = a * a * 10.0 ** (lc.ideal(v["gain_1khz_db"]) / 10.0)
    steady = -0.691 + 10.0 * math.log10(z2[-1])
    assert lc.calibration_problems(steady, -0.691 + 10.0 * math.log10(ideal_z), lc.calibration_lu()) == []


def test_block_energies_refuses_bad_input():
    m = loud()
    fs = 48000
    good = np.zeros((fs, 2))
    for bad in (np.zeros((fs, 3)), np.zeros((fs, 1, 2)), np.zeros((2, fs)), np.zeros(())):
        with pytest.raises(ValueError):
            m.block_energies(bad, fs)
    for value in (math.nan, math.inf, -math.inf):
        x = good.copy()
        x[fs // 2, 1] = value
        with pytest.raises(ValueError):
            m.block_energies(x, fs)
    for bad_fs in (0, 44101):
        with pytest.raises(ValueError):
            m.block_energies(good, bad_fs)


# ------------------------------------------------------------ Tech 3341


@pytest.mark.parametrize("case,fs", CASES)
def test_tech3341_case_within_the_calibration_row(case, fs):
    v = lc.tech3341_case(case, fs)
    x = lc.tech3341_signal(v)
    tol = lc.calibration_lu()
    gated = loud().integrated_lufs(x, fs)
    ungated = loud().integrated_lufs(x, fs, gating=False)
    assert isinstance(gated, float) and isinstance(ungated, float)
    expected = float(v["expected_lufs"])
    assert lc.calibration_problems(gated, expected, tol) == []
    assert lc.calibration_problems(gated, lc.ideal(v["ideal_gated"]), tol) == []
    assert lc.calibration_problems(ungated, lc.ideal(v["ideal_ungated"]), tol) == []
    if v["gating_case"] == "yes":
        # Must-fail: the meter with gating off fails the case.
        assert lc.calibration_problems(ungated, expected, tol), (case, fs, ungated)
    else:
        assert lc.calibration_problems(ungated, expected, tol) == []
        assert lc.calibration_problems(ungated, gated, tol) == []
    # Must-fail: the same reading moved 0.2 LU fails the comparison.
    assert lc.calibration_problems(gated + 0.2, expected, tol)
    assert lc.calibration_problems(gated - 0.2, expected, tol)


@pytest.mark.parametrize("fs", sorted({fs for _, fs in CASES}))
def test_tech3341_case_1_with_the_right_channel_silent(fs):
    # Different channels: a meter that reads one channel twice or drops one
    # fails here, where the in-phase cases cannot tell.
    v = lc.tech3341_case(1, fs)
    x = lc.tech3341_signal(v).copy()
    x[:, 1] = 0.0
    tol = lc.calibration_lu()
    want = float(v["expected_lufs"]) - 10.0 * math.log10(2.0)
    reading = loud().integrated_lufs(x, fs)
    assert lc.calibration_problems(reading, want, tol) == []
    assert lc.calibration_problems(reading, lc.ideal(v["ideal_gated"]) - 10.0 * math.log10(2.0), tol) == []
    # Must-fail, doctored in the harness: the left channel read twice.
    doubled = np.column_stack((x[:, 0], x[:, 0]))
    assert lc.calibration_problems(loud().integrated_lufs(doubled, fs), want, tol)


def test_tech3341_vectors_ideal_columns():
    """The ideal readings of the gating cases are outside the row with gating
    off and inside it with gating on (the must-fail is decided by the case,
    not by the meter's transients)."""
    tol = lc.calibration_lu()
    for v in lc.tech3341_cases():
        expected = float(v["expected_lufs"])
        assert abs(lc.ideal(v["ideal_gated"]) - expected) <= tol, v["case"]
        off = abs(lc.ideal(v["ideal_ungated"]) - expected) <= tol
        assert off == (v["gating_case"] == "no"), v["case"]


def test_memmap_input_equals_array_input(tmp_path):
    fs = 44100
    x = lc.tech3341_signal(lc.tech3341_case(5, fs))
    path = tmp_path / "case5.f64"
    x.astype("<f8").tofile(path)
    with lc.f64_frames(path, frames=x.shape[0]) as mm:
        assert isinstance(mm, np.memmap)
        z_mm = loud().block_energies(mm, fs)
        l_mm = loud().integrated_lufs(mm, fs)
    assert not path.exists()
    z = loud().block_energies(x, fs)
    l_arr = loud().integrated_lufs(x, fs)
    assert z_mm.tobytes() == z.tobytes()
    assert l_mm.hex() == l_arr.hex()


# ------------------------------------------------------------ silence and short signals


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_silent_and_short_signals_read_minus_inf(fs):
    m = loud()
    b = int(next(r for r in lc.vectors()["loudness_blocks"] if r["fs"] == fs)["block_frames"])
    tone = lc.tech3341_signal(lc.tech3341_case(1, fs))
    for name, x in (("silent 10 s", np.zeros((10 * fs, 2))),
                    ("no frames", np.zeros((0, 2))),
                    ("one frame short of a block", tone[: b - 1])):
        for gating in (True, False):
            got = m.integrated_lufs(x, fs, gating=gating)
            assert got == -math.inf, (name, gating, got)
    # Every block below the absolute gate: -inf gated, a finite reading ungated.
    quiet = tone[: 5 * fs] * 10.0 ** ((-80.0 + 23.0) / 20.0)
    assert m.integrated_lufs(quiet, fs) == -math.inf
    assert math.isfinite(m.integrated_lufs(quiet, fs, gating=False))
    assert m.integrated_lufs(quiet, fs, gating=False) < -70.0


# ------------------------------------------------------------ the assertion


def report_problems(a, measured_none=False):
    p = []
    if list(a) != ["name", "row", "threshold", "unit", "measured", "result", "note"]:
        return [f"keys {list(a)}"]
    r = table_row(lc.TOLERANCE_ROW)
    if a["name"] != "loudness":
        p.append(f"name {a['name']!r}")
    if a["row"] != lc.TOLERANCE_ROW:
        p.append(f"row {a['row']!r}")
    if a["threshold"] != r.value:
        p.append(f"threshold {a['threshold']!r}")
    if a["unit"] != r.unit:
        p.append(f"unit {a['unit']!r}")
    if measured_none != (a["measured"] is None):
        p.append(f"measured {a['measured']!r}")
    return p


@pytest.fixture(scope="module")
def tapdump_exe():
    return common.build("arcani-tapdump", common.TAPDUMP)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_check_loudness_on_a_scaled_engine_render(tapdump_exe, tmp_path, fs):
    """The assertion fixture's window (float output from the tap dump),
    scaled in the harness to read exactly the target: passes; scaled to
    must_fail_lu above or below: fails."""
    m = loud()
    fixture = lc.constants()["assertion_fixture"]
    recipe = json.loads((lc.FIXTURES_VALID / fixture).read_text(encoding="utf-8"))
    target = float(recipe["loudness_target_lufs"])
    v = lc.window_row(fixture, fs)
    assert v["result"] == "accepted" and v["repeats"] == "1", v
    path = lc.tapdump(tapdump_exe, lc.FIXTURES_VALID / fixture, fs, tmp_path,
                      window=(int(v["start_frame"]), int(v["body_frames"])))
    with lc.f64_frames(path, frames=int(v["body_frames"])) as mm:
        x = np.array(mm)
    l0 = m.integrated_lufs(x, fs)
    assert math.isfinite(l0) and l0 > target, l0
    tol = lc.tolerance_lu()
    must = float(lc.constants()["must_fail_lu"])

    def scaled(offset_lu):
        return x * (10.0 ** ((target + offset_lu - l0) / 20.0))

    at_target = m.check_loudness(scaled(0.0), fs, target)
    assert report_problems(at_target) == []
    assert at_target["result"] == "pass" and at_target["note"] == ""
    assert abs(at_target["measured"]) < 1e-6, at_target
    for offset, result in ((0.9 * tol, "pass"), (-0.9 * tol, "pass"), (must, "fail"), (-must, "fail"),
                           (1.1 * tol, "fail")):
        a = m.check_loudness(scaled(offset), fs, target)
        assert report_problems(a) == [], (offset, a)
        assert a["result"] == result, (offset, a)
        assert abs(a["measured"] - offset) < 1e-6, (offset, a)
        assert a["note"] == ""
    # The unscaled render (unit gain, far above the target) fails.
    assert m.check_loudness(x, fs, target)["result"] == "fail"


def test_check_loudness_not_finite_and_silent():
    m = loud()
    fs = 48000
    x = lc.tech3341_signal(lc.tech3341_case(1, fs))
    target = -23.0
    assert m.check_loudness(x, fs, target)["result"] == "pass"
    for value in (math.nan, math.inf, -math.inf):
        bad = x.copy()
        bad[fs, 0] = value
        a = m.check_loudness(bad, fs, target)
        assert report_problems(a, measured_none=True) == [], a
        assert a["result"] == "fail" and a["note"] == "not finite", a
    a = m.check_loudness(np.zeros((10 * fs, 2)), fs, target)
    assert report_problems(a, measured_none=True) == [], a
    assert a["result"] == "fail" and a["note"] == "silent", a
