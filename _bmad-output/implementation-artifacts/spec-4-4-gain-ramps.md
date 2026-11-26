---
title: 'Story 4.4: Gain ramps'
type: 'feature'
created: '2026-11-26'
status: 'ready-for-dev'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Every layer plays at unit level from the first sample to the last. No recipe can ramp a layer in, fade the session out, or stop a looping session without a hard cut at the cap. The loudness window cannot exclude ramps because none exist, and the coupled-gamma zero-theta rejection (AD-5) has no level to test.

**Approach:** Add optional gain schedules to each layer (theta reference, gamma PAC, binaural) and to the master. Each schedule is an initial gain plus non-overlapping ramps. Every ramp follows one law from a new `## Gain ramps` section of `docs/signal-spec.md`, is evaluated per sample, is aligned by the seconds-to-samples rule, and holds its end value exactly after its last sample. Add a tap before and a tap after each layer's gain. Narrow the loudness window to the steady part. Add a ramp tool calibrated on Python signals, and match the Python reference.

Decisions (planning, 2026-11-26; Audio can overrule any of them at approval):

1. **Recipe shape.** Each layer object and a new top-level `master` gets an optional `gain`: `{ "initial": g0, "ramps": [ { "start_s", "duration_s", "to" } ] }`. Gains are linear, 0 (silence) to 1 (full): a new `ranges.tsv` row `layer-gain`, so a ramp never boosts, as `loudness-gain` only turns down. Ramps are sorted and must not overlap (rule `gain.overlap`). Each ramp lies inside the session (rule `gain.outside_session`). Each schedule has at most 8 ramps (row `gain-ramp-count`), so the plan stays a fixed size. An absent `gain` means unity throughout, so every existing fixture keeps its recipe hash, loudness hash, and probe pins. The new fields are audio- and loudness-relevant.
2. **Minimum duration.** `duration_s < 0.010` is rejected (rule `gain.ramp_min`, limit `>= 10 ms (row gain-ramp-min)`). Exactly 10 ms passes. Modulation envelopes, burst edges, and the limiter are exempt.
3. **Looping recipes.** Each ramp ends at or before the opening end O, or starts at or after O + B (rule `gain.loop_body`). That keeps the first body pass, which the loudness window repeats, ramp-free. An end fade is a master ramp that ends at the cap.
4. **Loudness window.** A looping recipe keeps [O, O + kB). For a non-looping recipe, the window is the longest stretch with no layer or master ramp active, ties to the earliest. The `loudness-window-min` rule still applies. The CLI `--loudness` and `--store-gain` paths share it.
5. **Taps.** The existing `theta_reference` and `gamma_pac` taps become the before-gain taps, so every coupling, frequency, and phase test reads them unchanged. New after-gain taps for theta, gamma, and binaural, plus a before-gain binaural tap, are added to `arc_taps`. The stereo bus sums the after-gain layers. Master = join x loudness gain x master ramp gain. The limiter stays an identity stub (4.5).
6. **Coupled gamma at zero theta (deferred from 2.3).** Reject coupled gamma (rule `coupling.theta_silent`) at any sample where the gamma gain and depth are non-zero while the theta gain is exactly zero. The check is in closed form over the schedules, and master gain does not count. Must-fail fixture: a theta fade to silence that ends before a coupled gamma fade.
7. **Exact zeros.** At and after a ramp's end sample the gain is its `to` value exactly. A fade to silence therefore multiplies by 0, and the 24-bit output is exact zeros from then on.
8. **Ramp law** (Audio, 2026-11-26). Every layer and master ramp uses a raised cosine in linear gain: for samples [n0, n1) from a to b, `g[n] = a + (b - a) * (1 - cos(pi (n - n0) / (n1 - n0))) / 2`, with the engine cosine. This is the shape of the burst and theta edges, and it is flat at both ends. It is an engineering default and is logged as one.
9. **End fade at the cap** (Audio, 2026-11-26). Focus and Learn fade to silence over the last 5 min before their max run time. That is the Epic 6 starter value, logged in the design log, and the 4.4 looping end-fade fixture uses it. It mirrors the 5 min ramp-in and Sleep's 5 min fade. It is an engineering default.
10. **Spec size** (Audio, 2026-11-26): kept whole, deferred items included.
11. **Out of scope, left deferred:** the denormal-guard fixture, the short-session spacing note, and the 4.3 store refusal hook.

## Boundaries & Constraints

**Always:** Formulas are written first in `docs/signal-spec.md` with worked vectors, merged before engine or reference code. Engine-owned transcendentals only. `-ffp-contract=off`. The engine reads no files. Every new row gets a design-log line, and `gain-ramp-min` is cleared from pending. Every check has a passing fixture and a must-fail fixture doctored in the harness. Tests go first as a tests-only commit by a fresh-context QA agent. The binaural gain is one per-layer scalar applied equally to both ears, with no width or spatial stage. Keep added CI time near 3 min of CPU per platform.

**Never:** No limiter behavior (4.5), no starter recipes (Epic 6), no per-ear or pan gain, no gain above 1, no change to the bytes of renders without `gain`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ramp exactly 10 ms | `duration_s` 0.010 | compiles | N/A |
| Ramp 9.9 ms | `duration_s` 0.0099 | rejected, `gain.ramp_min` | parameter, value, rule, limit |
| Overlap / outside / count / gain > 1 | doctored fixtures | rejected by the named rule | parameter, value, rule, limit |
| Looping ramp inside first body | ramp crosses (O, O + B) | rejected, `gain.loop_body` | as above |
| Theta silent under coupled gamma | theta fade ends before gamma fade | rejected, `coupling.theta_silent` | as above |
| Fade to silence | 5 min master fade | exact zeros from its end sample | N/A |
| Unity schedule | `gain` with initial 1, no ramps | before- and after-gain taps bit-identical; output equals the no-`gain` render | N/A |
| Loudness, non-looping | 10 min layer ramp from silence, then steady | window = steady stretch, within 1 LU; whole render never above target + 1 LU | N/A |
| Loudness, looping, superseded window | gain measured over ramp-in plus one body (harness) | body plays above target, loudness fails | N/A |
| Window starts at O | looping fixture whose ramp-in makes the opening differ from the body | reading over [O, O + B) differs from [0, B) | N/A |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md`: new `## Gain ramps` before `## Loudness` (4548). Edit `Coupling` :1251 (zero-level rule), `Loop, End at the cap` :2810, `Loudness, Window` :4661-4671, and `Core, Seconds-to-samples rule` :44 (reuse, do not change).
- `recipes/recipe.schema.json`: `gain` on `theta_reference` :74, `gamma_pac` :128, `binaural` :193, and new top-level `master`. Every object keeps `additionalProperties: false`. `recipes/README.md` :41 and :126 text.
- `engine/src/recipe/recipe.{hpp,cpp}` (parse near :433) and `engine/src/validate/field_table.cpp` :25 (row mapping).
- `engine/src/validate/validate.cpp`: `kRows` :31-82 (new rows), `check_row` :200 (error shape), `check_loop` :276 (`gain.loop_body`), `check_rules` :406 (overlap, outside, ramp_min, `coupling.theta_silent`).
- `engine/src/plan/plan.{hpp,cpp}`: a fixed-size `GainSchedule` per layer plus master, with ramp sample bounds from `core::seconds_to_samples` (`engine/src/core/phase.cpp:42`). `master_gain` :171 stays the loudness gain.
- `engine/src/render/renderer.{hpp,cpp}` :50-136: apply the layer gains after each layer sample, before the bus (:110) and join (:112), and the master ramp at :113. `Taps` struct (`renderer.hpp:28`).
- `engine/include/arcani/arcani.h` :84-93 `arc_taps`, `engine/src/api/api.cpp` :343-358, `tests/tapdump/main.cpp` :201-218: the new taps.
- `reference/stub_chain.py` :114-169 (`KEYS` :66) and `reference/ideal.py:49`: the same law in binary64 with ideal cos.
- `cli/loudness.{hpp,cpp}` :81-101, 161-203 `loudness_window`: non-looping steady stretch. Callers `cli/main.cpp` :375-413 (store) and :579-594 (`--loudness`).
- `tests/assertions/clicks.py` (`check` :74; the docstring at :8 names 4.4) and `tests/python/test_loop_render.py` :204-215 (window builder pattern): click windows around every ramp edge.
- New `tests/assertions/gain_ramps.py`: the ramp tool, which estimates gain as after-gain tap over before-gain tap (master: output over join x loudness gain) and the shortest completed change.
- `tests/tables/thresholds.tsv:31` `gain-ramp-min` (pending 4-4). `ranges.tsv`: new `layer-gain`, `gain-ramp-count`.
- `ci/hash_expected.json`: new probe components for the ramp fixtures at 44.1 and 48 kHz. Existing pins must not move.

## Tasks & Acceptance

**Execution:**
- [ ] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, `tests/tables/*.tsv`, `docs/design-log.md`: Gain ramps section, vectors, rows, and log entries. Merged before code.
- [ ] Failing tests (QA agent, tests-only commit): `tests/cpp/test_gain_ramps.cpp`, `tests/python/test_gain_ramp_tool.py`, `test_gain_ramps_reference.py`, `test_gain_ramps_loudness.py`, invalid fixtures plus `invalid-expected.json`, and taps in `test_api.cpp`/`test_stages.cpp`.
- [ ] Schema, parser, validator, plan, renderer, API taps, tapdump, Python reference, CLI window.
- [ ] Fixtures `recipes/fixtures/valid/gain-*.json`: 5 min ramp-in (looping, opening differs from body), 10 min layer ramp from silence (non-looping), 5 min master fade to silence, and a looping end fade at the cap. Probe pins.

**Acceptance Criteria:**
- Given every ramp fixture at 44.1 and 48 kHz, when the ramp tool and click tool check every layer tap and the master output, then no gain change completes in under 10 ms, no ramp edge exceeds -60 dBFS after the 8 kHz high-pass, and a harness-doctored 5 ms layer fade fails.
- Given ramp renders, when compared with the Python reference, then taps and output differ by less than -100 dBFS.
- Given the full suite on the dev PC and in CI, when it runs, then everything passes, existing pins are unchanged, and `tools/check_row_coverage.py` sees every new row in use.

## Design Notes

**Phased handoff,** as in 4.1 to 4.3, on branch `story/4-4-gain-ramps`. The implementation agent writes the spec section, vectors, rows, and log, then commits. A fresh-context QA agent commits the failing tests. The implementation agent then implements without editing a test expectation. No push until review.

**Ramp law** (decision 8): `g[n] = b` exactly for n >= n1, and `g[n] = a` for n < n0. Because the curve is flat at both ends, a 10 ms ramp of a full-scale tone stays far below the click level. The spec section must give the cosine argument's exact binary64 evaluation order, so the engine and reference agree below -100 dBFS.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl`: expected build passes and ctest is green.
- `uv run --locked pytest -n auto`: expected all pass.
- `git status --porcelain -- recipes` after the suite: expected only committed fixture edits.
