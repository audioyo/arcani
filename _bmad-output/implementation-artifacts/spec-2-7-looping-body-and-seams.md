---
title: 'Story 2.7: Looping body and seams'
type: 'feature'
created: '2026-11-14'
baseline_commit: '38e99957fd3a76dba1eea948bcf72456572ceaee'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Focus and Learn are looping sessions (FR-7, FR-16, FR-29), but a recipe cannot say it loops, has no opening section or body, and has no max run time. Rows `max-run-time-focus` (45 min) and `max-run-time-learn` (20 min) are pending on this story.

**Approach:** A looping recipe carries a `loop` object. The signal spec's new Â§Loop defines the opening, the body, the seams, and the end. Looping repeats the parameter schedule while every oscillator phase keeps running on the one engine clock (readiness review R5), so theta, gamma, and rate-cycle phase cannot jump at a seam. A body with a rate cycle must hold a whole number of cycle periods, so each pass carries the same schedule.

Decisions (2026-11-14, build agent, under Audio's standing "settle tech forks yourselves" preference):
- **No opening glide (Audio, 2026-11-14, option A):** the epics AC's "theta rate curve that settles to the body's rate" is dropped. In this story the opening is a time span that sounds like the body; Story 4.4 gives it the ramp-in. No new rate shape.
- **Mode names the cap (Audio, 2026-11-14, option A):** `loop.mode` is `focus` or `learn` and selects row `max-run-time-focus` or `max-run-time-learn`.
- **Hard stop at the cap (Audio, 2026-11-14, option A):** output ends at the cap with no fade. The click tool keeps its last-50 ms exclusion. A `deferred-work.md` entry records that Story 4.4 must add an end fade at the cap for Focus and Learn.
- **Recipe fields:** optional top-level `loop` {`mode`, `opening_s`, `body_s`, `max_run_time_min`}, all required inside it. A recipe without `loop` is bit for bit what it is today, with the same hashes.
- **Compile rules** (named, first failure wins): `max_run_time_min` against its mode's row; `length_s` equals `max_run_time_min * 60` (the session ends at the cap; a listener timer comes in Phase 3); `opening_s >= 0`; `body_s > 0`; `opening_s` and `body_s` whole numbers of samples at 44.1 and 48 kHz (seconds-to-samples rule exact); with any rate cycle, `body_s` a whole multiple of every cycle's `period_s`; `opening_s + body_s <= length_s`.
- **Frames:** opening end `O = seconds_to_samples(opening_s)`, body `B = seconds_to_samples(body_s)`, seams at `O + k * B` below the session end. The engine renders silence past the end, as today. Seek is unchanged: a pure function of the frame.
- **Report:** the CLI report gains `loop` {`opening_end_frame`, `seam_frames`, `end_frame`} for the Story 6.2 seam list.
- **Fixtures (both rates):** `loop-swell-theta-cycle` (mode `learn`; theta 450 Hz sine, 75 percent, 4 +- 2 Hz cycle at 60 s; gamma 250 Hz, 40 Hz, smooth swell 0 degrees, 100 percent; opening 60 s, body 120 s; 20 min cap, 9 seams) rendered in full; `loop-bursts-theta-cycle` (same, bursts) checked in seam windows only. Compile-rejected and schema-invalid fixtures for every rule above.
- **CI cost:** only the swell fixture renders in full (about 7.5 s of engine time per rate on the dev PC). Click tool on the full render; phase, coupling timing, and reference match in 8 s windows around the opening join, every seam, and the end, rendered by seek in engine and reference. A full-render window equals its seek window byte for byte. Estimate: under 2 min added per CI job, no budget change.

## Boundaries & Constraints

**Always:** Â§Loop lands with vectors from `tools/signal_spec_vectors.py` before engine or reference code. Tests first from a fresh-context QA agent, committed failing. Must-fail renders are doctored in the harness (a phase step and a 1-sample gap at a seam), never in `engine/`. Rows and thresholds from the tables only; both `max-run-time-*` rows lose `pending`. Every existing vector, fixture byte, and pinned hash keeps passing. Design log entry (uu).

**Never:** Sample repetition (replaying stored samples); a second clock; rate curves on carriers; coupling to the binaural layer; gain ramps or fades (Story 4.4); the loudness window (4.1); starter recipes; pushing or opening the PR without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Full loop | swell fixture, both rates | no click at the join or any seam; no theta, gamma, or cycle phase jump; coupling within 2 ms; windows match reference within -100 dBFS | N/A |
| Seek | seek to a frame in pass 5 | byte-identical to the continuous render | N/A |
| No cap | `loop` without `max_run_time_min` | rejected (schema `required`) | no plan |
| Cap off row | mode `focus`, `max_run_time_min` 46; mode `learn`, 45 | rejected, the mode's row named | no plan |
| Body off cycle | `body_s` 90 with a 60 s cycle | rejected, rule names the period | no plan |
| No loop | every existing fixture | bytes and hashes unchanged | N/A |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md` -- new Â§Loop after Â§Rate curve (2158-2290); header story list (line 5). Vectors in `tools/signal_spec_vectors.py` (seam frames per fixture at both rates, compile cases), `tests/data/signal_spec_vectors.json`, `tests/cpp/SpecTables.cmake`; `tests/python/test_signal_spec_core.py:294` pins the table count.
- `recipes/recipe.schema.json` -- top-level `loop`, tags loudness-relevant. `engine/src/recipe/field_table.cpp`, `recipe.{hpp,cpp}` -- `std::optional<Loop>`.
- `engine/src/validate/validate.{hpp,cpp}` -- loop rules after the binaural checks; order text in `validate.hpp`. Rows from `tests/tables/ranges.tsv:19-20`.
- `engine/src/plan/plan.{hpp,cpp}` -- `frame_count` already ends output (`renderer.cpp:51`); add opening, body, and seam frames. Renderer and seek need no change.
- `cli/main.cpp`, `cli/report.*` -- `loop` block in the report.
- `reference/stub_chain.py` (`render(recipe_path, fs, frames=None)`) -- accepts `loop`; renders frame arrays for windows.
- `tests/assertions/clicks.py`, `frequency.py`, `coupling_timing.py`, `reference_match.py` -- reused unchanged; seam windows use the rate-curve modes from 2.6.
- Tests: `tests/cpp/test_validate.cpp`, `test_recipe.cpp`, `test_seek.cpp`, new `test_loop.cpp`; new `tests/python/test_loop_render.py`, `test_probe_loop.py`; update `test_recipe_schema.py`, `test_recipe_fixtures.py`, `test_hash_compare.py`.
- `tests/hashprobe/main.cpp` -- `probe_loop()` (5 s from frame 0, 5 s around the 9th seam via seek), components `loop-44100`, `loop-48000`; `ci/hash_expected.json` after the full run.
- Records: `recipes/fixtures/` and `invalid-expected.json`; `tests/data/recipe_hash_vectors.json`; `ranges.tsv` pending column; `docs/design-log.md` (uu); `recipes/README.md`.

## Tasks & Acceptance

**Execution:**
- [ ] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, vectors JSON -- Â§Loop with worked seam frames -- the spec merges first.
- [ ] tests (files above) -- a fresh-context QA agent writes the failing tests from the I/O matrix -- tests first.
- [ ] schema, field table, recipe, validator, plan, CLI report, reference, hash probe -- implementation.
- [ ] fixtures, hash vectors, rows, design log (uu), README, `ci/hash_expected.json`, `deferred-work.md` (end fade at the cap, for 4.4) -- records.
- [ ] `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given Â§Loop, then it defines body length, seam frames, and the end at the cap, with vectors, and no new oscillator formula.
- Given a looping recipe without a cap, or with a cap off its row, then compile rejects it with a named rule.
- Given the full swell render at both rates, then the click tool passes, the recovered theta and gamma envelope phase shows no step at any seam, coupling timing is within row `coupling-timing` across seams, and the join from opening to body is click-free.
- Given seek into a later pass, then samples equal the continuous render byte for byte.
- Given seam windows, then taps and output match the reference within `reference-match`.
- Given the hash probe, then `loop-*` components agree on all four platforms.

## Design Notes

Why schedule repetition and not sample repetition: replaying samples needs the body to hold a whole number of every carrier and envelope period at once, which almost no recipe meets. With every phase on the engine clock, a seam is only a frame number; the cycle rule keeps each pass's schedule identical. Story 4.4 ramps live in the opening, so the body stays steady.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: every ctest passes.
- `uv run pytest` -- expected: all pass (probe hash-entry tests pass after the full run).
- `uv run --no-project python tools/check_engine_source.py`, `tools/check_wording.py`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main`; `tools/signal_spec_vectors.py --check` -- expected: exit 0.

## Implementation Notes

Contracts the tests are written against (build agent, 2026-11-14). The signal spec's Loop section and `tests/data/signal_spec_vectors.json` (`loop_constants`, `loop_whole_samples`, `loop_compile_cases`, `loop_frames`; C++ `kLoop_*`, `kLoopWholeSamples`, `kLoopCompileCases`, `kLoopFrames`) are the values.

- **Fixtures.** `recipes/fixtures/valid/`: the 15 fixtures of `LOOP_FIXTURES` in `tools/signal_spec_vectors.py`, values exactly as there (seed 42, schema 1.0, engine 0.0.1, author `Arcani test fixtures`, loudness -36). Three compile (`loop-swell-theta-cycle.json`, `loop-bursts-theta-cycle.json`, `loop-focus-no-cycle.json`); the other twelve are compile-rejected, one per rule. `recipes/fixtures/invalid/`: `loop-missing-max-run-time.json` (`/loop/max_run_time_min`, `required`), `loop-missing-mode.json` (`/loop/mode`, `required`), `loop-mode-not-in-enum.json` (`/loop/mode` `sleep`, `enum`), `loop-opening-as-string.json` (`/loop/opening_s`, `type`), `loop-unknown-property.json` (`/loop/fade_s`, `unknown_property`), each the swell loop fixture with one change.
- **Schema and field table.** Top-level `loop` after `binaural`: object, `additionalProperties: false`, all four members required, every tag `loudness-relevant`; `mode` string enum `focus, learn`; `opening_s`, `body_s`, `max_run_time_min` numbers. Field table rows in that order, no `range_row` (the mode picks the row).
- **Recipe.** `enum class LoopMode { Focus, Learn }`, `kLoopModeEnum = "focus, learn"`, `struct Loop { LoopMode mode; double opening_s; double body_s; double max_run_time_min; }`, `Recipe::loop` (`std::optional<Loop>`).
- **Validator.** `range_rows()` gains `max-run-time-focus` and `max-run-time-learn` (unit `min`). `check_loop(const recipe::Recipe&)` holds the seven rules (nothing without `loop`); `check_ranges()` calls it after its field walk, so the loop rules follow every range check and precede `check_rules()`. Rule texts `kLoopLengthRule`, `kLoopWholeSamplesRule`, `kLoopWholeSamplesLimit`, `kLoopWholeCyclesRule`, `kLoopExceedsRule` equal `loop_constants`.
- **Plan and C API.** `plan::LoopFrames { bool present; std::uint64_t opening_end_frame, body_frames, seam_count; }` as `Plan::loop`. Public C API: `typedef struct arc_loop_frames { int looping; uint64_t opening_end_frame; uint64_t body_frames; uint64_t seam_count; uint64_t end_frame; } arc_loop_frames;` and `arc_status arc_plan_loop(const arc_plan* plan, arc_loop_frames* out_loop, arc_error* error)`: `ARC_ERR_INVALID_ARGUMENT` for a NULL plan or `out_loop`; without `loop`, `ARC_OK` with every field 0. Seam `k` (1 to `seam_count`) is `opening_end_frame + k * body_frames`.
- **Report.** `cli::Report::loop` (`std::optional<cli::LoopReport>` with `opening_end_frame`, `seam_frames`, `end_frame`), and `cli::loop_report(const arc_loop_frames&)` returning it (empty when `looping` is 0). `report_json` writes it right after `"frames"` only when present: `  "loop": {` newline `    "opening_end_frame": O,` newline `    "seam_frames": [s1, s2, ...],` (", " between, `[]` when none) newline `    "end_frame": N` newline `  },`. Without it the report bytes are unchanged.
- **Reference.** `theta.render`, `gamma.render`, `binaural.render`, and `rate_curve.offset_cycles` / `offset_units` take `frames` as an int (frames 0 to frames - 1, unchanged) or a 1-D integer ndarray of frame indices (output in that order). `stub_chain.render(recipe_path, fs, frames=None, start=0)`: the window `[start, start + T)`, `T = frames` when given, else `max(N - start, 0)`; frames at or past `N` are `+0.0`; `start < 0` raises ValueError. `stub_chain.loop_frames(recipe, fs)`: `None` without `loop`, else a dict with `opening_end_frame`, `body_frames`, `seam_frames` (list), `end_frame`, by the spec's rules from the recipe dict.
- **Tap dump.** `arcani-tapdump RECIPE RATE OUT_DIR --window START FRAMES`: compiles in measure mode, seeks to START, renders FRAMES frames in one call with every tap, writes the same six files; prints `arcani-tapdump: frames N start S total T`. `arcani-tapdump RECIPE RATE OUT_DIR --output-only`: renders the whole session in calls of 65536 frames without taps and streams `out.f64` only; prints `arcani-tapdump: frames N total N`. The old forms are unchanged.
- **Hash probe.** `probe_loop(fs)` embeds the values of `loop-swell-theta-cycle.json` (`kLoopSwellRecipe[]`): 5 s from frame 0, then `arc_seek` to `seam 9 - seconds_to_samples(2.5, fs)` and 5 s; components `loop-44100` and `loop-48000`, scope `engine`, `2 * 2 * 5 * fs` samples each. Their `ci/hash_expected.json` entries arrive after a green four-platform full run (design log (kk)); until then that one test fails.
- **Seam windows (Python).** Window length `loop_constants.window_s` (8 s). Join and seam windows: center `O` or seam `k`; the end window: center `N - 4 s`. Each window starts at the frame nearest the last time at or before `center - 4 s` where the ideal theta phase `frequency.curve_phase(t, rate_hz, cycle)` is an integer (a theta 0 degree point), so the coupling timing tool, given the recipe's cycle with `start_phase_deg` moved to the window start (`start_phase_deg + 360 * (start / fs) / period_s`, mod 360), predicts each 0 degree point within a frame. Engine windows come from `--window`, reference windows from `stub_chain.render(..., start=, frames=)`.
- **Checks.** Swell, both rates: the `--output-only` render's slice of each window equals the `--window` output byte for byte; the click tool on the whole render in overlapping chunks per channel (every sample outside the session's first and last `clicks.EXCLUDE_S` lies in some chunk's checked part); per window, theta, gamma, bus, and output match the reference (`reference_match.match_stereo`); coupling timing within row `coupling-timing` (`coupling_timing.check`, rate-curve mode); recovered theta envelope phase: `coupling_timing.zero_degree_times` against the scheduled 0 degree times, every error under row `coupling-timing-calibration`, with points on both sides of the join or seam; recovered gamma envelope phase: the gamma tap's `coupling_timing.envelope`, band-limited to the gamma band widened by the top of row `theta-rate`, made analytic, demodulated by the scheduled gamma envelope phase, with the mean phase of each side (0.5 s trimmed at the window ends) and their difference, as time at the gamma rate, under row `coupling-timing-calibration`. Bursts, both rates: reference match and coupling timing (`coupling="bursts"`) in every window. Must-fail, doctored in the harness: a 1-sample gap at a seam (drop the seam frame) fails the click tool; a phase step at a seam (from the seam on, the window continues with the engine render from `seam + round(0.001 * fs)`) fails the reference match, the click tool, and the theta and gamma phase checks.
- **Failing tests (red state).** The fresh-context QA agent wrote the tests in its worktree from these contracts and stopped at a usage limit before committing; the build agent added only the loop leaves to `tests/python/test_recipe_hash.py` (the one file it had not reached) and committed them as one tests-only commit. Red on the baseline 0b4cdd8: the C++ tests do not compile (no `arc_plan_loop`, `recipe::Loop`, `validate::check_loop`, `cli::LoopReport`); the Story 2.7 Python cases in `test_recipe_schema.py`, `test_recipe_fixtures.py`, `test_recipe_hash.py`, `test_hash_compare.py`, `test_probe_loop.py`, and `test_loop_render.py` (builds excluded) give 41 failed and 48 errors (missing fixtures, schema `loop`, reference window API, tap dump modes, probe components), 346 passed.
- **Test correction after the red commit.** `test_loop_accepts_both_modes_and_rejects_by_schema_keyword` expected only `type` for a numeric `mode`; jsonschema also reports `enum` for it (as for every enum field), so the test now requires `type` and `enum` for `mode` and `type` alone for the numbers. No threshold or rule changed.
- **Cost.** One full swell render per rate (no taps, about 0.9 GB of `out.f64` at 48 kHz, written to the pytest temp folder and memory-mapped), 11 windows per fixture and rate. The other loop fixtures are compile-only. C++: seek into pass 5 against a continuous render, and the looping recipe against the same recipe without `loop`, in windows only.

## Spec Change Log

## Review Triage Log
