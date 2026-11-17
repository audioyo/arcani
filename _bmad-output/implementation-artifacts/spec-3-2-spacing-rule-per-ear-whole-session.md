---
title: 'Story 3.2: Spacing rule per ear, whole session'
type: 'feature'
created: '2026-11-16'
baseline_commit: '12e3ad2aa60ff159e40025f305aaba3482b9c793'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-1-spectral-component-table-per-shape.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Compile builds the component table (Story 3.1) but nothing checks it. A recipe whose layers come within 50 Hz of each other in one ear still compiles. Threshold row `spacing-rule` (50 Hz, a placeholder) is pending on this story.

**Approach:** The signal spec gains a Spacing section. Compile checks every pair of rows from different layers in the same ear, using the closed-form minimum distance over a whole rate cycle. A failure returns no plan and a detailed error. A passing plan reports each ear's worst margin.

Decisions (2026-11-16, build agent; Audio delegated every decision and approval for Stories 3.1 to 3.3 on 2026-11-16):
- **Pairs.** In each ear, every row of one layer against every row of another: theta reference against gamma PAC, theta reference against binaural, gamma PAC against binaural. A layer's own rows are never compared. The two binaural rows are in different ears, so they are never compared.
- **Closed-form distance.** Every rate cycle has the one period of row `rate-cycle-period`. So the difference of two rows' frequencies is `c + X(t)`, with `c` the difference of their centers and `X(t)` one sinusoid of amplitude `H`. `H` comes from the rows' multiplier differences `(di, dj, db)` and the three cycles' swings and start phases, by the Story 3.1 half-width law extended to three terms. The minimum distance is `max(0, |c| - H)`, taken over a whole cycle whatever the session length, so a collision at any instant is found and the session is never sampled. Reading the multipliers, not the intervals, judges lines that sweep together by their real distance. This closes the 3.1 deferred row. Rows mirrored below 0 Hz use their listed interval and are compared as static intervals at their worst case.
- **Pass and fail.** Pass when the minimum distance is at least the row value (exactly 50 Hz passes), compared in binary64. The rule runs after the component table is built, so after every existing compile rule, and before `final.required`.
- **Which failure.** Among all failing pairs in both ears, report the one with the smallest minimum distance. Ties go to the left ear first, then table order of the first row, then of the second.
- **Error.** Rule `spacing_rule`. Parameter: the carrier field of the pair's later layer in field order (`/gamma_pac/carrier_hz`, or `/binaural/carrier_left_hz`). Value: the minimum distance, shortest round-trip text. Limit: `>= 50 Hz (row spacing-rule)`. `arc_error` and `recipe::Error` gain a `detail` field, empty for every other rule. For spacing it names the ear, both layers, both rows' multipliers and center frequencies, and where the minimum occurs: `whole session` when neither row sweeps; otherwise the first time in seconds from session start, within 1 ms, and the gamma, theta, and beat rates at that time. The engine finds that time with basic operations, `sqrt`, the cycle cosine, and integer bisection on the cycle phase. It makes no transcendental call.
- **Margins.** C API `arc_plan_spacing(plan, ear, out)` gives each ear's minimum distance, its margin (minimum distance less the row value), and the pair. With fewer than two layers in that ear it reports none. The CLI report gains a `spacing` block, written only when at least one ear has a pair. The design log entry lists the margin per starter and per ear, so it is clear which starters still pass when a critical-band source replaces 50 Hz.
- **Starter fixtures.** Four layer-configuration fixtures from `starter-recipes.md` and design log (m), (n): `starter-focus-layers.json`, `starter-learn-layers.json`, `starter-relax-layers.json`, `starter-sleep-layers.json`. Focus and Learn loop at their caps, with opening 60 s and body 120 s. None has ramps or fades (Epic 4). Story 3.3 renders previews from them. They are not the Epic 6 starter recipes.
- **Must-fail fixture.** `spacing-binaural-250-256-gamma-260.json`: gamma PAC 300 Hz carrier, AM at 40 Hz, uncoupled, 100 percent (side frequency 260 Hz), with binaural 250 Hz left and 256 Hz right. Its worst pair is right ear, 4 Hz.
- **Existing fixtures.** Every fixture that compiles today must still compile, unless the Spacing section names it as a collision. The Epic 2 coupled gamma plus binaural recipes (the AD-5 sweep in `test_binaural_ad5.py`) must pass.
- **Carrier rule wording.** The carrier rule stays on the recipe fields. The design log entry records how AD-20's "one table" reads: the spacing rule, the tests, and the carrier guard read the table, and the carrier rule's input is the layer's named rate. It is proposed to Audio as an AD-20 wording note at sign-off. The 3.1 deferred row is then closed.

## Boundaries & Constraints

**Always:** The Spacing section and its vectors land before engine or reference code. Tests come first, from a fresh-context QA agent, committed failing. Must-fails are doctored in the harness, for example a table with one row moved by 1e-9 Hz across the limit. Rows are read only from the tables, and `spacing-rule` loses `pending`. The Python reference computes distances and margins on its own, from the spec. Every pinned hash and vector passes, and report bytes are unchanged for recipes without a pair. Design log entry (ww).

**Never:** Change 50 Hz, the 40 dB component threshold, or the carrier rule. Sample the session. Make a transcendental call in `engine/`. Add starter loudness ramps, fades, or level fields. Do not close the story by weakening the rule if Focus fails: log the cause in the design log and resolve it through the signal spec.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Must-fail | `spacing-binaural-250-256-gamma-260.json` | rejected | `spacing_rule`, right ear, 4 Hz, gamma (1, 0) 260 Hz vs binaural 256 Hz, `whole session` |
| Exactly 50 Hz | theta 450 Hz unmodulated, binaural left 400 Hz | compiles, margin 0 | N/A |
| 49.99 Hz | binaural left 400.01 Hz | rejected | min distance 49.99 |
| Rate cycle collision | a sweep that reaches within 50 Hz only at a turning point | rejected | detail gives the first time and the rates there |
| Sweep together | theta and gamma rows moving with the same theta cycle | judged by `max(0, abs(c) - H)` from the multipliers | N/A |
| Starters | the four starter fixtures, and the AD-5 sweep | compile; margins reported per ear | N/A |
| One layer | theta only | compiles; no spacing pair | N/A |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md` -- new Spacing section after Components; header story list. Components: table, multipliers, Rate cycles half-width law, Frequencies below 0, Engine (allowed operations).
- `tools/signal_spec_vectors.py`, `tests/data/signal_spec_vectors.json`, `tests/cpp/SpecTables.cmake`, `tests/python/test_signal_spec_core.py` (table count) -- vectors.
- `engine/src/validate/components.{hpp,cpp}` -- the table. New `engine/src/validate/spacing.{hpp,cpp}`.
- `engine/src/plan/plan.cpp` -- after the table build; `Plan` gains spacing results.
- `engine/src/recipe/recipe.hpp` (`Error`), `engine/include/arcani/arcani.h` (`arc_error`, new `arc_plan_spacing`), `engine/src/api/api.cpp` (error copy, truncation rule at the header's top).
- `engine/src/core/rate_cycle.*` -- cycle cosine, cycles-to-units.
- `cli/report.{hpp,cpp}`, `cli/main.cpp` -- `spacing` block. Pattern: the optional `loop` block.
- `reference/components.py` -- the reference table. New `reference/spacing.py`.
- `tests/tapdump/main.cpp` -- `--components` mode, which may gain the spacing lines.
- `recipes/fixtures/valid/`, `recipes/README.md`, `tests/data/recipe_hash_vectors.json` (`tools/recipe_hash.py --write-vectors`).
- `tests/python/test_binaural_ad5.py` -- AD-5 sweep recipes.
- Records: `tests/tables/thresholds.tsv`, `docs/design-log.md` (ww), `_bmad-output/specs/spec-arcani-v0-1/starter-recipes.md` (Sleep bound 155 Hz, deferred row), `deferred-work.md` (close the three 3.1 rows and the Sleep bound row), guidebook, `sprint-status.yaml`.

## Tasks & Acceptance

**Execution:**
- [ ] `docs/signal-spec.md`, vectors -- Spacing section with vectors (pair distances, margins, error texts, first-time cases) -- the spec merges first.
- [ ] fixtures, hash vectors, `thresholds.tsv`, design log (ww) -- data.
- [ ] tests -- a fresh-context QA agent writes them failing -- tests first.
- [ ] `engine/src/validate/spacing.*`, plan, error `detail`, C API, CLI report, reference, tap dump -- implementation.
- [ ] `deferred-work.md`, `starter-recipes.md`, guidebook, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given a recipe's component table, when the spacing rule runs, then in each ear it checks 50 Hz between rows of different layers, exactly 50 Hz passes and less fails.
- Given a rate curve on any layer, then the closed-form worst case over the whole range decides, with no sampling.
- Given a spacing failure, then compile returns no plan and the error names parameter, value, rule, limit, both components, their layers, the ear, and where the minimum occurs.
- Given the must-fail fixture, then it is rejected in the right ear.
- Given the four starter fixtures and the AD-5 sweep, then each compiles, and its margins per ear are logged.
- Given engine and reference, then their minimum distances agree within row `component-frequency-error`.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

**Phased handoff (orchestrator).** The work runs as in Story 3.1, on branch `story/3-2-spacing-rule-per-ear-whole-session`, which is cut from the Story 3.1 branch until PR #19 merges.
1. The implementation agent does tasks 1 and 2, writes the test contracts under Implementation Notes, commits, and reports. It writes no engine, reference, or test code in this engagement.
2. A fresh-context QA agent commits the failing tests.
3. The implementation agent does the rest. It never edits a test expectation to make a test pass; it reports a wrong test with the reason.

Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01QHd78sH67YQwRftvvcTvJA`. Leave `.memlog.md` alone and edit with UTF-8-safe tools. No push.

The three-term half width, with `a = di * s_M`, `b = dj * s_theta`, `e = db * s_B` and start phases `phi_M`, `phi_theta`, `phi_B`:

```
H^2 = a^2 + b^2 + e^2 + 2ab cos(phi_M - phi_theta) + 2ae cos(phi_M - phi_B) + 2be cos(phi_theta - phi_B)
```

Starter margins as rough checks, to be confirmed by the vectors: Focus about 118 Hz (theta 444 Hz against the gamma line near 326 Hz); Sleep about 345 Hz (theta 448 Hz against binaural 103 Hz).

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: every ctest passes.
- `uv run pytest` -- expected: all pass, apart from probe hash entries that are waiting on a full run.
- `uv run --no-project python tools/check_engine_source.py`, `tools/check_wording.py`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main`; `tools/signal_spec_vectors.py --check` -- expected: exit 0.
