---
title: 'Story 2.6: Rate curves on theta and gamma rates'
type: 'feature'
created: '2026-11-13'
baseline_commit: '512e251a120a301d63935da266a4ded19f8128ba'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The theta rate and the gamma rate are fixed numbers. Rule 2 says every rate is variable. Story 2.5 wrote one rate-curve law for the binaural beat, and Epic 5's 8-hour fixture and Story 2.7's opening section need a theta curve.

**Approach:** Apply the §rate-curve law, closed-form integral, cycle cosine, and cycles-to-units rule unchanged to the theta envelope phase and the gamma envelope phase through an optional `rate_cycle` on each layer. Add worst-case range and carrier-rule checks, an envelope phase mode in the frequency tool, and a rate-curve mode in the coupling timing tool, each calibrated on Python-synthesized signals first.

Decisions (2026-11-13, build agent, under Audio's standing "settle tech forks yourselves" preference):
- **Recipe fields:** new optional `theta_reference.rate_cycle` and `gamma_pac.rate_cycle` {`swing_hz`, `period_s`, `start_phase_deg`}, all three required inside, the same shape as `binaural.beat_rate_cycle`. `rate_hz` stays required and is the center `r`. The rows `rate-cycle-period` and `rate-cycle-start-phase` apply as they do for the binaural cycle. Existing fixtures, recipe hashes, and pinned hashes stay unchanged.
- **Engine phase:** theta envelope phase `phase_E[n] = n * inc_E + U_E[n] mod 2^64`, gamma envelope phase `phase_M[n] = n * inc_M + U_M[n] mod 2^64`, each `U` from §rate-curve with that layer's own `P0`, `inc_P`, `K`, and `c0`. The carriers `phase_T` and `phase_G` do not change. The swell and the burst gate read the curved `phase_E`, so coupling follows the curve with no new rule. Sample 0 stays the 0 degree point (`U[0] = 0`). Without a cycle, a layer is bit for bit what it is today.
- **Worst-case checks** (after each layer's range checks, first failure wins, parameter `/<layer>/rate_cycle/swing_hz`): `swing_hz >= 0`, `r - s` and `r + s` against `theta-rate` or `gamma-rate`. The carrier rule judges the carrier against `r + s` through the existing interval form of `check_carrier_rule`.
- **Reference:** theta and gamma pick envelope segments by integer comparisons, so the reference builds an integer phase from the ideal cosine `U`, converted by the cycles-to-units rule. Shared helpers move from `reference/binaural.py` to a new `reference/rate_curve.py`. §rate-curve states the error bound per tap. Every bound must fall under row `reference-match`.
- **Frequency tool, envelope phase mode:** `phase_track` on the mean-removed analytic envelope of a sine-shape theta tap or an uncoupled gamma tap. Calibrated on Python-synthesized swept AM tones with a known schedule, plus a must-fail tone that is 0.02 Hz off.
- **Coupling timing tool, rate-curve mode:** takes an optional cycle (`swing_hz`, `period_s`, `start_phase_deg`). Zero-degree points are predicted where the ideal `Phi(t)` reaches an integer. Expected peaks are where `Phi` reaches `k + C/360`. The fit window and template use the local rate. Calibrated on synthesized curved swell and burst signals with known peak times, plus a 3 ms must-fail.
- **Fixtures (120 s, both rates):** `theta-cycle-sine` (450 Hz, 3.5 +- 2.5 Hz, 75 percent, start 0), `theta-cycle-smoothed-on-off` (same rates), `gamma-cycle-uncoupled` (250 Hz, 45 +- 15 Hz, 100 percent), `swell-theta-cycle` and `bursts-theta-cycle` (theta 450 Hz, 4 +- 2 Hz; gamma 250 Hz, 40 Hz, 0 degrees, 100 percent), `gamma-cycle-swell-theta-cycle` (both curved). Compile-rejected: `theta-cycle-below-1`, `theta-cycle-above-6`, `gamma-cycle-below-30`, `gamma-cycle-above-60`, `gamma-cycle-carrier-rule` (200 Hz, 45 +- 10 Hz: the center passes, the maximum 55 Hz breaks the rule). Invalid: `theta-cycle-missing-start-phase`. Hash probe components `rate-curves-44100` and `rate-curves-48000` render `gamma-cycle-swell-theta-cycle` with bursts: 5 s from frame 0, plus 5 s after a seek to 55 s.
- **Code move:** `cycles_to_units`, `cycle_cosine`, and `rate_cycle_offset` move from `core/envelope.*` to a new `core/rate_cycle.*`, unchanged (Story 2.5 review row 9). The `BeatRateCycle` struct becomes `RateCycle`.
- **Burst and edge lengths under a theta curve (Audio, 2026-11-14, option A):** `W`, `Hb`, and `Wb` stay fixed shares of the theta cycle, set once per plan at the center `rate_hz`, as today. Bursts are 50 ms and edges 10 ms at the center rate. They are shorter when theta is faster and longer when it is slower (2 to 6 Hz around 4 Hz: bursts about 33 to 100 ms, edges about 6.7 to 20 ms). §Theta reference and §Bursts say so. No new formula.
- **Cycle period (Audio, 2026-11-14, option A):** theta and gamma cycles use row `rate-cycle-period`, locked to exactly 60 s, until a study supports others. Row `rate-cycle-start-phase` applies unchanged.
- **Rows and log:** design log entry (ss). No threshold changes.

## Boundaries & Constraints

**Always:** §rate-curve and the theta, gamma, coupling, and bursts sections are updated with vectors from `tools/signal_spec_vectors.py`, and that spec commit lands before engine or reference code. Tests come first, from a fresh-context QA agent, committed failing. Each new tool mode passes calibration before it judges a render. Must-fail renders are made in the harness, never in `engine/`. Thresholds and ranges come from the tables only. Every existing vector, fixture byte, and pinned hash keeps passing.

**Never:**
- New rate-law shapes (piecewise-linear curves, ramps) or a second integral. If Story 2.7 needs a settling curve, raise it there.
- Rate curves on carriers.
- Loops (2.7), spacing checks (Epic 3), the 8-hour drift check (5.1), starter recipes.
- Coupling to the binaural layer.
- libm or fault injection in `engine/`.
- Pushing or opening the PR without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Theta curve | `theta-cycle-sine`, 44.1 and 48 kHz | envelope rate within `frequency-accuracy` of the schedule, no phase step; taps within `reference-match` | N/A |
| Gamma curve | `gamma-cycle-uncoupled` | same, on the gamma envelope | N/A |
| Coupled over theta curve | swell and bursts fixtures | every peak or burst center within `coupling-timing` | N/A |
| Worst case | theta `r - s` 0.99 or `r + s` 6.01; gamma 29.99 or 60.01 | rejected, row named, parameter `.../rate_cycle/swing_hz` | no plan |
| Carrier rule | gamma 200 Hz, 45 +- 10 Hz | rejected `carrier-rule` on `/gamma_pac/carrier_hz`, with value and limit naming 55 Hz | no plan |
| Seek | probe recipe, seek to 55 s | byte-identical to the continuous render | N/A |
| No cycle | every existing fixture | bytes and hashes unchanged | N/A |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md` -- update the header story list (line 5). §Rate curve (2152-2362): add Recipe fields for theta and gamma, the worst-case checks, theta and gamma under Engine, and the reference integer phase; per-tap error bounds; change the line "only the beat rate cycle uses the cycle cosine" (2236). Oscillators in §Theta reference (429) and §Gamma PAC (890): `phase_E` and `phase_M` gain `U`. §Coupling and §Bursts: they read the curved phase, and `W`, `Hb`, and `Wb` stay at the center rate; the coupling timing text now covers a curve.
- `tools/signal_spec_vectors.py` (`rate_cycle_rows` 1804, `rate_curve_rows` 1824, `RATE_CURVE_CASES` 1786) -- add theta and gamma cycle constants and curved sample vectors; update `tests/data/signal_spec_vectors.json` and `tests/cpp/SpecTables.cmake`. `tests/python/test_signal_spec_core.py:294` pins 36 tables.
- `recipes/recipe.schema.json` -- `rate_cycle` under `theta_reference` (74-103) and `gamma_pac` (104-144), copied from the inline `beat_rate_cycle` (162-185).
- `engine/src/recipe/field_table.cpp` (theta 26-34, gamma 38-50, cycle rows 60-63), `recipe.hpp` (`ThetaReference` 41, `GammaPac` 60, `BeatRateCycle` 79 renamed `RateCycle`), `recipe.cpp` (393-418).
- `engine/src/validate/validate.cpp` -- generalize `check_cycle_worst_case` (179-198) to take a layer's path, rate row, and center. Call it from `check_ranges` (204-250) after each layer's fields. In `check_rules`, the theta carrier rule (256) and gamma carrier rule (268) pass `r - s, r + s`. Update the order text in `validate.hpp` (1-17, 62-88).
- `engine/src/plan/plan.{hpp,cpp}` -- `ThetaOscillator` (hpp 71) and `GammaOscillator` (hpp 93) gain cycle constants like `BinauralEars` (112-120, cpp 154-160). `edge_units` (cpp 103-111) and the burst units (cpp 136-138) stay at the center `rate_hz`.
- `engine/src/render/renderer.cpp` -- the constructor (29) and `seek` (32-42) seed the cycle phases; the theta envelope (55), gamma envelope (65), and burst and swell (68, 72) read accumulator plus `rate_cycle_offset`; advance at 108-114.
- New `engine/src/core/rate_cycle.{hpp,cpp}`, moved from `core/envelope.{hpp,cpp}` (`kInvTwoPi` hpp:51, `cycles_to_units` :56, `cycle_cosine` :64, `rate_cycle_offset` :70); update the includes and `engine/CMakeLists.txt`. `tools/check_engine_source.py` must still pass.
- New `reference/rate_curve.py` (from `binaural.py` 49-80: `_start_units`, `cycle_constants`, `_cosine`, offset in cycles, plus an integer-units helper). `binaural.py` imports it with identical output. `theta.py` render (108-125) and `gamma.py` render (149-175, which re-derives `phase_e` at 164-166) apply it. `tests/python/test_reference_independent.py` must pass.
- `tests/assertions/frequency.py` -- envelope phase mode beside `phase_track` (160). `tests/assertions/coupling_timing.py` -- rate-curve mode in `zero_degree_times` (215), `timing_errors` (310), and `check` (351); the constant-rate path is unchanged.
- Tests: `tests/cpp/test_validate.cpp`, `test_recipe.cpp`, `test_seek.cpp`, new `test_rate_curves.cpp` (add to `tests/cpp/CMakeLists.txt`). New `tests/python/test_rate_curve_reference.py` and `test_probe_rate_curves.py`. Update `test_frequency_tool.py`, `test_coupling_timing_tool.py`, `test_recipe_schema.py`, `test_hash_compare.py`, and `test_tables_loader.py` if md rows change.
- `tests/hashprobe/main.cpp` -- `probe_rate_curves()` like `probe_binaural_cycle` (473), components table 540-558. Update `ci/hash_expected.json` after the full run.
- Records: `recipes/fixtures/` plus `invalid-expected.json`; `tests/data/recipe_hash_vectors.json` (`tools/recipe_hash.py --write-vectors`); `tests/tables/ranges.tsv` and `thresholds-and-ranges.md` (spec_row text for `rate-cycle-*` now covers all three layers); `docs/design-log.md` (ss); `recipes/README.md`.

## Tasks & Acceptance

**Execution:**
- [x] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, vectors JSON -- theta and gamma under §rate-curve, plus section updates and vectors -- the spec merges first.
- [x] tests (files above) -- a fresh-context QA agent writes the failing tests, covering the I/O matrix -- tests first.
- [x] schema, field table, recipe, validator, plan, renderer, `core/rate_cycle`, `reference/rate_curve.py`, `theta.py`, `gamma.py`, the two tool modes, hash probe -- implementation.
- [ ] fixtures, hash vectors, rows text, design log (ss), README, `ci/hash_expected.json` (after the full run) -- records.
- [ ] `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given §rate-curve after this story, when the theta or gamma rate has a cycle, then the engine and the reference use the Story 2.5 law, integral, cycle cosine, and cycles-to-units rule unchanged, and no new formula enters the spec.
- Given the envelope phase mode and the coupling timing rate-curve mode, then each reads its synthesized calibration signals within its calibration row and fails its doctored one.
- Given every curved fixture at both rates, then taps and output match the reference within `reference-match`, and theta and gamma rate errors read within `frequency-accuracy` with no phase step.
- Given the hash probe, then the `rate-curves-*` components are equal on all four platforms and match their expected entries.

## Design Notes

Why `U` on the envelope phase only: the coupling reads `phase_E`, so a curved theta drags the swell and the bursts with it for free. AD-5 holds because gamma still reads only the theta envelope phase and plan constants.

Why the reference builds integer phases: the theta segments and the burst segments are chosen by exact integer comparisons. Every envelope is continuous across its segment boundaries, so engine and reference phases a few units apart give a tiny error, not a jump.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: every ctest passes.
- `uv run pytest` -- expected: all pass (the probe hash-entry tests pass only after the full run).
- `uv run --no-project python tools/check_engine_source.py`, `tools/check_wording.py`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main`; `tools/signal_spec_vectors.py --check` -- expected: exit 0.

## Implementation Notes

- 2026-11-14: Signal spec Rate curve (Recipe fields, Range checks, Engine, Reference, and Error bound for theta and gamma), Theta reference, Gamma PAC layer, Coupling, and Bursts updated, with two new vector tables (theta and gamma rate cycles; theta and gamma rate curve samples; 38 in all) and six rows added to Vectors: rate curve (header now "Phase ideal (cycles)"). The vectors file gains `rate_curve_constants` (`length_s`, `curve_add`, `probe_fixtures`), `layer_rate_cycles`, and `rate_curve_samples`; `tests/cpp/SpecTables.cmake` generates `kLayerRateCycles` and `kRateCurveSamples`. Engine against ideal on the vector samples: at most 2.4e-8 (about -152 dBFS) on any tap.
- Interpretations by the build agent (Audio's "settle tech forks yourselves"):
  - Field order: `theta_reference.rate_cycle` is the last member of `theta_reference` (after `shape`); `gamma_pac.rate_cycle` the last of `gamma_pac` (after `coupling_phase_deg`). So the worst-case checks run right after each layer's own range checks, as the frozen decision says.
  - Coupled fixture details the frozen block leaves open: the theta reference of `swell-theta-cycle`, `bursts-theta-cycle`, and `gamma-cycle-swell-theta-cycle` is the sine shape at 75 percent depth (as in the Story 2.3 and 2.4 fixtures); the gamma cycle of `gamma-cycle-swell-theta-cycle` is 45 +- 15 Hz (the `gamma-cycle-uncoupled` cycle; a 250 Hz carrier passes the carrier rule at 60 Hz); every cycle starts at 0 degrees with the 60 s period.
  - "render `gamma-cycle-swell-theta-cycle` with bursts": the probe renders `gamma-cycle-swell-theta-cycle.json` and then `bursts-theta-cycle.json`, each 5 s from frame 0 plus 5 s after a seek to 55 s.
  - Compile-rejected values: `theta-cycle-below-1` 2 +- 1.01 Hz (`r - s` = 0.99), `theta-cycle-above-6` 4 +- 2.01 Hz (6.01), `gamma-cycle-below-30` 40 +- 10.01 Hz (29.99), `gamma-cycle-above-60` 50 +- 10.01 Hz (60.01), `gamma-cycle-carrier-rule` 200 Hz, 45 +- 10 Hz; all 60 s period, start 0, 5 s, theta 450 Hz 75 percent sine, gamma 250 Hz (200 Hz for the carrier-rule fixture) 100 percent uncoupled.
- Interfaces chosen by the build agent, for the tests-first commit:
  - Engine, new `engine/src/core/rate_cycle.hpp` (namespace `arcani::core`): `kInvTwoPi`, `cycles_to_units`, `cycle_cosine`, and `rate_cycle_offset`, moved unchanged from `core/envelope.hpp` (which no longer declares them). `engine/CMakeLists.txt` builds `core/rate_cycle.cpp`.
  - `recipe::RateCycle { double swing_hz, period_s, start_phase_deg; }` replaces `recipe::BeatRateCycle`; `Binaural::beat_rate_cycle` is `std::optional<RateCycle>`; `ThetaReference` and `GammaPac` gain `std::optional<RateCycle> rate_cycle` (absent when the field is absent).
  - Field table: `/theta_reference/rate_cycle` (Object, loudness-relevant, optional) after `/theta_reference/shape`, with `swing_hz` (no row), `period_s` (row `rate-cycle-period`), `start_phase_deg` (row `rate-cycle-start-phase`), all required; `/gamma_pac/rate_cycle` likewise after `/gamma_pac/coupling_phase_deg`. Schema: the same members, copied from `binaural.beat_rate_cycle`.
  - Validator errors exactly as signal spec Rate curve, Range checks, theta and gamma (limits `>= 0 Hz`, `>= 1 Hz (row theta-rate)`, `<= 6 Hz (row theta-rate)`, `>= 30 Hz (row gamma-rate)`, `<= 60 Hz (row gamma-rate)`, and the `rate-cycle-period` and `rate-cycle-start-phase` limits). The carrier rule passes `r - s, r + s` to `check_carrier_rule`; the gamma carrier-rule fixture fails with value `200`, limit `>= 220 Hz (4 x 55 Hz, row carrier-rule)`.
  - `plan::ThetaOscillator` and `plan::GammaOscillator` each gain `bool cycle = false; std::uint64_t cycle_start = 0; std::uint64_t cycle_increment = 0; double cycle_k = 0.0; double cycle_c0 = 0.0;` with the meaning of the `BinauralEars` fields (P0, inc_P, K, c0), all zero without a `rate_cycle` (and for a muted ear nothing changes: mute touches only the binaural layer). `edge_units`, `burst_half_width_units`, and `burst_edge_units` stay at the center `rate_hz`.
  - Hash probe: `probe_rate_curves(fs)` writes `rate-curves-44100.f32` and `rate-curves-48000.f32`: `gamma-cycle-swell-theta-cycle.json` then `bursts-theta-cycle.json`, each compiled in measure mode and rendered through the C API, 5 s from frame 0 then 5 s after `arc_seek` to `seconds_to_samples(55, fs)`, interleaved stereo float32 (2 * 2 * 10 * fs samples); scope `engine`, like `binaural-cycle-*`.
  - `reference/rate_curve.py`: `start_units(deg)` (P0, a Python int), `cycle_constants(cycle, fs)` -> `(P0, inc_P, K)`, `offset_cycles(cycle, fs, frames)` (ideal U in cycles, float64 ndarray; zeros when `cycle` is None), `cycles_to_units(v)` (float64 ndarray -> uint64 ndarray by the spec rule), `offset_units(cycle, fs, frames)` (uint64 ndarray; zeros when None). `reference/binaural.py` keeps `cycle_constants` and `beat_offset_cycles` (now from `rate_curve`), output unchanged. `reference/theta.py` `render` reads `theta_reference.get("rate_cycle")`; `reference/gamma.py` `render` reads `gamma_pac.get("rate_cycle")` for the gamma envelope phase and `theta_reference.get("rate_cycle")` for the coupled theta envelope phase.
  - `tests/assertions/frequency.py`: `curve_phase(t, rate_hz, cycle=None)` is the ideal phase integral in cycles at times `t` (seconds, any array), `Phi(t) = r t + K (cos(phi0) - cos(2 pi t / P + phi0))` with `K = s P / (2 pi)`, `cycle` a mapping with `swing_hz`, `period_s`, `start_phase_deg` (`r t` when None). Envelope phase mode: `ENVELOPE_TRIM_S = 10.0`, `ENVELOPE_TAPER_S = 5.0`; `envelope_phase_track(x, fs, expected_cycles)` takes `|analytic(x)|`, removes its mean, tapers each end by a raised cosine over `ENVELOPE_TAPER_S`, forms the analytic signal with every bin below half the bottom of row `theta-rate` zeroed, removes the expected phase, trims `ENVELOPE_TRIM_S` at each end, and unwraps: the same dict as `phase_track`. `check_envelope_phase(name, x, fs, expected_cycles)` is `check_phase`'s report shape on row `frequency-accuracy` (step rule `PHASE_STEP_CYCLES`, note `phase step`; `not finite`). Prototype on Python-synthesized swept AM (120 s, both rates): theta 3.5 +- 2.5 Hz at 0 and 270 degrees and 4 +- 2 Hz at 90 degrees, gamma 45 +- 15 Hz and 40 +- 10 Hz, read at most 5e-5 Hz (row `frequency-accuracy-calibration` 0.001 Hz); 0.02 Hz off reads at least 0.028 Hz and fails.
  - `tests/assertions/coupling_timing.py`: `zero_degree_times(..., cycle=None)`, `timing_errors(..., cycle=None)`, `check(..., cycle=None)`; `cycle` is the recipe's `theta_reference.rate_cycle` mapping and `theta_rate_hz` its center. With a cycle: the theta phase is `frequency.curve_phase`; each 0 degree point is predicted where it reaches an integer and refined by the template fit of `shape_template(shape, Phi(t) - Phi(tau), theta_rate_hz)` over one local period; the expected peak is where `Phi` reaches `Phi(tau) + coupling_phase_deg / 360`; the swell fit is `c0 + c1 cos(2 pi (Phi(t) - Phi(p))) + c2 sin(...)` over one local period, its peak phase turned to time through `Phi`; the burst refinement uses `burst_template((Phi(t) - Phi(tau)) / theta_rate_hz)` (Hb and Wb are fixed shares of the cycle at the center rate) with the constant `gamma_rate_hz`. Errors are seconds; the constant-rate path is unchanged.

- Red state of the tests-only commit 0e525e9 (fresh-context QA agent in its own worktree, fast-forwarded onto ffb404f): Python subset of the reference, probe, and record files 59 failed, 125 passed (missing `reference.rate_curve`, fixtures, schema members, tool functions); C++ did not compile against the old engine (new header and plan fields), checked by a syntax pass only.
- Implementation (this commit, after 0e525e9), green on the dev PC with the QA tests unchanged: `windows-clang-cl` workflow 4/4 ctest entries; `uv run pytest` 2,706 passed, 2 skipped, 4 failed, all waiting on the `rate-curves-*` entries of `ci/hash_expected.json` from a four-platform full run (`test_hash_compare.py::test_real_expected_file_has_every_component_with_its_scope`, `test_probe_determinism.py::test_every_probe_component_has_an_expected_entry` and `::test_windows_x64_probe_matches_every_expected_entry`, `test_probe_rate_curves.py::test_expected_entries_name_the_rate_curve_components`). `check_engine_source.py`, `check_fp_pragmas.py`, `check_wording.py`, `check_table_log.py --base main`, `signal_spec_vectors.py --check` exit 0. Dev PC probe hashes (not pinned): `rate-curves-44100` 1,764,000 samples `3df589ce...`, `rate-curves-48000` 1,920,000 samples `61385061...`; every existing pinned component unchanged.
- Measured: envelope phase mode on synthesized swept AM at most 5e-5 Hz (calibration row 0.001 Hz), on reference renders 7.2e-6 Hz (theta) and 1.2e-7 Hz (gamma); coupling timing rate-curve mode on synthesized curved swells 0.0003 ms and bursts 0.015 ms (calibration row 0.2 ms), 3 ms shift reads 3.0 ms; engine against ideal vectors at most 2.4e-8 (-152 dBFS).
- Cost: configure now parses a 1.7 MB vectors file (was 1.1 MB); the `windows-clang-cl` workflow took 5 min 13 s on the dev PC (baseline 4 min 53 s). The full pytest run took 24 min 51 s on the dev PC; CI wall-time budgets may need a look after the next full run. Probe adds about 7.1 plus 7.7 MB of float32 per platform per full run.
- Open: `ci/hash_expected.json` `rate-curves-44100` and `-48000` wait for a green four-platform full run, which needs a push (Audio's go-ahead). Review pass not yet run.

## Spec Change Log

## Review Triage Log
