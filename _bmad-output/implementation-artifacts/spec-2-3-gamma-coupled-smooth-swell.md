---
title: 'Story 2.3: Gamma coupled, smooth swell'
type: 'feature'
created: '2026-11-10'
baseline_commit: '2a14bc5388e9b80bc18ac5203af672af3249116b'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Gamma has only the uncoupled setting. Its AM depth cannot follow the theta reference, so the PAC layer, the core of the product, does not exist yet, and nothing measures coupling timing from the audio.

**Approach:** Write signal spec §coupling (swell depth function, coupling phase, worked vectors, margin per tap). Add the `smooth_swell` coupling and a coupling phase field, the AD-5 compile rejections, the engine and reference swell, and a coupling timing tool calibrated on Python-synthesized signals first.

Decisions (2026-11-10, build agent, under Audio's standing "settle tech forks yourselves" preference):
- **Recipe fields:** `gamma_pac.coupling` enum gains `smooth_swell` (Story 2.4 adds `bursts`). New optional `gamma_pac.coupling_phase_deg` (row `coupling-phase`, 0 to 360 inclusive, 360 the same point as 0), placed after `coupling`. Compile rejects `smooth_swell` without it (rule `coupled gamma needs a coupling phase`) and `uncoupled` with it (rule `coupling phase needs coupled gamma`), parameter `/gamma_pac/coupling_phase_deg`. Existing fixtures and hashes stay unchanged.
- **Swell law:** one raised cosine per theta cycle, centered on the coupling phase, the same for all four theta shapes, because §theta already puts each shape's 0 degree point at theta envelope phase 0. `C` = coupling phase as an integer phase (`deg / 360.0`, one rounding, times 2^64 exact, nearest integer ties to even, mod 2^64). Per sample, from the theta envelope phase `p_E` only: `s = sine_envelope(p_E - C mod 2^64)` (the §gamma envelope function), `a = 1.0 - (d * s) * (1.0 - e)`. So AM depth is `d` at the coupling phase and 0 half a theta cycle away; the carrier always plays. Smooth for every shape, so no edge of a hard-edged theta shape enters gamma.
- **AD-5 structural:** the engine swell is one function of (theta envelope phase, plan constants `C`); a C++ compile-time test pins its signature, and a test confirms the renderer passes the theta envelope accumulator and nothing else. No coupling-target field.
- **AD-5 rejections:** with `smooth_swell` and gamma `am_depth_percent > 0`, compile rejects a missing `theta_reference` and a theta `am_depth_percent` of 0, parameter `/gamma_pac/coupling`, value `smooth_swell`, rule `coupled gamma needs a theta reference with AM depth`. Gamma depth 0 passes. Order: after the carrier wave rule, then the coupling phase rules.
- **Margin per tap:** gamma tap 3 sines (swell, envelope, carrier); bus adds theta's 2; output adds the binaural sine. §coupling states each bound.
- **Coupling timing tool** (`tests/assertions/coupling_timing.py`): input the gamma tap, the theta tap, fs, theta rate, shape, coupling phase. Theta 0 degree times from the theta tap's analytic envelope fitted to the §theta ideal shape template (sub-sample). Swell peaks from the gamma tap's analytic envelope: `1 - |A|`, zero-phase low-pass below the gamma rate, a theta-rate cosine fit per cycle. Error per cycle = swell peak minus (0 degree time + phase / 360 / rate), wrapped. First and last 0.5 s trimmed. Reads only the two taps.
- **Fixtures:** theta 450 Hz, 6 Hz, 75 percent; gamma 250 Hz, 40 Hz; 5 s. The harness builds the 32 timing recipes (4 shapes x 0, 90, 180, 270 degrees x 25, 100 percent) in a temp folder. Committed in `valid/`: `swell-sine-0deg-100pct`, `swell-sawtooth-90deg-25pct`, `swell-smoothed-on-off-180deg-100pct`, `swell-reverse-saw-270deg-25pct` (the hash probe components `gamma-swell-44100` and `-48000`, scope `engine`), plus compile-rejected `swell-no-theta`, `swell-theta-depth-0`, `swell-no-coupling-phase`, `uncoupled-with-coupling-phase`, and accepted `swell-gamma-depth-0-no-theta`. Invalid: phase as text. Hash cost: about 7 MB of float32 per platform per full run, no paid service.
- **Zero level (Audio, 2026-11-10):** deferred to Story 4.4, where level and fade fields arrive: the theta zero-level rejection and the must-fail theta fade ending before a gamma fade. Logged in `deferred-work.md`. Today every layer runs at unit level, so no recipe can reach zero level.
- **Calibration tolerance (Audio, 2026-11-10):** new threshold row `coupling-timing-calibration`, 0.2 ms, a tenth of row `coupling-timing`, the frequency tool's rule (design log (ll)).
- **Rows:** `pending` cleared on `coupling-phase` and `coupling-timing`; `coupling-timing-calibration` added. Design log entry (nn).

## Boundaries & Constraints

**Always:** §coupling merges, with vectors from `tools/signal_spec_vectors.py`, before engine or reference implement it. Tests first, from a fresh-context QA agent, committed failing. The timing tool passes Python-synthesized signals with known peak times and fails a doctored one. Must-fail renders are made in the harness, never in `engine/`. Thresholds and ranges come from the tables. Every existing check, vector, and pinned hash keeps passing.

**Never:** Bursts, binaural coupling sweeps (Story 2.5), rate curves, level fields or gain ramps. Change theta, uncoupled gamma, binaural, or master chain output. Read the engine's internal depth in the timing tool. Fault injection or libm in `engine/`. Push or open the PR without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 32 timing renders, 44.1 and 48 kHz | shape x phase x depth | every swell peak within row `coupling-timing` of its coupling phase; gamma tap, bus, output within row `reference-match` | N/A |
| Harness shift | reference swell shifted 1 ms; 3 ms | passes; fails, at 25 and 100 percent | N/A |
| Phase edges | 0, 360, 359.99; -0.01, 360.01 | 0 and 360 give the same render; accepted; rejected with the row | no plan |
| AD-5 | no theta; theta depth 0; gamma depth 0 without theta | rejected; rejected; accepted, `a = 1.0` exactly | no plan |
| Uncoupled fixtures | every Story 2.2 fixture | bytes unchanged | N/A |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md` -- new §Coupling after §Gamma PAC layer (line 890 onward); §Gamma "Recipe fields", "Compile order", "Uncoupled", "Reference" point to it. Follow the §theta and §gamma pattern: fields, compile order, law (ideal and engine), per sample, seek (no new accumulator: the swell reads the theta envelope phase), reference, error bound, vectors.
- `tools/signal_spec_vectors.py`, `tests/data/signal_spec_vectors.json`, `tests/cpp/SpecTables.cmake` -- vectors: `C` per test phase, swell `s` and `a` at chosen phases, swell fixtures table, samples at block boundaries. `test_signal_spec_core.py` pins the table count (20 now).
- `recipes/recipe.schema.json` (`gamma_pac` at line 104), `engine/src/recipe/field_table.cpp`, `recipe.hpp` (`GammaCoupling`, `kGammaCouplingEnum`, `GammaPac` gains `std::optional<double> coupling_phase_deg`), `recipe.cpp`.
- `engine/src/validate/validate.{hpp,cpp}` -- `kRows` gains `coupling-phase`; `field_value` the path; `check_rules` (line 207) adds the coupling phase and AD-5 rules after the carrier wave rule.
- `engine/src/core/envelope.{hpp,cpp}` -- reuse `sine_envelope`; add a swell helper there or in plan if it keeps the AD-5 signature test simple.
- `engine/src/plan/plan.{hpp,cpp}` (`GammaOscillator` gains `coupled`, `coupling_phase_units`), `render/renderer.cpp` lines 55-62 (gamma reads `envelope_phase_`, the theta envelope accumulator; seek needs nothing new).
- `reference/gamma.py` (`COUPLINGS`, `render` gains the theta reference to derive `p_E`), `reference/stub_chain.py`; `tests/python/test_reference_independent.py` must pass.
- Tests: new `tests/cpp/test_coupling.cpp` (add to `tests/cpp/CMakeLists.txt`), `test_validate.cpp`, `test_recipe.cpp`; new `tests/python/test_coupling_reference.py`, `test_coupling_timing_tool.py`, `test_probe_swell.py`; update `test_gamma_reference.py` (its `COUPLINGS` contract), `test_recipe_schema.py`, `test_hash_compare.py`.
- `tests/hashprobe/main.cpp` (`probe_swell()` like `probe_gamma()`), `ci/hash_expected.json` after the full run. `tests/tapdump/` renders the harness temp recipes.
- Records: `tests/tables/ranges.tsv`, `thresholds.tsv`, `_bmad-output/specs/spec-arcani-v0-1/thresholds-and-ranges.md` if a row is added, `docs/design-log.md` (nn), `recipes/README.md`, `recipes/fixtures/invalid-expected.json`, `tests/data/recipe_hash_vectors.json` (`tools/recipe_hash.py --write-vectors`).

## Tasks & Acceptance

**Execution:**
- [x] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, vectors JSON -- §coupling with worked vectors -- the spec merges first.
- [x] tests (files above) -- fresh-context QA agent writes failing tests -- tests first.
- [x] schema, field table, recipe, validator, plan, renderer, `reference/gamma.py`, `stub_chain.py`, `tests/assertions/coupling_timing.py`, hash probe -- implementation.
- [ ] fixtures, hash vectors, rows, design log (nn), README, `ci/hash_expected.json` (after the full run) -- records.
- [x] `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given §coupling, then it defines the swell depth function per theta shape from theta phase alone, with vectors the engine and reference each pass, and states the margin per tap by sine evaluations.
- Given Python-synthesized swell signals with known peak times (filter delay included), then the timing tool reports them within the calibration tolerance and fails one with peaks moved past it.
- Given the C++ structural test, then the engine swell takes only the theta envelope phase as its signal input.
- Given each coupled render, then the gamma carrier and rate read within row `frequency-accuracy` and the carrier never stops: only AM depth varies.
- Given the hash probe, then the swell components equal on all four platforms and match their expected entries.

## Design Notes

Why one swell for every shape: a swell copied from the theta envelope would put the sawtooth's 10 ms drop into gamma depth and give smoothed on-off a flat top with no single peak to time. The raised cosine has one peak per cycle at the coupling phase for every shape, and the product sentence "smooth swell" describes it. No study sets the swell shape (research run `academic-lit-gamma-rate-and-coupling-phase-2026-10-27`, C5); it is an engineering default and design log (nn) says so.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: every ctest passes.
- `uv run pytest` -- expected: all pass (the swell hash-entry tests only after the full run).
- `uv run --no-project python tools/check_engine_source.py`, `tools/check_wording.py`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main`; `tools/signal_spec_vectors.py --check` -- expected: exit 0.

## Implementation Notes

- 2026-11-10: Signal spec Coupling section with four vector tables (coupling phase, swell, swell fixtures, swell samples; 24 in all) from `tools/signal_spec_vectors.py`, commit 28ba75d. `tests/cpp/SpecTables.cmake` generates `kCouplingPhases`, `kSwells`, `kSwellSamples`. Compile rule limits chosen by the build agent: AD-5 `theta_reference present with am_depth_percent > 0`; missing phase value `absent`, limit `present with coupling smooth_swell`; stray phase limit `absent with coupling uncoupled`. The frequency tool gains `rate_hz(..., min_hz=None)`, since a coupled gamma envelope has a theta-rate swell line as strong as its gamma-rate line.
- Red state of the tests-only commit (fresh-context QA agent), on the dev PC: `uv run pytest`: 409 failed, 1724 passed, 2 skipped. Failures by file: `test_coupling_timing_tool.py` 232 (no tool), `test_coupling_reference.py` 134 (no reference swell, fixtures, or engine coupling), `test_frequency_tool.py` 22 (no `min_hz`), `test_recipe_schema.py` 8, `test_probe_swell.py` 6, `test_recipe_hash.py` 5, `test_hash_compare.py` 1 (new component list), `test_gamma_reference.py` 1 (`COUPLINGS` contract). ctest: `arcani_tests` 35 of 246 Catch2 cases fail, the build compiles, the other three ctest entries pass.
- Implementation green on the dev PC: `windows-clang-cl` workflow 4/4 ctest entries pass; `uv run pytest` 2129 passed, 12 skipped, 4 failed, all waiting on the `gamma-swell-*` entries of `ci/hash_expected.json` from a four-platform full run (`test_hash_compare.py::test_real_expected_file_has_every_component_with_its_scope`, `test_probe_determinism.py::test_every_probe_component_has_an_expected_entry` and `::test_windows_x64_probe_matches_every_expected_entry`, `test_probe_swell.py::test_expected_entries_name_the_swell_components`). The extra skips are Windows application control blocking the freshly rebuilt probe (winerror 4551); in the run before, the probe ran and every swell segment matched the reference. `check_engine_source.py`, `check_wording.py`, `check_row_coverage.py`, `check_table_log.py --base main`, and `signal_spec_vectors.py --check` exit 0. Engine against reference on the four swell fixtures: worst gamma, bus, and output -137.1 dBFS; coupling timing worst 1.3e-6 ms; gamma carrier and rate within 7.0e-7 Hz. Design log (nn).
- Test edits during implementation (both QA defects, neither weakens a check): `test_validate.cpp` "valid/ means schema-valid" now lists the four compile-rejected swell fixtures as expected rejections; `test_coupling_timing_tool.py::test_swell_curve_has_no_delay` normalizes its lag correlation per lag, because the unnormalized dot product over a truncated window peaked at lag 1 even for an exact, undelayed copy of the swell.

## Spec Change Log

## Review Triage Log
