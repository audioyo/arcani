"""Checks that every engine/ source compiles with -ffp-contract=off and no fast-math flag (AD-9).

Usage: python tools/check_compile_flags.py BUILD_DIR

Reads BUILD_DIR/arcani_engine_check.json (written by engine/CMakeLists.txt),
then the compile_commands.json it names. Exit 0 when every engine source
passes; exit 1 with one line per violation otherwise. Each flag violation line
names the toolchain and version, the source file, and the flag.

Rules for each engine/ source (flags are seen bare, behind /clang: or -clang:,
or as the argument of -Xclang):

- Effective contraction must be off. clang-cl moves every /clang: and -clang:
  argument after all other arguments, so for clang-cl commands those tokens
  are evaluated last. The effective value is set by the last of
  -ffp-contract=X (X) or an fp model that implies contraction on:
  -ffp-model=precise|fast|aggressive, or /fp:precise|fast (also -fp:). The
  strict and except models never turn contraction on. No setter at all fails
  as missing.
- No fast-math flag (FAST_MATH_FLAGS below).
- No value-changing fp option: -fdenormal-fp-math= or -fdenormal-fp-math-f32=
  with any value other than ieee, -mdaz-ftz, -fcomplex-arithmetic=basic,
  -mrecip and -mrecip=*, -fveclib=* other than none, -mfpmath=387, and cc1
  -mreassociate, -menable-no-nans, -menable-no-infs, -menable-unsafe-fp-math.
- No @ response file (bare or behind a prefix).
- At least one engine/ source.

Standard library only.
"""

import json
import os
import posixpath
import re
import shlex
import sys
from pathlib import Path

# Fast-math flags, matched exactly on the bare flag (after any /clang: or
# -clang: prefix, or as the argument of -Xclang).
FAST_MATH_FLAGS = {
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
    "/fp:fast",
    "-fp:fast",
}

CONTRACT_PREFIX = "-ffp-contract="
# fp models that set contraction on when they take effect after -ffp-contract.
CONTRACT_ON_MODELS = {
    "-ffp-model=precise",
    "-ffp-model=fast",
    "-ffp-model=aggressive",
    "/fp:precise",
    "/fp:fast",
    "-fp:precise",
    "-fp:fast",
}
CLANG_PREFIXES = ("/clang:", "-clang:")

# fp options that change results without being fast-math flags.
VALUE_CHANGING_EXACT = {
    "-mdaz-ftz",
    "-fcomplex-arithmetic=basic",
    "-mrecip",
    "-mfpmath=387",
    "-mreassociate",
    "-menable-no-nans",
    "-menable-no-infs",
    "-menable-unsafe-fp-math",
}


def value_changing(bare):
    if bare in VALUE_CHANGING_EXACT or bare.startswith("-mrecip="):
        return True
    for prefix in ("-fdenormal-fp-math=", "-fdenormal-fp-math-f32="):
        if bare.startswith(prefix):
            return any(part != "ieee" for part in bare[len(prefix):].split(","))
    if bare.startswith("-fveclib="):
        return bare[len("-fveclib="):] != "none"
    return False


def normalize_path(path, base=None):
    text = str(path).replace("\\", "/")
    if base is not None and not (text.startswith("/") or re.match(r"^[A-Za-z]:/", text)):
        text = str(base).replace("\\", "/").rstrip("/") + "/" + text
    text = posixpath.normpath(text)
    if sys.platform == "win32" or re.match(r"^[A-Za-z]:/", text):
        text = text.lower()
    return text


def tokenize(entry):
    if "arguments" in entry:
        return [str(a) for a in entry["arguments"]]
    posix = os.name != "nt"
    tokens = shlex.split(entry.get("command", ""), posix=posix)
    if posix:
        return tokens
    return [t[1:-1] if len(t) >= 2 and t[0] == t[-1] == '"' else t for t in tokens]


def bare_flags(tokens, clang_cl):
    """Yields (bare flag, token as written) for each compiler option, in effective order.

    For clang-cl, /clang: and -clang: arguments take effect after all others.
    """
    normal = []
    deferred = []
    xclang = False
    for token in tokens:
        if xclang:
            xclang = False
            normal.append((token, token))
            continue
        if token == "-Xclang":
            xclang = True
            continue
        for prefix in CLANG_PREFIXES:
            if token.startswith(prefix):
                (deferred if clang_cl else normal).append((token[len(prefix):], token))
                break
        else:
            normal.append((token, token))
    return normal + deferred


def check_source(tokens, clang_cl):
    """Returns a list of (flag text, problem) for one compile command."""
    problems = []
    contract = None
    setter = None  # (token, from an fp model) of the last contraction setter
    for bare, token in bare_flags(tokens, clang_cl):
        if token.startswith("@") or bare.startswith("@"):
            problems.append((token, "response file hides the real flags"))
        if bare in FAST_MATH_FLAGS:
            problems.append((token, "fast-math flag"))
        if value_changing(bare):
            problems.append((token, "value-changing fp option"))
        if bare.startswith(CONTRACT_PREFIX):
            contract = bare[len(CONTRACT_PREFIX):]
            setter = (token, False)
        elif bare in CONTRACT_ON_MODELS:
            setter = (token, True)
    if contract is None:
        problems.append(("-ffp-contract=off", "missing"))
    elif setter[1]:
        problems.append((setter[0], "sets contraction on after -ffp-contract=off"))
    elif contract != "off":
        problems.append((setter[0], "last -ffp-contract value is not off"))
    return problems


def main(argv):
    if len(argv) != 2:
        print("usage: check_compile_flags.py BUILD_DIR", file=sys.stderr)
        return 2
    build_dir = Path(argv[1])
    check_path = build_dir / "arcani_engine_check.json"
    try:
        check = json.loads(check_path.read_text(encoding="utf-8"))
        toolchain = f"{check['toolchain_name']} {check['toolchain_version']}"
        source_dir = check["source_dir"]
        commands_path = Path(check["compile_commands"])
        entries = json.loads(commands_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        print(f"compile flag check: cannot read build facts from {check_path}: {exc}")
        return 1

    clang_cl = check["toolchain_name"] == "clang-cl"
    engine_prefix = normalize_path(source_dir).rstrip("/") + "/engine/"
    violations = []
    engine_sources = 0
    for entry in entries:
        file_path = normalize_path(entry.get("file", ""), entry.get("directory"))
        if not file_path.startswith(engine_prefix):
            continue
        engine_sources += 1
        shown = entry.get("file", "")
        for flag, problem in check_source(tokenize(entry), clang_cl):
            violations.append(f"{toolchain}: {shown}: {flag}: {problem}")

    if engine_sources == 0:
        violations.append(
            f"{toolchain}: no engine/ sources found in {commands_path}; nothing was checked"
        )

    for line in violations:
        print(line)
    if violations:
        return 1
    print(f"{toolchain}: {engine_sources} engine source(s) pass the AD-9 flag check")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
