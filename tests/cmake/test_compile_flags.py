"""Every engine/ source compiles with -ffp-contract=off and no fast-math flag (AD-9).

Contract with the build:

- Top-level CMake sets CMAKE_EXPORT_COMPILE_COMMANDS ON and adds the fp flag
  for the whole project: clang `-ffp-contract=off`, clang-cl
  `/clang:-ffp-contract=off`, after any other fp option on the command line.
- arcani_engine and arcani-render (only) get warnings as errors: clang
  `-Wall -Wextra -Werror`, clang-cl `/W4 /WX`.
- Configure writes `<build dir>/arcani_engine_check.json` (file(GENERATE)), a
  JSON object with these string keys, all paths absolute:
    toolchain_name     "clang-cl" on Windows, "clang" on Linux
    toolchain_version  compiler version, equal to the llvm pin in toolchain.json
    source_dir         top-level source directory (CMAKE_SOURCE_DIR)
    compile_commands   path of the build's compile_commands.json
    engine_library     path of the built arcani_engine library
    llvm_nm            path of llvm-nm, in the same directory as the compiler

Contract with the checker:

- `python tools/check_compile_flags.py BUILD_DIR` reads
  BUILD_DIR/arcani_engine_check.json, then the compile_commands.json it names
  (entries with "directory", "file", and "command" or "arguments"). An
  engine source is an entry whose "file" lies under `<source_dir>/engine/`. Paths may mix forward and
  back slashes; the checker normalizes them.
- Exit 0 when every engine source passes. Exit 1 when any of these hold, with
  one output line per violation (stdout or stderr):
    * an engine source's effective contraction is not off, or no
      `-ffp-contract=` flag is present. For clang-cl, `/clang:` and `-clang:`
      arguments take effect after all others. The effective value is set by
      the last of `-ffp-contract=X` (X) or an fp model implying contraction
      on: -ffp-model=precise|fast|aggressive (bare or behind `/clang:`), or
      /fp:precise|fast (also -fp:) in their effective position. Strict and
      except models never turn contraction on;
    * a value-changing fp option appears (bare, behind `/clang:`, or after
      `-Xclang`): -fdenormal-fp-math= or -fdenormal-fp-math-f32= other than
      ieee, -mdaz-ftz, -fcomplex-arithmetic=basic, -mrecip and -mrecip=*,
      -fveclib=* other than none, -mfpmath=387, -mreassociate,
      -menable-no-nans, -menable-no-infs, -menable-unsafe-fp-math;
    * a fast-math flag appears on an engine source: -ffast-math, -Ofast,
      -ffp-model=fast, -ffp-model=aggressive, -funsafe-math-optimizations,
      -fassociative-math, -freciprocal-math, -ffinite-math-only,
      -fno-honor-nans, -fno-honor-infinities, -fno-signed-zeros,
      -fapprox-func, -fcx-limited-range, /fp:fast (also -fp:fast); each also
      as /clang:<flag>, -clang:<flag>, or after -Xclang;
    * an engine source's command uses an `@` response file (also behind a
      prefix);
    * there are zero engine sources.
  A flag violation line contains "<toolchain_name> <toolchain_version>" (for
  example "clang-cl 23.1.4"), the source file's base name, and the offending
  flag text (for -ffp-contract problems, at least "-ffp-contract").
  Negated forms such as -fno-fast-math are not fast-math flags.

Real configures use the platform preset (windows-clang-cl or linux-clang) with
ARCANI_BUILD_TESTS=OFF into a temporary directory; on Windows through
tools/dev.ps1 for the Visual Studio environment. They skip only when cmake is
not on PATH.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "tools" / "check_compile_flags.py"
PRESET = "windows-clang-cl" if sys.platform == "win32" else "linux-clang"
CMAKE = shutil.which("cmake")
LLVM_PIN = json.loads((REPO_ROOT / "toolchain.json").read_text(encoding="utf-8"))["llvm"]["version"]

FAST_MATH_FLAGS = [
    "-ffast-math",
    "-Ofast",
    "-ffp-model=fast",
    "-ffp-model=aggressive",
    "-funsafe-math-optimizations",
    "-fassociative-math",
    "-freciprocal-math",
    "-ffinite-math-only",
    "-fno-honor-nans",
    "-fno-honor-infinities",
    "-fno-signed-zeros",
    "-fapprox-func",
    "-fcx-limited-range",
]


def run_checker(build_dir):
    result = subprocess.run(
        [sys.executable, str(CHECKER), str(build_dir)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode, result.stdout + result.stderr


# ---------------------------------------------------------------- synthetic


def engine_file(name):
    return str(REPO_ROOT / "engine" / "src" / name)


def make_build(tmp_path, entries, toolchain=("clang-cl", "23.1.4")):
    """Writes a synthetic build directory and returns its path.

    entries: list of (file path, command string).
    """
    build = tmp_path / "build"
    build.mkdir()
    commands = [
        {"directory": str(build), "file": f, "command": cmd} for f, cmd in entries
    ]
    (build / "compile_commands.json").write_text(json.dumps(commands), encoding="utf-8")
    check = {
        "toolchain_name": toolchain[0],
        "toolchain_version": toolchain[1],
        "source_dir": REPO_ROOT.as_posix(),
        "compile_commands": str(build / "compile_commands.json"),
        "engine_library": str(build / "engine" / "arcani_engine.lib"),
        "llvm_nm": "llvm-nm",
    }
    (build / "arcani_engine_check.json").write_text(json.dumps(check), encoding="utf-8")
    return build


def clang_cl(flags, src):
    return f"clang-cl.exe /nologo -TP /DWIN32 /EHsc /O2 {flags} /Fo{src}.obj /c {src}"


def clang(flags, src):
    return f"/usr/bin/clang++ -O3 -DNDEBUG -std=c++20 {flags} -o {src}.o -c {src}"


def assert_one_line_names(output, *needles):
    lines = [line for line in output.splitlines() if all(n in line for n in needles)]
    assert lines, f"no single line names all of {needles}:\n{output}"


@pytest.mark.parametrize(
    "flags",
    [
        "/clang:-ffp-contract=off",
        "/fp:precise /clang:-ffp-contract=off",
        "/clang:-ffp-contract=fast /clang:-ffp-contract=off",
        "/clang:-ffp-contract=off /clang:-fno-fast-math",
    ],
)
def test_clang_cl_contract_off_passes(tmp_path, flags):
    src = engine_file("dsp.cpp")
    code, out = run_checker(make_build(tmp_path, [(src, clang_cl(flags, src))]))
    assert code == 0, out


@pytest.mark.parametrize(
    "flags",
    [
        "-ffp-contract=off",
        "-ffp-contract=fast -ffp-contract=off",
        "-ffp-contract=off -fno-fast-math -fno-associative-math",
    ],
)
def test_clang_contract_off_passes(tmp_path, flags):
    src = engine_file("dsp.cpp")
    build = make_build(tmp_path, [(src, clang(flags, src))], toolchain=("clang", "23.1.4"))
    code, out = run_checker(build)
    assert code == 0, out


@pytest.mark.parametrize(
    "toolchain, command",
    [
        ("clang-cl", clang_cl),
        ("clang", clang),
    ],
)
def test_contract_missing_fails(tmp_path, toolchain, command):
    src = engine_file("dsp.cpp")
    build = make_build(tmp_path, [(src, command("", src))], toolchain=(toolchain, "23.1.4"))
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, f"{toolchain} 23.1.4", "dsp.cpp", "-ffp-contract")


@pytest.mark.parametrize(
    "toolchain, flags",
    [
        ("clang-cl", "/clang:-ffp-contract=off /clang:-ffp-contract=fast"),
        ("clang-cl", "/clang:-ffp-contract=off /clang:-ffp-contract=on"),
        ("clang", "-ffp-contract=off -ffp-contract=fast"),
        ("clang", "-ffp-contract=on"),
    ],
)
def test_contract_overridden_fails(tmp_path, toolchain, flags):
    src = engine_file("dsp.cpp")
    command = clang_cl if toolchain == "clang-cl" else clang
    build = make_build(tmp_path, [(src, command(flags, src))], toolchain=(toolchain, "23.1.4"))
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, f"{toolchain} 23.1.4", "dsp.cpp", "-ffp-contract")


@pytest.mark.parametrize("flag", FAST_MATH_FLAGS)
def test_fast_math_flag_fails_clang(tmp_path, flag):
    src = engine_file("dsp.cpp")
    build = make_build(
        tmp_path, [(src, clang(f"-ffp-contract=off {flag}", src))], toolchain=("clang", "23.1.4")
    )
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, "clang 23.1.4", "dsp.cpp", flag)


@pytest.mark.parametrize("flag", FAST_MATH_FLAGS)
def test_fast_math_flag_fails_behind_clang_prefix(tmp_path, flag):
    src = engine_file("dsp.cpp")
    build = make_build(
        tmp_path, [(src, clang_cl(f"/clang:{flag} /clang:-ffp-contract=off", src))]
    )
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, "clang-cl 23.1.4", "dsp.cpp", flag)


def test_fp_fast_fails(tmp_path):
    src = engine_file("dsp.cpp")
    build = make_build(tmp_path, [(src, clang_cl("/fp:fast /clang:-ffp-contract=off", src))])
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, "clang-cl 23.1.4", "dsp.cpp", "/fp:fast")


def test_each_violating_source_gets_its_own_line(tmp_path):
    a, b, ok = engine_file("alpha.cpp"), engine_file("beta.cpp"), engine_file("gamma.cpp")
    build = make_build(
        tmp_path,
        [
            (a, clang_cl("/clang:-ffast-math /clang:-ffp-contract=off", a)),
            (ok, clang_cl("/clang:-ffp-contract=off", ok)),
            (b, clang_cl("", b)),
        ],
    )
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, "clang-cl 23.1.4", "alpha.cpp", "-ffast-math")
    assert_one_line_names(out, "clang-cl 23.1.4", "beta.cpp", "-ffp-contract")
    assert "gamma.cpp" not in out, out


def test_response_file_fails(tmp_path):
    src = engine_file("dsp.cpp")
    build = make_build(
        tmp_path, [(src, clang_cl("/clang:-ffp-contract=off @CMakeFiles/dsp.rsp", src))]
    )
    code, out = run_checker(build)
    assert code == 1, out
    assert "dsp.cpp" in out, out


def test_zero_engine_sources_fails(tmp_path):
    cli = str(REPO_ROOT / "cli" / "main.cpp")
    build = make_build(tmp_path, [(cli, clang_cl("/clang:-ffp-contract=off", cli))])
    code, out = run_checker(build)
    assert code == 1, out


def test_empty_compile_commands_fails(tmp_path):
    code, out = run_checker(make_build(tmp_path, []))
    assert code == 1, out


@pytest.mark.parametrize(
    "toolchain, flags",
    [
        ("clang", "-ffp-contract=off -ffp-model=strict"),
        ("clang-cl", "/clang:-ffp-contract=off /fp:precise"),
        ("clang-cl", "/clang:-ffp-contract=off /fp:except"),
        ("clang-cl", "/clang:-ffp-contract=off /fp:strict"),
    ],
)
def test_fp_model_that_keeps_contract_off_passes(tmp_path, toolchain, flags):
    """clang-cl evaluates /clang: arguments after all others; strict and except never turn contraction on."""
    src = engine_file("dsp.cpp")
    command = clang_cl if toolchain == "clang-cl" else clang
    build = make_build(tmp_path, [(src, command(flags, src))], toolchain=(toolchain, "23.1.4"))
    code, out = run_checker(build)
    assert code == 0, out


@pytest.mark.parametrize(
    "toolchain, flags, named",
    [
        ("clang", "-ffp-contract=off -ffp-model=precise", "-ffp-model=precise"),
        ("clang-cl", "/clang:-ffp-contract=off /clang:-ffp-model=precise", "-ffp-model=precise"),
    ],
)
def test_fp_model_that_turns_contract_on_fails(tmp_path, toolchain, flags, named):
    src = engine_file("dsp.cpp")
    command = clang_cl if toolchain == "clang-cl" else clang
    build = make_build(tmp_path, [(src, command(flags, src))], toolchain=(toolchain, "23.1.4"))
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, f"{toolchain} 23.1.4", "dsp.cpp", named)


@pytest.mark.parametrize(
    "flags, named",
    [
        ("/clang:-ffp-contract=off -Xclang -ffast-math", "-ffast-math"),
        ("-clang:-ffast-math /clang:-ffp-contract=off", "-ffast-math"),
        ("-fp:fast /clang:-ffp-contract=off", "-fp:fast"),
    ],
)
def test_other_fast_math_spellings_fail(tmp_path, flags, named):
    src = engine_file("dsp.cpp")
    code, out = run_checker(make_build(tmp_path, [(src, clang_cl(flags, src))]))
    assert code == 1, out
    assert_one_line_names(out, "clang-cl 23.1.4", "dsp.cpp", named)


def test_arguments_form_fast_math_fails(tmp_path):
    src = engine_file("dsp.cpp")
    build = make_build(tmp_path, [(src, "unused")], toolchain=("clang", "23.1.4"))
    commands_path = build / "compile_commands.json"
    entries = json.loads(commands_path.read_text(encoding="utf-8"))
    del entries[0]["command"]
    entries[0]["arguments"] = ["clang++", "-O3", "-ffp-contract=off", "-ffast-math", "-c", src]
    commands_path.write_text(json.dumps(entries), encoding="utf-8")
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, "clang 23.1.4", "dsp.cpp", "-ffast-math")


@pytest.mark.parametrize("flags", ["/clang:@dsp.rsp", "-Xclang @dsp.rsp"])
def test_prefixed_response_file_fails(tmp_path, flags):
    src = engine_file("dsp.cpp")
    build = make_build(tmp_path, [(src, clang_cl(f"/clang:-ffp-contract=off {flags}", src))])
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, "clang-cl 23.1.4", "dsp.cpp", "@dsp.rsp")


VALUE_CHANGING_FLAGS = [
    "-fdenormal-fp-math=preserve-sign",
    "-fdenormal-fp-math-f32=positive-zero",
    "-mdaz-ftz",
    "-fcomplex-arithmetic=basic",
    "-mrecip",
    "-mrecip=all",
    "-fveclib=libmvec",
    "-mfpmath=387",
    "-mreassociate",
    "-menable-no-nans",
    "-menable-no-infs",
    "-menable-unsafe-fp-math",
]


@pytest.mark.parametrize("form", ["bare", "clang_prefix", "xclang"])
@pytest.mark.parametrize("flag", VALUE_CHANGING_FLAGS)
def test_value_changing_fp_option_fails(tmp_path, flag, form):
    src = engine_file("dsp.cpp")
    if form == "bare":
        build = make_build(
            tmp_path, [(src, clang(f"-ffp-contract=off {flag}", src))], toolchain=("clang", "23.1.4")
        )
        toolchain = "clang 23.1.4"
    else:
        written = f"/clang:{flag}" if form == "clang_prefix" else f"-Xclang {flag}"
        build = make_build(tmp_path, [(src, clang_cl(f"/clang:-ffp-contract=off {written}", src))])
        toolchain = "clang-cl 23.1.4"
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, toolchain, "dsp.cpp", flag)


@pytest.mark.parametrize(
    "flag", ["-fdenormal-fp-math=ieee", "-fdenormal-fp-math-f32=ieee", "-fveclib=none"]
)
def test_default_valued_fp_options_pass(tmp_path, flag):
    src = engine_file("dsp.cpp")
    build = make_build(
        tmp_path, [(src, clang(f"-ffp-contract=off {flag}", src))], toolchain=("clang", "23.1.4")
    )
    code, out = run_checker(build)
    assert code == 0, out


# --------------------------------------------------------- real configures


def cmake_command(args):
    if sys.platform == "win32":
        return [
            "powershell", "-NoProfile", "-File", str(REPO_ROOT / "tools" / "dev.ps1"),
            "cmake", *args,
        ]
    return [CMAKE, *args]


def configure(build_dir, *defines):
    result = subprocess.run(
        cmake_command(["--preset", PRESET, "-B", str(build_dir), "-DARCANI_BUILD_TESTS=OFF", *defines]),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        env=os.environ.copy(),
    )
    return result.returncode, result.stdout + result.stderr


needs_cmake = pytest.mark.skipif(CMAKE is None, reason="cmake is not on PATH")


@pytest.fixture(scope="module")
def preset_build(tmp_path_factory):
    build = tmp_path_factory.mktemp("flags_pass") / "build"
    code, out = configure(build)
    return build, code, out


@pytest.fixture(scope="module")
def fast_math_build(tmp_path_factory):
    build = tmp_path_factory.mktemp("flags_fast_math") / "build"
    flag = "/clang:-ffast-math" if sys.platform == "win32" else "-ffast-math"
    code, out = configure(build, f"-DCMAKE_CXX_FLAGS={flag}")
    return build, code, out


def read_check_json(build):
    path = build / "arcani_engine_check.json"
    assert path.is_file(), f"configure did not write {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def split_command(command):
    return shlex.split(command, posix=(os.name != "nt"))


def last_contract_value(tokens):
    value = None
    for t in tokens:
        bare = t[len("/clang:"):] if t.startswith("/clang:") else t
        if bare.startswith("-ffp-contract="):
            value = bare.split("=", 1)[1]
    return value


@needs_cmake
def test_check_json_written_by_configure(preset_build):
    build, code, out = preset_build
    assert code == 0, out
    check = read_check_json(build)
    for key in ("toolchain_name", "toolchain_version", "source_dir",
                "compile_commands", "engine_library", "llvm_nm"):
        assert isinstance(check.get(key), str) and check[key], f"missing key {key}: {check}"
    assert check["toolchain_name"] == ("clang-cl" if sys.platform == "win32" else "clang")
    assert check["toolchain_version"] == LLVM_PIN
    assert Path(check["source_dir"]).resolve() == REPO_ROOT
    assert Path(check["compile_commands"]).is_file()


@needs_cmake
def test_llvm_nm_is_next_to_pinned_compiler(preset_build):
    build, code, out = preset_build
    assert code == 0, out
    check = read_check_json(build)
    nm = Path(check["llvm_nm"])
    assert nm.is_file(), nm
    assert nm.stem == "llvm-nm", nm
    cache = (build / "CMakeCache.txt").read_text(encoding="utf-8")
    compiler = next(
        line.split("=", 1)[1]
        for line in cache.splitlines()
        if line.startswith("CMAKE_CXX_COMPILER:")
    )
    assert nm.resolve().parent == Path(compiler).resolve().parent, (nm, compiler)


@needs_cmake
def test_whole_project_has_contract_off_and_targets_have_warnings(preset_build):
    build, code, out = preset_build
    assert code == 0, out
    check = read_check_json(build)
    entries = json.loads(Path(check["compile_commands"]).read_text(encoding="utf-8"))
    by_name = {Path(e["file"]).as_posix().split("/")[-2] + "/" + Path(e["file"]).name: e for e in entries}
    for name in ("src/version.cpp", "cli/main.cpp"):
        assert name in by_name, f"{name} not in compile_commands: {sorted(by_name)}"
        tokens = split_command(by_name[name]["command"])
        assert last_contract_value(tokens) == "off", by_name[name]["command"]
        if sys.platform == "win32":
            assert "/W4" in tokens and "/WX" in tokens, by_name[name]["command"]
        else:
            for flag in ("-Wall", "-Wextra", "-Werror"):
                assert flag in tokens, by_name[name]["command"]


@needs_cmake
def test_flag_check_passes_on_preset_configure(preset_build):
    build, code, out = preset_build
    assert code == 0, out
    code, out = run_checker(build)
    assert code == 0, out


@needs_cmake
def test_flag_check_fails_on_fast_math_configure(fast_math_build):
    build, code, out = fast_math_build
    assert code == 0, out
    check = read_check_json(build)
    code, out = run_checker(build)
    assert code == 1, out
    toolchain = f"{check['toolchain_name']} {check['toolchain_version']}"
    assert_one_line_names(out, toolchain, "version.cpp", "-ffast-math")
