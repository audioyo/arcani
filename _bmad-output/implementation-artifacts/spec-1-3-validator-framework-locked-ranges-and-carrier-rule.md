---
title: 'Story 1.3: Validator framework, locked ranges, and carrier rule'
type: 'feature'
created: '2026-11-05'
status: 'in-progress'
baseline_commit: '655584b87e38e8d6eccc1f84388ef9f4b1badff5'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** `arc_compile` accepts any number the schema types allow: a 5000 Hz binaural carrier, a negative length, or a carrier under 4 times its modulation rate all become plans. Each later layer needs a ready place to register its fields against the locked-range table.

**Approach:** Add an engine validator that runs after parse in both modes. Every numeric recipe field is registered in the field table with its range row ID (or an explicit, reasoned exemption). The validator checks each present field against an engine-owned copy of its range row and exposes a carrier-rule check for a carrier and a rate interval. Tests prove the engine copy equals `tests/tables/ranges.tsv`.

Decisions (2026-11-05, build agent, under Audio's standing "settle tech forks yourselves" preference):
- Registration: `Field` gains `range_row` (row ID, empty when not range-governed) and `range_scale` (row unit to field unit: 1, or 3600 for `h` to `_s`). Mapping: `/length_s` to `session-length` (8 h = 28800 s), `/loudness_target_lufs` to `loudness-tones`, `/theta_reference/carrier_hz` to `theta-carrier`, `/binaural/carrier_left_hz` to `binaural-carrier`, `/binaural/beat_rate_hz` to `beat-rate`, plus the derived right carrier (`carrier_left_hz + beat_rate_hz`) to `binaural-carrier-right`, reported on `/binaural/beat_rate_hz`. `/loudness_gain_db` is exempt (written by the measure pass, not authored; Story 4.2 checks it). `/seed` is schema-bounded.
- `loudness_target_lufs` maps to `loudness-tones` (-36 LUFS-I, fixed) because every v0.1 starter targets -36 LUFS-I (design log 2026-10-27 (m), NFR15). Any other target is rejected. Every fixture at -16 moves to -36; `both-layers-loudness-target-changed.json` moves to -36.5 (a hash fixture, schema-valid but out of range). Hash vectors are regenerated.
- Engine range copy: a hand-written constexpr table in `engine/src/validate/`, one entry per row the field table names (id, min, max, max bound), the same pattern as the 1.1 field table against the schema. The engine reads no file.
- Bounds: `min` is always inclusive; `max` per `max_bound`. Comparison is on binary64 against `bound * range_scale`, which is exact for every v0.1 row.
- Check order in compile: input cap, sample rate, parse, ranges (field table order, derived right carrier after beat rate), `final.required`. First failure wins.
- Errors: rule `range.min` or `range.max`. Value: `json::format_number` of the field value. Limit names the bound in field units and the row, for example `>= 100 Hz (row theta-carrier)`, `< 1000 Hz (row binaural-carrier)`, `<= 28800 s (row session-length)`.
- Carrier rule: `check_carrier_rule(parameter, carrier_hz, rate_min_hz, rate_max_hz)` passes when `carrier_hz >= 4 * rate_max_hz` (4 from engine constant `kCarrierRatio`, tested equal to threshold row `carrier-rule`). Failure: rule `carrier_rule`, value the carrier, limit `>= 24 Hz (4 x 6 Hz, row carrier-rule)`. No v0.1 recipe field pairs a carrier with a rate yet, so compile has no caller until Epic 2; it is unit-tested through an internal header.
- Range fixtures are generated inside the C++ tests from one base recipe with substituted values (shortest round-trip text), not stored as files.
- `loudness-master` (-16 LUFS-I) is removed from `ranges.tsv` for v0.1 (Audio, 2026-11-05), with a design log line naming it. It returns in Phase 1 with the master level and voice. Any test or loader expectation that lists it is updated.

## Boundaries & Constraints

**Always:**
- Thresholds and ranges come from the tables; never edit a row value. Clear the `pending` field of `loudness-tones` only.
- Tests first, by a fresh-context QA agent, committed tests-only and failing. Every check has a passing and a must-fail case.
- Engine stays C++20 standard library only. All existing checks keep passing: symbols, flags, pragmas, wording, table log, row coverage, determinism of hashes.
- API tests include only `arcani/arcani.h`. New internal-header tests are limited to the validator header and the field table.

**Never:**
- The spacing rule (Epic 3), the CLI (1.4), loudness gain matching (4.2), new recipe fields, or real layer signals.
- Range checks in the JSON Schema (it holds structure and types only).
- Pushing or opening the pull request without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| In range | every valid stub-chain fixture, both modes | plan | N/A |
| Inclusive bound | theta carrier 100 and 500; length 28800 s; beat 0; target -36 | plan | N/A |
| Just outside inclusive | theta carrier next double below 100 or above 500; length above 28800; target -35.999... or -36.000...1 | no plan, `ARC_ERR_REJECTED` | parameter pointer, value text, `range.min` or `range.max`, limit with row ID |
| Exclusive bound | left carrier 1000; beat 30 | no plan | `range.max`, `< 1000 Hz (row binaural-carrier)`, `< 30 Hz (row beat-rate)` |
| Just inside exclusive | left carrier and beat at the next double below the bound | plan, unless the derived right carrier reaches 1030 | `range.max` on `/binaural/beat_rate_hz`, row `binaural-carrier-right` |
| Negative | length -1; carrier -0.5 | no plan | `range.min` |
| Carrier rule | 24 Hz at rate 6; next double below 24; interval 1 to 7 with carrier 24 | pass; fail; fail | `carrier_rule`, limit names 4 x the interval max |

</frozen-after-approval>

## Code Map

- `engine/src/recipe/field_table.{hpp,cpp}` -- add `range_row` and `range_scale` to `Field`; fill per the decisions. Keep schema order.
- `engine/src/validate/validate.{hpp,cpp}` (new) -- engine range table (`RangeRow {id, min, max, max_exclusive}`, `range_rows()`), `check_ranges(const recipe::Recipe&) -> std::optional<recipe::Error>`, `check_carrier_rule(...)`, `kCarrierRatio`.
- `engine/src/plan/plan.cpp:41-58` -- call `check_ranges` after parse, before `final.required`.
- `engine/src/json/number.hpp` -- reuse `format_number` for value and limit text.
- `engine/CMakeLists.txt` -- add the new sources.
- `tests/cpp/test_recipe.cpp` -- existing field-table vs schema test; extend: every `Number` field names a row or is in the exemption list; every named row exists, is a range row, has a unit consistent with the field suffix and scale, and is not pending.
- `tests/cpp/test_validate.cpp` (new) -- engine range table equals `ranges.tsv` (via `tests/assertions/tables.hpp` `row()`, which records usage), boundary matrix through `arc_compile`, carrier-rule unit tests, `kCarrierRatio` equals row `carrier-rule`. `tests/cpp/api_helpers.hpp` has compile helpers to reuse.
- `tests/cpp/CMakeLists.txt` -- add the test file.
- `recipes/fixtures/valid/*.json` -- loudness target -16 to -36 (-36.5 for the target-changed fixture); then `tools/recipe_hash.py --write-vectors`. Check `tests/hashprobe` embedded recipe literals for -16 too.
- `tests/tables/ranges.tsv` -- clear `pending` on `loudness-tones`; remove `loudness-master`. Grep `tests/` and `tools/` for `loudness-master` (for example `tests/python/test_tables_loader.py`).
- `recipes/README.md`, `recipes/recipe.schema.json` descriptions -- state that `valid/` means schema-valid and that locked ranges are checked at compile.

## Tasks & Acceptance

**Execution:**
- [ ] `tests/cpp/test_validate.cpp`, `tests/cpp/test_recipe.cpp`, `tests/cpp/CMakeLists.txt`, fixtures and hash vectors -- QA agent writes the failing tests -- tests first.
- [ ] `engine/src/recipe/field_table.*`, `engine/src/validate/*`, `engine/src/plan/plan.cpp`, `engine/CMakeLists.txt` -- registry, validator, compile call.
- [ ] `tests/tables/ranges.tsv`, `recipes/README.md`, schema description -- table and docs.
- [ ] `docs/design-log.md` entry (hh) (field-to-row mapping, loudness target -36, error format, check order, loudness-master outcome), `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given the field table, when the registration test runs, then it fails for any `Number` field with no range row and no exemption, and for a row ID that is missing, pending, or has a mismatched unit. A must-fail case (a doctored field list) is caught.
- Given the engine range table, when compared with `ranges.tsv`, then every entry's min, max, and bound match its row exactly.
- Given any value in the matrix that fails, when compiled in `measure` and in `final` mode, then status is `ARC_ERR_REJECTED`, the plan handle is NULL, and all four error fields match the matrix.
- Given the carrier rule check, then exactly 4 times passes, the next double below fails, and an interval whose minimum passes but maximum fails is rejected.
- Given every valid stub-chain fixture, when compiled, then it still compiles, and the 1.2 isolation, seek, and stage tests stay green.

## Implementation Notes

QA agent, tests-first pass (2026-11-05). Execution task 1 only; nothing under `engine/` is written. Settled test-side choices the implementation must follow:

- **Field table** (`recipe/field_table.hpp`, checked in `tests/cpp/test_recipe.cpp`, case "every numeric field names a locked-range row or a reasoned exemption"): `Field` gains `std::string_view range_row` ("" when not range-governed) and `double range_scale`, both assignable (the doctored cases copy the table into a `std::vector<Field>` and edit it). The test detects the members with a concept, so the suite builds before they exist. Rule applies to `Number` and `Integer` fields. Exemption list lives in the test: `/seed` (schema-bounded integer) and `/loudness_gain_db` (measure pass, Story 4.2); an exempt field must name no row, a non-numeric field must name no row. Expected mapping exactly as the decisions: `/length_s` session-length 3600, `/loudness_target_lufs` loudness-tones 1, `/theta_reference/carrier_hz` theta-carrier 1, `/binaural/carrier_left_hz` binaural-carrier 1, `/binaural/beat_rate_hz` beat-rate 1; every other field has an empty `range_row` (its scale is not checked). Unit fit by suffix: `_hz` Hz x1; `_s` s x1, min x60, h x3600; `_lufs` LUFS-I x1; `_deg` degrees x1; `_db` dB x1. Rows are read with `load_tables` (no usage recorded). Must-fail cases: cleared row, missing id, threshold row (`carrier-rule`), pending row (doctored table), wrong unit, right unit at wrong scale, exempt field with a row, non-numeric field with a row.
- **Validator header** `engine/src/validate/validate.hpp`, namespace `arcani::validate` (contract in the comment block of `tests/cpp/test_validate.cpp`): `struct RangeRow { std::string_view id; double min; double max; bool max_exclusive; }` in row units (session-length 0 to 8 h), aggregate-initialisable as `{id, min, max, max_exclusive}`; `std::span<const RangeRow> range_rows() noexcept` holds exactly the rows the field table names plus `binaural-carrier-right` (6 entries, no duplicates); `std::optional<recipe::Error> check_ranges(const recipe::Recipe&)` (not called by the tests directly); `inline constexpr double kCarrierRatio`; `std::optional<recipe::Error> check_carrier_rule(std::string_view parameter, double carrier_hz, double rate_min_hz, double rate_max_hz)`. The validator header may include `recipe/recipe.hpp` for `Error`. The test file also includes `recipe/field_table.hpp`, `tables.hpp`, and `api_helpers.hpp`; it compiles to one failing case until the header exists.
- **Engine table compare** goes through `tables::row()` (records usage of all six rows and of threshold row `carrier-rule`). Exact `==` on min and max, `max_exclusive == (max_bound == "exclusive")`. Must-fail: min one ulp off, max one ulp off, bound flipped, entry missing, unknown id.
- **Error text fixed by the tests:** value is the shortest round-trip text of the field value (`json::format_number`). Limit `"<op> <bound * range_scale> <unit> (row <id>)"`, op `>=` (min), `<=` (inclusive max), `<` (exclusive max); unit `s` for `/length_s`, else the row unit: `>= 100 Hz (row theta-carrier)`, `<= 28800 s (row session-length)`, `>= 0 s (row session-length)`, `<= -36 LUFS-I (row loudness-tones)`, `< 1000 Hz (row binaural-carrier)`, `< 30 Hz (row beat-rate)`, `>= 0 Hz (row beat-rate)`. Carrier rule: rule `carrier_rule`, limit `>= 24 Hz (4 x 6 Hz, row carrier-rule)` and `>= 28 Hz (4 x 7 Hz, row carrier-rule)` (all three numbers via `format_number`).
- **Matrix recipes** are built in the test from one base (1 s, -36 LUFS-I, theta 300 Hz, left 400 Hz, beat 6 Hz, gain and hash present) with value text written by hand from Python `repr` and proved by `strtod` against `std::nextafter`. Run at 48 kHz in both modes. Extra cases beyond the matrix: left carrier 0 and length 0 pass (inclusive minimums); beat -0.5 rejected; `both-layers-loudness-target-changed.json` (-36.5) rejected with `range.min` in both modes; every other valid fixture compiles in measure mode.
- **Check order tests:** several bad fields at once report the first in field-table order; a range fault beats `final.required`; sample rate and a parse fault (`/seed` as string, rule `type`) beat ranges.
- **Fixtures and vectors:** `loudness_target_lufs` -16 to -36 in all 77 fixtures, valid and invalid (same byte length, so `invalid-expected.json` offsets hold); `both-layers-loudness-target-changed.json` -16.5 to -36.5; `both-layers-reformatted.json` -16.0 to -36.0. `tools/recipe_hash.py --write-vectors` rewrote `tests/data/recipe_hash_vectors.json`. Hand-written canonical text in `tests/cpp/test_recipe.cpp` and `tests/python/test_recipe_hash.py` moved to -36, hex now `097f8d91f1ca50830fc9d48b4c967a26d810890fc2dfd70a2303a03fe09ee80a` (hashlib of the literal); the parse test expects -36.0. `tests/hashprobe/main.cpp` stub-chain literal moved to -36 (its samples do not depend on the target). No test or loader lists `loudness-master`, so its removal needs no test edit.
- **Open points for the implementer:** (1) the derived `binaural-carrier-right` check cannot fail through `arc_compile`: with left < 1000 and beat < 30 the binary64 sum stays below 1030 (left 999.9999999999999 + beat 29.999999999999996 = 1029.9999999999998), so only its passing side is tested, plus a `CHECK` that this sum is below 1030. (2) Threshold row `carrier-rule` is still pending on this story; once the test reads it through `row()`, `check_row_coverage.py` flags it as used while pending, so Task 3 must clear that `pending` too, although the Boundaries name only `loudness-tones`.
- **Red state at hand-off:** clean `windows-clang-cl` workflow builds; `arcani_tests` 105 cases, 2 fail ("recipe::Field has no range_row and range_scale", "not implemented: validate/validate.hpp"); the other three ctest entries pass. `uv run pytest` 1,095 passed, 2 NDK-only skips. Wording, pragma, row coverage, and table log checks exit 0. A throwaway implementation in a copy outside the repo (registration, validator, compile call, `ranges.tsv` edits) passed every C++ test; five planted bugs were each caught: exclusive max treated as inclusive, carrier rule against the interval minimum, an engine table min off, `/length_s` unscaled, ranges checked after `final.required`; leaving `loudness-tones` pending failed the registration case.

## Spec Change Log

## Review Triage Log

## Design Notes

The derived right carrier needs no new recipe field: it is `carrier_left_hz + beat_rate_hz`, computed in binary64 as compile already does, so the row check sees the exact frequency the binaural stub plays.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: build passes and every ctest passes.
- `uv run pytest` -- expected: all pass.
- `uv run --no-project python tools/check_wording.py`, `tools/check_fp_pragmas.py`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main` -- expected: exit 0.
