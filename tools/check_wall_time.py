"""Checks a CI job's wall time against the budget table, or estimates monthly CI minutes.

Usage:
  python tools/check_wall_time.py --tier fast|full --job NAME --start EPOCH [--now EPOCH] [--budget FILE]
  python tools/check_wall_time.py --estimate [--budget FILE]

Budget table (default ci/wall_time_budget.json):

  {"allowance_minutes_per_month": 2000, "public_repo": true, "source": "...",
   "tiers": {"fast": {"<job>": {"budget_minutes": 15, "runner": "ubuntu-24.04",
                                "multiplier": 1, "runs_per_month": 120}},
             "full": {...}}}

Check mode prints the job's wall minutes against its budget minutes and exits
1 when the wall time is over budget or the job is not in the table. Each job
records its start (epoch seconds) in its first step and runs this in its last
step, which runs even when an earlier step failed.

Estimate mode prints, per runner label, the monthly minutes (budget minutes
times runs per month, summed over jobs), the billing multiplier, and the
billed-equivalent minutes, then the total against the allowance. A public
repo is billed zero minutes on GitHub-hosted runners. Exit 0.

Standard library only.
"""

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUDGET = REPO_ROOT / "ci" / "wall_time_budget.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check(table, tier, job, start, now):
    entry = table.get("tiers", {}).get(tier, {}).get(job)
    if entry is None:
        print(f"wall time: job {tier}/{job} is not in the budget table")
        return 1
    budget = entry["budget_minutes"]
    wall = (now - start) / 60.0
    verdict = "over budget" if wall > budget else "within budget"
    print(f"wall time: {tier}/{job}: {wall:.1f} min of {budget} min budget ({verdict}, runner {entry['runner']})")
    if wall > budget:
        print(f"wall time: {tier}/{job} took {wall:.1f} min, over its {budget} min budget")
        return 1
    return 0


def estimate(table):
    per_runner = {}
    for tier, jobs in table.get("tiers", {}).items():
        for job, entry in jobs.items():
            row = per_runner.setdefault(entry["runner"], {"minutes": 0, "multiplier": entry["multiplier"]})
            if row["multiplier"] != entry["multiplier"]:
                print(f"estimate: runner {entry['runner']} has two multipliers in the table")
                return 1
            row["minutes"] += entry["budget_minutes"] * entry["runs_per_month"]
    allowance = table["allowance_minutes_per_month"]
    public = bool(table.get("public_repo"))
    print(f"{'runner':<18} {'minutes/month':>14} {'multiplier':>11} {'billed-equivalent':>18}")
    total_raw = 0
    total_billed = 0
    for runner in sorted(per_runner):
        row = per_runner[runner]
        billed = row["minutes"] * row["multiplier"]
        total_raw += row["minutes"]
        total_billed += billed
        print(f"{runner:<18} {row['minutes']:>14} {row['multiplier']:>11} {billed:>18}")
    print(f"{'total':<18} {total_raw:>14} {'':>11} {total_billed:>18}")
    print(f"allowance: {allowance} min/month; billed-equivalent if private: {total_billed} min/month")
    if total_billed > allowance:
        print(f"shortfall if private: {total_billed - allowance} min/month over the allowance")
    else:
        print("no shortfall: billed-equivalent minutes are within the allowance")
    if public:
        print("billed minutes: 0 (public repo, GitHub-hosted runners are free)")
    else:
        print(f"billed minutes: {total_billed} (private repo)")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description="Check CI wall time against the budget table.")
    parser.add_argument("--budget", type=Path, default=DEFAULT_BUDGET)
    parser.add_argument("--estimate", action="store_true")
    parser.add_argument("--tier", choices=["fast", "full"])
    parser.add_argument("--job")
    parser.add_argument("--start", type=float)
    parser.add_argument("--now", type=float)
    args = parser.parse_args(argv[1:])
    try:
        table = load(args.budget)
    except (OSError, ValueError) as exc:
        print(f"wall time: cannot read budget table {args.budget}: {exc}")
        return 1
    try:
        if args.estimate:
            return estimate(table)
        if args.tier is None or args.job is None or args.start is None:
            parser.error("--tier, --job, and --start are required unless --estimate is given")
        now = args.now if args.now is not None else time.time()
        return check(table, args.tier, args.job, args.start, now)
    except (KeyError, TypeError) as exc:
        print(f"wall time: budget table {args.budget} is missing a field: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
