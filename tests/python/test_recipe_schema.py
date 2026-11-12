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
- Story 2.2: `gamma_pac` (an optional object, the property right after
  `theta_reference`, tag `loudness-relevant`, additionalProperties false)
  requires, in this order, `carrier_hz`, `rate_hz`, `am_depth_percent`
  (numbers), `carrier_wave`, a string whose `enum` is exactly ["sine",
  "triangle", "softened_square"] (triangle and softened square are
  schema-valid so compile rejects them by name), and `coupling`, a string
  whose `enum` is exactly ["uncoupled"]. Every gamma property is
  `loudness-relevant`. `coupling` names the gamma depth setting; it is not a
  coupling target (no field may name a coupling target or a routing).
- Story 2.3: the `coupling` enum is exactly ["uncoupled", "smooth_swell"],
  and `gamma_pac` gains the optional `coupling_phase_deg` (number,
  `loudness-relevant`, not required), the property right after `coupling`.
  It is a setting of the gamma depth (where in the theta cycle the swell
  peaks), not a coupling target; phase text fails the schema with the `type`
  keyword. Its locked range (row coupling-phase) lives in the tables.
- Story 2.5: `binaural` gains, in this order after `beat_rate_hz`, the
  optional `beat_rate_cycle` (an object, additionalProperties false, that
  requires `swing_hz`, `period_s`, and `start_phase_deg`, each a number) and
  the optional `waveform`, a string whose `enum` is exactly ["sine",
  "triangle"] (triangle is schema-valid so compile rejects it by name; absent
  means sine). Every new property is `loudness-relevant`. The cycle's locked
  ranges (rows rate-cycle-period and rate-cycle-start-phase) and its
  worst-case rate checks live in the tables and the validator, not the schema.
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
    "/gamma_pac": ("object", ANY_TAG, False),                              # Story 2.2
    "/gamma_pac/carrier_hz": ("number", "loudness-relevant", True),
    "/gamma_pac/rate_hz": ("number", "loudness-relevant", True),
    "/gamma_pac/am_depth_percent": ("number", "loudness-relevant", True),
    "/gamma_pac/carrier_wave": ("string", "loudness-relevant", True),
    "/gamma_pac/coupling": ("string", "loudness-relevant", True),
    "/gamma_pac/coupling_phase_deg": ("number", "loudness-relevant", False),  # Story 2.3
    "/binaural": ("object", ANY_TAG, False),
    "/binaural/carrier_left_hz": ("number", "loudness-relevant", True),
    "/binaural/beat_rate_hz": ("number", "loudness-relevant", True),
    "/binaural/beat_rate_cycle": ("object", "loudness-relevant", False),             # Story 2.5
    "/binaural/beat_rate_cycle/swing_hz": ("number", "loudness-relevant", True),
    "/binaural/beat_rate_cycle/period_s": ("number", "loudness-relevant", True),
    "/binaural/beat_rate_cycle/start_phase_deg": ("number", "loudness-relevant", True),
    "/binaural/waveform": ("string", "loudness-relevant", False),                    # Story 2.5
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


# Story 2.2: the gamma depth setting is the one field whose name holds
# "coupling"; it selects how the gamma depth moves, never what it couples to.
# Story 2.3 adds its phase setting, where in the theta cycle the swell peaks.
# Neither names a coupling target.
COUPLING_SETTINGS = ("/gamma_pac/coupling", "/gamma_pac/coupling_phase_deg")


def test_no_routing_or_coupling_target_field_anywhere():
    schema = load_schema_strict()
    for pointer, _, _ in walk(schema):
        name = pointer.rsplit("/", 1)[1]
        assert "routing" not in name, f"{pointer}: field is outside the decided list"
        assert "target" not in name or name == "loudness_target_lufs", f"{pointer}: a target field"
        if pointer not in COUPLING_SETTINGS:
            assert "coupling" not in name, f"{pointer}: field is outside the decided list"


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


# ------------------------------------------------- gamma PAC layer (Story 2.2)

GAMMA_REQUIRED = ["carrier_hz", "rate_hz", "am_depth_percent", "carrier_wave", "coupling"]
GAMMA_PROPERTIES = GAMMA_REQUIRED + ["coupling_phase_deg"]  # Story 2.3: optional, after coupling
GAMMA_CARRIER_WAVE_ENUM = ["sine", "triangle", "softened_square"]
GAMMA_COUPLING_ENUM = ["uncoupled", "smooth_swell"]  # Story 2.3 adds smooth_swell


def gamma_recipe(carrier_wave="sine", coupling="uncoupled"):
    return {
        "schema_version": "1.0", "engine_version": "0.0.1", "seed": 42,
        "author": "Arcani test", "date": "2026-11-07", "rationale": "Schema enum test.",
        "length_s": 1, "loudness_target_lufs": -36,
        "gamma_pac": {"carrier_hz": 250, "rate_hz": 40, "am_depth_percent": 25,
                      "carrier_wave": carrier_wave, "coupling": coupling},
    }


def gamma_node(schema):
    assert "gamma_pac" in schema["properties"], "no gamma_pac property (Story 2.2)"
    return resolve(schema, schema["properties"]["gamma_pac"])


def test_gamma_pac_follows_theta_reference():
    schema = load_schema_strict()
    names = list(schema["properties"])
    assert "gamma_pac" in names, names
    assert names.index("gamma_pac") == names.index("theta_reference") + 1, names
    assert "gamma_pac" not in schema.get("required", [])


def test_gamma_pac_shape_tags_and_required():
    schema = load_schema_strict()
    node = gamma_node(schema)
    assert schema["properties"]["gamma_pac"].get("x-arcani-tag") == "loudness-relevant"
    assert node.get("type") == "object"
    assert node.get("additionalProperties") is False
    assert list(node["properties"]) == GAMMA_PROPERTIES
    assert sorted(node.get("required", [])) == sorted(GAMMA_REQUIRED)
    for name in GAMMA_PROPERTIES:
        assert node["properties"][name].get("x-arcani-tag") == "loudness-relevant", name


def test_gamma_enums_are_exact():
    schema = load_schema_strict()
    node = gamma_node(schema)
    wave = resolve(schema, node["properties"]["carrier_wave"])
    coupling = resolve(schema, node["properties"]["coupling"])
    assert wave.get("type") == "string" and wave.get("enum") == GAMMA_CARRIER_WAVE_ENUM
    assert coupling.get("type") == "string" and coupling.get("enum") == GAMMA_COUPLING_ENUM
    for name in ("carrier_hz", "rate_hz", "am_depth_percent"):
        assert resolve(schema, node["properties"][name]).get("type") == "number", name


def test_gamma_enums_accept_their_members_and_reject_other_text():
    import jsonschema

    validator = jsonschema.Draft202012Validator(load_schema_strict())
    for wave in GAMMA_CARRIER_WAVE_ENUM:
        assert not list(validator.iter_errors(gamma_recipe(carrier_wave=wave))), wave
    for wave in ("square", "Sine", "", "softened-square"):
        errors = list(validator.iter_errors(gamma_recipe(carrier_wave=wave)))
        assert errors, wave
        assert {e.validator for e in errors} == {"enum"}, (wave, [e.message for e in errors])
    for coupling in GAMMA_COUPLING_ENUM:
        assert not list(validator.iter_errors(gamma_recipe(coupling=coupling))), coupling
    for coupling in ("swell", "Uncoupled", "", "smooth-swell", "Smooth_swell", "bursts"):
        errors = list(validator.iter_errors(gamma_recipe(coupling=coupling)))
        assert errors, coupling
        assert {e.validator for e in errors} == {"enum"}, (coupling, [e.message for e in errors])
    extra = gamma_recipe()
    extra["gamma_pac"]["coupling_target"] = "theta_reference"
    errors = list(validator.iter_errors(extra))
    assert {e.validator for e in errors} == {"additionalProperties"}, [e.message for e in errors]


# ------------------------------------------- coupled smooth swell (Story 2.3)


def test_coupling_phase_is_an_optional_number_after_coupling():
    schema = load_schema_strict()
    node = gamma_node(schema)
    names = list(node["properties"])
    assert "coupling_phase_deg" in names, names
    assert names.index("coupling_phase_deg") == names.index("coupling") + 1, names
    assert "coupling_phase_deg" not in node.get("required", [])
    phase = resolve(schema, node["properties"]["coupling_phase_deg"])
    assert phase.get("type") == "number"
    assert node["properties"]["coupling_phase_deg"].get("x-arcani-tag") == "loudness-relevant"
    assert not {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"} & set(phase)


def test_coupling_phase_accepts_numbers_and_rejects_text():
    import jsonschema

    validator = jsonschema.Draft202012Validator(load_schema_strict())
    for coupling in GAMMA_COUPLING_ENUM:
        for phase in (0, 90, 359.99, 360):
            r = gamma_recipe(coupling=coupling)
            r["gamma_pac"]["coupling_phase_deg"] = phase
            # Schema-valid either way: compile, not the schema, pairs the
            # phase with the coupling and checks the locked range.
            assert not list(validator.iter_errors(r)), (coupling, phase)
    # Out of the locked range is still schema-valid (the range lives in the tables).
    for phase in (-0.01, 360.01):
        r = gamma_recipe(coupling="smooth_swell")
        r["gamma_pac"]["coupling_phase_deg"] = phase
        assert not list(validator.iter_errors(r)), phase
    for bad in ("90", True, None, [90]):
        r = gamma_recipe(coupling="smooth_swell")
        r["gamma_pac"]["coupling_phase_deg"] = bad
        errors = list(validator.iter_errors(r))
        assert errors, bad
        assert {e.validator for e in errors} == {"type"}, (bad, [e.message for e in errors])
        assert {"/".join(str(p) for p in e.absolute_path) for e in errors} == {
            "gamma_pac/coupling_phase_deg"}, bad


# ------------------------------------------- binaural layer (Story 2.5)

BINAURAL_PROPERTIES = ["carrier_left_hz", "beat_rate_hz", "beat_rate_cycle", "waveform"]
CYCLE_PROPERTIES = ["swing_hz", "period_s", "start_phase_deg"]
BINAURAL_WAVEFORM_ENUM = ["sine", "triangle"]


def binaural_recipe(cycle=None, waveform=None):
    b = {"carrier_left_hz": 100, "beat_rate_hz": 1.5}
    if cycle is not None:
        b["beat_rate_cycle"] = cycle
    if waveform is not None:
        b["waveform"] = waveform
    return {
        "schema_version": "1.0", "engine_version": "0.0.1", "seed": 42,
        "author": "Arcani test", "date": "2026-11-12", "rationale": "Schema binaural test.",
        "length_s": 1, "loudness_target_lufs": -36, "binaural": b,
    }


def binaural_node(schema):
    return resolve(schema, schema["properties"]["binaural"])


def test_binaural_gains_the_cycle_and_the_waveform_in_order():
    schema = load_schema_strict()
    node = binaural_node(schema)
    assert list(node["properties"]) == BINAURAL_PROPERTIES
    assert sorted(node.get("required", [])) == ["beat_rate_hz", "carrier_left_hz"]
    for name in ("beat_rate_cycle", "waveform"):
        assert node["properties"][name].get("x-arcani-tag") == "loudness-relevant", name
    cycle = resolve(schema, node["properties"]["beat_rate_cycle"])
    assert cycle.get("type") == "object"
    assert cycle.get("additionalProperties") is False
    assert list(cycle["properties"]) == CYCLE_PROPERTIES
    assert sorted(cycle.get("required", [])) == sorted(CYCLE_PROPERTIES)
    for name in CYCLE_PROPERTIES:
        prop = cycle["properties"][name]
        assert prop.get("x-arcani-tag") == "loudness-relevant", name
        assert resolve(schema, prop).get("type") == "number", name
        assert not {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"} & set(resolve(schema, prop))
    wave = resolve(schema, node["properties"]["waveform"])
    assert wave.get("type") == "string" and wave.get("enum") == BINAURAL_WAVEFORM_ENUM


def test_binaural_cycle_and_waveform_accept_and_reject():
    import jsonschema

    validator = jsonschema.Draft202012Validator(load_schema_strict())
    sleep = {"swing_hz": 1.5, "period_s": 60, "start_phase_deg": 270}
    assert not list(validator.iter_errors(binaural_recipe())), "no cycle, no waveform"
    assert not list(validator.iter_errors(binaural_recipe(cycle=sleep)))
    for wave in BINAURAL_WAVEFORM_ENUM:
        assert not list(validator.iter_errors(binaural_recipe(cycle=sleep, waveform=wave))), wave
    # Out of the locked ranges is still schema-valid (the ranges live in the tables).
    for cycle in ({"swing_hz": -1, "period_s": 59.99, "start_phase_deg": 360.01},
                  {"swing_hz": 1.51, "period_s": 60.01, "start_phase_deg": -0.01}):
        assert not list(validator.iter_errors(binaural_recipe(cycle=cycle))), cycle
    for wave in ("square", "Sine", "", "triangle_wave"):
        errors = list(validator.iter_errors(binaural_recipe(waveform=wave)))
        assert {e.validator for e in errors} == {"enum"}, (wave, [e.message for e in errors])
    errors = list(validator.iter_errors(binaural_recipe(waveform=1)))
    assert {e.validator for e in errors} == {"type"}, [e.message for e in errors]
    for name in CYCLE_PROPERTIES:
        missing = {k: v for k, v in sleep.items() if k != name}
        errors = list(validator.iter_errors(binaural_recipe(cycle=missing)))
        assert {e.validator for e in errors} == {"required"}, (name, [e.message for e in errors])
        text = dict(sleep, **{name: "1"})
        errors = list(validator.iter_errors(binaural_recipe(cycle=text)))
        assert {e.validator for e in errors} == {"type"}, (name, [e.message for e in errors])
        assert {"/".join(str(p) for p in e.absolute_path) for e in errors} == {
            f"binaural/beat_rate_cycle/{name}"}, name
    extra = dict(sleep, curve="linear")
    errors = list(validator.iter_errors(binaural_recipe(cycle=extra)))
    assert {e.validator for e in errors} == {"additionalProperties"}, [e.message for e in errors]
    errors = list(validator.iter_errors(binaural_recipe(cycle=[1.5, 60, 270])))
    assert {e.validator for e in errors} == {"type"}, [e.message for e in errors]
