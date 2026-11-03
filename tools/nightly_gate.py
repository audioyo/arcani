"""Decides whether a full-tier run goes ahead or is a nightly skip.

Usage:
  python tools/nightly_gate.py --event EVENT --main-sha SHA --runs FILE [--github-output FILE]

FILE is the GitHub API list of the full workflow's runs:
{"workflow_runs": [{"id", "head_sha", "head_branch", "event", "status",
"conclusion", "created_at"}, ...]}.

Only a schedule event can skip. It skips when the newest successful run on
main from a schedule or manual (workflow_dispatch) event has head_sha equal
to SHA, the current main. The reason is then
"skipped: main unchanged since run <id> (<sha>)". Pull request and manual
runs never skip.

Prints the reason and appends "run=true|false" and "reason=<text>" to the
GitHub output file. Exit 0 on a decision, 1 on malformed input.

Standard library only.
"""

import argparse
import json
import sys
from pathlib import Path

BASELINE_EVENTS = {"schedule", "workflow_dispatch"}


def decide(event, main_sha, runs):
    if event != "schedule":
        return True, f"run: {event} runs never skip"
    candidates = [
        r for r in runs
        if r.get("conclusion") == "success"
        and r.get("head_branch") == "main"
        and r.get("event") in BASELINE_EVENTS
    ]
    if not candidates:
        return True, "run: no successful scheduled or manual full run on main yet"
    newest = max(candidates, key=lambda r: (str(r.get("created_at", "")), int(r.get("id", 0))))
    if newest.get("head_sha") == main_sha:
        return False, f"skipped: main unchanged since run {newest['id']} ({newest['head_sha']})"
    return True, (
        f"run: main is {main_sha}, last passing full run {newest['id']} was on {newest.get('head_sha')}"
    )


def main(argv):
    parser = argparse.ArgumentParser(description="Nightly skip gate for the full workflow.")
    parser.add_argument("--event", required=True)
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv[1:])
    try:
        data = json.loads(args.runs.read_text(encoding="utf-8"))
        runs = data["workflow_runs"]
        if not isinstance(runs, list) or not all(isinstance(r, dict) for r in runs):
            raise ValueError("workflow_runs must be a list of objects")
        run, reason = decide(args.event, args.main_sha, runs)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"nightly gate: cannot read runs from {args.runs}: {exc}")
        return 1
    print(reason)
    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as out:
            out.write(f"run={'true' if run else 'false'}\n")
            out.write(f"reason={reason}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
