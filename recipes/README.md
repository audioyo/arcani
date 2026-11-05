# recipes

Session recipes. One JSON recipe fully defines a session. The four v0.1 starter recipes arrive in a later story; for now this folder holds the schema and the shared test fixtures.

## Schema

`recipe.schema.json` (JSON Schema draft 2020-12) holds structure and types only. Locked ranges live in `tests/tables/ranges.tsv` and are checked by the engine at compile, after parse and in both modes (Story 1.3), never in the schema. Every object rejects unknown properties.

## Locked ranges at compile

Each numeric field names its range row in the engine field table (`engine/src/recipe/field_table.cpp`); the engine keeps its own copy of those rows (`engine/src/validate/validate.cpp`), and a test proves the copy equals `ranges.tsv`.

| Field | Range row | Range |
| --- | --- | --- |
| `length_s` | `session-length` | 0 to 28800 s (8 h), inclusive |
| `loudness_target_lufs` | `loudness-tones` | -36 LUFS-I exactly |
| `theta_reference.carrier_hz` | `theta-carrier` | 100 to 500 Hz, inclusive |
| `binaural.carrier_left_hz` | `binaural-carrier` | 0 Hz up to, not including, 1000 Hz |
| `binaural.beat_rate_hz` | `beat-rate` | 0 Hz up to, not including, 30 Hz |
| right carrier (`carrier_left_hz + beat_rate_hz`, derived) | `binaural-carrier-right` | 0 Hz up to, not including, 1030 Hz; reported on `binaural.beat_rate_hz` |

`seed` is bounded by the schema. `loudness_gain_db` is written by the measure pass, not authored, and has no range row (Story 4.2 checks it). A range fault is rule `range.min` or `range.max`, with the value and a limit that names the bound and the row, for example `>= 100 Hz (row theta-carrier)`. Absent layers are not checked.

| Field | Type | Required | Tag |
| --- | --- | --- | --- |
| `schema_version` | string, `MAJOR.MINOR`, major 1 | yes | none |
| `engine_version` | string, `X.Y.Z` | yes | none |
| `seed` | integer, 0 to 2^53 - 1 | yes | none |
| `author` | string | yes | hash-excluded |
| `date` | string, `YYYY-MM-DD` | yes | hash-excluded |
| `rationale` | string | yes | hash-excluded |
| `length_s` | number, seconds | yes | loudness-relevant |
| `loudness_target_lufs` | number, LUFS | yes | loudness-relevant |
| `loudness_gain_db` | number, dB | no | hash-excluded |
| `loudness_hash` | string, 64 lowercase hex digits | no | hash-excluded |
| `theta_reference` | object | no | loudness-relevant |
| `theta_reference.carrier_hz` | number, Hz | yes, in its layer | loudness-relevant |
| `binaural` | object | no | loudness-relevant |
| `binaural.carrier_left_hz` | number, Hz | yes, in its layer | loudness-relevant |
| `binaural.beat_rate_hz` | number, Hz | yes, in its layer | loudness-relevant |

`date` is checked for shape only (`YYYY-MM-DD`, month 01 to 12, day 01 to 31), not for whether the date exists: `2026-02-31` passes.

Names are `snake_case`, with a unit suffix (`_hz`, `_deg`, `_db`, `_lufs`, `_s`) on every quantity. Layers are fixed top-level keys, never an array.

## Tags

Each property carries one `x-arcani-tag`:

- `hash-excluded`: left out of the recipe hash (metadata and the stored loudness result).
- `loudness-relevant`: changes the rendered loudness.
- `none`: neither.

## Versioning

Every recipe declares `schema_version` (`MAJOR.MINOR`) and `engine_version` (`X.Y.Z`). The supported schema major is 1; the engine rejects any other major with rule `schema_version.major`, and the schema pattern rejects it too. Both versions are part of the recipe hash.

## Recipe hash

Parse strictly (RFC 8259 plus I-JSON: no comments, trailing commas, duplicate keys, NaN, or lone surrogates), remove every `hash-excluded` field, write the rest as RFC 8785 canonical JSON, SHA-256 the UTF-8 bytes, and write lowercase hex. The engine (`engine/src/recipe/`) and `tools/recipe_hash.py` compute it independently:

```
uv run python tools/recipe_hash.py RECIPE.json
uv run python tools/recipe_hash.py --write-vectors   # refresh tests/data/recipe_hash_vectors.json
```

## Fixtures

`fixtures/valid/` and `fixtures/invalid/` are shared by the Python and C++ tests; the folder is the expected schema verdict. `valid/` means schema-valid: a valid fixture can still be out of a locked range and rejected at compile (`both-layers-loudness-target-changed.json`, -36.5 LUFS-I, is one). `fixtures/invalid-expected.json` names the expected error for each invalid fixture. Fixture values are placeholders, not starter defaults.
