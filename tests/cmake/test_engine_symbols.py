"""The engine library has no undefined libm transcendental, file, thread, clock, console, fenv,
randomness, fused multiply-add, or quad precision symbol, and the WAV writer has no randomness
or clock symbol.

Contract with the build:

- Configure writes `<build dir>/arcani_engine_check.json` with the keys listed
  in tests/cmake/test_compile_flags.py; this file uses `engine_library` (the
  built arcani_engine static library) and `llvm_nm` (found only next to the
  pinned compiler, or on macOS through `xcrun --find llvm-nm`, else `nm` next
  to the compiler; configure fails if it is missing there).
- ARCANI_ENGINE_TEST_EXTRA_SOURCE: test-only cache variable, documented like
  ARCANI_PIN_OVERRIDE_* in cmake/Pins.cmake and never set in presets or CI.
  When set to a source file path (the test passes an absolute path), that file
  is compiled into arcani_engine. The must-fail cases set it to
  tests/fixtures/engine/calls_std_sin.cpp and (Story 1.2)
  tests/fixtures/engine/calls_fesetenv.cpp.

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
  "libm transcendental", "file", "thread", "clock", "console", "fenv" (any case).
- Family "fenv" (Story 1.2): the C floating-point environment calls that set
  or save the mode or the exception flags (fesetenv, fegetenv, feholdexcept,
  feupdateenv, fesetround, feenableexcept, fedisableexcept, fesetexceptflag,
  feclearexcept, feraiseexcept, fesetexcept) and the MSVC mode calls
  (_controlfp, _controlfp_s, _control87, __control87_2, _clearfp, _fpreset,
  _set_controlfp), in their raw,
  Windows import, and Mach-O underscore forms. The engine sets its denormal
  mode with MXCSR / FPCR intrinsics only (AD-9), which leave no symbol.
- Families: libm transcendentals with f and l variants (sin, cos, tan, asin,
  acos, atan, atan2, sinh, cosh, tanh, asinh, acosh, atanh, exp, exp2, exp10,
  expm1, log, log2, log10, log1p, pow, cbrt, hypot, erf, erfc, tgamma, lgamma,
  lgamma_r, sincos, plus the pi, m1, p1, rootn, pown, powr, compoundn,
  Bessel, complex, MSVC __std_smf_, and vector _ZGV forms); file, thread, clock, and console APIs including the C++ library
  forms and the Windows UCRT internals listed in DENIED below. sqrt, floor,
  memcpy and the other names in ALLOWED pass.

Story 1.6 additions:

- Families "randomness", "fused multiply-add", and "quad precision" (any
  case), in the raw, Windows import (`__imp_`), and Mach-O underscore forms:
    * randomness: rand, srand, rand_r, rand_s, random, srandom, initstate,
      setstate, the rand48 family (drand48, erand48, lrand48, nrand48,
      mrand48, jrand48, srand48, seed48, lcong48), arc4random,
      arc4random_uniform, arc4random_buf, getrandom, getentropy,
      BCryptGenRandom, SystemFunction036, CryptGenRandom, ProcessPrng, and the
      demangled C++ forms of std::random_device (libstdc++, libc++ `std::__1`)
      and MSVC `std::_Random_device`. Time-based seeding is the existing clock
      family.
    * fused multiply-add: fma, fmaf, fmal.
    * quad precision: the compiler-rt tf helpers __addtf3, __subtf3,
      __multf3, __divtf3, __negtf2, __powitf2, the __extend*tf2 and
      __trunctf*2 families, the __fix*tf* and __float*tf* families, and the
      tf2 comparisons (__eqtf2, __netf2, __lttf2, __letf2, __gttf2, __getf2,
      __unordtf2, __cmptf2). normalize_c_name strips one `_`, so Mach-O
      `___addtf3` arrives as `__addtf3`. The double and float helpers
      (__adddf3, __extendsfdf2, ...) and fmax, fmin, fmod pass.
- WAV writer: configure also writes the key `wav_writer_library` into
  arcani_engine_check.json, the path of the built arcani_cli_core static
  library (cli/wav.cpp, cli/report.cpp). `check_engine_symbols.py BUILD_DIR`
  checks engine_library against every family and wav_writer_library against
  the randomness and clock families only. It exits 1 when either has a
  denied symbol, or when wav_writer_library is missing from the JSON or names
  no file (that line names the key or the path). A denied WAV writer line
  names the symbol and its family, and the output names the arcani_cli_core
  library path.
- `python tools/check_engine_symbols.py --wav-writer-nm-output FILE` checks
  FILE (llvm-nm text) as the WAV writer: randomness and clock families only,
  so fopen, fwrite, printf, sin, pthread_create, and fma pass there. Exit
  codes and line format as for --nm-output.
- ARCANI_CLI_TEST_EXTRA_SOURCE: test-only cache variable in cli/CMakeLists.txt,
  mirroring ARCANI_ENGINE_TEST_EXTRA_SOURCE: one extra source compiled into
  arcani_cli_core. Never set in presets or CI. The must-fail case sets it to
  tests/fixtures/engine/cli/calls_rand.cpp.
- Real builds build the targets arcani_engine and arcani_cli_core.
- Engine must-fail fixture tests/fixtures/engine/calls_rand_fma_quad.cpp:
  runtime calls to rand, std::random_device, and std::fma; where the compiler
  defines __SIZEOF_FLOAT128__, __float128 arithmetic plus the defined marker
  function arc_test_float128_present. The quad precision line is required
  only when llvm-nm lists that marker as defined in the built library.

Real builds use the platform preset (windows-clang-cl on Windows,
macos-appleclang on macOS, linux-clang otherwise) with
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
FENV_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "engine" / "calls_fesetenv.cpp"
RANDOM_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "engine" / "calls_rand_fma_quad.cpp"
CLI_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "engine" / "cli" / "calls_rand.cpp"
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
CMAKE = shutil.which("cmake")

LIBM = "libm transcendental"
FENV = "fenv"
RANDOM = "randomness"
FMA = "fused multiply-add"
QUAD = "quad precision"

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

# One row per added pattern and per previously untested alternative.
DENIED += [
    # libm
    ("exp10", {LIBM}),
    ("lgamma_r", {LIBM}),
    ("lgammaf_r", {LIBM}),
    ("lgammal_r", {LIBM}),
    ("__sin_finite", {LIBM}),
    ("__sincos_stret", {LIBM}),
    ("sinpi", {LIBM}),
    ("cospif", {LIBM}),
    ("atan2pil", {LIBM}),
    ("exp2m1", {LIBM}),
    ("log10p1f", {LIBM}),
    ("rootn", {LIBM}),
    ("pown", {LIBM}),
    ("powr", {LIBM}),
    ("compoundn", {LIBM}),
    ("__sinpi", {LIBM}),
    ("__cospif", {LIBM}),
    ("__tanpi", {LIBM}),
    ("j0", {LIBM}),
    ("y1f", {LIBM}),
    ("jnl", {LIBM}),
    ("cexp", {LIBM}),
    ("cpowf", {LIBM}),
    ("csqrtl", {LIBM}),
    ("cabs", {LIBM}),
    ("__std_smf_cyl_bessel_i", {LIBM}),
    ("_ZGVbN2v_sin", {LIBM}),
    ("_ZGVdN4vv_pow", {LIBM}),
    # file
    ("__isoc99_fscanf", {"file"}),
    ("__isoc23_vfscanf", {"file"}),
    ("__fprintf_chk", {"file"}),
    ("__vfprintf_chk", {"file"}),
    ("__std_fs_open_handle", {"file"}),
    ("std::filesystem::__cxx11::path::_M_split_cmpts()", {"file"}),
    ("__imp_CreateFileW", {"file"}),
    ("ReadFile", {"file"}),
    # console
    ("__isoc99_scanf", {"console"}),
    ("__isoc23_vscanf", {"console"}),
    ("__printf_chk", {"console"}),
    ("__vprintf_chk", {"console"}),
    ("WriteConsoleW", {"console"}),
    ("std::wcout", {"console"}),
    ("std::print(std::basic_format_string<char>)", {"console"}),
    # thread
    ("_Cnd_wait", {"thread"}),
    ("_Smtx_lock_exclusive", {"thread"}),
    ("__std_atomic_wait_direct", {"thread"}),
    ("__std_atomic_notify_one_direct", {"thread"}),
    ("WaitOnAddress", {"thread"}),
    ("WakeByAddressAll", {"thread"}),
    ("std::__1::__libcpp_atomic_wait(void const volatile*, long long)", {"thread"}),
    ("sched_yield", {"thread"}),
    ("std::mutex::lock()", {"thread"}),
    ("std::condition_variable::wait(std::unique_lock<std::mutex>&)", {"thread"}),
    ("std::jthread::join()", {"thread"}),
    # clock
    ("GetTickCount64", {"clock"}),
    ("GetSystemTimeAsFileTime", {"clock"}),
    ("mach_absolute_time", {"clock"}),
    ("localtime", {"clock"}),
    ("localtime_r", {"clock"}),
    ("_localtime64_s", {"clock"}),
    ("gmtime_r", {"clock"}),
    ("_mktime64", {"clock"}),
    ("ctime", {"clock"}),
    ("asctime_s", {"clock"}),
    ("strftime", {"clock"}),
    ("_tzset", {"clock"}),
]

# Story 1.2: the fenv family. The engine's denormal guard uses intrinsics only.
DENIED += [
    ("fesetenv", {FENV}),
    ("fegetenv", {FENV}),
    ("feholdexcept", {FENV}),
    ("feupdateenv", {FENV}),
    ("fesetround", {FENV}),
    ("__imp_fesetenv", {FENV}),
    ("__imp_feholdexcept", {FENV}),
    ("_fesetenv", {FENV}),
    ("_fesetround", {FENV}),
    ("_controlfp", {FENV}),
    ("_controlfp_s", {FENV}),
    ("__imp__controlfp", {FENV}),
    ("_control87", {FENV}),
    ("__control87_2", {FENV}),
    ("feenableexcept", {FENV}),
    ("fedisableexcept", {FENV}),
    ("fesetexceptflag", {FENV}),
    ("feclearexcept", {FENV}),
    ("feraiseexcept", {FENV}),
    ("fesetexcept", {FENV}),
    ("__imp_feclearexcept", {FENV}),
    ("_clearfp", {FENV}),
    ("_fpreset", {FENV}),
    ("_set_controlfp", {FENV}),
    ("__imp__fpreset", {FENV}),
]

# Story 1.6: randomness, fused multiply-add, and quad precision.
RANDOM_C_NAMES = [
    "rand", "srand", "rand_r", "rand_s", "random", "srandom", "initstate", "setstate",
    "drand48", "erand48", "lrand48", "nrand48", "mrand48", "jrand48", "srand48", "seed48",
    "lcong48", "arc4random", "arc4random_uniform", "arc4random_buf", "getrandom", "getentropy",
    "BCryptGenRandom", "SystemFunction036", "CryptGenRandom", "ProcessPrng",
]
QUAD_HELPERS = [
    "__addtf3", "__subtf3", "__multf3", "__divtf3", "__negtf2", "__powitf2",
    "__extenddftf2", "__extendsftf2", "__extendxftf2", "__extendhftf2",
    "__trunctfdf2", "__trunctfsf2", "__trunctfxf2", "__trunctfhf2",
    "__fixtfsi", "__fixtfdi", "__fixtfti", "__fixunstfsi", "__fixunstfdi", "__fixunstfti",
    "__floatsitf", "__floatditf", "__floattitf", "__floatunsitf", "__floatunditf", "__floatuntitf",
    "__eqtf2", "__netf2", "__lttf2", "__letf2", "__gttf2", "__getf2", "__unordtf2", "__cmptf2",
]
RANDOM_DEVICE_FORMS = [
    "std::random_device::_M_init(std::__cxx11::basic_string<char, std::char_traits<char>, "
    "std::allocator<char> > const&)",
    "std::random_device::_M_getval()",
    "std::random_device::_M_fini()",
    "std::__1::random_device::random_device(std::__1::basic_string<char, "
    "std::__1::char_traits<char>, std::__1::allocator<char> > const&)",
    "std::__1::random_device::operator()()",
    "std::__1::random_device::~random_device()",
    "unsigned int __cdecl std::_Random_device(void)",
    "__declspec(dllimport) unsigned int __cdecl std::_Random_device(void)",
]
DENIED += (
    [(name, {RANDOM}) for name in RANDOM_C_NAMES]
    + [("__imp_" + name, {RANDOM}) for name in ("rand", "rand_s", "BCryptGenRandom",
                                                  "SystemFunction036", "ProcessPrng")]
    + [("_" + name, {RANDOM}) for name in ("rand", "random", "arc4random", "arc4random_buf",
                                            "getentropy")]
    + [(name, {RANDOM}) for name in RANDOM_DEVICE_FORMS]
    + [(name, {FMA}) for name in ("fma", "fmaf", "fmal", "__imp_fma", "_fma", "_fmaf")]
    + [(name, {QUAD}) for name in QUAD_HELPERS]
    + [("_" + name, {QUAD}) for name in ("__addtf3", "__multf3", "__extenddftf2",
                                          "__trunctfdf2", "__lttf2")]
    + [("__imp_" + name, {QUAD}) for name in ("__addtf3", "__divtf3")]
)

# The WAV writer is checked against the randomness and clock families only.
WAV_WRITER_DENIED = [
    ("rand", {RANDOM}),
    ("__imp_rand", {RANDOM}),
    ("srand", {RANDOM}),
    ("BCryptGenRandom", {RANDOM}),
    ("std::random_device::_M_getval()", {RANDOM}),
    ("time", {"clock"}),
    ("_time64", {"clock"}),
    ("clock_gettime", {"clock"}),
    ("std::chrono::_V2::system_clock::now()", {"clock"}),
    ("std::chrono::steady_clock::now()", {"clock"}),
    ("_Xtime_get_ticks", {"clock"}),
]
WAV_WRITER_ALLOWED = [
    "fopen", "fwrite", "fclose", "__imp_fopen", "printf", "snprintf", "__stdio_common_vsprintf",
    "sin", "pthread_create", "fma", "__addtf3", "memcpy", "operator new(unsigned long)",
    "std::__throw_length_error(char const*)",
]

# Near misses of the Story 1.6 patterns; they pass in the engine check.
ALLOWED_STORY_1_6 = [
    "fmax", "fmin", "fmaxf", "fminl", "fmod", "fmodf",
    "__adddf3", "__muldf3", "__extendsfdf2", "__truncdfsf2", "__fixdfsi", "__floatsidf",
    "brand", "randomize_table", "strand",
]

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


# ------------------------------------------------- synthetic, Story 1.6


@pytest.mark.parametrize("form", ["linux", "windows"])
def test_story_1_6_near_misses_pass(tmp_path, form):
    code, out = check_nm(tmp_path, nm_text(ALLOWED + ALLOWED_STORY_1_6, form))
    assert code == 0, out


def test_every_new_family_is_listed_at_once(tmp_path):
    symbols = ["rand", "std::random_device::_M_getval()", "fma", "__multf3"]
    code, out = check_nm(tmp_path, nm_text(ALLOWED + symbols, "linux"))
    assert code == 1, out
    for s, fam in zip(symbols, [RANDOM, RANDOM, FMA, QUAD]):
        assert_line_names(out, s, {fam})


def test_mach_o_triple_underscore_quad_helper_fails(tmp_path):
    # Mach-O adds one underscore: ___addtf3 is __addtf3 after normalize_c_name.
    code, out = check_nm(tmp_path, nm_text(["___addtf3", "___trunctfdf2"], "linux"))
    assert code == 1, out
    assert_line_names(out, "___addtf3", {QUAD})
    assert_line_names(out, "___trunctfdf2", {QUAD})


def check_wav_writer_nm(tmp_path, text):
    path = tmp_path / "nm-cli.txt"
    path.write_text(text, encoding="utf-8")
    return run_checker("--wav-writer-nm-output", path)


def test_wav_writer_allowed_symbols_pass(tmp_path):
    """fopen and the other file, console, libm, thread, fma, and quad names pass in the WAV writer."""
    code, out = check_wav_writer_nm(tmp_path, nm_text(WAV_WRITER_ALLOWED, "linux"))
    assert code == 0, out


@pytest.mark.parametrize("symbol, families", WAV_WRITER_DENIED,
                         ids=[d[0][:60] for d in WAV_WRITER_DENIED])
def test_wav_writer_denied_symbol_fails(tmp_path, symbol, families):
    names = WAV_WRITER_ALLOWED[:4] + [symbol] + WAV_WRITER_ALLOWED[4:]
    code, out = check_wav_writer_nm(tmp_path, nm_text(names, "linux"))
    assert code == 1, out
    assert_line_names(out, symbol, families)
    for allowed in ("fopen", "fwrite", "pthread_create"):
        assert not any(allowed in line and "family" in line.lower() for line in out.splitlines()), out


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
    code2, out2 = run_cmake(["--build", str(build), "--target", "arcani_engine", "arcani_cli_core"])
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


def test_fenv_fixture_calls_fesetenv_with_runtime_argument():
    text = FENV_FIXTURE.read_text(encoding="utf-8")
    assert "std::fesetenv(" in text
    assert re.search(r"int\s+\w+\s*\(\s*const\s+std::fenv_t\s*\*\s*\w+\s*\)\s*\{", text), text


def test_no_fault_injection_in_engine_or_presets_or_ci():
    for folder in ("engine", "cli"):
        for path in (REPO_ROOT / folder).rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                for name in ("calls_std_sin", "calls_fesetenv", "calls_rand_fma_quad", "calls_rand"):
                    assert name not in text, (path, name)
    for path in [REPO_ROOT / "CMakePresets.json", *(REPO_ROOT / ".github").rglob("*.yml")]:
        text = path.read_text(encoding="utf-8")
        assert "ARCANI_ENGINE_TEST_EXTRA_SOURCE" not in text, path
        assert "ARCANI_CLI_TEST_EXTRA_SOURCE" not in text, path


def test_cli_cmake_declares_the_test_only_extra_source():
    text = (REPO_ROOT / "cli" / "CMakeLists.txt").read_text(encoding="utf-8")
    assert re.search(r"set\(\s*ARCANI_CLI_TEST_EXTRA_SOURCE\s+\"\"\s+CACHE\s+FILEPATH", text), (
        "cli/CMakeLists.txt must declare ARCANI_CLI_TEST_EXTRA_SOURCE as a FILEPATH cache "
        "variable with an empty default, like ARCANI_ENGINE_TEST_EXTRA_SOURCE")


def test_random_fixture_calls_each_source_with_runtime_arguments():
    text = RANDOM_FIXTURE.read_text(encoding="utf-8")
    assert "std::rand()" in text
    assert "std::random_device" in text
    assert re.search(r"double\s+\w+\s*\(\s*double\s+a,\s*double\s+b,\s*double\s+c\s*\)\s*\{\s*"
                     r"return\s+std::fma\(a,\s*b,\s*c\);", text), text
    assert "#if defined(__SIZEOF_FLOAT128__)" in text
    assert "__float128" in text and "arc_test_float128_present" in text


def test_cli_fixture_calls_rand():
    text = CLI_FIXTURE.read_text(encoding="utf-8")
    assert "std::rand()" in text


@pytest.fixture(scope="module")
def fenv_build(tmp_path_factory):
    build = tmp_path_factory.mktemp("symbols_fesetenv") / "build"
    code, out = configure_and_build_engine(
        build, f"-DARCANI_ENGINE_TEST_EXTRA_SOURCE={FENV_FIXTURE.as_posix()}")
    return build, code, out


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


@needs_cmake
def test_symbol_check_fails_on_fesetenv_build(fenv_build):
    build, code, out = fenv_build
    assert code == 0, out
    code, out = run_checker(build)
    assert code == 1, out
    lines = [line for line in out.splitlines() if "fesetenv" in line]
    assert lines, out
    assert any(FENV in line.lower() for line in lines), out


# ------------------------------------------------------ real builds, Story 1.6


def read_check(build):
    return json.loads((build / "arcani_engine_check.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def random_build(tmp_path_factory):
    build = tmp_path_factory.mktemp("symbols_rand_fma_quad") / "build"
    code, out = configure_and_build_engine(
        build, f"-DARCANI_ENGINE_TEST_EXTRA_SOURCE={RANDOM_FIXTURE.as_posix()}")
    return build, code, out


@pytest.fixture(scope="module")
def cli_rand_build(tmp_path_factory):
    build = tmp_path_factory.mktemp("symbols_cli_rand") / "build"
    code, out = configure_and_build_engine(
        build, f"-DARCANI_CLI_TEST_EXTRA_SOURCE={CLI_FIXTURE.as_posix()}")
    return build, code, out


def word_lines(out, word):
    return [line for line in out.splitlines()
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", line)]


def defines_symbol(build, name):
    """True when llvm-nm lists `name` as a defined symbol of the engine library."""
    check = read_check(build)
    result = subprocess.run([check["llvm_nm"], check["engine_library"]], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=300)
    assert result.returncode == 0, result.stderr
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-2] not in ("U", "w", "v") and parts[-1].lstrip("_") == name:
            return True
    return False


@needs_cmake
def test_check_json_names_the_wav_writer_library(engine_build):
    build, code, out = engine_build
    assert code == 0, out
    check = read_check(build)
    library = check.get("wav_writer_library")
    assert isinstance(library, str) and library, f"missing key wav_writer_library: {check}"
    assert Path(library).is_absolute(), library
    assert "arcani_cli_core" in Path(library).name, library
    assert Path(library).is_file(), f"{library} was not built"


@needs_cmake
def test_symbol_check_fails_on_rand_fma_quad_build(random_build):
    build, code, out = random_build
    assert code == 0, out
    code, out = run_checker(build)
    assert code == 1, out
    rand_lines = word_lines(out, "rand")
    assert rand_lines and any(RANDOM in line.lower() for line in rand_lines), out
    device_lines = [line for line in out.splitlines() if "random_device" in line.lower()]
    assert device_lines and any(RANDOM in line.lower() for line in device_lines), out
    fma_lines = word_lines(out, "fma")
    assert fma_lines and any(FMA in line.lower() for line in fma_lines), out
    if defines_symbol(build, "arc_test_float128_present"):
        quad_lines = [line for line in out.splitlines() if re.search(r"__\w*tf\w*\d", line)]
        assert quad_lines and any(QUAD in line.lower() for line in quad_lines), out


@needs_cmake
def test_symbol_check_fails_on_cli_rand_build(cli_rand_build):
    build, code, out = cli_rand_build
    assert code == 0, out
    code, out = run_checker(build)
    assert code == 1, out
    rand_lines = word_lines(out, "rand")
    assert rand_lines and any(RANDOM in line.lower() for line in rand_lines), out
    assert "arcani_cli_core" in out, out


@needs_cmake
def test_symbol_check_fails_when_wav_writer_library_is_missing(engine_build, tmp_path):
    build, code, out = engine_build
    assert code == 0, out
    check = read_check(build)
    missing = tmp_path / "missing" / "arcani_cli_core.lib"
    fake = tmp_path / "fake-build"
    fake.mkdir()
    (fake / "arcani_engine_check.json").write_text(
        json.dumps(dict(check, wav_writer_library=str(missing))), encoding="utf-8")
    code, out = run_checker(fake)
    assert code == 1, out
    assert "arcani_cli_core" in out or "wav_writer_library" in out, out


@needs_cmake
def test_symbol_check_fails_when_wav_writer_key_is_absent(engine_build, tmp_path):
    build, code, out = engine_build
    assert code == 0, out
    check = {k: v for k, v in read_check(build).items() if k != "wav_writer_library"}
    fake = tmp_path / "fake-build"
    fake.mkdir()
    (fake / "arcani_engine_check.json").write_text(json.dumps(check), encoding="utf-8")
    code, out = run_checker(fake)
    assert code == 1, out
    assert "wav_writer_library" in out, out
