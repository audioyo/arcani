"""Engine source scan: no long double, L literals, transcendental or fma calls, or <random> (Story 1.6, AD-9).

Constant-folded libm calls, `long double`, and `L` literals leave no symbol,
so tools/check_engine_symbols.py cannot see them. This scan reads the source.

Contract with tools/check_engine_source.py (standard library only):

- CLI: `python tools/check_engine_source.py [DIR ...]`; with no DIR it scans
  the repo's engine/ directory. It scans *.c, *.cc, *.cpp, *.cxx, *.h, *.hh,
  *.hpp, *.hxx, *.inl, *.ipp recursively; other files are ignored (the same
  set as tools/check_fp_pragmas.py).
- Comments (`//` and `/* ... */`, including block comments over several
  lines) and string and character literals (including raw strings
  `R"(...)"` and `R"delim(...)delim"`) are stripped before matching, with
  line numbers kept, so text inside them never fails.
- A violation, one per match, with the reason text in brackets:
    * the type `long double` (any whitespace between the words)
      [long double];
    * a floating-point literal with an `L` or `l` suffix: decimal with a
      point or an exponent (`0.5L`, `2.5e3l`, `1.L`) or hexadecimal with a
      `p` exponent (`0x1p-3L`) [long double literal]. Integer literals with
      an L suffix (`10L`, `0x10L`, `10UL`, `10LL`) pass;
    * a <cmath> transcendental name used as a call, `name (` with optional
      whitespace, written bare, `std::name`, `::name`, or `__builtin_name`.
      Names: sin cos tan asin acos atan atan2 sinh cosh tanh asinh acosh
      atanh exp exp2 exp10 expm1 log log2 log10 log1p pow cbrt hypot erf
      erfc tgamma lgamma sincos, each also with an `f` or `l` suffix
      [transcendental call];
    * `fma`, `fmaf`, `fmal` used as a call in the same four forms
      [fused multiply-add call];
    * `#include <random>` (spaces after `#` allowed) [random header].
  A name is matched as a whole identifier: `sine(`, `my_sin(`, and
  `sin_count` pass. `sqrt`, `std::sqrt`, and `#include <cmath>` pass.
- Exit 1 with one line per violation, exactly
  `<path>:<line>: <text>: <reason>`, where <line> is 1-based and <text> is
  the original source line with surrounding whitespace removed. Exit 1 also
  when a given directory is missing or holds no source file. Otherwise exit
  0, printing how many files were scanned.

Both workflows run it next to tools/check_fp_pragmas.py: every job of
fast.yml, and every job of full.yml that runs check_fp_pragmas.py.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "tools" / "check_engine_source.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "engine_source"
CLEAN = FIXTURES / "clean"
MUSTFAIL = FIXTURES / "mustfail"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp"}

LONG_DOUBLE = "long double"
LITERAL = "long double literal"
TRANSCENDENTAL = "transcendental call"
FMA = "fused multiply-add call"
RANDOM = "random header"
REASONS = (LONG_DOUBLE, LITERAL, TRANSCENDENTAL, FMA, RANDOM)

# Must-fail fixture (path relative to MUSTFAIL) -> (line, reason, text on that line).
MUSTFAIL_CASES = {
    "long_double.cpp": (3, LONG_DOUBLE, "long double wide = x;"),
    "long_double_split.hpp": (3, LONG_DOUBLE, "static_cast<long   double>(x)"),
    "literal_upper_l.cpp": (3, LITERAL, "0.5L"),
    "literal_lower_l.cc": (3, LITERAL, "2.5e3l"),
    "literal_hex_l.cxx": (3, LITERAL, "0x1p-3L"),
    "std_sin_call.cpp": (6, TRANSCENDENTAL, "std::sin(0.25)"),
    "bare_exp_call.h": (4, TRANSCENDENTAL, "exp (x)"),
    "global_pow_call.hh": (4, TRANSCENDENTAL, "::pow(x, 2.0)"),
    "builtin_exp_call.cpp": (3, TRANSCENDENTAL, "__builtin_exp(1.0)"),
    "builtin_sinf_call.ipp": (3, TRANSCENDENTAL, "__builtin_sinf(x)"),
    "fma_call.cpp": (4, FMA, "fma(a, b, c)"),
    "std_fmaf_call.inl": (3, FMA, "std::fmaf(a, b, c)"),
    "include_random.hxx": (3, RANDOM, "#include <random>"),
    "nested/log10_call.c": (3, TRANSCENDENTAL, "log10f(x)"),
}
FULL_JOBS_WITH_PRAGMA_CHECK_MIN = {"windows-x64", "windows-arm64", "macos-arm64", "android-build"}
FAST_JOBS = {"linux-x64", "windows-x64"}

VIOLATION = re.compile(r"^(?P<path>.+?):(?P<line>\d+): (?P<text>.*): (?P<reason>[^:]+)$")


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


def violations(out):
    """(path, line, text, reason) for each output line in the violation format."""
    found = []
    for line in out.splitlines():
        m = VIOLATION.match(line.rstrip())
        if m and m.group("reason") in REASONS:
            found.append((m.group("path"), int(m.group("line")), m.group("text"), m.group("reason")))
    return found


def source_files(root):
    return [p for p in root.rglob("*") if p.is_file() and p.suffix in SOURCE_SUFFIXES]


# ---------------------------------------------------------------- fixtures


def test_fixture_set_is_complete():
    found = {p.relative_to(MUSTFAIL).as_posix() for p in source_files(MUSTFAIL)}
    assert found == set(MUSTFAIL_CASES), sorted(found)
    assert {reason for _, reason, _ in MUSTFAIL_CASES.values()} == set(REASONS)
    assert len(source_files(CLEAN)) >= 2


def test_fixture_lines_hold_the_named_text():
    for rel, (line_no, _, text) in MUSTFAIL_CASES.items():
        lines = (MUSTFAIL / rel).read_text(encoding="utf-8").splitlines()
        assert text in lines[line_no - 1], (rel, line_no, lines[line_no - 1])


def test_clean_fixture_holds_the_near_misses():
    text = "\n".join(p.read_text(encoding="utf-8") for p in source_files(CLEAN))
    for needle in ("sine(", "sqrt(", "10L", "// ", "sin(", "long double", "R\"("):
        assert needle in text, needle


def test_clean_fixture_passes():
    code, out = run_checker(CLEAN)
    assert code == 0, out
    assert not violations(out), out
    assert re.search(rf"\b{len(source_files(CLEAN))}\b", out), (
        f"output does not give the scanned file count {len(source_files(CLEAN))}: {out}")


@pytest.mark.parametrize("name", sorted(p.name for p in source_files(CLEAN)))
def test_each_clean_file_passes_alone(tmp_path, name):
    (tmp_path / name).write_bytes((CLEAN / name).read_bytes())
    code, out = run_checker(tmp_path)
    assert code == 0, (name, out)


def test_mustfail_fixture_fails_with_one_line_per_violation():
    code, out = run_checker(MUSTFAIL)
    assert code == 1, out
    found = violations(out)
    assert len(found) == len(MUSTFAIL_CASES), out
    for rel, (line_no, reason, text) in MUSTFAIL_CASES.items():
        name = Path(rel).name
        hits = [v for v in found if v[0].replace("\\", "/").endswith(rel) and v[1] == line_no]
        assert len(hits) == 1, (rel, out)
        _, _, shown, shown_reason = hits[0]
        assert shown_reason == reason, (name, hits[0])
        assert text in shown, (name, hits[0])


@pytest.mark.parametrize("rel", sorted(MUSTFAIL_CASES))
def test_each_violating_form_fails_alone(tmp_path, rel):
    src = MUSTFAIL / rel
    target = tmp_path / src.name
    target.write_bytes(src.read_bytes())
    code, out = run_checker(tmp_path)
    assert code == 1, (rel, out)
    found = violations(out)
    assert len(found) == 1, (rel, out)
    path, line_no, text, reason = found[0]
    want_line, want_reason, want_text = MUSTFAIL_CASES[rel]
    assert Path(path).name == src.name and line_no == want_line, (rel, found[0])
    assert reason == want_reason and want_text in text, (rel, found[0])
    original = src.read_text(encoding="utf-8").splitlines()[want_line - 1].strip()
    assert text == original, (rel, text, original)


def test_block_comment_keeps_line_numbers():
    # std_sin_call.cpp has a three-line block comment above its violation.
    code, out = run_checker(MUSTFAIL)
    assert code == 1, out
    assert any(Path(v[0]).name == "std_sin_call.cpp" and v[1] == 6 for v in violations(out)), out


def test_clean_and_mustfail_together_fail():
    code, out = run_checker(CLEAN, MUSTFAIL)
    assert code == 1, out
    assert len(violations(out)) == len(MUSTFAIL_CASES), out


@pytest.mark.parametrize("line", [
    "double sine(double p);",
    "double r = std::sqrt(x) + sqrt(x) + __builtin_sqrt(x);",
    "long n = 10L;",
    "unsigned long long m = 0x10ULL + 10ul + 0xFL;",
    "float f = 1.0f;",
    "double d = 0x1p23 + 2.5e3;",
    "// std::sin(x) and long double and 1.0L",
    "/* exp(1.0) */ double ok = 1.0;",
    "const char* s = \"pow(x, y) long double 2.0L\";",
    "char c = 'L';",
    "int sin_count = 0;",
    "double y = my_sin(x) + obj_exp(x);",
    "#include <cmath>",
    "#include <cstdint>",
    "double longdouble = 1.0;",
], ids=lambda s: s[:40])
def test_allowed_lines_pass(tmp_path, line):
    (tmp_path / "ok.cpp").write_text(line + "\n", encoding="utf-8")
    code, out = run_checker(tmp_path)
    assert code == 0, (line, out)


@pytest.mark.parametrize("line, reason", [
    ("long double x = 0;", LONG_DOUBLE),
    ("double h = 1.L;", LITERAL),
    ("double h = .5l;", LITERAL),
    ("double h = 1e9L;", LITERAL),
    ("double h = 0x1.8p1l;", LITERAL),
    ("double c = cos(x);", TRANSCENDENTAL),
    ("double c = std::atan2(y, x);", TRANSCENDENTAL),
    ("float c = std::tanhf(x);", TRANSCENDENTAL),
    ("double c = ::log1p(x);", TRANSCENDENTAL),
    ("double c = __builtin_pow(x, y);", TRANSCENDENTAL),
    ("double c = exp2\t(x);", TRANSCENDENTAL),
    ("double c = fmal(a, b, c);", FMA),
    ("double c = __builtin_fma(a, b, c);", FMA),
    ("double c = ::fma(a, b, c);", FMA),
    ("#  include <random>", RANDOM),
], ids=lambda s: s[:40] if isinstance(s, str) else s)
def test_denied_lines_fail(tmp_path, line, reason):
    (tmp_path / "bad.cpp").write_text("// header\n" + line + "\n", encoding="utf-8")
    code, out = run_checker(tmp_path)
    assert code == 1, (line, out)
    found = violations(out)
    assert len(found) == 1, (line, out)
    assert found[0][1] == 2 and found[0][3] == reason, (line, found)


def test_missing_directory_fails(tmp_path):
    code, out = run_checker(tmp_path / "does-not-exist")
    assert code == 1, out


def test_directory_without_sources_fails(tmp_path):
    (tmp_path / "readme.txt").write_text("long double x = std::sin(1.0L);\n", encoding="utf-8")
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


def runs_script(job, script):
    return any(script in r for r in runs(job))


@pytest.mark.parametrize("job_id", sorted(FAST_JOBS))
def test_fast_jobs_run_source_scan(job_id):
    jobs = load("fast.yml")["jobs"]
    assert set(jobs) == FAST_JOBS
    assert runs_script(jobs[job_id], "tools/check_engine_source.py"), runs(jobs[job_id])


def full_pragma_jobs():
    jobs = load("full.yml")["jobs"]
    return {j for j, job in jobs.items() if runs_script(job, "tools/check_fp_pragmas.py")}


def test_full_pragma_jobs_include_the_flag_check_jobs():
    assert FULL_JOBS_WITH_PRAGMA_CHECK_MIN <= full_pragma_jobs(), sorted(full_pragma_jobs())


@pytest.mark.parametrize("job_id", sorted(FULL_JOBS_WITH_PRAGMA_CHECK_MIN))
def test_full_jobs_run_source_scan_next_to_pragma_check(job_id):
    job = load("full.yml")["jobs"][job_id]
    assert job_id in full_pragma_jobs()
    assert runs_script(job, "tools/check_engine_source.py"), runs(job)


def test_every_full_job_with_the_pragma_check_runs_the_source_scan():
    jobs = load("full.yml")["jobs"]
    for job_id in full_pragma_jobs():
        assert runs_script(jobs[job_id], "tools/check_engine_source.py"), (job_id, runs(jobs[job_id]))
