// Stored loudness gain, command-line tooling (Story 4.2; docs/signal-spec.md,
// Loudness gain: Gain rounding, File rewrite). No render: the gain step on
// chosen window readings, the gain text, the member scanner, and the file
// rewrite, each against the vectors, plus the final-mode compile of every
// rewritten text through the public C API.
//
// Contracts (spec Implementation Notes, cli/recipe_write.{hpp,cpp} in
// arcani_cli_core, namespace arcani::cli, no engine/src include):
//   struct Member { std::string name; std::size_t lead_begin, key_begin, key_end, value_begin, value_end; };
//     byte offsets into the text; name unescaped. Here: the lead is
//     [lead_begin, key_begin), the key token (quotes included) is
//     [key_begin, key_end), and the value token is [value_begin, value_end).
//   std::vector<Member> top_level_members(std::string_view accepted_json);
//     throws std::invalid_argument unless the text is one JSON object
//   std::optional<double> top_level_number(std::string_view accepted_json, std::string_view name);
//   std::string rewrite_loudness_members(std::string_view accepted_json, std::string_view gain_text,
//                                        std::string_view loudness_hash);
//     throws std::invalid_argument without loudness_target_lufs
//   std::string gain_text(std::int64_t k);                       // "-35.27", "0.00"
//   struct GainStep { bool stored; std::int64_t k; std::string gain_text, value, rule, limit; };
//     k 0 and texts empty when not applicable: here k is the rounded step
//     whenever x is finite (stored or rejected; 0 for a silent window),
//     gain_text is empty on a rejection, and value, rule, limit are empty
//     when stored.
//   GainStep gain_step(double window_lufs, double target_lufs, const arcani::test::tables::Row& gain_row);
//     throws TableError unless a ranges row in dB with finite bounds; its
//     limits come from the row's min_text and max_text.
//
// Vectors come from the generated spec_tables.hpp (kLoudnessGain_*,
// kLoudnessGainSteps, kLoudnessGainValues, kLoudnessRewrites,
// kLoudnessHashes); row loudness-gain from the tables through the assertion
// call. Must-fails are made here: a tie rounded toward zero, a doctored
// output byte, doctored rows.
//
// Until cli/recipe_write.hpp exists the file compiles to one failing test
// case, so the rest of the suite still runs.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#if __has_include("recipe_write.hpp")

#include "api_helpers.hpp"
#include "loudness_gain_helpers.hpp"
#include "recipe_write.hpp"
#include "spec_helpers.hpp"
#include "tables.hpp"

#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace api = arcani::test::api;
namespace cli = arcani::cli;
namespace lg = arcani::test::loudness;
namespace spec = arcani::test::spec;
namespace tables = arcani::test::tables;

namespace {

const tables::Row& gain_row() {
  const tables::Row& r = tables::row(spec::kLoudnessGain_row);
  REQUIRE(r.kind == "ranges");
  REQUIRE(r.unit == "dB");
  return r;
}

std::string limit_min(const tables::Row& r) { return ">= " + r.min_text + " " + r.unit + " (row " + r.id + ")"; }
std::string limit_max(const tables::Row& r) { return "<= " + r.max_text + " " + r.unit + " (row " + r.id + ")"; }

// Rounding the wrong way: x to the integer nearest it, a tie toward zero.
std::int64_t round_tie_toward_zero(double x) {
  const double t = std::trunc(x);
  const double f = x - t;
  if (std::fabs(f) > 0.5) {
    return static_cast<std::int64_t>(t + (x < 0 ? -1.0 : 1.0));
  }
  return static_cast<std::int64_t>(t);
}

const spec::LoudnessGainStepVector& step_case(std::string_view name) {
  for (const auto& v : spec::kLoudnessGainSteps) {
    if (name == v.name) {
      return v;
    }
  }
  FAIL("no gain step vector " << name);
  return spec::kLoudnessGainSteps[0];
}

const spec::LoudnessRewriteVector& rewrite_case(std::string_view name) {
  for (const auto& v : spec::kLoudnessRewrites) {
    if (name == v.name) {
      return v;
    }
  }
  FAIL("no rewrite vector " << name);
  return spec::kLoudnessRewrites[0];
}

std::string recipe_hash_of(const std::string& text, arc_mode mode, std::uint32_t fs) {
  api::PlanPtr p = api::compile_ok(text, api::options(mode, fs));
  return arc_plan_recipe_hash(p.get());
}

}  // namespace

// ------------------------------------------------------------ rows

TEST_CASE("store gain: row loudness-gain and the vector constants agree", "[store-gain][rows]") {
  const tables::Row& r = gain_row();
  CHECK(r.min == spec::kLoudnessGain_min_db);
  CHECK(r.max == spec::kLoudnessGain_max_db);
  CHECK(r.max_bound == "inclusive");
  CHECK(limit_min(r) == spec::kLoudnessGain_min_limit);
  CHECK(limit_max(r) == spec::kLoudnessGain_max_limit);
  CHECK(static_cast<double>(spec::kLoudnessGain_k_min) ==
        spec::kLoudnessGain_min_db * static_cast<double>(spec::kLoudnessGain_steps_per_db));
  CHECK(static_cast<double>(spec::kLoudnessGain_k_max) ==
        spec::kLoudnessGain_max_db * static_cast<double>(spec::kLoudnessGain_steps_per_db));
  CHECK(api::bits(spec::kLoudnessGain_c) == spec::kLoudnessGain_c_bits);
  // c is the binary64 nearest 10^(1/2000): within half an ulp of the ideal.
  const double ulp = std::nextafter(spec::kLoudnessGain_c, 2.0) - spec::kLoudnessGain_c;
  CHECK(std::fabs(spec::kLoudnessGain_c - spec::kLoudnessGain_c_ideal) <= ulp);
}

// ------------------------------------------------------------ gain step

TEST_CASE("store gain: gain_step gives every gain rounding vector with row loudness-gain", "[store-gain]") {
  const tables::Row& r = gain_row();
  for (const auto& v : spec::kLoudnessGainSteps) {
    INFO("case " << v.name);
    // The vector itself follows the spec steps (harness check).
    CHECK(api::bits(v.target_lufs - v.window_lufs) == api::bits(v.d));
    CHECK(api::bits(100.0 * v.d) == api::bits(v.x));
    if (v.has_k) {
      CHECK(static_cast<std::int64_t>(std::round(v.x)) == v.k);
    } else {
      CHECK(std::isinf(v.x));
    }

    const cli::GainStep s = cli::gain_step(v.window_lufs, v.target_lufs, r);
    CHECK(s.stored == v.stored);
    CHECK(s.k == (v.has_k ? v.k : 0));
    if (v.stored) {
      CHECK(s.gain_text == v.gain_text);
      CHECK(s.gain_text == lg::harness_gain_text(v.k));
      CHECK(s.value.empty());
      CHECK(s.rule.empty());
      CHECK(s.limit.empty());
    } else {
      CHECK(s.gain_text.empty());
      CHECK(std::string(v.parameter) == spec::kLoudnessGain_gain_parameter);
      CHECK(s.value == v.value);
      CHECK(s.rule == v.rule);
      CHECK(s.limit == v.limit);
      CHECK((s.limit == limit_min(r) || s.limit == limit_max(r)));
    }
  }
}

TEST_CASE("store gain: must fail, a tie rounded toward zero gives another k", "[store-gain][mustfail]") {
  int ties = 0;
  for (const auto& v : spec::kLoudnessGainSteps) {
    if (!v.has_k || std::fabs(v.x - std::trunc(v.x)) != 0.5) {
      continue;
    }
    INFO("case " << v.name);
    ++ties;
    CHECK(round_tie_toward_zero(v.x) != v.k);
    CHECK(cli::gain_step(v.window_lufs, v.target_lufs, gain_row()).k == v.k);
  }
  CHECK(ties >= 2);  // the two "tie away from zero" cases
  const auto& below = step_case("tie away from zero, below");
  CHECK(round_tie_toward_zero(below.x) == below.k + 1);
}

TEST_CASE("store gain: gain_step reads its bounds and limits from the row", "[store-gain][mustfail]") {
  const tables::Row& real = gain_row();
  SECTION("a doctored minimum moves the rejection and its limit") {
    tables::Row r = real;
    r.min = -30.0;
    r.min_text = "-30";
    const auto& v = step_case("typical");  // -35.27 dB with the real row
    const cli::GainStep s = cli::gain_step(v.window_lufs, v.target_lufs, r);
    CHECK_FALSE(s.stored);
    CHECK(s.rule == "range.min");
    CHECK(s.limit == ">= -30 dB (row loudness-gain)");
    CHECK(s.value == "-35.27");
  }
  SECTION("a row in LU throws TableError") {
    tables::Row r = real;
    r.unit = "LU";
    CHECK_THROWS_AS(cli::gain_step(-0.73, -36.0, r), tables::TableError);
  }
  SECTION("a thresholds row throws TableError") {
    tables::Row r = real;
    r.kind = "thresholds";
    CHECK_THROWS_AS(cli::gain_step(-0.73, -36.0, r), tables::TableError);
  }
  SECTION("an infinite bound throws TableError") {
    tables::Row r = real;
    r.min = -std::numeric_limits<double>::infinity();
    CHECK_THROWS_AS(cli::gain_step(-0.73, -36.0, r), tables::TableError);
  }
}

// ------------------------------------------------------------ gain text

TEST_CASE("store gain: gain_text writes every two-decimal stored gain vector", "[store-gain]") {
  int rows = 0;
  for (const auto& v : spec::kLoudnessGainValues) {
    INFO("text " << v.text);
    // The vector follows the spec (harness check): the text parses to v,
    // x = 100 * v, k = round(x).
    CHECK(api::bits(std::strtod(v.text, nullptr)) == api::bits(v.v));
    CHECK(api::bits(100.0 * v.v) == api::bits(v.x));
    CHECK(static_cast<std::int64_t>(std::round(v.x)) == v.k);
    if (!v.two_decimals) {
      continue;
    }
    ++rows;
    CHECK(cli::gain_text(v.k) == v.text);
    CHECK(lg::harness_gain_text(v.k) == v.text);
  }
  CHECK(rows >= 10);
  CHECK(cli::gain_text(0) == "0.00");
  CHECK(cli::gain_text(-5) == "-0.05");
  CHECK(cli::gain_text(-6000) == "-60.00");
  CHECK(cli::gain_text(-3527) == "-35.27");
  CHECK(cli::gain_text(spec::kLoudnessGain_rewrite_k) == rewrite_case("pretty, both missing").gain_text);
}

// ------------------------------------------------------------ member scanner

TEST_CASE("store gain: top_level_members finds escaped names, leads, keys, and values", "[store-gain]") {
  const auto& v = rewrite_case("escaped member names");
  const std::string text = v.input;
  const std::vector<cli::Member> m = cli::top_level_members(text);
  const std::vector<std::string> names = {"schema_version", "engine_version", "seed", "author", "date",
                                          "rationale", "length_s", "loudness_target_lufs", "loudness_gain_db",
                                          "theta_reference"};
  REQUIRE(m.size() == names.size());
  for (std::size_t i = 0; i < m.size(); ++i) {
    INFO("member " << i << " " << names[i]);
    CHECK(m[i].name == names[i]);
    REQUIRE(m[i].lead_begin <= m[i].key_begin);
    REQUIRE(m[i].key_begin < m[i].key_end);
    REQUIRE(m[i].key_end <= m[i].value_begin);
    REQUIRE(m[i].value_begin < m[i].value_end);
    REQUIRE(m[i].value_end <= text.size());
    CHECK(text.substr(m[i].lead_begin, m[i].key_begin - m[i].lead_begin) == "\n  ");
    CHECK(text[m[i].key_begin] == '"');
    CHECK(text[m[i].key_end - 1] == '"');
    CHECK(text.substr(m[i].key_end, m[i].value_begin - m[i].key_end) == ": ");
  }
  CHECK(text.substr(m[7].key_begin, m[7].key_end - m[7].key_begin) == "\"loudness\\u005ftarget_lufs\"");
  CHECK(text.substr(m[7].value_begin, m[7].value_end - m[7].value_begin) == "-36");
  CHECK(text.substr(m[8].value_begin, m[8].value_end - m[8].value_begin) == "-1.5");
  CHECK(text.substr(m[9].value_begin, m[9].value_end - m[9].value_begin) ==
        "{\"carrier_hz\": 200, \"rate_hz\": 6, \"am_depth_percent\": 0, \"shape\": \"sine\"}");
  CHECK(text.substr(m[0].value_begin, m[0].value_end - m[0].value_begin) == "\"1.0\"");

  // Compact and CRLF texts: empty leads and tab leads.
  const std::string compact = rewrite_case("compact, both missing").input;
  const std::vector<cli::Member> c = cli::top_level_members(compact);
  REQUIRE(c.size() == 9);
  CHECK(c[0].lead_begin == c[0].key_begin);
  CHECK(c[7].name == "loudness_target_lufs");
  const std::string crlf = rewrite_case("CRLF and tabs, both missing").input;
  const std::vector<cli::Member> t = cli::top_level_members(crlf);
  REQUIRE(t.size() == 9);
  CHECK(crlf.substr(t[3].lead_begin, t[3].key_begin - t[3].lead_begin) == "\r\n\t");
}

TEST_CASE("store gain: top_level_members refuses anything but one JSON object", "[store-gain]") {
  for (const char* bad : {"[1, 2]", "1", "\"x\"", "", "   "}) {
    INFO("text [" << bad << "]");
    CHECK_THROWS_AS(cli::top_level_members(bad), std::invalid_argument);
  }
  CHECK(cli::top_level_members("{}").empty());
  CHECK(cli::top_level_members(" {\"a\": 1} \n").size() == 1);
}

TEST_CASE("store gain: top_level_number reads loudness_target_lufs as -36", "[store-gain]") {
  for (const auto& v : spec::kLoudnessRewrites) {
    INFO("case " << v.name);
    const std::optional<double> t = cli::top_level_number(v.input, "loudness_target_lufs");
    REQUIRE(t.has_value());
    CHECK(api::bits(*t) == api::bits(-36.0));
    CHECK_FALSE(cli::top_level_number(v.input, "no_such_member").has_value());
  }
  // A nested member of the same name is not top level.
  CHECK_FALSE(cli::top_level_number("{\"a\": {\"loudness_target_lufs\": -36}}", "loudness_target_lufs").has_value());
}

// ------------------------------------------------------------ file rewrite

TEST_CASE("store gain: rewrite_loudness_members gives every file rewrite vector, and is its own rewrite",
          "[store-gain]") {
  for (const auto& v : spec::kLoudnessRewrites) {
    INFO("case " << v.name);
    const std::string out = cli::rewrite_loudness_members(v.input, v.gain_text, v.loudness_hash);
    CHECK(out == v.output);
    CHECK(cli::rewrite_loudness_members(out, v.gain_text, v.loudness_hash) == out);
    // Must fail: the output with one byte changed differs.
    std::string doctored = v.output;
    const auto at = doctored.find("-35.27");
    REQUIRE(at != std::string::npos);
    doctored[at + 5] = '8';
    CHECK(doctored != out);
  }
}

TEST_CASE("store gain: every rewritten text compiles in final mode with the input's hashes", "[store-gain]") {
  REQUIRE(lg::kHaveLoudnessHash);  // arc_plan_loudness_hash (arcani/arcani.h)
  for (const auto& v : spec::kLoudnessRewrites) {
    INFO("case " << v.name);
    const std::string input = v.input;
    const std::string output = v.output;
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO("fs " << fs);
      api::PlanPtr in = api::compile_ok(input, api::options(ARC_MODE_MEASURE, fs));
      CHECK(lg::plan_loudness_hash(in.get()) == v.loudness_hash);
      api::PlanPtr out = api::compile_ok(output, api::options(ARC_MODE_FINAL, fs));
      CHECK(lg::plan_loudness_hash(out.get()) == v.loudness_hash);
      CHECK(std::string(arc_plan_recipe_hash(out.get())) == arc_plan_recipe_hash(in.get()));
      CHECK(recipe_hash_of(output, ARC_MODE_MEASURE, fs) == recipe_hash_of(input, ARC_MODE_MEASURE, fs));
    }
  }
}

TEST_CASE("store gain: rewrite_loudness_members refuses a text without loudness_target_lufs", "[store-gain]") {
  CHECK_THROWS_AS(cli::rewrite_loudness_members("{\"length_s\": 600}", "-35.27", spec::kLoudnessHashes[0].loudness_hash),
                  std::invalid_argument);
  CHECK_THROWS_AS(cli::rewrite_loudness_members("[1]", "-35.27", spec::kLoudnessHashes[0].loudness_hash),
                  std::invalid_argument);
}

#else

TEST_CASE("store gain: cli/recipe_write.hpp exists (Story 4.2)", "[store-gain]") {
  FAIL("not implemented: cli/recipe_write.hpp (gain_step, gain_text, top_level_members, top_level_number, "
       "rewrite_loudness_members) is missing (Story 4.2)");
}

#endif
