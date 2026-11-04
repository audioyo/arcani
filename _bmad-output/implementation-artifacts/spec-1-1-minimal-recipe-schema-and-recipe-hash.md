---
title: 'Story 1.1: minimal recipe schema and recipe hash'
type: 'feature'
created: '2026-11-04'
status: 'done'
baseline_commit: '5ccdf78b86f8722133d33ccb86a4a67d9ec4cb93'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** There is no recipe format yet. Nothing defines which fields a recipe has, rejects a malformed or unsupported one, or gives a recipe a stable fingerprint, so tools cannot agree on what a recipe means or detect a change to its sound.

**Approach:** Add a JSON Schema for the minimal recipe in `recipes/`, an engine-owned strict JSON parser and recipe parse stage in `engine/`, and a recipe hash (SHA-256 over RFC 8785 canonical JSON minus hash-excluded fields) implemented twice: in the engine and, independently, in Python. Shared fixtures prove the schema and the engine accept and reject the same recipes, and that both hashes agree.

Decisions (2026-11-04, build agent, under Audio's standing "settle tech forks yourselves" preference; Audio approved proceeding on 2026-11-04, kept as one story at about 2,500 tokens, fresh-context agents allowed for this run):
- Minimal fields: `schema_version` ("MAJOR.MINOR", supported major 1), `engine_version` ("X.Y.Z"), `seed` (integer 0 to 2^53-1, the largest exactly representable JSON number), `author`, `date` ("YYYY-MM-DD"), `rationale`, `length_s`, `loudness_target_lufs`, optional `loudness_gain_db` and `loudness_hash` (64 lowercase hex). Stub chain: optional `theta_reference` {`carrier_hz`} and optional `binaural` {`carrier_left_hz`, `beat_rate_hz`}. Layers are fixed top-level keys, never an array.
- Tags (custom keyword `x-arcani-tag` on every property): `hash-excluded` = `author`, `date`, `rationale`, `loudness_gain_db`, `loudness_hash`; `loudness-relevant` = `length_s`, `loudness_target_lufs`, every layer field; `none` = `schema_version`, `engine_version`, `seed`. `engine_version` stays in the hash.
- The schema holds structure and types only, never locked-range numbers (one source: `tests/tables/ranges.tsv`, enforced by Story 1.3's validator after parse). The consistency test compares the schema with the engine parse stage.
- The engine does its own decimal-to-binary64 parsing and shortest round-trip formatting (exact big-integer arithmetic), not `std::from_chars`/`std::to_chars`, whose floating-point overloads are missing from the pinned Apple libc++.
- Python validates with the `jsonschema` package, added as a pinned dev dependency (test only, free), logged in the design log and the spine Stack table.

## Boundaries & Constraints

**Always:**
- Strict parser (RFC 8259 plus I-JSON): reject comments, trailing commas, leading zeros, NaN or Infinity literals, numbers that overflow binary64, duplicate keys, invalid UTF-8, lone surrogate escapes, a byte order mark, and nesting deeper than a fixed limit. Python's fixture loader applies the same rules (`object_pairs_hook`, `parse_constant`, UTF-8 decode check) before schema validation.
- Every parse error carries parameter (JSON Pointer to the field, or byte offset for syntax), value, rule, and limit. Unsupported schema major: parameter `schema_version`, the value, rule `schema_version.major`, limit = supported majors.
- RFC 8785: keys sorted by UTF-16 code units, ECMAScript number serialization, the RFC's string escaping. Canonicalizer is generic JSON, not recipe-specific.
- Engine stays C++20 standard library only, no exceptions crossing any future C API boundary, no file I/O in `engine/` (tests read files and pass bytes). All existing checks (symbol denylist, flags, pragmas, wording) keep passing.
- Tests first by a fresh-context QA agent, committed tests-only and failing before implementation. Every check has passing and must-fail fixtures. Recipe fixtures pass the wording check.

**Never:**
- A C API entry point (Story 1.2), locked-range or carrier checks (Story 1.3), report or determinism key output (Stories 1.4, 1.6), rate curves, looping, or describe-the-sound fields (Epics 2, 6).
- Routing, coupling-target, or any field outside the decided list. Threshold or range table edits.
- Pushing or opening the pull request without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid minimal | all required fields, both layers or none | schema and engine accept | N/A |
| Unknown field | `routing` or `coupling_target`, top level or in a layer | both reject | rule names unknown property |
| Missing or mistyped | required field absent, string where number expected | both reject | parameter names the field |
| Unsupported major | `schema_version` "2.0" | engine rejects | `schema_version`, "2.0", rule, limit "1" |
| Bad syntax | duplicate key, trailing comma, NaN, bad UTF-8 | both reject | rule names the syntax fault |
| Integer form | `seed` 7.0 | both accept; canonical form `7` | N/A |
| Pattern trap | `schema_version` "1.0\n" | both reject | Python `$` matches before a final newline; the pattern must not |
| Reformatted | same recipe, keys reordered, whitespace, `1.0` vs `1e0` | same hash | N/A |
| Metadata edit | `author`, `date`, `rationale`, gain, loudness hash changed | same hash | N/A |
| Audio edit | any other field changed | different hash | N/A |

</frozen-after-approval>

## Code Map

- `recipes/recipe.schema.json` -- new, JSON Schema draft 2020-12, `additionalProperties: false` at every object. `recipes/README.md` -- field list, tags, versioning.
- `recipes/fixtures/valid/*.json`, `recipes/fixtures/invalid/*.json` -- shared fixtures; the folder is the expected verdict.
- `engine/src/json/` -- new: strict parser into a value tree (numbers as binary64 plus integral flag), number text conversion, RFC 8785 canonicalizer. `engine/src/recipe/` -- field table (path, type, tag), parse stage returning recipe or structured error, recipe hash. `engine/src/crypto/sha256.*` -- new.
- `engine/CMakeLists.txt:10-13` -- add the new sources. Do not touch the nm or check-file logic below.
- `tests/cpp/CMakeLists.txt:13-18` -- add test files; pass `ARCANI_RECIPES_DIR` and the data dir as definitions (pattern at line 25).
- `tests/data/rfc8785_vectors.json` -- new: the RFC's examples (key sorting with non-BMP keys, number serialization table, escaping). `tests/data/sha256_vectors.json` -- FIPS 180-4 examples. `tests/data/recipe_hash_vectors.json` -- fixture name to expected hash, written by the Python tool, checked by both sides.
- `tools/recipe_hash.py` -- new, stdlib only: strict load, canonicalize, read tags from the schema, hash; `--write-vectors` refreshes the vectors file.
- `tests/python/` -- new tests for schema, tags, consistency, canonicalizer, hash; `pyproject.toml`, `uv.lock` -- add `jsonschema` to the dev group, exact pin.
- `tests/assertions/tables.*` -- reuse nothing; Story 1.1 adds no table rows.
- `docs/design-log.md` -- entry (ff): field list and tags, seed bound, number conversion choice, `jsonschema` pin. Spine Stack table gains the `jsonschema` row.

## Tasks & Acceptance

**Execution:**
- [x] `tests/python/test_recipe_*.py`, `tests/cpp/test_json.cpp`, `test_recipe.cpp`, `test_sha256.cpp`, fixtures and vector files -- QA agent writes failing tests from the ACs and matrix; tests-only commit -- tests first.
- [x] `recipes/recipe.schema.json`, `recipes/README.md` -- schema with tags.
- [x] `engine/src/json/*`, `engine/src/crypto/sha256.*`, `engine/src/recipe/*`, `engine/CMakeLists.txt` -- parser, canonicalizer, SHA-256, parse stage, hash.
- [x] `tools/recipe_hash.py`, `pyproject.toml`, `uv.lock` -- Python hash and dependency.
- [x] `docs/design-log.md`, spine Stack table, `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given the schema, when a test walks every property, then each is `snake_case` with a unit suffix where it holds a quantity, and carries exactly one valid `x-arcani-tag`.
- Given the engine field table, when a C++ test parses the schema file with the engine parser, then paths, types, and tags match it exactly.
- Given every fixture, when Python (strict load plus `jsonschema`) and the engine parse stage judge it, then each verdict matches the fixture's folder.
- Given the RFC 8785 and SHA-256 vectors, when engine and Python run them, then every output matches.
- Given every valid fixture, when engine and Python hash it, then both equal `tests/data/recipe_hash_vectors.json`, and the Python test confirms the file is current.
- Given number conversion, when the engine formats 10,000 seeded binary64 values plus edge values (subnormals, max, 1e21, 1e-7, -0), then output equals Python's ECMAScript formatting and parses back to the same bits.

## Implementation Notes

- Failing tests 06ba1f0 (fresh-context QA agent). Settled in the tests: error rule names (`unknown_property`, `json.duplicate_key`, `json.trailing_comma`, and the rest in `recipes/fixtures/invalid-expected.json`), shared by the engine and the Python strict loader; a syntax error's parameter is its byte offset as digits; the schema pattern itself rejects a major other than 1, so `schema_version` "2.0" is invalid for both sides; layer fields are required inside their layer; bad UTF-8 cases are built inside the tests, not stored as fixture files (the wording check fails non-UTF-8 files). Extra data file `tests/data/number_format_vectors.json` holds the 10,000 seeded values plus edges.

- Implementation 3a023ea. Engine choices within the spec: strict parser depth limit 64; extra rule ids for other syntax faults (`json.unexpected_char`, `json.unexpected_end`, `json.trailing_data`, `json.invalid_number`, `json.invalid_escape`, `json.invalid_literal`, `json.control_character`, `json.expected_key`, `json.expected_colon`, `json.expected_comma`); seed bound errors use rules `minimum` and `maximum`; schema patterns end in `$(?!\n)` for the pattern trap. Review, CI, and merge still open.

- Orchestrator check 0093a50: tests unchanged since 06ba1f0 apart from the generated `tests/data/recipe_hash_vectors.json`. Two clean `windows-clang-cl` workflow runs: the first ctest run failed once (11 s, output not captured) and was not reproduced in six later runs or a second clean build (53 cases, 1,673 assertions pass); treat as unexplained until CI confirms. `uv run pytest` 999 passed, 2 NDK-only skips; wording and pragma checks exit 0. Matrix audit: every row has a passing engine and Python test.

- Review pass 1 patches b05f867 (14 patch findings, triage below). Orchestrator check on a clean build: ctest 56 cases, 2,040 assertions pass; `uv run pytest` 1,045 passed, 2 NDK-only skips; wording, pragma, table-log, row-coverage, compile-flag, and engine-symbol checks pass.

## Spec Change Log

## Review Triage Log

Pass 1 (2026-11-04): blind hunter (BH), edge case hunter (EC), verification gap (VG), all fresh context.

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | VG: engine pattern checks (`date` month and day, version leading zeros, trailing newline on `engine_version`, `date`, `loudness_hash`) have no engine-side must-fail case | medium | grep of fixtures finds none; relaxing `date_ok` or `plain_number` keeps every C++ test green | patch |
| 2 | VG: high surrogate followed by an escaped non-low surrogate untested in C++ | low | only `\ud800A` (raw A) and `\ud800 ` exist; both stop at the earlier `\u` check | patch |
| 3 | VG other, BH: `parse names each strict rule` lists `{"a":1,"a":2}` twice; escaped-key case lost | low | `tests/cpp/test_json.cpp:258-259` identical | patch |
| 4 | EC, VG other, BH: `"01.0"` and `"2.01"` reported as `schema_version.major` instead of `pattern` | low | `recipe.cpp` check_value uses `all_digits`, not `plain_number`, before the major rule | patch |
| 5 | EC: duplicate key followed by a later syntax fault gives a different rule in engine and Python; several duplicates report different keys | low | engine checks duplicates after the whole object in sorted order (`value.cpp:321-333`); Python checks each key as read | patch |
| 6 | EC: Python `json.invalid_number` offset is the current position, engine uses the number start | low | `tools/recipe_hash.py:222,228,237` call `fail` without `start`; engine `value.cpp:462-496` passes `start` | patch |
| 7 | BH: no shared table checks rule plus byte offset on both sides | medium | `invalid-expected.json` has no offsets; findings 5 and 6 slipped through | patch |
| 8 | EC, BH: `recipe_hash.py` prints a hash for structurally invalid recipes | low | CLI runs only the strict loader; no current consumer; the tool must stay stdlib only | patch (state it in help and docstring) |
| 9 | EC: CLI traceback on a missing or directory path | low | `main` catches only `StrictJSONError` | patch |
| 10 | BH: hash vectors are written by the Python tool, so a bug shared by both sides would pass | low | engine and Python read tags differently, but no test pins canonical bytes | patch (one hand-written canonical text plus hashlib hash) |
| 11 | BH: no reason logged for keeping `schema_version` in the hash | low | design log (ff) gives a reason for `engine_version` only | patch (one sentence in (ff)) |
| 12 | BH: test accepts both `schema_version` and `/schema_version` as the parameter | low | `test_recipe.cpp` accepts either; engine emits the JSON Pointer | patch (require `/schema_version`) |
| 13 | EC, BH: `canonicalize` assumes valid UTF-8 for hand-built `Value` strings | low | only the parser builds values today; a precondition comment is a direct fix | patch (document precondition) |
| 14 | BH: `date` accepts impossible dates such as 2026-02-31 | low | schema and engine agree (shape only); a calendar check adds branches on both sides | patch (state shape-only in README) |
| 15 | EC, BH: a fractional seed that rounds to an integer in binary64 is accepted | false | JSON numbers are binary64 (I-JSON); jsonschema and the engine both see the rounded integer, and the hash uses that value, so the tools agree | reject |
| 16 | EC: `format_number` treats NaN or infinity as finite | false | no caller can pass one: the parser rejects non-finite input and nothing else builds numbers | reject |
| 17 | EC: boolean schema node crashes `load_tags` | false | the repo schema has no boolean subschemas | reject |
| 18 | BH: no input size, string length, or member count cap | low | no host passes input yet; a cap adds a rule on both sides; belongs to the Story 1.2 C API input contract | reject |
| 19 | BH: `loudness_gain_db` and `loudness_hash` can appear one without the other | false | both optional by decision; pairing is the `final` mode check (AD-13, Story 4.2) | reject |
| 20 | BH: records disagree on status; guidebook UPDATE_LOG missing record commits | low | `in-review` is the spec's review state, sprint status moves at present; record-only commits are not story sections | patch (records at close) |
| 21 | VG other, BH: unexplained one-off ctest failure | maybe-false | six reruns and a second clean build pass; CI on both fast platforms will show recurrence | defer (unverified medium) |

## Design Notes

Hash input: remove every hash-excluded path from the parsed tree, canonicalize the rest, SHA-256 the UTF-8 bytes, lowercase hex. Python reads the tags from the schema; the engine uses its compiled field table, and the field-table test keeps them equal.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: build and every ctest pass.
- `uv run pytest` -- expected: all pass.
- `uv run --no-project python tools/check_wording.py` and `tools/check_fp_pragmas.py` -- expected: exit 0.
