"""RFC 8785 canonical JSON, ECMAScript number text, and SHA-256 vectors (Story 1.1).

Data files (shared with tests/cpp/test_json.cpp and test_sha256.cpp):

- tests/data/rfc8785_vectors.json: the RFC's own examples. `canonicalize`
  cases hold input and expected output as text and as UTF-8 hex; `numbers`
  is the Appendix B table (bits as big-endian hex; NaN and Infinity rows have
  `text` null and must be rejected).
- tests/data/number_format_vectors.json: 10,000 finite binary64 values from
  splitmix64 (seed in the file, non-finite draws skipped) plus edge values,
  each as [bits hex, ECMAScript text].
- tests/data/sha256_vectors.json: FIPS 180-4 and NIST example messages.

This file checks the data against an independent ECMAScript formatter built
here on Python's shortest round-trip repr, then checks tools/recipe_hash.py
against the data.

Contract with tools/recipe_hash.py (loaded by path, standard library only):

- `format_number(x: float) -> str`: ECMAScript Number serialization
  (RFC 8785 section 3.2.2.3); -0 gives "0"; NaN or an infinity raises
  ValueError.
- `canonicalize(value) -> bytes`: RFC 8785 UTF-8 bytes of any JSON value
  from `strict_loads` (generic JSON, not recipe-specific). Keys sort by
  UTF-16 code units; an int is formatted as the binary64 it equals.
- `strict_loads(data: bytes)`, see test_recipe_fixtures.py.
"""

import hashlib
import importlib.util
import json
import struct
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "tests" / "data"
RFC = DATA / "rfc8785_vectors.json"
NUMBERS = DATA / "number_format_vectors.json"
SHA = DATA / "sha256_vectors.json"
TOOL = REPO_ROOT / "tools" / "recipe_hash.py"
MASK64 = (1 << 64) - 1


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_tool():
    assert TOOL.is_file(), f"missing {TOOL}"
    spec = importlib.util.spec_from_file_location("recipe_hash", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def from_bits(h):
    return struct.unpack(">d", bytes.fromhex(h))[0]


def to_bits(x):
    return struct.pack(">d", x).hex()


def es_format(x):
    """Independent ECMAScript Number::toString from Python's shortest repr."""
    if x != x or x in (float("inf"), float("-inf")):
        raise ValueError("not finite")
    if x == 0:
        return "0"
    if x < 0:
        return "-" + es_format(-x)
    mantissa, _, exp = repr(x).partition("e")
    exp = int(exp) if exp else 0
    ip, _, fp = mantissa.partition(".")
    digits = (ip + fp).lstrip("0").rstrip("0") or "0"
    if ip.strip("0"):
        n = len(ip.lstrip("0")) + exp
    else:
        n = -(len(fp) - len(fp.lstrip("0"))) + exp
    k = len(digits)
    if k <= n <= 21:
        return digits + "0" * (n - k)
    if 0 < n <= 21:
        return digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return "0." + "0" * (-n) + digits
    e = n - 1
    head = digits[0] + ("." + digits[1:] if k > 1 else "")
    return f"{head}e{'+' if e >= 0 else '-'}{abs(e)}"


def splitmix64(seed):
    state = seed
    while True:
        state = (state + 0x9E3779B97F4A7C15) & MASK64
        z = state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        yield z ^ (z >> 31)


# --- the data files themselves -------------------------------------------

def test_rfc_number_table_matches_the_independent_formatter():
    rows = load_json(RFC)["numbers"]
    assert len(rows) == 26
    for row in rows:
        x = from_bits(row["bits"])
        if row["text"] is None:
            with pytest.raises(ValueError):
                es_format(x)
        else:
            assert es_format(x) == row["text"], row


def test_rfc_canonical_cases_are_consistent():
    cases = load_json(RFC)["canonicalize"]
    assert [c["name"] for c in cases][:2] == ["key-sorting", "whitespace-numbers-escaping"]
    for c in cases:
        assert bytes.fromhex(c["input_utf8_hex"]) == c["input"].encode("utf-8")
        assert bytes.fromhex(c["canonical_utf8_hex"]) == c["canonical"].encode("utf-8")
    sort_out = json.loads(cases[0]["canonical"])
    assert list(sort_out) == ["\r", "1", "\u0080", "ö", "€", "\U0001F600", "דּ"]
    # RFC 8785 section 3.2.4, output exactly as printed in the RFC.
    assert cases[1]["canonical"] == (
        '{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
        '"string":"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}')


def test_number_vectors_are_the_seeded_draws_and_match_the_formatter():
    data = load_json(NUMBERS)
    assert data["generator"] == "splitmix64" and data["count"] == 10000
    draws = splitmix64(data["seed"])
    want = []
    while len(want) < data["count"]:
        u = next(draws)
        if (u >> 52) & 0x7FF != 0x7FF:
            want.append(f"{u:016x}")
    assert [b for b, _ in data["random"]] == want
    for bits, text in data["random"] + data["edges"]:
        x = from_bits(bits)
        assert es_format(x) == text, bits
        assert float(text) == x
    edge_bits = {b for b, _ in data["edges"]}
    for needed in ("8000000000000000", "0000000000000001", "000fffffffffffff",
                   "7fefffffffffffff", to_bits(1e21), to_bits(1e-7)):
        assert needed in edge_bits, needed


def test_sha256_vectors_match_hashlib():
    vectors = load_json(SHA)["vectors"]
    assert {v["name"] for v in vectors} >= {"empty", "abc", "two-block-448-bit", "one-million-a"}
    for v in vectors:
        message = (v["input_ascii"] * v["repeat"]).encode("ascii")
        assert hashlib.sha256(message).hexdigest() == v["sha256"], v["name"]


# --- tools/recipe_hash.py --------------------------------------------------

def test_tool_canonicalizes_the_rfc_examples():
    tool = load_tool()
    for c in load_json(RFC)["canonicalize"]:
        value = tool.strict_loads(bytes.fromhex(c["input_utf8_hex"]))
        assert tool.canonicalize(value) == bytes.fromhex(c["canonical_utf8_hex"]), c["name"]


def test_tool_formats_the_rfc_number_table():
    tool = load_tool()
    for row in load_json(RFC)["numbers"]:
        x = from_bits(row["bits"])
        if row["text"] is None:
            with pytest.raises(ValueError):
                tool.format_number(x)
        else:
            assert tool.format_number(x) == row["text"], row["bits"]


def test_tool_formats_seeded_and_edge_values_and_they_round_trip():
    tool = load_tool()
    data = load_json(NUMBERS)
    for bits, text in data["random"] + data["edges"]:
        x = from_bits(bits)
        got = tool.format_number(x)
        assert got == text, bits
        back = float(got)
        assert back == x and (to_bits(back) == bits or x == 0), bits


@pytest.mark.parametrize("text, want", [
    (b"7.0", b"7"),
    (b"1e0", b"1"),
    (b"-0", b"0"),
    (b"-0.0", b"0"),
    (b"9007199254740991", b"9007199254740991"),
    (b'{"seed":7.0}', b'{"seed":7}'),
    (b"[1.0, 1e0, 10E-1, 0.1e1]", b"[1,1,1,1]"),
    (b'"\\u0031.0"', b'"1.0"'),
    (b'{"b":[],"a":{}}', b'{"a":{},"b":[]}'),
])
def test_tool_canonical_forms(text, want):
    tool = load_tool()
    assert tool.canonicalize(tool.strict_loads(text)) == want


def test_tool_canonicalizer_is_generic_json():
    tool = load_tool()
    value = {"z": [None, True, False, "x"], "\U0001F600": 1, "דּ": 2, "a": {"b": 0.5}}
    assert tool.canonicalize(value) == (
        '{"a":{"b":0.5},"z":[null,true,false,"x"],"\U0001F600":1,"דּ":2}').encode("utf-8")
