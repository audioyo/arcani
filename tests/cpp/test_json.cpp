// Engine strict JSON parser, number text conversion, and RFC 8785
// canonicalizer (Story 1.1). Vectors: tests/data/rfc8785_vectors.json (the
// RFC's examples) and tests/data/number_format_vectors.json (10,000 seeded
// binary64 values plus edges, formatted by Python; see
// tests/python/test_recipe_canonical.py). Inputs and expected outputs are
// stored as hex, so reading them needs only plain ASCII strings.
//
// Expected interface (engine/src/json/, namespace arcani::json; C++20
// standard library only, no exceptions thrown, no file I/O):
//
// json/value.hpp
//   enum class Kind { Null, Bool, Number, String, Array, Object };
//   class Value {
//    public:
//     Kind kind() const noexcept;
//     bool boolean() const noexcept;
//     double number() const noexcept;
//     bool integral() const noexcept;      // number has no fractional part (7, 7.0, 1e0)
//     const std::string& string() const noexcept;   // UTF-8, escapes decoded
//     const std::vector<Value>& array() const noexcept;
//     const std::vector<std::pair<std::string, Value>>& object() const noexcept;  // document order
//     const Value* find(std::string_view key) const noexcept;  // nullptr if absent
//   };
//   struct Error {
//     std::size_t offset;   // byte offset of the fault
//     std::string rule;     // json.duplicate_key, json.trailing_comma, json.non_finite,
//                           // json.number_overflow, json.leading_zero, json.comment,
//                           // json.lone_surrogate, json.bom, json.invalid_utf8, json.depth,
//                           // or another json.* rule for other syntax faults
//     std::string value;    // offending text, may be empty
//     std::string limit;    // for json.depth: std::to_string(kMaxDepth)
//   };
//   struct ParseResult { std::optional<Value> value; Error error; };  // value empty on error
//   inline constexpr std::size_t kMaxDepth = ...;  // "[]" is depth 1; deeper input is
//                                                  // rejected without unbounded recursion
//   ParseResult parse(std::string_view utf8);      // RFC 8259 plus I-JSON, strict
//
// json/number.hpp
//   std::string format_number(double x);  // ECMAScript Number serialization (RFC 8785
//                                         // 3.2.2.3); -0 gives "0"; x must be finite
//   bool parse_number(std::string_view text, double& out);  // RFC 8259 number grammar,
//                                         // correctly rounded; false on bad grammar or
//                                         // overflow to infinity
//
// json/canonical.hpp
//   std::string canonicalize(const Value& v);  // RFC 8785 canonical UTF-8, generic JSON

#include <catch2/catch_test_macros.hpp>

#ifndef ARCANI_TEST_DATA_DIR
#error "ARCANI_TEST_DATA_DIR must name tests/data"
#endif

#if __has_include("json/value.hpp") && __has_include("json/number.hpp") && \
    __has_include("json/canonical.hpp")

#include "json/canonical.hpp"
#include "json/number.hpp"
#include "json/value.hpp"

#include <bit>
#include <cstdint>
#include <fstream>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace json = arcani::json;

namespace {

std::string read_file(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  REQUIRE(in.good());
  std::stringstream ss;
  ss << in.rdbuf();
  return ss.str();
}

std::string unhex(const std::string& hex) {
  REQUIRE(hex.size() % 2 == 0);
  std::string out;
  for (std::size_t i = 0; i < hex.size(); i += 2) {
    out += static_cast<char>(std::stoi(hex.substr(i, 2), nullptr, 16));
  }
  return out;
}

double from_bits(const std::string& hex) {
  return std::bit_cast<double>(static_cast<std::uint64_t>(std::stoull(hex, nullptr, 16)));
}

std::uint64_t bits(double x) { return std::bit_cast<std::uint64_t>(x); }

json::Value load(const std::string& name) {
  auto result = json::parse(read_file(std::string(ARCANI_TEST_DATA_DIR) + "/" + name));
  INFO(name << ": " << result.error.rule << " at " << result.error.offset);
  REQUIRE(result.value.has_value());
  return std::move(*result.value);
}

const json::Value& at(const json::Value& v, const char* key) {
  const json::Value* found = v.find(key);
  INFO(key);
  REQUIRE(found != nullptr);
  return *found;
}

std::string rule_of(std::string_view text) {
  const auto result = json::parse(text);
  if (result.value.has_value()) {
    return "accepted";
  }
  CHECK(result.error.offset <= text.size());
  return result.error.rule;
}

std::string nested(std::size_t depth) {
  return std::string(depth, '[') + std::string(depth, ']');
}

}  // namespace

TEST_CASE("canonicalize matches the RFC 8785 examples", "[json][rfc8785]") {
  const auto vectors = load("rfc8785_vectors.json");
  const auto& cases = at(vectors, "canonicalize").array();
  REQUIRE(cases.size() >= 4);
  for (const auto& c : cases) {
    INFO(at(c, "name").string());
    const auto parsed = json::parse(unhex(at(c, "input_utf8_hex").string()));
    REQUIRE(parsed.value.has_value());
    CHECK(json::canonicalize(*parsed.value) == unhex(at(c, "canonical_utf8_hex").string()));
  }
}

TEST_CASE("format_number matches the RFC 8785 Appendix B table", "[json][number]") {
  const auto vectors = load("rfc8785_vectors.json");
  int checked = 0;
  for (const auto& row : at(vectors, "numbers").array()) {
    const auto& text = at(row, "text");
    if (text.kind() == json::Kind::Null) {
      continue;  // NaN and Infinity: never reach the formatter (the parser rejects them)
    }
    const double x = from_bits(at(row, "bits").string());
    INFO(at(row, "bits").string());
    CHECK(json::format_number(x) == text.string());
    double back = 1.0;
    REQUIRE(json::parse_number(text.string(), back));
    CHECK(back == x);
    ++checked;
  }
  CHECK(checked == 24);
}

TEST_CASE("format_number equals Python's ECMAScript text for seeded and edge values",
          "[json][number]") {
  const auto vectors = load("number_format_vectors.json");
  const auto& random = at(vectors, "random").array();
  REQUIRE(random.size() == 10000);
  std::size_t mismatches = 0;
  std::size_t not_round_trip = 0;
  for (const auto* list : {&random, &at(vectors, "edges").array()}) {
    for (const auto& pair : *list) {
      const auto& hex = pair.array().at(0).string();
      const auto& want = pair.array().at(1).string();
      const double x = from_bits(hex);
      const std::string got = json::format_number(x);
      if (got != want) {
        if (mismatches < 10) {
          UNSCOPED_INFO(hex << ": got " << got << ", want " << want);
        }
        ++mismatches;
      }
      double back = 1.0;
      const bool ok = json::parse_number(got, back);
      if (!ok || (bits(back) != bits(x) && !(x == 0.0 && back == 0.0))) {
        ++not_round_trip;
      }
    }
  }
  CHECK(mismatches == 0);
  CHECK(not_round_trip == 0);
}

TEST_CASE("format_number handles signed zero and the exponent switch points", "[json][number]") {
  CHECK(json::format_number(-0.0) == "0");
  CHECK(json::format_number(0.0) == "0");
  CHECK(json::format_number(1e21) == "1e+21");
  CHECK(json::format_number(1e20) == "100000000000000000000");
  CHECK(json::format_number(1e-7) == "1e-7");
  CHECK(json::format_number(1e-6) == "0.000001");
  CHECK(json::format_number(std::bit_cast<double>(UINT64_C(0x0000000000000001))) == "5e-324");
  CHECK(json::format_number(std::bit_cast<double>(UINT64_C(0x7fefffffffffffff))) ==
        "1.7976931348623157e+308");
}

TEST_CASE("parse_number rounds correctly", "[json][number]") {
  // Expected bits from Python float(); hard halfway and boundary cases.
  const std::pair<const char*, std::uint64_t> cases[] = {
      {"2.2250738585072011e-308", UINT64_C(0x000fffffffffffff)},
      {"2.2250738585072012e-308", UINT64_C(0x0010000000000000)},
      {"4.9406564584124654e-324", UINT64_C(0x0000000000000001)},
      {"2.4703282292062327e-324", UINT64_C(0x0000000000000000)},
      {"2.4703282292062328e-324", UINT64_C(0x0000000000000001)},
      {"1e23", UINT64_C(0x44b52d02c7e14af6)},
      {"9007199254740993", UINT64_C(0x4340000000000000)},
      {"1.7976931348623158e308", UINT64_C(0x7fefffffffffffff)},
      {"0.1", UINT64_C(0x3fb999999999999a)},
      {"8.98846567431158e307", UINT64_C(0x7fe0000000000000)},
      {"1.00000000000000011102230246251565404236316680908203125", UINT64_C(0x3ff0000000000000)},
      {"1.00000000000000011102230246251565404236316680908203124", UINT64_C(0x3ff0000000000000)},
      {"1.00000000000000011102230246251565404236316680908203126", UINT64_C(0x3ff0000000000001)},
      {"123456789012345678901234567890e-10", UINT64_C(0x43e56a95319d63e1)},
      {"6e2", UINT64_C(0x4082c00000000000)},
      {"-0", UINT64_C(0x8000000000000000)},
  };
  for (const auto& [text, want] : cases) {
    INFO(text);
    double got = 1.0;
    REQUIRE(json::parse_number(text, got));
    CHECK(bits(got) == want);
  }
  double out = 0.0;
  CHECK_FALSE(json::parse_number("1.7976931348623159e308", out));
  CHECK_FALSE(json::parse_number("1e400", out));
  CHECK_FALSE(json::parse_number("01", out));
  CHECK_FALSE(json::parse_number("1.", out));
  CHECK_FALSE(json::parse_number("+1", out));
  CHECK_FALSE(json::parse_number("", out));
}

TEST_CASE("parse keeps the integral flag and decodes values", "[json]") {
  const auto r = json::parse(
      R"({"i":7,"f":7.0,"e":1e0,"x":1.5e1,"h":7.5,"s":"aé😀\n","t":true,"n":null,"a":[]})");
  REQUIRE(r.value.has_value());
  const auto& v = *r.value;
  REQUIRE(v.kind() == json::Kind::Object);
  CHECK(v.object().size() == 9);
  CHECK(v.object().front().first == "i");  // document order
  CHECK(at(v, "i").integral());
  CHECK(at(v, "f").integral());
  CHECK(at(v, "f").number() == 7.0);
  CHECK(at(v, "e").integral());
  CHECK(at(v, "x").integral());
  CHECK_FALSE(at(v, "h").integral());
  CHECK(at(v, "s").string() == "a\xc3\xa9\xf0\x9f\x98\x80\n");
  CHECK(at(v, "t").kind() == json::Kind::Bool);
  CHECK(at(v, "t").boolean());
  CHECK(at(v, "n").kind() == json::Kind::Null);
  CHECK(at(v, "a").array().empty());
  CHECK(v.find("missing") == nullptr);
  CHECK(json::canonicalize(at(v, "f")) == "7");
}

TEST_CASE("parse names each strict rule", "[json][strict]") {
  const std::pair<std::string, const char*> cases[] = {
      {R"({"a":1,"a":2})", "json.duplicate_key"},
      {R"({"a":1,"\u0061":2})", "json.duplicate_key"},
      {"[1,]", "json.trailing_comma"},
      {R"({"a":1,})", "json.trailing_comma"},
      {"[NaN]", "json.non_finite"},
      {"[Infinity]", "json.non_finite"},
      {"[-Infinity]", "json.non_finite"},
      {"[1e400]", "json.number_overflow"},
      {"[-1.7976931348623159e308]", "json.number_overflow"},
      {"[01]", "json.leading_zero"},
      {"[-01]", "json.leading_zero"},
      {"[1]//c", "json.comment"},
      {"/*c*/[1]", "json.comment"},
      {R"(["\ud800"])", "json.lone_surrogate"},
      {R"(["\udc00"])", "json.lone_surrogate"},
      {R"(["\ud800A"])", "json.lone_surrogate"},
      {R"(["\ud800\u0041"])", "json.lone_surrogate"},
      {"\xEF\xBB\xBF[1]", "json.bom"},
      {"[\"\x80\"]", "json.invalid_utf8"},
      {"[\"\xFF\"]", "json.invalid_utf8"},
      {"[\"\xC0\xAF\"]", "json.invalid_utf8"},
      {"[\"\xE2\x82\"]", "json.invalid_utf8"},
      {"[\"\xED\xA0\x80\"]", "json.invalid_utf8"},
      {"[\"\xF4\x90\x80\x80\"]", "json.invalid_utf8"},
  };
  for (const auto& [text, rule] : cases) {
    INFO(text);
    CHECK(rule_of(text) == rule);
  }
}

TEST_CASE("parse gives the shared rule and byte offset for each fault", "[json][strict]") {
  // tests/data/json_error_vectors.json; tests/python/test_recipe_fixtures.py
  // requires the same rule and offset from tools/recipe_hash.py.
  const auto vectors = load("json_error_vectors.json");
  const auto& cases = at(vectors, "cases").array();
  REQUIRE(cases.size() >= 20);
  for (const auto& c : cases) {
    INFO(at(c, "name").string());
    const std::string text = unhex(at(c, "input_hex").string());
    const auto r = json::parse(text);
    REQUIRE_FALSE(r.value.has_value());
    CHECK(r.error.rule == at(c, "rule").string());
    CHECK(r.error.offset == static_cast<std::size_t>(at(c, "offset").number()));
  }
}

TEST_CASE("parse rejects other malformed input", "[json][strict]") {
  const std::string cases[] = {
      "[1 2]", "{a:1}", std::string("[\"\x01\"]"), "['a']", "[1.]", "[.5]", "[1e]", "[+1]",
      R"(["\x"])", "", "[1] [2]", "[tru]", "[", "{\"a\"}", std::string("[1]\0", 4),
  };
  for (const auto& text : cases) {
    INFO(text);
    const auto rule = rule_of(text);
    CHECK(rule != "accepted");
    CHECK(rule.rfind("json.", 0) == 0);
  }
}

TEST_CASE("parse enforces the nesting limit without deep recursion", "[json][strict]") {
  REQUIRE(json::kMaxDepth >= 16);
  CHECK(json::parse(nested(json::kMaxDepth)).value.has_value());
  const auto over = json::parse(nested(json::kMaxDepth + 1));
  REQUIRE_FALSE(over.value.has_value());
  CHECK(over.error.rule == "json.depth");
  CHECK(over.error.limit == std::to_string(json::kMaxDepth));
  const auto huge = json::parse(nested(1000000));
  REQUIRE_FALSE(huge.value.has_value());
  CHECK(huge.error.rule == "json.depth");
  std::string objects;
  for (std::size_t i = 0; i <= json::kMaxDepth; ++i) {
    objects += "{\"k\":";
  }
  objects += "1" + std::string(json::kMaxDepth + 1, '}');
  CHECK(rule_of(objects) == "json.depth");
}

TEST_CASE("parse accepts the largest finite number and whitespace", "[json]") {
  const auto r = json::parse(" \t\r\n[1.7976931348623158e308 , -0 ,1E+2]\n");
  REQUIRE(r.value.has_value());
  const auto& a = r.value->array();
  REQUIRE(a.size() == 3);
  CHECK(bits(a[0].number()) == UINT64_C(0x7fefffffffffffff));
  CHECK(json::canonicalize(*r.value) == "[1.7976931348623157e+308,0,100]");
}

#else

TEST_CASE("json parser, number conversion, and canonicalizer are implemented", "[json]") {
  FAIL("not implemented: json/value.hpp, json/number.hpp, json/canonical.hpp");
}

#endif
