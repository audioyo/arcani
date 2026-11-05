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
  std::string carrier_left_hz = "400";
  std::string beat_rate_hz = "6";
  bool theta = true;
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
    s += ",\n  \"theta_reference\": {\n    \"carrier_hz\": " + v.theta_carrier_hz + "\n  }";
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
  REQUIRE(expected_ids.size() == 6);
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
  const std::set<std::string> expected_rejected = {"both-layers-loudness-target-changed.json"};
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
