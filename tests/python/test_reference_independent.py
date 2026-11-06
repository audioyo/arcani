"""reference/ imports no engine code and loads no engine binary (Story 1.5, AD-16).

Two checks, each with must-fail modules in tests/fixtures/reference_independence/
(each case folder holds a stand-in `reference/stub_chain.py`; they are test
fixtures, never part of reference/):

1. Import scan. Every .py file under the directory is parsed (ast). A file
   fails when it:
   - imports a module whose top-level name is not in the standard library
     (`sys.stdlib_module_names`), not `numpy`, and not `reference` (relative
     imports inside the package are allowed);
   - imports any of FORBIDDEN_MODULES (`ctypes`, `_ctypes`, `cffi`,
     `subprocess`, `_posixsubprocess`, `multiprocessing`, `importlib`), or
     names `__import__`;
   - uses an attribute or imported name in FORBIDDEN_NAMES
     (`add_dll_directory`, `system`, `popen`, `startfile`, any `exec*` or
     `spawn*` of `os`, `ctypeslib`, `load_library`, `CDLL`, `cdll`,
     `windll`, `LoadLibrary`);
   - holds a string constant, other than a docstring, that names an engine,
     CLI, or build path or a binary: after backslashes become `/` and case
     is folded, it contains `engine/`, `cli/`, or `build/`, equals `engine`,
     `cli`, or `build`, contains `arcani-render`, `arcani-tapdump`,
     `arcani_engine`, or `arcani-hashprobe`, or ends with `.dll`, `.so`,
     `.dylib`, `.pyd`, or `.exe`.
   Docstrings may describe the engine in prose (the reference's own
   docstring says it reads no engine code).
2. Isolated run. A child `python -I` (no user site, no PYTHON* variables, no
   script or working directory on sys.path) imports NumPy first, records
   the loaded modules as the baseline (NumPy itself loads ctypes, so ctypes
   cannot be judged here; the scan covers it), puts the given root on
   sys.path, imports `reference.stub_chain`, and renders both 1 s stub chain
   fixtures at 44.1 and 48 kHz. It fails when the import or a render raises,
   when a module loaded after the baseline is in FORBIDDEN_LOADED
   (FORBIDDEN_MODULES without importlib, which the import system may load
   itself) or is
   not standard library, NumPy, or `reference`, or when any loaded module's
   file lies under the repo's engine/, cli/, or build/ folder or under an
   extra forbidden root the test names.

Must-fail cases: a module that imports ctypes fails the scan (the acceptance
criterion); others import subprocess (scan and isolated run), call
os.add_dll_directory, name a build path, use importlib, use
numpy.ctypeslib, and load a module from a forbidden root (isolated run).
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "reference"
MUSTFAIL = REPO_ROOT / "tests" / "fixtures" / "reference_independence"
FIXTURES_VALID = REPO_ROOT / "recipes" / "fixtures" / "valid"
RENDER_CASES = [(str(FIXTURES_VALID / name), fs)
                for name in ("stub-chain-1s-beat-0.json", "stub-chain-1s-beat-6.json")
                for fs in (44100, 48000)]

FORBIDDEN_MODULES = {"ctypes", "_ctypes", "cffi", "subprocess", "_posixsubprocess",
                     "multiprocessing", "importlib"}
# The import system may load importlib submodules itself, so the isolated run
# judges loaded modules without importlib; the scan forbids importing it.
FORBIDDEN_LOADED = FORBIDDEN_MODULES - {"importlib"}
FORBIDDEN_NAMES = {"add_dll_directory", "system", "popen", "startfile", "ctypeslib",
                   "load_library", "CDLL", "cdll", "windll", "LoadLibrary", "__import__"}
FORBIDDEN_PREFIXES = ("exec", "spawn")  # os.execv, os.spawnl, ...
ALLOWED_TOP = {"numpy", "reference"}
PATH_PARTS = ("engine/", "cli/", "build/")
PATH_WORDS = {"engine", "cli", "build"}
BINARY_WORDS = ("arcani-render", "arcani-tapdump", "arcani_engine", "arcani-hashprobe")
BINARY_SUFFIXES = (".dll", ".so", ".dylib", ".pyd", ".exe")


# ------------------------------------------------------------ the scan


def _docstring_nodes(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _path_like(text):
    t = text.replace("\\", "/").lower()
    if t in PATH_WORDS or any(p in t for p in PATH_PARTS) or any(w in t for w in BINARY_WORDS):
        return True
    return t.endswith(BINARY_SUFFIXES)


def _check_import(top, where, problems):
    if top in FORBIDDEN_MODULES:
        problems.append(f"{where}: imports {top}")
    elif top not in sys.stdlib_module_names and top not in ALLOWED_TOP:
        problems.append(f"{where}: imports {top}, which is not the standard library, numpy, or reference")


def _forbidden_name(name):
    return name in FORBIDDEN_NAMES or name.startswith(FORBIDDEN_PREFIXES)


def scan_problems(directory):
    """Problems of every .py file under directory (empty list when clean)."""
    directory = Path(directory)
    problems = []
    files = sorted(directory.rglob("*.py"))
    if not files:
        problems.append(f"{directory}: no Python files")
    for path in files:
        rel = path.relative_to(directory)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            where = f"{rel}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _check_import(alias.name.split(".")[0], where, problems)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    _check_import(node.module.split(".")[0], where, problems)
                for alias in node.names:
                    if _forbidden_name(alias.name) and (node.module or "") in ("os", "ctypes", "numpy"):
                        problems.append(f"{where}: imports {alias.name} from {node.module}")
            elif isinstance(node, ast.Attribute):
                if node.attr in FORBIDDEN_NAMES:
                    problems.append(f"{where}: uses .{node.attr}")
                elif node.attr.startswith(FORBIDDEN_PREFIXES) and isinstance(node.value, ast.Name) \
                        and node.value.id == "os":
                    problems.append(f"{where}: uses os.{node.attr}")
            elif isinstance(node, ast.Name):
                if node.id in ("__import__", "CDLL", "cdll", "windll", "LoadLibrary", "add_dll_directory"):
                    problems.append(f"{where}: names {node.id}")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) not in docstrings and _path_like(node.value):
                    problems.append(f"{where}: string {node.value!r} names an engine, CLI, or build path "
                                    f"or a binary")
    return problems


def test_scan_passes_on_reference():
    assert (REFERENCE / "stub_chain.py").is_file(), "missing reference/stub_chain.py (Story 1.5)"
    problems = scan_problems(REFERENCE)
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("case, expect", [
    ("ctypes_import", "imports ctypes"),
    ("subprocess_import", "imports subprocess"),
    ("dll_directory", "add_dll_directory"),
    ("build_path", "build path"),
    ("importlib_load", "imports importlib"),
    ("numpy_ctypeslib", "ctypeslib"),
    ("third_party_import", "not the standard library"),
])
def test_scan_fails_on_a_mustfail_module(case, expect):
    directory = MUSTFAIL / case / "reference"
    assert (directory / "stub_chain.py").is_file(), directory
    problems = scan_problems(directory)
    assert any(expect in p for p in problems), problems


def test_scan_allows_docstring_prose_and_relative_imports(tmp_path):
    pkg = tmp_path / "reference"
    pkg.mkdir()
    (pkg / "stub_chain.py").write_text(
        '"""Reads no engine/ code and loads no build/ binary."""\n'
        "import json\nimport math\n\nimport numpy as np\n\nfrom . import ideal\n"
        "from reference import ideal as again\n\n\n"
        'def render(path, fs):\n    """Not engine/ code."""\n    return {"x": np.zeros(2)}\n',
        encoding="utf-8")
    assert scan_problems(pkg) == []


# ---------------------------------------------------------- isolated run

CHILD = r'''
import json
import sys

root, cases_json = sys.argv[1], sys.argv[2]
import numpy  # baseline: the reference may use NumPy, which loads ctypes itself
baseline = set(sys.modules)
sys.path.insert(0, root)
error = None
try:
    import reference.stub_chain as sc
    for path, fs in json.loads(cases_json):
        out = sc.render(path, fs)
        if not isinstance(out, dict) or "output" not in out:
            error = "render returned no output"
except BaseException as e:
    error = repr(e)
new = sorted(set(sys.modules) - baseline)
files = {}
for name, module in list(sys.modules.items()):
    f = getattr(module, "__file__", None)
    if isinstance(f, str):
        files[name] = f
print(json.dumps({"error": error, "new": new, "files": files, "flags_isolated": sys.flags.isolated}))
'''


def isolated_run(root, extra_forbidden_roots=()):
    result = subprocess.run([sys.executable, "-I", "-c", CHILD, str(root), json.dumps(RENDER_CASES)],
                            capture_output=True, text=True, timeout=300, cwd=str(Path(root)))
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def run_problems(report, extra_forbidden_roots=()):
    problems = []
    if report["flags_isolated"] != 1:
        problems.append("child did not run with python -I")
    if report["error"] is not None:
        problems.append(f"import or render failed: {report['error']}")
    for name in report["new"]:
        top = name.split(".")[0]
        if top in FORBIDDEN_LOADED:
            problems.append(f"loaded {name}")
        elif top not in sys.stdlib_module_names and top not in ALLOWED_TOP:
            problems.append(f"loaded {name}, which is not the standard library, numpy, or reference")
    roots = [REPO_ROOT / "engine", REPO_ROOT / "cli", REPO_ROOT / "build", *map(Path, extra_forbidden_roots)]
    for name, f in report["files"].items():
        p = Path(f).resolve()
        for r in roots:
            if p.is_relative_to(r.resolve()):
                problems.append(f"loaded {name} from {p}")
    return problems


def test_isolated_run_of_reference_loads_nothing_forbidden():
    assert (REFERENCE / "stub_chain.py").is_file(), "missing reference/stub_chain.py (Story 1.5)"
    report = isolated_run(REPO_ROOT)
    problems = run_problems(report)
    assert not problems, "\n".join(problems)
    assert any(n == "reference.stub_chain" for n in report["new"]), report["new"]


def test_isolated_run_fails_on_a_module_that_loads_subprocess():
    report = isolated_run(MUSTFAIL / "subprocess_import")
    problems = run_problems(report)
    assert any("loaded subprocess" in p for p in problems), problems


def test_isolated_run_fails_on_a_module_loaded_from_a_forbidden_root():
    case = MUSTFAIL / "forbidden_root"
    report = isolated_run(case)
    assert report["error"] is None, report["error"]
    # The stand-in folder is not a forbidden root by default; named as one,
    # the module loaded from it fails by its file.
    assert not any(" from " in p for p in run_problems(report))
    problems = run_problems(report, extra_forbidden_roots=[case / "fake_build"])
    assert any(p.startswith("loaded fake_engine from") for p in problems), problems


def test_isolated_run_fails_when_the_module_is_missing(tmp_path):
    problems = run_problems(isolated_run(tmp_path))
    assert any("import or render failed" in p for p in problems), problems
