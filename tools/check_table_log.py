"""Design log gate for the threshold and range tables (Story 0.3).

Usage:
  python tools/check_table_log.py --base REF [--repo DIR]

Compares tests/tables/thresholds.tsv and tests/tables/ranges.tsv at REF
(`git show`; a file missing at REF has no rows) with the working tree (a
missing file has no rows). Rows are keyed by id. A changed id is one that was
added, removed, or changed in any field except `pending`: marking a row as
used, or pending on another story, is not a value change (CLAUDE.md,
Workflow; spec decision 2026-11-03).

Every changed id must appear in backticks, such as `drift-8h`, on a line
added to docs/design-log.md between REF and the working tree
(`git diff REF -- docs/design-log.md`).

Exit 0 when every changed id is logged, or nothing changed. Exit 1 with one
line per unlogged id. Exit 2 on a git error (bad REF, not a repository).
CI passes the merge base with origin/main as REF. Standard library only.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

TABLES = ("tests/tables/thresholds.tsv", "tests/tables/ranges.tsv")
DESIGN_LOG = "docs/design-log.md"
BACKTICK_RE = re.compile(r"`([^`\n]+)`")


class GitError(Exception):
    pass


def git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if check and result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result


def rows_of(text):
    """Raw TSV rows keyed by id, each a dict of every field but pending."""
    lines = [line.rstrip("\r") for line in text.split("\n") if line.strip()]
    if not lines:
        return {}
    header = lines[0].split("\t")
    rows = {}
    for line in lines[1:]:
        fields = line.split("\t")
        record = dict(zip(header, fields))
        record["_extra"] = "\t".join(fields[len(header):])
        record.pop("pending", None)
        rows[fields[0]] = record
    return rows


def at_ref(repo, ref, path):
    result = git(repo, "show", f"{ref}:{path}", check=False)
    if result.returncode != 0:
        # Distinguish a missing file from a bad ref.
        git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        return ""
    return result.stdout.decode("utf-8")


def in_tree(repo, path):
    p = Path(repo) / path
    return p.read_bytes().decode("utf-8") if p.is_file() else ""


def changed_ids(repo, ref):
    out = []
    for path in TABLES:
        old = rows_of(at_ref(repo, ref, path))
        new = rows_of(in_tree(repo, path))
        for row_id in new:
            if row_id not in old:
                out.append((row_id, "added", path))
            elif new[row_id] != old[row_id]:
                out.append((row_id, "changed", path))
        for row_id in old:
            if row_id not in new:
                out.append((row_id, "removed", path))
    return out


def logged_ids(repo, ref):
    diff = git(repo, "diff", "--no-color", "--no-ext-diff", ref, "--", DESIGN_LOG)
    ids = set()
    for line in diff.stdout.decode("utf-8", "replace").split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            ids.update(BACKTICK_RE.findall(line))
    return ids


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", required=True, help="git ref to compare against")
    parser.add_argument("--repo", help="repository root (default: git top level of the cwd)")
    args = parser.parse_args(argv)
    try:
        if args.repo:
            repo = Path(args.repo)
        else:
            top = git(".", "rev-parse", "--show-toplevel")
            repo = Path(top.stdout.decode("utf-8").strip())
        git(repo, "rev-parse", "--verify", "--quiet", f"{args.base}^{{commit}}")
        changes = changed_ids(repo, args.base)
        logged = logged_ids(repo, args.base) if changes else set()
    except GitError as e:
        print(f"check_table_log: {e}", file=sys.stderr)
        return 2
    unlogged = [c for c in changes if c[0] not in logged]
    for row_id, how, path in unlogged:
        print(f"unlogged table change: row `{row_id}` {how} in {path}; add a {DESIGN_LOG} "
              f"line naming `{row_id}` in backticks")
    if unlogged:
        return 1
    print(f"check_table_log: {len(changes)} changed row(s) since {args.base}, all logged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
