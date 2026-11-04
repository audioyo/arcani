"""Recipe hash, independent of the engine (Story 1.1). Standard library only.

Recipe hash: parse the recipe strictly, remove every property the schema tags
`hash-excluded`, write the rest as RFC 8785 canonical JSON, SHA-256 the UTF-8
bytes, and print lowercase hex. The engine computes the same hash in
engine/src/recipe/; tests/data/recipe_hash_vectors.json holds the agreed
values for every valid fixture.

The strict loader applies the engine parser's rules (RFC 8259 plus I-JSON):
no byte order mark, valid UTF-8, no comments, no trailing commas, no leading
zeros, no NaN or Infinity, no number that overflows binary64, no duplicate
keys, no lone surrogate escapes, and nesting no deeper than MAX_DEPTH.

This tool checks JSON syntax only, not the recipe schema: a recipe the
schema rejects still gets a hash here, and that hash means nothing. Validate
against recipes/recipe.schema.json (or parse with the engine) first.

Usage:
  python tools/recipe_hash.py RECIPE.json [...]   print each recipe hash
  python tools/recipe_hash.py --write-vectors     refresh the vectors file
"""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "recipes" / "recipe.schema.json"
VALID_DIR = REPO_ROOT / "recipes" / "fixtures" / "valid"
VECTORS_PATH = REPO_ROOT / "tests" / "data" / "recipe_hash_vectors.json"

# Same limit as the engine (engine/src/json/value.hpp, kMaxDepth). "[]" is depth 1.
MAX_DEPTH = 64
HASH_EXCLUDED = "hash-excluded"


class StrictJSONError(ValueError):
    """A strict-parse fault: `rule` is the engine rule id, `offset` a byte offset."""

    def __init__(self, rule, offset, message=""):
        super().__init__(f"{rule} at byte {offset}" + (f": {message}" if message else ""))
        self.rule = rule
        self.offset = offset


# --- strict loader ---------------------------------------------------------

_WS = " \t\n\r"
_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
_HEX = "0123456789abcdefABCDEF"


class _Parser:
    def __init__(self, text, data):
        self.s = text
        self.data = data
        self.i = 0

    def fail(self, rule, index=None):
        index = self.i if index is None else index
        raise StrictJSONError(rule, len(self.s[:index].encode("utf-8")))

    def peek(self):
        return self.s[self.i] if self.i < len(self.s) else ""

    def ws(self):
        s = self.s
        while self.i < len(s):
            c = s[self.i]
            if c in _WS:
                self.i += 1
            elif c == "/":
                self.fail("json.comment" if s[self.i + 1:self.i + 2] in ("/", "*") else "json.unexpected_char")
            else:
                return

    def value(self, depth):
        c = self.peek()
        if c == "{":
            return self.obj(depth + 1)
        if c == "[":
            return self.arr(depth + 1)
        if c == '"':
            return self.string()
        if c != "" and c in "-0123456789":
            return self.number()
        for word, val in (("true", True), ("false", False), ("null", None)):
            if c == word[0]:
                if self.s.startswith(word, self.i):
                    self.i += len(word)
                    return val
                self.fail("json.invalid_literal")
        if self.s.startswith("NaN", self.i) or self.s.startswith("Infinity", self.i):
            self.fail("json.non_finite")
        if c == "":
            self.fail("json.unexpected_end")
        self.fail("json.unexpected_char")

    def enter(self, depth):
        if depth > MAX_DEPTH:
            self.fail("json.depth")
        self.i += 1
        self.ws()

    def arr(self, depth):
        self.enter(depth)
        out = []
        if self.peek() == "]":
            self.i += 1
            return out
        while True:
            out.append(self.value(depth))
            self.ws()
            c = self.peek()
            if c == ",":
                self.i += 1
                self.ws()
                if self.peek() == "]":
                    self.fail("json.trailing_comma")
            elif c == "]":
                self.i += 1
                return out
            else:
                self.fail("json.unexpected_end" if c == "" else "json.expected_comma")

    def obj(self, depth):
        self.enter(depth)
        out = {}
        if self.peek() == "}":
            self.i += 1
            return out
        while True:
            if self.peek() != '"':
                self.fail("json.unexpected_end" if self.peek() == "" else "json.expected_key")
            at = self.i
            key = self.string()
            if key in out:
                self.fail("json.duplicate_key", at)
            self.ws()
            if self.peek() != ":":
                self.fail("json.unexpected_end" if self.peek() == "" else "json.expected_colon")
            self.i += 1
            self.ws()
            out[key] = self.value(depth)
            self.ws()
            c = self.peek()
            if c == ",":
                self.i += 1
                self.ws()
                if self.peek() == "}":
                    self.fail("json.trailing_comma")
            elif c == "}":
                self.i += 1
                return out
            else:
                self.fail("json.unexpected_end" if c == "" else "json.expected_comma")

    def hex4(self, at):
        h = self.s[at:at + 4]
        if len(h) != 4 or any(ch not in _HEX for ch in h):
            self.fail("json.invalid_escape", at - 2)
        return int(h, 16)

    def string(self):
        s = self.s
        self.i += 1
        parts = []
        start = self.i
        while True:
            if self.i >= len(s):
                self.fail("json.unexpected_end")
            c = s[self.i]
            if c == '"':
                parts.append(s[start:self.i])
                self.i += 1
                return "".join(parts)
            if c < " ":
                self.fail("json.control_character")
            if c != "\\":
                self.i += 1
                continue
            parts.append(s[start:self.i])
            esc = s[self.i + 1:self.i + 2]
            if esc in _ESCAPES:
                parts.append(_ESCAPES[esc])
                self.i += 2
            elif esc == "u":
                at = self.i
                cp = self.hex4(self.i + 2)
                self.i += 6
                if 0xDC00 <= cp <= 0xDFFF:
                    self.fail("json.lone_surrogate", at)
                if 0xD800 <= cp <= 0xDBFF:
                    if s[self.i:self.i + 2] != "\\u":
                        self.fail("json.lone_surrogate", at)
                    low = self.hex4(self.i + 2)
                    if not 0xDC00 <= low <= 0xDFFF:
                        self.fail("json.lone_surrogate", at)
                    self.i += 6
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00)
                parts.append(chr(cp))
            else:
                self.fail("json.unexpected_end" if esc == "" else "json.invalid_escape")
            start = self.i

    def number(self):
        s = self.s
        start = self.i
        if self.peek() == "-":
            self.i += 1
            if s.startswith("Infinity", self.i):
                self.fail("json.non_finite", start)
        digits = "0123456789"
        c = self.peek()
        if c == "0":
            self.i += 1
            if self.peek() != "" and self.peek() in digits:
                self.fail("json.leading_zero", start)
        elif c != "" and c in "123456789":
            while self.peek() != "" and self.peek() in digits:
                self.i += 1
        else:
            self.fail("json.invalid_number", start)
        is_int = True
        if self.peek() == ".":
            is_int = False
            self.i += 1
            if not (self.peek() != "" and self.peek() in digits):
                self.fail("json.invalid_number", start)
            while self.peek() != "" and self.peek() in digits:
                self.i += 1
        if self.peek() in ("e", "E"):
            is_int = False
            self.i += 1
            if self.peek() in ("+", "-"):
                self.i += 1
            if not (self.peek() != "" and self.peek() in digits):
                self.fail("json.invalid_number", start)
            while self.peek() != "" and self.peek() in digits:
                self.i += 1
        text = s[start:self.i]
        if is_int:
            # A JSON integer with more digits than binary64 can reach overflows.
            if len(text.lstrip("-")) > 309:
                self.fail("json.number_overflow", start)
            value = int(text)
            try:
                float(value)
            except OverflowError:
                self.fail("json.number_overflow", start)
            return value
        value = float(text)
        if math.isinf(value):
            self.fail("json.number_overflow", start)
        return value


def strict_loads(data):
    """Parses UTF-8 JSON bytes under the engine's strict rules."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    data = bytes(data)
    if data.startswith(b"\xef\xbb\xbf"):
        raise StrictJSONError("json.bom", 0)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as err:
        raise StrictJSONError("json.invalid_utf8", err.start) from None
    p = _Parser(text, data)
    p.ws()
    value = p.value(0)
    p.ws()
    if p.i != len(text):
        p.fail("json.trailing_data")
    return value


# --- RFC 8785 --------------------------------------------------------------

def format_number(x):
    """ECMAScript Number serialization (RFC 8785 section 3.2.2.3)."""
    x = float(x)
    if math.isnan(x) or math.isinf(x):
        raise ValueError("JSON numbers must be finite")
    if x == 0:
        return "0"
    if x < 0:
        return "-" + format_number(-x)
    # repr gives the shortest round-trip digits, the closest to x among them.
    mantissa, _, exp = repr(x).partition("e")
    int_part, _, frac_part = mantissa.partition(".")
    all_digits = int_part + frac_part
    stripped = all_digits.lstrip("0")
    point = len(int_part) - (len(all_digits) - len(stripped)) + (int(exp) if exp else 0)
    digits = stripped.rstrip("0")
    k, n = len(digits), point
    if k <= n <= 21:
        return digits + "0" * (n - k)
    if 0 < n <= 21:
        return digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return "0." + "0" * (-n) + digits
    e = n - 1
    head = digits[0] + ("." + digits[1:] if k > 1 else "")
    return f"{head}e{'+' if e >= 0 else '-'}{abs(e)}"


def _string(s):
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif o < 0x20:
            short = {0x08: "\\b", 0x09: "\\t", 0x0A: "\\n", 0x0C: "\\f", 0x0D: "\\r"}.get(o)
            out.append(short if short else f"\\u{o:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _utf16_key(s):
    return s.encode("utf-16-be", errors="surrogatepass")


def _canon(value, out):
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, (int, float)):
        try:
            out.append(format_number(float(value)))
        except OverflowError:
            raise ValueError(f"integer {value} does not fit binary64") from None
    elif isinstance(value, str):
        out.append(_string(value))
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for i, item in enumerate(value):
            if i:
                out.append(",")
            _canon(item, out)
        out.append("]")
    elif isinstance(value, dict):
        out.append("{")
        for i, key in enumerate(sorted(value, key=_utf16_key)):
            if not isinstance(key, str):
                raise TypeError(f"object key {key!r} is not a string")
            if i:
                out.append(",")
            out.append(_string(key))
            out.append(":")
            _canon(value[key], out)
        out.append("}")
    else:
        raise TypeError(f"not a JSON value: {type(value).__name__}")


def canonicalize(value):
    """RFC 8785 canonical UTF-8 bytes of any JSON value."""
    out = []
    _canon(value, out)
    return "".join(out).encode("utf-8")


# --- schema tags and the recipe hash -----------------------------------------

def load_schema():
    return strict_loads(SCHEMA_PATH.read_bytes())


def _resolve(schema, node):
    for _ in range(16):
        ref = node.get("$ref")
        if ref is None:
            return node
        if not ref.startswith("#/"):
            raise ValueError(f"only local $ref is supported, got {ref}")
        node = schema
        for part in ref[2:].split("/"):
            node = node[part.replace("~1", "/").replace("~0", "~")]
    raise ValueError("$ref chain too long")


def _pointer_part(name):
    return name.replace("~", "~0").replace("/", "~1")


def load_tags(schema):
    """JSON Pointer of every schema property to its x-arcani-tag."""
    tags = {}

    def walk(node, prefix):
        node = _resolve(schema, node)
        for name, prop in node.get("properties", {}).items():
            pointer = f"{prefix}/{_pointer_part(name)}"
            target = _resolve(schema, prop)
            tags[pointer] = prop.get("x-arcani-tag", target.get("x-arcani-tag"))
            if target.get("type") == "object":
                walk(prop, pointer)

    walk(schema, "")
    return tags


def _strip(value, prefix, excluded):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            pointer = f"{prefix}/{_pointer_part(key)}"
            if pointer not in excluded:
                out[key] = _strip(item, pointer, excluded)
        return out
    return value


def hash_value(value, schema=None):
    """Recipe hash of a parsed recipe: 64 lowercase hex digits."""
    tags = load_tags(load_schema() if schema is None else schema)
    excluded = {p for p, t in tags.items() if t == HASH_EXCLUDED}
    return hashlib.sha256(canonicalize(_strip(value, "", excluded))).hexdigest()


def hash_bytes(data, schema=None):
    return hash_value(strict_loads(data), schema)


def compute_vectors():
    schema = load_schema()
    return {p.name: hash_bytes(p.read_bytes(), schema) for p in sorted(VALID_DIR.glob("*.json"))}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Recipe hash: SHA-256 over RFC 8785 canonical "
                                     "JSON minus the schema's hash-excluded fields. Checks JSON "
                                     "syntax only, not the schema: the hash of a recipe the "
                                     "schema rejects means nothing.")
    parser.add_argument("recipes", nargs="*", type=Path, help="recipe files to hash")
    parser.add_argument("--write-vectors", action="store_true",
                        help=f"write every valid fixture's hash to {VECTORS_PATH.relative_to(REPO_ROOT).as_posix()}")
    args = parser.parse_args(argv)
    if args.write_vectors:
        text = json.dumps(compute_vectors(), indent=2, sort_keys=True) + "\n"
        VECTORS_PATH.write_bytes(text.encode("utf-8"))
        print(f"wrote {VECTORS_PATH}")
    schema = load_schema() if args.recipes else None
    status = 0
    for path in args.recipes:
        try:
            print(f"{hash_bytes(path.read_bytes(), schema)}  {path}")
        except (StrictJSONError, OSError) as err:
            print(f"{path}: {err}", file=sys.stderr)
            status = 1
    if not args.write_vectors and not args.recipes:
        parser.print_help()
    return status


if __name__ == "__main__":
    sys.exit(main())
