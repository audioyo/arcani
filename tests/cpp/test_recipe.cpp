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
//
// Story 2.6 (rate curves on the theta and gamma rates), recipe/recipe.hpp:
//   struct RateCycle { double swing_hz, period_s, start_phase_deg; };  // replaces BeatRateCycle
//   Binaural::beat_rate_cycle is std::optional<RateCycle>;
//   ThetaReference and GammaPac gain std::optional<RateCycle> rate_cycle;  // absent when absent
// Field table: /theta_reference/rate_cycle (Object, LoudnessRelevant, not
// required) right after /theta_reference/shape, then its swing_hz (no range
// row), period_s (row rate-cycle-period), start_phase_deg (row
// rate-cycle-start-phase), each a required Number; /gamma_pac/rate_cycle
// likewise right after /gamma_pac/coupling_phase_deg. The type is reached
// through a lookup probe and the members through requires-expressions, so the
// suite builds before they exist.
//
// Story 2.7 (looping body and seams), recipe/recipe.hpp:
//   enum class LoopMode { Focus, Learn };
//   inline constexpr std::string_view kLoopModeEnum = "focus, learn";
//   struct Loop { LoopMode mode; double opening_s; double body_s; double max_run_time_min; };
//   Recipe gains std::optional<Loop> loop;  // absent when the recipe has no loop
// Field table, right after the binaural rows and last: /loop (Object,
// LoudnessRelevant, not required), then /loop/mode (String), /loop/opening_s,
// /loop/body_s, /loop/max_run_time_min (Numbers), each required and
// LoudnessRelevant, none naming a range row (the mode picks the max run time
// row, and the loop rules bound the times). Mode text outside the enum is
// rule "enum", value the text, limit kLoopModeEnum. The members are read
// through requires-expressions and the enum constant through a lookup probe,
// so the suite builds before they exist.

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

// Story 2.6 lookup probe for types: the fallbacks live in their own
// namespace, reached through a using-directive (visible as members of the
// global namespace), so a real arcani::recipe type hides its fallback.
namespace recipe_rate_cycle_fallback {
struct RateCycle {
  int missing = 0;
};
struct BeatRateCycle {
  int missing = 0;
};
}  // namespace recipe_rate_cycle_fallback

namespace arcani::recipe_rate_cycle_probe {
using namespace ::recipe_rate_cycle_fallback;
using namespace arcani::recipe;
using RateCycleType = RateCycle;
inline constexpr bool kRateCycleDeclared =
    !std::is_same_v<RateCycleType, ::recipe_rate_cycle_fallback::RateCycle>;
inline constexpr bool kBeatRateCycleGone =
    std::is_same_v<BeatRateCycle, ::recipe_rate_cycle_fallback::BeatRateCycle>;
}  // namespace arcani::recipe_rate_cycle_probe

// Story 2.7 lookup probe, as for kBinauralWaveformEnum above.
inline constexpr std::string_view kLoopModeEnum = "(missing)";

namespace arcani::recipe_loop_probe {
using namespace arcani::recipe;
inline const std::string loop_mode_enum(kLoopModeEnum);
}  // namespace arcani::recipe_loop_probe

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

// Story 4.4: FieldType gains Array, reached through a requires-expression so
// the suite builds before it exists.
template <class E>
constexpr bool kHasArrayType = requires { E::Array; };

template <class E>
bool is_array_type(E t) {
  if constexpr (kHasArrayType<E>) {
    return t == E::Array;
  } else {
    (void)t;
    return false;
  }
}

const char* type_name(recipe::FieldType t) {
  if (is_array_type(t)) {
    return "array";
  }
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
    // Story 4.4: an array's items are listed under the path segment "*"
    // (the items object itself is no field of its own).
    if (type->string() == "array") {
      const json::Value* items = member(p, "items");
      REQUIRE(items != nullptr);
      walk(root, *items, path + "/*", out);
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

// Story 4.4 (docs/signal-spec.md, Gain ramps, Recipe fields): the six rows
// of a gain member, under its schedule's path, in this order.
const std::vector<std::string> kGainRows = {"/gain",
                                            "/gain/initial",
                                            "/gain/ramps",
                                            "/gain/ramps/*/start_s",
                                            "/gain/ramps/*/duration_s",
                                            "/gain/ramps/*/to"};

TEST_CASE("field table orders the binaural rows before the loop rows, the cycle and waveform after the beat rate",
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
  // Story 2.7: the five loop rows follow the binaural rows. Story 4.4: the
  // six binaural gain rows come before them, and the seven master rows end
  // the table.
  REQUIRE(start + binaural.size() + kGainRows.size() + 5 + 1 + kGainRows.size() == paths.size());
  for (std::size_t i = 0; i < binaural.size(); ++i) {
    CHECK(paths[start + i] == binaural[i]);
  }
  for (std::size_t i = 0; i < kGainRows.size(); ++i) {
    CHECK(paths[start + binaural.size() + i] == "/binaural" + kGainRows[i]);
  }
  CHECK(paths[start + binaural.size() + kGainRows.size()] == "/loop");
  for (const auto& f : recipe::fields()) {
    const std::string path(f.path);
    if (path.rfind("/binaural", 0) != 0 || path.rfind("/binaural/gain", 0) == 0) {
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
                                          "/gamma_pac/coupling_phase_deg",  // Story 2.3
                                          "/gamma_pac/rate_cycle",          // Story 2.6
                                          "/gamma_pac/rate_cycle/swing_hz",
                                          "/gamma_pac/rate_cycle/period_s",
                                          "/gamma_pac/rate_cycle/start_phase_deg"};
  const auto at = std::find(paths.begin(), paths.end(), gamma.front());
  REQUIRE(at != paths.end());
  const auto start = static_cast<std::size_t>(at - paths.begin());
  REQUIRE(start + gamma.size() <= paths.size());
  for (std::size_t i = 0; i < gamma.size(); ++i) {
    CHECK(paths[start + i] == gamma[i]);
  }
  REQUIRE(start >= 1);
  CHECK(paths[start - 1].rfind("/theta_reference", 0) == 0);
  // Story 4.4: the six gain rows follow the rate cycle.
  REQUIRE(start + gamma.size() + kGainRows.size() < paths.size());
  for (std::size_t i = 0; i < kGainRows.size(); ++i) {
    CHECK(paths[start + gamma.size() + i] == "/gamma_pac" + kGainRows[i]);
  }
  CHECK(paths[start + gamma.size() + kGainRows.size()] == "/binaural");
  for (const auto& f : recipe::fields()) {
    const std::string path(f.path);
    if (path.rfind("/gamma_pac", 0) != 0 || path.rfind("/gamma_pac/gain", 0) == 0) {
      continue;
    }
    INFO(path);
    CHECK(f.tag == recipe::FieldTag::LoudnessRelevant);
    if (path == "/gamma_pac" || path == "/gamma_pac/rate_cycle") {
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

// ------------------------------------- rate curves on theta and gamma (Story 2.6)

namespace {

namespace rc_probe = arcani::recipe_rate_cycle_probe;

std::string rate_cycle_text(const std::string& body) { return ", \"rate_cycle\": " + body; }

// A 450 Hz carrier amplitude-modulated at 3.5 Hz by the sine envelope, 75
// percent, with `extra` appended inside theta_reference after shape.
std::string theta_cycle_recipe(const std::string& extra) {
  return "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
         "\"author\": \"Arcani test\", \"date\": \"2026-11-14\", "
         "\"rationale\": \"Rate curve parse test, made in the test.\", "
         "\"length_s\": 10, \"loudness_target_lufs\": -36, "
         "\"theta_reference\": {\"carrier_hz\": 450, \"rate_hz\": 3.5, \"am_depth_percent\": 75, "
         "\"shape\": \"sine\"" +
         extra + "}}";
}

// A 250 Hz sine carrier amplitude-modulated at 45 Hz, 100 percent, uncoupled,
// with `extra` appended inside gamma_pac after coupling.
std::string gamma_cycle_recipe(const std::string& extra) {
  return "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
         "\"author\": \"Arcani test\", \"date\": \"2026-11-14\", "
         "\"rationale\": \"Rate curve parse test, made in the test.\", "
         "\"length_s\": 10, \"loudness_target_lufs\": -36, "
         "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": 45, \"am_depth_percent\": 100, "
         "\"carrier_wave\": \"sine\", \"coupling\": \"uncoupled\"" +
         extra + "}}";
}

template <class L>
concept HasRateCycle = requires(const L& l) {
  { l.rate_cycle.has_value() } -> std::convertible_to<bool>;
  { l.rate_cycle->swing_hz } -> std::convertible_to<double>;
  { l.rate_cycle->period_s } -> std::convertible_to<double>;
  { l.rate_cycle->start_phase_deg } -> std::convertible_to<double>;
};

// The layer's rate_cycle against `cycle` (nullopt: absent), or a failed check
// when the layer has no rate_cycle member yet.
template <class L>
void check_rate_cycle(const L& layer, std::optional<WantCycle> cycle, const char* which) {
  if constexpr (HasRateCycle<L>) {
    REQUIRE(layer.rate_cycle.has_value() == cycle.has_value());
    if (cycle.has_value()) {
      CHECK(layer.rate_cycle->swing_hz == cycle->swing_hz);
      CHECK(layer.rate_cycle->period_s == cycle->period_s);
      CHECK(layer.rate_cycle->start_phase_deg == cycle->start_phase_deg);
    }
  } else {
    FAIL("not implemented: recipe::" << which << " has no std::optional<RateCycle> rate_cycle (Story 2.6)");
  }
}

template <class L>
void check_member_type(const char* which) {
  if constexpr (HasRateCycle<L>) {
    CHECK(std::is_same_v<decltype(L::rate_cycle), std::optional<rc_probe::RateCycleType>>);
  } else {
    FAIL("not implemented: recipe::" << which << " has no rate_cycle (Story 2.6)");
  }
}

template <class R>
concept CycleStructMembers = requires { &R::swing_hz; &R::period_s; &R::start_phase_deg; };

template <class R>
void check_cycle_struct() {
  if constexpr (CycleStructMembers<R>) {
    CHECK(std::is_same_v<decltype(R::swing_hz), double>);
    CHECK(std::is_same_v<decltype(R::period_s), double>);
    CHECK(std::is_same_v<decltype(R::start_phase_deg), double>);
  } else {
    FAIL("not implemented: recipe::RateCycle {swing_hz, period_s, start_phase_deg} (Story 2.6)");
  }
}

}  // namespace

TEST_CASE("recipe::RateCycle is the one cycle type of all three layers", "[recipe][rate-curves]") {
  CHECK(rc_probe::kRateCycleDeclared);
  check_cycle_struct<rc_probe::RateCycleType>();
  CHECK(std::is_same_v<decltype(recipe::Binaural::beat_rate_cycle), std::optional<rc_probe::RateCycleType>>);
  check_member_type<recipe::ThetaReference>("ThetaReference");
  check_member_type<recipe::GammaPac>("GammaPac");
}

TEST_CASE("recipe::BeatRateCycle is gone: it became RateCycle", "[recipe][rate-curves]") {
  CHECK(rc_probe::kBeatRateCycleGone);
}

TEST_CASE("engine parse stage fills the theta and gamma rate cycles", "[recipe][rate-curves]") {
  struct Case {
    std::string extra;
    std::optional<WantCycle> cycle;
  };
  // Compile, not parse, rejects out-of-range cycle values
  // (tests/cpp/test_validate.cpp), so parse accepts them all.
  const Case cases[] = {
      {"", std::nullopt},
      {rate_cycle_text("{\"swing_hz\": 2.5, \"period_s\": 60, \"start_phase_deg\": 0}"), WantCycle{2.5, 60.0, 0.0}},
      {rate_cycle_text("{\"start_phase_deg\": 270, \"period_s\": 59.99, \"swing_hz\": 0}"),
       WantCycle{0.0, 59.99, 270.0}},
      {rate_cycle_text("{\"swing_hz\": -1.01, \"period_s\": 60.01, \"start_phase_deg\": 360.01}"),
       WantCycle{-1.01, 60.01, 360.01}},
  };
  for (const auto& c : cases) {
    INFO("'" << c.extra << "'");
    {
      const auto r = recipe::parse(theta_cycle_recipe(c.extra));
      INFO(r.error.rule << " " << r.error.parameter << " " << r.error.value);
      REQUIRE(r.recipe.has_value());
      REQUIRE(r.recipe->theta_reference.has_value());
      CHECK(r.recipe->theta_reference->rate_hz == 3.5);  // rate_hz stays the center
      check_rate_cycle(*r.recipe->theta_reference, c.cycle, "ThetaReference");
    }
    {
      const auto r = recipe::parse(gamma_cycle_recipe(c.extra));
      INFO(r.error.rule << " " << r.error.parameter << " " << r.error.value);
      REQUIRE(r.recipe.has_value());
      REQUIRE(r.recipe->gamma_pac.has_value());
      CHECK(r.recipe->gamma_pac->rate_hz == 45.0);
      check_rate_cycle(*r.recipe->gamma_pac, c.cycle, "GammaPac");
    }
  }
  // Every earlier fixture with a theta or gamma layer has no rate_cycle.
  for (const char* name : {"both-layers.json", "theta-sine-6hz.json", "gamma-uncoupled-40hz-25pct.json",
                           "swell-sine-0deg-100pct.json", "bursts-40hz.json", "theta-gamma-uncoupled.json"}) {
    INFO(name);
    const auto r = recipe::parse(fixture("valid", name));
    REQUIRE(r.recipe.has_value());
    if (r.recipe->theta_reference.has_value()) {
      check_rate_cycle(*r.recipe->theta_reference, std::nullopt, "ThetaReference");
    }
    if (r.recipe->gamma_pac.has_value()) {
      check_rate_cycle(*r.recipe->gamma_pac, std::nullopt, "GammaPac");
    }
  }
  // The rate-curve fixtures parse with their cycles, every one from 0 degrees
  // with the 60 s period.
  struct Fixture {
    const char* name;
    std::optional<WantCycle> theta, gamma;
  };
  const Fixture fixtures[] = {
      {"theta-cycle-sine.json", WantCycle{2.5, 60.0, 0.0}, std::nullopt},
      {"theta-cycle-smoothed-on-off.json", WantCycle{2.5, 60.0, 0.0}, std::nullopt},
      {"gamma-cycle-uncoupled.json", std::nullopt, WantCycle{15.0, 60.0, 0.0}},
      {"swell-theta-cycle.json", WantCycle{2.0, 60.0, 0.0}, std::nullopt},
      {"bursts-theta-cycle.json", WantCycle{2.0, 60.0, 0.0}, std::nullopt},
      {"gamma-cycle-swell-theta-cycle.json", WantCycle{2.0, 60.0, 0.0}, WantCycle{15.0, 60.0, 0.0}},
  };
  for (const auto& f : fixtures) {
    INFO(f.name);
    const auto r = recipe::parse(fixture("valid", f.name));
    INFO(r.error.rule << " " << r.error.parameter << " " << r.error.value);
    REQUIRE(r.recipe.has_value());
    REQUIRE(r.recipe->theta_reference.has_value() == f.theta.has_value());
    if (f.theta.has_value()) {
      check_rate_cycle(*r.recipe->theta_reference, f.theta, "ThetaReference");
    }
    if (r.recipe->gamma_pac.has_value()) {
      check_rate_cycle(*r.recipe->gamma_pac, f.gamma, "GammaPac");
    } else {
      CHECK_FALSE(f.gamma.has_value());
    }
    CHECK_FALSE(r.recipe->binaural.has_value());
  }
}

TEST_CASE("engine parse names theta and gamma rate cycle faults", "[recipe][rate-curves]") {
  struct Case {
    std::string body;
    const char* rule;
    const char* member;  // after /<layer>/rate_cycle
  };
  const Case cases[] = {
      {"{\"swing_hz\": 2.5, \"start_phase_deg\": 0}", "required", "/period_s"},
      {"{\"period_s\": 60, \"start_phase_deg\": 0}", "required", "/swing_hz"},
      {"{\"swing_hz\": 2.5, \"period_s\": 60}", "required", "/start_phase_deg"},
      {"{\"swing_hz\": \"2.5\", \"period_s\": 60, \"start_phase_deg\": 0}", "type", "/swing_hz"},
      {"{\"swing_hz\": 2.5, \"period_s\": 60, \"start_phase_deg\": 0, \"curve\": \"linear\"}", "unknown_property",
       "/curve"},
      {"60", "type", ""},
  };
  for (const bool theta : {true, false}) {
    for (const auto& c : cases) {
      const std::string text =
          theta ? theta_cycle_recipe(rate_cycle_text(c.body)) : gamma_cycle_recipe(rate_cycle_text(c.body));
      INFO((theta ? "theta " : "gamma ") << c.body);
      const auto r = recipe::parse(text);
      INFO("got " << r.error.rule << " " << r.error.parameter);
      REQUIRE_FALSE(r.recipe.has_value());
      CHECK(r.error.rule == c.rule);
      CHECK(r.error.parameter ==
            std::string(theta ? "/theta_reference" : "/gamma_pac") + "/rate_cycle" + c.member);
    }
  }
}

TEST_CASE("field table orders the theta rows, the rate cycle after shape", "[recipe][rate-curves][schema]") {
  std::vector<std::string> paths;
  for (const auto& f : recipe::fields()) {
    paths.emplace_back(f.path);
  }
  const std::vector<std::string> theta = {
      "/theta_reference",          "/theta_reference/carrier_hz",          "/theta_reference/rate_hz",
      "/theta_reference/am_depth_percent", "/theta_reference/shape",      "/theta_reference/rate_cycle",
      "/theta_reference/rate_cycle/swing_hz", "/theta_reference/rate_cycle/period_s",
      "/theta_reference/rate_cycle/start_phase_deg"};
  const auto at = std::find(paths.begin(), paths.end(), theta.front());
  REQUIRE(at != paths.end());
  const auto start = static_cast<std::size_t>(at - paths.begin());
  // Story 4.4: the six gain rows follow the rate cycle.
  REQUIRE(start + theta.size() + kGainRows.size() < paths.size());
  for (std::size_t i = 0; i < theta.size(); ++i) {
    CHECK(paths[start + i] == theta[i]);
  }
  for (std::size_t i = 0; i < kGainRows.size(); ++i) {
    CHECK(paths[start + theta.size() + i] == "/theta_reference" + kGainRows[i]);
  }
  CHECK(paths[start + theta.size() + kGainRows.size()] == "/gamma_pac");
  for (const auto& f : recipe::fields()) {
    const std::string path(f.path);
    if (path.rfind("/theta_reference/rate_cycle", 0) != 0 && path.rfind("/gamma_pac/rate_cycle", 0) != 0) {
      continue;
    }
    INFO(path);
    CHECK(f.tag == recipe::FieldTag::LoudnessRelevant);
    if (path == "/theta_reference/rate_cycle" || path == "/gamma_pac/rate_cycle") {
      CHECK(f.type == recipe::FieldType::Object);
      CHECK_FALSE(f.required);
    } else {
      CHECK(f.type == recipe::FieldType::Number);
      CHECK(f.required);
    }
  }
}

TEST_CASE("the rate-curve fixtures have distinct recipe hashes; earlier hashes are unchanged",
          "[recipe][rate-curves][hash]") {
  const auto h = engine_hashes();
  std::set<std::string> seen;
  for (const char* name : {"theta-cycle-sine.json", "theta-cycle-smoothed-on-off.json", "gamma-cycle-uncoupled.json",
                           "swell-theta-cycle.json", "bursts-theta-cycle.json",
                           "gamma-cycle-swell-theta-cycle.json", "theta-cycle-below-1.json",
                           "theta-cycle-above-6.json", "gamma-cycle-below-30.json", "gamma-cycle-above-60.json",
                           "gamma-cycle-carrier-rule.json"}) {
    INFO(name);
    REQUIRE(h.count(name) == 1);
    CHECK(seen.insert(h.at(name)).second);
  }
  // A rate_cycle changes the hash: the same theta layer without one hashes
  // differently, and the earlier hand-written hash still holds.
  const auto with = recipe::parse(theta_cycle_recipe(
      rate_cycle_text("{\"swing_hz\": 2.5, \"period_s\": 60, \"start_phase_deg\": 0}")));
  const auto without = recipe::parse(theta_cycle_recipe(""));
  REQUIRE(with.recipe.has_value());
  REQUIRE(without.recipe.has_value());
  CHECK(with.recipe->hash != without.recipe->hash);
  CHECK(h.at("both-layers.json") == "fd3e0508393b78386fa9a6f62e6b6282ca0e268648661eececa4fac3430a8a4c");
}

// ------------------------------------------------ looping body and seams (Story 2.7)

namespace {

// A 450 Hz carrier amplitude-modulated by the sine envelope at 4 Hz, 75
// percent depth, with `loop` as the last member (empty: no loop).
std::string loop_recipe(const std::string& loop, const std::string& length = "1200") {
  std::string s =
      "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
      "\"author\": \"Arcani test\", \"date\": \"2026-11-14\", "
      "\"rationale\": \"Loop parse test, made in the test.\", "
      "\"length_s\": " + length + ", \"loudness_target_lufs\": -36, "
      "\"theta_reference\": {\"carrier_hz\": 450, \"rate_hz\": 4, \"am_depth_percent\": 75, \"shape\": \"sine\"}";
  if (!loop.empty()) {
    s += ", \"loop\": " + loop;
  }
  return s + "}";
}

template <class R>
concept RecipeHasLoop = requires(const R& r) {
  { r.loop.has_value() } -> std::convertible_to<bool>;
  r.loop->mode;
  { r.loop->opening_s } -> std::convertible_to<double>;
  { r.loop->body_s } -> std::convertible_to<double>;
  { r.loop->max_run_time_min } -> std::convertible_to<double>;
};

struct WantLoop {
  bool focus;
  double opening_s, body_s, max_run_time_min;
};

// The recipe's loop against `want` (nullopt: absent), or a failed check when
// the recipe has no loop member yet.
template <class R>
void check_recipe_loop(const R& r, std::optional<WantLoop> want) {
  if constexpr (RecipeHasLoop<R>) {
    using Mode = std::remove_cvref_t<decltype(r.loop->mode)>;
    REQUIRE(r.loop.has_value() == want.has_value());
    if (want.has_value()) {
      CHECK(r.loop->mode == (want->focus ? Mode::Focus : Mode::Learn));
      CHECK(r.loop->opening_s == want->opening_s);
      CHECK(r.loop->body_s == want->body_s);
      CHECK(r.loop->max_run_time_min == want->max_run_time_min);
    }
  } else {
    FAIL("not implemented: recipe::Recipe has no std::optional<Loop> loop (Story 2.7)");
  }
}

template <class R>
void check_loop_member_types() {
  if constexpr (RecipeHasLoop<R>) {
    using L = typename decltype(R::loop)::value_type;
    CHECK(std::is_same_v<decltype(L::opening_s), double>);
    CHECK(std::is_same_v<decltype(L::body_s), double>);
    CHECK(std::is_same_v<decltype(L::max_run_time_min), double>);
    CHECK(std::is_enum_v<decltype(L::mode)>);
  } else {
    FAIL("not implemented: recipe::Loop {mode, opening_s, body_s, max_run_time_min} (Story 2.7)");
  }
}

// The max run time row of a mode (the assertion call records the id).
double cap_of(const char* mode) {
  return tables::row(std::string(mode) == "focus" ? "max-run-time-focus" : "max-run-time-learn").max;
}

}  // namespace

TEST_CASE("the loop mode enum constant names both modes in schema order", "[recipe][loop]") {
  CHECK(arcani::recipe_loop_probe::loop_mode_enum == "focus, learn");
}

TEST_CASE("recipe::Loop holds the mode and three binary64 times", "[recipe][loop]") {
  check_loop_member_types<recipe::Recipe>();
}

TEST_CASE("engine parse stage fills the loop; a recipe without one has none", "[recipe][loop]") {
  struct Case {
    std::string loop;
    WantLoop want;
  };
  // Compile, not parse, applies the loop rules (tests/cpp/test_loop.cpp), so
  // parse accepts caps off their rows, negative and zero times, and any
  // member order.
  const Case cases[] = {
      {"{\"mode\": \"learn\", \"opening_s\": 60, \"body_s\": 120, \"max_run_time_min\": 21}",
       {false, 60.0, 120.0, 21.0}},
      {"{\"mode\": \"focus\", \"opening_s\": 0, \"body_s\": 90.25, \"max_run_time_min\": 44.5}",
       {true, 0.0, 90.25, 44.5}},
      {"{\"max_run_time_min\": 46, \"body_s\": 0, \"opening_s\": -60, \"mode\": \"focus\"}",
       {true, -60.0, 0.0, 46.0}},
      {"{\"mode\": \"learn\", \"opening_s\": 60.1, \"body_s\": 120.125, \"max_run_time_min\": 19}",
       {false, 60.1, 120.125, 19.0}},
  };
  for (const auto& c : cases) {
    INFO(c.loop);
    const auto r = recipe::parse(loop_recipe(c.loop));
    INFO(r.error.rule << " " << r.error.parameter << " " << r.error.value);
    REQUIRE(r.recipe.has_value());
    check_recipe_loop(*r.recipe, c.want);
  }
  {
    const auto r = recipe::parse(loop_recipe(""));
    REQUIRE(r.recipe.has_value());
    check_recipe_loop(*r.recipe, std::nullopt);
  }
  // Every fixture written before Story 2.7 has no loop.
  for (const char* name : {"both-layers.json", "theta-sine-6hz.json", "swell-theta-cycle.json",
                           "bursts-theta-cycle.json", "binaural-cycle-sleep.json",
                           "gamma-cycle-swell-theta-cycle.json"}) {
    INFO(name);
    const auto r = recipe::parse(fixture("valid", name));
    REQUIRE(r.recipe.has_value());
    check_recipe_loop(*r.recipe, std::nullopt);
  }
  // The three compile-accepted loop fixtures parse with their loops; each
  // cap is its mode's row and the session ends at the cap.
  struct Fixture {
    const char* name;
    const char* mode;
    double opening_s, body_s;
  };
  const Fixture fixtures[] = {
      {"loop-swell-theta-cycle.json", "learn", 60.0, 120.0},
      {"loop-bursts-theta-cycle.json", "learn", 60.0, 120.0},
      {"loop-focus-no-cycle.json", "focus", 0.0, 90.25},
  };
  for (const auto& f : fixtures) {
    INFO(f.name);
    const auto r = recipe::parse(fixture("valid", f.name));
    INFO(r.error.rule << " " << r.error.parameter << " " << r.error.value);
    REQUIRE(r.recipe.has_value());
    check_recipe_loop(*r.recipe, WantLoop{std::string(f.mode) == "focus", f.opening_s, f.body_s, cap_of(f.mode)});
    CHECK(r.recipe->length_s == cap_of(f.mode) * 60.0);
  }
}

TEST_CASE("engine parse names loop faults", "[recipe][loop]") {
  struct Case {
    std::string loop;
    const char* rule;
    const char* parameter;
    const char* value;  // nullptr: not checked
  };
  const Case cases[] = {
      {"{\"mode\": \"learn\", \"opening_s\": 60, \"body_s\": 120}", "required", "/loop/max_run_time_min", nullptr},
      {"{\"opening_s\": 60, \"body_s\": 120, \"max_run_time_min\": 21}", "required", "/loop/mode", nullptr},
      {"{\"mode\": \"learn\", \"body_s\": 120, \"max_run_time_min\": 21}", "required", "/loop/opening_s", nullptr},
      {"{\"mode\": \"learn\", \"opening_s\": 60, \"max_run_time_min\": 21}", "required", "/loop/body_s", nullptr},
      {"{\"mode\": \"sleep\", \"opening_s\": 60, \"body_s\": 120, \"max_run_time_min\": 21}", "enum", "/loop/mode",
       "sleep"},
      {"{\"mode\": \"Learn\", \"opening_s\": 60, \"body_s\": 120, \"max_run_time_min\": 21}", "enum", "/loop/mode",
       "Learn"},
      {"{\"mode\": 1, \"opening_s\": 60, \"body_s\": 120, \"max_run_time_min\": 21}", "type", "/loop/mode", nullptr},
      {"{\"mode\": \"learn\", \"opening_s\": \"60\", \"body_s\": 120, \"max_run_time_min\": 21}", "type",
       "/loop/opening_s", nullptr},
      {"{\"mode\": \"learn\", \"opening_s\": 60, \"body_s\": 120, \"max_run_time_min\": \"21\"}", "type",
       "/loop/max_run_time_min", nullptr},
      {"{\"mode\": \"learn\", \"opening_s\": 60, \"body_s\": 120, \"max_run_time_min\": 21, \"fade_s\": 5}",
       "unknown_property", "/loop/fade_s", nullptr},
      {"21", "type", "/loop", nullptr},
  };
  for (const auto& c : cases) {
    INFO(c.loop);
    const auto r = recipe::parse(loop_recipe(c.loop));
    INFO("got " << r.error.rule << " " << r.error.parameter << " " << r.error.value << " " << r.error.limit);
    REQUIRE_FALSE(r.recipe.has_value());
    CHECK(r.error.rule == c.rule);
    CHECK(r.error.parameter == c.parameter);
    if (c.value != nullptr) {
      CHECK(r.error.value == c.value);
    }
    if (std::string(c.rule) == "enum") {
      CHECK(r.error.limit == arcani::recipe_loop_probe::loop_mode_enum);
      CHECK(r.error.limit == "focus, learn");
    }
  }
}

TEST_CASE("the five invalid loop fixtures fail parse with their named fault", "[recipe][loop][fixtures]") {
  struct Case {
    const char* name;
    const char* parameter;
    const char* rule;
  };
  const Case cases[] = {
      {"loop-missing-max-run-time.json", "/loop/max_run_time_min", "required"},
      {"loop-missing-mode.json", "/loop/mode", "required"},
      {"loop-mode-not-in-enum.json", "/loop/mode", "enum"},
      {"loop-opening-as-string.json", "/loop/opening_s", "type"},
      {"loop-unknown-property.json", "/loop/fade_s", "unknown_property"},
  };
  for (const auto& c : cases) {
    INFO(c.name);
    const auto r = recipe::parse(fixture("invalid", c.name));
    INFO("got " << r.error.rule << " " << r.error.parameter << " " << r.error.value << " " << r.error.limit);
    REQUIRE_FALSE(r.recipe.has_value());
    CHECK(r.error.parameter == c.parameter);
    CHECK(r.error.rule == c.rule);
    if (std::string(c.rule) == "enum") {
      CHECK(r.error.value == "sleep");
      CHECK(r.error.limit == arcani::recipe_loop_probe::loop_mode_enum);
    }
  }
}

TEST_CASE("field table has the loop rows after the binaural rows, then the master rows", "[recipe][loop][schema]") {
  std::vector<std::string> paths;
  for (const auto& f : recipe::fields()) {
    paths.emplace_back(f.path);
  }
  const std::vector<std::string> loop = {"/loop", "/loop/mode", "/loop/opening_s", "/loop/body_s",
                                         "/loop/max_run_time_min"};
  const auto at = std::find(paths.begin(), paths.end(), loop.front());
  REQUIRE(at != paths.end());
  const auto start = static_cast<std::size_t>(at - paths.begin());
  REQUIRE(start > 0);
  // Story 4.4: the seven master rows (/master and its gain rows) end the table.
  REQUIRE(start + loop.size() + 1 + kGainRows.size() == paths.size());
  CHECK(paths[start - 1].rfind("/binaural", 0) == 0);
  for (std::size_t i = 0; i < loop.size(); ++i) {
    CHECK(paths[start + i] == loop[i]);
  }
  CHECK(paths[start + loop.size()] == "/master");
  for (std::size_t i = 0; i < kGainRows.size(); ++i) {
    CHECK(paths[start + loop.size() + 1 + i] == "/master" + kGainRows[i]);
  }
  for (const auto& f : recipe::fields()) {
    const std::string path(f.path);
    if (path.rfind("/loop", 0) != 0) {
      continue;
    }
    INFO(path);
    CHECK(f.tag == recipe::FieldTag::LoudnessRelevant);
    CHECK(f.range_row.empty());  // the mode picks the row
    if (path == "/loop") {
      CHECK(f.type == recipe::FieldType::Object);
      CHECK_FALSE(f.required);
    } else if (path == "/loop/mode") {
      CHECK(f.type == recipe::FieldType::String);
      CHECK(f.required);
    } else {
      CHECK(f.type == recipe::FieldType::Number);
      CHECK(f.required);
    }
  }
}

TEST_CASE("the loop fixtures have distinct recipe hashes; a loop changes the hash; earlier hashes are unchanged",
          "[recipe][loop][hash]") {
  const auto h = engine_hashes();
  std::set<std::string> seen;
  for (const char* name : {"loop-swell-theta-cycle.json", "loop-bursts-theta-cycle.json", "loop-focus-no-cycle.json",
                           "loop-focus-cap-46.json", "loop-learn-cap-45.json", "loop-learn-cap-19.json",
                           "loop-length-not-cap.json", "loop-opening-negative.json", "loop-body-zero.json",
                           "loop-opening-not-whole-samples.json", "loop-body-not-whole-samples.json",
                           "loop-body-off-cycle.json", "loop-gamma-body-off-cycle.json",
                           "loop-binaural-body-off-cycle.json", "loop-exceeds-session.json"}) {
    INFO(name);
    REQUIRE(h.count(name) == 1);
    CHECK(seen.insert(h.at(name)).second);
  }
  const std::string loop = "{\"mode\": \"learn\", \"opening_s\": 60, \"body_s\": 120, \"max_run_time_min\": 21}";
  const auto with = recipe::parse(loop_recipe(loop));
  const auto without = recipe::parse(loop_recipe(""));
  REQUIRE(with.recipe.has_value());
  REQUIRE(without.recipe.has_value());
  CHECK(with.recipe->hash != without.recipe->hash);
  // Every loop member is in the hash.
  for (const char* other : {"{\"mode\": \"focus\", \"opening_s\": 60, \"body_s\": 120, \"max_run_time_min\": 21}",
                            "{\"mode\": \"learn\", \"opening_s\": 0, \"body_s\": 120, \"max_run_time_min\": 21}",
                            "{\"mode\": \"learn\", \"opening_s\": 60, \"body_s\": 60, \"max_run_time_min\": 21}",
                            "{\"mode\": \"learn\", \"opening_s\": 60, \"body_s\": 120, \"max_run_time_min\": 44}"}) {
    INFO(other);
    const auto r = recipe::parse(loop_recipe(other));
    REQUIRE(r.recipe.has_value());
    CHECK(r.recipe->hash != with.recipe->hash);
  }
  // Hashes committed before Story 2.7 hold: a recipe without loop keeps its hash.
  CHECK(h.at("both-layers.json") == "fd3e0508393b78386fa9a6f62e6b6282ca0e268648661eececa4fac3430a8a4c");
  CHECK(h.at("swell-theta-cycle.json") == "ae9a452ae78ded5ba4989a98e4341d7eec11f246cdf8f32bfd7f12ff0fcaf926");
  CHECK(h.at("gamma-cycle-swell-theta-cycle.json") ==
        "d3249325d97c170c613b2741a6c79fe485034dc73adc46d41e451c38afeb1c7d");
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

// ------------------------------------------------- gain schedules (Story 4.4)
//
// docs/signal-spec.md, Gain ramps, Recipe fields; spec Implementation Notes,
// Recipe and Field table:
//   struct GainRampField { double start_s = 0.0; double duration_s = 0.0; double to = 0.0; };
//   struct Gain { double initial = 1.0; std::vector<GainRampField> ramps; };
//   std::optional<Gain> gain in ThetaReference, GammaPac, and Binaural;
//   struct Master { std::optional<Gain> gain; }; std::optional<Master> master in Recipe.
// FieldType gains Array; array items are listed with the path segment "*".
// Parse: `ramps` not an array is rule type, limit array, at /.../gain/ramps;
// an element not an object is rule type, limit object, at /.../ramps/<i>;
// a missing or unknown member inside an element is named with its index.
// The members are read through requires-expressions, so the suite builds
// before they exist.

namespace {

const char* const kGainSchedulePaths[] = {"/theta_reference", "/gamma_pac", "/binaural", "/master"};

// A recipe with every layer; `theta_gain`, `gamma_gain`, `binaural_gain`
// are appended inside their layer (empty: none), `tail` after binaural.
std::string gain_recipe(const std::string& theta_gain, const std::string& gamma_gain = "",
                        const std::string& binaural_gain = "", const std::string& tail = "") {
  const auto member = [](const std::string& g) { return g.empty() ? std::string() : ", \"gain\": " + g; };
  return "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
         "\"author\": \"Arcani test\", \"date\": \"2026-11-26\", "
         "\"rationale\": \"Gain parse test, made in the test.\", "
         "\"length_s\": 600, \"loudness_target_lufs\": -36, "
         "\"theta_reference\": {\"carrier_hz\": 450, \"rate_hz\": 4, \"am_depth_percent\": 75, \"shape\": \"sine\"" +
         member(theta_gain) +
         "}, \"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": 40, \"am_depth_percent\": 100, \"carrier_wave\": "
         "\"sine\", \"coupling\": \"smooth_swell\", \"coupling_phase_deg\": 0" +
         member(gamma_gain) + "}, \"binaural\": {\"carrier_left_hz\": 100, \"beat_rate_hz\": 2" +
         member(binaural_gain) + "}" + tail + "}";
}

template <class R>
concept RecipeHasGain = requires(const R& r) {
  { r.theta_reference->gain.has_value() } -> std::convertible_to<bool>;
  { r.gamma_pac->gain.has_value() } -> std::convertible_to<bool>;
  { r.binaural->gain.has_value() } -> std::convertible_to<bool>;
  { r.master.has_value() } -> std::convertible_to<bool>;
  { r.master->gain.has_value() } -> std::convertible_to<bool>;
  { r.theta_reference->gain->initial } -> std::convertible_to<double>;
  { r.theta_reference->gain->ramps.size() } -> std::convertible_to<std::size_t>;
  { r.theta_reference->gain->ramps[0].start_s } -> std::convertible_to<double>;
  { r.theta_reference->gain->ramps[0].duration_s } -> std::convertible_to<double>;
  { r.theta_reference->gain->ramps[0].to } -> std::convertible_to<double>;
};

struct WantRamp {
  double start_s, duration_s, to;
};

struct WantGain {
  double initial;
  std::vector<WantRamp> ramps;
};

template <class G>
void check_gain(const G& got, const std::optional<WantGain>& want, const char* where) {
  INFO(where);
  REQUIRE(got.has_value() == want.has_value());
  if (!want) {
    return;
  }
  CHECK(got->initial == want->initial);
  REQUIRE(got->ramps.size() == want->ramps.size());
  for (std::size_t i = 0; i < want->ramps.size(); ++i) {
    INFO("ramp " << i);
    CHECK(got->ramps[i].start_s == want->ramps[i].start_s);
    CHECK(got->ramps[i].duration_s == want->ramps[i].duration_s);
    CHECK(got->ramps[i].to == want->ramps[i].to);
  }
}

// theta, gamma, binaural, master; a recipe without a layer passes nullopt for it.
template <class R>
void check_recipe_gains(const R& r, const std::optional<WantGain> (&want)[4], bool has_master) {
  if constexpr (RecipeHasGain<R>) {
    if (r.theta_reference) {
      check_gain(r.theta_reference->gain, want[0], "theta_reference");
    }
    if (r.gamma_pac) {
      check_gain(r.gamma_pac->gain, want[1], "gamma_pac");
    }
    if (r.binaural) {
      check_gain(r.binaural->gain, want[2], "binaural");
    }
    REQUIRE(r.master.has_value() == has_master);
    if (has_master) {
      check_gain(r.master->gain, want[3], "master");
    }
  } else {
    (void)r;
    (void)want;
    (void)has_master;
    FAIL("not implemented: recipe::Gain, GainRampField, the gain members, and recipe::Master (Story 4.4)");
  }
}

template <class R>
void check_nine_ramps_and_empty_master(const R& r) {
  if constexpr (RecipeHasGain<R>) {
    CHECK(r.theta_reference->gain->ramps.size() == 9);
    REQUIRE(r.master.has_value());
    CHECK_FALSE(r.master->gain.has_value());
  } else {
    (void)r;
    FAIL("not implemented: recipe::Gain and recipe::Master (Story 4.4)");
  }
}

}  // namespace

TEST_CASE("field table: the gain rows of every schedule, in order, with their types, tags, and rows",
          "[recipe][gain-ramps][schema]") {
  std::vector<std::string> paths;
  for (const auto& f : recipe::fields()) {
    paths.emplace_back(f.path);
  }
  const auto master = std::find(paths.begin(), paths.end(), "/master");
  REQUIRE(master != paths.end());
  for (const char* schedule : kGainSchedulePaths) {
    INFO(schedule);
    const auto at = std::find(paths.begin(), paths.end(), std::string(schedule) + "/gain");
    REQUIRE(at != paths.end());
    const auto start = static_cast<std::size_t>(at - paths.begin());
    REQUIRE(start + kGainRows.size() <= paths.size());
    for (std::size_t i = 0; i < kGainRows.size(); ++i) {
      CHECK(paths[start + i] == schedule + kGainRows[i]);
    }
  }
  std::size_t gain_rows = 0;
  for (const auto& f : recipe::fields()) {
    const std::string path(f.path);
    if (path == "/master") {
      CHECK(f.type == recipe::FieldType::Object);
      CHECK_FALSE(f.required);
      CHECK(f.tag == recipe::FieldTag::LoudnessRelevant);
      CHECK(f.range_row.empty());
      continue;
    }
    const auto g = path.find("/gain");
    if (g == std::string::npos) {
      continue;
    }
    INFO(path);
    ++gain_rows;
    const std::string rest = path.substr(g);
    CHECK(f.tag == recipe::FieldTag::LoudnessRelevant);
    if (rest == "/gain") {
      CHECK(f.type == recipe::FieldType::Object);
      CHECK_FALSE(f.required);
      CHECK(f.range_row.empty());
    } else if (rest == "/gain/initial" || rest == "/gain/ramps/*/to") {
      CHECK(f.type == recipe::FieldType::Number);
      CHECK(f.required);
      CHECK(std::string(f.range_row) == tables::row("layer-gain").id);
      CHECK(f.range_scale == 1.0);
    } else if (rest == "/gain/ramps") {
      CHECK(is_array_type(f.type));
      CHECK(std::string(type_name(f.type)) == "array");
      CHECK_FALSE(f.required);
      CHECK(f.range_row.empty());  // the count is checked by name, row gain-ramp-count
    } else {
      CHECK((rest == "/gain/ramps/*/start_s" || rest == "/gain/ramps/*/duration_s"));
      CHECK(f.type == recipe::FieldType::Number);
      CHECK(f.required);
      CHECK(f.range_row.empty());
    }
  }
  CHECK(gain_rows == 4 * kGainRows.size());
}

TEST_CASE("engine parse stage fills the gain schedules and the master", "[recipe][gain-ramps]") {
  {
    const auto r = recipe::parse(fixture("valid", "gain-master-fade.json"));
    INFO(r.error.rule << " " << r.error.parameter << " " << r.error.value);
    REQUIRE(r.recipe.has_value());
    const std::optional<WantGain> want[4] = {std::nullopt, std::nullopt, WantGain{0.0, {{0.0, 0.01, 1.0}}},
                                             WantGain{1.0, {{120.0, 300.0, 0.0}}}};
    check_recipe_gains(*r.recipe, want, true);
  }
  {
    const auto r = recipe::parse(fixture("valid", "gain-ramp-in-loop.json"));
    INFO(r.error.rule << " " << r.error.parameter << " " << r.error.value);
    REQUIRE(r.recipe.has_value());
    const std::optional<WantGain> want[4] = {WantGain{0.0, {{0.0, 300.0, 1.0}}}, WantGain{0.0, {{0.0, 300.0, 1.0}}},
                                             std::nullopt, std::nullopt};
    check_recipe_gains(*r.recipe, want, false);
  }
  {
    // Every schedule, an empty ramps array, and two ramps in array order;
    // parse keeps the values as written (compile applies the rules).
    const auto r = recipe::parse(gain_recipe(
        "{\"initial\": 0.25, \"ramps\": []}", "{\"initial\": 1}",
        "{\"ramps\": [{\"to\": 0.5, \"duration_s\": 0.0099, \"start_s\": 10}, "
        "{\"start_s\": 5, \"duration_s\": 1, \"to\": 1.5}], \"initial\": -1}",
        ", \"master\": {\"gain\": {\"initial\": 0.5, \"ramps\": [{\"start_s\": 1, \"duration_s\": 2, \"to\": 0}]}}"));
    INFO(r.error.rule << " " << r.error.parameter << " " << r.error.value);
    REQUIRE(r.recipe.has_value());
    const std::optional<WantGain> want[4] = {WantGain{0.25, {}}, WantGain{1.0, {}},
                                             WantGain{-1.0, {{10.0, 0.0099, 0.5}, {5.0, 1.0, 1.5}}},
                                             WantGain{0.5, {{1.0, 2.0, 0.0}}}};
    check_recipe_gains(*r.recipe, want, true);
  }
  {
    // A master without a gain member, and nine ramps (the count is a
    // compile check, row gain-ramp-count).
    std::string nine;
    for (int i = 0; i < 9; ++i) {
      nine += std::string(i ? ", " : "") + "{\"start_s\": " + std::to_string(10 * (i + 1)) +
              ", \"duration_s\": 1, \"to\": 1}";
    }
    const auto r = recipe::parse(gain_recipe("{\"initial\": 1, \"ramps\": [" + nine + "]}", "", "", ", \"master\": {}"));
    INFO(r.error.rule << " " << r.error.parameter << " " << r.error.value);
    REQUIRE(r.recipe.has_value());
    check_nine_ramps_and_empty_master(*r.recipe);
  }
  // Every fixture written before Story 4.4 has no gain and no master.
  for (const char* name : {"both-layers.json", "theta-sine-6hz.json", "swell-theta-cycle.json",
                           "bursts-theta-cycle.json", "binaural-cycle-sleep.json", "loop-swell-theta-cycle.json"}) {
    INFO(name);
    const auto r = recipe::parse(fixture("valid", name));
    REQUIRE(r.recipe.has_value());
    const std::optional<WantGain> none[4] = {};
    check_recipe_gains(*r.recipe, none, false);
  }
}

TEST_CASE("engine parse names gain faults with the element index", "[recipe][gain-ramps]") {
  struct Case {
    std::string text;
    const char* rule;
    const char* parameter;
    const char* limit;  // nullptr: not checked
  };
  const std::string ramp = "{\"start_s\": 1, \"duration_s\": 1, \"to\": 1}";
  const Case cases[] = {
      {gain_recipe("{\"initial\": 1, \"ramps\": 5}"), "type", "/theta_reference/gain/ramps", "array"},
      {gain_recipe("{\"initial\": 1, \"ramps\": {}}"), "type", "/theta_reference/gain/ramps", "array"},
      {gain_recipe("{\"initial\": 1, \"ramps\": [" + ramp + ", 3]}"), "type", "/theta_reference/gain/ramps/1",
       "object"},
      {gain_recipe("", "{\"initial\": 1, \"ramps\": [[]]}"), "type", "/gamma_pac/gain/ramps/0", "object"},
      {gain_recipe("", "", "{\"initial\": 1, \"ramps\": [" + ramp + ", " + ramp + ", {\"start_s\": 1, \"duration_s\": 1}]}"),
       "required", "/binaural/gain/ramps/2/to", "present"},
      {gain_recipe("{\"initial\": 1, \"ramps\": [{\"duration_s\": 1, \"to\": 1}]}"), "required",
       "/theta_reference/gain/ramps/0/start_s", "present"},
      {gain_recipe("{\"initial\": 1, \"ramps\": [{\"start_s\": 1, \"duration_s\": 1, \"to\": 1, \"shape\": \"cos\"}]}"),
       "unknown_property", "/theta_reference/gain/ramps/0/shape", nullptr},
      {gain_recipe("{\"initial\": 1, \"ramps\": [{\"start_s\": 1, \"duration_s\": 1, \"to\": \"1\"}]}"), "type",
       "/theta_reference/gain/ramps/0/to", "number"},
      {gain_recipe("{}"), "required", "/theta_reference/gain/initial", "present"},
      {gain_recipe("{\"initial\": \"1\"}"), "type", "/theta_reference/gain/initial", "number"},
      {gain_recipe("", "", "1"), "type", "/binaural/gain", "object"},
      {gain_recipe("", "", "{\"initial\": 1, \"fade_s\": 5}"), "unknown_property", "/binaural/gain/fade_s",
       "initial, ramps"},
      {gain_recipe("", "", "", ", \"master\": {\"gain\": {\"initial\": 1}, \"fade\": 1}"), "unknown_property",
       "/master/fade", "gain"},
      {gain_recipe("", "", "", ", \"master\": 1"), "type", "/master", "object"},
      {gain_recipe("", "", "", ", \"master\": {\"gain\": {\"initial\": 1, \"ramps\": [" + ramp + ", null]}}"), "type",
       "/master/gain/ramps/1", "object"},
  };
  for (const auto& c : cases) {
    INFO(c.text);
    const auto r = recipe::parse(c.text);
    INFO("got " << r.error.rule << " " << r.error.parameter << " " << r.error.value << " " << r.error.limit);
    REQUIRE_FALSE(r.recipe.has_value());
    CHECK(r.error.rule == c.rule);
    CHECK(r.error.parameter == c.parameter);
    if (c.limit != nullptr) {
      CHECK(r.error.limit == c.limit);
    }
  }
}

TEST_CASE("the five invalid gain fixtures fail parse with their named fault", "[recipe][gain-ramps][fixtures]") {
  struct Case {
    const char* name;
    const char* parameter;
    const char* rule;
    const char* limit;
  };
  const Case cases[] = {
      {"gain-ramps-as-object.json", "/theta_reference/gain/ramps", "type", "array"},
      {"gain-ramp-missing-to.json", "/gamma_pac/gain/ramps/0/to", "required", "present"},
      {"gain-unknown-property.json", "/binaural/gain/fade_s", "unknown_property", "initial, ramps"},
      {"gain-initial-as-string.json", "/master/gain/initial", "type", "number"},
      {"gain-ramp-not-an-object.json", "/theta_reference/gain/ramps/0", "type", "object"},
  };
  for (const auto& c : cases) {
    INFO(c.name);
    const auto r = recipe::parse(fixture("invalid", c.name));
    INFO("got " << r.error.rule << " " << r.error.parameter << " " << r.error.value << " " << r.error.limit);
    REQUIRE_FALSE(r.recipe.has_value());
    CHECK(r.error.parameter == c.parameter);
    CHECK(r.error.rule == c.rule);
    CHECK(r.error.limit == c.limit);
  }
}

TEST_CASE("the gain fixtures have distinct recipe hashes; a gain member changes the hash", "[recipe][gain-ramps][hash]") {
  std::set<std::string> hashes;
  for (const char* name : {"gain-ramp-in-loop.json", "gain-layer-ramp-10min.json", "gain-master-fade.json",
                           "gain-end-fade-loop.json", "gain-theta-silent.json"}) {
    INFO(name);
    const auto r = recipe::parse(fixture("valid", name));
    REQUIRE(r.recipe.has_value());
    CHECK(hashes.insert(r.recipe->hash).second);
  }
  // A unity gain renders the same bits but is a different recipe text.
  const auto plain = recipe::parse(gain_recipe(""));
  const auto unity = recipe::parse(gain_recipe("{\"initial\": 1}"));
  REQUIRE(plain.recipe.has_value());
  REQUIRE(unity.recipe.has_value());
  CHECK(plain.recipe->hash != unity.recipe->hash);
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
    // Story 2.5: the worst-case rate checks (r - s and r + s against row
    // beat-rate, f_C + s against binaural-carrier-right) and swing_hz >= 0
    // bound it; signal spec, Rate curve, Range checks.
    {"/binaural/beat_rate_cycle/swing_hz", "bounded by the worst-case rate checks, no range row of its own"},
    // Story 2.6: swing_hz >= 0 and r - s, r + s against row theta-rate or
    // gamma-rate bound them; signal spec, Rate curve, Range checks, theta and
    // gamma.
    {"/theta_reference/rate_cycle/swing_hz", "bounded by the worst-case rate checks, no range row of its own"},
    {"/gamma_pac/rate_cycle/swing_hz", "bounded by the worst-case rate checks, no range row of its own"},
    // Story 2.7: the loop mode picks the max run time row (max-run-time-focus
    // or max-run-time-learn), and the loop rules bound the opening and body
    // (at least 0 and above 0, whole samples, whole rate cycles, within the
    // session); signal spec, Loop, Compile order.
    {"/loop/opening_s", "bounded by the loop rules, no range row of its own"},
    {"/loop/body_s", "bounded by the loop rules, no range row of its own"},
    {"/loop/max_run_time_min", "checked against the row its loop mode names, not a fixed row"},
    // Story 4.4: the gain rules bound a ramp's start and length (at least 10
    // ms, inside the session, no overlap, out of the first body pass);
    // signal spec, Gain ramps, Compile order.
    {"/theta_reference/gain/ramps/*/start_s", "bounded by the gain rules, no range row of its own"},
    {"/theta_reference/gain/ramps/*/duration_s", "bounded by the gain rules, no range row of its own"},
    {"/gamma_pac/gain/ramps/*/start_s", "bounded by the gain rules, no range row of its own"},
    {"/gamma_pac/gain/ramps/*/duration_s", "bounded by the gain rules, no range row of its own"},
    {"/binaural/gain/ramps/*/start_s", "bounded by the gain rules, no range row of its own"},
    {"/binaural/gain/ramps/*/duration_s", "bounded by the gain rules, no range row of its own"},
    {"/master/gain/ramps/*/start_s", "bounded by the gain rules, no range row of its own"},
    {"/master/gain/ramps/*/duration_s", "bounded by the gain rules, no range row of its own"},
};

// The field-to-row mapping settled in the Story 1.3 spec (path -> row, scale).
const std::map<std::string, std::pair<std::string, double>> kExpectedRegistration = {
    {"/length_s", {"session-length", 3600.0}},
    {"/loudness_target_lufs", {"loudness-tones", 1.0}},
    // Story 4.2: the stored gain is range-checked in both modes.
    {"/loudness_gain_db", {"loudness-gain", 1.0}},
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
    {"/theta_reference/rate_cycle/period_s", {"rate-cycle-period", 1.0}},             // Story 2.6
    {"/theta_reference/rate_cycle/start_phase_deg", {"rate-cycle-start-phase", 1.0}},  // Story 2.6
    {"/gamma_pac/rate_cycle/period_s", {"rate-cycle-period", 1.0}},                   // Story 2.6
    {"/gamma_pac/rate_cycle/start_phase_deg", {"rate-cycle-start-phase", 1.0}},        // Story 2.6
    // Story 4.4: every gain is linear, row layer-gain (the ramp count is
    // checked by name against row gain-ramp-count, not through a field).
    {"/theta_reference/gain/initial", {"layer-gain", 1.0}},
    {"/theta_reference/gain/ramps/*/to", {"layer-gain", 1.0}},
    {"/gamma_pac/gain/initial", {"layer-gain", 1.0}},
    {"/gamma_pac/gain/ramps/*/to", {"layer-gain", 1.0}},
    {"/binaural/gain/initial", {"layer-gain", 1.0}},
    {"/binaural/gain/ramps/*/to", {"layer-gain", 1.0}},
    {"/master/gain/initial", {"layer-gain", 1.0}},
    {"/master/gain/ramps/*/to", {"layer-gain", 1.0}},
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
      // Story 4.4: a gain has no unit suffix; initial and to are ratios.
      {"/initial", "ratio", 1.0}, {"/to", "ratio", 1.0},
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
      field_at(doctored, "/seed").range_row = "loudness-tones";
      CHECK(any_names(registration_problems(doctored, rows), "/seed",
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
