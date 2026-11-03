# CI setup: manual steps for Audio

The workflows live in `.github/workflows/`. Two tiers run there:

- **fast** (`fast.yml`): every push, Windows x64 and Linux x64.
- **full** (`full.yml`): every pull request into `main`, nightly at 03:00 UTC (9 pm your time), and manual runs. Windows x64, Windows arm64, macOS arm64, and the Android NDK arm64 build, plus the hash compare. Its last job, `verdict`, passes only when every other job passed, or when the nightly run was skipped because `main` had not changed.

Every runner is GitHub-hosted. The repo is public, so these runs are free. Background and numbers: design log entries 2026-11-02 (y) and (aa).

These settings are in GitHub, not in the repo, so they are done by hand. Do them once, after the full workflow has run at least once (checks only show up in the picker after they have run).

## 1. Spending cap at $0

So a mistake can never bill you.

1. On GitHub, open your account menu (top right), then **Settings**.
2. Open **Billing and licensing**, then **Budgets and alerts** (older layout: **Spending limits**).
3. For **Actions**, set the budget (or spending limit) to **$0** and turn on **Stop usage when budget limit is reached**.
4. Save.

## 2. Branch rule for `main`

1. Open the repo `audioyo/arcani`, then **Settings**, then **Rules** (or **Branches**).
2. Edit the rule for `main` that part 1 set up (design log entry (y)).
3. Keep: require a pull request before merging; require the status checks `windows-x64` and `linux-x64` from `fast`; require branches to be up to date.
4. Add the status check **`verdict`** from the workflow **full**.
5. Save.

After this, a pull request into `main` cannot merge unless the full tier passed. The full workflow also has a job called `windows-x64`; the `windows-x64` check required in step 3 is the fast one, and both must pass anyway.

## 3. First manual full run

1. Open the repo, then **Actions**, then the **full** workflow.
2. Click **Run workflow**, pick the branch, and run it.
3. When it ends, every job should be green, and each job's last step prints its wall time against its budget. Tell Claude the run number so the design log can record it and the budgets can be corrected.
