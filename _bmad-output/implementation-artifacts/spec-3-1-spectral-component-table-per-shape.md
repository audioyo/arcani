---
title: 'Story 3.1: Spectral component table per shape'
type: 'feature'
created: '2026-11-16'
baseline_commit: 'dbb346fb9a5d2d25267214ee789bcc756daaf837'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/review-carrier-rule-coupled-gamma-2026-11-16.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The validator cannot say what each layer puts in each ear. Story 3.2's spacing rule needs every layer's spectral lines, per ear, over the whole session, in closed form (AD-20). Threshold row `spectral-component-level` (40 dB) is pending on this story.

**Approach:** The signal spec gains a Components section: the Fourier line model of every v0.1 shape, with worked vectors. Compile builds a component table from it and stores it in the plan. The Python reference builds the same table from the spec on its own. A cross-check measures reference renders of Epic 2's fixtures with the Story 2.4 spectrum tool and holds every line to the table.

Decisions (2026-11-16, build agent; Audio delegated every decision and approval for Stories 3.1 to 3.3 on 2026-11-16):
- **Carrier rule unchanged (rule 4 review, 2026-11-16, `review-carrier-rule-coupled-gamma-2026-11-16.md`):** the modulation rate of a carrier is its layer's own named rate, at its worst case along a rate cycle; coupling does not change it. The stricter reading (gamma rate plus theta rate) is not adopted: no source decides it, it is not consistent for bursts, and it would reject `bursts-60hz.json` and `gamma-cycle-swell-theta-cycle.json`. The Components section records the definition; Story 3.3 gets a listening line for a 250 Hz carrier with coupled gamma AM at 60 Hz. `check_carrier_rule` and every error text stay as they are.
- **Line model.** A layer is `a(t) * sin(2 pi f_c t)` with `a >= 0` periodic, so its lines sit at `f_c` plus the lines of `a`, and the carrier line is always the strongest. Level is the line amplitude over the carrier line amplitude, a linear ratio in (0, 1]. A component is a line with level at least `10^(-40/20)` (row `spectral-component-level`).
  - Theta, depth `d`, envelope coefficients `c_k`, `w = E * rate_hz` (edge share of the cycle, center rate): carrier amplitude `1 - d + d c_0`, lines at `f_T +- k f_theta` with amplitude `d |c_k|`. Sine: `c_0 = 1/2`, `c_1 = 1/4`. Smoothed on-off (half on share `h = 1/4`): `c_0 = 2h - w`, `c_k = sin(pi k (2h - w)) / (pi k) * P(k, w)`. Sawtooth and reverse saw: `c_0 = 1/2`, `|c_k| = |P(k, w) + sin(pi k w) / (pi k (1 - w))| / (2 pi k)`. `P(k, w) = cos(pi k w) / (1 - (2 k w)^2)`, and `pi / 4` at `2 k w = 1`.
  - Gamma uncoupled: carrier `1 - d/2`, `f_G +- f_M` at `d/4`.
  - Smooth swell: carrier `1 - d/4`; `f_G +- f_theta` and `f_G +- f_M` at `d/8`; `f_G +- f_M +- f_theta` at `d/16`. The coupling phase moves no line.
  - Bursts: gate coefficients `g_j` are the smoothed on-off form with `h = 0.025 * rate_hz` and `w = 0.01 * rate_hz` of the theta reference; lines `(i, j)` at `f_G + i f_M + j f_theta`, `i` in {-1, 0, 1}: `(0, 0)` at `1 - d g_0 / 2`, `(0, j)` at `d |g_j| / 2`, `(+-1, j)` at `d |g_j| / 4`. When neither rate has a cycle and the gamma rate is an exact whole multiple of the theta rate, lines at one frequency add as complex amplitudes (gate phase `e^(-2 pi i j C / 2^64)`), and the table holds the sum. Amended 2026-11-16 (orchestrator, under Audio's delegation, on the engagement 1 finding): lines also coincide at a whole number plus one half (45 Hz over 6 Hz), so the sum applies whenever twice the gamma rate is a whole multiple of the theta rate and neither rate has a cycle.
  - Binaural: one line per ear at level 1: left `f_L`, right `f_L + beat rate`.
- **Rate cycles.** Levels do not change along a cycle (`W`, `Hb`, `Wb` are fixed shares of the theta cycle). A component's frequency is `center + i * swing_M * sin(...) + j * swing_theta * sin(...)`; the table gives `center_hz` and the exact interval `[low_hz, high_hz]`, half width `sqrt((i s_M)^2 + (j s_T)^2 + 2 i j s_M s_T cos(phi_M - phi_T))`. A frequency below 0 is listed at its absolute value (an interval that crosses 0 starts at 0).
- **Table.** Per ear (left, then right), per layer (theta reference, gamma PAC, binaural), ascending `center_hz`: layer, ear, `center_hz`, `low_hz`, `high_hz`, `level`, and the integer rate multipliers (`gamma_mult`, `theta_mult`, `beat_mult`) Story 3.2 needs. A muted ear has no binaural component. Public C API: `arc_plan_component_count` and `arc_plan_component`.
- **Unmodeled shape.** The existing rejections (custom theta shape, non-sine gamma carrier, non-sine binaural) keep their texts and order. The table builder itself returns rule `no component model` for any shape it has no model for, tested directly on the builder.
- **Engine arithmetic.** Basic binary64 operations, `sqrt`, and the cycle cosine only (no transcendental call), so the table is the same bytes on every platform. New threshold rows, engineering defaults: `component-level-error` (1e-6, ratio) and `component-frequency-error` (1e-9 Hz) bound the engine table and the reference table against the vectors. A line whose ideal level is within `component-level-error` of the threshold may be in or out.
- **Cross-check.** Static fixtures: every measured line within 40 dB of its tap's strongest line is in the table within rows `spectrum-frequency` and `spectrum-level`, and every table component is measured. Rate-cycle fixtures (120 s): the table's intervals, widened by the tool's resolution, merge into bands; each band's measured power equals the sum of its components' level squared within `spectrum-level`, and no line at or above the 40 dB threshold lies outside the bands. The band power measure is calibrated first on Python-synthesized swept tones of known power.

## Boundaries & Constraints

**Always:** The Components section and its vectors (`tools/signal_spec_vectors.py`, exact and 60-digit arithmetic) land before engine or reference code. Tests first from a fresh-context QA agent, committed failing. Must-fail: a model doctored in the harness to drop one side frequency fails the cross-check; no fault code in `engine/`. Thresholds from the tables only; `spectral-component-level` loses `pending`. Every existing vector, fixture byte, recipe hash, error text, and pinned hash keeps passing. A probe component hashes the table of a few fixtures on all four platforms. Design log entry (vv).

**Never:** The spacing rule or any new rejection of a recipe that compiles today (Story 3.2). Changing the carrier rule. Sampling the session to find components. Reading the table at render time. Starter recipe files (3.3). Changing `tests/assertions/spectrum.py`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Sine theta | 450 Hz carrier, sine AM at 6 Hz, 75 percent | both ears: 444, 450, 456 Hz; levels 0.3, 1, 0.3 | N/A |
| Smooth swell | 250 Hz carrier, AM at 40 Hz, 100 percent, theta 6 Hz | 9 lines, 204 to 296 Hz; 1/6 and 1/12 of the carrier | N/A |
| Bursts, whole ratio | `bursts-60hz.json` | coincident lines summed; equals the measured spectrum | N/A |
| Depth 0 | any layer at depth 0 | the carrier alone | N/A |
| Beat rate cycle | `binaural-cycle-sleep.json` | left 100 Hz; right center 101.5, interval [100, 103] | N/A |
| Theta cycle | theta 3.5 +- 2.5 Hz, sine | `450 +- k` lines with intervals `k * [1, 6]` Hz from the carrier | N/A |
| Muted ear | right ear muted | no right binaural component | N/A |
| Unmodeled shape | builder given a custom shape | no table | rule `no component model` |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md` -- new Components section after Loop (before 24-bit rounding); header story list (line 5). Formulas: Theta reference (429), Gamma PAC layer (892), Coupling (1232), Bursts (1593, its Spectrum paragraph), Binaural layer (1970), Rate curve (2158).
- `tools/signal_spec_vectors.py`, `tests/data/signal_spec_vectors.json`, `tests/cpp/SpecTables.cmake` -- vectors; `tests/python/test_signal_spec_core.py` pins the table count.
- `engine/src/validate/validate.{hpp,cpp}` -- `check_rules()` (carrier rule, shape rejections) unchanged. New `engine/src/validate/components.{hpp,cpp}`.
- `engine/src/core/rate_cycle.{hpp,cpp}` (cycle cosine, cycles-to-units), `core/envelope.*`, `core/sine.*` -- reuse; no new transcendental.
- `engine/src/plan/plan.{hpp,cpp}` -- build the table after `check_rules()`; `Plan::components`.
- `engine/include/arcani/arcani.h`, `engine/src/api/api.cpp` -- two new calls; pattern: `arc_plan_loop`.
- `reference/` -- new `reference/components.py`, from the spec only; `reference/ideal.py`, `rate_curve.py` helpers.
- `tests/assertions/spectrum.py` (`lines`, `match`, `check`; unchanged), `tables.py`; new `tests/assertions/component_check.py`.
- `tests/tapdump/main.cpp` -- new mode `--components` writing `components.tsv` (`%.17g`).
- `tests/hashprobe/main.cpp`, `ci/hash_expected.json`, `tools/probe_reference.py` -- probe component `components`.
- `tests/tables/thresholds.tsv`, `tools/check_table_log.py`, `tools/check_row_coverage.py` -- rows.
- `tools/check_engine_source.py` -- `sqrt` passes; transcendental calls fail.
- Records: `docs/design-log.md`, `deferred-work.md` (carrier rule row closed), `docs/timeline-guidebook.html`, `sprint-status.yaml`.

## Tasks & Acceptance

**Execution:**
- [ ] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, vectors JSON, `SpecTables.cmake` -- Components section with vectors -- the spec merges first.
- [ ] `tests/tables/thresholds.tsv`, `docs/design-log.md` (vv) -- rows and the carrier rule decision -- tables are data.
- [ ] tests (C++ `tests/cpp/test_components.cpp`; Python tool calibration, reference table, cross-check, probe) -- a fresh-context QA agent writes failing tests -- tests first.
- [ ] `engine/src/validate/components.*`, plan, C API, tap dump mode, hash probe -- implementation.
- [ ] `reference/components.py`, `tests/assertions/component_check.py` -- reference and cross-check tool.
- [ ] `deferred-work.md`, guidebook, `sprint-status.yaml`, `ci/hash_expected.json` -- records.

**Acceptance Criteria:**
- Given the signal spec, when Components merges, then it models every v0.1 shape with vectors, and defines a component by row `spectral-component-level`.
- Given a compiled recipe, when the table is read through the C API, then it lists per ear and per layer every component's center, interval, and level, equal to the vectors within the two error rows.
- Given reference renders of every Epic 2 shape fixture, when the cross-check runs, then every measured line is in the table and every table component is measured, within the spectrum rows.
- Given a model with one side frequency dropped in the harness, then the cross-check fails.
- Given the hash probe, then `components` agrees on all four platforms.

## Implementation Notes

### Engagement 1 (2026-11-16): what landed

- `docs/signal-spec.md`, Components (after Loop, before 24-bit rounding), with three vector tables: `Vectors: component coefficients`, `Vectors: component cases`, `Vectors: components`. 44 generated tables in all.
- `tools/signal_spec_vectors.py`: the model in exact and 70-digit decimal arithmetic; `tests/data/signal_spec_vectors.json` regenerated (new keys only, the `spec` text aside); `tests/cpp/SpecTables.cmake` emits the new tables. `tests/python/test_signal_spec_core.py`: only the pinned table count, 41 to 44.
- `tests/tables/thresholds.tsv`: rows `component-level-error` (0.000001, ratio) and `component-frequency-error` (0.000000001, Hz), both pending on this story. `spectral-component-level` keeps `pending` until an assertion reads it through `row` (the row coverage check fails a used row that is still pending, and an unused row that is not): engagement 3 clears all three.
- `docs/design-log.md` entry 2026-11-16 (vv).

### Finding against the frozen Line model decision

The decision sums coincident burst lines "when ... the gamma rate is an exact whole multiple of the theta rate". Lines also coincide when the ratio is a whole number plus one half: `bursts-45hz.json` (45 Hz over 6 Hz) has `(1, j)` and `(-1, j + 15)` at one frequency. Listed singly they differ from the true spectrum by up to 0.063 in level, so the cross-check acceptance criterion could not pass on that fixture. The Components section sums whenever twice the gamma rate is a whole multiple of the theta rate (neither rate with a cycle). The whole-multiple case is exactly as decided. Verified by an independent NumPy FFT of one period of the ideal amplitude for all 30 static cases: same rows, levels within 3.3e-14. Other points the section settles, none contradicting the frozen text: the whole test is the Loop Cycle rule's binary64 test; a cycle of swing 0 is no cycle; a summed row is named after the member with the smallest `|gamma_mult|`, then `|theta_mult|`; ties in `center_hz` order by `gamma_mult`, then `theta_mult`.

### Contracts for the tests (engagement 2) and the implementation (engagement 3)

**Vectors (`tests/data/signal_spec_vectors.json`).**

- `component_constants`: `level_db` ("40.0"), `threshold` ("0.01"), `threshold_hex` (the binary64 nearest), `level_error`, `frequency_error`, `layers` (`theta_reference`, `gamma_pac`, `binaural`), `ears` (`left`, `right`), `no_model_rule` (`no component model`), `case_length_s`, `probe_cases` (six case names, in probe order).
- `component_coefficients`: rows `form` (`smoothed_on_off`, `sawtooth`, `burst_gate`), `rate_hex`, `h_hex` (or `none`), `w_hex`, `k`, `p`, `c`, `bound` (decimal text, or `none`).
- `component_cases`: rows `case`, `fixture` (file name in `recipes/fixtures/valid/`, or `none`), `mute` (`none`, `left`, `right`), `theta_reference`, `gamma_pac`, `binaural` (compact JSON text of the layer object, or `none`), `recipe` (a complete compile-ready recipe text), `components` (row count, both ears).
- `components`: rows `case`, `ear` (`both`, `left`, `right`), `layer`, `gamma_mult`, `theta_mult`, `beat_mult` (integers), `center`, `low`, `high`, `level` (decimal text, 25 digits). In table order per case, the two ear tables merged: expand `both` to a left row and a right row, then left rows first.
- C++ (`spec_tables.hpp`, namespace `arcani::test::spec`): `kComponent_level_db`, `kComponent_threshold`, `kComponent_threshold_binary64`, `kComponent_level_error`, `kComponent_frequency_error`, `kComponent_case_length_s` (double), `kComponent_no_model_rule` (text), `kComponent_layers[]`, `kComponent_ears[]`, `kComponent_probe_cases[]` (text arrays); `ComponentCoefficientVector {form, rate_hz, has_h, h, w, k, has_p, p, c, has_bound, bound}` in `kComponentCoefficients[]`; `ComponentCaseVector {name, fixture, mute, recipe, components}` in `kComponentCases[]`; `ComponentVector {case_name, ear, layer, gamma_mult, theta_mult, beat_mult, center_hz, low_hz, high_hz, level}` in `kComponents[]`.
- Thresholds come from the tables only: rows `spectral-component-level`, `component-level-error`, `component-frequency-error`, `spectrum-frequency`, `spectrum-level`. The constants in the vectors file are there to be cross-checked against the rows, not to replace them.

**Public C API (`engine/include/arcani/arcani.h`, `engine/src/api/api.cpp`).**

```c
typedef enum arc_component_layer {
  ARC_COMPONENT_THETA_REFERENCE = 0,
  ARC_COMPONENT_GAMMA_PAC = 1,
  ARC_COMPONENT_BINAURAL = 2
} arc_component_layer;

typedef enum arc_ear { ARC_EAR_LEFT = 0, ARC_EAR_RIGHT = 1 } arc_ear;

typedef struct arc_component {
  arc_component_layer layer;
  arc_ear ear;
  double center_hz;
  double low_hz;
  double high_hz;
  double level;       /* line amplitude over the layer's carrier line, in (0, 1] */
  int32_t gamma_mult;
  int32_t theta_mult;
  int32_t beat_mult;
} arc_component;

/* Component count; 0 for NULL. */
size_t arc_plan_component_count(const arc_plan* plan);
/* Fills *out_component with row `index` of the table (left ear rows first). */
arc_status arc_plan_component(const arc_plan* plan, size_t index, arc_component* out_component,
                              arc_error* error);
```

`arc_plan_component` follows `arc_plan_stage`: `ARC_ERR_INVALID_ARGUMENT` for a NULL `plan` (parameter `plan`), a NULL `out_component` (parameter `out_component`), or `index >= count` (the existing `bad_index` error). The table is the same at 44100 and 48000 Hz and honors `mute_binaural_ear`. Plain C: `tests/cpp/test_api_c.c` must still compile with the header.

**Engine internals (`engine/src/validate/components.{hpp,cpp}`, namespace `arcani::validate`).**

```cpp
enum class ComponentLayer : int { ThetaReference = 0, GammaPac = 1, Binaural = 2 };
enum class Ear : int { Left = 0, Right = 1 };
struct Component {
  ComponentLayer layer; Ear ear;
  double center_hz, low_hz, high_hz, level;
  std::int32_t gamma_mult, theta_mult, beat_mult;
};
enum class MutedEar { None, Left, Right };
struct ComponentResult { std::vector<Component> components; std::optional<recipe::Error> error; };
inline constexpr std::string_view kNoComponentModelRule = "no component model";
inline constexpr double kComponentLevelDb = 40.0;                      // row spectral-component-level
inline constexpr double kComponentThreshold = 0x1.47ae147ae147bp-7;    // 10^(-40/20)
ComponentResult build_components(const recipe::Recipe& r, MutedEar mute);
```

On an unmodeled shape `components` is empty and `error` is: `/theta_reference/shape`, `custom`, `no component model`, `sine, smoothed_on_off, sawtooth, reverse_saw`; or `/gamma_pac/carrier_wave`, the wave text, `no component model`, `sine`; or `/binaural/waveform`, `triangle`, `no component model`, `sine`; checked in that order. `plan::Plan` gains `std::vector<validate::Component> components`, filled in `plan::compile` after `check_rules()`; a builder error there is returned as the compile error (unreachable today, since `check_rules()` rejects those shapes first with their own texts). The renderer never reads it. `tools/check_engine_source.py` must keep passing: `sqrt` is allowed, no transcendental call.

**Tap dump (`tests/tapdump/main.cpp`).** `arcani-tapdump RECIPE RATE OUT_DIR --components [--mute left|right]` compiles, renders nothing, and writes `OUT_DIR/components.tsv`: a header line `ear<TAB>layer<TAB>gamma_mult<TAB>theta_mult<TAB>beat_mult<TAB>center_hz<TAB>low_hz<TAB>high_hz<TAB>level`, then one line per row in table order, `ear` as `left` or `right`, `layer` as `theta_reference`, `gamma_pac`, or `binaural`, the four doubles as `%.17g`, LF line ends. It prints `arcani-tapdump: components N` and exits 0; exit codes otherwise as the other modes.

**Hash probe (`tests/hashprobe/main.cpp`, `ci/hash_expected.json`).** One new component `components`, scope `engine`, after `loop-48000`. For each case of `probe_cases`, in order (recipe text embedded like the other probe fixtures, compiled at 48000 Hz, no muted ear): one float32 holding the row count, then per row 21 float32 values: `layer`, `ear`, `gamma_mult`, `theta_mult`, `beat_mult` as their integer values, then `center_hz`, `low_hz`, `high_hz`, `level`, each as the four 16-bit words of its binary64 pattern, most significant first, every word a float32 in 0 to 65535 (exact). So the hash covers every bit of the table. 6 + 21 * 314 = 6600 samples (rows: 106, 46, 72, 64, 24, 2). The expected entry is pinned from a full four-platform CI run, as for every engine component; until then the hash-entry test for `components` is the one expected failure.

**Python reference (`reference/components.py`).** From the signal spec only (`tests/python/test_reference_independent.py` rules apply).

```python
class Component(NamedTuple):
    layer: str          # "theta_reference" | "gamma_pac" | "binaural"
    ear: str            # "left" | "right"
    center_hz: float
    low_hz: float
    high_hz: float
    level: float
    gamma_mult: int
    theta_mult: int
    beat_mult: int

class NoComponentModel(ValueError):
    parameter: str; value: str; rule: str; limit: str      # rule is "no component model"

def component_table(recipe: dict, mute: str = "none") -> list[Component]: ...
def component_table_from_file(recipe_path, mute: str = "none") -> list[Component]: ...
```

`recipe` is the parsed recipe JSON; the result is the full table, left ear rows first.

**Cross-check tool (`tests/assertions/component_check.py`).** NumPy and the standard library; reads rows through `row` on every call; uses `spectrum.lines` and never changes `spectrum.py`. `table` is a list of rows with attributes `center_hz`, `low_hz`, `high_hz`, `level` for one layer in one ear (the reference `Component` fits).

```python
def threshold_db() -> float                      # row spectral-component-level
def check_static(name, x, fs, table) -> list     # report assertion dicts, as spectrum.check returns
def band_power_db(x, fs, lo_hz, hi_hz) -> float  # band power re the tap's total power, in dB
def bands(table, resolution_hz) -> list          # merged (lo_hz, hi_hz, expected_power_db)
def check_bands(name, x, fs, table) -> list      # report assertion dicts
```

- `check_static`: three dicts. Rows `spectrum-frequency` and `spectrum-level`: worst error over every table row against the nearest measured line (levels compared in dB, `20 * log10(level)`). Row `spectral-component-level`, measured the count of unmatched lines: a measured line within the threshold of the tap's strongest that no table row matches, or a table row with no measured line. A line or row within row `spectrum-level` of the threshold is exempt from the count (the nearest fixture lines sit 0.05 dB above it, at 148 Hz in `bursts-60hz.json`, and 0.17 dB under it).
- `check_bands`: for a rate-cycle fixture over a whole number of cycles. Each table interval widened by the tool's resolution (`8 * fs / len(x)` Hz at each end), overlapping intervals merged; per band the measured `band_power_db` against `10 * log10(sum of level^2)` re the same reference, within row `spectrum-level`; and the count of measured lines at or above the threshold outside every band (row `spectral-component-level`).
- Calibration first (`tests/python/test_component_check_tool.py`): `band_power_db` on Python-synthesized swept tones of known power, and `check_static` on synthesized multi-tone signals, each with a must-fail.
- Must-fail for the cross-check: the test drops one side-frequency row from the reference table in the harness and expects a fail. No fault code in `engine/` or `reference/`.

**Suggested test files (the QA agent may split differently).** `tests/cpp/test_components.cpp` (every case of `kComponentCases` compiled from its `recipe` text, and from its fixture file where it has one, against `kComponents` within the two error rows, same rows in the same order; both sample rates equal; muted ears; C API argument errors; `build_components` on an unmodeled shape; the coefficient vectors are for the reference and for any engine helper the implementation exposes), `tests/python/test_components_reference.py` (reference table against the vectors; fixture layer objects equal the case cells), `tests/python/test_component_check_tool.py` (calibration), `tests/python/test_components_crosscheck.py` (reference renders of every Epic 2 shape fixture; static and band checks; the dropped side frequency), `tests/python/test_components_engine.py` (the tap dump's `components.tsv` against the reference table within the error rows), `tests/python/test_probe_components.py` (probe component decoded against the reference table; hash entry).

## Spec Change Log

## Review Triage Log

## Design Notes

**Phased handoff (orchestrator, 2026-11-16).** The implementation agent works in three engagements on branch `story/3-1-spectral-component-table-per-shape`, never pushing:
1. Tasks 1 and 2 (signal spec section, vectors, table rows, design log entry). Then it writes the contracts the tests need (file names, function signatures, C API structs, tap dump mode, probe component, vector table names) under Implementation Notes, commits, and reports back. It writes no engine, reference, or test code in this engagement.
2. The orchestrator launches the fresh-context QA agent, which commits the failing tests alone.
3. The implementation agent is re-engaged for the remaining tasks, and never edits a test expectation to make it pass; a wrong test is reported back with the reason.

Commits are small, say what changed and why, and end with the lines `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01QHd78sH67YQwRftvvcTvJA`. Leave `_bmad-output/party-mode/memories/installed/.memlog.md` alone (unrelated local change). Edit files with UTF-8-safe tools (PowerShell 5.1 `Get-Content -Raw` reads UTF-8 as ANSI). Full `uv run pytest` takes about 30 min on the dev PC; run the story's own test files while iterating and the full suite once before reporting.

A prototype of the model (2026-11-16, NumPy, 48 kHz reference renders) matched the spectrum tool on the sine, smoothed on-off, sawtooth, and reverse saw theta fixtures at 1 and 6 Hz, the uncoupled and swell gamma fixtures, and the 40, 45, and 60 Hz burst fixtures: same line count (3 to 53 per layer), worst frequency error 0.0002 Hz, worst level error 0.013 dB.

A swept line keeps its power, so a rate-cycle fixture is judged by band power over a whole number of cycles, not by peak height.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: every ctest passes.
- `uv run pytest` -- expected: all pass (the probe hash-entry test passes after the full CI run).
- `uv run --no-project python tools/check_engine_source.py`, `tools/check_wording.py`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main`; `tools/signal_spec_vectors.py --check` -- expected: exit 0.
