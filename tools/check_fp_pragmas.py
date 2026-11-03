"""Fails on floating-point pragmas in engine/ sources (AD-9).

Usage: python tools/check_fp_pragmas.py [DIR ...]

Scans every C or C++ source and header under each DIR (default: the repo's
engine/ directory), recursively. A floating-point pragma can turn contraction
or reassociation back on, or change the rounding or fp environment, inside
one file while every compile flag still looks clean, so the compile-flag
check (tools/check_compile_flags.py) cannot see it.

Fails on a pragma whose argument starts with one of FP_PRAGMAS, in any of
the three spellings:

- a preprocessor line `#pragma ...` (leading whitespace and spaces after the
  `#` allowed);
- the operator `_Pragma("...")` anywhere on a line;
- MSVC `__pragma(...)` anywhere on a line.

Other pragmas (`once`, `warning`, `clang diagnostic`, ...) pass. Exit 0 when
no file has a floating-point pragma, printing how many files were scanned;
exit 1 with one line per violation, `<path>:<line>: <text>: floating-point
pragma`, or when a directory is missing or holds no source files.

Standard library only.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRS = [REPO_ROOT / "engine"]
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp"}

# Pragma arguments (prefixes, whitespace-normalized) that change fp semantics.
FP_PRAGMAS = (
    "clang fp",
    "STDC FP_CONTRACT",
    "STDC FENV_ACCESS",
    "STDC FENV_ROUND",
    "STDC CX_LIMITED_RANGE",
    "float_control",
    "fenv_access",
    "fp_contract",
    "GCC optimize",
)

DIRECTIVE = re.compile(r"^\s*#\s*pragma\b(.*)$")
OPERATOR = re.compile(r'\b_Pragma\s*\(\s*L?"((?:[^"\\]|\\.)*)"\s*\)')
MSVC = re.compile(r"\b__pragma\s*\(")


def msvc_arguments(line):
    """Yields the argument text of each __pragma(...) on the line (balanced parentheses)."""
    for match in MSVC.finditer(line):
        depth = 1
        i = match.end()
        start = i
        while i < len(line) and depth:
            if line[i] == "(":
                depth += 1
            elif line[i] == ")":
                depth -= 1
            i += 1
        yield line[start:i - 1] if depth == 0 else line[start:]


def is_fp_pragma(argument):
    words = " ".join(argument.replace("(", " ( ").split())
    for prefix in FP_PRAGMAS:
        if words == prefix or words.startswith(prefix + " ") or words.startswith(prefix + "("):
            return True
    return False


def pragmas(line):
    """Yields (text as written, argument) for every pragma on one source line."""
    m = DIRECTIVE.match(line)
    if m:
        yield line.strip(), m.group(1)
    for m in OPERATOR.finditer(line):
        yield m.group(0), m.group(1).replace('\\"', '"')
    for argument in msvc_arguments(line):
        yield f"__pragma({argument})", argument


def check_file(path):
    problems = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]
    # Join backslash-continued lines, keeping the first line's number.
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        number = i + 1
        line = lines[i]
        while line.endswith("\\") and i + 1 < len(lines):
            i += 1
            line = line[:-1] + " " + lines[i]
        for written, argument in pragmas(line):
            if is_fp_pragma(argument):
                problems.append(f"{path}:{number}: {written}: floating-point pragma")
        i += 1
    return problems


def main(argv):
    dirs = [Path(a) for a in argv[1:]] or DEFAULT_DIRS
    problems = []
    scanned = 0
    for directory in dirs:
        if not directory.is_dir():
            problems.append(f"fp pragma check: {directory} is not a directory")
            continue
        files = sorted(p for p in directory.rglob("*")
                       if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES)
        if not files:
            problems.append(f"fp pragma check: no C or C++ source files in {directory}")
            continue
        for path in files:
            scanned += 1
            problems.extend(check_file(path))
    for line in problems:
        print(line)
    if problems:
        return 1
    print(f"fp pragma check: {scanned} file(s) scanned, no floating-point pragma")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
