"""Recipe hash in Python, and the shared hash vectors file (Story 1.1).

Definition (spec Design Notes): remove every hash-excluded path (tag
`hash-excluded` in recipes/recipe.schema.json) from the parsed recipe,
canonicalize the rest with RFC 8785, SHA-256 the UTF-8 bytes, write lowercase
hex. `engine_version` stays in the hash.

Contract with tools/recipe_hash.py (loaded by path, standard library only, no
engine code, no jsonschema):

- `hash_value(value: dict, schema: dict | None = None) -> str`: the recipe
  hash of a parsed recipe (schema defaults to `load_schema()`).
- `hash_bytes(data: bytes, schema: dict | None = None) -> str`:
  `hash_value(strict_loads(data), schema)`.
- `compute_vectors() -> dict[str, str]`: valid fixture file name (for example
  `both-layers.json`) to its hash, for every recipes/fixtures/valid/*.json.
- `python tools/recipe_hash.py --write-vectors` writes compute_vectors() to
  tests/data/recipe_hash_vectors.json as one JSON object, file name to hash.
  `--help` exits 0 and names `--write-vectors`.

tests/data/recipe_hash_vectors.json is written by that tool after the
implementation lands; until then the vectors tests fail on its absence.
tests/cpp/test_recipe.cpp checks the engine hash against the same file.

Matrix rows covered: reformatted (same hash), metadata edit (same hash),
audio edit (different hash), integer form (7.0 hashes as 7).
"""

import ast
import copy
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VALID = REPO_ROOT / "recipes" / "fixtures" / "valid"
SCHEMA = REPO_ROOT / "recipes" / "recipe.schema.json"
TOOL = REPO_ROOT / "tools" / "recipe_hash.py"
VECTORS = REPO_ROOT / "tests" / "data" / "recipe_hash_vectors.json"
HEX64 = re.compile(r"[0-9a-f]{64}")

BASE = "both-layers.json"
SAME_AS_BASE = [
    "both-layers-reformatted.json",
    "both-layers-metadata-edited.json",
    "both-layers-without-loudness-fields.json",
]
DIFFERENT_FROM_BASE = [
    "both-layers-seed-changed.json",
    "both-layers-engine-version-changed.json",
    "both-layers-schema-minor-changed.json",
    "both-layers-length-changed.json",
    "both-layers-loudness-target-changed.json",
    "both-layers-theta-carrier-changed.json",
    "both-layers-binaural-carrier-left-changed.json",
    "both-layers-beat-rate-changed.json",
    "theta-reference-only.json",
    "binaural-only.json",
]
SAME_PAIRS = [("minimal-seed-7.json", "minimal-seed-7-0.json")]

HASH_EXCLUDED = ["/author", "/date", "/rationale", "/loudness_gain_db", "/loudness_hash"]
IN_HASH = ["/schema_version", "/engine_version", "/seed", "/length_s", "/loudness_target_lufs",
           "/theta_reference/carrier_hz", "/binaural/carrier_left_hz", "/binaural/beat_rate_hz"]


def load_tool():
    assert TOOL.is_file(), f"missing {TOOL}"
    spec = importlib.util.spec_from_file_location("recipe_hash", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(name):
    return (VALID / name).read_bytes()


def base_value():
    return json.loads(fixture(BASE).decode("utf-8"))


def get(doc, pointer):
    for part in pointer[1:].split("/"):
        doc = doc[part]
    return doc


def put(doc, pointer, value):
    doc = copy.deepcopy(doc)
    parts = pointer[1:].split("/")
    target = doc
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    return doc


def drop(doc, pointer):
    doc = copy.deepcopy(doc)
    parts = pointer[1:].split("/")
    target = doc
    for part in parts[:-1]:
        target = target[part]
    del target[parts[-1]]
    return doc


def changed(value):
    if isinstance(value, bool):
        raise AssertionError("no boolean recipe field")
    if isinstance(value, (int, float)):
        return value + 1
    if value == "1.0":
        return "1.1"
    if re.fullmatch(r"\d+\.\d+\.\d+", value):
        return value[:-1] + str((int(value[-1]) + 1) % 10)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return "2030-01-01"
    if HEX64.fullmatch(value):
        return hashlib.sha256(value.encode()).hexdigest()
    return value + " edited"


def test_hash_is_lowercase_hex_and_follows_the_definition():
    tool = load_tool()
    value = base_value()
    got = tool.hash_value(value)
    assert HEX64.fullmatch(got)
    stripped = value
    for pointer in HASH_EXCLUDED:
        stripped = drop(stripped, pointer)
    assert got == hashlib.sha256(tool.canonicalize(stripped)).hexdigest()
    assert tool.hash_bytes(fixture(BASE)) == got


def test_hash_equals_sha256_of_the_hand_written_canonical_text():
    # Written out by hand from both-layers.json, not by the tool: hash-excluded
    # fields removed, keys sorted, integral numbers without a fraction.
    # tests/cpp/test_recipe.cpp checks the same literal and hex on the engine.
    canonical = (
        '{"binaural":{"beat_rate_hz":6,"carrier_left_hz":400},"engine_version":"0.0.1",'
        '"length_s":600,"loudness_target_lufs":-16,"schema_version":"1.0","seed":42,'
        '"theta_reference":{"carrier_hz":200}}').encode("utf-8")
    want = hashlib.sha256(canonical).hexdigest()
    assert want == "154db16986eae01f0cefdce72bf0e1b8fd38eaf5abcf69f61064cc77d3e11127"
    tool = load_tool()
    assert tool.canonicalize(drop(drop(drop(drop(drop(base_value(), "/author"), "/date"),
                                             "/rationale"), "/loudness_gain_db"),
                                  "/loudness_hash")) == canonical
    assert tool.hash_bytes(fixture(BASE)) == want


def test_hash_does_not_mutate_its_input():
    tool = load_tool()
    value = base_value()
    before = copy.deepcopy(value)
    tool.hash_value(value)
    assert value == before


@pytest.mark.parametrize("name", SAME_AS_BASE)
def test_reformatted_or_metadata_only_edit_keeps_the_hash(name):
    tool = load_tool()
    assert tool.hash_bytes(fixture(name)) == tool.hash_bytes(fixture(BASE))


@pytest.mark.parametrize("name", DIFFERENT_FROM_BASE)
def test_audio_edit_changes_the_hash(name):
    tool = load_tool()
    assert tool.hash_bytes(fixture(name)) != tool.hash_bytes(fixture(BASE))


@pytest.mark.parametrize("a, b", SAME_PAIRS)
def test_integer_form_hashes_like_the_integer(a, b):
    tool = load_tool()
    assert tool.hash_bytes(fixture(a)) == tool.hash_bytes(fixture(b))


@pytest.mark.parametrize("pointer", HASH_EXCLUDED)
def test_every_hash_excluded_field_is_ignored(pointer):
    tool = load_tool()
    value = base_value()
    assert tool.hash_value(put(value, pointer, changed(get(value, pointer)))) == tool.hash_value(value)
    assert tool.hash_value(drop(value, pointer)) == tool.hash_value(value)


@pytest.mark.parametrize("pointer", IN_HASH)
def test_every_other_field_changes_the_hash(pointer):
    tool = load_tool()
    value = base_value()
    assert tool.hash_value(put(value, pointer, changed(get(value, pointer)))) != tool.hash_value(value)


def test_excluded_and_in_hash_lists_cover_every_leaf_tag():
    tool = load_tool()
    tags = tool.load_tags(tool.load_schema())
    assert sorted(p for p, t in tags.items() if t == "hash-excluded") == sorted(HASH_EXCLUDED)
    leaves = {p for p in tags if p not in ("/theta_reference", "/binaural")}
    assert leaves == set(HASH_EXCLUDED) | set(IN_HASH)


def test_tool_uses_only_the_standard_library():
    assert TOOL.is_file(), f"missing {TOOL}"
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            mods = [node.module]
        else:
            continue
        for mod in mods:
            assert mod.split(".")[0] in sys.stdlib_module_names, f"non-stdlib import {mod}"


def test_cli_offers_write_vectors():
    assert TOOL.is_file(), f"missing {TOOL}"
    out = subprocess.run([sys.executable, str(TOOL), "--help"], capture_output=True, text=True,
                         cwd=REPO_ROOT, check=False)
    assert out.returncode == 0, out.stderr
    assert "--write-vectors" in out.stdout


def test_hash_vectors_file_exists_and_covers_every_valid_fixture():
    assert VECTORS.is_file(), f"missing {VECTORS}: run python tools/recipe_hash.py --write-vectors"
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert sorted(data) == sorted(p.name for p in VALID.glob("*.json"))
    for name, value in data.items():
        assert HEX64.fullmatch(value), name


def test_hash_vectors_file_is_current():
    tool = load_tool()
    assert VECTORS.is_file(), f"missing {VECTORS}: run python tools/recipe_hash.py --write-vectors"
    assert json.loads(VECTORS.read_text(encoding="utf-8")) == tool.compute_vectors()
