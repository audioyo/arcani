# recipes

Session recipes. One JSON recipe fully defines a session. The four v0.1 starter recipes arrive in a later story; for now this folder holds the schema and the shared test fixtures.

## Schema

`recipe.schema.json` (JSON Schema draft 2020-12) holds structure and types only. Locked ranges live in `tests/tables/ranges.tsv` and are checked after parse (Story 1.3), never in the schema. Every object rejects unknown properties.

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

`fixtures/valid/` and `fixtures/invalid/` are shared by the Python and C++ tests; the folder is the expected verdict. `fixtures/invalid-expected.json` names the expected error for each invalid fixture. Fixture values are placeholders, not starter defaults.
