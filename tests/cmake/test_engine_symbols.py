"""The engine library has no undefined libm transcendental, file, thread, clock, or console symbol.

Contract with the build:

- Configure writes `<build dir>/arcani_engine_check.json` with the keys listed
  in tests/cmake/test_compile_flags.py; this file uses `engine_library` (the
  built arcani_engine static library) and `llvm_nm` (found only next to the
  pinned compiler; configure fails if it is missing there).
- ARCANI_ENGINE_TEST_EXTRA_SOURCE: test-only cache variable, documented like
  ARCANI_PIN_OVERRIDE_* in cmake/Pins.cmake and never set in presets or CI.
  When set to a source file path (the test passes an absolute path), that file
  is compiled into arcani_engine. The must-fail case sets it to
  tests/fixtures/engine/calls_std_sin.cpp.

Contract with the checker:

- `python tools/check_engine_symbols.py BUILD_DIR` reads
  BUILD_DIR/arcani_engine_check.json and runs llvm_nm on engine_library to list
  undefined symbols, both raw and demangled.
- `python tools/check_engine_symbols.py --nm-output FILE` (no build directory)
  instead checks FILE, text in llvm-nm's output format (archive member headers
  such as "version.cpp.o:", blank lines, and "<spaces>U <name>" lines, where
  <name> may contain spaces). Each name is checked as given against both the
  C-name and the C++-name lists, so synthetic input mixes raw C names and
  demangled C++ names.
- Raw names match after stripping a `__imp_` prefix and then one leading `_`.
- Exit 0 when nothing is denied. Exit 1 otherwise, with one output line per
  denied symbol (stdout or stderr) containing the symbol exactly as listed by
  llvm-nm (the text after "U ") and its family name, one of:
  "libm transcendental", "file", "thread", "clock", "console" (any case).
- Families: libm transcendentals with f and l variants (sin, cos, tan, asin,
  acos, atan, atan2, sinh, cosh, tanh, asinh, acosh, atanh, exp, exp2, expm1,
  log, log2, log10, log1p, pow, cbrt, hypot, erf, erfc, tgamma, lgamma,
  sincos); file, thread, clock, and console APIs including the C++ library
  forms and the Windows UCRT internals listed in DENIED below. sqrt, floor,
  memcpy and the other names in ALLOWED pass.

Real builds use the platform preset (windows-clang-cl or linux-clang) with
ARCANI_BUILD_TESTS=OFF, build only the arcani_engine target into a temporary
directory, on Windows through tools/dev.ps1. They skip only when cmake is not
on PATH.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "tools" / "check_engine_symbols.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "engine" / "calls_std_sin.cpp"
PRESET = "windows-clang-cl" if sys.platform == "win32" else "linux-clang"
CMAKE = shutil.which("cmake")

LIBM = "libm transcendental"

TRANSCENDENTALS = [
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
    "exp", "exp2", "expm1", "log", "log2", "log10", "log1p",
    "pow", "cbrt", "hypot", "erf", "erfc", "tgamma", "lgamma", "sincos",
]

# (symbol as llvm-nm lists it, accepted family names)
DENIED = (
    # libm: Linux raw, f and l variants, Windows import, Mach-O leading underscore.
    [(name, {LIBM}) for name in TRANSCENDENTALS]
    + [(name + "f", {LIBM}) for name in TRANSCENDENTALS]
    + [(name + "l", {LIBM}) for name in TRANSCENDENTALS]
    + [("__imp_" + name, {LIBM}) for name in ("sin", "cosf", "pow", "exp2", "log10")]
    + [("_" + name, {LIBM}) for name in ("sin", "atan2f", "tanh")]
    + [
        # file
        ("fopen", {"file"}),
        ("fopen64", {"file"}),
        ("fclose", {"file"}),
        ("fread", {"file"}),
        ("fwrite", {"file"}),
        ("fseek", {"file"}),
        ("ftell", {"file"}),
        ("_wfopen", {"file"}),
        ("__imp_fopen_s", {"file"}),
        ("std::basic_ofstream<char, std::char_traits<char> >::basic_ofstream(char const*, std::_Ios_Openmode)", {"file"}),
        ("std::basic_ifstream<char, std::char_traits<char> >::basic_ifstream(char const*, std::_Ios_Openmode)", {"file"}),
        ("std::basic_filebuf<char, std::char_traits<char> >::open(char const*, std::_Ios_Openmode)", {"file"}),
        ("public: __cdecl std::basic_ofstream<char, struct std::char_traits<char>>::basic_ofstream<char, struct std::char_traits<char>>(char const *, int, int)", {"file"}),
        # thread
        ("pthread_create", {"thread"}),
        ("pthread_mutex_lock", {"thread"}),
        ("std::thread::_M_start_thread(std::unique_ptr<std::thread::_State, std::default_delete<std::thread::_State> >, void (*)())", {"thread"}),
        ("std::thread::join()", {"thread"}),
        ("_Thrd_create", {"thread"}),
        ("__imp__Thrd_join", {"thread"}),
        ("_Thrd_hardware_concurrency", {"thread"}),
        ("_Mtx_lock", {"thread"}),
        ("__imp__Mtx_unlock", {"thread"}),
        # clock
        ("clock", {"clock"}),
        ("time", {"clock"}),
        ("gettimeofday", {"clock"}),
        ("clock_gettime", {"clock"}),
        ("timespec_get", {"clock"}),
        ("_Xtime_get_ticks", {"clock"}),
        ("__imp__Xtime_get_ticks", {"clock"}),
        ("_Query_perf_counter", {"clock"}),
        ("_Query_perf_frequency", {"clock"}),
        ("std::chrono::_V2::system_clock::now()", {"clock"}),
        ("std::chrono::_V2::steady_clock::now()", {"clock"}),
        ("std::__1::chrono::system_clock::now()", {"clock"}),
        ("std::chrono::steady_clock::now()", {"clock"}),
        # console
        ("printf", {"console"}),
        ("puts", {"console"}),
        ("putchar", {"console"}),
        ("std::cout", {"console"}),
        ("std::cerr", {"console"}),
        ("std::clog", {"console"}),
        ("std::cin", {"console"}),
        ("std::ios_base::Init::Init()", {"console"}),
        ("__declspec(dllimport) class std::basic_ostream<char, struct std::char_traits<char>> std::cout", {"console"}),
        ("__acrt_iob_func", {"console"}),
        ("__imp___acrt_iob_func", {"console"}),
        ("__stdio_common_vfprintf", {"console", "file"}),
        ("__imp___stdio_common_vsprintf", {"console", "file"}),
        ("__stdio_common_vfscanf", {"console", "file"}),
    ]
)

ALLOWED = [
    "sqrt", "sqrtf", "sqrtl", "__imp_sqrt", "_sqrt",
    "floor", "floorf", "ceil", "fabs", "fmod",
    "memcpy", "memset", "memmove", "__imp_memcpy",
    "__cxa_atexit", "__cxa_pure_virtual", "__gxx_personality_v0",
    "__security_check_cookie", "__CxxFrameHandler4", "_fltused",
    "operator new(unsigned long)", "operator delete(void*, unsigned long)",
    "std::terminate()", "std::logic_error::logic_error(char const*)",
    "std::exception::what() const", "std::__throw_length_error(char const*)",
]


def run_checker(*args):
    result = subprocess.run(
        [sys.executable, str(CHECKER), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode, result.stdout + result.stderr


def nm_text(names, form):
    """llvm-nm style output for one archive member."""
    member = "version.cpp.obj" if form == "windows" else "version.cpp.o"
    lines = ["", f"{member}:"] + [f"                 U {n}" for n in names] + [""]
    return "\n".join(lines)


def check_nm(tmp_path, text):
    path = tmp_path / "nm.txt"
    path.write_text(text, encoding="utf-8")
    return run_checker("--nm-output", path)


def assert_line_names(output, symbol, families):
    lines = [line for line in output.splitlines() if symbol in line]
    assert lines, f"no line names {symbol!r}:\n{output}"
    assert any(f.lower() in line.lower() for line in lines for f in families), (
        f"line naming {symbol!r} does not name family {sorted(families)}:\n{output}"
    )


# ---------------------------------------------------------------- synthetic


@pytest.mark.parametrize("form", ["linux", "windows"])
def test_allowed_symbols_pass(tmp_path, form):
    code, out = check_nm(tmp_path, nm_text(ALLOWED, form))
    assert code == 0, out


def test_empty_nm_output_passes(tmp_path):
    code, out = check_nm(tmp_path, nm_text([], "linux"))
    assert code == 0, out


@pytest.mark.parametrize("symbol, families", DENIED, ids=[d[0][:60] for d in DENIED])
def test_denied_symbol_fails(tmp_path, symbol, families):
    form = "windows" if ("__imp_" in symbol or "__cdecl" in symbol or "dllimport" in symbol
                         or symbol.startswith(("_Thrd", "_Mtx", "_Xtime", "_Query", "__acrt", "__stdio"))) else "linux"
    names = ALLOWED[:3] + [symbol] + ALLOWED[3:6]
    code, out = check_nm(tmp_path, nm_text(names, form))
    assert code == 1, out
    assert_line_names(out, symbol, families)


def test_every_denied_symbol_is_listed(tmp_path):
    symbols = ["sin", "fopen", "_Thrd_create", "clock_gettime", "std::cout"]
    code, out = check_nm(tmp_path, nm_text(ALLOWED + symbols, "linux"))
    assert code == 1, out
    for s, fam in zip(symbols, [LIBM, "file", "thread", "clock", "console"]):
        assert_line_names(out, s, {fam})
    for a in ("sqrt", "floor", "memcpy"):
        assert not any(re.search(rf"(?<![A-Za-z0-9_:]){a}(?![A-Za-z0-9])", line)
                       for line in out.splitlines()), out


# ------------------------------------------------------------ real builds


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


def configure_and_build_engine(build, *defines):
    code, out = run_cmake(["--preset", PRESET, "-B", str(build), "-DARCANI_BUILD_TESTS=OFF", *defines])
    if code != 0:
        return code, out
    code2, out2 = run_cmake(["--build", str(build), "--target", "arcani_engine"])
    return code2, out + out2


needs_cmake = pytest.mark.skipif(CMAKE is None, reason="cmake is not on PATH")


@pytest.fixture(scope="module")
def engine_build(tmp_path_factory):
    build = tmp_path_factory.mktemp("symbols_pass") / "build"
    code, out = configure_and_build_engine(build)
    return build, code, out


@pytest.fixture(scope="module")
def sin_build(tmp_path_factory):
    build = tmp_path_factory.mktemp("symbols_std_sin") / "build"
    code, out = configure_and_build_engine(build, f"-DARCANI_ENGINE_TEST_EXTRA_SOURCE={FIXTURE.as_posix()}")
    return build, code, out


def test_fixture_calls_std_sin_with_runtime_argument():
    text = FIXTURE.read_text(encoding="utf-8")
    assert "std::sin(" in text
    assert re.search(r"double\s+\w+\s*\(\s*double\s+\w+\s*\)\s*\{", text), text


def test_no_fault_injection_in_engine_or_presets_or_ci():
    for path in (REPO_ROOT / "engine").rglob("*"):
        if path.is_file():
            assert "calls_std_sin" not in path.read_text(encoding="utf-8", errors="replace"), path
    for path in [REPO_ROOT / "CMakePresets.json", *(REPO_ROOT / ".github").rglob("*.yml")]:
        assert "ARCANI_ENGINE_TEST_EXTRA_SOURCE" not in path.read_text(encoding="utf-8"), path


@needs_cmake
def test_symbol_check_passes_on_engine_build(engine_build):
    build, code, out = engine_build
    assert code == 0, out
    check_path = build / "arcani_engine_check.json"
    assert check_path.is_file(), f"configure did not write {check_path}"
    check = json.loads(check_path.read_text(encoding="utf-8"))
    assert Path(check["engine_library"]).is_file(), check
    code, out = run_checker(build)
    assert code == 0, out


@needs_cmake
def test_symbol_check_fails_on_std_sin_build(sin_build):
    build, code, out = sin_build
    assert code == 0, out
    code, out = run_checker(build)
    assert code == 1, out
    lines = [line for line in out.splitlines()
             if re.search(r"(?<![A-Za-z0-9])sin(?![A-Za-z0-9])", line)]
    assert lines, out
    assert any(LIBM in line.lower() for line in lines), out
