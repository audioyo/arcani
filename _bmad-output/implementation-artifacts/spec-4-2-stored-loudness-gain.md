---
title: 'Story 4.2: Stored loudness gain'
type: 'feature'
created: '2026-11-21'
status: 'in-progress'
baseline_commit: 'af4f0977df830df0462d6a10dd25c3450e85c12e'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Every layer still plays at unit amplitude, so renders sit about 35 dB above the -36 LUFS-I target. The recipe fields `loudness_gain_db` and `loudness_hash` exist, but nothing writes them, `final` compile only checks that they are present, and no renderer applies the gain (AD-13).

**Approach:** Add a measure command to `arcani-render`: `arcani-render RECIPE --store-gain`. It compiles the recipe in `measure` mode, renders it, and measures loudness over the 4.1 window. It then rewrites only the two loudness members of the recipe file. `final` compile rejects a missing gain, an out-of-range gain, or a stale loudness hash. The engine and the Python reference apply the gain in the master chain in `final` mode only. In `final` mode, `--loudness` adds pass/fail loudness checks to the report. A CI check proves no recipe file changes during a run.

Decisions (planning, 2026-11-21, within AD-13; Audio can overrule any of them at approval):

1. **Loudness hash.** SHA-256 hex of the RFC 8785 canonical form of an object holding only the top-level members tagged `loudness-relevant` that are present: `length_s`, `loudness_target_lufs`, the layer objects, and `loop`. v0.1 has no assets. `schema_version`, `engine_version`, and `seed` stay out, as AD-13 and the schema tags say. An engine change that moves the level is caught instead by the final-mode loudness checks on every measured fixture in CI.
2. **Gain value.** `gain = target - L_window`, rounded half away from zero to 0.01 dB. It is stored as the integer `k = 100 * gain` written with exactly two decimals (for example `-35.27`). The rounding makes re-measuring byte-identical even though the meters call `tan` and `log10` (deferred finding 4.1 B9). The error is at most 0.005 LU against a 1 LU tolerance. Only the dev PC writes gains.
3. **Linear gain.** `g = c^|k|` by binary exponentiation in binary64, with `c = 10^(1/2000)` as a hex literal; for negative `k`, `g = 1 / c^|k|`. Engine and reference use the same operation order, so the gain is bit-exact on every platform with no new transcendental (AD-9).
4. **File rewrite.** Every byte outside the two members is kept. If a member exists, only its value text is replaced. If it is missing, it is inserted right after the `loudness_target_lufs` member, using that member's leading whitespace. The new bytes must compile in `final` mode before the file is replaced (temp file, then rename). If the rule fails, nothing is written.
5. **Allowed stored gain.** New range row `loudness-gain`: -60 dB to 0 dB (Audio, 2026-11-25). The stored gain can only turn the sound down; a recipe that would need a boost is refused. It is an engineering safety bound, not a research value.

## Boundaries & Constraints

**Always:** Meters and the file writer stay outside `engine/`, and the CLI never includes `engine/src`. The stored gain applies only in `final` mode, and `measure` renders stay byte-identical to today. Every new row gets a design-log line. Every check has a passing and a must-fail fixture, doctored in the harness. Tests that run `--store-gain` work on temp copies, never on the checkout. Tests go first, as a tests-only commit by a fresh-context QA agent.

**Never:** No true-peak check (4.3), ramps (4.4), or limiter work (4.5). No per-layer levels. No change to the recipe hash or its tags. Never write a gain during CI.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Store | a valid recipe 60 s or longer, no gain | the file gains both members, and the gain prints | exit 0 |
| Store twice | the stored file, measured again | same bytes | exit 0 |
| Short window | non-looping, under 60 s | nothing written | `loudness_window_rule`, exit 1 |
| Needed gain out of range | outside row `loudness-gain` | nothing written | rule `range.min`/`range.max` on `/loudness_gain_db`, exit 1 |
| Final, missing gain | no `loudness_gain_db` | rejected | `final.required` (unchanged) |
| Final, stale hash | a loudness-relevant field edited after storing | rejected | parameter `/loudness_hash`, value the stored hash, rule `final.loudness_hash`, limit `= <computed hash>` |
| Final, metadata edited | `author`, `date`, or `rationale` changed | compiles | N/A |
| Final render | stored recipe, `--mode final --loudness` | window within 1 LU (`loudness`); whole render at most target + 1 LU (`loudness_whole`) | exit 4 on fail |
| Final must-fail | stored gain plus 1.5 dB, in the harness | `loudness` fails | exit 4 |
| CI unchanged | a run ends with a recipe file modified or added | the check fails, naming the file | exit 1 |

</frozen-after-approval>

## Code Map

- `recipes/recipe.schema.json:58-72`, `recipes/README.md:36,52-93`: field tags. Update the README text that says `loudness_gain_db` has no range row (line 36). Document the hash, the rounding, and `--store-gain`.
- `engine/src/recipe/recipe.cpp:353-365,465`: `strip_hash_excluded`, recipe hash (`json::canonicalize`, `crypto::sha256_hex`). Add the loudness hash next to it, driven by the field-table tags (`field_table.cpp:22-25`, `field_table.hpp:22`). Remove the "Story 4.2 checks it" comment once the range check exists.
- `engine/src/validate/` + `tests/tables/ranges.tsv`: range check on `loudness_gain_db` with row `loudness-gain` (present in either mode).
- `engine/src/plan/plan.cpp:115-130`: add the hash match after `final.required`. `Plan` gets the computed loudness hash and `master_gain` (1.0 in `measure`).
- `engine/include/arcani/arcani.h`, `engine/src/api/api.cpp`: one accessor for the plan's loudness hash, written into a caller buffer of 65 chars, in the style of `arc_plan_loop`. Add matching `test_api_c.c` coverage.
- `engine/src/render/renderer.cpp:113`: `join * 1.0` becomes `join * master_gain`. `reference/stub_chain.py:32,119-127` gets the same change, taking mode and gain from the recipe.
- `docs/signal-spec.md:312,327,351` (Master chain, `g_c`): add the gain formula, the rounding rule, and `c` with its hex value, plus vectors from `tools/signal_spec_vectors.py`. Remove the "Story 4.2" notes at lines 4673 and 4681.
- `tools/recipe_hash.py` (`canonicalize` :368, `load_tags` :398, `_strip` :415): add `loudness_hash_value`, for Python cross-checks.
- `cli/main.cpp:107-179` (`parse_args`), `:230` (`write_text_file`), `:353-484` (loudness flow). `--store-gain` excludes `--out`, `--report`, `--preview`, `--mode`, and `--loudness`. New `cli/recipe_write.{hpp,cpp}` holds the top-level member scanner and the splice, run only on bytes the engine accepted. The gain text is built from the integer `k`.
- `cli/report.{hpp,cpp}`: final-mode loudness checks in the existing check shape (`json_number` :80-87).
- `recipes/fixtures/valid/*.json` (15 files with placeholder `6a29ccd6...83a6`): give each its real loudness hash. The `-changed` variants keep their own correct hash. The invalid fixtures and the C++ tests that reuse the placeholder are compiled in `measure` mode; leave them alone unless a test needs `final`.
- `.github/workflows/fast.yml`, `full.yml`: a last step in every job runs a new `tools/check_recipes_unchanged.py` (`git status --porcelain -- recipes`).
- `deferred-work.md:80,128-129`: both entries are resolved by this story.

## Tasks & Acceptance

**Execution:**
- [ ] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, `tests/tables/ranges.tsv`, `docs/design-log.md`, `recipes/README.md`: add the loudness hash, the gain rounding, `c^k`, row `loudness-gain`, design-log entries for the row and the rounding step, and vectors. The signal spec is the single formula source, merged before code.
- [ ] `tests/cpp/test_store_gain.cpp`, `tests/cpp/test_api.cpp`, `tests/cpp/test_cli.cpp`, `tests/python/test_store_gain.py`, `tests/python/test_recipes_unchanged.py`: failing tests from the matrix, as a tests-only commit (rule 6).
- [ ] engine (`recipe.cpp`, validate, `plan.cpp`, `renderer.cpp`, `arcani.h`, `api.cpp`) and `reference/stub_chain.py`: hash, range, final checks, and applied gain.
- [ ] `cli/recipe_write.{hpp,cpp}`, `cli/main.cpp`, `cli/report.{hpp,cpp}`, `cli/CMakeLists.txt`: `--store-gain` and the final-mode checks.
- [ ] `recipes/fixtures/valid/*.json`: real loudness hashes.
- [ ] `tools/check_recipes_unchanged.py`, `.github/workflows/*.yml`: the CI check, plus a pytest must-fail that runs it in a temp git repo with a modified recipe.

**Acceptance Criteria:**
- Given a final-mode render of a stored recipe, when the engine and the Python reference render it at 44.1 and 48 kHz, then they match below -100 dBFS, and the four-platform hash check covers it.
- Given any existing `measure` render, when it runs, then its WAV and report bytes do not change.
- Given the full suite, when it runs on the dev PC and in CI, then everything passes and `tools/check_row_coverage.py` sees `loudness-gain` in use.

## Design Notes

**Phased handoff.** As in Story 4.1, on branch `story/4-2-stored-loudness-gain`:
1. The implementation agent writes the spec section, vectors, row, and design log, and commits.
2. A fresh-context QA agent commits the failing tests.
3. The implementation agent implements, never editing a test expectation to make a test pass. No push.

Every test that stores a gain uses the 4.1 `loudness_constants.assertion_fixture` (60 s or longer) on a temp copy, plus one looping fixture. Keep added CI time to about 3 minutes of CPU per platform.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl`: expected build passes and ctest is green.
- `uv run --locked pytest -n auto`: expected all pass.
- `git status --porcelain -- recipes` after the suite: expected empty.
