"""Two-way coverage between assertions and table rows (Story 0.3).

Usage:
  python tools/check_row_coverage.py [--tables DIR] [--usage FILE ...] [--sprint-status FILE]

Reads both tables with the Python loader (tests/assertions/tables.py), the
row usage files that pytest and ctest write (one id per line; defaults:
build/row-usage/*.txt), and the development_status of the sprint status file
(default _bmad-output/implementation-artifacts/sprint-status.yaml).

Fails, one line per problem naming the row id, on:
- a row no assertion used whose `pending` is empty;
- a row an assertion used that is still `pending` (clear the field);
- a `pending` story key that is not in sprint status;
- a `pending` story whose status is `done`;
- a usage file id that is in no table.

Exit 0 when nothing fails, 1 on any problem or a table error, 2 when no usage
file exists (run ctest and pytest first). Needs pyyaml (a locked dev
dependency): run with `uv run --locked`.
"""

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

from assertions.tables import TableError, load_tables  # noqa: E402

DEFAULT_SPRINT = REPO_ROOT / "_bmad-output" / "implementation-artifacts" / "sprint-status.yaml"


def default_usage_files():
    return sorted((REPO_ROOT / "build" / "row-usage").glob("*.txt"))


def read_usage(paths):
    used = set()
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                used.add(line)
    return used


def problems(rows, used, status):
    out = []
    for r in rows.values():
        where = f"{r.path.name}:{r.line}"
        if r.pending:
            if r.id in used:
                out.append(f"row `{r.id}` ({where}) is used by an assertion but still pending on "
                           f"story {r.pending}; clear its pending field")
            if r.pending not in status:
                out.append(f"row `{r.id}` ({where}) is pending on story {r.pending}, which is not "
                           f"in sprint status")
            elif status[r.pending] == "done":
                out.append(f"row `{r.id}` ({where}) is pending on story {r.pending}, which is done; "
                           f"the story must assert the row")
        elif r.id not in used:
            out.append(f"row `{r.id}` ({where}) is not used by any assertion and has no pending story")
    for row_id in sorted(used - set(rows)):
        out.append(f"usage file names row `{row_id}`, which is in no table")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tables", default=str(REPO_ROOT / "tests" / "tables"))
    parser.add_argument("--usage", nargs="+", action="extend")
    parser.add_argument("--sprint-status", default=str(DEFAULT_SPRINT))
    args = parser.parse_args(argv)

    usage_files = [Path(p) for p in args.usage] if args.usage else default_usage_files()
    usage_files = [p for p in usage_files if p.is_file()]
    if not usage_files:
        print("check_row_coverage: no row usage file found; run ctest and pytest first "
              "(they write build/row-usage/ctest.txt and pytest.txt)", file=sys.stderr)
        return 2
    try:
        rows = load_tables(args.tables)
    except TableError as e:
        print(f"check_row_coverage: {e}")
        return 1
    data = yaml.safe_load(Path(args.sprint_status).read_text(encoding="utf-8")) or {}
    status = {str(k): str(v) for k, v in (data.get("development_status") or {}).items()}

    found = problems(rows, read_usage(usage_files), status)
    for line in found:
        print(line)
    if found:
        return 1
    names = ", ".join(p.name for p in usage_files)
    print(f"check_row_coverage: {len(rows)} rows, each used or pending on an open story ({names})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
