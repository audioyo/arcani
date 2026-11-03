"""Checks the engine library for denied undefined symbols (AD-9 pure core).

Usage:
  python tools/check_engine_symbols.py BUILD_DIR
  python tools/check_engine_symbols.py --nm-output FILE

With BUILD_DIR, reads BUILD_DIR/arcani_engine_check.json (written by
engine/CMakeLists.txt) and runs its llvm_nm on its engine_library, listing
every symbol both raw and demangled and keeping the undefined ones (type U, w,
or v). It does not pass --undefined-only: for Mach-O files (macOS) llvm-nm
then prints bare names with no type column, which this parser would skip. With --nm-output, checks FILE, text
in llvm-nm's output format, instead.

Denied names come from tools/engine_symbol_denylist.json. Exit 0 when nothing
is denied; exit 1 with one line per denied symbol, naming the symbol as
llvm-nm lists it and its family.

Standard library only.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

DENYLIST = Path(__file__).resolve().parent / "engine_symbol_denylist.json"
UNDEFINED_TYPES = {"U", "w", "v"}


def load_denylist(path=DENYLIST):
    data = json.loads(path.read_text(encoding="utf-8"))
    families = []
    for family in data["families"]:
        c_names = [re.compile(p) for p in family["c_names"]]
        cpp_names = [re.compile(p) for p in family["cpp_names"]]
        families.append((family["name"], c_names, cpp_names))
    return families


def normalize_c_name(name):
    if name.startswith("__imp_"):
        name = name[len("__imp_"):]
    if name.startswith("_"):
        name = name[1:]
    return name


def undefined_names(nm_text):
    """Returns the undefined symbol names in llvm-nm output, in order, deduplicated."""
    names = []
    seen = set()
    for line in nm_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        kind, _, rest = stripped.partition(" ")
        if kind not in UNDEFINED_TYPES or not rest.strip():
            continue  # member header ("version.cpp.o:") or a defined symbol
        name = rest.strip()
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def family_of(name, families):
    raw = normalize_c_name(name)
    for family, c_names, cpp_names in families:
        if any(p.fullmatch(raw) for p in c_names):
            return family
        if any(p.search(name) for p in cpp_names):
            return family
    return None


def check_names(names, families):
    return [(name, fam) for name in names if (fam := family_of(name, families)) is not None]


def run_nm(nm, library, demangle):
    # No --undefined-only: on Mach-O it drops the type column (see above).
    args = [nm]
    if demangle:
        args.append("--demangle")
    args.append(str(library))
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout


def main(argv):
    try:
        families = load_denylist()
    except (OSError, ValueError, KeyError, re.error) as exc:
        print(f"symbol check: cannot load {DENYLIST}: {exc}")
        return 1

    if len(argv) == 3 and argv[1] == "--nm-output":
        try:
            text = Path(argv[2]).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"symbol check: cannot read {argv[2]}: {exc}")
            return 1
        names = undefined_names(text)
        where = argv[2]
    elif len(argv) == 2:
        check_path = Path(argv[1]) / "arcani_engine_check.json"
        try:
            check = json.loads(check_path.read_text(encoding="utf-8"))
            nm = check["llvm_nm"]
            library = Path(check["engine_library"])
        except (OSError, ValueError, KeyError) as exc:
            print(f"symbol check: cannot read build facts from {check_path}: {exc}")
            return 1
        if not library.is_file():
            print(f"symbol check: engine library {library} does not exist; build arcani_engine first")
            return 1
        try:
            names = undefined_names(run_nm(nm, library, demangle=False))
            for name in undefined_names(run_nm(nm, library, demangle=True)):
                if name not in names:
                    names.append(name)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f"symbol check: llvm-nm failed: {exc}")
            return 1
        where = str(library)
    else:
        print("usage: check_engine_symbols.py BUILD_DIR | --nm-output FILE", file=sys.stderr)
        return 2

    denied = check_names(names, families)
    for name, family in denied:
        print(f"denied symbol: {name} (family: {family})")
    if denied:
        print(f"{len(denied)} denied undefined symbol(s) in {where}")
        return 1
    print(f"{len(names)} undefined symbol(s) in {where}, none denied")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
