"""CI check: no recipe file changes during a run (Story 4.2).

Only the dev PC stores loudness gains (docs/signal-spec.md, Loudness gain,
Store); a CI run must never write one. This runs at the end of every CI job,
right before the wall-time step.

Usage:
  python tools/check_recipes_unchanged.py [--repo DIR]

Runs `git status --porcelain --untracked-files=all -- recipes` in DIR
(default: the repo root). Exit 0 when it prints nothing. Exit 1 with one
line per modified, added, deleted, or untracked path under recipes/, each
naming the path as git prints it. Exit 2 on a git error (for example DIR is
not a git work tree). Standard library only.
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def changed_paths(repo):
    """The porcelain lines for recipes/, or raise RuntimeError on a git error."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all", "--", "recipes"],
            capture_output=True)
    except OSError as err:
        raise RuntimeError(f"cannot run git: {err}") from err
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip() or f"git exit {result.returncode}")
    return [line for line in result.stdout.decode("utf-8", "replace").splitlines() if line.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fail when any file under recipes/ is changed or added.")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help="the git work tree (default: this repo)")
    args = parser.parse_args(argv)
    try:
        lines = changed_paths(args.repo)
    except RuntimeError as err:
        print(f"check_recipes_unchanged: git error: {err}", file=sys.stderr)
        return 2
    if not lines:
        return 0
    for line in lines:
        status, path = line[:2].strip(), line[3:]
        print(f"check_recipes_unchanged: recipe file changed during the run ({status}): {path}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
