---
title: 'Story 1.1: minimal recipe schema and recipe hash'
type: 'feature'
created: '2026-11-04'
status: 'in-progress'
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
- [ ] `tests/python/test_recipe_*.py`, `tests/cpp/test_json.cpp`, `test_recipe.cpp`, `test_sha256.cpp`, fixtures and vector files -- QA agent writes failing tests from the ACs and matrix; tests-only commit -- tests first.
- [ ] `recipes/recipe.schema.json`, `recipes/README.md` -- schema with tags.
- [ ] `engine/src/json/*`, `engine/src/crypto/sha256.*`, `engine/src/recipe/*`, `engine/CMakeLists.txt` -- parser, canonicalizer, SHA-256, parse stage, hash.
- [ ] `tools/recipe_hash.py`, `pyproject.toml`, `uv.lock` -- Python hash and dependency.
- [ ] `docs/design-log.md`, spine Stack table, `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given the schema, when a test walks every property, then each is `snake_case` with a unit suffix where it holds a quantity, and carries exactly one valid `x-arcani-tag`.
- Given the engine field table, when a C++ test parses the schema file with the engine parser, then paths, types, and tags match it exactly.
- Given every fixture, when Python (strict load plus `jsonschema`) and the engine parse stage judge it, then each verdict matches the fixture's folder.
- Given the RFC 8785 and SHA-256 vectors, when engine and Python run them, then every output matches.
- Given every valid fixture, when engine and Python hash it, then both equal `tests/data/recipe_hash_vectors.json`, and the Python test confirms the file is current.
- Given number conversion, when the engine formats 10,000 seeded binary64 values plus edge values (subnormals, max, 1e21, 1e-7, -0), then output equals Python's ECMAScript formatting and parses back to the same bits.

## Implementation Notes

- Failing tests 06ba1f0 (fresh-context QA agent). Settled in the tests: error rule names (`unknown_property`, `json.duplicate_key`, `json.trailing_comma`, and the rest in `recipes/fixtures/invalid-expected.json`), shared by the engine and the Python strict loader; a syntax error's parameter is its byte offset as digits; the schema pattern itself rejects a major other than 1, so `schema_version` "2.0" is invalid for both sides; layer fields are required inside their layer; bad UTF-8 cases are built inside the tests, not stored as fixture files (the wording check fails non-UTF-8 files). Extra data file `tests/data/number_format_vectors.json` holds the 10,000 seeded values plus edges.

## Spec Change Log

## Review Triage Log

## Design Notes

Hash input: remove every hash-excluded path from the parsed tree, canonicalize the rest, SHA-256 the UTF-8 bytes, lowercase hex. Python reads the tags from the schema; the engine uses its compiled field table, and the field-table test keeps them equal.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: build and every ctest pass.
- `uv run pytest` -- expected: all pass.
- `uv run --no-project python tools/check_wording.py` and `tools/check_fp_pragmas.py` -- expected: exit 0.
