// Engine recipe parse stage, field table, and recipe hash (Story 1.1).
// Shared data: recipes/recipe.schema.json, recipes/fixtures/valid|invalid
// (the folder is the verdict), recipes/fixtures/invalid-expected.json (the
// expected error per invalid fixture), and tests/data/recipe_hash_vectors.json
// (fixture name to hash, written by tools/recipe_hash.py). The same fixtures
// are judged in Python by tests/python/test_recipe_fixtures.py.
//
// Expected interface (engine/src/recipe/, namespace arcani::recipe; C++20
// standard library only, no exceptions thrown, no file I/O):
//
// recipe/field_table.hpp
//   enum class FieldType { String, Number, Integer, Object };
//   enum class FieldTag { None, HashExcluded, LoudnessRelevant };
//   struct Field {
//     std::string_view path;   // JSON Pointer, for example "/binaural/beat_rate_hz"
//     FieldType type;
//     FieldTag tag;            // schema x-arcani-tag: none, hash-excluded, loudness-relevant
//     bool required;           // required within its parent object
//   };
//   std::span<const Field> fields() noexcept;  // every schema property, objects included
//
// recipe/recipe.hpp
//   struct Error {
//     std::string parameter;  // JSON Pointer of the field ("" = whole document), or for
//                             // a syntax fault the byte offset in decimal digits
//     std::string value;
//     std::string rule;       // unknown_property, required, type, pattern,
//                             // schema_version.major, or the json.* parser rule
//     std::string limit;      // schema_version.major: the supported majors, "1"
//   };
//   struct ThetaReference { double carrier_hz; };
//   struct Binaural { double carrier_left_hz; double beat_rate_hz; };
//   struct Recipe {
//     std::string schema_version, engine_version;
//     std::uint64_t seed;
//     std::string author, date, rationale;
//     double length_s, loudness_target_lufs;
//     std::optional<double> loudness_gain_db;
//     std::optional<std::string> loudness_hash;
//     std::optional<ThetaReference> theta_reference;
//     std::optional<Binaural> binaural;
//     std::string hash;  // recipe hash: SHA-256 of the RFC 8785 form minus hash-excluded
//                        // fields, 64 lowercase hex digits
//   };
//   struct ParseResult { std::optional<Recipe> recipe; Error error; };  // recipe empty on error
//   ParseResult parse(std::string_view utf8);

#include <catch2/catch_test_macros.hpp>

#ifndef ARCANI_RECIPES_DIR
#error "ARCANI_RECIPES_DIR must name recipes/"
#endif
#ifndef ARCANI_TEST_DATA_DIR
#error "ARCANI_TEST_DATA_DIR must name tests/data"
#endif

#if __has_include("recipe/recipe.hpp") && __has_include("recipe/field_table.hpp") && \
    __has_include("json/value.hpp")

#include "crypto/sha256.hpp"
#include "json/value.hpp"
#include "recipe/field_table.hpp"
#include "recipe/recipe.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <vector>

namespace fs = std::filesystem;
namespace json = arcani::json;
namespace recipe = arcani::recipe;
namespace crypto = arcani::crypto;

namespace {

const std::string kRecipes = ARCANI_RECIPES_DIR;
const std::string kData = ARCANI_TEST_DATA_DIR;

std::string read_file(const fs::path& path) {
  std::ifstream in(path, std::ios::binary);
  INFO(path.string());
  REQUIRE(in.good());
  std::stringstream ss;
  ss << in.rdbuf();
  return ss.str();
}

std::vector<std::string> fixture_names(const std::string& folder) {
  std::vector<std::string> out;
  for (const auto& entry : fs::directory_iterator(kRecipes + "/fixtures/" + folder)) {
    if (entry.path().extension() == ".json") {
      out.push_back(entry.path().filename().string());
    }
  }
  std::sort(out.begin(), out.end());
  return out;
}

std::string fixture(const std::string& folder, const std::string& name) {
  return read_file(kRecipes + "/fixtures/" + folder + "/" + name);
}

json::Value parse_json_file(const fs::path& path) {
  auto r = json::parse(read_file(path));
  INFO(path.string() << ": " << r.error.rule << " at " << r.error.offset);
  REQUIRE(r.value.has_value());
  return std::move(*r.value);
}

const json::Value* member(const json::Value& v, const char* key) {
  return v.kind() == json::Kind::Object ? v.find(key) : nullptr;
}

const char* tag_name(recipe::FieldTag t) {
  switch (t) {
    case recipe::FieldTag::None:
      return "none";
    case recipe::FieldTag::HashExcluded:
      return "hash-excluded";
    case recipe::FieldTag::LoudnessRelevant:
      return "loudness-relevant";
  }
  return "?";
}

const char* type_name(recipe::FieldType t) {
  switch (t) {
    case recipe::FieldType::String:
      return "string";
    case recipe::FieldType::Number:
      return "number";
    case recipe::FieldType::Integer:
      return "integer";
    case recipe::FieldType::Object:
      return "object";
  }
  return "?";
}

// path -> (type, tag, required)
using FieldMap = std::map<std::string, std::tuple<std::string, std::string, bool>>;

const json::Value& resolve(const json::Value& root, const json::Value& node) {
  const json::Value* cur = &node;
  for (int hops = 0; hops < 8; ++hops) {
    const json::Value* ref = member(*cur, "$ref");
    if (ref == nullptr) {
      return *cur;
    }
    const std::string target = ref->string();
    REQUIRE(target.rfind("#/", 0) == 0);
    const json::Value* t = &root;
    std::stringstream parts(target.substr(2));
    std::string part;
    while (std::getline(parts, part, '/')) {
      t = member(*t, part.c_str());
      REQUIRE(t != nullptr);
    }
    cur = t;
  }
  FAIL("$ref chain too long");
  return node;
}

void walk(const json::Value& root, const json::Value& object, const std::string& prefix,
          FieldMap& out) {
  const json::Value& node = resolve(root, object);
  std::set<std::string> required;
  if (const auto* req = member(node, "required")) {
    for (const auto& name : req->array()) {
      required.insert(name.string());
    }
  }
  const json::Value* props = member(node, "properties");
  if (props == nullptr) {
    return;
  }
  for (const auto& [name, prop] : props->object()) {
    const std::string path = prefix + "/" + name;
    const json::Value& p = resolve(root, prop);
    const json::Value* type = member(p, "type");
    const json::Value* tag = member(prop, "x-arcani-tag");
    if (tag == nullptr) {
      tag = member(p, "x-arcani-tag");
    }
    INFO(path);
    REQUIRE(type != nullptr);
    REQUIRE(tag != nullptr);
    out[path] = {type->string(), tag->string(), required.count(name) == 1};
    if (type->string() == "object") {
      walk(root, p, path, out);
    }
  }
}

std::map<std::string, std::string> engine_hashes() {
  std::map<std::string, std::string> out;
  for (const auto& name : fixture_names("valid")) {
    const auto r = recipe::parse(fixture("valid", name));
    INFO(name << ": " << r.error.rule << " " << r.error.parameter);
    REQUIRE(r.recipe.has_value());
    out[name] = r.recipe->hash;
  }
  return out;
}

bool all_digits(const std::string& s) {
  return !s.empty() && std::all_of(s.begin(), s.end(), [](char c) { return c >= '0' && c <= '9'; });
}

}  // namespace

TEST_CASE("engine field table matches the schema exactly", "[recipe][schema]") {
  const auto schema = parse_json_file(kRecipes + "/recipe.schema.json");
  FieldMap from_schema;
  walk(schema, schema, "", from_schema);
  REQUIRE_FALSE(from_schema.empty());
  FieldMap from_engine;
  for (const auto& f : recipe::fields()) {
    const std::string path(f.path);
    INFO(path);
    CHECK(from_engine.count(path) == 0);
    from_engine[path] = {type_name(f.type), tag_name(f.tag), f.required};
  }
  for (const auto& [path, want] : from_schema) {
    INFO("schema field " << path);
    REQUIRE(from_engine.count(path) == 1);
    CHECK(from_engine.at(path) == want);
  }
  for (const auto& [path, _] : from_engine) {
    INFO("engine field " << path);
    CHECK(from_schema.count(path) == 1);
  }
}

TEST_CASE("engine accepts every valid fixture", "[recipe][fixtures]") {
  const auto names = fixture_names("valid");
  REQUIRE(names.size() >= 2);
  for (const auto& name : names) {
    const auto r = recipe::parse(fixture("valid", name));
    INFO(name << ": " << r.error.rule << " " << r.error.parameter << " " << r.error.value);
    CHECK(r.recipe.has_value());
  }
}

TEST_CASE("engine rejects every invalid fixture with the expected error", "[recipe][fixtures]") {
  const auto expected = parse_json_file(kRecipes + "/fixtures/invalid-expected.json");
  const json::Value* table = member(expected, "fixtures");
  REQUIRE(table != nullptr);
  const auto names = fixture_names("invalid");
  REQUIRE(names.size() == table->object().size());
  for (const auto& name : names) {
    INFO(name);
    const json::Value* want = table->find(name);
    REQUIRE(want != nullptr);
    const std::string text = fixture("invalid", name);
    const auto r = recipe::parse(text);
    INFO("got rule " << r.error.rule << ", parameter " << r.error.parameter << ", value "
                     << r.error.value << ", limit " << r.error.limit);
    REQUIRE_FALSE(r.recipe.has_value());
    CHECK_FALSE(r.error.rule.empty());
    if (const auto* rule = member(*want, "rule")) {
      CHECK(r.error.rule == rule->string());
      if (rule->string().rfind("json.", 0) == 0) {
        CHECK(all_digits(r.error.parameter));
        CHECK(std::stoull(r.error.parameter) <= text.size());
      }
    }
    if (const auto* param = member(*want, "parameter")) {
      CHECK(r.error.parameter == param->string());
    }
    if (const auto* value = member(*want, "value")) {
      CHECK(r.error.value == value->string());
    }
    if (const auto* limit = member(*want, "limit")) {
      CHECK(r.error.limit == limit->string());
    }
  }
}

TEST_CASE("engine rejects bad UTF-8 inside a recipe", "[recipe][fixtures]") {
  const std::string base = fixture("valid", "both-layers.json");
  const auto at = base.find("Arcani test");
  REQUIRE(at != std::string::npos);
  const std::string bad[] = {"\x80", "\xFF", "\xC0\xAF", "\xE2\x82", "\xED\xA0\x80",
                             "\xF4\x90\x80\x80"};
  for (const auto& seq : bad) {
    std::string text = base;
    text.insert(at + 7, seq + " ");
    const auto r = recipe::parse(text);
    REQUIRE_FALSE(r.recipe.has_value());
    CHECK(r.error.rule == "json.invalid_utf8");
    CHECK(r.error.parameter == std::to_string(at + 7));
  }
}

TEST_CASE("engine pattern checks reject a final newline in every patterned field",
          "[recipe][fixtures]") {
  // Mirrors the Python pattern-trap test: Python's $ matches before a final
  // newline, so each pattern (and the engine's hand-written check) must not.
  const std::string base = fixture("valid", "both-layers.json");
  for (const char* field : {"schema_version", "engine_version", "date", "loudness_hash"}) {
    INFO(field);
    const std::string key = std::string("\"") + field + "\": \"";
    const auto key_at = base.find(key);
    REQUIRE(key_at != std::string::npos);
    const auto close = base.find('"', key_at + key.size());
    REQUIRE(close != std::string::npos);
    std::string text = base;
    text.insert(close, "\\n");  // the JSON escape for a newline
    const auto r = recipe::parse(text);
    REQUIRE_FALSE(r.recipe.has_value());
    CHECK(r.error.rule == "pattern");
    CHECK(r.error.parameter == std::string("/") + field);
  }
}

TEST_CASE("recipe hash equals SHA-256 of the hand-written canonical text", "[recipe][hash]") {
  // Written out by hand from both-layers.json, not by any tool: hash-excluded
  // fields removed, keys sorted, integral numbers without a fraction. The hex
  // is hashlib.sha256 of this literal; tests/python/test_recipe_hash.py checks
  // the same literal against the Python tool.
  const std::string canonical =
      R"({"binaural":{"beat_rate_hz":6,"carrier_left_hz":400},"engine_version":"0.0.1",)"
      R"("length_s":600,"loudness_target_lufs":-16,"schema_version":"1.0","seed":42,)"
      R"("theta_reference":{"carrier_hz":200}})";
  const std::string want = "154db16986eae01f0cefdce72bf0e1b8fd38eaf5abcf69f61064cc77d3e11127";
  CHECK(crypto::sha256_hex(canonical) == want);
  const auto r = recipe::parse(fixture("valid", "both-layers.json"));
  REQUIRE(r.recipe.has_value());
  CHECK(r.recipe->hash == want);
}

TEST_CASE("engine parse stage fills the recipe fields", "[recipe]") {
  const auto r = recipe::parse(fixture("valid", "both-layers.json"));
  REQUIRE(r.recipe.has_value());
  const auto& rec = *r.recipe;
  CHECK(rec.schema_version == "1.0");
  CHECK(rec.engine_version == "0.0.1");
  CHECK(rec.seed == 42);
  CHECK(rec.length_s == 600.0);
  CHECK(rec.loudness_target_lufs == -16.0);
  REQUIRE(rec.loudness_gain_db.has_value());
  CHECK(*rec.loudness_gain_db == -1.5);
  REQUIRE(rec.loudness_hash.has_value());
  CHECK(rec.loudness_hash->size() == 64);
  REQUIRE(rec.theta_reference.has_value());
  CHECK(rec.theta_reference->carrier_hz == 200.0);
  REQUIRE(rec.binaural.has_value());
  CHECK(rec.binaural->carrier_left_hz == 400.0);
  CHECK(rec.binaural->beat_rate_hz == 6.0);
  CHECK(rec.hash.size() == 64);
  CHECK(std::all_of(rec.hash.begin(), rec.hash.end(),
                    [](char c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'); }));

  const auto none = recipe::parse(fixture("valid", "minimal-no-layers.json"));
  REQUIRE(none.recipe.has_value());
  CHECK_FALSE(none.recipe->theta_reference.has_value());
  CHECK_FALSE(none.recipe->binaural.has_value());
  CHECK_FALSE(none.recipe->loudness_gain_db.has_value());
  CHECK_FALSE(none.recipe->loudness_hash.has_value());
}

TEST_CASE("seed integer form and seed bounds", "[recipe]") {
  const auto seven = recipe::parse(fixture("valid", "minimal-seed-7-0.json"));
  REQUIRE(seven.recipe.has_value());
  CHECK(seven.recipe->seed == 7);
  const auto max = recipe::parse(fixture("valid", "minimal-seed-max.json"));
  REQUIRE(max.recipe.has_value());
  CHECK(max.recipe->seed == UINT64_C(9007199254740991));
}

TEST_CASE("recipe hash groups: reformatted and metadata edits keep it, audio edits change it",
          "[recipe][hash]") {
  const auto h = engine_hashes();
  const std::string base = h.at("both-layers.json");
  for (const char* same : {"both-layers-reformatted.json", "both-layers-metadata-edited.json",
                           "both-layers-without-loudness-fields.json"}) {
    INFO(same);
    CHECK(h.at(same) == base);
  }
  for (const char* diff :
       {"both-layers-seed-changed.json", "both-layers-engine-version-changed.json",
        "both-layers-schema-minor-changed.json", "both-layers-length-changed.json",
        "both-layers-loudness-target-changed.json", "both-layers-theta-carrier-changed.json",
        "both-layers-binaural-carrier-left-changed.json", "both-layers-beat-rate-changed.json",
        "theta-reference-only.json", "binaural-only.json"}) {
    INFO(diff);
    CHECK(h.at(diff) != base);
  }
  CHECK(h.at("minimal-seed-7.json") == h.at("minimal-seed-7-0.json"));
}

TEST_CASE("engine recipe hash equals the shared hash vectors", "[recipe][hash]") {
  const fs::path path = kData + "/recipe_hash_vectors.json";
  if (!fs::exists(path)) {
    FAIL("missing tests/data/recipe_hash_vectors.json: run python tools/recipe_hash.py "
         "--write-vectors");
  }
  const auto vectors = parse_json_file(path);
  const auto h = engine_hashes();
  REQUIRE(vectors.object().size() == h.size());
  for (const auto& [name, hash] : h) {
    INFO(name);
    const json::Value* want = vectors.find(name);
    REQUIRE(want != nullptr);
    CHECK(hash == want->string());
  }
}

#else

TEST_CASE("recipe parse stage, field table, and hash are implemented", "[recipe]") {
  FAIL("not implemented: recipe/recipe.hpp, recipe/field_table.hpp, json/value.hpp");
}

#endif
