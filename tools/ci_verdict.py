"""Final verdict of the full-tier workflow.

Usage:
  python tools/ci_verdict.py --needs FILE

FILE is toJSON(needs) from the verdict job:
{"<job>": {"result": "success|failure|cancelled|skipped", "outputs": {...}}}.
The gate job's outputs carry "run" ("true" or "false") and "reason".

Passes (exit 0) when the gate succeeded, run is "true", and every other
required job reports success. The only other pass is a nightly skip: gate
succeeded, run is "false", and every other required job was skipped; it
prints a "::notice::" line with the gate's reason. Anything else, including a
skipped, cancelled, or never-scheduled (missing) Android job, exits 1 with one
line per offending job naming the job and its result.

Standard library only.
"""

import argparse
import json
import sys
from pathlib import Path

GATE = "gate"
REQUIRED_JOBS = [
    "windows-x64",
    "windows-arm64",
    "macos-arm64",
    "android-build",
    "android-arm64",
    "contract-mustfail",
    "hash-compare",
]


def result_of(needs, job):
    entry = needs.get(job)
    if not isinstance(entry, dict):
        return "missing"
    return str(entry.get("result", "missing"))


def verdict(needs):
    """Returns (passed, lines)."""
    gate_result = result_of(needs, GATE)
    if gate_result != "success":
        return False, [f"verdict: job {GATE} result {gate_result} (must be success)"]
    outputs = needs[GATE].get("outputs") or {}
    run = outputs.get("run")
    reason = outputs.get("reason", "")
    results = {job: result_of(needs, job) for job in REQUIRED_JOBS}
    if run == "true":
        bad = [f"verdict: job {job} result {res} (must be success)" for job, res in results.items() if res != "success"]
        if bad:
            return False, bad
        return True, [f"verdict: all {len(REQUIRED_JOBS) + 1} required jobs succeeded"]
    if run == "false":
        bad = [
            f"verdict: job {job} result {res} (a nightly skip must skip every job)"
            for job, res in results.items() if res != "skipped"
        ]
        if bad:
            return False, bad
        return True, [f"::notice::{reason}", f"verdict: nightly skip: {reason}"]
    return False, [f"verdict: gate output run is {run!r}, expected 'true' or 'false'"]


def main(argv):
    parser = argparse.ArgumentParser(description="Final verdict of the full workflow.")
    parser.add_argument("--needs", required=True, type=Path)
    args = parser.parse_args(argv[1:])
    try:
        needs = json.loads(args.needs.read_text(encoding="utf-8"))
        if not isinstance(needs, dict):
            raise ValueError("needs must be a JSON object")
    except (OSError, ValueError) as exc:
        print(f"verdict: cannot read needs from {args.needs}: {exc}")
        return 1
    passed, lines = verdict(needs)
    for line in lines:
        print(line)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
