// Validator, locked ranges, and the carrier rule (Story 1.3).
//
// Three parts:
//
// 1. The engine range table against tests/tables/ranges.tsv, through the
//    validator header (the one internal header this story adds a test for,
//    beside the field table). Expected interface, engine/src/validate/
//    validate.hpp, namespace arcani::validate:
//
//      struct RangeRow {
//        std::string_view id;  // ranges.tsv row id
//        double min;           // row units (h for session-length), always inclusive
//        double max;           // row units
//        bool max_exclusive;   // ranges.tsv max_bound == "exclusive"
//        std::string_view unit = "Hz";  // ranges.tsv unit (defaulted, last)
//      };
//      std::span<const RangeRow> range_rows() noexcept;
//      // One entry per row the field table names, plus binaural-carrier-right
//      // (the derived right carrier, carrier_left_hz + beat_rate_hz).
//
//      std::optional<recipe::Error> check_ranges(const recipe::Recipe&);
//
//      inline constexpr double kCarrierRatio = 4.0;  // threshold row carrier-rule
//      std::optional<recipe::Error> check_carrier_rule(std::string_view parameter,
//                                                      double carrier_hz,
//                                                      double rate_min_hz,
//                                                      double rate_max_hz);
//      // Passes when carrier_hz >= kCarrierRatio * rate_max_hz. Failure:
//      // parameter as given, value json::format_number(carrier_hz), rule
//      // "carrier_rule", limit ">= 24 Hz (4 x 6 Hz, row carrier-rule)".
//
// 2. The boundary matrix of the spec through the public C API, in measure and
//    final mode at 48 kHz. Recipes are made here from one base recipe with
//    substituted value text (shortest round-trip, written out by hand and
//    proved by strtod below), not stored as fixture files. Range errors:
//    ARC_ERR_REJECTED, no plan; parameter the field pointer; value the
//    shortest round-trip text of the field value; rule range.min or
//    range.max; limit "<op> <bound * range_scale> <unit> (row <id>)", where
//    op is ">=" for min, "<=" for an inclusive max, "<" for an exclusive max,
//    and unit is "s" for a scaled seconds field, else the row unit.
//
// 3. Check order: input cap, sample rate, parse, ranges (field table order,
//    derived right carrier after beat rate), final.required. First failure
//    wins.
//
// Story 2.1 (theta reference): theta_reference requires carrier_hz, rate_hz
// (row theta-rate), am_depth_percent (row theta-depth, unit percent), and
// shape. The field table order inside theta_reference is carrier_hz,
// rate_hz, am_depth_percent, shape. Schema faults on shape: a non-string is
// rule "type" (limit "string"); text outside the schema enum is rule "enum",
// value the text, limit the enum members in schema order joined by ", "
// ("sine, smoothed_on_off, sawtooth, reverse_saw, custom"). The schema
// accepts "custom", and compile rejects it after the ranges and before
// final.required: parameter /theta_reference/shape, value custom, rule
// "shape not modeled in the signal spec", limit "sine, smoothed_on_off,
// sawtooth, reverse_saw". The carrier rule checks carrier_hz against
// rate_hz; inside the locked ranges it always passes (100 Hz >= 4 x 6 Hz),
// so its failure is reached only through check_carrier_rule directly.
//
// Story 2.2 (gamma PAC layer, uncoupled): gamma_pac requires carrier_hz (row
// gamma-carrier, 200 to 500 Hz), rate_hz (row gamma-rate, 30 to 60 Hz),
// am_depth_percent (row coupling-depth, 0 to 100 percent), carrier_wave, and
// coupling, in that field table order, between the theta_reference rows and
// the binaural rows. Schema faults: carrier_wave text outside the enum is
// rule "enum", limit "sine, triangle, softened_square"; coupling text outside
// it is rule "enum", limit "uncoupled". The schema accepts triangle and
// softened_square so compile rejects them by name: parameter
// /gamma_pac/carrier_wave, value the text, rule "non-sine carrier not
// modeled" (validate::kNonSineCarrierRule), limit "sine"
// (validate::kModeledGammaCarrierWaves). The gamma carrier rule checks
// carrier_hz against rate_hz and, unlike theta, is reachable inside the
// locked ranges: a 200 Hz carrier at a 60 Hz rate fails with limit
// ">= 240 Hz (4 x 60 Hz, row carrier-rule)". Compile order after the ranges:
// theta carrier rule, theta custom shape, gamma carrier rule, carrier wave
// rule, then final.required.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#if __has_include("validate/validate.hpp") && defined(ARC_ERROR_FIELD_BYTES)

#include "api_helpers.hpp"
#include "recipe/field_table.hpp"
#include "tables.hpp"
#include "validate/validate.hpp"

#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <initializer_list>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace api = arcani::test::api;
namespace recipe = arcani::recipe;
namespace tables = arcani::test::tables;
namespace validate = arcani::validate;

namespace {

// ------------------------------------------------------------ range table

using RowLookup = std::map<std::string, tables::Row>;

// Problems between an engine range table and the table rows. lookup returns
// nullptr for an unknown id.
template <class Lookup>
std::vector<std::string> range_table_problems(std::span<const validate::RangeRow> engine,
                                              const std::set<std::string>& expected_ids,
                                              Lookup lookup) {
  std::vector<std::string> out;
  std::set<std::string> seen;
  for (const auto& e : engine) {
    const std::string id(e.id);
    if (!seen.insert(id).second) {
      out.push_back(id + ": listed twice in the engine range table");
      continue;
    }
    if (expected_ids.count(id) == 0) {
      out.push_back(id + ": in the engine range table but named by no field");
    }
    const tables::Row* r = lookup(id);
    if (r == nullptr) {
      out.push_back(id + ": not a row of ranges.tsv");
      continue;
    }
    if (r->kind != "ranges") {
      out.push_back(id + ": not a range row");
      continue;
    }
    if (!(e.min == r->min)) {
      out.push_back(id + ": min differs from ranges.tsv " + r->min_text);
    }
    if (!(e.max == r->max)) {
      out.push_back(id + ": max differs from ranges.tsv " + r->max_text);
    }
    if (e.max_exclusive != (r->max_bound == "exclusive")) {
      out.push_back(id + ": max bound differs from ranges.tsv " + r->max_bound);
    }
    if (std::string(e.unit) != r->unit) {
      out.push_back(id + ": unit differs from ranges.tsv " + r->unit);
    }
    if (!r->pending.empty()) {
      out.push_back(id + ": still pending in ranges.tsv on " + r->pending);
    }
  }
  for (const auto& id : expected_ids) {
    if (seen.count(id) == 0) {
      out.push_back(id + ": named by the field table but missing from the engine range table");
    }
  }
  return out;
}

std::set<std::string> ids_named_by_fields() {
  std::set<std::string> out;
  for (const auto& f : recipe::fields()) {
    if (!f.range_row.empty()) {
      out.insert(std::string(f.range_row));
    }
  }
  out.insert("binaural-carrier-right");
  return out;
}

RowLookup load_rows() {
  RowLookup out;
  for (const auto& r : tables::load_tables(ARCANI_TABLES_DIR)) {
    out[r.id] = r;
  }
  return out;
}

bool any_names(const std::vector<std::string>& problems, const std::string& id,
               const std::string& words) {
  for (const auto& p : problems) {
    if (p.find(id) != std::string::npos && p.find(words) != std::string::npos) {
      return true;
    }
  }
  return false;
}

// ------------------------------------------------------------ recipes

// Value text for each numeric field of the base recipe; empty theta or
// binaural text drops that layer.
struct Values {
  std::string length_s = "1";
  std::string loudness_target_lufs = "-36";
  std::string theta_carrier_hz = "300";
  // Story 2.1. Empty text omits that theta field; theta_shape is written as
  // given, so quote a string or pass any other JSON value.
  std::string theta_rate_hz = "6";
  std::string theta_am_depth_percent = "75";
  std::string theta_shape = "\"sine\"";
  std::string carrier_left_hz = "400";
  std::string beat_rate_hz = "6";
  // Story 2.2. The gamma layer is off by default, so every earlier case
  // keeps its recipe. Empty text omits that gamma field; the two string
  // fields are written as given.
  std::string gamma_carrier_hz = "250";
  std::string gamma_rate_hz = "40";
  std::string gamma_am_depth_percent = "25";
  std::string gamma_carrier_wave = "\"sine\"";
  std::string gamma_coupling = "\"uncoupled\"";
  bool theta = true;
  bool gamma = false;
  bool binaural = true;
  bool gain = true;  // loudness_gain_db and loudness_hash
};

std::string make_recipe(const Values& v) {
  std::string s =
      "{\n"
      "  \"schema_version\": \"1.0\",\n"
      "  \"engine_version\": \"0.0.1\",\n"
      "  \"seed\": 42,\n"
      "  \"author\": \"Arcani test fixtures\",\n"
      "  \"date\": \"2026-11-05\",\n"
      "  \"rationale\": \"Story 1.3 range matrix recipe, made in the test.\",\n"
      "  \"length_s\": " + v.length_s + ",\n"
      "  \"loudness_target_lufs\": " + v.loudness_target_lufs;
  if (v.gain) {
    s += ",\n  \"loudness_gain_db\": -1.5,\n"
         "  \"loudness_hash\": \"6a29ccd608e4c1945bfff95af078a97daea48eca54a38e065ae33dfa9c2d83a6\"";
  }
  if (v.theta) {
    std::string body;
    const auto add = [&body](const char* key, const std::string& text) {
      if (text.empty()) {
        return;
      }
      body += body.empty() ? "\n" : ",\n";
      body += std::string("    \"") + key + "\": " + text;
    };
    add("carrier_hz", v.theta_carrier_hz);
    add("rate_hz", v.theta_rate_hz);
    add("am_depth_percent", v.theta_am_depth_percent);
    add("shape", v.theta_shape);
    s += ",\n  \"theta_reference\": {" + body + "\n  }";
  }
  if (v.gamma) {
    std::string body;
    const auto add = [&body](const char* key, const std::string& text) {
      if (text.empty()) {
        return;
      }
      body += body.empty() ? "\n" : ",\n";
      body += std::string("    \"") + key + "\": " + text;
    };
    add("carrier_hz", v.gamma_carrier_hz);
    add("rate_hz", v.gamma_rate_hz);
    add("am_depth_percent", v.gamma_am_depth_percent);
    add("carrier_wave", v.gamma_carrier_wave);
    add("coupling", v.gamma_coupling);
    s += ",\n  \"gamma_pac\": {" + body + "\n  }";
  }
  if (v.binaural) {
    s += ",\n  \"binaural\": {\n    \"carrier_left_hz\": " + v.carrier_left_hz +
         ",\n    \"beat_rate_hz\": " + v.beat_rate_hz + "\n  }";
  }
  s += "\n}\n";
  return s;
}

constexpr arc_mode kModes[] = {ARC_MODE_MEASURE, ARC_MODE_FINAL};

void expect_plan(const Values& v) {
  const std::string text = make_recipe(v);
  for (const arc_mode mode : kModes) {
    INFO("mode " << mode << "\n" << text);
    auto plan = api::compile_ok(text, api::options(mode, 48000));
    CHECK(plan != nullptr);
  }
}

struct Want {
  std::string parameter, value, rule, limit;
};

void expect_rejected(const Values& v, const Want& want,
                     std::initializer_list<arc_mode> modes = {ARC_MODE_MEASURE, ARC_MODE_FINAL}) {
  const std::string text = make_recipe(v);
  for (const arc_mode mode : modes) {
    INFO("mode " << mode << "\n" << text);
    const api::Compiled c = api::compile(text, api::options(mode, 48000));
    INFO(api::describe(c.error));
    CHECK(c.status == ARC_ERR_REJECTED);
    CHECK(c.plan == nullptr);
    REQUIRE(api::all_written(c.error));
    CHECK(std::string(c.error.parameter) == want.parameter);
    CHECK(std::string(c.error.value) == want.value);
    CHECK(std::string(c.error.rule) == want.rule);
    CHECK(std::string(c.error.limit) == want.limit);
  }
}

// The hand-written value text reads back to exactly x (the shortest
// round-trip digits were taken from the binary64 value; strtod proves the
// text names that value).
void require_text_is(const std::string& text, double x) {
  INFO(text);
  REQUIRE(std::strtod(text.c_str(), nullptr) == x);
}

double below(double x) { return std::nextafter(x, -std::numeric_limits<double>::infinity()); }
double above(double x) { return std::nextafter(x, std::numeric_limits<double>::infinity()); }

}  // namespace

// ------------------------------------------------------------ part 1

TEST_CASE("engine range table equals ranges.tsv row for row", "[validate][ranges]") {
  const auto expected_ids = ids_named_by_fields();
  // Story 2.1 adds theta-rate and theta-depth; Story 2.2 adds gamma-carrier,
  // gamma-rate, and coupling-depth.
  REQUIRE(expected_ids.size() == 11);
  CHECK(expected_ids.count("theta-rate") == 1);
  CHECK(expected_ids.count("theta-depth") == 1);
  CHECK(expected_ids.count("gamma-carrier") == 1);
  CHECK(expected_ids.count("gamma-rate") == 1);
  CHECK(expected_ids.count("coupling-depth") == 1);
  // row() is the assertion call: it records each id for the row coverage check.
  const auto via_row = [](const std::string& id) -> const tables::Row* {
    try {
      return &tables::row(id);
    } catch (const tables::TableError&) {
      return nullptr;
    }
  };
  const auto problems = range_table_problems(validate::range_rows(), expected_ids, via_row);
  for (const auto& p : problems) {
    UNSCOPED_INFO(p);
  }
  CHECK(problems.empty());
}

TEST_CASE("range table comparison catches a doctored engine table", "[validate][ranges]") {
  const auto rows = load_rows();
  const auto lookup = [&](const std::string& id) -> const tables::Row* {
    const auto it = rows.find(id);
    return it == rows.end() ? nullptr : &it->second;
  };
  const auto expected_ids = ids_named_by_fields();
  const std::vector<validate::RangeRow> real(validate::range_rows().begin(),
                                             validate::range_rows().end());
  auto find = [](std::vector<validate::RangeRow>& t, std::string_view id) -> validate::RangeRow& {
    for (auto& e : t) {
      if (e.id == id) {
        return e;
      }
    }
    FAIL("no engine entry " << std::string(id));
    return t.front();
  };

  SECTION("the real table passes against the loaded rows") {
    CHECK(range_table_problems(real, expected_ids, lookup).empty());
  }
  SECTION("must fail: min one ulp off") {
    auto t = real;
    find(t, "theta-carrier").min = below(100.0);
    CHECK(any_names(range_table_problems(t, expected_ids, lookup), "theta-carrier", "min"));
  }
  SECTION("must fail: max one ulp off") {
    auto t = real;
    find(t, "session-length").max = above(8.0);
    CHECK(any_names(range_table_problems(t, expected_ids, lookup), "session-length", "max"));
  }
  SECTION("must fail: max bound flipped") {
    auto t = real;
    find(t, "beat-rate").max_exclusive = false;
    CHECK(any_names(range_table_problems(t, expected_ids, lookup), "beat-rate", "bound"));
  }
  SECTION("must fail: unit differs") {
    auto t = real;
    find(t, "session-length").unit = "s";
    CHECK(any_names(range_table_problems(t, expected_ids, lookup), "session-length", "unit"));
  }
  SECTION("must fail: a pending row") {
    auto doctored = rows;
    doctored.at("binaural-carrier-right").pending = "1-3-validator-framework-locked-ranges-and-carrier-rule";
    const auto doctored_lookup = [&](const std::string& id) -> const tables::Row* {
      const auto it = doctored.find(id);
      return it == doctored.end() ? nullptr : &it->second;
    };
    CHECK(any_names(range_table_problems(real, expected_ids, doctored_lookup),
                    "binaural-carrier-right", "pending"));
  }
  SECTION("must fail: an entry missing") {
    std::vector<validate::RangeRow> t;
    for (const auto& e : real) {
      if (e.id != "binaural-carrier-right") {
        t.push_back(e);
      }
    }
    CHECK(any_names(range_table_problems(t, expected_ids, lookup), "binaural-carrier-right",
                    "missing"));
  }
  SECTION("must fail: an id that is no row") {
    auto t = real;
    t.push_back({"no-such-row", 0.0, 1.0, false});
    CHECK(any_names(range_table_problems(t, expected_ids, lookup), "no-such-row", "ranges.tsv"));
  }
}

TEST_CASE("carrier ratio constant equals threshold row carrier-rule", "[validate][carrier]") {
  CHECK(validate::kCarrierRatio == tables::row("carrier-rule").value());
}

TEST_CASE("carrier rule: exactly 4 times passes, the next double below fails", "[validate][carrier]") {
  const auto ok = validate::check_carrier_rule("/fixture/carrier_hz", 24.0, 6.0, 6.0);
  CHECK_FALSE(ok.has_value());

  const double just_below = below(24.0);
  require_text_is("23.999999999999996", just_below);
  const auto bad = validate::check_carrier_rule("/fixture/carrier_hz", just_below, 6.0, 6.0);
  REQUIRE(bad.has_value());
  CHECK(bad->parameter == "/fixture/carrier_hz");
  CHECK(bad->value == "23.999999999999996");
  CHECK(bad->rule == "carrier_rule");
  CHECK(bad->limit == ">= 24 Hz (4 x 6 Hz, row carrier-rule)");
}

TEST_CASE("carrier rule judges a rate interval by its maximum", "[validate][carrier]") {
  // 24 Hz passes against the interval minimum (4 x 1) but not the maximum.
  const auto bad = validate::check_carrier_rule("/fixture/carrier_hz", 24.0, 1.0, 7.0);
  REQUIRE(bad.has_value());
  CHECK(bad->parameter == "/fixture/carrier_hz");
  CHECK(bad->value == "24");
  CHECK(bad->rule == "carrier_rule");
  CHECK(bad->limit == ">= 28 Hz (4 x 7 Hz, row carrier-rule)");

  CHECK_FALSE(validate::check_carrier_rule("/fixture/carrier_hz", 28.0, 1.0, 7.0).has_value());
  CHECK(validate::check_carrier_rule("/fixture/carrier_hz", below(28.0), 1.0, 7.0).has_value());
}

// ------------------------------------------------------------ part 2

TEST_CASE("range matrix: the base recipe and every stub chain fixture compile",
          "[validate][compile]") {
  expect_plan(Values{});
  for (const char* name : {api::kBeat0, api::kBeat6, api::kNoLayers}) {
    for (const arc_mode mode : kModes) {
      INFO(name << ", mode " << mode);
      CHECK(api::compile_ok(api::valid(name), api::options(mode, 48000)) != nullptr);
    }
  }
  CHECK(api::compile_ok(api::valid(api::kNoGain), api::options(ARC_MODE_MEASURE, 48000)) != nullptr);
}

TEST_CASE("range matrix: inclusive bounds pass at the bound", "[validate][compile]") {
  for (const char* theta : {"100", "500"}) {
    Values v;
    v.theta_carrier_hz = theta;
    expect_plan(v);
  }
  {
    Values v;
    v.length_s = "28800";  // session-length 8 h
    expect_plan(v);
  }
  {
    Values v;
    v.length_s = "0";
    expect_plan(v);
  }
  {
    Values v;
    v.beat_rate_hz = "0";
    expect_plan(v);
  }
  {
    Values v;
    v.carrier_left_hz = "0";  // binaural-carrier min 0, inclusive
    expect_plan(v);
  }
  {
    Values v;
    v.loudness_target_lufs = "-36";
    expect_plan(v);
  }
}

TEST_CASE("range matrix: just outside an inclusive bound is rejected", "[validate][compile]") {
  struct Case {
    std::string text;
    double value;
    void (*set)(Values&, const std::string&);
    Want want;
  };
  const auto theta = [](Values& v, const std::string& t) { v.theta_carrier_hz = t; };
  const auto length = [](Values& v, const std::string& t) { v.length_s = t; };
  const auto target = [](Values& v, const std::string& t) { v.loudness_target_lufs = t; };
  const Case cases[] = {
      {"99.99999999999999", below(100.0), theta,
       {"/theta_reference/carrier_hz", "99.99999999999999", "range.min",
        ">= 100 Hz (row theta-carrier)"}},
      {"500.00000000000006", above(500.0), theta,
       {"/theta_reference/carrier_hz", "500.00000000000006", "range.max",
        "<= 500 Hz (row theta-carrier)"}},
      {"28800.000000000004", above(28800.0), length,
       {"/length_s", "28800.000000000004", "range.max", "<= 28800 s (row session-length)"}},
      {"-35.99999999999999", above(-36.0), target,
       {"/loudness_target_lufs", "-35.99999999999999", "range.max",
        "<= -36 LUFS-I (row loudness-tones)"}},
      {"-36.00000000000001", below(-36.0), target,
       {"/loudness_target_lufs", "-36.00000000000001", "range.min",
        ">= -36 LUFS-I (row loudness-tones)"}},
  };
  for (const auto& c : cases) {
    require_text_is(c.text, c.value);
    Values v;
    c.set(v, c.text);
    expect_rejected(v, c.want);
  }
}

TEST_CASE("range matrix: an exclusive bound rejects the bound itself", "[validate][compile]") {
  {
    Values v;
    v.carrier_left_hz = "1000";
    expect_rejected(v, {"/binaural/carrier_left_hz", "1000", "range.max",
                        "< 1000 Hz (row binaural-carrier)"});
  }
  {
    Values v;
    v.beat_rate_hz = "30";
    expect_rejected(v, {"/binaural/beat_rate_hz", "30", "range.max", "< 30 Hz (row beat-rate)"});
  }
}

TEST_CASE("range matrix: just inside an exclusive bound compiles", "[validate][compile]") {
  require_text_is("999.9999999999999", below(1000.0));
  require_text_is("29.999999999999996", below(30.0));
  {
    Values v;
    v.carrier_left_hz = "999.9999999999999";
    expect_plan(v);
  }
  {
    Values v;
    v.beat_rate_hz = "29.999999999999996";
    expect_plan(v);
  }
  {
    // Both at the top: the derived right carrier, summed in binary64 as
    // compile does, stays below 1030 Hz, so binaural-carrier-right passes.
    // From in-range inputs the sum cannot reach 1030 (the left deficit alone
    // exceeds half an ulp at 1030 once the beat deficit is added), so its
    // must-fail side is not reachable through arc_compile.
    volatile double left = below(1000.0);
    volatile double beat = below(30.0);
    CHECK(left + beat < 1030.0);
    Values v;
    v.carrier_left_hz = "999.9999999999999";
    v.beat_rate_hz = "29.999999999999996";
    expect_plan(v);
  }
}

TEST_CASE("range matrix: negative values are rejected at the minimum", "[validate][compile]") {
  {
    Values v;
    v.length_s = "-1";
    expect_rejected(v, {"/length_s", "-1", "range.min", ">= 0 s (row session-length)"});
  }
  {
    Values v;
    v.theta_carrier_hz = "-0.5";
    expect_rejected(v, {"/theta_reference/carrier_hz", "-0.5", "range.min",
                        ">= 100 Hz (row theta-carrier)"});
  }
  {
    Values v;
    v.carrier_left_hz = "-0.5";
    expect_rejected(v, {"/binaural/carrier_left_hz", "-0.5", "range.min",
                        ">= 0 Hz (row binaural-carrier)"});
  }
  {
    Values v;
    v.beat_rate_hz = "-0.5";
    expect_rejected(v, {"/binaural/beat_rate_hz", "-0.5", "range.min",
                        ">= 0 Hz (row beat-rate)"});
  }
}

TEST_CASE("range matrix: an absent layer is not range-checked", "[validate][compile]") {
  // Out-of-range text in a dropped layer never reaches the recipe.
  Values v;
  v.theta = false;
  v.binaural = false;
  expect_plan(v);
}

TEST_CASE("valid/ means schema-valid: the out-of-range hash fixture is rejected at compile",
          "[validate][compile]") {
  const std::string text = api::valid("both-layers-loudness-target-changed.json");
  for (const arc_mode mode : kModes) {
    INFO("mode " << mode);
    const api::Compiled c = api::compile(text, api::options(mode, 48000));
    INFO(api::describe(c.error));
    CHECK(c.status == ARC_ERR_REJECTED);
    CHECK(c.plan == nullptr);
    REQUIRE(api::all_written(c.error));
    CHECK(std::string(c.error.parameter) == "/loudness_target_lufs");
    CHECK(std::string(c.error.value) == "-36.5");
    CHECK(std::string(c.error.rule) == "range.min");
    CHECK(std::string(c.error.limit) == ">= -36 LUFS-I (row loudness-tones)");
  }
  // Every other valid fixture compiles in measure mode. The folder is read,
  // so a new valid/ fixture is covered; an expected rejection must be listed.
  // Story 2.2 adds three schema-valid gamma fixtures that compile rejects by
  // a named rule (checked one by one in the gamma section below).
  const std::set<std::string> expected_rejected = {
      "both-layers-loudness-target-changed.json", "gamma-carrier-rule-200hz-60hz.json",
      "gamma-carrier-wave-triangle.json", "gamma-carrier-wave-softened-square.json"};
  std::set<std::string> rejected_seen;
  std::size_t compiled = 0;
  for (const auto& entry :
       std::filesystem::directory_iterator(std::string(ARCANI_RECIPES_DIR) + "/fixtures/valid")) {
    if (!entry.is_regular_file() || entry.path().extension() != ".json") {
      continue;
    }
    const std::string name = entry.path().filename().string();
    INFO(name);
    if (expected_rejected.count(name) == 1) {
      rejected_seen.insert(name);
      continue;
    }
    CHECK(api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, 48000)) != nullptr);
    ++compiled;
  }
  CHECK(rejected_seen == expected_rejected);
  CHECK(compiled > 0);
}

// ------------------------------------------------------------ theta reference (Story 2.1)

TEST_CASE("theta: every shape compiles in both modes at both rates", "[validate][theta]") {
  for (const char* shape : {"\"sine\"", "\"smoothed_on_off\"", "\"sawtooth\"", "\"reverse_saw\""}) {
    Values v;
    v.theta_shape = shape;
    const std::string text = make_recipe(v);
    for (const arc_mode mode : kModes) {
      for (const std::uint32_t fs : {44100u, 48000u}) {
        INFO(shape << ", mode " << mode << ", fs " << fs);
        CHECK(api::compile_ok(text, api::options(mode, fs)) != nullptr);
      }
    }
  }
}

TEST_CASE("theta: range edges pass at the bound", "[validate][theta]") {
  for (const char* carrier : {"100", "500"}) {
    Values v;
    v.theta_carrier_hz = carrier;
    expect_plan(v);
  }
  for (const char* rate : {"1", "6"}) {
    Values v;
    v.theta_rate_hz = rate;
    expect_plan(v);
  }
  for (const char* depth : {"0", "100"}) {
    Values v;
    v.theta_am_depth_percent = depth;
    expect_plan(v);
  }
  {
    // The tightest in-range pair for the carrier rule: 100 Hz needs only 24 Hz.
    Values v;
    v.theta_carrier_hz = "100";
    v.theta_rate_hz = "6";
    expect_plan(v);
  }
}

TEST_CASE("theta: just outside a range edge is rejected with its row", "[validate][theta]") {
  struct Case {
    std::string text;
    void (*set)(Values&, const std::string&);
    Want want;
  };
  const auto carrier = [](Values& v, const std::string& t) { v.theta_carrier_hz = t; };
  const auto rate = [](Values& v, const std::string& t) { v.theta_rate_hz = t; };
  const auto depth = [](Values& v, const std::string& t) { v.theta_am_depth_percent = t; };
  const Case cases[] = {
      {"99.99", carrier,
       {"/theta_reference/carrier_hz", "99.99", "range.min", ">= 100 Hz (row theta-carrier)"}},
      {"500.01", carrier,
       {"/theta_reference/carrier_hz", "500.01", "range.max", "<= 500 Hz (row theta-carrier)"}},
      {"0.99", rate, {"/theta_reference/rate_hz", "0.99", "range.min", ">= 1 Hz (row theta-rate)"}},
      {"6.01", rate, {"/theta_reference/rate_hz", "6.01", "range.max", "<= 6 Hz (row theta-rate)"}},
      {"0.9999999999999999", rate,
       {"/theta_reference/rate_hz", "0.9999999999999999", "range.min", ">= 1 Hz (row theta-rate)"}},
      {"6.000000000000001", rate,
       {"/theta_reference/rate_hz", "6.000000000000001", "range.max", "<= 6 Hz (row theta-rate)"}},
      {"-0.01", depth,
       {"/theta_reference/am_depth_percent", "-0.01", "range.min",
        ">= 0 percent (row theta-depth)"}},
      {"100.01", depth,
       {"/theta_reference/am_depth_percent", "100.01", "range.max",
        "<= 100 percent (row theta-depth)"}},
      {"100.00000000000001", depth,
       {"/theta_reference/am_depth_percent", "100.00000000000001", "range.max",
        "<= 100 percent (row theta-depth)"}},
  };
  require_text_is("0.9999999999999999", below(1.0));
  require_text_is("6.000000000000001", above(6.0));
  require_text_is("100.00000000000001", above(100.0));
  for (const auto& c : cases) {
    Values v;
    c.set(v, c.text);
    expect_rejected(v, c.want);
  }
}

TEST_CASE("theta: the carrier rule names a carrier below 4 x the theta rate", "[validate][theta]") {
  // Inside the locked ranges every pair passes, so the rule is checked
  // directly, with the theta parameter name compile uses.
  CHECK_FALSE(validate::check_carrier_rule("/theta_reference/carrier_hz", 24.0, 6.0, 6.0).has_value());
  const auto bad = validate::check_carrier_rule("/theta_reference/carrier_hz", below(24.0), 6.0, 6.0);
  REQUIRE(bad.has_value());
  CHECK(bad->parameter == "/theta_reference/carrier_hz");
  CHECK(bad->rule == "carrier_rule");
  CHECK(bad->limit == ">= 24 Hz (4 x 6 Hz, row carrier-rule)");
  // The lowest carrier against the highest rate passes.
  const auto& carrier = tables::row("theta-carrier");
  const auto& rate = tables::row("theta-rate");
  CHECK(carrier.min >= validate::kCarrierRatio * rate.max);
  CHECK_FALSE(validate::check_carrier_rule("/theta_reference/carrier_hz", carrier.min, rate.min,
                                           rate.max)
                  .has_value());
}

TEST_CASE("theta: a custom shape is rejected by name, with no plan", "[validate][theta]") {
  Values v;
  v.theta_shape = "\"custom\"";
  expect_rejected(v, {"/theta_reference/shape", "custom", "shape not modeled in the signal spec",
                      "sine, smoothed_on_off, sawtooth, reverse_saw"});
  for (const std::uint32_t fs : {44100u, 48000u}) {
    const api::Compiled c = api::compile(make_recipe(v), api::options(ARC_MODE_MEASURE, fs));
    CHECK(c.status == ARC_ERR_REJECTED);
    CHECK(c.plan == nullptr);
  }
}

TEST_CASE("theta: shape text outside the schema enum is a schema fault", "[validate][theta]") {
  const std::string enum_limit = "sine, smoothed_on_off, sawtooth, reverse_saw, custom";
  for (const char* text : {"square", "Sine", "smoothed-on-off", ""}) {
    Values v;
    v.theta_shape = std::string("\"") + text + "\"";
    expect_rejected(v, {"/theta_reference/shape", text, "enum", enum_limit});
  }
  {
    Values v;
    v.theta_shape = "3";
    const api::Compiled c = api::compile(make_recipe(v), api::options(ARC_MODE_MEASURE, 48000));
    REQUIRE(api::all_written(c.error));
    CHECK(c.status == ARC_ERR_REJECTED);
    CHECK(std::string(c.error.parameter) == "/theta_reference/shape");
    CHECK(std::string(c.error.rule) == "type");
    CHECK(std::string(c.error.limit) == "string");
  }
}

TEST_CASE("theta: every theta field is required", "[validate][theta]") {
  struct Case {
    void (*drop)(Values&);
    const char* parameter;
  };
  const Case cases[] = {
      {[](Values& v) { v.theta_carrier_hz.clear(); }, "/theta_reference/carrier_hz"},
      {[](Values& v) { v.theta_rate_hz.clear(); }, "/theta_reference/rate_hz"},
      {[](Values& v) { v.theta_am_depth_percent.clear(); }, "/theta_reference/am_depth_percent"},
      {[](Values& v) { v.theta_shape.clear(); }, "/theta_reference/shape"},
  };
  for (const auto& c : cases) {
    Values v;
    c.drop(v);
    const api::Compiled r = api::compile(make_recipe(v), api::options(ARC_MODE_MEASURE, 48000));
    INFO(c.parameter << ": " << api::describe(r.error));
    REQUIRE(api::all_written(r.error));
    CHECK(r.status == ARC_ERR_REJECTED);
    CHECK(std::string(r.error.parameter) == c.parameter);
    CHECK(std::string(r.error.rule) == "required");
  }
}

TEST_CASE("theta: check order inside theta_reference, ranges before the shape rule",
          "[validate][theta][order]") {
  {
    Values v;  // carrier before rate before depth
    v.theta_carrier_hz = "50";
    v.theta_rate_hz = "7";
    v.theta_am_depth_percent = "101";
    expect_rejected(v, {"/theta_reference/carrier_hz", "50", "range.min",
                        ">= 100 Hz (row theta-carrier)"});
  }
  {
    Values v;
    v.theta_rate_hz = "7";
    v.theta_am_depth_percent = "101";
    expect_rejected(v, {"/theta_reference/rate_hz", "7", "range.max", "<= 6 Hz (row theta-rate)"});
  }
  {
    Values v;  // a range fault wins over the custom shape
    v.theta_am_depth_percent = "101";
    v.theta_shape = "\"custom\"";
    expect_rejected(v, {"/theta_reference/am_depth_percent", "101", "range.max",
                        "<= 100 percent (row theta-depth)"});
  }
  {
    Values v;  // a binaural range fault also comes before the shape rule
    v.theta_shape = "\"custom\"";
    v.carrier_left_hz = "1000";
    expect_rejected(v, {"/binaural/carrier_left_hz", "1000", "range.max",
                        "< 1000 Hz (row binaural-carrier)"});
  }
  {
    Values v;  // the shape rule comes before final.required
    v.gain = false;
    v.theta_shape = "\"custom\"";
    expect_rejected(v, {"/theta_reference/shape", "custom", "shape not modeled in the signal spec",
                        "sine, smoothed_on_off, sawtooth, reverse_saw"},
                    {ARC_MODE_FINAL});
  }
}

// ------------------------------------------------------------ gamma PAC layer (Story 2.2)

namespace {

Values with_gamma() {
  Values v;
  v.gamma = true;
  return v;
}

const char* const kNonSine = "non-sine carrier not modeled";

}  // namespace

TEST_CASE("gamma: the base gamma recipe compiles in both modes at both rates", "[validate][gamma]") {
  for (const bool theta : {true, false}) {
    for (const bool binaural : {true, false}) {
      Values v = with_gamma();
      v.theta = theta;
      v.binaural = binaural;
      const std::string text = make_recipe(v);
      for (const arc_mode mode : kModes) {
        for (const std::uint32_t fs : {44100u, 48000u}) {
          INFO("theta " << theta << ", binaural " << binaural << ", mode " << mode << ", fs " << fs);
          CHECK(api::compile_ok(text, api::options(mode, fs)) != nullptr);
        }
      }
    }
  }
}

TEST_CASE("gamma: every gamma fixture compiles at both rates", "[validate][gamma]") {
  for (const char* name : {"gamma-uncoupled-40hz-25pct.json", "gamma-uncoupled-40hz-100pct.json",
                           "gamma-uncoupled-60hz-25pct.json", "gamma-uncoupled-60hz-100pct.json",
                           "theta-gamma-uncoupled.json"}) {
    for (const std::uint32_t fs : {44100u, 48000u}) {
      INFO(name << ", fs " << fs);
      CHECK(api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs)) != nullptr);
    }
  }
}

TEST_CASE("gamma: range edges pass at the bound (carrier rule permitting)", "[validate][gamma]") {
  {
    // The carrier floor needs a rate the carrier rule allows: 200 >= 4 x 30.
    Values v = with_gamma();
    v.gamma_carrier_hz = "200";
    v.gamma_rate_hz = "30";
    expect_plan(v);
  }
  {
    Values v = with_gamma();
    v.gamma_carrier_hz = "500";
    expect_plan(v);
  }
  for (const char* rate : {"30", "60"}) {
    Values v = with_gamma();
    v.gamma_rate_hz = rate;  // 250 Hz >= 4 x 60 Hz
    expect_plan(v);
  }
  for (const char* depth : {"0", "100"}) {
    Values v = with_gamma();
    v.gamma_am_depth_percent = depth;
    expect_plan(v);
  }
  {
    Values v = with_gamma();
    v.gamma_carrier_hz = "500";
    v.gamma_rate_hz = "60";
    v.gamma_am_depth_percent = "100";
    expect_plan(v);
  }
}

TEST_CASE("gamma: just outside a range edge is rejected with its row", "[validate][gamma]") {
  struct Case {
    std::string text;
    void (*set)(Values&, const std::string&);
    Want want;
  };
  // The carrier cases run at a 30 Hz rate, so the carrier rule never decides.
  const auto carrier = [](Values& v, const std::string& t) {
    v.gamma_carrier_hz = t;
    v.gamma_rate_hz = "30";
  };
  const auto rate = [](Values& v, const std::string& t) { v.gamma_rate_hz = t; };
  const auto depth = [](Values& v, const std::string& t) { v.gamma_am_depth_percent = t; };
  const Case cases[] = {
      {"199.99", carrier,
       {"/gamma_pac/carrier_hz", "199.99", "range.min", ">= 200 Hz (row gamma-carrier)"}},
      {"199.99999999999997", carrier,
       {"/gamma_pac/carrier_hz", "199.99999999999997", "range.min", ">= 200 Hz (row gamma-carrier)"}},
      {"500.01", carrier,
       {"/gamma_pac/carrier_hz", "500.01", "range.max", "<= 500 Hz (row gamma-carrier)"}},
      {"500.00000000000006", carrier,
       {"/gamma_pac/carrier_hz", "500.00000000000006", "range.max", "<= 500 Hz (row gamma-carrier)"}},
      {"29.99", rate, {"/gamma_pac/rate_hz", "29.99", "range.min", ">= 30 Hz (row gamma-rate)"}},
      {"29.999999999999996", rate,
       {"/gamma_pac/rate_hz", "29.999999999999996", "range.min", ">= 30 Hz (row gamma-rate)"}},
      {"60.01", rate, {"/gamma_pac/rate_hz", "60.01", "range.max", "<= 60 Hz (row gamma-rate)"}},
      {"60.00000000000001", rate,
       {"/gamma_pac/rate_hz", "60.00000000000001", "range.max", "<= 60 Hz (row gamma-rate)"}},
      {"-0.01", depth,
       {"/gamma_pac/am_depth_percent", "-0.01", "range.min", ">= 0 percent (row coupling-depth)"}},
      {"100.01", depth,
       {"/gamma_pac/am_depth_percent", "100.01", "range.max", "<= 100 percent (row coupling-depth)"}},
      {"100.00000000000001", depth,
       {"/gamma_pac/am_depth_percent", "100.00000000000001", "range.max",
        "<= 100 percent (row coupling-depth)"}},
  };
  require_text_is("199.99999999999997", below(200.0));
  require_text_is("500.00000000000006", above(500.0));
  require_text_is("29.999999999999996", below(30.0));
  require_text_is("60.00000000000001", above(60.0));
  require_text_is("100.00000000000001", above(100.0));
  for (const auto& c : cases) {
    Values v = with_gamma();
    c.set(v, c.text);
    expect_rejected(v, c.want);
  }
}

TEST_CASE("gamma: the carrier rule rejects a carrier below 4 x the gamma rate", "[validate][gamma]") {
  // Unlike theta, the rule is reachable inside the locked ranges.
  const auto& carrier = tables::row("gamma-carrier");
  const auto& rate = tables::row("gamma-rate");
  CHECK(carrier.min < validate::kCarrierRatio * rate.max);
  {
    Values v = with_gamma();
    v.gamma_carrier_hz = "200";
    v.gamma_rate_hz = "60";
    expect_rejected(v, {"/gamma_pac/carrier_hz", "200", "carrier_rule",
                        ">= 240 Hz (4 x 60 Hz, row carrier-rule)"});
  }
  {
    Values v = with_gamma();
    v.gamma_carrier_hz = "240";
    v.gamma_rate_hz = "60";
    expect_plan(v);
  }
  {
    require_text_is("239.99999999999997", below(240.0));
    Values v = with_gamma();
    v.gamma_carrier_hz = "239.99999999999997";
    v.gamma_rate_hz = "60";
    expect_rejected(v, {"/gamma_pac/carrier_hz", "239.99999999999997", "carrier_rule",
                        ">= 240 Hz (4 x 60 Hz, row carrier-rule)"});
  }
  {
    Values v = with_gamma();
    v.gamma_carrier_hz = "200";
    v.gamma_rate_hz = "50.5";
    expect_rejected(v, {"/gamma_pac/carrier_hz", "200", "carrier_rule",
                        ">= 202 Hz (4 x 50.5 Hz, row carrier-rule)"});
  }
  {
    // No plan at either sample rate.
    Values v = with_gamma();
    v.gamma_carrier_hz = "200";
    v.gamma_rate_hz = "60";
    for (const std::uint32_t fs : {44100u, 48000u}) {
      const api::Compiled c = api::compile(make_recipe(v), api::options(ARC_MODE_MEASURE, fs));
      CHECK(c.status == ARC_ERR_REJECTED);
      CHECK(c.plan == nullptr);
    }
  }
}

TEST_CASE("gamma: a non-sine carrier wave is rejected by name, with no plan", "[validate][gamma]") {
  for (const char* wave : {"triangle", "softened_square"}) {
    Values v = with_gamma();
    v.gamma_carrier_wave = std::string("\"") + wave + "\"";
    expect_rejected(v, {"/gamma_pac/carrier_wave", wave, kNonSine, "sine"});
    for (const std::uint32_t fs : {44100u, 48000u}) {
      const api::Compiled c = api::compile(make_recipe(v), api::options(ARC_MODE_MEASURE, fs));
      CHECK(c.status == ARC_ERR_REJECTED);
      CHECK(c.plan == nullptr);
    }
  }
}

TEST_CASE("gamma: the schema-valid compile-rejected fixtures name their rule", "[validate][gamma]") {
  struct Case {
    const char* name;
    Want want;
  };
  const Case cases[] = {
      {"gamma-carrier-rule-200hz-60hz.json",
       {"/gamma_pac/carrier_hz", "200", "carrier_rule", ">= 240 Hz (4 x 60 Hz, row carrier-rule)"}},
      {"gamma-carrier-wave-triangle.json", {"/gamma_pac/carrier_wave", "triangle", kNonSine, "sine"}},
      {"gamma-carrier-wave-softened-square.json",
       {"/gamma_pac/carrier_wave", "softened_square", kNonSine, "sine"}},
  };
  for (const auto& c : cases) {
    const std::string text = api::valid(c.name);
    for (const arc_mode mode : kModes) {
      INFO(c.name << ", mode " << mode);
      const api::Compiled r = api::compile(text, api::options(mode, 48000));
      INFO(api::describe(r.error));
      CHECK(r.status == ARC_ERR_REJECTED);
      CHECK(r.plan == nullptr);
      REQUIRE(api::all_written(r.error));
      CHECK(std::string(r.error.parameter) == c.want.parameter);
      CHECK(std::string(r.error.value) == c.want.value);
      CHECK(std::string(r.error.rule) == c.want.rule);
      CHECK(std::string(r.error.limit) == c.want.limit);
    }
  }
}

TEST_CASE("gamma: carrier wave and coupling text outside the schema enum is a schema fault",
          "[validate][gamma]") {
  for (const char* text : {"square", "Sine", "softened-square", ""}) {
    Values v = with_gamma();
    v.gamma_carrier_wave = std::string("\"") + text + "\"";
    expect_rejected(v, {"/gamma_pac/carrier_wave", text, "enum", "sine, triangle, softened_square"});
  }
  for (const char* text : {"swell", "smooth_swell", "bursts", "Uncoupled", ""}) {
    Values v = with_gamma();
    v.gamma_coupling = std::string("\"") + text + "\"";
    expect_rejected(v, {"/gamma_pac/coupling", text, "enum", "uncoupled"});
  }
  for (const bool wave : {true, false}) {
    Values v = with_gamma();
    (wave ? v.gamma_carrier_wave : v.gamma_coupling) = "3";
    const api::Compiled c = api::compile(make_recipe(v), api::options(ARC_MODE_MEASURE, 48000));
    REQUIRE(api::all_written(c.error));
    CHECK(c.status == ARC_ERR_REJECTED);
    CHECK(std::string(c.error.parameter) ==
          (wave ? "/gamma_pac/carrier_wave" : "/gamma_pac/coupling"));
    CHECK(std::string(c.error.rule) == "type");
    CHECK(std::string(c.error.limit) == "string");
  }
}

TEST_CASE("gamma: every gamma field is required", "[validate][gamma]") {
  struct Case {
    void (*drop)(Values&);
    const char* parameter;
  };
  const Case cases[] = {
      {[](Values& v) { v.gamma_carrier_hz.clear(); }, "/gamma_pac/carrier_hz"},
      {[](Values& v) { v.gamma_rate_hz.clear(); }, "/gamma_pac/rate_hz"},
      {[](Values& v) { v.gamma_am_depth_percent.clear(); }, "/gamma_pac/am_depth_percent"},
      {[](Values& v) { v.gamma_carrier_wave.clear(); }, "/gamma_pac/carrier_wave"},
      {[](Values& v) { v.gamma_coupling.clear(); }, "/gamma_pac/coupling"},
  };
  for (const auto& c : cases) {
    Values v = with_gamma();
    c.drop(v);
    const api::Compiled r = api::compile(make_recipe(v), api::options(ARC_MODE_MEASURE, 48000));
    INFO(c.parameter << ": " << api::describe(r.error));
    REQUIRE(api::all_written(r.error));
    CHECK(r.status == ARC_ERR_REJECTED);
    CHECK(std::string(r.error.parameter) == c.parameter);
    CHECK(std::string(r.error.rule) == "required");
  }
}

TEST_CASE("gamma: check order, ranges in field table order then the rules",
          "[validate][gamma][order]") {
  {
    Values v = with_gamma();  // carrier before rate before depth inside gamma_pac
    v.gamma_carrier_hz = "150";
    v.gamma_rate_hz = "70";
    v.gamma_am_depth_percent = "101";
    expect_rejected(v, {"/gamma_pac/carrier_hz", "150", "range.min", ">= 200 Hz (row gamma-carrier)"});
  }
  {
    Values v = with_gamma();
    v.gamma_rate_hz = "70";
    v.gamma_am_depth_percent = "101";
    expect_rejected(v, {"/gamma_pac/rate_hz", "70", "range.max", "<= 60 Hz (row gamma-rate)"});
  }
  {
    Values v = with_gamma();  // theta ranges come before gamma ranges
    v.theta_carrier_hz = "50";
    v.gamma_carrier_hz = "150";
    expect_rejected(v, {"/theta_reference/carrier_hz", "50", "range.min",
                        ">= 100 Hz (row theta-carrier)"});
  }
  {
    Values v = with_gamma();  // gamma ranges come before binaural ranges
    v.gamma_carrier_hz = "150";
    v.carrier_left_hz = "1000";
    expect_rejected(v, {"/gamma_pac/carrier_hz", "150", "range.min", ">= 200 Hz (row gamma-carrier)"});
  }
  {
    Values v = with_gamma();  // a range fault wins over the gamma carrier rule
    v.gamma_carrier_hz = "200";
    v.gamma_rate_hz = "60";
    v.gamma_am_depth_percent = "101";
    expect_rejected(v, {"/gamma_pac/am_depth_percent", "101", "range.max",
                        "<= 100 percent (row coupling-depth)"});
  }
  {
    Values v = with_gamma();  // a range fault wins over the carrier wave rule
    v.gamma_am_depth_percent = "101";
    v.gamma_carrier_wave = "\"triangle\"";
    expect_rejected(v, {"/gamma_pac/am_depth_percent", "101", "range.max",
                        "<= 100 percent (row coupling-depth)"});
  }
  {
    Values v = with_gamma();  // a binaural range fault wins over both gamma rules
    v.gamma_carrier_hz = "200";
    v.gamma_rate_hz = "60";
    v.gamma_carrier_wave = "\"softened_square\"";
    v.beat_rate_hz = "30";
    expect_rejected(v, {"/binaural/beat_rate_hz", "30", "range.max", "< 30 Hz (row beat-rate)"});
  }
  {
    Values v = with_gamma();  // the theta shape rule wins over the gamma carrier rule
    v.theta_shape = "\"custom\"";
    v.gamma_carrier_hz = "200";
    v.gamma_rate_hz = "60";
    expect_rejected(v, {"/theta_reference/shape", "custom", "shape not modeled in the signal spec",
                        "sine, smoothed_on_off, sawtooth, reverse_saw"});
  }
  {
    Values v = with_gamma();  // the theta shape rule wins over the carrier wave rule
    v.theta_shape = "\"custom\"";
    v.gamma_carrier_wave = "\"triangle\"";
    expect_rejected(v, {"/theta_reference/shape", "custom", "shape not modeled in the signal spec",
                        "sine, smoothed_on_off, sawtooth, reverse_saw"});
  }
  {
    Values v = with_gamma();  // the gamma carrier rule wins over the carrier wave rule
    v.gamma_carrier_hz = "200";
    v.gamma_rate_hz = "60";
    v.gamma_carrier_wave = "\"triangle\"";
    expect_rejected(v, {"/gamma_pac/carrier_hz", "200", "carrier_rule",
                        ">= 240 Hz (4 x 60 Hz, row carrier-rule)"});
  }
  {
    Values v = with_gamma();  // the gamma carrier rule comes before final.required
    v.gain = false;
    v.gamma_carrier_hz = "200";
    v.gamma_rate_hz = "60";
    expect_rejected(v, {"/gamma_pac/carrier_hz", "200", "carrier_rule",
                        ">= 240 Hz (4 x 60 Hz, row carrier-rule)"},
                    {ARC_MODE_FINAL});
  }
  {
    Values v = with_gamma();  // the carrier wave rule comes before final.required
    v.gain = false;
    v.gamma_carrier_wave = "\"softened_square\"";
    expect_rejected(v, {"/gamma_pac/carrier_wave", "softened_square", kNonSine, "sine"},
                    {ARC_MODE_FINAL});
  }
  {
    // In range, sine, and without the gain: final.required, as before.
    Values v = with_gamma();
    v.gain = false;
    const api::Compiled c = api::compile(make_recipe(v), api::options(ARC_MODE_FINAL, 48000));
    REQUIRE(api::all_written(c.error));
    CHECK(c.status == ARC_ERR_REJECTED);
    CHECK(std::string(c.error.rule) == "final.required");
  }
}

TEST_CASE("gamma: the carrier rule names the gamma parameter when checked directly",
          "[validate][gamma]") {
  const auto bad = validate::check_carrier_rule("/gamma_pac/carrier_hz", 200.0, 60.0, 60.0);
  REQUIRE(bad.has_value());
  CHECK(bad->parameter == "/gamma_pac/carrier_hz");
  CHECK(bad->value == "200");
  CHECK(bad->rule == "carrier_rule");
  CHECK(bad->limit == ">= 240 Hz (4 x 60 Hz, row carrier-rule)");
  CHECK_FALSE(validate::check_carrier_rule("/gamma_pac/carrier_hz", 240.0, 60.0, 60.0).has_value());
}

// ------------------------------------------------------------ part 3

TEST_CASE("check order: ranges in field table order, first failure wins", "[validate][order]") {
  {
    Values v;  // length before target before theta before binaural
    v.length_s = "-1";
    v.loudness_target_lufs = "-16";
    v.theta_carrier_hz = "50";
    v.carrier_left_hz = "1000";
    v.beat_rate_hz = "30";
    expect_rejected(v, {"/length_s", "-1", "range.min", ">= 0 s (row session-length)"});
  }
  {
    Values v;
    v.loudness_target_lufs = "-16";
    v.theta_carrier_hz = "50";
    v.carrier_left_hz = "1000";
    expect_rejected(v, {"/loudness_target_lufs", "-16", "range.max",
                        "<= -36 LUFS-I (row loudness-tones)"});
  }
  {
    Values v;
    v.theta_carrier_hz = "50";
    v.carrier_left_hz = "1000";
    expect_rejected(v, {"/theta_reference/carrier_hz", "50", "range.min",
                        ">= 100 Hz (row theta-carrier)"});
  }
  {
    Values v;
    v.carrier_left_hz = "1000";
    v.beat_rate_hz = "30";
    expect_rejected(v, {"/binaural/carrier_left_hz", "1000", "range.max",
                        "< 1000 Hz (row binaural-carrier)"});
  }
}

TEST_CASE("check order: ranges before final.required", "[validate][order]") {
  Values v;
  v.gain = false;
  v.theta_carrier_hz = "50";
  expect_rejected(v, {"/theta_reference/carrier_hz", "50", "range.min",
                      ">= 100 Hz (row theta-carrier)"},
                  {ARC_MODE_FINAL});
  // In range and without the gain: final.required, as in Story 1.2.
  Values ok;
  ok.gain = false;
  const api::Compiled c = api::compile(make_recipe(ok), api::options(ARC_MODE_FINAL, 48000));
  REQUIRE(api::all_written(c.error));
  CHECK(c.status == ARC_ERR_REJECTED);
  CHECK(std::string(c.error.rule) == "final.required");
}

TEST_CASE("check order: sample rate and parse faults come before ranges", "[validate][order]") {
  Values v;
  v.theta_carrier_hz = "50";
  {
    const api::Compiled c = api::compile(make_recipe(v), api::options(ARC_MODE_MEASURE, 32000));
    REQUIRE(api::all_written(c.error));
    CHECK(c.status == ARC_ERR_REJECTED);
    CHECK(std::string(c.error.rule) == "sample_rate");
  }
  {
    std::string text = make_recipe(v);
    const auto at = text.find("\"seed\": 42");
    REQUIRE(at != std::string::npos);
    text.replace(at, 10, "\"seed\": \"42\"");
    const api::Compiled c = api::compile(text, api::options(ARC_MODE_MEASURE, 48000));
    REQUIRE(api::all_written(c.error));
    CHECK(c.status == ARC_ERR_REJECTED);
    CHECK(std::string(c.error.parameter) == "/seed");
    CHECK(std::string(c.error.rule) == "type");
  }
}

#else

TEST_CASE("validator, range table, and carrier rule are implemented", "[validate]") {
  FAIL("not implemented: validate/validate.hpp (Story 1.3)");
}

#endif
