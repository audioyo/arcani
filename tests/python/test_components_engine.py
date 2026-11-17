"""Engine component table from the tap dump against the vectors and the reference table (Story 3.1).

Contract with the tap dump (tests/tapdump/main.cpp, target arcani-tapdump;
Story 3.1 spec, Implementation Notes):

- `arcani-tapdump RECIPE RATE OUT_DIR --components [--mute left|right]`
  compiles in measure mode, renders nothing, and writes
  OUT_DIR/components.tsv: the header line
  `ear<TAB>layer<TAB>gamma_mult<TAB>theta_mult<TAB>beat_mult<TAB>center_hz<TAB>low_hz<TAB>high_hz<TAB>level`,
  then one line per table row in table order, ear `left` or `right`, layer
  `theta_reference`, `gamma_pac`, or `binaural`, the four doubles as %.17g,
  LF line ends. It prints `arcani-tapdump: components N` and exits 0. Exit
  codes otherwise as the other modes: 2 on a usage error, 1 when the recipe
  cannot be read or is rejected.

Every vector case, at both sample rates: the engine table equals the vector
rows within rows component-level-error and component-frequency-error, the
same rows in the same order, equals the Python reference table within the
same rows, and is the same bytes at both rates.

The dump tests skip only when cmake is not on PATH, or when Windows
application control blocks the binary (OSError winerror 4551 or 1260).
"""

import os
import re
import shutil
import subprocess
import sys

import pytest

import components_common as common
from assertions.tables import load_tables

REPO_ROOT = common.REPO_ROOT
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
HEADER = "ear\tlayer\tgamma_mult\ttheta_mult\tbeat_mult\tcenter_hz\tlow_hz\thigh_hz\tlevel"
DUMP_FILES = ("out.f64", "theta.f64", "gamma.f64", "bus.f64", "join.f64", "master.f64")


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


def run(exe, args):
    try:
        return subprocess.run([str(exe), *[str(a) for a in args]], capture_output=True, text=True, timeout=120)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the dump (winerror {e.winerror})")
        raise


def mute_args(mute):
    return [] if mute == "none" else ["--mute", mute]


def parse_tsv(data):
    """The rows of components.tsv bytes, checking the file format on the way."""
    assert b"\r" not in data, "components.tsv has a CR"
    text = data.decode("utf-8")
    assert text.endswith("\n"), "components.tsv does not end with LF"
    lines = text[:-1].split("\n")
    assert lines[0] == HEADER, lines[0]
    rows = []
    for number, raw in enumerate(lines[1:], start=2):
        f = raw.split("\t")
        assert len(f) == 9, (number, raw)
        assert f[0] in common.EARS and f[1] in common.LAYERS, (number, raw)
        for text_int in f[2:5]:
            assert re.fullmatch(r"-?[0-9]+", text_int), (number, raw)
        values = [float(v) for v in f[5:9]]
        for v, t in zip(values, f[5:9]):
            assert "%.17g" % v == t, (number, t, "not %.17g")
        rows.append(common.Row(f[1], f[0], values[0], values[1], values[2], values[3],
                               int(f[2]), int(f[3]), int(f[4])))
    return rows


def dump_table(exe, recipe_path, fs, out_dir, mute="none"):
    out_dir.mkdir(parents=True, exist_ok=True)
    result = run(exe, [recipe_path, fs, out_dir, "--components", *mute_args(mute)])
    assert result.returncode == 0, result.stdout + result.stderr
    data = (out_dir / "components.tsv").read_bytes()
    rows = parse_tsv(data)
    assert result.stdout.strip() == f"arcani-tapdump: components {len(rows)}", result.stdout
    for name in DUMP_FILES:
        assert not (out_dir / name).exists(), f"--components rendered {name}"
    return rows, data


def write_case(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    path.write_bytes(common.case(name)["recipe"].encode("utf-8"))
    return path


# ------------------------------------------------------------ format checks without the engine


def test_must_fail_the_tsv_format_check_catches_a_broken_file():
    good = (HEADER + "\nleft\ttheta_reference\t0\t0\t0\t450\t450\t450\t1\n").encode("utf-8")
    rows = parse_tsv(good)
    assert rows == [common.Row("theta_reference", "left", 450.0, 450.0, 450.0, 1.0, 0, 0, 0)]
    for bad in (good.replace(b"\n", b"\r\n"),
                good[:-1],
                good.replace(b"ear\t", b"Ear\t"),
                good.replace(b"\t450\t450\t450", b"\t450.0\t450\t450"),
                good.replace(b"left\t", b"both\t"),
                good.replace(b"\t0\t0\t0\t", b"\t0\t0.5\t0\t")):
        with pytest.raises(AssertionError):
            parse_tsv(bad)


# ------------------------------------------------------------ the engine


@pytest.mark.parametrize("name", common.case_names())
def test_engine_table_equals_the_vectors_and_the_reference(name, tapdump, tmp_path):
    c = common.case(name)
    path = write_case(tmp_path, name)
    want = common.want_rows(name)
    reference = common.reference_components().component_table(common.case_recipe(name), c["mute"])
    data_by_rate = {}
    for fs in SAMPLE_RATES:
        rows, data = dump_table(tapdump, path, fs, tmp_path / f"out-{fs}", c["mute"])
        problems = common.compare(rows, want)
        assert not problems, f"{name} {fs}:\n" + "\n".join(problems)
        problems = common.compare(rows, common.as_rows(reference))
        assert not problems, f"{name} {fs} against the reference:\n" + "\n".join(problems)
        data_by_rate[fs] = data
    assert len(set(data_by_rate.values())) == 1, f"{name}: the table differs between sample rates"


@pytest.mark.parametrize("c", [c for c in common.fixture_cases()], ids=lambda c: c["case"])
def test_engine_table_of_the_fixture_file_equals_the_vectors(c, tapdump, tmp_path):
    fs = SAMPLE_RATES[-1]
    rows, _ = dump_table(tapdump, common.FIXTURES_VALID / c["fixture"], fs, tmp_path / "out", c["mute"])
    problems = common.compare(rows, common.want_rows(c["case"]))
    assert not problems, "\n".join(problems)


def test_engine_muted_ear_drops_only_that_binaural_row(tapdump, tmp_path):
    fs = SAMPLE_RATES[0]
    path = common.FIXTURES_VALID / "binaural-beat-6.json"
    full, _ = dump_table(tapdump, path, fs, tmp_path / "none")
    assert [r.ear for r in full] == ["left", "right"]
    for mute, keep in (("left", "right"), ("right", "left")):
        rows, _ = dump_table(tapdump, path, fs, tmp_path / mute, mute)
        assert [r.ear for r in rows] == [keep], (mute, rows)
        assert rows == [r for r in full if r.ear == keep]


def test_engine_components_mode_refuses_a_rejected_recipe_and_bad_arguments(tapdump, tmp_path):
    fs = SAMPLE_RATES[0]
    rejected = common.FIXTURES_VALID / "gamma-carrier-wave-triangle.json"
    out = tmp_path / "rejected"
    out.mkdir()
    result = run(tapdump, [rejected, fs, out, "--components"])
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert not (out / "components.tsv").exists()
    assert "non-sine carrier not modeled" in result.stderr, result.stderr
    good = common.FIXTURES_VALID / "theta-sine-6hz.json"
    for args in (["--components", "--mute", "middle"], ["--components", "--mute"], ["--components", "extra"]):
        result = run(tapdump, [good, fs, tmp_path / "usage", *args])
        assert result.returncode == 2, (args, result.stdout, result.stderr)
        assert not (tmp_path / "usage" / "components.tsv").exists(), args
    result = run(tapdump, [tmp_path / "missing.json", fs, tmp_path / "missing", "--components"])
    assert result.returncode == 1, (result.stdout, result.stderr)
