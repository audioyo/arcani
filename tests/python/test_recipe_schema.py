"""Recipe schema: field list, names, units, and tags (Story 1.1).

Contract with recipes/recipe.schema.json (JSON Schema draft 2020-12):

- `"$schema"` is `https://json-schema.org/draft/2020-12/schema` and the file
  is a valid schema of that draft.
- Every object (the root and each layer) is `"type": "object"` with
  `"additionalProperties": false`. Layers are fixed top-level keys
  (`theta_reference`, `binaural`), never an array. Local `$ref` into `$defs`
  is allowed; the walk below resolves it.
- Every property carries exactly one `x-arcani-tag`, a string, one of
  `hash-excluded`, `loudness-relevant`, `none`.
- Property names are snake_case. A property of type `number` holds a quantity
  and ends in a unit suffix (`_hz`, `_deg`, `_db`, `_lufs`, `_s`, `_percent`).
  `seed` (integer) is a count, not a quantity.
- Story 2.1: `theta_reference` requires `carrier_hz`, `rate_hz`,
  `am_depth_percent` (numbers, loudness-relevant) and `shape`, a string
  whose `enum` is exactly ["sine", "smoothed_on_off", "sawtooth",
  "reverse_saw", "custom"] in that order (`custom` is schema-valid so compile
  can reject it with a named rule; any other text fails the schema with the
  `enum` keyword).
- The schema holds structure and types only. The only numeric bounds allowed
  are the seed bounds 0 and 2^53 - 1; locked ranges live in
  tests/tables/ranges.tsv (Story 1.3).

Contract with tools/recipe_hash.py (loaded by path, standard library only):

- `load_schema() -> dict` reads recipes/recipe.schema.json.
- `load_tags(schema: dict) -> dict[str, str]` maps the JSON Pointer of every
  property (for example `/binaural/beat_rate_hz`) to its tag.

The expected field list, types, and tags are the spec's decisions
(spec-1-1-minimal-recipe-schema-and-recipe-hash.md, Intent). Object
properties (the layers) carry a valid tag, but its value is not fixed here.
"""

import importlib.util
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / "recipes" / "recipe.schema.json"
TOOL = REPO_ROOT / "tools" / "recipe_hash.py"

TAGS = {"hash-excluded", "loudness-relevant", "none"}
UNIT_SUFFIXES = ("_hz", "_deg", "_db", "_lufs", "_s", "_percent")
SNAKE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
ANY_TAG = object()
SEED_MAX = 2**53 - 1

# JSON Pointer -> (type, tag, required within its parent object).
FIELDS = {
    "/schema_version": ("string", "none", True),
    "/engine_version": ("string", "none", True),
    "/seed": ("integer", "none", True),
    "/author": ("string", "hash-excluded", True),
    "/date": ("string", "hash-excluded", True),
    "/rationale": ("string", "hash-excluded", True),
    "/length_s": ("number", "loudness-relevant", True),
    "/loudness_target_lufs": ("number", "loudness-relevant", True),
    "/loudness_gain_db": ("number", "hash-excluded", False),
    "/loudness_hash": ("string", "hash-excluded", False),
    "/theta_reference": ("object", ANY_TAG, False),
    "/theta_reference/carrier_hz": ("number", "loudness-relevant", True),
    "/theta_reference/rate_hz": ("number", "loudness-relevant", True),
    "/theta_reference/am_depth_percent": ("number", "loudness-relevant", True),
    "/theta_reference/shape": ("string", "loudness-relevant", True),
    "/binaural": ("object", ANY_TAG, False),
    "/binaural/carrier_left_hz": ("number", "loudness-relevant", True),
    "/binaural/beat_rate_hz": ("number", "loudness-relevant", True),
}


def _no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    dup = {k for k in keys if keys.count(k) > 1}
    assert not dup, f"recipe.schema.json repeats keys {sorted(dup)} in one object"
    return dict(pairs)


def load_schema_strict():
    assert SCHEMA.is_file(), f"missing {SCHEMA}"
    return json.loads(SCHEMA.read_bytes().decode("utf-8"), object_pairs_hook=_no_duplicates)


def load_tool():
    assert TOOL.is_file(), f"missing {TOOL}"
    spec = importlib.util.spec_from_file_location("recipe_hash", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve(schema, node):
    while "$ref" in node:
        ref = node["$ref"]
        assert ref.startswith("#/"), f"only local $ref is allowed, got {ref}"
        target = schema
        for part in ref[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        node = target
    return node


def walk(schema):
    """Yields (pointer, property node, required) for every property."""
    def objects(node, prefix):
        node = resolve(schema, node)
        required = set(node.get("required", []))
        for name, prop in node.get("properties", {}).items():
            pointer = f"{prefix}/{name}"
            yield pointer, prop, name in required
            if resolve(schema, prop).get("type") == "object":
                yield from objects(prop, pointer)
    yield from objects(schema, "")


def prop_type(schema, prop):
    t = resolve(schema, prop).get("type", prop.get("type"))
    assert isinstance(t, str), f"each property has one type string, got {t!r}"
    return t


def all_objects(schema):
    seen = [schema]
    for _, prop, _ in walk(schema):
        node = resolve(schema, prop)
        if node.get("type") == "object":
            seen.append(node)
    return seen


def test_schema_is_draft_2020_12_and_valid():
    import jsonschema  # dev dependency added by Story 1.1

    schema = load_schema_strict()
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema.get("type") == "object"


def test_every_object_rejects_unknown_properties():
    schema = load_schema_strict()
    for node in all_objects(schema):
        assert node.get("additionalProperties") is False, node
        assert "patternProperties" not in node
        assert "unevaluatedProperties" not in node or node["unevaluatedProperties"] is False


def test_field_list_types_and_required_match_the_spec():
    schema = load_schema_strict()
    got = {pointer: (prop_type(schema, prop), required) for pointer, prop, required in walk(schema)}
    want = {pointer: (t, required) for pointer, (t, _, required) in FIELDS.items()}
    assert got == want


def test_root_required_list_is_exact():
    schema = load_schema_strict()
    want = sorted(p[1:] for p, (_, _, req) in FIELDS.items() if req and p.count("/") == 1)
    assert sorted(schema.get("required", [])) == want


def test_every_property_is_snake_case_with_unit_suffix_for_quantities():
    schema = load_schema_strict()
    for pointer, prop, _ in walk(schema):
        name = pointer.rsplit("/", 1)[1]
        assert SNAKE.fullmatch(name), f"{pointer}: not snake_case"
        if prop_type(schema, prop) == "number":
            assert name.endswith(UNIT_SUFFIXES), f"{pointer}: quantity without a unit suffix"


def test_every_property_carries_exactly_one_valid_tag():
    schema = load_schema_strict()
    count = 0
    for pointer, prop, _ in walk(schema):
        assert "x-arcani-tag" in prop, f"{pointer}: no x-arcani-tag"
        tag = prop["x-arcani-tag"]
        assert isinstance(tag, str), f"{pointer}: x-arcani-tag must be one string, got {tag!r}"
        assert tag in TAGS, f"{pointer}: unknown tag {tag!r}"
        count += 1
    assert count == len(FIELDS)


def test_tags_match_the_spec_decisions():
    schema = load_schema_strict()
    got = {pointer: prop["x-arcani-tag"] for pointer, prop, _ in walk(schema)}
    for pointer, (_, tag, _) in FIELDS.items():
        if tag is not ANY_TAG:
            assert got.get(pointer) == tag, f"{pointer}: tag {got.get(pointer)!r}, want {tag!r}"


def test_engine_version_stays_in_the_hash():
    schema = load_schema_strict()
    got = {pointer: prop["x-arcani-tag"] for pointer, prop, _ in walk(schema)}
    assert got["/engine_version"] != "hash-excluded"


def test_no_routing_or_coupling_target_field_anywhere():
    schema = load_schema_strict()
    for pointer, _, _ in walk(schema):
        name = pointer.rsplit("/", 1)[1]
        assert "routing" not in name and "coupling" not in name, f"{pointer}: field is outside the decided list"


def _numbers_with_keys(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                yield f"{path}/{k}", k, v
            yield from _numbers_with_keys(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _numbers_with_keys(v, f"{path}/{i}")


def test_schema_holds_no_locked_range_numbers():
    schema = load_schema_strict()
    bound_keys = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"}
    for path, key, value in _numbers_with_keys(schema):
        if key in bound_keys:
            assert path.startswith("/properties/seed/"), f"{path}: numeric bound outside seed"
            assert value in (0, SEED_MAX), f"{path}: seed bound {value} is not 0 or 2^53 - 1"


def test_tool_reads_the_same_tags_from_the_schema():
    tool = load_tool()
    schema = tool.load_schema()
    assert schema == load_schema_strict()
    got = tool.load_tags(schema)
    want = {pointer: prop["x-arcani-tag"] for pointer, prop, _ in walk(schema)}
    assert got == want


# ------------------------------------------------- theta shape (Story 2.1)

THETA_SHAPE_ENUM = ["sine", "smoothed_on_off", "sawtooth", "reverse_saw", "custom"]


def theta_recipe(shape):
    return {
        "schema_version": "1.0", "engine_version": "0.0.1", "seed": 42,
        "author": "Arcani test", "date": "2026-11-06", "rationale": "Schema enum test.",
        "length_s": 1, "loudness_target_lufs": -36,
        "theta_reference": {"carrier_hz": 450, "rate_hz": 6, "am_depth_percent": 75,
                            "shape": shape},
    }


def test_theta_shape_enum_is_exact():
    schema = load_schema_strict()
    node = resolve(schema, schema["properties"]["theta_reference"])
    shape = resolve(schema, node["properties"]["shape"])
    assert shape.get("type") == "string"
    assert shape.get("enum") == THETA_SHAPE_ENUM


def test_theta_shape_enum_accepts_custom_and_rejects_other_text():
    import jsonschema

    validator = jsonschema.Draft202012Validator(load_schema_strict())
    for shape in THETA_SHAPE_ENUM:
        assert not list(validator.iter_errors(theta_recipe(shape))), shape
    for shape in ("square", "Sine", "", "smoothed-on-off"):
        errors = list(validator.iter_errors(theta_recipe(shape)))
        assert errors, shape
        assert {e.validator for e in errors} == {"enum"}, (shape, [e.message for e in errors])
