"""Recipe fixtures: Python strict load plus jsonschema verdicts (Story 1.1).

The folder is the verdict: every recipes/fixtures/valid/*.json passes the
strict loader and the schema; every recipes/fixtures/invalid/*.json fails one
of them. recipes/fixtures/invalid-expected.json lists every invalid fixture
with the expected error (see its description). tests/cpp/test_recipe.cpp
judges the same fixtures with the engine parse stage.

Contract with tools/recipe_hash.py (loaded by path, standard library only):

- `StrictJSONError(ValueError)` with attributes `rule` (str) and `offset`
  (int, byte offset into the input).
- `strict_loads(data: bytes)` returns the parsed value (dict, list, str, int
  or float, bool, None) or raises StrictJSONError. It applies the engine's
  strict rules (RFC 8259 plus I-JSON): no byte order mark, valid UTF-8, no
  comments, no trailing commas, no leading zeros, no NaN or Infinity, no
  number that overflows binary64, no duplicate keys (after unescaping), no
  lone surrogate escapes, nesting no deeper than a fixed limit. A deep input
  raises StrictJSONError, never RecursionError. The rule ids for those faults
  are the `json.` rules in invalid-expected.json, plus `json.invalid_utf8`,
  whose offset is the first byte of the invalid sequence.
- `load_schema() -> dict`.

Matrix rows covered (spec I/O & Edge-Case Matrix): valid minimal, unknown
field, missing or mistyped, unsupported major, bad syntax, integer form,
pattern trap. Bad UTF-8 is built in the test from a valid fixture, because a
fixture file that is not UTF-8 fails the repo wording check.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "recipes" / "fixtures"
VALID = FIXTURES / "valid"
INVALID = FIXTURES / "invalid"
EXPECTED = FIXTURES / "invalid-expected.json"
SCHEMA = REPO_ROOT / "recipes" / "recipe.schema.json"
TOOL = REPO_ROOT / "tools" / "recipe_hash.py"
KEBAB = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\.json")

# Strict-loader rules Python must name exactly, as the engine does.
JSON_RULES = {
    "json.bom", "json.comment", "json.depth", "json.duplicate_key", "json.invalid_utf8",
    "json.leading_zero", "json.lone_surrogate", "json.non_finite", "json.number_overflow",
    "json.trailing_comma",
}

# Bytes swapped into the author string of both-layers.json.
BAD_UTF8 = {
    "lone-continuation-byte": b"\x80",
    "invalid-byte-ff": b"\xff",
    "overlong-slash": b"\xc0\xaf",
    "truncated-three-byte": b"\xe2\x82",
    "encoded-surrogate": b"\xed\xa0\x80",
    "above-u10ffff": b"\xf4\x90\x80\x80",
}


def names(folder):
    return sorted(p.name for p in folder.glob("*.json"))


def load_tool():
    assert TOOL.is_file(), f"missing {TOOL}"
    spec = importlib.util.spec_from_file_location("recipe_hash", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected():
    return json.loads(EXPECTED.read_text(encoding="utf-8"))["fixtures"]


def validator():
    import jsonschema  # dev dependency added by Story 1.1

    assert SCHEMA.is_file(), f"missing {SCHEMA}"
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def judge(data):
    """Returns (verdict, StrictJSONError or None, jsonschema errors)."""
    tool = load_tool()
    try:
        value = tool.strict_loads(data)
    except tool.StrictJSONError as err:
        return "invalid", err, []
    errors = list(validator().iter_errors(value))
    return ("invalid" if errors else "valid"), None, errors


def test_fixture_folders_are_populated_and_named_in_kebab_case():
    assert len(names(VALID)) >= 2 and len(names(INVALID)) >= 2
    for name in names(VALID) + names(INVALID):
        assert KEBAB.fullmatch(name), f"{name}: not a kebab-case .json name"
    assert not set(names(VALID)) & set(names(INVALID))


def test_every_invalid_fixture_has_an_expected_error_and_no_stale_entries():
    exp = expected()
    assert sorted(exp) == names(INVALID)
    for name, entry in exp.items():
        assert set(entry) <= {"parameter", "rule", "value", "limit", "schema_keyword"}, name
        assert "parameter" in entry or entry.get("rule", "").startswith("json."), name


def test_matrix_rows_have_fixtures():
    exp = expected()
    rules = {e.get("rule") for e in exp.values()}
    assert {"unknown_property", "required", "type", "pattern", "schema_version.major"} <= rules
    assert {"json.duplicate_key", "json.trailing_comma", "json.non_finite"} <= rules
    params = {e.get("parameter") for e in exp.values()}
    assert {"/routing", "/coupling_target", "/binaural/routing",
            "/theta_reference/coupling_target"} <= params
    major = exp["schema-version-major-2.json"]
    assert (major["value"], major["rule"], major["limit"]) == ("2.0", "schema_version.major", "1")
    trap = json.loads((INVALID / "schema-version-trailing-newline.json").read_text(encoding="utf-8"))
    assert trap["schema_version"] == "1.0\n"
    assert "7.0" in (VALID / "minimal-seed-7-0.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", names(VALID))
def test_valid_fixture_is_accepted(name):
    verdict, err, errors = judge((VALID / name).read_bytes())
    assert err is None, f"{name}: strict load rejected it: {err.rule if hasattr(err, 'rule') else err}"
    assert verdict == "valid", f"{name}: schema errors {[e.message for e in errors]}"


@pytest.mark.parametrize("name", names(INVALID))
def test_invalid_fixture_is_rejected_for_the_expected_reason(name):
    entry = expected()[name]
    verdict, err, errors = judge((INVALID / name).read_bytes())
    assert verdict == "invalid", f"{name}: accepted"
    rule = entry.get("rule", "")
    if rule.startswith("json."):
        assert err is not None, f"{name}: passed the strict loader; schema errors {[e.message for e in errors]}"
        assert err.rule == rule, f"{name}: rule {err.rule!r}, want {rule!r}"
        assert isinstance(err.offset, int) and 0 <= err.offset <= (INVALID / name).stat().st_size
        return
    assert err is None, f"{name}: strict loader rejected a well-formed document ({err.rule})"
    if "schema_keyword" in entry:
        got = {e.validator for e in errors}
        assert entry["schema_keyword"] in got, f"{name}: schema keywords {sorted(got)}"


def test_pattern_trap_rejects_a_final_newline_in_every_pattern():
    # Python re `$` matches before a final newline; each pattern must not.
    base = json.loads((VALID / "both-layers.json").read_text(encoding="utf-8"))
    v = validator()
    for field in ("schema_version", "engine_version", "date", "loudness_hash"):
        doc = dict(base)
        doc[field] = base[field] + "\n"
        assert not v.is_valid(doc), f"{field}: a trailing newline passed the pattern"


def test_seed_integer_form_is_accepted_and_loads_as_seven():
    tool = load_tool()
    value = tool.strict_loads((VALID / "minimal-seed-7-0.json").read_bytes())
    assert value["seed"] == 7
    assert validator().is_valid(value)


@pytest.mark.parametrize("case", sorted(BAD_UTF8))
def test_bad_utf8_is_rejected_by_the_strict_loader(case):
    tool = load_tool()
    data = (VALID / "both-layers.json").read_bytes()
    assert b"Arcani test fixtures" in data
    bad = data.replace(b"Arcani test", b"Arcani " + BAD_UTF8[case] + b" test", 1)
    with pytest.raises(tool.StrictJSONError) as info:
        tool.strict_loads(bad)
    assert info.value.rule == "json.invalid_utf8"
    assert info.value.offset == data.index(b"Arcani test") + len(b"Arcani ")


def test_strict_loader_rules_cover_every_json_rule():
    used = {e["rule"] for e in expected().values() if e.get("rule", "").startswith("json.")}
    assert used | {"json.invalid_utf8"} == JSON_RULES


@pytest.mark.parametrize("text, rule", [
    (b'{"a":1,"a":2}', "json.duplicate_key"),
    (b'{"a":1,"\\u0061":2}', "json.duplicate_key"),
    (b"[1,]", "json.trailing_comma"),
    (b'{"a":1,}', "json.trailing_comma"),
    (b"[NaN]", "json.non_finite"),
    (b"[Infinity]", "json.non_finite"),
    (b"[-Infinity]", "json.non_finite"),
    (b"[1e400]", "json.number_overflow"),
    (b"[-1.7976931348623159e308]", "json.number_overflow"),
    (b"[01]", "json.leading_zero"),
    (b"[-01]", "json.leading_zero"),
    (b"[1]//c", "json.comment"),
    (b"/*c*/[1]", "json.comment"),
    (b'["\\ud800"]', "json.lone_surrogate"),
    (b'["\\udc00"]', "json.lone_surrogate"),
    (b'["\\ud800\\u0041"]', "json.lone_surrogate"),
    (b"\xef\xbb\xbf[1]", "json.bom"),
    (b"[" * 100000 + b"]" * 100000, "json.depth"),
])
def test_strict_loader_names_each_rule(text, rule):
    tool = load_tool()
    with pytest.raises(tool.StrictJSONError) as info:
        tool.strict_loads(text)
    assert info.value.rule == rule


@pytest.mark.parametrize("text", [
    b"[1 2]", b"{a:1}", b'["\x01"]', b"['a']", b"[1.]", b"[.5]", b"[1e]", b"[+1]",
    b'["\\x"]', b"", b"[1] [2]", b"[tru]",
])
def test_strict_loader_rejects_other_malformed_input(text):
    tool = load_tool()
    with pytest.raises(tool.StrictJSONError):
        tool.strict_loads(text)


ERROR_VECTORS = REPO_ROOT / "tests" / "data" / "json_error_vectors.json"


def error_vectors():
    return json.loads(ERROR_VECTORS.read_text(encoding="utf-8"))["cases"]


def test_error_vectors_cover_every_json_rule():
    rules = {c["rule"] for c in error_vectors()}
    assert JSON_RULES <= rules
    used = {e["rule"] for e in expected().values() if e.get("rule", "").startswith("json.")}
    assert used <= rules


@pytest.mark.parametrize("case", error_vectors(), ids=lambda c: c["name"])
def test_strict_loader_matches_the_shared_rule_and_offset(case):
    # tests/cpp/test_json.cpp runs the same vectors against the engine parser.
    tool = load_tool()
    with pytest.raises(tool.StrictJSONError) as info:
        tool.strict_loads(bytes.fromhex(case["input_hex"]))
    assert (info.value.rule, info.value.offset) == (case["rule"], case["offset"])


def test_strict_loader_accepts_largest_finite_and_surrogate_pairs():
    tool = load_tool()
    assert tool.strict_loads(b"[1.7976931348623158e308]") == [1.7976931348623157e308]
    assert tool.strict_loads(b'["\\ud83d\\ude00"]') == ["\U0001F600"]
    assert tool.strict_loads('["é"]'.encode("utf-8")) == ["é"]
