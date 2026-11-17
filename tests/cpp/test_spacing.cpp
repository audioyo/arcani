// Spacing rule per ear, whole session (Story 3.2; docs/signal-spec.md,
// Spacing).
//
// Compile reads the component table (Story 3.1) and checks, in each ear,
// every row of one layer against every row of another layer by the closed
// form max(0, |c| - H) over a whole rate cycle, never sampling the session.
// A pair passes when its minimum distance is at least row spacing-rule
// (exactly 50 Hz passes). A failure returns no plan and the error
//   parameter  the carrier field of row 2's layer (/gamma_pac/carrier_hz or
//              /binaural/carrier_left_hz)
//   value      the minimum distance, shortest round-trip text
//   rule       spacing_rule
//   limit      ">= 50 Hz (row spacing-rule)"
//   detail     "<ear> ear: <layer 1> (<i>, <j>, <b>) at <c1> Hz and <layer 2>
//              (<i>, <j>, <b>) at <c2> Hz; <where>"
// the smallest failing distance of both ears, ties to the left ear, then the
// smaller index of row 1, then of row 2. Every other rule leaves detail
// empty.
//
// Contracts (spec Implementation Notes):
//   arc_error gains char detail[ARC_ERROR_DETAIL_BYTES] after limit, with
//   #define ARC_ERROR_DETAIL_BYTES 512; recipe::Error gains std::string detail.
//   typedef struct arc_spacing { int32_t has_pair; double min_distance_hz;
//     double margin_hz; size_t component_1; size_t component_2; } arc_spacing;
//   arc_status arc_plan_spacing(const arc_plan* plan, arc_ear ear,
//                               arc_spacing* out_spacing, arc_error* error);
//   NULL plan: parameter "plan"; NULL out_spacing: parameter "out_spacing"
//   (value "null", rule "argument.null", limit "non-null"); an ear other
//   than ARC_EAR_LEFT and ARC_EAR_RIGHT: parameter "ear", value the integer,
//   rule "argument.enum", limit "0 (left) 1 (right)". The result is the same
//   at both sample rates and honors mute_binaural_ear.
//   engine/src/validate/spacing.hpp (namespace arcani::validate):
//   kSpacingRule, kSpacingRuleHz, SpacingPair {min_distance_hz, margin_hz,
//   component_1, component_2}, SpacingResult {ears, error},
//   check_spacing(recipe, table), SpacingPairInput, SpacingPairForm
//   {x, y, h, min_distance_hz, sweeps, first_units}, spacing_pair_form(in),
//   acos_units(v). validate::Component gains bool mirrored; plan::Plan gains
//   std::array<std::optional<validate::SpacingPair>, 2> spacing.
//
// Vectors come from the generated spec_tables.hpp (kSpacingCases,
// kSpacingMargins, kSpacingPairs, kSpacing_*); the rows spacing-rule,
// spacing-time-error, component-frequency-error, frequency-accuracy, and
// rate-cycle-period from the tables through the assertion call. No threshold
// is written here as a literal. Must-fail cases are made here by doctoring a
// component table, a recipe text, or a detail text.
//
// Until engine/src/validate/spacing.hpp and the C API declarations exist the
// file compiles to one failing test case, so the rest of the suite still
// runs.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#if defined(ARC_ERROR_DETAIL_BYTES) && __has_include("validate/spacing.hpp") && \
    __has_include("plan/plan.hpp") && __has_include("recipe/recipe.hpp")

#include "api_helpers.hpp"
#include "core/rate_cycle.hpp"
#include "json/value.hpp"
#include "plan/plan.hpp"
#include "recipe/recipe.hpp"
#include "spacing_helpers.hpp"
#include "spec_helpers.hpp"
#include "tables.hpp"
#include "validate/components.hpp"
#include "validate/spacing.hpp"

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <iterator>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>

namespace api = arcani::test::api;
namespace json = arcani::json;
namespace plan = arcani::plan;
namespace recipe = arcani::recipe;
namespace sp = arcani::test::spacing;
namespace spec = arcani::test::spec;
namespace validate = arcani::validate;

namespace {

// ------------------------------------------------------------ rows

double rule_hz() {
  const spec::Row& r = spec::row("spacing-rule");
  return spec::unit_to_hz(r.value(), r.unit);
}

sp::Tolerances tolerances() {
  sp::Tolerances t;
  const spec::Row& f = spec::row("component-frequency-error");
  t.frequency_hz = spec::unit_to_hz(f.value(), f.unit);
  const spec::Row& s = spec::row("spacing-time-error");
  t.time_s = spec::unit_to_seconds(s.value(), s.unit);
  t.rate_hz = spec::frequency_accuracy_hz();
  const spec::Row& p = spec::row("rate-cycle-period");
  REQUIRE(p.min == p.max);
  t.period_s = spec::unit_to_seconds(p.min, p.unit);
  return t;
}

// ------------------------------------------------------------ vectors

const spec::SpacingCaseVector& find_case(std::string_view name) {
  for (const auto& c : spec::kSpacingCases) {
    if (name == c.name) {
      return c;
    }
  }
  FAIL("no spacing case " << name);
  return spec::kSpacingCases[0];
}

const spec::SpacingMarginVector& find_margin(std::string_view name, int ear) {
  for (const auto& m : spec::kSpacingMargins) {
    if (name == m.case_name && std::string_view(m.ear) == sp::kEars[ear]) {
      return m;
    }
  }
  FAIL("no spacing margin " << name << " " << sp::kEars[ear]);
  return spec::kSpacingMargins[0];
}

arc_mute_ear api_mute(std::string_view mute) {
  if (mute == "left") {
    return ARC_MUTE_LEFT;
  }
  if (mute == "right") {
    return ARC_MUTE_RIGHT;
  }
  REQUIRE(mute == "none");
  return ARC_MUTE_NONE;
}

validate::MutedEar engine_mute(std::string_view mute) {
  return mute == "left" ? validate::MutedEar::Left : mute == "right" ? validate::MutedEar::Right
                                                                     : validate::MutedEar::None;
}

plan::MuteEar plan_mute(std::string_view mute) {
  return mute == "left" ? plan::MuteEar::Left : mute == "right" ? plan::MuteEar::Right : plan::MuteEar::None;
}

// The recipe text with loudness_gain_db and loudness_hash added, so final
// mode compiles it.
std::string with_gain(const std::string& text) {
  const auto at = text.find('{');
  REQUIRE(at != std::string::npos);
  return text.substr(0, at + 1) +
         "\"loudness_gain_db\": -1.5, "
         "\"loudness_hash\": \"6a29ccd608e4c1945bfff95af078a97daea48eca54a38e065ae33dfa9c2d83a6\", " +
         text.substr(at + 1);
}

// The recipe text with its length_s replaced.
std::string with_length(const std::string& text, const std::string& length) {
  const std::string key = "\"length_s\":";
  auto at = text.find(key);
  REQUIRE(at != std::string::npos);
  at += key.size();
  auto end = text.find_first_of(",}", at);
  REQUIRE(end != std::string::npos);
  return text.substr(0, at) + length + text.substr(end);
}

// One member text replaced once.
std::string replaced(const std::string& text, const std::string& from, const std::string& to) {
  const auto at = text.find(from);
  INFO("replace '" << from << "' in " << text);
  REQUIRE(at != std::string::npos);
  REQUIRE(text.find(from, at + 1) == std::string::npos);
  std::string out = text;
  out.replace(at, from.size(), to);
  return out;
}

recipe::Recipe parsed(const std::string& text) {
  recipe::ParseResult r = recipe::parse(text);
  INFO(text << "\n" << r.error.parameter << " " << r.error.rule);
  REQUIRE(r.recipe.has_value());
  return *r.recipe;
}

std::vector<validate::Component> table_of(const std::string& text, std::string_view mute = "none") {
  validate::ComponentResult r = validate::build_components(parsed(text), engine_mute(mute));
  REQUIRE_FALSE(r.error.has_value());
  return r.components;
}

// The carrier field of a row 2 layer, or nothing for a layer that is never row 2 (theta_reference,
// or a doctored text), so the caller records a problem instead of aborting.
std::optional<std::string> carrier_field(const std::string& layer) {
  if (layer == "gamma_pac") {
    return std::string(spec::kSpacing_carrier_field_gamma_pac);
  }
  if (layer == "binaural") {
    return std::string(spec::kSpacing_carrier_field_binaural);
  }
  return std::nullopt;
}

std::string row_name(const arc_component& c) {
  const int layer = static_cast<int>(c.layer);
  REQUIRE(layer >= 0);
  REQUIRE(layer < 3);
  return std::string(sp::kLayers[layer]) + " (" + std::to_string(c.gamma_mult) + ", " +
         std::to_string(c.theta_mult) + ", " + std::to_string(c.beat_mult) + ")";
}

std::string row_name(const validate::Component& c) {
  const int layer = static_cast<int>(c.layer);
  REQUIRE(layer >= 0);
  REQUIRE(layer < 3);
  return std::string(sp::kLayers[layer]) + " (" + std::to_string(c.gamma_mult) + ", " +
         std::to_string(c.theta_mult) + ", " + std::to_string(c.beat_mult) + ")";
}

// ------------------------------------------------------------ the error

struct WantError {
  std::string parameter;
  double value_hz = 0.0;
  bool value_exact = false;  // the ideal value is a binary64: the text is its shortest text
  std::string detail;        // ideal numbers
};

WantError want_error(const spec::SpacingCaseVector& c) {
  REQUIRE(c.rejected);
  WantError w;
  w.parameter = c.parameter;
  w.value_hz = c.value_hz;
  w.detail = c.detail;
  sp::Detail d;
  REQUIRE(sp::parse_detail(w.detail, d, false).empty());
  // Every static pair (and every distance of 0) has a binary64 ideal value.
  w.value_exact = d.where.kind != "first" || c.value_hz == 0.0;
  return w;
}

// Problems of one spacing error (the five fields as texts) against the case.
std::vector<std::string> error_problems(const std::string& parameter, const std::string& value,
                                        const std::string& rule, const std::string& limit,
                                        const std::string& detail, const WantError& want) {
  const sp::Tolerances tol = tolerances();
  std::vector<std::string> problems;
  if (parameter != want.parameter) {
    problems.push_back("parameter " + parameter + ", want " + want.parameter);
  }
  if (rule != spec::kSpacing_rule) {
    problems.push_back("rule " + rule + ", want " + spec::kSpacing_rule);
  }
  if (limit != spec::kSpacing_limit) {
    problems.push_back("limit " + limit + ", want " + spec::kSpacing_limit);
  }
  if (!sp::is_shortest(value)) {
    problems.push_back("value '" + value + "' is not a shortest round-trip text");
  } else if (!(std::fabs(sp::number(value) - want.value_hz) < tol.frequency_hz)) {
    problems.push_back("value " + value + ", want " + sp::shortest(want.value_hz));
  } else if (want.value_exact && value != sp::shortest(want.value_hz)) {
    problems.push_back("value " + value + ", want exactly " + sp::shortest(want.value_hz));
  }
  for (const std::string& p : sp::compare_detail(detail, want.detail, tol)) {
    problems.push_back("detail: " + p);
  }
  // The parameter is the carrier field of row 2's layer.
  sp::Detail d;
  if (sp::parse_detail(detail, d, true).empty()) {
    const std::optional<std::string> field = carrier_field(d.pair.row_2.layer);
    if (!field.has_value()) {
      problems.push_back("row 2's layer " + d.pair.row_2.layer + " has no carrier field");
    } else if (parameter != *field) {
      problems.push_back("parameter " + parameter + " is not the carrier field of row 2's layer " +
                         d.pair.row_2.layer);
    }
  }
  return problems;
}

std::vector<std::string> api_error_problems(const arc_error& e, const WantError& want) {
  if (!api::all_written(e) || !api::written(e.detail)) {
    return {"error fields not all written"};
  }
  return error_problems(e.parameter, e.value, e.rule, e.limit, e.detail, want);
}

std::vector<std::string> engine_error_problems(const recipe::Error& e, const WantError& want) {
  return error_problems(e.parameter, e.value, e.rule, e.limit, e.detail, want);
}

// ------------------------------------------------------------ margins

struct Margin {
  bool has_pair = false;
  double min_distance_hz = 0.0;
  double margin_hz = 0.0;
  std::size_t component_1 = 0;
  std::size_t component_2 = 0;
};

Margin api_margin(const arc_plan* p, arc_ear ear) {
  arc_spacing s;
  std::memset(&s, 0xA5, sizeof s);
  arc_error e;
  api::poison(e);
  const arc_status status = arc_plan_spacing(p, ear, &s, &e);
  INFO("ear " << static_cast<int>(ear) << ": " << api::describe(e));
  REQUIRE(status == ARC_OK);
  REQUIRE((s.has_pair == 0 || s.has_pair == 1));
  Margin m;
  m.has_pair = s.has_pair == 1;
  m.min_distance_hz = s.min_distance_hz;
  m.margin_hz = s.margin_hz;
  m.component_1 = s.component_1;
  m.component_2 = s.component_2;
  if (!m.has_pair) {
    // Every other field 0.
    CHECK(api::bits(s.min_distance_hz) == 0);
    CHECK(api::bits(s.margin_hz) == 0);
    CHECK(s.component_1 == 0);
    CHECK(s.component_2 == 0);
  }
  return m;
}

Margin engine_margin(const std::optional<validate::SpacingPair>& p) {
  Margin m;
  if (p) {
    m.has_pair = true;
    m.min_distance_hz = p->min_distance_hz;
    m.margin_hz = p->margin_hz;
    m.component_1 = p->component_1;
    m.component_2 = p->component_2;
  }
  return m;
}

// Problems of one ear's margin against the margin vector. `names` gives a
// row's layer and multipliers by table index.
template <class Names>
std::vector<std::string> margin_problems(const Margin& m, const spec::SpacingMarginVector& v, Names names) {
  const double ftol = tolerances().frequency_hz;
  std::vector<std::string> problems;
  if (m.has_pair != v.has_pair) {
    problems.push_back(std::string("has_pair ") + (m.has_pair ? "1" : "0") + ", want " + (v.has_pair ? "1" : "0"));
    return problems;
  }
  if (!v.has_pair) {
    return problems;
  }
  if (!(std::fabs(m.min_distance_hz - v.distance_hz) < ftol)) {
    problems.push_back("min distance " + sp::shortest(m.min_distance_hz) + ", want " + sp::shortest(v.distance_hz));
  }
  if (!(std::fabs(m.margin_hz - v.margin_hz) < ftol)) {
    problems.push_back("margin " + sp::shortest(m.margin_hz) + ", want " + sp::shortest(v.margin_hz));
  }
  // The margin is one binary64 subtraction of the row value.
  if (api::bits(m.margin_hz) != api::bits(m.min_distance_hz - rule_hz())) {
    problems.push_back("margin " + sp::shortest(m.margin_hz) + " is not min distance less row spacing-rule");
  }
  if (m.component_1 != v.index_1 || m.component_2 != v.index_2) {
    problems.push_back("components " + std::to_string(m.component_1) + ", " + std::to_string(m.component_2) +
                       ", want " + std::to_string(v.index_1) + ", " + std::to_string(v.index_2));
  } else {
    if (names(m.component_1) != v.row_1) {
      problems.push_back("row 1 is " + names(m.component_1) + ", want " + v.row_1);
    }
    if (names(m.component_2) != v.row_2) {
      problems.push_back("row 2 is " + names(m.component_2) + ", want " + v.row_2);
    }
  }
  if (!(m.component_1 < m.component_2)) {
    problems.push_back("component_1 is not the smaller index");
  }
  return problems;
}

std::string api_row_name(const arc_plan* p, std::size_t index) {
  arc_component c;
  arc_error e;
  api::poison(e);
  if (arc_plan_component(p, index, &c, &e) != ARC_OK) {
    return "(no row " + std::to_string(index) + ")";
  }
  return row_name(c);
}

void check_plan_margins(const arc_plan* p, const spec::SpacingCaseVector& c) {
  for (int ear = 0; ear < 2; ++ear) {
    INFO("case " << c.name << ", ear " << sp::kEars[ear]);
    const Margin m = api_margin(p, ear == 0 ? ARC_EAR_LEFT : ARC_EAR_RIGHT);
    const auto problems =
        margin_problems(m, find_margin(c.name, ear), [p](std::size_t i) { return api_row_name(p, i); });
    INFO(sp::joined(problems));
    CHECK(problems.empty());
    if (m.has_pair) {
      CHECK(m.margin_hz >= 0.0);  // 0 or more in a plan that compiled
    }
  }
}

bool same_margin_bits(const Margin& a, const Margin& b) {
  return a.has_pair == b.has_pair && api::bits(a.min_distance_hz) == api::bits(b.min_distance_hz) &&
         api::bits(a.margin_hz) == api::bits(b.margin_hz) && a.component_1 == b.component_1 &&
         a.component_2 == b.component_2;
}

// A recipe made here with all three layers and no rate cycle, so every row
// of a doctored table is static. Parsed only, never compiled.
const std::string kStaticLayers =
    "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, \"author\": \"Arcani test\", "
    "\"date\": \"2026-11-16\", \"rationale\": \"Spacing test, made in the test.\", \"length_s\": 10, "
    "\"loudness_target_lufs\": -36, "
    "\"theta_reference\": {\"carrier_hz\": 450, \"rate_hz\": 6, \"am_depth_percent\": 75, \"shape\": \"sine\"}, "
    "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": 40, \"am_depth_percent\": 100, \"carrier_wave\": \"sine\", "
    "\"coupling\": \"uncoupled\"}, "
    "\"binaural\": {\"carrier_left_hz\": 100, \"beat_rate_hz\": 6}}";

// A component row made here, for doctored tables.
validate::Component line(validate::ComponentLayer layer, validate::Ear ear, double center_hz, int g = 0, int t = 0,
                         int b = 0) {
  validate::Component c{};
  c.layer = layer;
  c.ear = ear;
  c.center_hz = center_hz;
  c.low_hz = center_hz;
  c.high_hz = center_hz;
  c.level = 1.0;
  c.gamma_mult = g;
  c.theta_mult = t;
  c.beat_mult = b;
  c.mirrored = false;
  return c;
}

void require_null_argument(arc_status s, const arc_error& e, const char* parameter) {
  INFO(api::describe(e));
  CHECK(s == ARC_ERR_INVALID_ARGUMENT);
  REQUIRE(api::all_written(e));
  REQUIRE(api::written(e.detail));
  CHECK(std::string(e.parameter) == parameter);
  CHECK(std::string(e.value) == "null");
  CHECK(std::string(e.rule) == "argument.null");
  CHECK(std::string(e.limit) == "non-null");
  CHECK(std::string(e.detail).empty());
}

}  // namespace

// ------------------------------------------------------------ constants and types

TEST_CASE("spacing: the engine constants equal the vectors and rows spacing-rule and spacing-time-error",
          "[spacing]") {
  CHECK(validate::kSpacingRule == std::string_view(spec::kSpacing_rule));
  CHECK(validate::kSpacingRule == "spacing_rule");
  CHECK(validate::kSpacingRuleHz == rule_hz());
  CHECK(spec::kSpacing_rule_hz == rule_hz());
  CHECK(spec::kSpacing_time_error_s == tolerances().time_s);
  // The limit names the row value as its shortest text.
  CHECK(std::string(spec::kSpacing_limit) == ">= " + sp::shortest(rule_hz()) + " Hz (row spacing-rule)");
  CHECK(std::string(spec::kSpacing_whole_session) == sp::kWholeSession);
  CHECK(std::string(spec::kSpacing_listed_intervals) == sp::kListedIntervals);
  CHECK(std::size(spec::kSpacing_fixtures) == 5);
  CHECK(std::size(spec::kSpacing_starter_fixtures) == 4);
  CHECK(std::string(spec::kSpacing_must_fail_fixture) == "spacing-binaural-250-256-gamma-260.json");
}

TEST_CASE("spacing: the C API, error, plan, and component types hold the contract", "[spacing][api]") {
  CHECK(ARC_ERROR_DETAIL_BYTES == 512);
  CHECK(sizeof(arc_error::detail) == ARC_ERROR_DETAIL_BYTES);
  CHECK(offsetof(arc_error, detail) == offsetof(arc_error, limit) + sizeof(arc_error::limit));
  CHECK(std::is_same_v<decltype(arc_spacing::has_pair), std::int32_t>);
  CHECK(std::is_same_v<decltype(arc_spacing::min_distance_hz), double>);
  CHECK(std::is_same_v<decltype(arc_spacing::margin_hz), double>);
  CHECK(std::is_same_v<decltype(arc_spacing::component_1), std::size_t>);
  CHECK(std::is_same_v<decltype(arc_spacing::component_2), std::size_t>);
  CHECK(std::is_same_v<decltype(&arc_plan_spacing), arc_status (*)(const arc_plan*, arc_ear, arc_spacing*, arc_error*)>);
  CHECK(std::is_same_v<decltype(recipe::Error::detail), std::string>);
  CHECK(std::is_same_v<decltype(validate::Component::mirrored), bool>);
  CHECK(std::is_same_v<decltype(plan::Plan::spacing), std::array<std::optional<validate::SpacingPair>, 2>>);
  CHECK(std::is_same_v<decltype(validate::SpacingResult::ears), std::array<std::optional<validate::SpacingPair>, 2>>);
  CHECK(std::is_same_v<decltype(validate::SpacingResult::error), std::optional<recipe::Error>>);
  CHECK(std::is_same_v<decltype(&validate::check_spacing),
                       validate::SpacingResult (*)(const recipe::Recipe&, std::span<const validate::Component>)>);
  CHECK(std::is_same_v<decltype(&validate::spacing_pair_form),
                       validate::SpacingPairForm (*)(const validate::SpacingPairInput&)>);
  CHECK(std::is_same_v<decltype(&validate::acos_units), std::uint64_t (*)(double)>);
}

// ------------------------------------------------------------ every case through compile

TEST_CASE("spacing: every case compiles or is rejected as the vectors say, at both rates and in both modes",
          "[spacing][vectors]") {
  REQUIRE(std::size(spec::kSpacingCases) > 0);
  int rejected = 0;
  for (const auto& c : spec::kSpacingCases) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO("case " << c.name << ", fs " << fs << ", mute " << c.mute);
      const std::string text = c.recipe;
      if (c.rejected) {
        const WantError want = want_error(c);
        // Final mode without a stored gain: the spacing rule runs before final.required.
        for (const arc_mode mode : {ARC_MODE_MEASURE, ARC_MODE_FINAL}) {
          INFO("mode " << mode);
          const api::Compiled r = api::compile(text, api::options(mode, fs, api_mute(c.mute)));
          CHECK(r.status == ARC_ERR_REJECTED);
          CHECK(r.plan == nullptr);
          const auto problems = api_error_problems(r.error, want);
          INFO(api::describe(r.error) << "\ndetail '" << (api::written(r.error.detail) ? r.error.detail : "?")
                                      << "'\n" << sp::joined(problems));
          CHECK(problems.empty());
        }
      } else {
        auto p = api::compile_ok(text, api::options(ARC_MODE_MEASURE, fs, api_mute(c.mute)));
        check_plan_margins(p.get(), c);
        auto f = api::compile_ok(with_gain(text), api::options(ARC_MODE_FINAL, fs, api_mute(c.mute)));
        check_plan_margins(f.get(), c);
      }
    }
    rejected += c.rejected ? 1 : 0;
  }
  CHECK(rejected > 0);
}

TEST_CASE("spacing: every fixture case compiled from its fixture file agrees with the vectors", "[spacing][vectors]") {
  int fixtures = 0;
  for (const auto& c : spec::kSpacingCases) {
    if (std::string_view(c.fixture) == "none") {
      continue;
    }
    ++fixtures;
    const std::string text = api::valid(c.fixture);
    const std::uint32_t fs = spec::sample_rates().back();
    INFO("case " << c.name << ", fixture " << c.fixture << ", mute " << c.mute);
    if (c.rejected) {
      const api::Compiled r = api::compile(text, api::options(ARC_MODE_MEASURE, fs, api_mute(c.mute)));
      CHECK(r.status == ARC_ERR_REJECTED);
      const auto problems = api_error_problems(r.error, want_error(c));
      INFO(api::describe(r.error) << "\n" << sp::joined(problems));
      CHECK(problems.empty());
    } else {
      auto p = api::compile_ok(text, api::options(ARC_MODE_MEASURE, fs, api_mute(c.mute)));
      check_plan_margins(p.get(), c);
    }
  }
  CHECK(fixtures > static_cast<int>(std::size(spec::kSpacing_fixtures)));
}

TEST_CASE("spacing: the margins are the same bits at both sample rates", "[spacing][vectors]") {
  const std::vector<std::uint32_t> rates = spec::sample_rates();
  REQUIRE(rates.size() >= 2);
  for (const auto& c : spec::kSpacingCases) {
    if (c.rejected) {
      continue;
    }
    INFO("case " << c.name);
    auto first = api::compile_ok(c.recipe, api::options(ARC_MODE_MEASURE, rates[0], api_mute(c.mute)));
    for (std::size_t k = 1; k < rates.size(); ++k) {
      auto other = api::compile_ok(c.recipe, api::options(ARC_MODE_MEASURE, rates[k], api_mute(c.mute)));
      for (const arc_ear ear : {ARC_EAR_LEFT, ARC_EAR_RIGHT}) {
        CHECK(same_margin_bits(api_margin(first.get(), ear), api_margin(other.get(), ear)));
      }
    }
  }
}

TEST_CASE("spacing: plan::compile gives the same error and Plan::spacing as the C API", "[spacing]") {
  for (const auto& c : spec::kSpacingCases) {
    INFO("case " << c.name);
    const std::uint32_t fs = spec::sample_rates()[0];
    plan::CompileResult r = plan::compile(c.recipe, plan::Mode::Measure, fs, plan_mute(c.mute));
    const api::Compiled a = api::compile(c.recipe, api::options(ARC_MODE_MEASURE, fs, api_mute(c.mute)));
    if (c.rejected) {
      REQUIRE_FALSE(r.plan.has_value());
      const auto problems = engine_error_problems(r.error, want_error(c));
      INFO(sp::joined(problems));
      CHECK(problems.empty());
      REQUIRE(api::written(a.error.detail));
      CHECK(r.error.detail == a.error.detail);
      CHECK(r.error.value == a.error.value);
    } else {
      REQUIRE(r.plan.has_value());
      REQUIRE(a.plan != nullptr);
      for (int ear = 0; ear < 2; ++ear) {
        CHECK(same_margin_bits(engine_margin(r.plan->spacing[static_cast<std::size_t>(ear)]),
                               api_margin(a.plan.get(), ear == 0 ? ARC_EAR_LEFT : ARC_EAR_RIGHT)));
      }
    }
  }
}

// ------------------------------------------------------------ check_spacing on the table

TEST_CASE("spacing: check_spacing gives every case's margins and error, rejected cases included",
          "[spacing][vectors]") {
  for (const auto& c : spec::kSpacingCases) {
    INFO("case " << c.name << ", mute " << c.mute);
    const recipe::Recipe r = parsed(c.recipe);
    const std::vector<validate::Component> table = table_of(c.recipe, c.mute);
    REQUIRE(table.size() == c.components);
    const validate::SpacingResult result = validate::check_spacing(r, table);
    for (int ear = 0; ear < 2; ++ear) {
      INFO("ear " << sp::kEars[ear]);
      const auto problems = margin_problems(engine_margin(result.ears[static_cast<std::size_t>(ear)]),
                                            find_margin(c.name, ear), [&table](std::size_t i) {
                                              return i < table.size() ? row_name(table[i]) : std::string("(none)");
                                            });
      INFO(sp::joined(problems));
      CHECK(problems.empty());
    }
    CHECK(result.error.has_value() == c.rejected);
    if (c.rejected && result.error) {
      const auto problems = engine_error_problems(*result.error, want_error(c));
      INFO(sp::joined(problems));
      CHECK(problems.empty());
    }
  }
}

TEST_CASE("spacing: the margin vectors pair each case and ear with the case's pair count", "[spacing][vectors]") {
  CHECK(std::size(spec::kSpacingMargins) == 2 * std::size(spec::kSpacingCases));
  for (const auto& c : spec::kSpacingCases) {
    for (int ear = 0; ear < 2; ++ear) {
      const auto& m = find_margin(c.name, ear);
      CHECK(m.has_pair == (m.pairs > 0));
    }
  }
}

// ------------------------------------------------------------ the closed form alone

TEST_CASE("spacing: spacing_pair_form reproduces every pair vector within the rows", "[spacing][vectors]") {
  const sp::Tolerances tol = tolerances();
  REQUIRE(std::size(spec::kSpacingPairs) > 0);
  for (const auto& v : spec::kSpacingPairs) {
    INFO("pair " << v.label);
    validate::SpacingPairInput in{};
    in.c_hz = v.c_hz;
    in.di = v.di;
    in.dj = v.dj;
    in.db = v.db;
    in.swing_gamma_hz = v.swing_gamma_hz;
    in.start_gamma_deg = v.start_gamma_deg;
    in.swing_theta_hz = v.swing_theta_hz;
    in.start_theta_deg = v.start_theta_deg;
    in.swing_beat_hz = v.swing_beat_hz;
    in.start_beat_deg = v.start_beat_deg;
    const validate::SpacingPairForm f = validate::spacing_pair_form(in);
    CHECK(std::fabs(f.x - v.x) < tol.frequency_hz);
    CHECK(std::fabs(f.y - v.y) < tol.frequency_hz);
    CHECK(std::fabs(f.h - v.h) < tol.frequency_hz);
    CHECK(std::fabs(f.min_distance_hz - v.distance_hz) < tol.frequency_hz);
    CHECK(f.min_distance_hz >= 0.0);
    CHECK(f.sweeps == v.has_first);
    if (v.has_first && f.sweeps) {
      const double fraction = static_cast<double>(f.first_units) * 0x1p-64;
      INFO("first fraction " << sp::shortest(fraction) << ", want " << sp::shortest(v.first));
      CHECK(sp::around_cycle(fraction * tol.period_s, v.first * tol.period_s, tol.period_s) < tol.time_s);
    }
  }
}

TEST_CASE("spacing: acos_units is the smallest phase in [0, 2^63] whose cycle cosine is at most v", "[spacing]") {
  const double values[] = {1.0, 0.999999, 0.5, 0.1, 0.0, -0.0, -0.3, -0.5, -0.999999, -1.0, 1.5, -1.5};
  for (const double v : values) {
    INFO("v " << sp::shortest(v));
    const std::uint64_t x = validate::acos_units(v);
    CHECK(x <= (std::uint64_t{1} << 63));
    if (arcani::core::cycle_cosine(0) <= v) {
      CHECK(x == 0);
      continue;
    }
    if (x < (std::uint64_t{1} << 63)) {
      CHECK(arcani::core::cycle_cosine(x) <= v);
    }
    CHECK(x > 0);
    CHECK(arcani::core::cycle_cosine(x - 1) > v);
  }
  // Must-fail twin of the check above: a phase one step either side is caught.
  const std::uint64_t half = validate::acos_units(0.5);
  CHECK_FALSE(arcani::core::cycle_cosine((half + 1) - 1) > 0.5);  // half + 1: its predecessor is already <= v
  CHECK_FALSE(arcani::core::cycle_cosine(half - 1) <= 0.5);       // half - 1: its own cosine is still > v
}

// ------------------------------------------------------------ matrix rows

TEST_CASE("spacing: must-fail fixture, rejected in the right ear at 4 Hz, whole session", "[spacing][matrix]") {
  const auto& c = find_case("spacing-binaural-250-256-gamma-260");
  CHECK(std::string(c.fixture) == spec::kSpacing_must_fail_fixture);
  REQUIRE(c.rejected);
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const api::Compiled r = api::compile(api::valid(spec::kSpacing_must_fail_fixture), api::options(ARC_MODE_MEASURE, fs));
    REQUIRE(r.status == ARC_ERR_REJECTED);
    REQUIRE(api::written(r.error.detail));
    CHECK(std::string(r.error.parameter) == "/binaural/carrier_left_hz");
    CHECK(std::string(r.error.value) == "4");
    CHECK(std::string(r.error.rule) == "spacing_rule");
    CHECK(std::string(r.error.limit) == spec::kSpacing_limit);
    CHECK(std::string(r.error.detail) ==
          "right ear: gamma_pac (-1, 0, 0) at 260 Hz and binaural (0, 0, 1) at 256 Hz; whole session");
  }
}

TEST_CASE("spacing: a muted ear has no binaural pair; the must-fail fixture then fails in the other ear",
          "[spacing][matrix][mute]") {
  const std::string text = api::valid(spec::kSpacing_must_fail_fixture);
  const std::uint32_t fs = spec::sample_rates()[0];
  {
    // Right ear muted: the left ear's 260 Hz gamma line is 10 Hz from the 250 Hz binaural carrier.
    const api::Compiled r = api::compile(text, api::options(ARC_MODE_MEASURE, fs, ARC_MUTE_RIGHT));
    REQUIRE(r.status == ARC_ERR_REJECTED);
    REQUIRE(api::written(r.error.detail));
    CHECK(std::string(r.error.value) == "10");
    CHECK(std::string(r.error.detail) ==
          "left ear: gamma_pac (-1, 0, 0) at 260 Hz and binaural (0, 0, 0) at 250 Hz; whole session");
  }
  {
    const api::Compiled r = api::compile(text, api::options(ARC_MODE_MEASURE, fs, ARC_MUTE_LEFT));
    REQUIRE(r.status == ARC_ERR_REJECTED);
    REQUIRE(api::written(r.error.detail));
    CHECK(std::string(r.error.value) == "4");
    CHECK(std::string(r.error.detail).rfind("right ear: ", 0) == 0);
  }
  // Theta and binaural with one ear muted: that ear has one layer, so no pair.
  const std::string sleep = api::valid("starter-sleep-layers.json");
  for (const auto& [mute, quiet] : {std::pair{ARC_MUTE_LEFT, ARC_EAR_LEFT}, std::pair{ARC_MUTE_RIGHT, ARC_EAR_RIGHT}}) {
    auto p = api::compile_ok(sleep, api::options(ARC_MODE_MEASURE, fs, mute));
    CHECK_FALSE(api_margin(p.get(), quiet).has_pair);
    CHECK(api_margin(p.get(), quiet == ARC_EAR_LEFT ? ARC_EAR_RIGHT : ARC_EAR_LEFT).has_pair);
  }
}

TEST_CASE("spacing: exactly 50 Hz passes with margin 0; 49.99 Hz is rejected", "[spacing][matrix]") {
  const auto& exact = find_case("spacing-exactly-50hz");
  CHECK_FALSE(exact.rejected);
  for (const std::uint32_t fs : spec::sample_rates()) {
    auto p = api::compile_ok(exact.recipe, api::options(ARC_MODE_MEASURE, fs));
    for (const arc_ear ear : {ARC_EAR_LEFT, ARC_EAR_RIGHT}) {
      const Margin m = api_margin(p.get(), ear);
      REQUIRE(m.has_pair);
      CHECK(m.min_distance_hz == rule_hz());
      CHECK(api::bits(m.margin_hz) == 0);  // +0.0
    }
  }
  const auto& below = find_case("spacing-49.99hz");
  REQUIRE(below.rejected);
  const api::Compiled r = api::compile(below.recipe, api::options(ARC_MODE_MEASURE, spec::sample_rates()[0]));
  CHECK(r.status == ARC_ERR_REJECTED);
  REQUIRE(api::all_written(r.error));
  CHECK(std::string(r.error.value) == sp::shortest(450.0 - 400.01));
  // Must-pass twin made here: the exact case's binaural carrier at 400.01 Hz is rejected the same way.
  const api::Compiled moved = api::compile(replaced(exact.recipe, "\"carrier_left_hz\":400,", "\"carrier_left_hz\":400.01,"),
                                           api::options(ARC_MODE_MEASURE, spec::sample_rates()[0]));
  CHECK(moved.status == ARC_ERR_REJECTED);
  REQUIRE(api::all_written(moved.error));
  CHECK(std::string(moved.error.value) == std::string(r.error.value));
}

TEST_CASE("spacing: a row moved 1e-9 Hz across the limit fails; moved away it passes", "[spacing][matrix][must-fail]") {
  const auto& c = find_case("spacing-exactly-50hz");
  const recipe::Recipe r = parsed(c.recipe);
  const std::vector<validate::Component> table = table_of(c.recipe);
  REQUIRE(table.size() == 4);
  {
    const validate::SpacingResult ok = validate::check_spacing(r, table);
    CHECK_FALSE(ok.error.has_value());
    REQUIRE(ok.ears[0].has_value());
    CHECK(ok.ears[0]->margin_hz == 0.0);
  }
  // The left binaural row (index 1, 400 Hz) moved up toward the 450 Hz theta row.
  std::vector<validate::Component> closer = table;
  REQUIRE(closer[1].layer == validate::ComponentLayer::Binaural);
  for (double* f : {&closer[1].center_hz, &closer[1].low_hz, &closer[1].high_hz}) {
    *f += 1e-9;
  }
  const validate::SpacingResult bad = validate::check_spacing(r, closer);
  REQUIRE(bad.error.has_value());
  CHECK(bad.error->rule == "spacing_rule");
  CHECK(bad.error->parameter == "/binaural/carrier_left_hz");
  CHECK(bad.error->detail.rfind("left ear: theta_reference (0, 0, 0) at 450 Hz and binaural (0, 0, 0) at ", 0) == 0);
  CHECK(sp::number(bad.error->value) < rule_hz());
  REQUIRE(bad.ears[0].has_value());
  CHECK(bad.ears[0]->margin_hz < 0.0);
  // Moved away instead: it passes with a margin above 0.
  std::vector<validate::Component> away = table;
  for (double* f : {&away[1].center_hz, &away[1].low_hz, &away[1].high_hz}) {
    *f -= 1e-9;
  }
  const validate::SpacingResult good = validate::check_spacing(r, away);
  CHECK_FALSE(good.error.has_value());
  REQUIRE(good.ears[0].has_value());
  CHECK(good.ears[0]->margin_hz > 0.0);
}

TEST_CASE("spacing: a layer's own rows are never compared, nor the two binaural rows", "[spacing][matrix]") {
  // Gamma lines 2 Hz apart in one ear are one layer: no pair, no failure.
  const recipe::Recipe r = parsed(kStaticLayers);
  using L = validate::ComponentLayer;
  using E = validate::Ear;
  const std::vector<validate::Component> own = {line(L::GammaPac, E::Left, 300.0, -1), line(L::GammaPac, E::Left, 302.0),
                                                line(L::GammaPac, E::Right, 300.0, -1),
                                                line(L::GammaPac, E::Right, 302.0)};
  const validate::SpacingResult a = validate::check_spacing(r, own);
  CHECK_FALSE(a.error.has_value());
  CHECK_FALSE(a.ears[0].has_value());
  CHECK_FALSE(a.ears[1].has_value());
  // The binaural pair 1 Hz apart sits in two ears: no pair.
  const std::vector<validate::Component> pair = {line(L::Binaural, E::Left, 300.0),
                                                 line(L::Binaural, E::Right, 301.0, 0, 0, 1)};
  const validate::SpacingResult b = validate::check_spacing(r, pair);
  CHECK_FALSE(b.error.has_value());
  CHECK_FALSE(b.ears[0].has_value());
  CHECK_FALSE(b.ears[1].has_value());
  // Must-fail twin: the same rows as two layers in one ear fail.
  const std::vector<validate::Component> two = {line(L::GammaPac, E::Left, 300.0), line(L::Binaural, E::Left, 301.0)};
  const validate::SpacingResult c = validate::check_spacing(r, two);
  REQUIRE(c.error.has_value());
  CHECK(c.error->value == "1");
  REQUIRE(c.ears[0].has_value());
  CHECK_FALSE(c.ears[1].has_value());
}

TEST_CASE("spacing: the worst pair is reported; ties go to the left ear, then row 1, then row 2",
          "[spacing][matrix][ties]") {
  const recipe::Recipe r = parsed(kStaticLayers);
  using L = validate::ComponentLayer;
  using E = validate::Ear;
  // Per ear: theta 100 Hz, gamma 140 Hz, binaural 180 Hz. Pairs (0, 1) and
  // (1, 2) are both 40 Hz; (0, 2) is 80 Hz.
  const auto ear_rows = [](E ear, double binaural_hz) {
    return std::vector<validate::Component>{line(L::ThetaReference, ear, 100.0), line(L::GammaPac, ear, 140.0),
                                            line(L::Binaural, ear, binaural_hz, 0, 0, ear == E::Right ? 1 : 0)};
  };
  const auto table = [&](double left_binaural, double right_binaural) {
    std::vector<validate::Component> t = ear_rows(E::Left, left_binaural);
    for (const auto& c : ear_rows(E::Right, right_binaural)) {
      t.push_back(c);
    }
    return t;
  };
  {
    // Every tie: left ear, row 1 index 0, so the pair theta-gamma, parameter of gamma.
    const validate::SpacingResult s = validate::check_spacing(r, table(180.0, 180.0));
    REQUIRE(s.error.has_value());
    CHECK(s.error->parameter == "/gamma_pac/carrier_hz");
    CHECK(s.error->value == "40");
    CHECK(s.error->detail == "left ear: theta_reference (0, 0, 0) at 100 Hz and gamma_pac (0, 0, 0) at 140 Hz; "
                             "whole session");
    REQUIRE(s.ears[0].has_value());
    CHECK(s.ears[0]->component_1 == 0);
    CHECK(s.ears[0]->component_2 == 1);
    REQUIRE(s.ears[1].has_value());
    CHECK(s.ears[1]->component_1 == 3);
    CHECK(s.ears[1]->component_2 == 4);
  }
  {
    // The right ear's gamma-binaural pair 0.5 Hz closer: the smallest distance wins over the left ear.
    const validate::SpacingResult s = validate::check_spacing(r, table(180.0, 179.5));
    REQUIRE(s.error.has_value());
    CHECK(s.error->parameter == "/binaural/carrier_left_hz");
    CHECK(s.error->value == "39.5");
    CHECK(s.error->detail.rfind("right ear: gamma_pac (0, 0, 0) at 140 Hz and binaural (0, 0, 1) at 179.5 Hz", 0) ==
          0);
    REQUIRE(s.ears[1].has_value());
    CHECK(s.ears[1]->component_1 == 4);
    CHECK(s.ears[1]->component_2 == 5);
    // The left ear's margin still ties to the smaller row 1.
    REQUIRE(s.ears[0].has_value());
    CHECK(s.ears[0]->component_1 == 0);
  }
  {
    // Ties within the left ear only: the smaller row 2 for the same row 1.
    // Rows 1 and 2 are both 20 Hz from row 0.
    std::vector<validate::Component> t = {line(L::ThetaReference, E::Left, 100.0),
                                          line(L::GammaPac, E::Left, 80.0, -1), line(L::GammaPac, E::Left, 120.0, 1)};
    const validate::SpacingResult s = validate::check_spacing(r, t);
    REQUIRE(s.ears[0].has_value());
    CHECK(s.ears[0]->component_1 == 0);
    CHECK(s.ears[0]->component_2 == 1);
    REQUIRE(s.error.has_value());
    CHECK(s.error->detail == "left ear: theta_reference (0, 0, 0) at 100 Hz and gamma_pac (-1, 0, 0) at 80 Hz; "
                             "whole session");
  }
}

TEST_CASE("spacing: a rate cycle that comes within 50 Hz only at a turning point is rejected, in closed form",
          "[spacing][matrix][rate-cycle]") {
  const auto& c = find_case("spacing-turning-point");
  REQUIRE(c.rejected);
  const WantError want = want_error(c);
  // The minimum is at 30 s. A session of 1 s ends long before it, and an
  // 8 h session holds it many times: the same error, since the rule judges
  // the whole cycle and never samples the session.
  for (const std::string& length : {std::string("1"), std::string("10"), sp::shortest(spec::session_length_seconds())}) {
    INFO("length " << length);
    const api::Compiled r = api::compile(with_length(c.recipe, length), api::options(ARC_MODE_MEASURE, 48000));
    REQUIRE(r.status == ARC_ERR_REJECTED);
    const auto problems = api_error_problems(r.error, want);
    INFO(api::describe(r.error) << "\n" << sp::joined(problems));
    CHECK(problems.empty());
  }
  // Must-pass twin: the theta carrier 1 Hz higher keeps 50.5 Hz at the turning point.
  auto p = api::compile_ok(replaced(c.recipe, "\"carrier_hz\":154.5", "\"carrier_hz\":155.5"),
                           api::options(ARC_MODE_MEASURE, 48000));
  const Margin m = api_margin(p.get(), ARC_EAR_RIGHT);
  REQUIRE(m.has_pair);
  CHECK(std::fabs(m.min_distance_hz - (rule_hz() + 0.5)) < tolerances().frequency_hz);
}

TEST_CASE("spacing: a gamma rate cycle crossing the binaural carrier gives the first time and the rates there",
          "[spacing][matrix][rate-cycle]") {
  for (const char* name : {"spacing-gamma-cycle-crossing", "spacing-cycles-60deg-apart", "spacing-three-cycles"}) {
    const auto& c = find_case(name);
    INFO("case " << name);
    REQUIRE(c.rejected);
    const api::Compiled r = api::compile(c.recipe, api::options(ARC_MODE_MEASURE, 44100));
    REQUIRE(r.status == ARC_ERR_REJECTED);
    REQUIRE(api::written(r.error.detail));
    sp::Detail d;
    REQUIRE(sp::parse_detail(r.error.detail, d, true).empty());
    CHECK(d.where.kind == "first");
    CHECK(d.where.time_s >= 0.0);
    CHECK(d.where.time_s < tolerances().period_s);
    const auto problems = api_error_problems(r.error, want_error(c));
    INFO(r.error.detail << "\n" << sp::joined(problems));
    CHECK(problems.empty());
  }
}

TEST_CASE("spacing: rows that sweep together are judged by their real distance, not their intervals",
          "[spacing][matrix][sweep-together]") {
  const auto& c = find_case("spacing-sweep-together");
  REQUIRE_FALSE(c.rejected);
  const std::vector<validate::Component> table = table_of(c.recipe);
  // The listed intervals of the worst pair are under 50 Hz apart.
  const auto& m = find_margin(c.name, 0);
  REQUIRE(m.has_pair);
  const validate::Component& a = table.at(m.index_1);
  const validate::Component& b = table.at(m.index_2);
  const double interval_gap = std::fmax(b.low_hz - a.high_hz, a.low_hz - b.high_hz);
  CHECK(interval_gap < rule_hz());
  auto p = api::compile_ok(c.recipe, api::options(ARC_MODE_MEASURE, 48000));
  const Margin got = api_margin(p.get(), ARC_EAR_LEFT);
  REQUIRE(got.has_pair);
  CHECK(got.min_distance_hz >= rule_hz());
  CHECK(std::fabs(got.min_distance_hz - m.distance_hz) < tolerances().frequency_hz);
  // Must-fail twin: the gamma cycle at 0 degrees no longer moves with the
  // theta cycle, so the distance shrinks to the interval gap and fails.
  const std::string apart = replaced(c.recipe, "\"start_phase_deg\":180", "\"start_phase_deg\":0");
  const api::Compiled r = api::compile(apart, api::options(ARC_MODE_MEASURE, 48000));
  CHECK(r.status == ARC_ERR_REJECTED);
  REQUIRE(api::written(r.error.detail));
  CHECK(std::string(r.error.rule) == "spacing_rule");
  CHECK(std::fabs(sp::number(r.error.value) - interval_gap) < tolerances().frequency_hz);
}

// Whether each row of a case's table is flagged mirrored exactly when its
// unmirrored interval reaches below 0 Hz (Components, Frequencies below 0):
// a theta reference row's unmirrored center is carrier + k * rate and its
// half-width |k| * swing; gamma PAC and binaural rows never reach 0 Hz
// inside the locked ranges. Returns the number of mirrored rows.
namespace {

int check_mirrored(const std::string& text, std::string_view mute) {
  const std::vector<validate::Component> table = table_of(text, mute);
  const json::ParseResult doc = json::parse(text);
  REQUIRE(doc.value.has_value());
  const json::Value* theta = doc.value->find("theta_reference");
  double carrier = 0.0;
  double rate = 0.0;
  double swing = 0.0;
  if (theta != nullptr) {
    carrier = theta->find("carrier_hz")->number();
    rate = theta->find("rate_hz")->number();
    if (const json::Value* cycle = theta->find("rate_cycle")) {
      swing = cycle->find("swing_hz")->number();
    }
  }
  int mirrored = 0;
  for (const validate::Component& row : table) {
    INFO(row_name(row) << " at " << sp::shortest(row.center_hz));
    if (row.layer != validate::ComponentLayer::ThetaReference) {
      CHECK_FALSE(row.mirrored);
      continue;
    }
    const double k = row.theta_mult;
    CHECK(row.mirrored == (carrier + k * rate - std::fabs(k) * swing < 0.0));
    mirrored += row.mirrored ? 1 : 0;
  }
  return mirrored;
}

}  // namespace

TEST_CASE("spacing: a row is flagged mirrored exactly when its interval reaches below 0 Hz",
          "[spacing][matrix][mirrored]") {
  CHECK(check_mirrored(find_case("spacing-mirrored-row").recipe, "none") > 0);
  for (const auto& c : spec::kSpacingCases) {
    INFO("case " << c.name);
    check_mirrored(c.recipe, c.mute);
  }
  // The mirrored case is compared by its listed intervals: the where text says so.
  const auto& c = find_case("spacing-mirrored-row");
  REQUIRE(c.rejected);
  const api::Compiled r = api::compile(c.recipe, api::options(ARC_MODE_MEASURE, 48000));
  REQUIRE(r.status == ARC_ERR_REJECTED);
  REQUIRE(api::written(r.error.detail));
  sp::Detail d;
  REQUIRE(sp::parse_detail(r.error.detail, d, true).empty());
  CHECK(d.where.kind == sp::kListedIntervals);
}

TEST_CASE("spacing: one layer compiles with no pair in either ear", "[spacing][matrix]") {
  for (const char* text_name : {"spacing-one-layer"}) {
    auto p = api::compile_ok(find_case(text_name).recipe, api::options(ARC_MODE_MEASURE, 48000));
    CHECK_FALSE(api_margin(p.get(), ARC_EAR_LEFT).has_pair);
    CHECK_FALSE(api_margin(p.get(), ARC_EAR_RIGHT).has_pair);
  }
  for (const char* fixture : {api::kBeat0, api::kNoLayers, "gamma-uncoupled-40hz-25pct.json"}) {
    INFO(fixture);
    auto p = api::compile_ok(api::valid(fixture), api::options(ARC_MODE_MEASURE, 48000));
    CHECK_FALSE(api_margin(p.get(), ARC_EAR_LEFT).has_pair);
    CHECK_FALSE(api_margin(p.get(), ARC_EAR_RIGHT).has_pair);
  }
}

TEST_CASE("spacing: the four starter fixtures and the AD-5 sweep compile with a margin in each ear",
          "[spacing][matrix][starters]") {
  for (const char* fixture : spec::kSpacing_starter_fixtures) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(fixture << ", fs " << fs);
      auto p = api::compile_ok(api::valid(fixture), api::options(ARC_MODE_MEASURE, fs));
      for (const arc_ear ear : {ARC_EAR_LEFT, ARC_EAR_RIGHT}) {
        const Margin m = api_margin(p.get(), ear);
        CHECK(m.has_pair);
        CHECK(m.margin_hz >= 0.0);
      }
    }
  }
  int ad5 = 0;
  for (const auto& c : spec::kSpacingCases) {
    if (std::string_view(c.name).rfind("ad5-", 0) != 0) {
      continue;
    }
    ++ad5;
    INFO(c.name);
    CHECK_FALSE(c.rejected);
    auto p = api::compile_ok(c.recipe, api::options(ARC_MODE_MEASURE, 48000));
    for (const arc_ear ear : {ARC_EAR_LEFT, ARC_EAR_RIGHT}) {
      const Margin m = api_margin(p.get(), ear);
      CHECK(m.has_pair);
      CHECK(m.margin_hz >= 0.0);
    }
  }
  CHECK(ad5 == 14);
}

// ------------------------------------------------------------ the detail field elsewhere

TEST_CASE("spacing: every other rule leaves the detail empty", "[spacing][api][detail]") {
  const std::uint32_t fs = 48000;
  int rejections = 0;
  for (const char* folder : {"valid", "invalid"}) {
    for (const auto& entry :
         std::filesystem::directory_iterator(std::string(ARCANI_RECIPES_DIR) + "/fixtures/" + folder)) {
      if (!entry.is_regular_file() || entry.path().extension() != ".json") {
        continue;
      }
      const std::string name = entry.path().filename().string();
      if (name == spec::kSpacing_must_fail_fixture || name == "invalid-expected.json") {
        continue;
      }
      const api::Compiled c = api::compile(api::fixture(folder, name), api::options(ARC_MODE_MEASURE, fs));
      if (c.status == ARC_OK) {
        continue;
      }
      ++rejections;
      INFO(folder << "/" << name << ": " << api::describe(c.error));
      REQUIRE(api::written(c.error.detail));
      CHECK(std::string(c.error.detail).empty());
      CHECK(std::string(c.error.rule) != "spacing_rule");
    }
  }
  CHECK(rejections > 20);
  // final.required, a bad sample rate, and argument errors.
  {
    const api::Compiled c = api::compile(api::valid(api::kNoGain), api::options(ARC_MODE_FINAL, fs));
    REQUIRE(c.status == ARC_ERR_REJECTED);
    CHECK(std::string(c.error.rule) == "final.required");
    REQUIRE(api::written(c.error.detail));
    CHECK(std::string(c.error.detail).empty());
  }
  {
    const api::Compiled c = api::compile(api::valid(api::kBeat6), api::options(ARC_MODE_MEASURE, 22050));
    REQUIRE(c.status != ARC_OK);
    REQUIRE(api::written(c.error.detail));
    CHECK(std::string(c.error.detail).empty());
  }
  {
    arc_error e;
    api::poison(e);
    arc_plan* out = nullptr;
    const arc_compile_options o = api::options(ARC_MODE_MEASURE, fs);
    require_null_argument(arc_compile(nullptr, 0, &o, &out, &e), e, "utf8");
  }
  {
    auto p = api::compile_ok(api::valid(api::kBeat6), api::options(ARC_MODE_MEASURE, fs));
    arc_error w;
    arc_error e;
    api::poison(e);
    CHECK(arc_plan_warning(p.get(), arc_plan_warning_count(p.get()), &w, &e) == ARC_ERR_INVALID_ARGUMENT);
    REQUIRE(api::written(e.detail));
    CHECK(std::string(e.detail).empty());
    arc_component comp;
    api::poison(e);
    CHECK(arc_plan_component(p.get(), arc_plan_component_count(p.get()), &comp, &e) == ARC_ERR_INVALID_ARGUMENT);
    REQUIRE(api::written(e.detail));
    CHECK(std::string(e.detail).empty());
  }
  // recipe::Error from plan::compile: empty for a range error.
  {
    plan::CompileResult r = plan::compile(replaced(api::valid(api::kBeat6), "\"length_s\": 1,", "\"length_s\": -1,"),
                                          plan::Mode::Measure, fs, plan::MuteEar::None);
    REQUIRE_FALSE(r.plan.has_value());
    CHECK(r.error.parameter == "/length_s");
    CHECK(r.error.detail.empty());
  }
}

// ------------------------------------------------------------ C API arguments

TEST_CASE("spacing: arc_plan_spacing refuses a NULL plan, a NULL output, and an unknown ear", "[spacing][api]") {
  auto p = api::compile_ok(find_case("spacing-exactly-50hz").recipe, api::options(ARC_MODE_MEASURE, 48000));
  arc_spacing s;
  arc_error e;
  api::poison(e);
  require_null_argument(arc_plan_spacing(nullptr, ARC_EAR_LEFT, &s, &e), e, "plan");
  api::poison(e);
  require_null_argument(arc_plan_spacing(p.get(), ARC_EAR_LEFT, nullptr, &e), e, "out_spacing");
  for (const int bad : {2, -1, 7}) {
    api::poison(e);
    CHECK(arc_plan_spacing(p.get(), static_cast<arc_ear>(bad), &s, &e) == ARC_ERR_INVALID_ARGUMENT);
    REQUIRE(api::all_written(e));
    REQUIRE(api::written(e.detail));
    CHECK(std::string(e.parameter) == "ear");
    CHECK(std::string(e.value) == std::to_string(bad));
    CHECK(std::string(e.rule) == "argument.enum");
    CHECK(std::string(e.limit) == "0 (left) 1 (right)");
    CHECK(std::string(e.detail).empty());
  }
  // A NULL error pointer is allowed.
  CHECK(arc_plan_spacing(p.get(), static_cast<arc_ear>(2), &s, nullptr) == ARC_ERR_INVALID_ARGUMENT);
  CHECK(arc_plan_spacing(p.get(), ARC_EAR_RIGHT, &s, nullptr) == ARC_OK);
  CHECK(s.has_pair == 1);
}

// ------------------------------------------------------------ must-fail of the comparisons

TEST_CASE("spacing: the error and margin comparisons catch doctored texts and values", "[spacing][must-fail]") {
  const auto& c = find_case("spacing-three-cycles");
  const WantError want = want_error(c);
  // The vector's own texts with the engine's shortest numbers pass.
  sp::Detail d;
  REQUIRE(sp::parse_detail(want.detail, d, false).empty());
  const std::string good =
      std::string("right ear: gamma_pac (-1, -1, 0) at 201 Hz and binaural (0, 0, 1) at 151.5 Hz; first at ") +
      sp::shortest(d.where.time_s) + " s, gamma rate " + sp::shortest(d.where.rate_hz[0]) + " Hz, theta rate " +
      sp::shortest(d.where.rate_hz[1]) + " Hz, beat rate " + sp::shortest(d.where.rate_hz[2]) + " Hz";
  const std::string value = sp::shortest(c.value_hz);
  const std::string rule = spec::kSpacing_rule;
  const std::string limit = spec::kSpacing_limit;
  CHECK(error_problems(c.parameter, value, rule, limit, good, want).empty());
  const sp::Tolerances tol = tolerances();
  // Each doctored field is caught.
  CHECK_FALSE(error_problems("/gamma_pac/carrier_hz", value, rule, limit, good, want).empty());
  CHECK_FALSE(error_problems(c.parameter, sp::shortest(c.value_hz + 2.0 * tol.frequency_hz), rule, limit, good, want)
                  .empty());
  CHECK_FALSE(error_problems(c.parameter, value + "0", rule, limit, good, want).empty());  // not shortest
  CHECK_FALSE(error_problems(c.parameter, value, "spacing", limit, good, want).empty());
  CHECK_FALSE(error_problems(c.parameter, value, rule, ">= 40 Hz (row spacing-rule)", good, want).empty());
  const std::pair<std::string, std::string> doctors[] = {
      {"right ear", "left ear"},
      {"gamma_pac (-1, -1, 0)", "gamma_pac (-1, 1, 0)"},
      {"binaural (0, 0, 1)", "theta_reference (0, 0, 1)"},
      {"at 201 Hz", "at 201.5 Hz"},
      {"at 201 Hz", "at 201.0 Hz"},
      {"first at " + sp::shortest(d.where.time_s), "first at " + sp::shortest(d.where.time_s + 2.0 * tol.time_s)},
      {"gamma rate " + sp::shortest(d.where.rate_hz[0]), "gamma rate " + sp::shortest(d.where.rate_hz[0] + 2.0 * tol.rate_hz)},
      {"beat rate " + sp::shortest(d.where.rate_hz[2]) + " Hz", "beat rate none"},
      {"; first at", "; at"},
  };
  for (const auto& [from, to] : doctors) {
    INFO("doctored: " << from << " -> " << to);
    CHECK_FALSE(error_problems(c.parameter, value, rule, limit, replaced(good, from, to), want).empty());
  }
  CHECK_FALSE(error_problems(c.parameter, value, rule, limit, sp::kWholeSession, want).empty());
  // A time within the row around the cycle end passes, measured around the cycle.
  CHECK(sp::around_cycle(0.0, tol.period_s - 0.5 * tol.time_s, tol.period_s) < tol.time_s);
  CHECK_FALSE(sp::around_cycle(0.0, tol.period_s - 2.0 * tol.time_s, tol.period_s) < tol.time_s);

  // Margins: the vector itself passes, doctored values fail.
  const auto& mv = find_margin(c.name, 1);
  const auto names = [&](std::size_t i) {
    return i == mv.index_1 ? std::string(mv.row_1) : i == mv.index_2 ? std::string(mv.row_2) : std::string("?");
  };
  Margin m;
  m.has_pair = true;
  m.min_distance_hz = mv.distance_hz;
  m.margin_hz = mv.distance_hz - rule_hz();
  m.component_1 = mv.index_1;
  m.component_2 = mv.index_2;
  CHECK(margin_problems(m, mv, names).empty());
  Margin bad = m;
  bad.min_distance_hz += 2.0 * tol.frequency_hz;
  bad.margin_hz = bad.min_distance_hz - rule_hz();
  CHECK_FALSE(margin_problems(bad, mv, names).empty());
  bad = m;
  bad.margin_hz = std::nextafter(m.margin_hz, 0.0);  // not one subtraction
  CHECK_FALSE(margin_problems(bad, mv, names).empty());
  bad = m;
  bad.component_2 += 1;
  CHECK_FALSE(margin_problems(bad, mv, names).empty());
  bad = m;
  bad.has_pair = false;
  CHECK_FALSE(margin_problems(bad, mv, names).empty());
}

#else

TEST_CASE("spacing rule is implemented", "[spacing]") {
  FAIL("not implemented: validate/spacing.hpp, arc_error::detail (ARC_ERROR_DETAIL_BYTES), or arc_plan_spacing "
       "(Story 3.2)");
}

#endif
