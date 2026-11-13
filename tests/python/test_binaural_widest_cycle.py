"""The widest compile-accepted beat rate cycle matches the reference (Story 2.5, precise cycle cosine).

docs/signal-spec.md, Binaural layer, Error bound: the cycle right ear's engine
error is the cycle cosine's error scaled by 2 pi K, so the widest cycle
compile accepts is the hardest case for row `reference-match`. Audio's
decision of 2026-11-12 (spec, "Precise cycle cosine", review pass 1 row 1)
is that every compile-accepted cycle keeps the right ear within the row.

Harness recipes, made here in a pytest temp folder, one whole cycle (60 s)
each, no other layer:

- binaural layer: a 100 Hz pure sine in the left ear and a pure sine in the
  right ear whose beat rate cycles around a 15 Hz center with the widest
  swing compile accepts, every 60 s, from start phase 0 degrees (at the
  center, rising), 90 (at the maximum), 180 (center, falling), 270 (at the
  minimum), or 123.4 (off the quadrant points, where c0 is not exact).

The widest swing is found here from row `beat-rate` (read through the
assertion call): the largest binary64 `s` with `r - s >= min` and
`fl(r + s) < max`. The largest binary64 below 15 does not qualify, because
15 + (15 - 2^-49) rounds to 30 (a tie, to even); the swing is 15 - 2^-48, so
`r + s = 30 - 2^-48` and K is about 143.2. A test pins that boundary: the
dump rejects the swing one step wider with rule `range.max` on
`/binaural/beat_rate_cycle/swing_hz`.

Each recipe is rendered with arcani-tapdump (tests/tapdump/) at both rates of
row `sample-rates`. Both ears of the join tap and the output pass row
`reference-match` against reference.stub_chain.render through
tests/assertions/reference_match.py. Must-fail made here: the reference right
ear with a phase offset of K * 1e-7 cycles (2 pi K * 1e-7 radians, the size
of the engine sine's cosine error times 2 pi K) fails the row, while the same
harness law with no offset passes it, so the row can tell.

The dump tests skip only when cmake is not on PATH, or when Windows
application control blocks the binary (OSError winerror 4551 or 1260).
"""

import importlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from assertions import row as table_row
from assertions.tables import load_tables

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / "recipes" / "recipe.schema.json"
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
EXE_NAME = "arcani-tapdump.exe" if sys.platform == "win32" else "arcani-tapdump"
TAPDUMP = REPO_ROOT / "build" / PRESET / "tests" / "tapdump" / EXE_NAME

SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
LEFT_HZ = 100.0
CENTER_HZ = 15.0
PERIOD_S = 60.0
LENGTH_S = 60
# Every quadrant point and one off-quadrant phase: the bound holds at any start phase.
START_PHASES = (0, 90, 180, 270, 123.4)
SWING_PARAMETER = "/binaural/beat_rate_cycle/swing_hz"
MUST_FAIL_CYCLES_PER_K = 1e-7


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def stub_chain():
    _repo_on_path()
    return importlib.import_module("reference.stub_chain")


def binaural_ref():
    _repo_on_path()
    return importlib.import_module("reference.binaural")


def ideal():
    _repo_on_path()
    return importlib.import_module("reference.ideal")


def rm():
    return importlib.import_module("assertions.reference_match")


def beat_rate_row():
    r = table_row("beat-rate")
    assert r.unit == "Hz", r
    return r


def widest_swing():
    """The largest binary64 swing compile accepts at the 15 Hz center (Rate curve, Range checks)."""
    r = beat_rate_row()
    s = CENTER_HZ
    while not (CENTER_HZ - s >= r.min and CENTER_HZ + s < r.max):
        s = math.nextafter(s, 0.0)
    return s


def widest_binaural(start_phase_deg, swing=None):
    return {"carrier_left_hz": LEFT_HZ, "beat_rate_hz": CENTER_HZ,
            "beat_rate_cycle": {"swing_hz": widest_swing() if swing is None else swing,
                                "period_s": PERIOD_S, "start_phase_deg": start_phase_deg}}


def widest_recipe(binaural):
    return {
        "schema_version": "1.0", "engine_version": "0.0.1", "seed": 42,
        "author": "Arcani test", "date": "2026-11-12",
        "rationale": "Widest beat rate cycle recipe, made in the test.",
        "length_s": LENGTH_S, "loudness_target_lufs": -36,
        "binaural": binaural,
    }


def write_recipe(folder, name, binaural):
    path = folder / name
    path.write_text(json.dumps(widest_recipe(binaural), indent=2), encoding="utf-8")
    return path


# ------------------------------------------------------ without a build


def test_the_widest_swing_is_the_largest_binary64_the_beat_rate_checks_accept():
    r = beat_rate_row()
    s = widest_swing()
    assert s == math.nextafter(math.nextafter(CENTER_HZ, 0.0), 0.0) == CENTER_HZ - 2.0**-48
    assert CENTER_HZ - s >= r.min and CENTER_HZ + s < r.max
    wider = math.nextafter(s, math.inf)
    assert not (CENTER_HZ + wider < r.max), "one step wider must reach the row max"
    # The right carrier worst case is far inside its row.
    right = table_row("binaural-carrier-right")
    assert (LEFT_HZ + CENTER_HZ) + s < right.max
    # K is near 143.2, the case the spec's Error bound names.
    k = s * PERIOD_S / (2.0 * math.pi)
    assert 143.0 < k < 143.3, k


def test_the_widest_recipes_are_schema_valid():
    import jsonschema

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for deg in START_PHASES:
        errors = list(validator.iter_errors(widest_recipe(widest_binaural(deg))))
        assert not errors, (deg, [e.message for e in errors])


def harness_right_ear(binaural, fs, frames, offset_cycles):
    """The reference right ear law (Binaural layer, Reference) plus a constant phase offset in cycles."""
    f_center = float(binaural["carrier_left_hz"]) + float(binaural["beat_rate_hz"])
    n = np.arange(frames, dtype=np.uint64)
    phase_c = n * np.uint64(ideal().phase_increment(f_center, fs))  # wraps modulo 2^64
    y = phase_c.astype(np.float64) / 2.0**64 + binaural_ref().beat_offset_cycles(binaural, fs, frames)
    y = y + offset_cycles
    y = y - np.rint(y)
    return np.sin(2.0 * math.pi * y)


@pytest.mark.parametrize("deg", START_PHASES)
def test_must_fail_a_right_ear_off_by_2_pi_k_times_1e_7_fails_the_row(deg, tmp_path):
    fs = SAMPLE_RATES[0]
    frames = 10 * fs  # ten seconds is enough to show the row's teeth
    b = widest_binaural(deg)
    path = write_recipe(tmp_path, f"widest-{deg}.json", b)
    ref = stub_chain().render(path, fs, frames=frames)
    ref_right = np.asarray(ref["join"])[1::2]
    mod = rm()
    table_row("reference-match")
    same = mod.match(f"harness law, start {deg}", harness_right_ear(b, fs, frames, 0.0), ref_right)
    assert same["result"] == "pass", same
    k = float(b["beat_rate_cycle"]["swing_hz"]) * PERIOD_S / (2.0 * math.pi)
    doctored = harness_right_ear(b, fs, frames, k * MUST_FAIL_CYCLES_PER_K)
    miss = mod.match(f"doctored right ear, start {deg}", doctored, ref_right)
    assert miss["result"] == "fail", miss
    assert miss["measured"] is not None and miss["measured"] >= miss["threshold"], miss


# ------------------------------------------------------ engine dumps


def cmake_command(args):
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-File", str(REPO_ROOT / "tools" / "dev.ps1"), "cmake", *args]
    return [CMAKE, *args]


@pytest.fixture(scope="module")
def tapdump():
    if CMAKE is None:
        pytest.skip("cmake is not on PATH")
    result = subprocess.run(cmake_command(["--build", "--preset", PRESET, "--target", "arcani-tapdump"]),
                            cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
                            env=os.environ.copy())
    assert result.returncode == 0, (
        f"building arcani-tapdump failed (configure the {PRESET} preset first):\n"
        f"{result.stdout}{result.stderr}")
    assert TAPDUMP.is_file(), f"dump binary not at {TAPDUMP}"
    return TAPDUMP


def run_dump(exe, recipe, fs, out_dir, expect_ok=True):
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run([str(exe), str(recipe), str(fs), str(out_dir), "0"],
                                capture_output=True, text=True, timeout=600)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the dump (winerror {e.winerror})")
        raise
    if expect_ok:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


DUMP_KEYS = (("join", "join"), ("output", "out"))


@pytest.mark.parametrize("deg", START_PHASES)
@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_widest_cycle_matches_the_reference_in_both_ears(deg, fs, tapdump, tmp_path):
    b = widest_binaural(deg)
    path = write_recipe(tmp_path, f"widest-{deg}.json", b)
    out_dir = tmp_path / "dump"
    # Compile accepts the recipe: the dump exits 0 and writes every tap.
    result = run_dump(tapdump, path, fs, out_dir)
    frames = ideal().seconds_to_samples(float(LENGTH_S), fs)
    assert f"frames {frames} total {frames}" in result.stdout, result.stdout
    eng = {key: np.fromfile(out_dir / f"{name}.f64", dtype="<f8").astype(np.float64) for key, name in DUMP_KEYS}
    shutil.rmtree(out_dir, ignore_errors=True)
    for key, a in eng.items():
        assert a.size == 2 * frames, (deg, fs, key, a.size)
    ref = stub_chain().render(path, fs, frames=frames)
    mod = rm()
    table_row("reference-match")
    results = []
    for key in ("join", "output"):
        results += mod.match_stereo(f"widest cycle start {deg} {fs} {key}", eng[key], np.asarray(ref[key]))
    assert len(results) == 4
    failed = [r for r in results if r["result"] != "pass"]
    assert not failed, failed


def test_engine_rejects_the_swing_one_step_wider(tapdump, tmp_path):
    wider = math.nextafter(widest_swing(), math.inf)
    assert wider == math.nextafter(CENTER_HZ, 0.0)
    path = write_recipe(tmp_path, "wider.json", widest_binaural(0, swing=wider))
    result = run_dump(tapdump, path, SAMPLE_RATES[0], tmp_path / "dump", expect_ok=False)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert not (tmp_path / "dump" / "join.f64").exists()
    text = result.stdout + result.stderr
    assert "range.max" in text and SWING_PARAMETER in text, text
