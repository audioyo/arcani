"""No floating-point pragma in engine/ sources (AD-9; deferred-work entry from Story 0.1 part 2).

Contract with tools/check_fp_pragmas.py (standard library only):

- CLI: `python tools/check_fp_pragmas.py [DIR ...]`; with no DIR it scans the
  repo's engine/ directory. It scans *.c, *.cc, *.cpp, *.cxx, *.h, *.hh,
  *.hpp, *.hxx, *.inl, *.ipp recursively; other files are ignored.
- A violation is a preprocessor `#pragma` line (leading whitespace and spaces
  after `#` allowed) whose argument starts with `clang fp`, `STDC
  FP_CONTRACT`, `STDC FENV_ACCESS`, `STDC FENV_ROUND`, `STDC
  CX_LIMITED_RANGE`, `float_control`, `fenv_access`, `fp_contract`, or `GCC
  optimize`; or the same argument in a `_Pragma("...")` or MSVC
  `__pragma(...)` anywhere on a line.
- Exit 1 with one line per violation, `<path>:<line>: <text>: floating-point
  pragma`. Exit 1 also when a given directory is missing or holds no source
  file. Otherwise exit 0, printing how many files were scanned.
- `#pragma once`, `#pragma warning(...)`, and `#pragma clang diagnostic ...`
  pass, and so does a `//` comment that mentions a banned `#pragma`.

Both workflows run it: every job of fast.yml, and every job of full.yml that
runs tools/check_compile_flags.py.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "tools" / "check_fp_pragmas.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "fp_pragmas"
CLEAN = FIXTURES / "clean"
MUSTFAIL = FIXTURES / "mustfail"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp"}

# Must-fail fixture (path relative to MUSTFAIL) -> line of its violation.
MUSTFAIL_LINES = {
    "contract_fast.cpp": 3,
    "stdc_fp_contract.c": 2,
    "stdc_fenv_access.h": 2,
    "stdc_fenv_round.hh": 2,
    "stdc_cx_limited_range.cc": 2,
    "float_control.cxx": 2,
    "fenv_access.hpp": 2,
    "fp_contract.hxx": 2,
    "underscore_pragma.ipp": 2,
    "msvc_pragma.cpp": 2,
    "nested/gcc_optimize.inl": 2,
}
FULL_FLAG_CHECK_JOBS = {"windows-x64", "windows-arm64", "macos-arm64", "android-build"}
FAST_JOBS = {"linux-x64", "windows-x64"}


def run_checker(*dirs):
    assert CHECKER.is_file(), f"missing {CHECKER}"
    result = subprocess.run(
        [sys.executable, str(CHECKER), *map(str, dirs)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=REPO_ROOT,
    )
    return result.returncode, result.stdout + result.stderr


def violation_lines(out):
    return [line for line in out.splitlines() if line.rstrip().endswith(": floating-point pragma")]


def source_files(root):
    return [p for p in root.rglob("*") if p.is_file() and p.suffix in SOURCE_SUFFIXES]


# ---------------------------------------------------------------- fixtures


def test_fixture_set_is_complete():
    found = {p.relative_to(MUSTFAIL).as_posix() for p in source_files(MUSTFAIL)}
    assert found == set(MUSTFAIL_LINES), sorted(found)
    assert len(source_files(CLEAN)) >= 2


def test_clean_fixture_passes():
    code, out = run_checker(CLEAN)
    assert code == 0, out
    assert not violation_lines(out), out
    assert re.search(rf"\b{len(source_files(CLEAN))}\b", out), (
        f"output does not give the scanned file count {len(source_files(CLEAN))}: {out}")


def test_mustfail_fixture_fails_with_one_line_per_violation():
    code, out = run_checker(MUSTFAIL)
    assert code == 1, out
    lines = violation_lines(out)
    assert len(lines) == len(MUSTFAIL_LINES), out
    for rel, line_no in MUSTFAIL_LINES.items():
        name = re.escape(Path(rel).name)
        assert any(re.search(rf"{name}:{line_no}: ", line) for line in lines), (rel, out)


def test_contract_fast_names_file_and_line():
    code, out = run_checker(MUSTFAIL)
    assert code == 1, out
    hits = [line for line in violation_lines(out) if "contract_fast.cpp" in line]
    assert len(hits) == 1, out
    assert re.search(r"contract_fast\.cpp:3: .*#pragma clang fp contract\(fast\)"
                     r".*: floating-point pragma$", hits[0]), hits[0]


@pytest.mark.parametrize("rel", sorted(MUSTFAIL_LINES))
def test_each_violating_form_fails_alone(tmp_path, rel):
    src = MUSTFAIL / rel
    target = tmp_path / src.name
    target.write_bytes(src.read_bytes())
    code, out = run_checker(tmp_path)
    assert code == 1, (rel, out)
    lines = violation_lines(out)
    assert len(lines) == 1, (rel, out)
    assert f"{src.name}:{MUSTFAIL_LINES[rel]}: " in lines[0], (rel, out)


def test_clean_and_mustfail_together_fail():
    code, out = run_checker(CLEAN, MUSTFAIL)
    assert code == 1, out
    assert len(violation_lines(out)) == len(MUSTFAIL_LINES), out


@pytest.mark.parametrize("line", [
    "#pragma once",
    "#pragma warning(disable : 4100)",
    "#pragma clang diagnostic ignored \"-Wshadow\"",
    "// #pragma STDC FENV_ACCESS ON is banned",
    "double clang_fp = 1.0;  // a name, not a pragma",
])
def test_allowed_lines_pass(tmp_path, line):
    (tmp_path / "ok.hpp").write_text(line + "\n", encoding="utf-8")
    code, out = run_checker(tmp_path)
    assert code == 0, (line, out)


def test_missing_directory_fails(tmp_path):
    code, out = run_checker(tmp_path / "does-not-exist")
    assert code == 1, out


def test_directory_without_sources_fails(tmp_path):
    (tmp_path / "readme.txt").write_text("#pragma clang fp contract(fast)\n", encoding="utf-8")
    code, out = run_checker(tmp_path)
    assert code == 1, out


def test_repo_engine_passes_by_default():
    code, out = run_checker()
    assert code == 0, out
    assert re.search(rf"\b{len(source_files(REPO_ROOT / 'engine'))}\b", out), out


def test_repo_engine_passes_explicitly():
    code, out = run_checker(REPO_ROOT / "engine")
    assert code == 0, out


# --------------------------------------------------------------- workflows


def load(name):
    path = WORKFLOWS / name
    assert path.is_file(), f"missing {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def runs(job):
    return [s["run"] for s in job.get("steps", []) if isinstance(s.get("run"), str)]


def runs_pragma_check(job):
    return any("tools/check_fp_pragmas.py" in r for r in runs(job))


@pytest.mark.parametrize("job_id", sorted(FAST_JOBS))
def test_fast_jobs_run_pragma_check(job_id):
    jobs = load("fast.yml")["jobs"]
    assert set(jobs) == FAST_JOBS
    assert runs_pragma_check(jobs[job_id]), runs(jobs[job_id])


def test_full_flag_check_jobs_are_the_expected_set():
    jobs = load("full.yml")["jobs"]
    flag_jobs = {j for j, job in jobs.items()
                 if any("tools/check_compile_flags.py" in r for r in runs(job))}
    assert flag_jobs == FULL_FLAG_CHECK_JOBS, sorted(flag_jobs)


@pytest.mark.parametrize("job_id", sorted(FULL_FLAG_CHECK_JOBS))
def test_full_flag_check_jobs_run_pragma_check(job_id):
    job = load("full.yml")["jobs"][job_id]
    assert runs_pragma_check(job), runs(job)
