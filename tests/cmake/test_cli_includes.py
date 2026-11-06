"""cli/ sources reach the engine only through its public header (Story 1.4 Include rule).

Contract with the checker, tools/check_cli_includes.py (standard library only):

- `python tools/check_cli_includes.py BUILD_DIR` reads
  BUILD_DIR/arcani_engine_check.json (written by configure; keys
  toolchain_name, toolchain_version, source_dir, compile_commands, see
  tests/cmake/test_compile_flags.py), then the compile_commands.json it names
  (entries with "directory", "file", and "command" or "arguments").
- A CLI source is an entry whose "file" lies under `<source_dir>/cli/`.
  Paths may mix forward and back slashes and may be relative to the entry's
  "directory"; the checker normalizes them (case-insensitively on Windows).
- An include path option is one of -I, /I, -isystem, -iquote, -idirafter,
  -imsvc, /imsvc, -external:I, /external:I, joined to its path (`-Ipath`) or
  followed by it as the next token (`-I path`), bare or behind /clang: or
  -clang:.
- Exit 1 when any CLI source has an include path equal to or under
  `<source_dir>/engine/src`, with one line per violation naming the
  source's base name and the include path as written; when a CLI source's
  command uses an `@` response file (it would hide the include paths); when
  there is no CLI source; or when the build facts cannot be read.
- Exit 0 otherwise. Other sources (engine/, tests/) are not checked, and a
  path that only starts with the same letters (`engine/srcx`) is not under
  engine/src.

Real configures use the platform preset with ARCANI_BUILD_TESTS=OFF into a
temporary directory (on Windows through tools/dev.ps1); the must-fail
configure adds an include path into engine/src through CMAKE_CXX_FLAGS, so
cli/main.cpp's command carries it. They skip only when cmake is not on PATH.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "tools" / "check_cli_includes.py"
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
CMAKE = shutil.which("cmake")
ENGINE_SRC = (REPO_ROOT / "engine" / "src").as_posix()
ENGINE_INCLUDE = (REPO_ROOT / "engine" / "include").as_posix()
TABLES = (REPO_ROOT / "tests" / "assertions").as_posix()


def run_checker(build_dir):
    result = subprocess.run(
        [sys.executable, str(CHECKER), str(build_dir)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode, result.stdout + result.stderr


def make_build(tmp_path, entries, toolchain=("clang-cl", "23.1.4")):
    """Writes a synthetic build directory; entries: (file path, command string)."""
    build = tmp_path / "build"
    (build / "cli").mkdir(parents=True)
    commands = [
        {"directory": str(build / "cli"), "file": f, "command": cmd} for f, cmd in entries
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


def cli_file(name):
    return str(REPO_ROOT / "cli" / name)


def engine_file(name):
    return str(REPO_ROOT / "engine" / "src" / name)


def clang_cl(flags, src):
    return f"clang-cl.exe /nologo -TP /DWIN32 /O2 {flags} /clang:-ffp-contract=off /Fo{src}.obj /c {src}"


def clang(flags, src):
    return f"/usr/bin/clang++ -O3 -std=c++20 {flags} -ffp-contract=off -o {src}.o -c {src}"


def assert_one_line_names(output, *needles):
    lines = [line for line in output.splitlines() if all(n in line for n in needles)]
    assert lines, f"no single line names all of {needles}:\n{output}"


GOOD_INCLUDES = f"-I{ENGINE_INCLUDE} -I{TABLES} -I{(REPO_ROOT / 'cli').as_posix()}"


# ---------------------------------------------------------------- synthetic


@pytest.mark.parametrize("command", [clang_cl, clang])
def test_public_header_includes_pass(tmp_path, command):
    main, wav = cli_file("main.cpp"), cli_file("wav.cpp")
    build = make_build(tmp_path, [(main, command(GOOD_INCLUDES, main)),
                                  (wav, command(GOOD_INCLUDES, wav))])
    code, out = run_checker(build)
    assert code == 0, out


def test_engine_sources_may_include_engine_src(tmp_path):
    main, eng = cli_file("main.cpp"), engine_file("api/api.cpp")
    build = make_build(tmp_path, [(main, clang_cl(GOOD_INCLUDES, main)),
                                  (eng, clang_cl(f"-I{ENGINE_SRC} -I{ENGINE_INCLUDE}", eng))])
    code, out = run_checker(build)
    assert code == 0, out


def test_a_sibling_directory_with_the_same_prefix_passes(tmp_path):
    main = cli_file("main.cpp")
    build = make_build(tmp_path, [(main, clang_cl(f"{GOOD_INCLUDES} -I{ENGINE_SRC}x", main))])
    code, out = run_checker(build)
    assert code == 0, out


def relative_engine_src(build):
    return os.path.relpath(REPO_ROOT / "engine" / "src", build / "cli").replace("\\", "/")


@pytest.mark.parametrize("form", [
    "-I{p}",
    "-I {p}",
    "/I{p}",
    "/I {p}",
    "-isystem {p}",
    "-isystem{p}",
    "-iquote {p}",
    "-idirafter {p}",
    "-imsvc {p}",
    "/imsvc{p}",
    "/external:I{p}",
    "-external:I {p}",
    "/clang:-I{p}",
    "-clang:-isystem{p}",
    "-I{p}/core",
    "-I{p}/",
    "-I{backslash}",
    "-I{upper}",
    "-I{relative}",
    "--include-directory={p}",
    "--include-directory {p}",
    "-cxx-isystem {p}",
    "-iwithprefix {p}",
    "-iwithprefixbefore{p}",
    "-Xclang -internal-isystem -Xclang {p}",
])
def test_include_into_engine_src_fails(tmp_path, form):
    main = cli_file("main.cpp")
    build = tmp_path / "build"
    upper = ENGINE_SRC.upper() if sys.platform == "win32" else ENGINE_SRC
    if form == "-I{upper}" and sys.platform != "win32":
        pytest.skip("paths are case-sensitive here")
    relative = ""
    if "{relative}" in form:
        try:
            relative = relative_engine_src(build)
        except ValueError:
            # Windows has no relative path between drives (CI: repo on D:, temp on C:).
            pytest.skip("the temp directory is on another drive than the repo")
    flag = form.format(p=ENGINE_SRC, backslash=ENGINE_SRC.replace("/", "\\"), upper=upper,
                       relative=relative)
    if "\\" in flag and sys.platform != "win32":
        pytest.skip("backslash paths are a Windows form")
    build = make_build(tmp_path, [(main, clang_cl(f"{GOOD_INCLUDES} {flag}", main))])
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, "main.cpp", "engine")


def test_each_violating_cli_source_gets_its_own_line(tmp_path):
    main, wav, report = cli_file("main.cpp"), cli_file("wav.cpp"), cli_file("report.cpp")
    build = make_build(tmp_path, [
        (main, clang(f"{GOOD_INCLUDES} -I{ENGINE_SRC}", main)),
        (wav, clang(GOOD_INCLUDES, wav)),
        (report, clang(f"-isystem {ENGINE_SRC}/json {GOOD_INCLUDES}", report)),
    ], toolchain=("clang", "23.1.4"))
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, "main.cpp", "engine/src")
    assert_one_line_names(out, "report.cpp", "engine/src")
    assert "wav.cpp" not in out, out


def test_arguments_form_fails(tmp_path):
    main = cli_file("main.cpp")
    build = make_build(tmp_path, [(main, "unused")], toolchain=("clang", "23.1.4"))
    path = build / "compile_commands.json"
    entries = json.loads(path.read_text(encoding="utf-8"))
    del entries[0]["command"]
    entries[0]["arguments"] = ["clang++", "-I", ENGINE_SRC, "-c", main]
    path.write_text(json.dumps(entries), encoding="utf-8")
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, "main.cpp", "engine")


def test_response_file_fails(tmp_path):
    main = cli_file("main.cpp")
    build = make_build(tmp_path, [(main, clang_cl(f"{GOOD_INCLUDES} @CMakeFiles/main.rsp", main))])
    code, out = run_checker(build)
    assert code == 1, out
    assert "main.cpp" in out, out


def test_zero_cli_sources_fails(tmp_path):
    eng = engine_file("version.cpp")
    build = make_build(tmp_path, [(eng, clang_cl(f"-I{ENGINE_INCLUDE}", eng))])
    code, out = run_checker(build)
    assert code == 1, out


def test_missing_build_facts_fail(tmp_path):
    code, out = run_checker(tmp_path)
    assert code == 1, out


# --------------------------------------------------------- real configures


def cmake_command(args):
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-File", str(REPO_ROOT / "tools" / "dev.ps1"),
                "cmake", *args]
    return [CMAKE, *args]


def configure(build_dir, *defines):
    result = subprocess.run(
        cmake_command(["--preset", PRESET, "-B", str(build_dir), "-DARCANI_BUILD_TESTS=OFF",
                       *defines]),
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=600, env=os.environ.copy(),
    )
    return result.returncode, result.stdout + result.stderr


needs_cmake = pytest.mark.skipif(CMAKE is None, reason="cmake is not on PATH")


@needs_cmake
def test_include_check_passes_on_preset_configure(tmp_path_factory):
    build = tmp_path_factory.mktemp("includes_pass") / "build"
    code, out = configure(build)
    assert code == 0, out
    code, out = run_checker(build)
    assert code == 0, out


@needs_cmake
def test_include_check_fails_on_an_engine_src_include(tmp_path_factory):
    build = tmp_path_factory.mktemp("includes_fail") / "build"
    code, out = configure(build, f"-DCMAKE_CXX_FLAGS=-I{ENGINE_SRC}")
    assert code == 0, out
    code, out = run_checker(build)
    assert code == 1, out
    assert_one_line_names(out, "main.cpp", "engine")
