---
title: 'Story 4.2: Stored loudness gain'
type: 'feature'
created: '2026-11-21'
status: 'done'
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
- [x] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, `tests/tables/ranges.tsv`, `docs/design-log.md`, `recipes/README.md`: add the loudness hash, the gain rounding, `c^k`, row `loudness-gain`, design-log entries for the row and the rounding step, and vectors. The signal spec is the single formula source, merged before code.
- [x] `tests/cpp/test_store_gain.cpp`, `tests/cpp/test_api.cpp`, `tests/cpp/test_cli.cpp`, `tests/python/test_store_gain.py`, `tests/python/test_recipes_unchanged.py`: failing tests from the matrix, as a tests-only commit (rule 6).
- [x] engine (`recipe.cpp`, validate, `plan.cpp`, `renderer.cpp`, `arcani.h`, `api.cpp`) and `reference/stub_chain.py`: hash, range, final checks, and applied gain.
- [x] `cli/recipe_write.{hpp,cpp}`, `cli/main.cpp`, `cli/report.{hpp,cpp}`, `cli/CMakeLists.txt`: `--store-gain` and the final-mode checks.
- [x] `recipes/fixtures/valid/*.json`: real loudness hashes.
- [x] `tools/check_recipes_unchanged.py`, `.github/workflows/*.yml`: the CI check, plus a pytest must-fail that runs it in a temp git repo with a modified recipe.

**Acceptance Criteria:**
- Given a final-mode render of a stored recipe, when the engine and the Python reference render it at 44.1 and 48 kHz, then they match below -100 dBFS, and the four-platform hash check covers it.
- Given any existing `measure` render, when it runs, then its WAV and report bytes do not change.
- Given the full suite, when it runs on the dev PC and in CI, then everything passes and `tools/check_row_coverage.py` sees `loudness-gain` in use.

## Implementation Notes

Everything below follows `docs/signal-spec.md`, Loudness gain, and its vectors (`tests/data/signal_spec_vectors.json`, keys `loudness_gain_constants`, `loudness_hashes`, `loudness_gain_steps`, `loudness_gain_values`, `loudness_rewrites`; C++ `kLoudnessGain_*`, `kLoudnessHashes`, `kLoudnessGainSteps`, `kLoudnessGainValues`, `kLoudnessRewrites` in the generated `spec_tables.hpp`). Vector constants are cross-checked against the rows, never used in their place. Row `loudness-gain` is in `tests/tables/ranges.tsv`, pending on this story; clear `pending` once a test reads it through `row()`.

**Engine.**

- `engine/src/recipe/field_table.cpp`: `/loudness_gain_db` names range row `loudness-gain` (scale 1.0); `engine/src/validate/validate.cpp` gains `{"loudness-gain", -60.0, 0.0, false, "dB"}` and a value lookup for the field (present only). The range check runs in both modes, in field table order. The engine range table test then expects 17 ids.
- `engine/src/recipe/recipe.cpp`: the loudness hash next to `strip_hash_excluded`: the root's members whose field table entry is top level and tagged `LoudnessRelevant`, then `json::canonicalize` and `crypto::sha256_hex`. The recipe hash is unchanged.
- `engine/src/plan/plan.cpp`: after the two `final.required` checks, `final.loudness_hash` (parameter `/loudness_hash`, value the stored hash, limit `"= " + H`). `Plan` gains `loudness_hash` (both modes) and `master_gain` (1.0 in measure mode; `g` by Linear gain in final mode).
- `engine/src/render/renderer.cpp`: `join * 1.0` becomes `join * plan.master_gain`.
- C API, in the style of `arc_plan_loop`:

```
/* Writes the plan's loudness hash (docs/signal-spec.md, Loudness gain): 64
   lowercase hex digits and a terminating NUL, into out_hash. Both modes.
   ARC_ERR_INVALID_ARGUMENT for a NULL plan or out_hash. */
arc_status arc_plan_loudness_hash(const arc_plan* plan, char out_hash[65], arc_error* error);
```

**Python.** `tools/recipe_hash.py` gains `loudness_hash_value(value, schema=None)` and `loudness_hash_bytes(data, schema=None)`, from `canonicalize`, `load_tags`, and the top-level `loudness-relevant` members, and a `--loudness` flag that prints the loudness hash instead of the recipe hash. `reference/stub_chain.py` takes the compile mode (`measure` default, `final`) and, in final mode, `loudness_gain_db` from the recipe, computes `k` and `g` by the spec steps in binary64, and multiplies the master by `g`.

**Command-line tooling, `cli/recipe_write.{hpp,cpp}`** in `arcani_cli_core`, namespace `arcani::cli` (no `engine/src` include):

```
struct Member { std::string name; std::size_t lead_begin, key_begin, key_end, value_begin, value_end; };  // byte offsets; name unescaped
std::vector<Member> top_level_members(std::string_view accepted_json);   // throws std::invalid_argument unless one JSON object
std::optional<double> top_level_number(std::string_view accepted_json, std::string_view name);  // std::from_chars of the value token
std::string rewrite_loudness_members(std::string_view accepted_json, std::string_view gain_text, std::string_view loudness_hash);
                                                                          // throws std::invalid_argument without loudness_target_lufs
std::string gain_text(std::int64_t k);                                    // "-35.27", "0.00"
struct GainStep { bool stored; std::int64_t k; std::string gain_text, value, rule, limit; };  // k 0 and texts empty when not applicable
GainStep gain_step(double window_lufs, double target_lufs, const arcani::test::tables::Row& gain_row);
                                                                          // throws TableError unless a ranges row in dB with finite bounds
```

`gain_step` limits come from the row's `min_text` and `max_text`: `>= -60 dB (row loudness-gain)`, `<= 0 dB (row loudness-gain)`. `arcani-render --store-gain` follows Loudness gain, Store, steps 1 to 9. The final-mode assertions `loudness` and `loudness_whole` go in `cli/report.{hpp,cpp}` (functions `loudness_assertion(row, window_lufs, target)` and `loudness_whole_assertion(row, whole_lufs, target)` returning `Assertion`), appended after render speed only in final mode with `--loudness`. Update the usage text, the `main.cpp` header comment, and the `CLAUDE.md` render command line.

**Test tools.** `arcani-tapdump` gains an optional `--final` argument (compile in final mode; every other mode unchanged), so the Python reference match can read a final-mode master. Hash probe components `stub-chain-final-44100` and `stub-chain-final-48000`: the final-mode render of `stub-chain-1s-beat-6.json` (scope `engine`); their `ci/hash_expected.json` entries wait for a green four-platform full run, as in earlier stories.

**CI check, `tools/check_recipes_unchanged.py`** (standard library only): runs `git status --porcelain --untracked-files=all -- recipes` in the repo (`--repo DIR`, default the repo root); exit 0 when empty; exit 1 with one line per modified, added, deleted, or untracked path, naming it; exit 2 on a git error. It is the last step of every job in `.github/workflows/fast.yml` and `full.yml`, after the tests.

**Test contracts (the QA agent may split differently; keep the added CI time to about 3 minutes of CPU per platform; every store works on a temp copy, never on the checkout; delete each large file as soon as it is read):**

- `tests/cpp/test_store_gain.cpp` (guarded by `__has_include("recipe_write.hpp")`): `gain_step` against every `kLoudnessGainSteps` row with the real `loudness-gain` row, and a doctored row with unit `LU` throws; `gain_text` against every `kLoudnessGainValues` row whose `two_decimals` is true; `rewrite_loudness_members` against every `kLoudnessRewrites` row (output bytes exact, the output rewritten again unchanged); each output compiles in final mode through `arc_compile`, and `arc_plan_loudness_hash` on the input equals the row's hash; `top_level_members` finds the escaped names of the `escaped member names` case; `top_level_number` reads `loudness_target_lufs` as -36. Must-fails doctored here: a tie rounded toward zero gives a different `k`; an output with one byte changed differs.
- `tests/cpp/test_api.cpp`: `arc_plan_loudness_hash` equals `kLoudnessHashes` for every listed fixture the engine accepts in measure mode, at both rates; NULL plan or buffer gives `ARC_ERR_INVALID_ARGUMENT`. Final mode: every listed fixture compiles except `both-layers-loudness-target-changed.json` (range) and `stub-chain-1s-no-gain.json` (`final.required`); a harness copy with the old placeholder hash is rejected with parameter `/loudness_hash`, value the placeholder, rule `final.loudness_hash`, limit `= ` plus the vector hash; a harness copy with `length_s` changed is stale; copies with `author`, `date`, or `rationale` changed compile. Range in both modes: `-60.01` fails `range.min` and `0.01` fails `range.max` with the vector limits, `-60` and `0` compile. Applied gain on `stub-chain-1s-beat-6.json` with all taps at both rates: final-mode master equals join times the `-1.5` row's `g` bit for bit, the theta, gamma, bus, and join taps equal measure mode's, and with the stored gain `0.00` or `-0.00` the final output equals the measure output bit for bit. Add the accessor to `test_api_c.c`.
- `tests/cpp/test_cli.cpp`: `--store-gain` with each excluded option, and twice, exits 2 and leaves the file's bytes unchanged; a temp copy of `theta-sine-6hz.json` exits 1 with the `loudness_window_rule` line, unchanged; a temp copy of a recipe with no layers and a 60 s session (made in the harness) exits 1 with `value=inf rule=range.max`, unchanged. On temp copies of both store fixtures at 48 kHz: exit 0, the stdout line, every byte outside the two members unchanged, the gain text two decimals, the hash equal to the `kLoudnessHashes` row; a second store gives the same bytes. Final render of each stored copy with `--mode final --loudness` at 48 kHz (and the non-looping one at 44.1 kHz too): exit 0, `loudness` and `loudness_whole` pass; the must-fail copy (gain `+1.5` dB, `k + 150`) exits 4 with `loudness` failing; a stored copy with `length_s` edited exits 1 with the `final.loudness_hash` line. The measure-mode `--loudness` report has no loudness assertion.
- `tests/python/test_store_gain.py`: `loudness_hash_value` against every `loudness_hashes` row, and the same and different relations among the `both-layers` variants; `reference/stub_chain.py` in final mode on `stub-chain-1s-beat-6.json` against the engine (`arcani-tapdump --final`) at both rates, every compared signal below `reference-match`; its `g` equals the stored gain vectors bit for bit; the Python meter on a final-mode render of a stored temp copy reads within `loudness-tolerance` of the target; the rows `loudness-gain` and the vector bounds agree.
- `tests/python/test_recipes_unchanged.py`: in a temp git repo, a clean tree exits 0; a modified recipe, an added (untracked) recipe, and a deleted recipe each exit 1 naming the path; a change outside `recipes/` exits 0; a must-fail CI step that writes a gain into a recipe in that repo is caught.

## Spec Change Log

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

## Review Triage Log

Pass 1 (2026-11-25): blind-hunter (B), edge-case-hunter (E), verification-gap (V).

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| B1 | No CI test catches an engine change that moves the level | high | Every final-mode loudness test first runs `--store-gain` with the current engine on a temp copy; no committed recipe holds a measured gain, so a level shift is re-measured and passes. Contradicts intent decision 1. Root cause is a missing fixture and test, not code: the implementation would re-derive identically, so patch instead of a revert loopback. | patch |
| B2/E10 | Stored gain depends on `--rate`, and the hash does not record the rate | low | Real: storing at 44.1 kHz then 48 kHz can differ by one 0.01 dB step. Error is far inside the 1 LU tolerance; the default rate is 48000; a fix adds a rule or removes a spec'd option. | reject |
| B3 | The final report does not echo the applied gain or the loudness hash | low | Real, but the gain is in the recipe file, so same file + engine + seed still gives the same bytes (rule 1). The fix adds report members (new surface). | reject |
| B4 | The schema lacks the -60 to 0 bounds | low | Bounds are not schema-borne by convention (2 min/max in the whole schema; ranges live in `ranges.tsv`). Its description "written by the measure pass" is stale: a direct text correction. | patch (description only) |
| B5 | CLAUDE.md not updated | false | Fixed in e4113d3 at Audio's request. | reject |
| B6 | CI step position worded two ways; step duplicated across 12 jobs | low | The fix to the wording edits the spec; the duplication follows the existing wall-time step pattern. | reject |
| B7/E6 | `check_recipes_unchanged.py` misses gitignored, quoted, renamed, or restored paths | low | No current test writes such paths; the fix adds parsing complexity. | reject |
| B8a/E2 | `run_store` step 7 prints a `rejected:` line for non-REJECTED statuses | low | Real at `cli/main.cpp` step 7; direct correction. Exit 3 for a real rejection matches the signal spec, step 7. | patch |
| B8b/E4 | `.partial` overwrite, symlink, OneDrive rename retry, untested cleanup | low | Same `.partial` pattern as the WAV writer; rare; the fixes add guards. | reject |
| B9/V2 | Branch committed with 3 failing tests (missing `stub-chain-final-*` pins) | medium | Real. Precedent (`ci/hash_expected.json` source, theta-envelopes): missing entries stop the desktop probes running in the full run, so pin the windows-x64 dev PC values now and confirm on all four platforms in CI. | patch |
| B10 | Status fields disagree | false | In-flight states during review; sprint status moves at step 5. | reject |
| B11 | A recipe 0.005 LU too quiet cannot be stored | false | Intent decision 5 (Audio): a recipe that needs a boost is refused. | reject |
| B12/E7 | Python reference does not range-check or hash-check in final mode; C++ store tests hard-code the -36 target | low | The engine is the checker; the reference only renders accepted recipes. Every store fixture targets -36. | reject |
| E1 | An out-of-range stored gain blocks a re-store | low | Only reachable by hand-editing; the range check in both modes is the spec'd contract. | reject |
| E3 | A huge finite `x` shows the value in steps, not dB | false | Needs a window reading near 4.6e16 dB; unreachable from a finite meter. | reject |
| E5 | `if: always()` step fails noisily when uv setup never ran | low | Same pattern as the existing wall-time step. | reject |
| E8 | Test helper key search is fragile | low | Test-only; current fixtures do not trigger it. | reject |
| E9 | Rounding near a half step could differ between platforms | false | Only the dev PC stores gains (intent decision 2), so cross-platform storing is never needed. | reject |
| E11 | Positive gains are now rejected in measure mode | false | The range check in both modes is the spec'd contract; Audio confirmed the fixture edit. | reject |
| V1 | First-failure order of the `loudness_gain_db` range check is not pinned | medium | Pre-verified gap: no order case combines an out-of-range gain with another range fault. | patch |
