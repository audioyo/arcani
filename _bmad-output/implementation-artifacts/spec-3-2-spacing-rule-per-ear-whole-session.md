---
title: 'Story 3.2: Spacing rule per ear, whole session'
type: 'feature'
created: '2026-11-16'
baseline_commit: '12e3ad2aa60ff159e40025f305aaba3482b9c793'
status: 'done'
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
| Must-fail | `spacing-binaural-250-256-gamma-260.json` | rejected | `spacing_rule`, right ear, 4 Hz, gamma (-1, 0) 260 Hz vs binaural 256 Hz (multiplier corrected 2026-11-16: 300 - 40 Hz is gamma_mult -1), `whole session` |
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
- [x] `docs/signal-spec.md`, vectors -- Spacing section with vectors (pair distances, margins, error texts, first-time cases) -- the spec merges first.
- [x] fixtures, hash vectors, `thresholds.tsv`, design log (ww) -- data.
- [x] tests -- a fresh-context QA agent writes them failing -- tests first.
- [x] `engine/src/validate/spacing.*`, plan, error `detail`, C API, CLI report, reference, tap dump -- implementation.
- [x] `deferred-work.md`, `starter-recipes.md`, guidebook, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given a recipe's component table, when the spacing rule runs, then in each ear it checks 50 Hz between rows of different layers, exactly 50 Hz passes and less fails.
- Given a rate curve on any layer, then the closed-form worst case over the whole range decides, with no sampling.
- Given a spacing failure, then compile returns no plan and the error names parameter, value, rule, limit, both components, their layers, the ear, and where the minimum occurs.
- Given the must-fail fixture, then it is rejected in the right ear.
- Given the four starter fixtures and the AD-5 sweep, then each compiles, and its margins per ear are logged.
- Given engine and reference, then their minimum distances agree within row `component-frequency-error`.

## Implementation Notes

### Engagement 1 (2026-11-16): what landed

- `docs/signal-spec.md`, Spacing (after Components, before 24-bit rounding), and the header story list. Three vector tables: `Vectors: spacing cases`, `Vectors: spacing margins`, `Vectors: spacing pairs`; 47 generated tables in all.
- `tools/signal_spec_vectors.py`: the rule in 70-digit decimal arithmetic (first times by exact bisection on the cycle fraction), plus the spec's binary64 engine steps run on every vector pair as a check (worst distance error 1.3e-10 Hz, worst time error 2e-11 s). Component rows gain an internal `mirrored` flag that the JSON does not write. `tests/data/signal_spec_vectors.json` regenerated (new keys only, the `spec` text aside); `tests/cpp/SpecTables.cmake` emits the new tables. `tests/python/test_signal_spec_core.py`: only the pinned table count, 44 to 47.
- Fixtures in `recipes/fixtures/valid/`: `starter-focus-layers.json`, `starter-learn-layers.json`, `starter-relax-layers.json`, `starter-sleep-layers.json`, `spacing-binaural-250-256-gamma-260.json`, each written by `spacing_fixture_text()` of the generator (so the file equals the case's recipe values). `recipes/README.md` names them; `tests/data/recipe_hash_vectors.json` regenerated (`tools/recipe_hash.py --write-vectors`, five new entries only).
- `tests/tables/thresholds.tsv`: new row `spacing-time-error` (1, ms), pending on this story. `spacing-rule` keeps `pending` until an assertion reads it through `row` (the row coverage check fails a used row that is still pending, and an unused row that is not): engagement 3 clears both.
- `docs/design-log.md` entry 2026-11-16 (ww), with the margins per starter and per ear; the Current state "Carrier spacing" row cites it.
- Not done here (engagement 3, records): `deferred-work.md` (close the three Story 3.1 rows and the Sleep bound row), `starter-recipes.md` (Sleep bound 155 Hz, the Focus spacing risk), guidebook, `sprint-status.yaml`.

### Findings against the frozen sections

1. **Must-fail multipliers.** The I/O matrix writes the must-fail detail as `gamma (1, 0) 260 Hz`. In the component table the 260 Hz line of a 300 Hz carrier at 40 Hz is `gamma_mult -1` (300 - 40). The Spacing section writes the row as the table names it, with all three multipliers: `right ear: gamma_pac (-1, 0, 0) at 260 Hz and binaural (0, 0, 1) at 256 Hz; whole session`. Ear, value (4 Hz), both layers, both centers, and `whole session` are as the matrix says.
2. **Mirrored rows and "where".** The decision compares a mirrored row as a static interval at its worst case and gives "the first time" for any row that sweeps. The worst case of two intervals has no single moment, so a pair with a mirrored row and a sweep reports `listed intervals, a row mirrored below 0 Hz`. Only weak outer theta lines with a carrier near 100 Hz are ever mirrored; vector `spacing-mirrored-row` (a 1 Hz binaural carrier) covers it.
3. **Harness recipes in existing tests.** No fixture that compiles today is rejected (closest pair 64 Hz), and the AD-5 sweep passes (closest 64 Hz). But several recipes written inside test files collide and are expected to compile, so the rule would fail those tests. Found by hand (the QA agent confirms; `spacing_result(theta, gamma, binaural)` in the generator judges any layer set):
   - `tests/cpp/test_validate.cpp`: `with_gamma()` on the base `Values` (theta reference 300 Hz carrier at 6 Hz beside a gamma PAC 250 Hz carrier at 40 Hz: 294 Hz against 290 Hz, 4 Hz), used wherever a gamma case keeps the theta reference and expects a plan; and the "every other valid fixture compiles" list, which must name `spacing-binaural-250-256-gamma-260.json` as expected-rejected.
   - `tests/cpp/test_gamma.cpp` `theta_gamma_binaural_recipe()`, `tests/cpp/test_coupling.cpp` and `tests/cpp/test_bursts.cpp` (`kBaseTheta` with `kBinaural`), `tests/cpp/test_rate_curves.cpp` (the muted-ear case): a 450 Hz theta reference at 6 Hz (or 4 +- 2 Hz) beside a 400 Hz left and 406 Hz right binaural pair, 38 Hz or less.
   The tests-first engagement moves each to spacing-clean values that keep what the test checks (for example the binaural pair at 100 Hz left, as the AD-5 sweep and `three-layers` use), never weakening an assertion, and lists every change in its commit message. Every hash probe recipe is a fixture copy and passes, so no pinned hash moves.
4. **Settled, not contradicting:** with `H = 0` (a sweep that cancels, as in `spacing-sweep-together`) the first time is 0 s; the time is in the first cycle whatever the session length; `H` is evaluated as `sqrt(X^2 + Y^2)` (the same value as the three-term law, with the cycle cosine's error linear in the swings); the detail names each row by its three multipliers `(gamma_mult, theta_mult, beat_mult)`.

### Contracts for the tests (engagement 2) and the implementation (engagement 3)

**Vectors (`tests/data/signal_spec_vectors.json`).**

- `spacing_constants`: `rule_hz` ("50.0"), `time_error_s` ("0.001"), `rule` (`spacing_rule`), `limit` (`>= 50 Hz (row spacing-rule)`), `whole_session`, `listed_intervals` (the two fixed where texts), `carrier_fields` (`gamma_pac`: `/gamma_pac/carrier_hz`, `binaural`: `/binaural/carrier_left_hz`), `fixtures` (the five Story 3.2 fixtures), `must_fail_fixture`, `starter_fixtures` (four).
- `spacing_cases` (74 rows): `case`, `fixture` (file in `recipes/fixtures/valid/` or `none`), `mute`, `theta_reference`, `gamma_pac`, `binaural` (compact JSON or `none`), `recipe` (complete compile-ready text), `components` (row count, both ears), `result` (`pass` or `rejected`), `parameter`, `value` (ideal minimum distance, 25 digits), `rule`, `limit`, `detail` (ideal numbers); `none` for the error fields of a passing case. The first 46 are the component cases with the same names and recipe texts.
- `spacing_margins` (148 rows, case by case, left then right): `case`, `ear`, `pairs` (pairs compared in that ear), `distance`, `margin`, `index_1`, `row_1`, `index_2`, `row_2` (`<layer> (<i>, <j>, <b>)`), `where` (the where text with ideal numbers); every field but `case`, `ear`, `pairs` is `none` without a pair.
- `spacing_pairs` (12 rows): `label`, `c_hex`, `di`, `dj`, `db`, `swing_gamma_hex`, `start_gamma_hex`, `swing_theta_hex`, `start_theta_hex`, `swing_beat_hex`, `start_beat_hex` (a swing of 0 is no cycle; the period is 60 s), `x`, `y`, `h`, `distance`, `first` (cycle fraction `t / P`, `none` without a sweep).
- C++ (`spec_tables.hpp`, namespace `arcani::test::spec`): `kSpacing_rule_hz`, `kSpacing_time_error_s` (double); `kSpacing_rule`, `kSpacing_limit`, `kSpacing_whole_session`, `kSpacing_listed_intervals`, `kSpacing_must_fail_fixture`, `kSpacing_carrier_field_gamma_pac`, `kSpacing_carrier_field_binaural` (text); `kSpacing_fixtures[]`, `kSpacing_starter_fixtures[]`; `SpacingCaseVector {name, fixture, mute, recipe, components, rejected, parameter, value_hz, rule, limit, detail}` in `kSpacingCases[]`; `SpacingMarginVector {case_name, ear, pairs, has_pair, distance_hz, margin_hz, index_1, row_1, index_2, row_2, where}` in `kSpacingMargins[]`; `SpacingPairVector {label, c_hz, di, dj, db, swing_gamma_hz, start_gamma_deg, swing_theta_hz, start_theta_deg, swing_beat_hz, start_beat_deg, x, y, h, distance_hz, has_first, first}` in `kSpacingPairs[]`.
- Thresholds from the tables only: rows `spacing-rule`, `spacing-time-error`, `component-frequency-error`, `frequency-accuracy`. The vector constants are cross-checked against the rows, never used in their place.
- Comparing: distances, margins, and centers within row `component-frequency-error`; a time within row `spacing-time-error` around the cycle (`min(d mod P, P - d mod P)`, `P` 60 s); each rate within row `frequency-accuracy`; words of the detail exactly, numbers parsed by the grammar of Spacing, Error. Where the ideal value is a binary64 (every static pair), the error value text is its shortest round-trip text: `float(value) == float(ideal)`.

**Engine error and C API (`engine/src/recipe/recipe.hpp`, `engine/include/arcani/arcani.h`, `engine/src/api/api.cpp`).**

- `recipe::Error` gains `std::string detail;` after `limit`, empty for every other rule.
- `arc_error` gains `char detail[ARC_ERROR_DETAIL_BYTES];` after `limit`, with `#define ARC_ERROR_DETAIL_BYTES 512`, cut by the same rule as the other fields (at most `ARC_ERROR_DETAIL_BYTES - 1` bytes ending in `...`, never inside a UTF-8 sequence). Every call that writes an `arc_error` (compile, argument errors, warnings) writes it, `""` for every other rule. The header's top comment says five fields. `tests/cpp/test_api_c.c` must still compile.
- New:

```c
typedef struct arc_spacing {
  int32_t has_pair;        /* 0: fewer than two layers in this ear; every other field 0 */
  double min_distance_hz;  /* the smallest minimum distance of any pair in this ear */
  double margin_hz;        /* min_distance_hz - the value of row spacing-rule */
  size_t component_1;      /* arc_plan_component index of the pair's row 1 (the smaller index) */
  size_t component_2;      /* and of row 2 */
} arc_spacing;

/* The worst spacing pair of one ear (docs/signal-spec.md, Spacing, Margins).
   ARC_ERR_INVALID_ARGUMENT for a NULL plan (parameter "plan"), a NULL
   out_spacing (parameter "out_spacing"), or an ear other than ARC_EAR_LEFT
   and ARC_EAR_RIGHT (the existing bad enum error, parameter "ear", allowed
   "0 (left) 1 (right)"). */
arc_status arc_plan_spacing(const arc_plan* plan, arc_ear ear, arc_spacing* out_spacing,
                            arc_error* error);
```

  The result is the same at 44100 and 48000 Hz and honors `mute_binaural_ear`.

**Engine internals (`engine/src/validate/spacing.{hpp,cpp}`, namespace `arcani::validate`).**

```cpp
inline constexpr std::string_view kSpacingRule = "spacing_rule";
inline constexpr double kSpacingRuleHz = 50.0;   // row spacing-rule
struct SpacingPair {
  double min_distance_hz; double margin_hz;
  std::size_t component_1; std::size_t component_2;
};
struct SpacingResult {
  std::array<std::optional<SpacingPair>, 2> ears;   // [Ear::Left], [Ear::Right]
  std::optional<recipe::Error> error;               // the reported failure, detail filled
};
SpacingResult check_spacing(const recipe::Recipe& r, std::span<const Component> table);

// The closed form alone (Vectors: spacing pairs; period 60 s).
struct SpacingPairInput {
  double c_hz; int di, dj, db;
  double swing_gamma_hz, start_gamma_deg, swing_theta_hz, start_theta_deg, swing_beat_hz, start_beat_deg;
};
struct SpacingPairForm {
  double x, y, h, min_distance_hz;
  bool sweeps; std::uint64_t first_units;   // first time as cycle phase advance, valid when sweeps
};
SpacingPairForm spacing_pair_form(const SpacingPairInput& in);
std::uint64_t acos_units(double v);          // Spacing, Engine
```

  `validate::Component` gains `bool mirrored` (set by `build_components`; the C API `arc_component` is unchanged). `plan::Plan` gains `std::array<std::optional<validate::SpacingPair>, 2> spacing`; `plan::compile` calls `check_spacing` right after the table is built and before `final.required`, and returns its error as the compile error. `tools/check_engine_source.py` must keep passing (no transcendental call).

**Command-line renderer (`cli/report.{hpp,cpp}`, `cli/main.cpp`).**

- `struct SpacingEar { double min_distance_hz; double margin_hz; std::uint64_t component_1; std::uint64_t component_2; std::string pair; };` and `struct SpacingReport { std::optional<SpacingEar> left; std::optional<SpacingEar> right; };`; `Report` gains `std::optional<SpacingReport> spacing` after `loop`, set only when an ear has a pair. `report_json` writes it after `loop` and before `determinism_key`, exactly as in Spacing, Report (each ear one line, members `min_distance_hz`, `margin_hz`, `component_1`, `component_2`, `pair` in that order, `null` for an ear without a pair; numbers by `json_number` or the integer writer). `pair` is `<layer 1> (<i>, <j>, <b>) at <center 1> Hz and <layer 2> (<i>, <j>, <b>) at <center 2> Hz` from `arc_plan_component`, centers as shortest round-trip text.
- On a rejection the stderr line stays `rejected: parameter=... value=... rule=... limit=...`, and gains ` detail=<detail>` before the newline only when the detail is not empty, so every other rejection prints the same bytes. No WAV and no report are written.

**Tap dump (`tests/tapdump/main.cpp`).** New mode `arcani-tapdump RECIPE RATE OUT_DIR --spacing [--mute left|right]`: compiles, renders nothing, writes `OUT_DIR/spacing.tsv` with the header `ear<TAB>has_pair<TAB>min_distance_hz<TAB>margin_hz<TAB>component_1<TAB>component_2` and one line per ear (left, then right; `has_pair` 0 or 1; doubles `%.17g`; 0 fields without a pair), LF line ends, prints `arcani-tapdump: spacing`, exits 0. A rejected recipe prints the existing rejected line with ` detail=<detail>` appended when the detail is not empty, and exits 1 as today.

**Python reference (`reference/spacing.py`).** From the signal spec only (`tests/python/test_reference_independent.py` rules apply); binary64 with NumPy.

```python
class SpacingPair(NamedTuple):
    ear: str                 # "left" | "right"
    min_distance_hz: float
    margin_hz: float
    component_1: int         # table index, the smaller
    component_2: int
    where: str               # the where text with the reference's own numbers

class SpacingError(ValueError):
    parameter: str; value: str; rule: str; limit: str; detail: str   # rule "spacing_rule"

def spacing_margins(recipe: dict, mute: str = "none") -> dict[str, SpacingPair | None]: ...
def check_spacing(recipe: dict, mute: str = "none") -> None: ...        # raises SpacingError
def pair_form(c_hz, di, dj, db, gamma=(0.0, 0.0), theta=(0.0, 0.0), beat=(0.0, 0.0)) -> tuple:
    """(x, y, h, min_distance_hz, first) with each cycle as (swing_hz, start_phase_deg), period 60 s;
    first the cycle fraction of the first time, None without a sweep."""
```

  It holds `SPACING_HZ = 50.0  # row spacing-rule`, as `reference/components.py` holds `LEVEL_DB`, and a test cross-checks the constant against the row; its numbers in the detail are its own shortest round-trip floats.

**Suggested test files (the QA agent may split differently).** `tests/cpp/test_spacing.cpp` (every case of `kSpacingCases` compiled from its recipe text and from its fixture where it has one, at both rates and in both modes: rejected or not, the four error fields and the detail by its grammar; `arc_plan_spacing` against `kSpacingMargins` per ear, indices equal and the rows' layers and multipliers equal to `row_1` and `row_2`; `spacing_pair_form` and `acos_units` against `kSpacingPairs`; muted ears; C API argument errors; must-fails doctored in the harness, for example a component table with one row moved by 1e-9 Hz across the limit passed to `check_spacing`, and the exact 50 Hz case moved to 49.99 Hz), `tests/python/test_spacing_reference.py` (the reference against the vectors; fixture layer objects equal the case cells; the starter fixtures' values against `starter-recipes.md`), `tests/python/test_spacing_engine.py` (the tap dump's `spacing.tsv` and the CLI report's `spacing` block against the reference within the rows; a report of a recipe without a pair unchanged byte for byte; the must-fail fixture writes no WAV), plus the harness recipe moves of finding 3 and the expected-rejected fixture list in `test_validate.cpp`.

### Contract amendment (2026-11-17, orchestrator under Audio's delegation, on the QA finding)

`check_spacing` (engine) and `spacing_margins` (reference) return the per-ear margins for a rejected recipe too, with margins below 0, as Vectors: spacing margins show. A plan that compiled still has every margin at 0 or more.

### Engagement 3 (2026-11-17): implementation

- **Engine:** `engine/src/validate/spacing.{hpp,cpp}`: `check_spacing`, `spacing_pair_form`, `acos_units`, and `shortest_text` (the shortest digits of `json::format_number` rewritten in the `std::to_chars` form, fixed or scientific, whichever is shorter, ties to fixed; the engine library avoids floating-point `to_chars`, design log 2026-11-04 (ff)). Binary64 basic operations, `std::sqrt`, and `core::cycle_cosine` only, in the spec's order. `validate::Component::mirrored` set by `build_components` (`center - half < 0`). `plan::compile` runs the rule right after the table and before `final.required`; `plan::Plan::spacing` holds the margins.
- **Error and C API:** `recipe::Error::detail`; `arc_error::detail[ARC_ERROR_DETAIL_BYTES]` (512) after `limit`, written by every call through the same truncation rule (`write_field` is now a template on the field size); `arc_spacing` and `arc_plan_spacing` as contracted (bad ear: parameter `ear`, rule `argument.enum`, limit `0 (left) 1 (right)`).
- **CLI and tap dump:** `cli::SpacingEar`, `cli::SpacingReport`, `cli::spacing_report(plan)`, `Report::spacing` written after `loop`; the rejected line gains ` detail=<detail>` only when the detail is not empty. `arcani-tapdump --spacing [--mute left|right]` writes `spacing.tsv`; its rejected line gains the same suffix.
- **Reference:** `reference/spacing.py` from the spec only (NumPy `sin`, `cos`, `arctan2`, `arccos`, `sqrt`; the start phase cosine and sine exact at the quarter points; mirrored rows found from the unmirrored center less the row's own half width).
- **Records:** rows `spacing-rule` and `spacing-time-error` lose `pending`; `deferred-work.md` closes the margins, where-and-sweep-together, carrier rule wording, and Sleep 155 Hz rows; `starter-recipes.md` gives the 155 Hz bound and settles the Focus risk at 118 Hz; design log (ww) gains the implementation and results; sprint status `review`; guidebook.
- **Tests that fail for reasons in the tests (no expectation edited):**
  1. `tests/cpp/test_report.cpp:868` (`report_json writes the spacing block ...`, both ears): the expected text ends the right ear's object with `},` before `  },`, a trailing comma that makes the report invalid JSON. Spacing, Report and the one-ear case of the same test (`"right": null` with no comma) both put no comma after the last ear. The implementation writes `}` there.
  2. `tests/cpp/test_spacing.cpp:1161` (`the error and margin comparisons catch doctored texts and values`): the doctor `binaural (0, 0, 1) -> theta_reference (0, 0, 1)` reaches the harness's `carrier_field()`, whose `REQUIRE(layer == "binaural")` throws instead of adding a problem, so the must-fail check aborts. Engine-independent: the test builds the texts itself.
  3. `tests/python/test_spacing_engine.py::test_engine_spacing_mode_honors_the_muted_ear_and_refuses_bad_arguments`: it expects the right ear's `component_1` and `component_2` with the left ear muted to equal those without a muted ear. Muting the left ear removes the left binaural row, so every right-ear table index drops by one (4, 7 becomes 3, 6); the distances agree. Indices are positions in the whole table (Spacing, Table index), and the reference gives the same 3, 6.
- **Python harness recipes that collide (not moved by the tests-first commit, no expectation edited):** the rule now rejects, correctly, two recipes written inside Python tests that expect a compile:
  4. `tests/python/test_bursts_reference.py::test_engine_burst_timing_render`, the 8 cases with the smoothed on-off theta at 100 percent depth: theta line `(0, -15, 0)` at 360 Hz against the burst line `(1, 6, 0)` at 326 Hz, 34 Hz, in both ears.
  5. `tests/python/test_gamma_reference.py::test_engine_output_with_a_binaural_layer_matches_the_reference` (both rates): a 450 Hz theta reference beside a 400/406 Hz binaural pair, 38 Hz in the right ear (the same pair the tests-first commit moved to 100/106 Hz in the C++ tests).
  Both need their recipes moved to spacing-clean values by the QA agent, as finding 3 did for the C++ files.
- **Verification (dev PC):** `cmake --build --preset windows-clang-cl` clean (warnings as errors); `ctest --preset windows-clang-cl` 3 of 4 entries pass, `arcani_tests` 434 test cases, 432 pass, 2 fail (items 1 and 2), 4,661,829 of 4,661,832 assertions. Story Python files `test_spacing_reference.py` and `test_spacing_engine.py`: 272 passed, 1 failed (item 3); `test_reference_independent.py` passes with `reference/spacing.py`. Full `uv run pytest`: 3,547 passed, 2 skipped, 11 failed (37 min): item 3, and items 4 and 5 (10 cases). `check_engine_source.py`, `check_fp_pragmas.py`, `check_wording.py`, `check_table_log.py --base main`, `check_row_coverage.py`, and `signal_spec_vectors.py --check` exit 0.

- **Final verification (2026-11-17, dev PC, at 0fe945b):** `cmake --workflow --preset windows-clang-cl` exit 0, ctest 4 of 4 entries; full `uv run --locked pytest` 3,558 passed, 2 skipped (the pinned NDK cases), 0 failed (36 min); `check_engine_source`, `check_fp_pragmas`, `check_wording`, `check_row_coverage`, `check_table_log --base main`, and `signal_spec_vectors --check` exit 0.

## Spec Change Log

## Review Triage Log

Pass 1 (2026-11-17): blind hunter (BH), edge case hunter (EC), and verification gap (VG), each in a fresh context, on diff 12e3ad2..98faa46. The generated `signal_spec_vectors.json` and the guidebook were left out.

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | BH: implementation committed with 13 known failing tests; burst timing recipes untouched | medium | true at 98faa46; all five causes were in the tests | patch (done, QA tests-only commit 4c5c25b) |
| 2 | VG: the must-fail check of the error comparison aborts at its third doctored text, so the later doctors never run | medium | `carrier_field()` REQUIRE threw | patch (done, 4c5c25b: records a problem; every doctor runs) |
| 3 | VG: the muted-ear tap dump test fails before its usage-error and no-detail checks | medium | indices shift when a binaural row is muted | patch (done, 4c5c25b: indices compared to the muted reference table) |
| 4 | VG: the smoothed on-off burst timing renders at 100 percent are rejected at compile, so their timing and reference match never run | medium | theta line 360 Hz vs burst line 326 Hz | patch (done, 4c5c25b: timing theta carrier 500 Hz, closest now 84 Hz) |
| 5 | VG: report both-ears expectation has a trailing comma | low | invalid JSON in the test text | patch (done, 4c5c25b) |
| 6 | VG: the gamma reference test with a binaural layer is rejected at compile | medium | 450 Hz theta vs 406 Hz binaural, 38 Hz | patch (done, 4c5c25b: binaural 100/106 Hz, closest now 104 Hz) |
| 7 | BH, EC, VG: `cli::spacing_report` skips an ear on an API failure, so the report reads as "no pair" | low | true at `cli/report.cpp:136-148`; not reachable for a compiled plan and a valid ear, but it would hide an engine bug silently | patch (done, 0fe945b) |
| 8 | BH: design log (ww) says three tests failed and leaves out the two Python harness recipes | low | true; five findings, 13 cases | patch (done, 0fe945b) |
| 9 | BH: `arc_plan_spacing` header does not say indices are whole-table positions that shift with the muted ear | low | true; QA finding 3 tripped on exactly this | patch (done, 0fe945b) |
| 10 | BH: the ` detail=` stderr suffix is unquoted, so the line has no end marker for it | low | true; `detail=` is always last and runs to the end of the line, which is not written down | patch (done, 0fe945b: signal spec, Spacing, Error) |
| 11 | BH: no engine version or ABI change for the larger `arc_error` and the new rejections | false | accepted recipes render the same bytes (the rule reads the plan only); a rejected recipe has no output; no caller is built against the header before v0.1, and Story 3.1 grew the C API the same way | reject |
| 12 | BH: sessions shorter than one 60 s cycle are judged on the whole cycle; the first time can lie past `length_s` | medium | true by the frozen whole-cycle decision; no starter or fixture is that short | defer (Story 4.4 session lengths) |
| 13 | BH: the closed form assumes one cycle period without an assertion | false | row `rate-cycle-period` is locked at exactly 60 s and the parser rejects any other period; design log (ww) states the dependency | reject |
| 14 | BH: only the worst failing pair is reported | low | frozen decision; the fix edits the spec | reject |
| 15 | BH: the error parameter is the later layer's carrier, not every field that set the pair | low | frozen decision; the detail names both rows and their multipliers | reject |
| 16 | BH: the location of the minimum is given only in a rejection detail, not for a passing plan's worst pair | low | true; the closed deferred row asked only for the rejection report, which is done | defer (designer GUI) |
| 17 | BH: the pair text is built in the CLI, the engine, and the reference separately | false | the report block and the detail are both compared to the same vectors in `test_report.cpp`, `test_spacing.cpp`, and `test_spacing_engine.py`, so drift fails a test | reject |
| 18 | BH: 512-byte detail truncation never driven | low | the longest vector detail is far below 512 bytes; the template shares the truncation rule the 256-byte fields test | reject |

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
