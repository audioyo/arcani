---
title: 'Story 0.5: Independent review of the pending architecture decisions'
type: 'chore'
created: '2026-11-04'
status: 'in-progress'
baseline_commit: '921b53f456efb36973da0dee81713b695238c614'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-0-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** AD-4, AD-5, AD-9, AD-19, AD-20 and the Stack table still carry `[REVIEW PENDING]` in the architecture spine. CLAUDE.md rule 4 says they lock only after an independent review, and Epic 1 may not start until they do.

**Approach:** Fresh-context reviewer agents, with no part in writing the spine, review each decision against the PRD, SPEC, CLAUDE.md, the research library, and the S0.2 result (design log (bb): byte-identical on all four platforms, no fallback used). Each decision gets a verdict, lock or change; findings are saved beside the spine's existing reviews and applied.

Decisions (2026-11-04, build agent, under Audio's standing "settle tech forks yourselves" preference):
- Two reviewers run in parallel: (A) the signal decisions AD-4, AD-5, AD-19, AD-20; (B) AD-9 and the Stack table, with a web check of every pinned version. Neither sees the other's output.
- A "lock" verdict is applied directly. A "change" verdict that alters what a decision requires is shown to Audio in plain language before it is applied; wording that only records what the repo already does (for example, Stack pins already logged in design log (y), (aa)) counts as a lock with an edit.

## Boundaries & Constraints

**Always:**
- Each verdict cites the source it was checked against (file and section) and, for AD-9, design log (bb) and the full run it names.
- AD-9 review states whether the -100 dBFS fallback and its scope stay as written, given that S0.2 needed no fallback, and whether the Android check (static NDK binary on hosted arm64 Linux, design log (aa)) satisfies "emulator or device".
- Locked decision: `[REVIEW PENDING]` removed from its heading. Changed decision: new text, a design log entry with the reason, and every affected story in `epics.md` updated.
- One design log entry (ee) records every verdict and names the review file.
- No em dashes; no banned terms (wording check passes).

**Never:**
- Signal, engine, table, threshold, or CI changes in this story. A finding that needs one becomes a `deferred-work.md` entry or a story update.
- Weakening a decision to dodge a finding without stating the finding and Audio's choice.
- Pushing or opening the pull request without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| All lock | every verdict lock | six tags removed, entry (ee), test passes | N/A |
| One change | a verdict alters a rule | Audio decides first; then text, log entry, affected stories | Audio declines: lock as written, finding recorded as rejected with reason |
| Tag left | spine still has `[REVIEW PENDING]` | test fails | names the heading |
| No verdict | review file misses one of the six | test fails | names the decision |

</frozen-after-approval>

## Code Map

- `_bmad-output/planning-artifacts/architecture/architecture-Arcani-2026-10-27/ARCHITECTURE-SPINE.md` -- line 27 review-status note, AD headings at lines 92, 98, 122, 182, 188, Stack table at 239, Open Questions row for the review at about 339 (mark resolved, cite entry (ee)). Stack table is stale against `toolchain.json` (LLVM 23.1.4, Apple clang 17.0.0, Ninja 1.13.2, pytest pin) and design log (y), (aa).
- `.../reviews/` -- existing reviews use YAML front matter (title, reviewed, date, method) plus a Verdict section. New file: `review-independent-s0-5.md`.
- `.../.memlog.md` -- append an `(outcome)` line per verdict.
- `docs/design-log.md` -- entry (ee) at the top of entries, above (dd); entry (bb) holds the S0.2 result.
- `_bmad-output/planning-artifacts/epics.md` line 93 and `_bmad-output/specs/spec-arcani-v0-1/SPEC.md` line 114 -- the "REVIEW PENDING" notes: say the review closed, cite (ee).
- `tests/python/test_repo_layout.py` -- style for a small repo-content test.
- `sprint-status.yaml`, `docs/timeline-guidebook.html` -- status and UPDATE_LOG per CLAUDE.md Workflow.
- Do not change: `engine/`, `tests/tables/`, `ci/`, `.github/`, `docs/signal-spec.md`.

## Tasks & Acceptance

**Execution:**
- [x] `tests/python/test_architecture_review.py` -- fresh-context QA agent, failing tests-only commit: spine has no `[REVIEW PENDING]`; the review file exists and gives a lock or change verdict for each of AD-4, AD-5, AD-9, AD-19, AD-20, Stack; design log has entry (ee) naming the review file.
- [x] `reviews/review-independent-s0-5.md` -- run reviewers A and B, merge their findings with a verdict table.
- [x] Audio checkpoint for any "change" verdict.
- [x] Spine, `.memlog.md`, `epics.md`, `SPEC.md`, affected stories -- apply verdicts.
- [x] `docs/design-log.md`, `sprint-status.yaml`, `docs/timeline-guidebook.html` -- records.

**Acceptance Criteria:**
- Given a clean checkout, when `uv run pytest` and `uv run python tools/check_wording.py` run, then both pass.
- Given the spine, when searched, then no `[REVIEW PENDING]` remains and the review Open Question is marked resolved.

## Implementation Notes

- Tests-only commit b52ff92 (fresh-context QA agent): `tests/python/test_architecture_review.py`. Its module docstring fixes the verdict table format (`| Decision | Verdict | ... |`, Decision exactly one of `AD-4`, `AD-5`, `AD-9`, `AD-19`, `AD-20`, `Stack`, each once; Verdict exactly `lock` or `change`). The spine's line 27 "Review status" note also contains the literal tag and must be reworded. Make these tests pass; do not edit them.
- Reviews done by the orchestrator (reviewers A and B, fresh context, run in parallel). Full findings, to merge into `reviews/review-independent-s0-5.md` (keep both reviewers' findings, sections, and citations; add the combined verdict table at the top; record Audio's decisions below):
  - `C:\Users\goegl\AppData\Local\Temp\claude\C--Users-goegl-OneDrive-Documents-Antigravity-Arcani\619ad9dc-345e-4ec4-98a5-fb21c5e9f1ab\scratchpad\review-A.md` (AD-4 lock, AD-5 change, AD-19 lock, AD-20 lock; each with exact wording edits)
  - `C:\Users\goegl\AppData\Local\Temp\claude\C--Users-goegl-OneDrive-Documents-Antigravity-Arcani\619ad9dc-345e-4ec4-98a5-fb21c5e9f1ab\scratchpad\review-B.md` (AD-9 change, Stack change; proposed AD-9 text and replacement Stack table)
- Audio's checkpoint decisions (2026-11-04), all approved as the reviewers proposed:
  1. AD-5: apply reviewer A's new rule (reject coupled gamma when the theta reference is absent, at zero level, or at zero AM depth wherever gamma level and depth are non-zero; uncoupled gamma has constant depth). Update epics.md FR-3 line, S2.3 (rejection AC plus must-fail fixture), S6.5, SPEC CAP-4.
  2. AD-9 phone: require the engine library from the real Android app build to match the hashes on a physical phone before the Phase 0 part 2 stack spike closes. The hosted static NDK run stays the v0.1 proof.
  3. AD-9 rules: apply reviewer B's full proposed AD-9 text (IEEE denormal mode restored on return, no explicit fma, no `long double`, float-to-integer clamp rule, x86-64 only, narrowed fallback with rule-4 review). Update Stories 1.2, 1.4, 1.6, and Story 0.1's AC text (records the chosen alternative) in epics.md.
  4. Stack: apply reviewer B's replacement Stack table (miniaudio 0.11.26 floor, Flutter 3.47.8 floor, rows for what the repo already pins).
- Wording edits for the locked AD-4, AD-19, AD-20 are reviewer A's; apply them exactly. Design log entry (ee) covers every verdict, these decisions, and the advisory links for the Stack changes; it supersedes the AD-9 wording points of (j) where they differ. Low-severity notes that need later work and have no story become `deferred-work.md` entries. Update the spine's `updated:` front matter.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass, including the new test.
- `uv run python tools/check_wording.py` -- expected: exit 0.

**Manual checks:**
- Each verdict in the review file cites its source; each change has a design log line and updated stories.
