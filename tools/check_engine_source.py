"""Fails on long double, L literals, transcendental or fma calls, or <random> in engine/ sources (AD-9).

Usage: python tools/check_engine_source.py [DIR ...]

Scans every C or C++ source and header under each DIR (default: the repo's
engine/ directory), recursively, with the same suffix set as
tools/check_fp_pragmas.py. A constant-folded libm call, a `long double`, or an
`L` literal leaves no undefined symbol, so tools/check_engine_symbols.py
cannot see it; this scan reads the source instead (Story 1.6).

Comments and string and character literals (raw strings too) are blanked
first, keeping line numbers, so text inside them never fails. Then it fails
on:

- the type `long double` (any whitespace between the words) [long double];
- a floating-point literal with an `L` or `l` suffix, decimal with a point or
  an exponent, or hexadecimal with a `p` exponent [long double literal].
  Integer literals such as `10L` pass;
- a <cmath> transcendental name used as a call, bare, `std::`, `::`, or
  `__builtin_` [transcendental call]. `sqrt` passes: IEEE 754 rounds it
  correctly on every target (design log 2026-11-02 (z));
- `fma`, `fmaf`, `fmal` used as a call in the same forms
  [fused multiply-add call];
- `#include <random>` [random header];
- a hardware random or timer intrinsic (`_rdrand32_step`, `__rdtsc`,
  `__builtin_readcyclecounter`, `__rndr`, ...) [hardware intrinsic];
- a <random> library name (`mt19937`, `random_device`, any
  `*_distribution`, `seed_seq`, ...) [random library name];
- an extended precision type (`__float128`, `_Float128`, `__float80`,
  `__ibm128`, `_Float64x`) [extended precision type].

A transcendental is any name of the libm family in
tools/engine_symbol_denylist.json or a C++17 special math function. A member
call (`obj.log(x)`, `p->exp(x)`) passes.

Exit 0 when nothing is found, printing how many files were scanned; exit 1
with one line per violation, `<path>:<line>: <text>: <reason>`, or when a
directory is missing or holds no source files.

Standard library only.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRS = [REPO_ROOT / "engine"]
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp"}

# The libm family of tools/engine_symbol_denylist.json, plus the C++17 special
# math functions of <cmath>.
TRANSCENDENTALS = (
    "sin cos tan asin acos atan atan2 sinh cosh tanh asinh acosh atanh exp exp2 exp10 expm1 "
    "log log2 log10 log1p pow cbrt hypot erf erfc tgamma lgamma sincos "
    "j0 j1 jn y0 y1 yn sinpi cospi tanpi sincospi "
    "assoc_laguerre assoc_legendre beta comp_ellint_1 comp_ellint_2 comp_ellint_3 "
    "cyl_bessel_i cyl_bessel_j cyl_bessel_k cyl_neumann ellint_1 ellint_2 ellint_3 expint "
    "hermite laguerre legendre riemann_zeta sph_bessel sph_legendre sph_neumann"
).split()

# A member call (`obj.log(x)`, `p->exp(x)`) is not a libm call.
_CALL_PREFIX = r"(?<![\w.])(?<!->)(?:std\s*::\s*|::\s*|__builtin_)?"

# Hardware random and timer intrinsics: they leave no symbol.
HARDWARE_INTRINSICS = (
    r"_rdrand\d+_step|_rdseed\d+_step|__builtin_ia32_rdrand\w*|__builtin_ia32_rdseed\w*"
    r"|__rdtscp?|__builtin_ia32_rdtsc\w*|__builtin_readcyclecounter"
    r"|__rndr|__rndrrs|__builtin_arm_rndr\w*"
)
# <random> library names, used with or without the include line.
RANDOM_LIBRARY_NAMES = (
    r"mt19937(?:_64)?|minstd_rand0?|default_random_engine|ranlux\w*|knuth_b|random_device"
    r"|\w+_distribution|seed_seq"
)
EXTENDED_TYPES = r"__float128|_Float128|__float80|__ibm128|_Float64x"
RULES = (
    (re.compile(r"\blong\s+double\b"), "long double"),
    (re.compile(r"(?<![\w.'])(?:\d[\d']*\.[\d']*|\.\d[\d']*)(?:[eE][+-]?\d+)?[lL](?![\w.])"),
     "long double literal"),
    (re.compile(r"(?<![\w.'])\d[\d']*[eE][+-]?\d+[lL](?![\w.])"), "long double literal"),
    (re.compile(r"(?<![\w.'])0[xX][0-9a-fA-F']*\.?[0-9a-fA-F']*[pP][+-]?\d+[lL](?![\w.])"),
     "long double literal"),
    (re.compile(_CALL_PREFIX + r"(?:" + "|".join(sorted(TRANSCENDENTALS, key=len, reverse=True))
                + r")[fl]?\s*\(|" + _CALL_PREFIX + r"lgamma[fl]?_r\s*\("), "transcendental call"),
    (re.compile(_CALL_PREFIX + r"fma[fl]?\s*\("), "fused multiply-add call"),
    (re.compile(r"^[ \t]*#[ \t]*include[ \t]*<[ \t]*random[ \t]*>", re.MULTILINE), "random header"),
    (re.compile(r"(?<!\w)(?:" + HARDWARE_INTRINSICS + r")(?!\w)"), "hardware intrinsic"),
    (re.compile(r"(?<!\w)(?:" + RANDOM_LIBRARY_NAMES + r")(?!\w)"), "random library name"),
    (re.compile(r"(?<!\w)(?:" + EXTENDED_TYPES + r")(?!\w)"), "extended precision type"),
)

IDENTIFIER = re.compile(r"[A-Za-z_]\w*")
PP_NUMBER = re.compile(r"\.?\d(?:[eEpP][+-]|'(?=\w)|[\w.])*")
RAW_PREFIXES = {"R", "u8R", "uR", "UR", "LR"}
LITERAL_PREFIXES = {"L", "u8", "u", "U"}


def _blank(text):
    """Text with every character except a newline replaced by a space."""
    return re.sub(r"[^\n]", " ", text)


def strip_comments_and_literals(text):
    """Returns text with comments and string and character literals blanked, same length and lines."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            end = text.find("\n", i)
            end = n if end < 0 else end
            out.append(_blank(text[i:end]))
            i = end
        elif c == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append(_blank(text[i:end]))
            i = end
        elif c in "\"'":
            end = _quoted_end(text, i)
            out.append(_blank(text[i:end]))
            i = end
        elif c.isalpha() or c == "_":
            m = IDENTIFIER.match(text, i)
            word = m.group(0)
            end = m.end()
            if word in RAW_PREFIXES and end < n and text[end] == '"':
                close = _raw_end(text, end)
                out.append(word + _blank(text[end:close]))
                i = close
            else:
                out.append(word)
                i = end
                if word in LITERAL_PREFIXES and end < n and text[end] in "\"'":
                    close = _quoted_end(text, end)
                    out.append(_blank(text[end:close]))
                    i = close
        elif c.isdigit() or (c == "." and nxt.isdigit()):
            m = PP_NUMBER.match(text, i)
            out.append(m.group(0))
            i = m.end()
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _quoted_end(text, start):
    """Index just past the string or character literal that opens at text[start]."""
    quote = text[start]
    i = start + 1
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == quote:
            return i + 1
        if ch == "\n":
            return i  # unterminated: stop at the line end
        i += 1
    return len(text)


def _raw_end(text, quote):
    """Index just past the raw string whose opening quote is at text[quote]."""
    paren = text.find("(", quote + 1)
    if paren < 0:
        return quote + 1
    delimiter = text[quote + 1:paren]
    close = text.find(")" + delimiter + '"', paren + 1)
    return len(text) if close < 0 else close + len(delimiter) + 2


def check_file(path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    stripped = strip_comments_and_literals(text)
    found = []
    for pattern, reason in RULES:
        for m in pattern.finditer(stripped):
            start = m.start()
            while start < m.end() and stripped[start].isspace():
                start += 1
            line_no = stripped.count("\n", 0, start) + 1
            found.append((line_no, start, reason))
    found.sort()
    return [f"{path}:{line_no}: {lines[line_no - 1].strip()}: {reason}"
            for line_no, _, reason in found]


def main(argv):
    dirs = [Path(a) for a in argv[1:]] or DEFAULT_DIRS
    problems = []
    scanned = 0
    for directory in dirs:
        if not directory.is_dir():
            problems.append(f"engine source check: {directory} is not a directory")
            continue
        files = sorted(p for p in directory.rglob("*")
                       if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES)
        if not files:
            problems.append(f"engine source check: no C or C++ source files in {directory}")
            continue
        for path in files:
            scanned += 1
            problems.extend(check_file(path))
    for line in problems:
        print(line)
    if problems:
        return 1
    print(f"engine source check: {scanned} file(s) scanned, no long double, L literal, "
          "transcendental or fma call, <random>, hardware intrinsic, or extended precision type")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
