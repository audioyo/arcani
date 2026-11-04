"""Fails on listed terms and em dashes in tracked text files (Story 0.4).

Usage: python tools/check_wording.py [--terms FILE] [--exempt FILE] [PATH ...]

Enforces the naming and copy rules (CLAUDE.md "Never", PRD section 6
Naming, Claims, and Wording). Defaults: `--terms tools/wording/terms.tsv`,
`--exempt tools/wording/exempt.txt`, and every file `git ls-files` lists in
the repo root. A positional PATH replaces the `git ls-files` set; a
directory PATH is walked recursively. Exemptions apply to every file: each
glob (fnmatch, where `*` also crosses `/`) is matched against the file's
repo-relative POSIX path, or its absolute POSIX path outside the repo.

Run it locally from the repo root:

    uv run python tools/check_wording.py

By default only tracked files are scanned, so a new file is checked after
`git add`.

The whole text of each file is checked, not only comments and strings, and
each term is matched over the whole text, so a multi-word term split by a
line wrap still matches (multi-word patterns use `\\s+` between words).

Term list: tab-separated, header row `id, pattern, case, category, source`.
`pattern` is a Python regex matched at word boundaries that also break at
`_`, so a term inside a snake_case identifier matches; `case` is
`sensitive` or `insensitive`; `category` is `project-term`,
`comparable-name`, or `claim`; `source` must not be empty; ids are unique.

Exemption list: one glob per line, each followed by ` # reason`. Blank
lines and lines starting with `#` are ignored.

Files with a NUL byte in their first 8 KiB are skipped as binary, except a
UTF-16 file (byte order mark FF FE or FE FF), which fails as not UTF-8. A
file that is not valid UTF-8 fails.

Output: one line per match, `<path>:<line>: <matched text>: term <id>` or
`<path>:<line>: em dash` (U+2014, or its named, decimal, or hex HTML entity, in any
case), on the line where the match starts; whitespace in
the matched text is shown as single spaces. Exit 0 when nothing matches, printing
how many files were scanned; 1 on any match or undecodable file; 2 on a
setup error (bad term row, unreasoned exemption, missing terms or exempt
file, missing PATH, git failure).

Standard library only.
"""

import argparse
import bisect
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TERMS = REPO_ROOT / "tools" / "wording" / "terms.tsv"
DEFAULT_EXEMPT = REPO_ROOT / "tools" / "wording" / "exempt.txt"
COLUMNS = ["id", "pattern", "case", "category", "source"]
CASES = {"sensitive": 0, "insensitive": re.IGNORECASE}
CATEGORIES = {"project-term", "comparable-name", "claim"}
EM_DASH = chr(0x2014)
BOM = chr(0xFEFF)
# The em dash itself or its HTML entity forms (named, decimal, hex).
EM_DASH_RE = re.compile(EM_DASH + r"|&m(?:dash);|&#0*8212;|&#x0*2014;", re.IGNORECASE)
# Word boundaries that also break at `_`, so a term inside a snake_case
# identifier still matches.
WORD_START = r"(?<![^\W_])"
WORD_END = r"(?![^\W_])"
UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
BINARY_PROBE = 8192


class SetupError(Exception):
    """A term list, exemption list, or path argument is unusable."""


def read_lines(path):
    try:
        text = path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        raise SetupError(f"{path}: file not found")
    except (OSError, UnicodeDecodeError) as exc:
        raise SetupError(f"{path}: cannot read: {exc}")
    if text.startswith(BOM):
        text = text[1:]
    if text.endswith("\n"):
        text = text[:-1]
    return [line.rstrip("\r") for line in text.split("\n")] if text else []


def load_terms(path):
    """Returns [(id, compiled regex)] or raises SetupError naming line and id."""
    lines = read_lines(path)
    if not lines or lines[0].split("\t") != COLUMNS:
        raise SetupError(f"{path}:1: header: columns must be exactly {', '.join(COLUMNS)}")
    terms = []
    seen = set()
    for number, raw in enumerate(lines[1:], start=2):
        fields = raw.split("\t")
        row_id = fields[0].strip()
        where = f"{path}:{number}: {row_id or 'row'}"
        if not raw.strip():
            raise SetupError(f"{path}:{number}: row: blank line")
        if len(fields) != len(COLUMNS):
            raise SetupError(f"{where}: {len(fields)} fields, expected {len(COLUMNS)}")
        row = dict(zip(COLUMNS, (f.strip() for f in fields)))
        if not row_id:
            raise SetupError(f"{where}: empty id")
        if row_id in seen:
            raise SetupError(f"{where}: duplicate id")
        seen.add(row_id)
        if not row["source"]:
            raise SetupError(f"{where}: empty source")
        if row["case"] not in CASES:
            raise SetupError(f"{where}: case must be sensitive or insensitive: '{row['case']}'")
        if row["category"] not in CATEGORIES:
            raise SetupError(f"{where}: category must be one of "
                             f"{', '.join(sorted(CATEGORIES))}: '{row['category']}'")
        if not row["pattern"]:
            raise SetupError(f"{where}: empty pattern")
        try:
            regex = re.compile(rf"{WORD_START}(?:{row['pattern']}){WORD_END}",
                               CASES[row["case"]])
        except re.error as exc:
            raise SetupError(f"{where}: pattern does not compile: {exc}")
        terms.append((row_id, regex))
    return terms


def load_exempt(path):
    """Returns the exemption globs or raises SetupError naming the line."""
    globs = []
    for number, raw in enumerate(read_lines(path), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        glob, sep, reason = line.partition(" # ")
        if not sep or not reason.strip() or not glob.strip():
            raise SetupError(f"{path}:{number}: exemption has no ' # reason': {line}")
        globs.append(glob.strip())
    return globs


def display_path(path):
    path = path.resolve()
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def git_files():
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True,
                             check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SetupError(f"wording check: git ls-files failed: {exc}")
    names = [n for n in out.decode("utf-8").split("\0") if n]
    # A tracked file deleted in the working tree has nothing to scan.
    return [p for p in (REPO_ROOT / n for n in names) if p.is_file()]


def walk(paths):
    files = []
    for arg in paths:
        path = Path(arg)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(p for p in path.rglob("*") if p.is_file()))
        else:
            raise SetupError(f"wording check: {arg}: no such file or directory")
    return files


def check_text(shown, text, terms):
    """Matches each term over the whole text, so a multi-word term split by a
    line wrap still matches; each hit is reported on the line it starts on."""
    newlines = [i for i, c in enumerate(text) if c == "\n"]

    def line_of(offset):
        return bisect.bisect_right(newlines, offset - 1) + 1

    hits = []
    for row_id, regex in terms:
        for m in regex.finditer(text):
            matched = " ".join(m.group(0).split())
            hits.append((m.start(), f"{shown}:{line_of(m.start())}: {matched}: term {row_id}"))
    for m in EM_DASH_RE.finditer(text):
        hits.append((m.start(), f"{shown}:{line_of(m.start())}: em dash"))
    hits.sort(key=lambda h: h[0])
    return [message for _, message in hits]


def main(argv):
    parser = argparse.ArgumentParser(description="Wording check (Story 0.4).")
    parser.add_argument("--terms", type=Path, default=DEFAULT_TERMS)
    parser.add_argument("--exempt", type=Path, default=DEFAULT_EXEMPT)
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv[1:])

    try:
        terms = load_terms(args.terms)
        globs = load_exempt(args.exempt)
        files = walk(args.paths) if args.paths else git_files()
    except SetupError as exc:
        print(exc, file=sys.stderr)
        return 2

    problems = []
    scanned = 0
    seen = set()
    for path in files:
        shown = display_path(path)
        if shown in seen or any(fnmatch.fnmatchcase(shown, g) for g in globs):
            continue
        seen.add(shown)
        try:
            data = path.read_bytes()
        except OSError as exc:
            problems.append(f"{shown}: cannot read: {exc}")
            continue
        if data.startswith(UTF16_BOMS):
            scanned += 1
            problems.append(f"{shown}: not valid UTF-8 text: UTF-16 byte order mark")
            continue
        if b"\0" in data[:BINARY_PROBE]:
            continue
        scanned += 1
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            problems.append(f"{shown}: not valid UTF-8 text: {exc}")
            continue
        problems.extend(check_text(shown, text, terms))

    for line in problems:
        print(line)
    if problems:
        print(f"wording check: {len(problems)} problem(s) in {scanned} file(s) scanned",
              file=sys.stderr)
        return 1
    print(f"wording check: {scanned} file(s) scanned, no listed term or em dash")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    sys.exit(main(sys.argv))
