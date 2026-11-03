"""The C++ and Python table loaders read the same rows (Story 0.3).

Contract with the test-only binary `arcani-tables-dump` (CMake target in
tests/assertions/, EXCLUDE_FROM_ALL, buildable with ARCANI_BUILD_TESTS=OFF,
output at `<build>/tests/assertions/arcani-tables-dump[.exe]`):

- `arcani-tables-dump [TABLES_DIR]` (default: the repo tests/tables) prints
  on stdout one line per row the C++ loader read, in load order (thresholds
  then ranges), LF line ends, in the format of Python
  `assertions.tables.dump_lines`, and exits 0.
- On a loader error it exits 1 and prints a message on stderr naming the
  file, `:<line>:`, and the id.

The test requires the dump of the repo tables to equal
`dump_lines(load_tables())` line for line (same ids, value texts, binary64
bits, units, bounds); a mismatch names the first differing id.

The real build follows tests/python/test_probe_reference.py: configure the
platform preset with ARCANI_BUILD_TESTS=OFF into a temporary directory,
build only arcani-tables-dump (on Windows through tools/dev.ps1), and run
it. It skips only when cmake is not on PATH, or when Windows application
control blocks the binary (OSError winerror 4551 or 1260).
"""

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLES = REPO_ROOT / "tests" / "tables"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "tables"
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
EXE_NAME = "arcani-tables-dump.exe" if sys.platform == "win32" else "arcani-tables-dump"


def cmake_command(args):
    if sys.platform == "win32":
        return [
            "powershell", "-NoProfile", "-File", str(REPO_ROOT / "tools" / "dev.ps1"),
            "cmake", *args,
        ]
    return [CMAKE, *args]


def run_cmake(args):
    result = subprocess.run(
        cmake_command(args),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        env=os.environ.copy(),
    )
    return result.returncode, result.stdout + result.stderr


@pytest.fixture(scope="module")
def dump_exe(tmp_path_factory):
    """Builds arcani-tables-dump once; returns its path."""
    if CMAKE is None:
        pytest.skip("cmake is not on PATH")
    build = tmp_path_factory.mktemp("tables-dump") / "build"
    code, out = run_cmake(["--preset", PRESET, "-B", str(build), "-DARCANI_BUILD_TESTS=OFF"])
    if code == 0:
        code2, out2 = run_cmake(["--build", str(build), "--target", "arcani-tables-dump"])
        code, out = code2, out + out2
    assert code == 0, out
    exe = build / "tests" / "assertions" / EXE_NAME
    assert exe.is_file(), f"dump binary not at {exe}"
    return exe


def run_dump(exe, *args):
    try:
        return subprocess.run([str(exe), *map(str, args)], capture_output=True, timeout=120)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the dump (winerror {e.winerror})")
        raise


def first_difference(cpp_lines, py_lines):
    for cpp, py in zip(cpp_lines, py_lines):
        if cpp != py:
            row_id = (py.split("\t") + [""])[1]
            return f"first differing id {row_id}:\n  C++    {cpp!r}\n  Python {py!r}"
    if len(cpp_lines) != len(py_lines):
        longer = cpp_lines if len(cpp_lines) > len(py_lines) else py_lines
        extra = longer[min(len(cpp_lines), len(py_lines))]
        side = "C++" if longer is cpp_lines else "Python"
        return f"first differing id {(extra.split(chr(9)) + [''])[1]}: only {side} has {extra!r}"
    return None


def test_first_difference_names_the_id():
    a = ["thresholds\tx-one\tHz\t1\t00", "ranges\tx-two\tHz\t0\t00\t1\t00\tinclusive"]
    b = [a[0], "ranges\tx-two\tHz\t0\t00\t2\t00\tinclusive"]
    assert first_difference(a, a) is None
    assert "x-two" in first_difference(a, b)
    assert "x-two" in first_difference(a[:1], a)


def test_cpp_dump_equals_python_rows(dump_exe):
    tables = importlib.import_module("assertions.tables")
    expected = tables.dump_lines(list(tables.load_tables().values()))
    result = run_dump(dump_exe, TABLES)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert b"\r" not in result.stdout, "dump must use LF line ends"
    got = result.stdout.decode("utf-8").split("\n")
    assert got and got[-1] == "", "dump must end with a newline"
    diff = first_difference(got[:-1], expected)
    assert diff is None, diff


def test_cpp_dump_default_dir_is_repo_tables(dump_exe):
    assert run_dump(dump_exe).stdout == run_dump(dump_exe, TABLES).stdout


def test_cpp_dump_fails_on_bad_tables(dump_exe):
    result = run_dump(dump_exe, FIXTURES / "dup-across")
    err = result.stderr.decode("utf-8", "replace")
    assert result.returncode == 1, (result.returncode, err)
    assert "ranges.tsv" in err and ":3:" in err and "fixture-twice" in err, err
