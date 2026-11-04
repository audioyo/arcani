---
title: 'Story 0.4: CI wording check'
type: 'feature'
created: '2026-11-03'
status: 'in-progress'
baseline_commit: '37e260741143377144fb80196419f631b546b8ff'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-0-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The naming and copy rules (CLAUDE.md "Never", PRD §6 Naming, Claims, and Wording) are enforced only by people reading every line. Nothing stops a banned term, a comparable's feature name, a health claim, or an em dash from landing.

**Approach:** One stdlib Python check, `tools/check_wording.py`, scans tracked text files against a term list data file and for em dashes, minus a path exemption list kept in the repo. It runs in both fast CI jobs. Existing violations in scanned files are fixed in this story.

Decisions (2026-11-03, build agent, under Audio's standing "settle tech forks yourselves" preference):
- The whole text of every scanned file is checked, not just comments and strings: a superset that needs no per-language parser and covers recipe descriptions whatever the recipe format (Story 1.1).
- "Expand" (a comparable's product name) is not listed: as a whole word it is an ordinary verb, so every match would be noise. "Sound Science", "BrainWave", "neural phase locking", and "neural effect" are listed.

Decisions by Audio (2026-11-03):
- `docs/project-plan.md`: its clean-room and patent sections move to a new exempt research file, `docs/research-ip-and-clean-room.md`, which describes sources. The plan links to it and its remaining mentions are reworded to "the earlier project" or similar neutral wording.
- CLAUDE.md and all of `_bmad-output/` are exempt as rule sources and planning records. The check guards `docs/`, code, tests, tools, CI files, recipes, and READMEs.
- Claim words are only those the rules name: health, therapy, therapeutic, treatment, neurostimulation, medical (CLAUDE.md, PRD §6), plus ADHD and insomnia (`research-comparables.md`).

## Boundaries & Constraints

**Always:**
- Term list `tools/wording/terms.tsv`, tab-separated with one header row: `id, pattern, case, category, source`. `pattern` is a Python regex matched at word boundaries; `case` is `sensitive` or `insensitive`; `category` is `project-term`, `comparable-name`, or `claim`; `source` cites CLAUDE.md, PRD §6, or `research-comparables.md`. Load fails, naming line and id, on an empty source, bad case or category, duplicate id, or a pattern that does not compile.
- Exemption list `tools/wording/exempt.txt`: one glob per line, each followed by ` # reason`; a line with no reason fails. It holds the term list itself, the research files (`docs/research-library.md`, `docs/research-ip-and-clean-room.md`), CLAUDE.md, `_bmad-output/**`, vendored agent tooling (`_bmad/**`, `.claude/**`, `.agents/**`), and the must-fail fixtures. `tests/python/test_check_wording.py` is not exempt, so it never spells a listed term; it reads them from fixtures.
- Scanned files: `git ls-files` minus exemptions; files with a NUL byte in their first 8 KiB are skipped as binary; an undecodable non-binary file fails.
- Output: one line per match, `<path>:<line>: <matched text>: term <id>` or `<path>:<line>: em dash` (U+2014). Exit 0 with the count of files scanned; 1 on any match; 2 on a setup error. `--terms`, `--exempt`, and positional paths override the defaults for tests.
- Must-fail fixtures under `tests/fixtures/wording/`: a doc with an em dash, a recipe file whose description has a health claim, a code comment with a banned term; plus a passing fixture and a research-path fixture that passes only through its exemption. Tests first by a fresh-context QA agent, committed tests-only before implementation.
- Both fast jobs run the check before the build; `tests/python/test_ci_workflows.py` covers the step.
- Design log entry (dd): term list, exemption list, decisions above. No em dashes; no new banned terms outside exempt files.

**Never:**
- Weakening a pattern or adding an exemption just to make the current repo pass without a reason line.
- Signal, engine, table, or threshold changes.
- Pushing or opening the pull request without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Clean repo | current tree after fixes | exit 0 | N/A |
| Em dash | doc fixture with U+2014 | exit 1 | names file, line |
| Health claim | recipe fixture description | exit 1 | names file, line, term |
| Banned term | code comment fixture | exit 1 | names file, line, term |
| Research file | listed term under an exempt glob | exit 0 | N/A |
| Term list itself | terms.tsv holds every term | not scanned | N/A |
| Word boundary | `sample`, `Samsung`, `gatewayed` style text | no match | N/A |
| Bad term row | empty source, bad regex, duplicate id | exit 2 | names line, id |
| Unreasoned exemption | glob with no `# reason` | exit 2 | names line |

</frozen-after-approval>

## Code Map

- `tools/check_fp_pragmas.py` -- pattern to follow: docstring with usage and exit codes, stdlib only, `<path>:<line>: <text>: <reason>` lines.
- `tests/python/test_fp_pragmas.py` -- test pattern: runs the tool on fixture dirs with `subprocess`, checks exit code and lines.
- `tests/assertions/tables.py` -- TSV loading style (header row, line-numbered errors) to mirror; do not import it (thresholds only).
- `.github/workflows/fast.yml` -- add "Wording check" after "Floating-point pragma check" in `linux-x64` and `windows-x64`, `uv run --no-project python tools/check_wording.py`.
- `tests/python/test_ci_workflows.py` -- extend to require the step in both jobs.
- `ci/wall_time_budget.json` -- unchanged; the scan takes seconds.
- `docs/project-plan.md` -- the only scanned file with current hits. Move "IP and clean-room rules" (around lines 61-93, the source and patent tables) and the motion-layer comparison table (around 139-141) to `docs/research-ip-and-clean-room.md`; reword lines 11-14, 27, 41, 282, 399, 406 and keep every link that other docs cite (grep for `project-plan.md#`). Lines 13 and 406 hold claim words in prohibition sentences; reword to describe the sound. No em dashes in scanned files today.
- `docs/design-log.md` -- entry (dd) at the top of the dated entries, above (cc).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` -- `0-3-threshold-and-range-tables-as-data: done` (PR #3 merged as 37e2607).
- Do not change: engine, tables, `tools/check_fp_pragmas.py`.

## Tasks & Acceptance

**Execution:**
- [x] QA agent, failing tests-only commit: `tests/python/test_check_wording.py` and `tests/fixtures/wording/*` from the matrix.
- [x] `tools/wording/terms.tsv`, `tools/wording/exempt.txt`, `tools/check_wording.py`.
- [x] `docs/project-plan.md`, `docs/research-ip-and-clean-room.md` -- split and reword per Audio's decision.
- [x] `.github/workflows/fast.yml`, `tests/python/test_ci_workflows.py`.
- [x] `docs/design-log.md`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given a clean checkout, when `uv run pytest` and `uv run python tools/check_wording.py` run, then both pass.
- Given Audio's go-ahead to push, when the fast tier runs on the branch, then both jobs run the wording check and pass.

## Implementation Notes

- Tests-only commit 3ffaa7b (fresh-context QA agent). The interface it fixes is in the docstring of `tests/python/test_check_wording.py`: flags `--terms`, `--exempt`, positional paths (directories walked; exemptions still apply, globs matched on repo-relative POSIX paths); exit 0/1/2; setup-error messages name `:<line>:` or `line <line>` and the id. The real `exempt.txt` must cover `tests/fixtures/wording/terms.tsv`, `tests/fixtures/wording/mustfail/**`, `tests/fixtures/wording/research/**`; the real terms must catch the must-fail fixtures. Make these tests pass; do not edit them.
- Audio's own uncommitted edit to `CLAUDE.md` and untracked `docs/timeline-guidebook.html` are not part of this story: leave both untouched and uncommitted.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `uv run python tools/check_wording.py` -- expected: exit 0, file count printed.
- `uv run pytest` -- expected: all pass.
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: pass (unchanged).
