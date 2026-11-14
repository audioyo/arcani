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
//     std::string_view range_row;  // Story 1.3: ranges.tsv row id, "" if not range-governed
//     double range_scale;          // Story 1.3: row unit to field unit (1, or 3600 for h to _s)
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
//   enum class ThetaShape { Sine, SmoothedOnOff, Sawtooth, ReverseSaw, Custom };  // Story 2.1
//   struct ThetaReference { double carrier_hz; double rate_hz; double am_depth_percent;
//                           ThetaShape shape; };
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
//
// Story 2.2 (gamma PAC layer, uncoupled), recipe/recipe.hpp:
//   enum class GammaCarrierWave { Sine, Triangle, SoftenedSquare };
//   enum class GammaCoupling { Uncoupled };
//   inline constexpr std::string_view kGammaCarrierWaveEnum = "sine, triangle, softened_square";
//   inline constexpr std::string_view kGammaCouplingEnum = "uncoupled";
//   struct GammaPac { double carrier_hz; double rate_hz; double am_depth_percent;
//                     GammaCarrierWave carrier_wave; GammaCoupling coupling; };
//   Recipe gains std::optional<GammaPac> gamma_pac;
// Unknown carrier_wave or coupling text: rule "enum", parameter
// /gamma_pac/carrier_wave or /gamma_pac/coupling, value the text, limit the
// enum constant. Field table: /gamma_pac (Object, LoudnessRelevant, not
// required), then carrier_hz (row gamma-carrier), rate_hz (row gamma-rate),
// am_depth_percent (row coupling-depth), carrier_wave, coupling (each
// required, LoudnessRelevant), between the theta_reference rows and the
// binaural rows. The gamma members are read through templates, so the suite
// builds before they exist and the missing pieces fail as test cases.
//
// Story 2.3 (gamma PAC layer, coupled smooth swell), recipe/recipe.hpp:
//   enum class GammaCoupling { Uncoupled, SmoothSwell };
//   inline constexpr std::string_view kGammaCouplingEnum = "uncoupled, smooth_swell";
//   GammaPac gains std::optional<double> coupling_phase_deg;  // absent when the field is
// Field table: /gamma_pac/coupling_phase_deg (Number, LoudnessRelevant, not
// required, range row coupling-phase, scale 1) right after /gamma_pac/coupling.
// Phase text is rule "type" at /gamma_pac/coupling_phase_deg.
//
// Story 2.4 (gamma PAC layer, coupled 50 ms bursts), recipe/recipe.hpp:
//   enum class GammaCoupling { Uncoupled, SmoothSwell, Bursts };
//   inline constexpr std::string_view kGammaCouplingEnum = "uncoupled, smooth_swell, bursts";
// bursts parses like smooth_swell, with or without coupling_phase_deg
// (compile decides). Bursts is read through a requires-expression, so the
// suite builds before it exists.
//
// Story 2.5 (binaural layer and rate curve), recipe/recipe.hpp:
//   enum class BinauralWaveform { Sine, Triangle };
//   inline constexpr std::string_view kBinauralWaveformEnum = "sine, triangle";
//   struct BeatRateCycle { double swing_hz = 0.0; double period_s = 0.0;
//                          double start_phase_deg = 0.0; };
//   Binaural gains std::optional<BeatRateCycle> beat_rate_cycle; and
//   BinauralWaveform waveform = BinauralWaveform::Sine;  // absent means sine
// Field table, right after /binaural/beat_rate_hz and in this order:
// /binaural/beat_rate_cycle (Object, not required), its swing_hz (no range
// row: the worst-case rate checks bound it), period_s (row
// rate-cycle-period), start_phase_deg (row rate-cycle-start-phase), each a
// required Number, then /binaural/waveform (String, not required); every one
// LoudnessRelevant. Waveform text outside the enum is rule "enum", limit
// "sine, triangle". The new members are read through templates and the enum
// constant through a lookup probe, so the suite builds before they exist.

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
#include "tables.hpp"

#include <algorithm>
#include <concepts>
#include <filesystem>
#include <fstream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <string_view>
#include <tuple>
#include <type_traits>
#include <utility>
#include <vector>

// Story 2.5 lookup probe: inside arcani::recipe_probe the using-directive
// makes arcani::recipe's names visible as members of arcani, found before
// this global fallback.
inline constexpr std::string_view kBinauralWaveformEnum = "(missing)";

namespace arcani::recipe_probe {
using namespace arcani::recipe;
inline const std::string binaural_waveform_enum(kBinauralWaveformEnum);
}  // namespace arcani::recipe_probe

namespace fs = std::filesystem;
namespace json = arcani::json;
namespace recipe = arcani::recipe;
namespace crypto = arcani::crypto;
namespace tables = arcani::test::tables;

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
  // Written out by hand from both-layers.json (Story 2.1: its theta reference
  // gains rate_hz 6, am_depth_percent 0, shape sine), not by any tool: hash-excluded
  // fields removed, keys sorted, integral numbers without a fraction. The hex
  // is hashlib.sha256 of this literal; tests/python/test_recipe_hash.py checks
  // the same literal against the Python tool.
  const std::string canonical =
      R"({"binaural":{"beat_rate_hz":6,"carrier_left_hz":400},"engine_version":"0.0.1",)"
      R"("length_s":600,"loudness_target_lufs":-36,"schema_version":"1.0","seed":42,)"
      R"("theta_reference":{"am_depth_percent":0,"carrier_hz":200,"rate_hz":6,"shape":"sine"}})";
  const std::string want = "fd3e0508393b78386fa9a6f62e6b6282ca0e268648661eececa4fac3430a8a4c";
  CHECK(crypto::sha256_hex(canonical) == want);
  const auto r = recipe::parse(fixture("valid", "both-layers.json"));
  REQUIRE(r.recipe.has_value());
  CHECK(r.recipe->hash == want);
}

// Story 2.1: rate_hz, am_depth_percent, and shape (enum recipe::ThetaShape)
// in ThetaReference. A template, so the suite still builds before the fields
// exist and the missing fields show as a failing check.
template <class T>
void check_story_2_1_theta_fields(const T& theta) {
  if constexpr (requires { theta.rate_hz; theta.am_depth_percent; theta.shape; }) {
    using Shape = std::remove_cvref_t<decltype(theta.shape)>;
    CHECK(theta.rate_hz == 6.0);
    CHECK(theta.am_depth_percent == 0.0);
    CHECK(theta.shape == Shape::Sine);
  } else {
    FAIL("not implemented: ThetaReference rate_hz, am_depth_percent, shape (Story 2.1)");
  }
}

TEST_CASE("engine parse stage fills the recipe fields", "[recipe]") {
  const auto r = recipe::parse(fixture("valid", "both-layers.json"));
  REQUIRE(r.recipe.has_value());
  const auto& rec = *r.recipe;
  CHECK(rec.schema_version == "1.0");
  CHECK(rec.engine_version == "0.0.1");
  CHECK(rec.seed == 42);
  CHECK(rec.length_s == 600.0);
  CHECK(rec.loudness_target_lufs == -36.0);
  REQUIRE(rec.loudness_gain_db.has_value());
  CHECK(*rec.loudness_gain_db == -1.5);
  REQUIRE(rec.loudness_hash.has_value());
  CHECK(rec.loudness_hash->size() == 64);
  REQUIRE(rec.theta_reference.has_value());
  CHECK(rec.theta_reference->carrier_hz == 200.0);
  check_story_2_1_theta_fields(*rec.theta_reference);
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

// ------------------------------------------- binaural layer (Story 2.5)

namespace {

std::string binaural_text(const std::string& extra) {
  return "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
         "\"author\": \"Arcani test\", \"date\": \"2026-11-12\", "
         "\"rationale\": \"Binaural parse test, made in the test.\", "
         "\"length_s\": 10, \"loudness_target_lufs\": -36, "
         "\"binaural\": {\"carrier_left_hz\": 100, \"beat_rate_hz\": 1.5" +
         extra + "}}";
}

template <class B>
concept HasCycleAndWaveform = requires(const B& b) {
  { b.beat_rate_cycle.has_value() } -> std::convertible_to<bool>;
  { b.beat_rate_cycle->swing_hz } -> std::convertible_to<double>;
  { b.beat_rate_cycle->period_s } -> std::convertible_to<double>;
  { b.beat_rate_cycle->start_phase_deg } -> std::convertible_to<double>;
  b.waveform;
};

struct WantCycle {
  double swing_hz, period_s, start_phase_deg;
};

template <class B>
void check_binaural(const B& b, std::optional<WantCycle> cycle, bool triangle) {
  CHECK(b.carrier_left_hz == 100.0);
  CHECK(b.beat_rate_hz == 1.5);
  if constexpr (HasCycleAndWaveform<B>) {
    using Wave = std::remove_cvref_t<decltype(b.waveform)>;
    REQUIRE(b.beat_rate_cycle.has_value() == cycle.has_value());
    if (cycle.has_value()) {
      CHECK(b.beat_rate_cycle->swing_hz == cycle->swing_hz);
      CHECK(b.beat_rate_cycle->period_s == cycle->period_s);
      CHECK(b.beat_rate_cycle->start_phase_deg == cycle->start_phase_deg);
    }
    CHECK(b.waveform == (triangle ? Wave::Triangle : Wave::Sine));
  } else {
    FAIL("not implemented: recipe::Binaural has no beat_rate_cycle and waveform (Story 2.5)");
  }
}

template <class B>
void check_binaural_no_cycle(const B& b) {
  if constexpr (HasCycleAndWaveform<B>) {
    using Wave = std::remove_cvref_t<decltype(b.waveform)>;
    CHECK_FALSE(b.beat_rate_cycle.has_value());
    CHECK(b.waveform == Wave::Sine);
  } else {
    FAIL("not implemented: recipe::Binaural has no beat_rate_cycle and waveform (Story 2.5)");
  }
}

}  // namespace

TEST_CASE("the binaural waveform enum constant names both waveforms in schema order", "[recipe][binaural]") {
  CHECK(arcani::recipe_probe::binaural_waveform_enum == "sine, triangle");
}

TEST_CASE("engine parse stage fills the beat rate cycle and the waveform", "[recipe][binaural]") {
  struct Case {
    std::string extra;
    std::optional<WantCycle> cycle;
    bool triangle;
  };
  // Compile, not parse, rejects triangle and out-of-range cycle values
  // (tests/cpp/test_validate.cpp), so parse accepts them all.
  const Case cases[] = {
      {"", std::nullopt, false},
      {", \"waveform\": \"sine\"", std::nullopt, false},
      {", \"waveform\": \"triangle\"", std::nullopt, true},
      {", \"beat_rate_cycle\": {\"swing_hz\": 1.5, \"period_s\": 60, \"start_phase_deg\": 270}",
       WantCycle{1.5, 60.0, 270.0}, false},
      {", \"beat_rate_cycle\": {\"start_phase_deg\": 0, \"period_s\": 59.99, \"swing_hz\": 0}, "
       "\"waveform\": \"triangle\"",
       WantCycle{0.0, 59.99, 0.0}, true},
      {", \"beat_rate_cycle\": {\"swing_hz\": 1.51, \"period_s\": 60.01, \"start_phase_deg\": 360.01}",
       WantCycle{1.51, 60.01, 360.01}, false},
  };
  for (const auto& c : cases) {
    INFO("'" << c.extra << "'");
    const auto r = recipe::parse(binaural_text(c.extra));
    INFO(r.error.rule << " " << r.error.parameter << " " << r.error.value);
    REQUIRE(r.recipe.has_value());
    REQUIRE(r.recipe->binaural.has_value());
    check_binaural(*r.recipe->binaural, c.cycle, c.triangle);
  }
  // Every earlier fixture has neither field.
  const auto old = recipe::parse(fixture("valid", "binaural-only.json"));
  REQUIRE(old.recipe.has_value());
  REQUIRE(old.recipe->binaural.has_value());
  check_binaural_no_cycle(*old.recipe->binaural);
}

TEST_CASE("engine parse names binaural waveform and cycle faults", "[recipe][binaural]") {
  struct Case {
    std::string extra, rule, parameter, value, limit;
  };
  const Case cases[] = {
      {", \"waveform\": \"square\"", "enum", "/binaural/waveform", "square", "sine, triangle"},
      {", \"waveform\": \"Sine\"", "enum", "/binaural/waveform", "Sine", "sine, triangle"},
      {", \"waveform\": \"\"", "enum", "/binaural/waveform", "", "sine, triangle"},
      {", \"waveform\": 1", "type", "/binaural/waveform", "", ""},
      {", \"beat_rate_cycle\": {\"swing_hz\": 1.5, \"start_phase_deg\": 270}", "required",
       "/binaural/beat_rate_cycle/period_s", "", ""},
      {", \"beat_rate_cycle\": {\"period_s\": 60, \"start_phase_deg\": 270}", "required",
       "/binaural/beat_rate_cycle/swing_hz", "", ""},
      {", \"beat_rate_cycle\": {\"swing_hz\": 1.5, \"period_s\": 60}", "required",
       "/binaural/beat_rate_cycle/start_phase_deg", "", ""},
      {", \"beat_rate_cycle\": {\"swing_hz\": \"1.5\", \"period_s\": 60, \"start_phase_deg\": 270}",
       "type", "/binaural/beat_rate_cycle/swing_hz", "", ""},
      {", \"beat_rate_cycle\": {\"swing_hz\": 1.5, \"period_s\": 60, \"start_phase_deg\": 270, "
       "\"curve\": \"linear\"}",
       "unknown_property", "/binaural/beat_rate_cycle/curve", "", ""},
      {", \"beat_rate_cycle\": 60", "type", "/binaural/beat_rate_cycle", "", ""},
  };
  for (const auto& c : cases) {
    INFO("'" << c.extra << "'");
    const auto r = recipe::parse(binaural_text(c.extra));
    INFO("got " << r.error.rule << " " << r.error.parameter << " '" << r.error.value << "' " << r.error.limit);
    REQUIRE_FALSE(r.recipe.has_value());
    CHECK(r.error.rule == c.rule);
    CHECK(r.error.parameter == c.parameter);
    if (c.rule == "enum") {
      CHECK(r.error.value == c.value);
      CHECK(r.error.limit == c.limit);
    }
  }
}

TEST_CASE("field table orders the binaural rows last, the cycle and waveform after the beat rate",
          "[recipe][binaural][schema]") {
  std::vector<std::string> paths;
  for (const auto& f : recipe::fields()) {
    paths.emplace_back(f.path);
  }
  const std::vector<std::string> binaural = {
      "/binaural", "/binaural/carrier_left_hz", "/binaural/beat_rate_hz", "/binaural/beat_rate_cycle",
      "/binaural/beat_rate_cycle/swing_hz", "/binaural/beat_rate_cycle/period_s",
      "/binaural/beat_rate_cycle/start_phase_deg", "/binaural/waveform"};
  const auto at = std::find(paths.begin(), paths.end(), binaural.front());
  REQUIRE(at != paths.end());
  const auto start = static_cast<std::size_t>(at - paths.begin());
  REQUIRE(start + binaural.size() == paths.size());
  for (std::size_t i = 0; i < binaural.size(); ++i) {
    CHECK(paths[start + i] == binaural[i]);
  }
  for (const auto& f : recipe::fields()) {
    const std::string path(f.path);
    if (path.rfind("/binaural", 0) != 0) {
      continue;
    }
    INFO(path);
    CHECK(f.tag == recipe::FieldTag::LoudnessRelevant);
    if (path == "/binaural" || path == "/binaural/beat_rate_cycle") {
      CHECK(f.type == recipe::FieldType::Object);
      CHECK_FALSE(f.required);
    } else if (path == "/binaural/waveform") {
      CHECK(f.type == recipe::FieldType::String);
      CHECK_FALSE(f.required);
    } else {
      CHECK(f.type == recipe::FieldType::Number);
      CHECK(f.required);
    }
  }
}

// ------------------------------------------------ gamma PAC layer (Story 2.2)

namespace {

std::string gamma_text(const std::string& wave, const std::string& coupling) {
  return std::string(
             "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
             "\"author\": \"Arcani test\", \"date\": \"2026-11-07\", "
             "\"rationale\": \"Gamma parse test, made in the test.\", "
             "\"length_s\": 10, \"loudness_target_lufs\": -36, "
             "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": 40, \"am_depth_percent\": 25, "
             "\"carrier_wave\": \"") +
         wave + "\", \"coupling\": \"" + coupling + "\"}}";
}

// Story 2.2: Recipe::gamma_pac (std::optional<GammaPac>). A template, so the
// suite still builds before the member exists.
template <class R>
void check_story_2_2_gamma(const R& rec, const std::string& wave) {
  if constexpr (requires { rec.gamma_pac; }) {
    REQUIRE(rec.gamma_pac.has_value());
    const auto& g = *rec.gamma_pac;
    using Wave = std::remove_cvref_t<decltype(g.carrier_wave)>;
    using Coupling = std::remove_cvref_t<decltype(g.coupling)>;
    CHECK(g.carrier_hz == 250.0);
    CHECK(g.rate_hz == 40.0);
    CHECK(g.am_depth_percent == 25.0);
    CHECK(g.coupling == Coupling::Uncoupled);
    if (wave == "sine") {
      CHECK(g.carrier_wave == Wave::Sine);
    } else if (wave == "triangle") {
      CHECK(g.carrier_wave == Wave::Triangle);
    } else {
      CHECK(g.carrier_wave == Wave::SoftenedSquare);
    }
  } else {
    FAIL("not implemented: Recipe::gamma_pac (Story 2.2)");
  }
}

template <class R>
void check_no_gamma(const R& rec) {
  if constexpr (requires { rec.gamma_pac; }) {
    CHECK_FALSE(rec.gamma_pac.has_value());
  } else {
    FAIL("not implemented: Recipe::gamma_pac (Story 2.2)");
  }
}

}  // namespace

TEST_CASE("engine parse stage fills the gamma PAC fields", "[recipe][gamma]") {
  // Triangle and softened square are schema-valid: parse accepts them and
  // compile rejects them by name (tests/cpp/test_validate.cpp).
  for (const char* wave : {"sine", "triangle", "softened_square"}) {
    INFO(wave);
    const auto r = recipe::parse(gamma_text(wave, "uncoupled"));
    INFO(r.error.rule << " " << r.error.parameter << " " << r.error.value);
    REQUIRE(r.recipe.has_value());
    check_story_2_2_gamma(*r.recipe, wave);
    CHECK_FALSE(r.recipe->theta_reference.has_value());
    CHECK_FALSE(r.recipe->binaural.has_value());
  }
  const auto none = recipe::parse(fixture("valid", "theta-sine-6hz.json"));
  REQUIRE(none.recipe.has_value());
  check_no_gamma(*none.recipe);
}

TEST_CASE("engine parse names text outside the gamma enums", "[recipe][gamma]") {
  struct Case {
    std::string wave, coupling, parameter, value, limit;
  };
  const Case cases[] = {
      {"square", "uncoupled", "/gamma_pac/carrier_wave", "square", "sine, triangle, softened_square"},
      {"Sine", "uncoupled", "/gamma_pac/carrier_wave", "Sine", "sine, triangle, softened_square"},
      // Story 2.3: smooth_swell joins the coupling enum; Story 2.4 adds bursts.
      {"sine", "swell", "/gamma_pac/coupling", "swell", "uncoupled, smooth_swell, bursts"},
      {"sine", "Bursts", "/gamma_pac/coupling", "Bursts", "uncoupled, smooth_swell, bursts"},
      {"sine", "burst", "/gamma_pac/coupling", "burst", "uncoupled, smooth_swell, bursts"},
      {"sine", "Smooth_swell", "/gamma_pac/coupling", "Smooth_swell", "uncoupled, smooth_swell, bursts"},
      {"sine", "", "/gamma_pac/coupling", "", "uncoupled, smooth_swell, bursts"},
  };
  for (const auto& c : cases) {
    INFO(c.wave << " / " << c.coupling);
    const auto r = recipe::parse(gamma_text(c.wave, c.coupling));
    REQUIRE_FALSE(r.recipe.has_value());
    CHECK(r.error.rule == "enum");
    CHECK(r.error.parameter == c.parameter);
    CHECK(r.error.value == c.value);
    CHECK(r.error.limit == c.limit);
  }
}

// ------------------------------------------ coupled smooth swell (Story 2.3)

namespace {

// gamma_text with an optional coupling_phase_deg member written as given.
std::string swell_text(const std::string& coupling, const std::string& phase) {
  std::string t = gamma_text("sine", coupling);
  if (!phase.empty()) {
    const auto at = t.rfind("}}");
    t.insert(at, ", \"coupling_phase_deg\": " + phase);
  }
  return t;
}

template <class E>
concept HasSmoothSwell = requires { E::SmoothSwell; };

template <class G>
concept HasCouplingPhase = requires(const G& g) {
  { g.coupling_phase_deg.has_value() } -> std::convertible_to<bool>;
  { *g.coupling_phase_deg } -> std::convertible_to<double>;
};

template <class R>
void check_swell(const R& rec, bool smooth, std::optional<double> phase) {
  REQUIRE(rec.gamma_pac.has_value());
  const auto& g = *rec.gamma_pac;
  using Coupling = std::remove_cvref_t<decltype(g.coupling)>;
  if constexpr (HasSmoothSwell<Coupling>) {
    CHECK(g.coupling == (smooth ? Coupling::SmoothSwell : Coupling::Uncoupled));
  } else {
    FAIL("not implemented: recipe::GammaCoupling has no SmoothSwell (Story 2.3)");
  }
  using Gamma = std::remove_cvref_t<decltype(g)>;
  if constexpr (HasCouplingPhase<Gamma>) {
    REQUIRE(g.coupling_phase_deg.has_value() == phase.has_value());
    if (phase.has_value()) {
      CHECK(*g.coupling_phase_deg == *phase);
    }
  } else {
    FAIL("not implemented: recipe::GammaPac has no std::optional<double> coupling_phase_deg (Story 2.3)");
  }
}

}  // namespace

TEST_CASE("the coupling enum constant names every coupling in schema order", "[recipe][gamma][coupling]") {
  // Story 2.4 adds bursts.
  CHECK(recipe::kGammaCouplingEnum == "uncoupled, smooth_swell, bursts");
}

TEST_CASE("engine parse stage fills the coupling and the coupling phase", "[recipe][gamma][coupling]") {
  struct Case {
    std::string coupling, phase;
    bool smooth;
    std::optional<double> want;
  };
  // Compile, not parse, rejects smooth_swell without a phase and uncoupled
  // with one (tests/cpp/test_validate.cpp), so parse accepts all four.
  const Case cases[] = {
      {"smooth_swell", "90", true, 90.0},       {"smooth_swell", "0", true, 0.0},
      {"smooth_swell", "360", true, 360.0},     {"smooth_swell", "359.99", true, 359.99},
      {"smooth_swell", "", true, std::nullopt}, {"uncoupled", "", false, std::nullopt},
      {"uncoupled", "90", false, 90.0},
  };
  for (const auto& c : cases) {
    INFO(c.coupling << " / '" << c.phase << "'");
    const auto r = recipe::parse(swell_text(c.coupling, c.phase));
    INFO(r.error.rule << " " << r.error.parameter << " " << r.error.value);
    REQUIRE(r.recipe.has_value());
    check_swell(*r.recipe, c.smooth, c.want);
  }
}

namespace {

template <class E>
concept HasBursts = requires { E::Bursts; };

template <class R>
void check_bursts(const R& rec, std::optional<double> phase) {
  REQUIRE(rec.gamma_pac.has_value());
  const auto& g = *rec.gamma_pac;
  using Coupling = std::remove_cvref_t<decltype(g.coupling)>;
  if constexpr (HasBursts<Coupling>) {
    CHECK(g.coupling == Coupling::Bursts);
  } else {
    FAIL("not implemented: recipe::GammaCoupling has no Bursts (Story 2.4)");
  }
  REQUIRE(g.coupling_phase_deg.has_value() == phase.has_value());
  if (phase.has_value()) {
    CHECK(*g.coupling_phase_deg == *phase);
  }
}

}  // namespace

TEST_CASE("engine parse stage fills the bursts coupling and its phase", "[recipe][gamma][coupling][bursts]") {
  struct Case {
    std::string phase;
    std::optional<double> want;
  };
  // Compile, not parse, rejects bursts without a phase
  // (tests/cpp/test_validate.cpp), so parse accepts both.
  const Case cases[] = {{"0", 0.0}, {"90", 90.0}, {"360", 360.0}, {"359.99", 359.99}, {"", std::nullopt}};
  for (const auto& c : cases) {
    INFO("bursts / '" << c.phase << "'");
    const auto r = recipe::parse(swell_text("bursts", c.phase));
    INFO(r.error.rule << " " << r.error.parameter << " " << r.error.value << " " << r.error.limit);
    REQUIRE(r.recipe.has_value());
    check_bursts(*r.recipe, c.want);
  }
  // The burst fixtures parse with coupling bursts at 0 degrees.
  for (const char* name : {"bursts-40hz.json", "bursts-45hz.json", "bursts-60hz.json"}) {
    INFO(name);
    const auto r = recipe::parse(fixture("valid", name));
    REQUIRE(r.recipe.has_value());
    check_bursts(*r.recipe, 0.0);
    REQUIRE(r.recipe->theta_reference.has_value());
  }
  // A smooth swell still parses as SmoothSwell.
  const auto swell = recipe::parse(swell_text("smooth_swell", "90"));
  REQUIRE(swell.recipe.has_value());
  check_swell(*swell.recipe, true, 90.0);
}

TEST_CASE("engine parse names coupling phase text a type fault", "[recipe][gamma][coupling]") {
  for (const char* phase : {"\"90\"", "true", "null"}) {
    INFO(phase);
    const auto r = recipe::parse(swell_text("smooth_swell", phase));
    REQUIRE_FALSE(r.recipe.has_value());
    CHECK(r.error.rule == "type");
    CHECK(r.error.parameter == "/gamma_pac/coupling_phase_deg");
  }
}

TEST_CASE("field table orders the gamma rows between theta and binaural", "[recipe][gamma][schema]") {
  std::vector<std::string> paths;
  for (const auto& f : recipe::fields()) {
    paths.emplace_back(f.path);
  }
  const std::vector<std::string> gamma = {"/gamma_pac", "/gamma_pac/carrier_hz", "/gamma_pac/rate_hz",
                                          "/gamma_pac/am_depth_percent", "/gamma_pac/carrier_wave",
                                          "/gamma_pac/coupling",
                                          "/gamma_pac/coupling_phase_deg"};  // Story 2.3
  const auto at = std::find(paths.begin(), paths.end(), gamma.front());
  REQUIRE(at != paths.end());
  const auto start = static_cast<std::size_t>(at - paths.begin());
  REQUIRE(start + gamma.size() <= paths.size());
  for (std::size_t i = 0; i < gamma.size(); ++i) {
    CHECK(paths[start + i] == gamma[i]);
  }
  REQUIRE(start >= 1);
  CHECK(paths[start - 1].rfind("/theta_reference", 0) == 0);
  REQUIRE(start + gamma.size() < paths.size());
  CHECK(paths[start + gamma.size()] == "/binaural");
  for (const auto& f : recipe::fields()) {
    const std::string path(f.path);
    if (path.rfind("/gamma_pac", 0) != 0) {
      continue;
    }
    INFO(path);
    CHECK(f.tag == recipe::FieldTag::LoudnessRelevant);
    if (path == "/gamma_pac") {
      CHECK(f.type == recipe::FieldType::Object);
      CHECK_FALSE(f.required);
    } else if (path == "/gamma_pac/coupling_phase_deg") {
      CHECK(f.type == recipe::FieldType::Number);
      CHECK_FALSE(f.required);  // Story 2.3: optional, compile rules decide
    } else {
      CHECK(f.required);
      const bool text = path == "/gamma_pac/carrier_wave" || path == "/gamma_pac/coupling";
      CHECK(f.type == (text ? recipe::FieldType::String : recipe::FieldType::Number));
    }
  }
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

// ------------------------------------------- range registration (Story 1.3)
//
// Every numeric field (Number or Integer) names its locked-range row in the
// field table, or is on the reasoned exemption list below. Expected Field
// members (recipe/field_table.hpp), added in Story 1.3:
//
//   std::string_view range_row;  // row id in tests/tables/ranges.tsv, "" when
//                                // the field is not range-governed
//   double range_scale;          // row unit to field unit: 1, or 3600 for h to _s
//
// A named row must exist in ranges.tsv (not thresholds.tsv), must not be
// pending, and its unit must fit the field's unit suffix at that scale. The
// rows are read with load_tables (not row()), so the doctored cases below do
// not record usage of rows they only pretend to use.

namespace {

// path -> reason. Fields here carry no range row.
const std::map<std::string, std::string> kRangeExempt = {
    {"/seed", "schema-bounded integer (0 to 2^53 - 1 in the schema)"},
    {"/loudness_gain_db", "written by the measure pass, not authored; Story 4.2 checks it"},
    // Story 2.5: the worst-case rate checks (r - s and r + s against row
    // beat-rate, f_C + s against binaural-carrier-right) and swing_hz >= 0
    // bound it; signal spec, Rate curve, Range checks.
    {"/binaural/beat_rate_cycle/swing_hz", "bounded by the worst-case rate checks, no range row of its own"},
};

// The field-to-row mapping settled in the Story 1.3 spec (path -> row, scale).
const std::map<std::string, std::pair<std::string, double>> kExpectedRegistration = {
    {"/length_s", {"session-length", 3600.0}},
    {"/loudness_target_lufs", {"loudness-tones", 1.0}},
    {"/theta_reference/carrier_hz", {"theta-carrier", 1.0}},
    {"/theta_reference/rate_hz", {"theta-rate", 1.0}},             // Story 2.1
    {"/theta_reference/am_depth_percent", {"theta-depth", 1.0}},   // Story 2.1
    {"/gamma_pac/carrier_hz", {"gamma-carrier", 1.0}},             // Story 2.2
    {"/gamma_pac/rate_hz", {"gamma-rate", 1.0}},                   // Story 2.2
    {"/gamma_pac/am_depth_percent", {"coupling-depth", 1.0}},      // Story 2.2
    {"/gamma_pac/coupling_phase_deg", {"coupling-phase", 1.0}},    // Story 2.3
    {"/binaural/carrier_left_hz", {"binaural-carrier", 1.0}},
    {"/binaural/beat_rate_hz", {"beat-rate", 1.0}},
    {"/binaural/beat_rate_cycle/period_s", {"rate-cycle-period", 1.0}},              // Story 2.5
    {"/binaural/beat_rate_cycle/start_phase_deg", {"rate-cycle-start-phase", 1.0}},  // Story 2.5
};

template <class F>
concept HasRangeRegistration = requires(const F& f) {
  { f.range_row } -> std::convertible_to<std::string_view>;
  { f.range_scale } -> std::convertible_to<double>;
};

bool ends_with(const std::string& s, const std::string& tail) {
  return s.size() >= tail.size() && s.compare(s.size() - tail.size(), tail.size(), tail) == 0;
}

// Empty when the row unit fits the field's unit suffix at this scale.
std::string unit_problem(const std::string& path, const std::string& unit, double scale) {
  struct Fit {
    const char* suffix;
    const char* unit;
    double scale;
  };
  static const Fit kFits[] = {
      {"_hz", "Hz", 1.0},       {"_s", "s", 1.0},           {"_s", "min", 60.0},
      {"_s", "h", 3600.0},      {"_lufs", "LUFS-I", 1.0},   {"_deg", "degrees", 1.0},
      {"_db", "dB", 1.0},       {"_percent", "percent", 1.0},
  };
  bool suffix_known = false;
  for (const auto& fit : kFits) {
    if (!ends_with(path, fit.suffix)) {
      continue;
    }
    suffix_known = true;
    if (unit == fit.unit && scale == fit.scale) {
      return "";
    }
  }
  if (!suffix_known) {
    return path + ": no unit suffix in the field name";
  }
  return path + ": row unit " + unit + " at scale " + std::to_string(scale) +
         " does not fit the field's unit suffix";
}

template <class F>
std::vector<std::string> registration_problems(const std::vector<F>& fields,
                                               const std::vector<tables::Row>& rows) {
  std::vector<std::string> out;
  for (const auto& f : fields) {
    const std::string path(f.path);
    const std::string row_id(f.range_row);
    const bool numeric =
        f.type == recipe::FieldType::Number || f.type == recipe::FieldType::Integer;
    const bool exempt = kRangeExempt.count(path) == 1;
    if (!numeric) {
      if (!row_id.empty()) {
        out.push_back(path + ": a non-numeric field names range row " + row_id);
      }
      if (exempt) {
        out.push_back(path + ": a non-numeric field is on the exemption list");
      }
      continue;
    }
    if (exempt) {
      if (!row_id.empty()) {
        out.push_back(path + ": an exempt field names range row " + row_id);
      }
      continue;
    }
    if (row_id.empty()) {
      out.push_back(path + ": numeric field with no range row and no exemption");
      continue;
    }
    const auto it = std::find_if(rows.begin(), rows.end(),
                                 [&](const tables::Row& r) { return r.id == row_id; });
    if (it == rows.end()) {
      out.push_back(path + ": range row " + row_id + " is missing from the tables");
      continue;
    }
    if (it->kind != "ranges") {
      out.push_back(path + ": row " + row_id + " is a " + it->kind + " row, not a range row");
      continue;
    }
    if (!it->pending.empty()) {
      out.push_back(path + ": range row " + row_id + " is pending on " + it->pending);
    }
    if (const std::string u = unit_problem(path, it->unit, f.range_scale); !u.empty()) {
      out.push_back(u);
    }
  }
  return out;
}

bool any_names(const std::vector<std::string>& problems, const std::string& path,
               const std::string& words) {
  return std::any_of(problems.begin(), problems.end(), [&](const std::string& p) {
    return p.find(path) != std::string::npos && p.find(words) != std::string::npos;
  });
}

template <class F>
F& field_at(std::vector<F>& fields, const char* path) {
  auto it = std::find_if(fields.begin(), fields.end(),
                         [&](const F& f) { return f.path == std::string_view(path); });
  REQUIRE(it != fields.end());
  return *it;
}

template <class F>
void run_registration_test() {
  if constexpr (HasRangeRegistration<F>) {
    const auto rows = tables::load_tables(ARCANI_TABLES_DIR);
    const std::vector<F> real(recipe::fields().begin(), recipe::fields().end());

    SECTION("the real field table passes") {
      const auto problems = registration_problems(real, rows);
      for (const auto& p : problems) {
        UNSCOPED_INFO(p);
      }
      CHECK(problems.empty());
    }

    SECTION("the real field table has the settled mapping") {
      for (const auto& f : real) {
        const std::string path(f.path);
        INFO(path);
        const auto want = kExpectedRegistration.find(path);
        if (want == kExpectedRegistration.end()) {
          CHECK(f.range_row.empty());
        } else {
          CHECK(std::string(f.range_row) == want->second.first);
          CHECK(static_cast<double>(f.range_scale) == want->second.second);
        }
      }
      for (const auto& [path, _] : kExpectedRegistration) {
        INFO(path);
        CHECK(std::any_of(real.begin(), real.end(),
                          [&](const F& f) { return f.path == std::string_view(path); }));
      }
    }

    SECTION("must fail: a numeric field with no row and no exemption") {
      auto doctored = real;
      field_at(doctored, "/length_s").range_row = "";
      CHECK(any_names(registration_problems(doctored, rows), "/length_s", "no range row"));
    }
    SECTION("must fail: a row id missing from the tables") {
      auto doctored = real;
      field_at(doctored, "/theta_reference/carrier_hz").range_row = "no-such-row";
      CHECK(any_names(registration_problems(doctored, rows), "/theta_reference/carrier_hz",
                      "missing"));
    }
    SECTION("must fail: a threshold row, not a range row") {
      auto doctored = real;
      field_at(doctored, "/binaural/beat_rate_hz").range_row = "carrier-rule";
      CHECK(any_names(registration_problems(doctored, rows), "/binaural/beat_rate_hz",
                      "not a range row"));
    }
    SECTION("must fail: a pending row") {
      auto doctored_rows = rows;
      auto it = std::find_if(doctored_rows.begin(), doctored_rows.end(),
                             [](const tables::Row& r) { return r.id == "theta-carrier"; });
      REQUIRE(it != doctored_rows.end());
      it->pending = "9-1-fixture-story";
      CHECK(any_names(registration_problems(real, doctored_rows), "/theta_reference/carrier_hz",
                      "pending"));
    }
    SECTION("must fail: a unit that does not fit the field suffix") {
      auto doctored = real;
      field_at(doctored, "/binaural/carrier_left_hz").range_row = "session-length";
      CHECK(any_names(registration_problems(doctored, rows), "/binaural/carrier_left_hz",
                      "does not fit"));
    }
    SECTION("must fail: the right unit at the wrong scale") {
      auto doctored = real;
      field_at(doctored, "/length_s").range_scale = 1.0;
      CHECK(any_names(registration_problems(doctored, rows), "/length_s", "does not fit"));
    }
    SECTION("must fail: an exempt field that names a row") {
      auto doctored = real;
      field_at(doctored, "/loudness_gain_db").range_row = "loudness-tones";
      CHECK(any_names(registration_problems(doctored, rows), "/loudness_gain_db",
                      "exempt field names"));
    }
    SECTION("must fail: a non-numeric field that names a row") {
      auto doctored = real;
      field_at(doctored, "/author").range_row = "theta-carrier";
      CHECK(any_names(registration_problems(doctored, rows), "/author", "non-numeric"));
    }
  } else {
    FAIL("not implemented: recipe::Field has no range_row and range_scale (Story 1.3)");
  }
}

}  // namespace

TEST_CASE("every numeric field names a locked-range row or a reasoned exemption",
          "[recipe][ranges]") {
  run_registration_test<recipe::Field>();
}

#else

TEST_CASE("recipe parse stage, field table, and hash are implemented", "[recipe]") {
  FAIL("not implemented: recipe/recipe.hpp, recipe/field_table.hpp, json/value.hpp");
}

#endif
