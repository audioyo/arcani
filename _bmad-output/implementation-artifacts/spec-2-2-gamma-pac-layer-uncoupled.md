---
title: 'Story 2.2: Gamma PAC layer, uncoupled'
type: 'feature'
created: '2026-11-07'
baseline_commit: '63536b4f89605c9cf950bc742d8f443a88e25a95'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The gamma PAC layer is still the stub `gamma = 0.0`, and the recipe has no gamma field. There is no gamma layer to listen to and no uncoupled control for later coupling comparisons.

**Approach:** Write signal spec §gamma (AM law, uncoupled setting, worked vectors, margin per tap). Add the recipe fields and validator checks. Replace the engine and reference gamma stubs with an uncoupled gamma layer. Add an AM depth tool, calibrated on Python-synthesized signals first.

Decisions (2026-11-07, build agent, under Audio's standing "settle tech forks yourselves" preference):
- **Recipe fields** (`gamma_pac`, optional object, all five members required, placed after `theta_reference` in schema and field table order): `carrier_hz` (row `gamma-carrier`), `rate_hz` (row `gamma-rate`), `am_depth_percent` (row `coupling-depth`), `carrier_wave`, one of `sine`, `triangle`, `softened_square`, and `coupling`, enum `uncoupled` only (Stories 2.3 and 2.4 add `smooth_swell` and `bursts`). Triangle and softened square are schema-valid so compile rejects them by name: parameter `/gamma_pac/carrier_wave`, value the text, rule `non-sine carrier not modeled`, limit `sine`. The carrier rule checks `carrier_hz` against `rate_hz`.
- **AM law:** the theta sine shape at the gamma rate. Two accumulators, phase 0 at n = 0: carrier at `carrier_hz`, envelope at `rate_hz`. `e = (1 + cos 2 pi phi) / 2` (engine: `sine(p + 2^62)`, as §theta), `a = 1 - d * (1 - e)`, `d = am_depth_percent / 100`, `gamma = a * sine(carrier phase)`, both channels. Uncoupled means `d` is constant for the whole render. Unit amplitude: level fields are Epic 4, as for theta.
- **Error margin per tap** (design log (ee)): gamma tap 2 sine evaluations; bus and output add every other layer's count. §gamma states each bound.
- **AM depth tool** (`tests/assertions/am_depth.py`): analytic envelope of a tap, the first and last 0.5 s trimmed; per full gamma cycle the peak and trough. Constant depth means every cycle's peak is within row `reference-match` (as linear full-scale amplitude) of 1 and every trough within it of `1 - d`. No new row. Calibration: harness AM tones at 25 and 100 percent pass; must-fails: depth stepped 1 percent mid-render, and a slow depth drift.
- **Frequency tool:** reused unchanged, with calibration cases added at a 250 Hz carrier and 40 and 60 Hz rates, read within row `frequency-accuracy-calibration`.
- **Fixtures** (`recipes/fixtures/valid/`): `gamma-uncoupled-40hz-25pct.json`, `-40hz-100pct`, `-60hz-25pct`, `-60hz-100pct` (gamma only, 250 Hz sine carrier, 10 s), and `theta-gamma-uncoupled.json` (theta sine, 450 Hz, 6 Hz, 75 percent; gamma 250 Hz, 40 Hz, 100 percent; 10 s) for the bus sum. Invalid: carrier 200 at 60 Hz, triangle, softened square, coupling text not in the enum.
- **Hash check:** probe components `gamma-uncoupled-44100` and `-48000`, scope `engine`, the 5 fixtures in turn. Expected hashes from a green four-platform full run (design log (kk)). Cost: about 16 and 18 MB of float32 per platform per full run; no paid service.
- **Rows:** `pending` cleared on `coupling-depth`. Design log entry (mm).

## Boundaries & Constraints

**Always:** §gamma merges, with vectors from `tools/signal_spec_vectors.py`, before engine or reference implement it. Tests first, from a fresh-context QA agent, committed failing. Every tool has a passing and a must-fail fixture made in the harness. Thresholds and ranges come from the tables. Every existing check, stub chain vector, and pinned hash keeps passing.

**Never:** Coupling, coupling phase, swell, bursts, or the AD-5 rejection (Stories 2.3, 2.4). Change theta, binaural, or master chain behavior. Add level fields, gain ramps, or rate curves. Fault injection or libm in `engine/`. Push or open the PR without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Each gamma fixture, 44.1 and 48 kHz | fixture | gamma tap, bus, output within -100 dBFS of the reference; carrier and rate within row `frequency-accuracy`; depth constant | N/A |
| Range edges | carrier 200/500, rate 30/60, depth 0/100 | accepted (carrier rule permitting) | 199.99, 500.01, 29.99, 60.01, -0.01, 100.01 rejected with the row |
| Carrier rule | 200 Hz at 60 Hz; 240 Hz at 60 Hz | rejected `carrier_rule`, limit `>= 240 Hz (4 x 60 Hz, row carrier-rule)`; accepted | no plan |
| Non-sine carrier | `triangle`, `softened_square` | rejected, rule `non-sine carrier not modeled`, limit `sine` | no plan |
| Unknown text | `carrier_wave: "square"`, `coupling: "swell"` | schema rule `enum` | no plan |
| No `gamma_pac` | every existing fixture | bytes unchanged | N/A |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md` -- new §Gamma PAC layer after §Theta reference; the Stub chain `gamma = 0.0` line and its bus bit-equality sentence point to it. `-0.0`: at 100 percent depth the gamma tap can be `-0.0`; state what the bus is there.
- `tools/signal_spec_vectors.py`, `tests/data/signal_spec_vectors.json`, `tests/cpp/SpecTables.cmake` -- gamma vectors (increments, envelope, samples at block boundaries, fixtures table), following the §theta pattern; `test_signal_spec_core.py` pins the table count (16 now).
- `recipes/recipe.schema.json`, `engine/src/recipe/field_table.cpp` (gamma rows between theta and binaural), `recipe.hpp` (`GammaPac`, `GammaCarrierWave`, `GammaCoupling`, enum text constants like `kThetaShapeEnum`), `recipe.cpp` (parse, enum check).
- `engine/src/validate/validate.{hpp,cpp}` -- `kRows` gains `gamma-rate`, `gamma-carrier`, `coupling-depth`; `field_value` the three paths; `check_rules` adds the gamma carrier rule then the carrier-wave rule after the theta rules.
- `engine/src/plan/plan.{hpp,cpp}` (`GammaOscillator`: present, two increments, depth), `render/renderer.cpp` (gamma sample replaces `const double gamma = 0.0`; seek sets both gamma phases). Reuse `core::envelope(EnvelopeShape::Sine, ...)` or a sine-only helper in `core/envelope`.
- `reference/stub_chain.py` (gamma tap), new `reference/gamma.py` (from the spec, not from `theta.py` code); `tests/python/test_reference_independent.py` must pass.
- Tests: new `tests/cpp/test_gamma.cpp` (add to `tests/cpp/CMakeLists.txt`, `__has_include` guard as `test_theta.cpp`), `test_validate.cpp`, `test_recipe.cpp`; new `tests/python/test_gamma_reference.py`, `test_am_depth_tool.py`, `test_probe_gamma.py`; `test_frequency_tool.py`, `test_recipe_schema.py`, `test_hash_compare.py` (entry count).
- `tests/hashprobe/main.cpp` (`render_recipe()`; add `probe_gamma()` like `probe_theta()`), `ci/hash_expected.json` (after the full run).
- Records: `tests/tables/ranges.tsv`, `_bmad-output/specs/spec-arcani-v0-1/thresholds-and-ranges.md` if a row changes, `docs/design-log.md` (mm), `recipes/README.md`, `recipes/fixtures/invalid-expected.json`, `tests/data/recipe_hash_vectors.json` (`tools/recipe_hash.py --write-vectors`).

## Tasks & Acceptance

**Execution:**
- [ ] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, vectors JSON -- §gamma with worked vectors -- the spec merges first.
- [ ] tests (files above) -- QA agent writes failing tests -- tests first.
- [ ] schema, field table, recipe, validator, plan, renderer, `reference/gamma.py`, `stub_chain.py`, `tests/assertions/am_depth.py`, hash probe -- implementation.
- [ ] fixtures, hash vectors, rows, design log (mm), README, `ci/hash_expected.json` (after the full run) -- records.
- [ ] `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given §gamma, then it defines the AM law and the uncoupled setting with vectors the engine and the reference each pass, and states the margin per tap by sine evaluations.
- Given each gamma fixture at both rates, then the engine gamma tap and output differ from the reference by less than row `reference-match`, the frequency tool reads carrier and rate within row `frequency-accuracy`, and the AM depth tool finds depth constant at the recipe value.
- Given the harness signals, then the AM depth tool passes the steady tones and fails the stepped and drifting ones.
- Given the hash probe, then the gamma components equal on all four platforms and match their expected entries.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: every ctest passes.
- `uv run pytest` -- expected: all pass (the gamma hash-entry tests only after the full run).
- `uv run --no-project python tools/check_engine_source.py`, `tools/check_wording.py`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main` -- expected: exit 0.

## Implementation Notes

- 2026-11-07: §gamma written in `docs/signal-spec.md` with four vector tables (gamma envelope, gamma fixtures, gamma samples, theta and gamma bus) from `tools/signal_spec_vectors.py`; 20 vector tables in all. `tests/cpp/SpecTables.cmake` generates `kGammaEnvelopes`, `kGammaSamples`, `kGammaBus`. The engine gamma envelope never reaches 0 (trough about 2.8e-8), so the engine gamma tap is never `-0.0`; the reference's can be, at 100 percent depth.
- Compile-rejected fixtures (carrier rule 200 Hz at 60 Hz, triangle, softened square) go in `recipes/fixtures/valid/`: that folder is the schema verdict (`recipes/README.md`), and these are schema-valid. The schema faults (`coupling: "swell"`, `carrier_wave: "square"`) go in `invalid/`.
- Red state of the tests-only commit (fresh-context QA agent), on the dev PC: `uv run pytest`: 79 failed, 39 errors, 1599 passed, 2 skipped (baseline 1575 passed). Failures by file: `test_am_depth_tool.py` 40 (no `am_depth.py`), `test_gamma_reference.py` 17 failed plus 39 setup errors (no `reference/gamma.py`, no fixtures), `test_probe_gamma.py` 5 (no probe components), `test_recipe_hash.py` 7 and `test_recipe_schema.py` 7 (no `gamma_pac` in the schema), `test_signal_spec_core.py` 2 (fixture files missing), `test_hash_compare.py` 1 (no gamma expected entries until the four-platform full run). ctest: `arcani_tests` 24 of 214 Catch2 cases fail (gamma parse, field table, validator rows and rules, plan, renderer, fixtures), the build compiles, the other three ctest entries pass.
- QA findings: the frequency tool can misread the carrier on a 100 percent AM tone whose envelope reaches exact zero, so it is pointed only at engine output (trough above 0) and at harness tones with the engine's trough floor; the AM depth tool's sampling grid alone gives about -106.8 dBFS at 44.1 kHz, 60 Hz, 100 percent, against the -100 dBFS row.

## Spec Change Log

## Review Triage Log
