// The JSON report, the render speed rule, and the plan getters (Story 1.4).
//
// Contract with cli/ (internal header, reached through the PUBLIC include
// directory of the static library arcani_cli_core, which is cli/ itself;
// arcani_cli_core links arcani::engine and arcani::test_tables):
//
//   // cli/report.hpp
//   #include "tables.hpp"   // arcani::test::tables::Row
//   namespace arcani::cli {
//   enum class Result { pass, fail, not_applicable };
//   struct Assertion {
//     std::string name;                // "render speed"
//     std::string row;                 // table row id, "render-speed"
//     double threshold = 0.0;          // the row's value
//     std::string unit;                // the row's unit
//     std::optional<double> measured;  // empty: written as null
//     Result result = Result::not_applicable;
//     std::string note;                // empty unless not_applicable
//   };
//   struct DeterminismKey {
//     std::string recipe_hash;                // 64 lowercase hex digits
//     std::vector<std::string> asset_hashes;  // empty in v0.1
//     std::string engine_version;
//     std::uint32_t sample_rate = 0;
//   };
//   struct Report {
//     std::string engine_version;
//     std::uint64_t seed = 0;
//     std::uint32_t sample_rate = 0;
//     std::string mode;  // "measure" or "final"
//     std::uint64_t frames = 0;
//     DeterminismKey determinism_key;
//     std::vector<Assertion> assertions;
//   };
//   // A JSON string literal, quotes included: escapes " and \ as \" and \\,
//   // U+0008, U+0009, U+000A, U+000C, U+000D as \b \t \n \f \r, every other
//   // byte below 0x20 as \u00xx (lowercase hex); every other byte as is
//   // (UTF-8 passes through, / and 0x7F are not escaped).
//   std::string json_string(std::string_view utf8);
//   // Shortest round-trip text of a finite double: exactly what
//   // std::to_chars(first, last, x) writes.
//   std::string json_number(double x);
//   // The report as one UTF-8 JSON object, members in the order of the
//   // structs above; whitespace is free. seed, sample_rate, and frames are
//   // written as plain decimal integers; threshold and measured through
//   // json_number; result as "pass", "fail", or "not_applicable".
//   std::string report_json(const Report& report);
//   // True only when the value of ARCANI_REFERENCE_MACHINE (nullptr when
//   // unset) is exactly "1".
//   bool is_reference_machine(const char* env_value) noexcept;
//   // The summed arc_render time in seconds; a total of 0 ticks counts as 1.
//   double elapsed_seconds(std::chrono::steady_clock::duration total) noexcept;
//   // The render speed assertion. name "render speed", row row.id,
//   // threshold row.value(), unit row.unit. frames == 0: not_applicable,
//   // note "no frames" (checked first). Else !is_reference: not_applicable,
//   // note "not the reference machine". Else measured =
//   // (static_cast<double>(frames) / rate) / elapsed_s, pass when
//   // measured >= threshold, else fail. measured is empty when
//   // not_applicable.
//   Assertion render_speed(const arcani::test::tables::Row& row, std::uint64_t frames,
//                          std::uint32_t rate, double elapsed_s, bool is_reference);
//   // 4 when any assertion failed, else 0 (pass and not_applicable only).
//   int assertions_exit_code(const std::vector<Assertion>& assertions) noexcept;
//   }
//
// Plan getters (public C API, engine/include/arcani/arcani.h):
//   const char* arc_plan_recipe_hash(const arc_plan*);  // 64 hex, "" for NULL
//   uint64_t arc_plan_seed(const arc_plan*);            // 0 for NULL
// They are detected with a concept, so the suite builds before they exist.
//
// The render-speed row is read through the assertion call tables::row, so
// its use is recorded for the coverage check.

#include <arcani/arcani.h>

#include "cli_helpers.hpp"
#include "json/value.hpp"
#include "tables.hpp"

#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <concepts>
#include <cstring>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

#ifndef ARCANI_TEST_DATA_DIR
#error "ARCANI_TEST_DATA_DIR must name tests/data"
#endif

namespace h = arcani::test::cli;
namespace json = arcani::json;
namespace tables = arcani::test::tables;

namespace {

json::Value parse_ok(const std::string& text) {
  json::ParseResult r = json::parse(text);
  INFO("JSON: " << text);
  INFO("parse fault " << r.error.rule << " at " << r.error.offset);
  REQUIRE(r.value.has_value());
  return *r.value;
}

const char* const kGoodReport = R"({
  "engine_version": "0.0.1",
  "seed": 42,
  "sample_rate": 48000,
  "mode": "measure",
  "frames": 48000,
  "determinism_key": {
    "recipe_hash": "779404f01db97e80f86e776b2803e468629ff28710ef3d5ae542f4ca049e6868",
    "asset_hashes": [],
    "engine_version": "0.0.1",
    "sample_rate": 48000
  },
  "assertions": [
    {"name": "render speed", "row": "render-speed", "threshold": 20, "unit": "times real time",
     "measured": null, "result": "not_applicable", "note": "not the reference machine"},
    {"name": "render speed", "row": "render-speed", "threshold": 20, "unit": "times real time",
     "measured": 31.5, "result": "pass", "note": ""}
  ]
})";

std::string replaced(const std::string& text, const std::string& from, const std::string& to) {
  const auto at = text.find(from);
  REQUIRE(at != std::string::npos);
  std::string out = text;
  out.replace(at, from.size(), to);
  return out;
}

}  // namespace

// ------------------------------------------------------------ harness

TEST_CASE("report check: a spec report passes, doctored reports fail", "[report][mustfail]") {
  const std::string good = kGoodReport;
  CHECK(h::report_problems(parse_ok(good)).empty());
  const std::pair<const char*, const char*> doctors[] = {
      {R"("seed": 42,)", R"("seed": "42",)"},
      {R"("seed": 42,)", R"("seed": -1,)"},
      {R"("seed": 42,)", R"("seed": 4.5,)"},
      {R"("mode": "measure",)", R"("mode": "loud",)"},
      {R"("frames": 48000,)", ""},
      {R"("mode": "measure",
  "frames": 48000,)", R"("frames": 48000,
  "mode": "measure",)"},
      {R"("asset_hashes": [],)", R"("asset_hashes": {},)"},
      {R"("asset_hashes": [],)", R"("asset_hashes": [1],)"},
      {R"("recipe_hash": "779404f0)", R"("recipe_hash": "779404F0)"},
      {R"(e6868",)", R"(e68",)"},
      {R"("engine_version": "0.0.1",
    "sample_rate")", R"("engine_version": "0.0.2",
    "sample_rate")"},
      {R"("sample_rate": 48000
  })", R"("sample_rate": 44100
  })"},
      {R"("measured": null, "result": "not_applicable")", R"("measured": 3, "result": "not_applicable")"},
      {R"("note": "not the reference machine")", R"("note": "")"},
      {R"("measured": 31.5, "result": "pass", "note": "")", R"("measured": null, "result": "pass", "note": "")"},
      {R"("measured": 31.5, "result": "pass", "note": "")", R"("measured": "31.5", "result": "pass", "note": "")"},
      {R"("result": "pass", "note": "")", R"("result": "ok", "note": "")"},
      {R"("result": "pass", "note": "")", R"("result": "pass", "note": "fast")"},
      {R"("threshold": 20, "unit": "times real time",
     "measured": 31.5)", R"("threshold": "20", "unit": "times real time",
     "measured": 31.5)"},
      {R"(, "note": ""})", R"(, "note": "", "extra": 1})"},
      {R"("assertions": [)", R"("extra": 1, "assertions": [)"},
  };
  for (const auto& [from, to] : doctors) {
    const std::string bad = replaced(good, from, to);
    INFO("doctored: " << from << " -> " << to);
    CHECK_FALSE(h::report_problems(parse_ok(bad)).empty());
  }
}

#if defined(ARCANI_HAVE_CLI_CORE) && __has_include("report.hpp")

#include "report.hpp"

#include <charconv>
#include <chrono>

namespace cli = arcani::cli;

namespace {

const tables::Row& speed_row() { return tables::row("render-speed"); }

// Token after "key": in a JSON text (no nested search), up to , } ] or space.
std::string raw_member(const std::string& text, const std::string& key) {
  const std::string quoted = "\"" + key + "\"";
  auto at = text.find(quoted);
  REQUIRE(at != std::string::npos);
  at = text.find(':', at + quoted.size());
  REQUIRE(at != std::string::npos);
  ++at;
  while (at < text.size() && (text[at] == ' ' || text[at] == '\n' || text[at] == '\r' ||
                              text[at] == '\t')) {
    ++at;
  }
  auto end = at;
  while (end < text.size() && text[end] != ',' && text[end] != '}' && text[end] != ']' &&
         text[end] != ' ' && text[end] != '\n' && text[end] != '\r' && text[end] != '\t') {
    ++end;
  }
  return text.substr(at, end - at);
}

// RFC 8259 number grammar.
bool json_number_grammar(const std::string& t) {
  std::size_t i = 0;
  auto digit = [&](std::size_t k) { return k < t.size() && t[k] >= '0' && t[k] <= '9'; };
  if (i < t.size() && t[i] == '-') ++i;
  if (!digit(i)) return false;
  if (t[i] == '0') {
    ++i;
  } else {
    while (digit(i)) ++i;
  }
  if (i < t.size() && t[i] == '.') {
    ++i;
    if (!digit(i)) return false;
    while (digit(i)) ++i;
  }
  if (i < t.size() && (t[i] == 'e' || t[i] == 'E')) {
    ++i;
    if (i < t.size() && (t[i] == '+' || t[i] == '-')) ++i;
    if (!digit(i)) return false;
    while (digit(i)) ++i;
  }
  return i == t.size();
}

std::string to_chars_text(double x) {
  char buf[64];
  const auto r = std::to_chars(buf, buf + sizeof buf, x);
  REQUIRE(r.ec == std::errc());
  return std::string(buf, r.ptr);
}

cli::Report sample_report() {
  cli::Report r;
  r.engine_version = "0.0.1";
  r.seed = 9007199254740991ull;  // largest seed the schema allows (2^53 - 1)
  r.sample_rate = 48000;
  r.mode = "final";
  r.frames = 1382400000ull;  // 8 h at 48 kHz
  r.determinism_key.recipe_hash = std::string(64, 'a');
  r.determinism_key.engine_version = r.engine_version;
  r.determinism_key.sample_rate = r.sample_rate;
  cli::Assertion na;
  na.name = "render speed";
  na.row = "render-speed";
  na.threshold = 20.0;
  na.unit = "times real time";
  na.result = cli::Result::not_applicable;
  na.note = "quote \" backslash \\ newline \n control \x01 done";
  cli::Assertion pass = na;
  pass.measured = 0.1 + 0.2;
  pass.result = cli::Result::pass;
  pass.note = "";
  cli::Assertion fail = pass;
  fail.measured = 19.99;
  fail.result = cli::Result::fail;
  r.assertions = {na, pass, fail};
  return r;
}

// An elapsed time E with (frames / rate) / E exactly `target`, for
// frames == rate (so frames / rate is exactly 1).
double elapsed_for(double target) {
  double e = 1.0 / target;
  for (int i = 0; i < 8; ++i) {
    e = std::nextafter(e, 0.0);
  }
  for (int i = 0; i <= 16; ++i, e = std::nextafter(e, 1.0)) {
    if (1.0 / e == target) {
      return e;
    }
  }
  FAIL("no elapsed time within 8 ulps gives the target speed exactly");
  return 0.0;
}

}  // namespace

// ------------------------------------------------------------- JSON text

TEST_CASE("json_string escapes quotes, backslashes, and control bytes only", "[report][cli]") {
  CHECK(cli::json_string("plain") == "\"plain\"");
  CHECK(cli::json_string("") == "\"\"");
  CHECK(cli::json_string("a\"b") == "\"a\\\"b\"");
  CHECK(cli::json_string("a\\b") == "\"a\\\\b\"");
  CHECK(cli::json_string("\b\t\n\f\r") == "\"\\b\\t\\n\\f\\r\"");
  CHECK(cli::json_string(std::string("\x00\x01\x1f", 3)) == "\"\\u0000\\u0001\\u001f\"");
  CHECK(cli::json_string("\x0b") == "\"\\u000b\"");
  CHECK(cli::json_string("a/b\x7f") == "\"a/b\x7f\"");
  CHECK(cli::json_string("\xc3\xa9 \xe2\x82\xac") == "\"\xc3\xa9 \xe2\x82\xac\"");
}

TEST_CASE("json_number writes the shortest round-trip text", "[report][cli]") {
  const double values[] = {20.0, 0.0, -0.0, 0.1, 0.1 + 0.2, 19.99, -2.5, 1e21, 1e-7,
                           5e-324, std::numeric_limits<double>::max(), 1.0 / 3.0,
                           std::nextafter(20.0, 0.0), 1382400000.0, 9007199254740991.0};
  for (double x : values) {
    const std::string t = cli::json_number(x);
    INFO("x = " << to_chars_text(x) << ", text " << t);
    CHECK(t == to_chars_text(x));
    CHECK(json_number_grammar(t));
    const json::Value v = parse_ok("[" + t + "]");
    REQUIRE(v.array().size() == 1);
    const double back = v.array()[0].number();
    CHECK(std::memcmp(&back, &x, sizeof x) == 0);
  }
  CHECK(cli::json_number(20.0) == "20");
  CHECK(cli::json_number(0.1) == "0.1");
}

TEST_CASE("report_json writes every member in order and round-trips the values",
          "[report][cli]") {
  const cli::Report r = sample_report();
  const std::string text = cli::report_json(r);
  const json::Value v = parse_ok(text);
  INFO(text);
  CHECK(h::report_problems(v).empty());
  for (const std::string& p : h::report_problems(v)) {
    UNSCOPED_INFO(p);
  }
  CHECK(v.find("engine_version")->string() == "0.0.1");
  CHECK(raw_member(text, "seed") == "9007199254740991");
  CHECK(raw_member(text, "frames") == "1382400000");
  CHECK(v.find("seed")->number() == 9007199254740991.0);
  CHECK(v.find("sample_rate")->number() == 48000.0);
  CHECK(v.find("mode")->string() == "final");
  const json::Value& key = *v.find("determinism_key");
  CHECK(key.find("recipe_hash")->string() == std::string(64, 'a'));
  CHECK(key.find("asset_hashes")->array().empty());
  CHECK(key.find("engine_version")->string() == "0.0.1");
  CHECK(key.find("sample_rate")->number() == 48000.0);
  const auto& list = v.find("assertions")->array();
  REQUIRE(list.size() == 3);
  CHECK(list[0].find("measured")->kind() == json::Kind::Null);
  CHECK(list[0].find("result")->string() == "not_applicable");
  CHECK(list[0].find("note")->string() == r.assertions[0].note);
  CHECK(list[0].find("threshold")->number() == 20.0);
  CHECK(list[0].find("unit")->string() == "times real time");
  CHECK(list[0].find("name")->string() == "render speed");
  CHECK(list[0].find("row")->string() == "render-speed");
  CHECK(list[1].find("result")->string() == "pass");
  CHECK(list[1].find("measured")->number() == 0.1 + 0.2);
  CHECK(text.find("0.30000000000000004") != std::string::npos);
  CHECK(list[2].find("result")->string() == "fail");
  CHECK(list[2].find("measured")->number() == 19.99);
}

TEST_CASE("report_json with no assertions and asset hashes present", "[report][cli]") {
  cli::Report r = sample_report();
  r.assertions.clear();
  r.determinism_key.asset_hashes = {std::string(64, 'b')};
  const json::Value v = parse_ok(cli::report_json(r));
  CHECK(h::report_problems(v).empty());
  CHECK(v.find("assertions")->array().empty());
  const auto& assets = v.find("determinism_key")->find("asset_hashes")->array();
  REQUIRE(assets.size() == 1);
  CHECK(assets[0].string() == std::string(64, 'b'));
}

// ------------------------------------------------------------ speed rule

TEST_CASE("render speed: the threshold passes and the next double below fails", "[report][cli]") {
  const tables::Row& row = speed_row();
  const double t = row.value();
  REQUIRE(t > 0.0);
  const double at = elapsed_for(t);
  const double below = elapsed_for(std::nextafter(t, 0.0));
  for (std::uint32_t rate : {44100u, 48000u}) {
    INFO("rate " << rate);
    const cli::Assertion pass = cli::render_speed(row, rate, rate, at, true);
    CHECK(pass.name == "render speed");
    CHECK(pass.row == row.id);
    CHECK(pass.threshold == t);
    CHECK(pass.unit == row.unit);
    REQUIRE(pass.measured.has_value());
    CHECK(*pass.measured == t);
    CHECK(pass.result == cli::Result::pass);
    CHECK(pass.note.empty());
    const cli::Assertion fail = cli::render_speed(row, rate, rate, below, true);
    REQUIRE(fail.measured.has_value());
    CHECK(*fail.measured == std::nextafter(t, 0.0));
    CHECK(fail.result == cli::Result::fail);
    CHECK(fail.note.empty());
  }
}

TEST_CASE("render speed: measured is (frames / rate) / elapsed", "[report][cli]") {
  const tables::Row& row = speed_row();
  const std::uint64_t frames = 1382400000ull;
  const std::uint32_t rate = 48000;
  const double elapsed = 1234.5678;
  const cli::Assertion a = cli::render_speed(row, frames, rate, elapsed, true);
  REQUIRE(a.measured.has_value());
  CHECK(*a.measured == (static_cast<double>(frames) / rate) / elapsed);
  CHECK(a.result == (*a.measured >= row.value() ? cli::Result::pass : cli::Result::fail));
  // 44.1 kHz, 3 s of audio in 0.1 s.
  const cli::Assertion b = cli::render_speed(row, 3 * 44100, 44100, 0.1, true);
  REQUIRE(b.measured.has_value());
  CHECK(*b.measured == (static_cast<double>(3 * 44100) / 44100) / 0.1);
}

TEST_CASE("render speed: not the reference machine is not applicable", "[report][cli]") {
  const tables::Row& row = speed_row();
  const cli::Assertion a = cli::render_speed(row, 48000, 48000, 1e-6, false);
  CHECK(a.result == cli::Result::not_applicable);
  CHECK_FALSE(a.measured.has_value());
  CHECK(a.note == "not the reference machine");
  CHECK(a.row == row.id);
  CHECK(a.threshold == row.value());
  CHECK(a.unit == row.unit);
  CHECK(a.name == "render speed");
}

TEST_CASE("render speed: 0 frames is not applicable, with or without the reference machine",
          "[report][cli]") {
  const tables::Row& row = speed_row();
  for (bool reference : {true, false}) {
    const cli::Assertion a = cli::render_speed(row, 0, 48000, 1e-9, reference);
    CHECK(a.result == cli::Result::not_applicable);
    CHECK_FALSE(a.measured.has_value());
    CHECK(a.note == "no frames");
  }
}

TEST_CASE("reference machine: only the exact value 1", "[report][cli]") {
  CHECK(cli::is_reference_machine("1"));
  CHECK_FALSE(cli::is_reference_machine(nullptr));
  for (const char* v : {"", "0", "true", "yes", "1 ", " 1", "01", "11", "2"}) {
    INFO("value [" << v << "]");
    CHECK_FALSE(cli::is_reference_machine(v));
  }
}

TEST_CASE("elapsed time: 0 ticks counts as 1 tick", "[report][cli]") {
  using clock = std::chrono::steady_clock;
  const double tick = std::chrono::duration<double>(clock::duration(1)).count();
  REQUIRE(tick > 0.0);
  CHECK(cli::elapsed_seconds(clock::duration::zero()) == tick);
  CHECK(cli::elapsed_seconds(clock::duration(1)) == tick);
  CHECK(cli::elapsed_seconds(std::chrono::duration_cast<clock::duration>(std::chrono::seconds(2))) ==
        2.0);
}

TEST_CASE("exit code: 4 when any assertion fails, else 0", "[report][cli]") {
  const tables::Row& row = speed_row();
  const cli::Assertion na = cli::render_speed(row, 48000, 48000, 1.0, false);
  const cli::Assertion zero = cli::render_speed(row, 0, 48000, 1.0, true);
  const cli::Assertion pass = cli::render_speed(row, 48000, 48000, elapsed_for(row.value()), true);
  // Matrix row "Speed, reference": measured 19.99 against 20 fails, exit 4.
  const cli::Assertion slow = cli::render_speed(row, 48000, 48000, elapsed_for(19.99), true);
  REQUIRE(slow.measured.has_value());
  CHECK(*slow.measured == 19.99);
  CHECK(slow.result == (19.99 >= row.value() ? cli::Result::pass : cli::Result::fail));
  CHECK(cli::assertions_exit_code({}) == 0);
  CHECK(cli::assertions_exit_code({na}) == 0);
  CHECK(cli::assertions_exit_code({zero}) == 0);
  CHECK(cli::assertions_exit_code({pass}) == 0);
  CHECK(cli::assertions_exit_code({pass, na, zero}) == 0);
  if (slow.result == cli::Result::fail) {
    CHECK(cli::assertions_exit_code({slow}) == 4);
    CHECK(cli::assertions_exit_code({pass, slow, na}) == 4);
  }
  cli::Assertion forced = pass;
  forced.result = cli::Result::fail;
  CHECK(cli::assertions_exit_code({na, forced}) == 4);
}

#else

TEST_CASE("not implemented: cli/report.hpp (arcani_cli_core)", "[report][cli]") {
  FAIL("arcani_cli_core with cli/report.hpp (report_json, render_speed, ...) does not exist yet");
}

#endif

// ------------------------------------------------------------ plan getters

#ifdef ARC_ERROR_FIELD_BYTES

#include "api_helpers.hpp"

namespace {

template <class P>
concept HasPlanGetters = requires(const P* p) {
  { arc_plan_recipe_hash(p) } -> std::same_as<const char*>;
  { arc_plan_seed(p) } -> std::same_as<std::uint64_t>;
};

std::string read_text(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  INFO(path);
  REQUIRE(in.good());
  std::stringstream ss;
  ss << in.rdbuf();
  return ss.str();
}

template <class P>
void check_plan_getters() {
  namespace api = arcani::test::api;
  if constexpr (HasPlanGetters<P>) {
    const P* none = nullptr;
    REQUIRE(arc_plan_recipe_hash(none) != nullptr);
    CHECK(std::string(arc_plan_recipe_hash(none)).empty());
    CHECK(arc_plan_seed(none) == 0);
    const json::Value vectors =
        parse_ok(read_text(std::string(ARCANI_TEST_DATA_DIR) + "/recipe_hash_vectors.json"));
    int compiled = 0;
    for (const auto& [name, hash] : vectors.object()) {
      INFO(name);
      const std::string text = api::valid(name);
      const json::Value recipe = parse_ok(text);
      const json::Value* seed = recipe.find("seed");
      REQUIRE(seed != nullptr);
      REQUIRE(seed->integral());
      REQUIRE(seed->number() >= 0.0);
      REQUIRE(seed->number() <= 9007199254740991.0);
      api::Compiled c = api::compile(text, api::options(ARC_MODE_MEASURE, 48000));
      if (c.status != ARC_OK) {
        continue;  // a valid fixture outside the locked ranges (Story 1.3)
      }
      ++compiled;
      const P* plan = c.plan.get();  // dependent, so the calls resolve only when P is known
      const char* got = arc_plan_recipe_hash(plan);
      REQUIRE(got != nullptr);
      CHECK(std::string(got) == hash.string());
      CHECK(h::is_lower_hex(got, 64));
      CHECK(arc_plan_seed(plan) == static_cast<std::uint64_t>(seed->number()));
      CHECK(arc_plan_recipe_hash(plan) == got);  // the same string while the plan lives
    }
    CHECK(compiled >= 20);
  } else {
    FAIL("not implemented: arc_plan_recipe_hash and arc_plan_seed in arcani/arcani.h");
  }
}

}  // namespace

TEST_CASE("plan getters return the recipe hash and the seed", "[report][api]") {
  check_plan_getters<arc_plan>();
}

#endif
