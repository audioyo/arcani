"""Checks that cli/ sources reach the engine only through its public header (Story 1.4).

Usage: python tools/check_cli_includes.py BUILD_DIR

Reads BUILD_DIR/arcani_engine_check.json (written by engine/CMakeLists.txt),
then the compile_commands.json it names. A CLI source is an entry whose file
lies under <source_dir>/cli/. Exit 1, with one line per violation, when a CLI
source has an include path equal to or under <source_dir>/engine/src, when a
CLI source's command uses an @ response file, when there is no CLI source, or
when the build facts cannot be read. Exit 0 otherwise.

Include path options: -I, /I, -isystem, -iquote, -idirafter, -imsvc, /imsvc,
-external:I, /external:I, joined to the path or followed by it as the next
token, bare or behind /clang: or -clang:. Relative paths are taken from the
entry's directory.

Standard library only.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_compile_flags import CLANG_PREFIXES, normalize_path, tokenize  # noqa: E402

# Longest first, so -isystem is not read as -i plus "system".
INCLUDE_OPTIONS = sorted(
    ["-I", "/I", "-isystem", "-iquote", "-idirafter", "-imsvc", "/imsvc", "-external:I",
     "/external:I"],
    key=len,
    reverse=True,
)


def strip_prefix(token):
    for prefix in CLANG_PREFIXES:
        if token.startswith(prefix):
            return token[len(prefix):]
    return token


def include_paths(tokens):
    """Yields (path as written, whole option text) for each include path option."""
    i = 0
    while i < len(tokens):
        bare = strip_prefix(tokens[i])
        for option in INCLUDE_OPTIONS:
            if bare == option:
                if i + 1 < len(tokens):
                    path = strip_prefix(tokens[i + 1])
                    yield path, f"{tokens[i]} {tokens[i + 1]}"
                    i += 1
                break
            if bare.startswith(option):
                yield bare[len(option):], tokens[i]
                break
        i += 1


def main(argv):
    if len(argv) != 2:
        print("usage: check_cli_includes.py BUILD_DIR", file=sys.stderr)
        return 2
    check_path = Path(argv[1]) / "arcani_engine_check.json"
    try:
        check = json.loads(check_path.read_text(encoding="utf-8"))
        source_dir = check["source_dir"]
        commands_path = Path(check["compile_commands"])
        entries = json.loads(commands_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"CLI include check: cannot read build facts from {check_path}: {exc}")
        return 1

    root = normalize_path(source_dir).rstrip("/")
    cli_prefix = root + "/cli/"
    engine_src = root + "/engine/src"
    violations = []
    cli_sources = 0
    for entry in entries:
        directory = entry.get("directory")
        file_path = normalize_path(entry.get("file", ""), directory)
        if not file_path.startswith(cli_prefix):
            continue
        cli_sources += 1
        shown = entry.get("file", "")
        tokens = tokenize(entry)
        for token in tokens:
            if strip_prefix(token).startswith("@"):
                violations.append(f"{shown}: {token}: response file hides the include paths")
        for path, written in include_paths(tokens):
            if not path:
                continue
            resolved = normalize_path(path, directory)
            if resolved == engine_src or resolved.startswith(engine_src + "/"):
                violations.append(
                    f"{shown}: {written}: include path into engine/src (public header only)"
                )

    if cli_sources == 0:
        violations.append(f"no cli/ sources found in {commands_path}; nothing was checked")

    for line in violations:
        print(line)
    if violations:
        return 1
    print(f"{cli_sources} CLI source(s) include the engine through its public header only")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
