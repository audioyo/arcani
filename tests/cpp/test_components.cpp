// Spectral component table per shape (Story 3.1; docs/signal-spec.md,
// Components).
//
// Compile builds one table of every layer's spectral lines per ear from the
// signal spec's closed form and stores it in the plan; the renderer never
// reads it. The table is read through the public C API:
//
//   typedef enum arc_component_layer { ARC_COMPONENT_THETA_REFERENCE = 0,
//     ARC_COMPONENT_GAMMA_PAC = 1, ARC_COMPONENT_BINAURAL = 2 } arc_component_layer;
//   typedef enum arc_ear { ARC_EAR_LEFT = 0, ARC_EAR_RIGHT = 1 } arc_ear;
//   typedef struct arc_component { arc_component_layer layer; arc_ear ear;
//     double center_hz, low_hz, high_hz, level;
//     int32_t gamma_mult, theta_mult, beat_mult; } arc_component;
//   size_t arc_plan_component_count(const arc_plan* plan);    // 0 for NULL
//   arc_status arc_plan_component(const arc_plan* plan, size_t index,
//                                 arc_component* out_component, arc_error* error);
//
// arc_plan_component follows arc_plan_stage: ARC_ERR_INVALID_ARGUMENT for a
// NULL plan (parameter "plan") or out_component (parameter "out_component"),
// value "null", rule "argument.null", limit "non-null"; index >= count is
// parameter "index", value the index, rule "argument.index", limit the count.
// The table is the same at both sample rates and honors mute_binaural_ear.
//
// Engine internals (engine/src/validate/components.hpp, namespace
// arcani::validate): ComponentLayer, Ear, Component, MutedEar,
// ComponentResult {components, error}, kNoComponentModelRule,
// kComponentLevelDb, kComponentThreshold, build_components(recipe, mute).
// On an unmodeled shape build_components returns no rows and the error
// /theta_reference/shape (custom), /gamma_pac/carrier_wave (the wave text),
// or /binaural/waveform (triangle), rule "no component model", limit the
// modeled shapes, checked in that order. plan::Plan gains
// std::vector<validate::Component> components.
//
// Vectors come from the generated spec_tables.hpp (kComponentCases,
// kComponents, kComponent_*); the error rows component-level-error and
// component-frequency-error and the level row spectral-component-level from
// the tables through the assertion call. No threshold is written here as a
// literal.
//
// Until engine/src/validate/components.hpp exists the file compiles to one
// failing test case, so the rest of the suite still runs. Once it exists the
// C API declarations are expected with it.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#if defined(ARC_ERROR_FIELD_BYTES) && __has_include("validate/components.hpp") && \
    __has_include("plan/plan.hpp") && __has_include("recipe/recipe.hpp")

#include "api_helpers.hpp"
#include "plan/plan.hpp"
#include "recipe/recipe.hpp"
#include "spec_helpers.hpp"
#include "tables.hpp"
#include "validate/components.hpp"

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iterator>
#include <sstream>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

namespace api = arcani::test::api;
namespace plan = arcani::plan;
namespace recipe = arcani::recipe;
namespace spec = arcani::test::spec;
namespace validate = arcani::validate;

namespace {

// One table row, the same shape whichever side it comes from.
struct Line {
  std::string layer;
  std::string ear;
  int gamma_mult = 0;
  int theta_mult = 0;
  int beat_mult = 0;
  double center_hz = 0.0;
  double low_hz = 0.0;
  double high_hz = 0.0;
  double level = 0.0;
};

const char* const kLayerNames[] = {"theta_reference", "gamma_pac", "binaural"};
const char* const kEarNames[] = {"left", "right"};

double level_error() {
  const spec::Row& r = spec::row("component-level-error");
  REQUIRE(r.unit == "ratio");
  return r.value();
}

double frequency_error() {
  const spec::Row& r = spec::row("component-frequency-error");
  return spec::unit_to_hz(r.value(), r.unit);
}

// The vector table of a case in table order: "both" rows expanded, the left
// ear's rows first.
std::vector<Line> want_rows(const spec::ComponentCaseVector& c) {
  std::vector<Line> out;
  for (const char* ear : kEarNames) {
    for (const auto& v : spec::kComponents) {
      if (std::string_view(v.case_name) != c.name) {
        continue;
      }
      const std::string_view e(v.ear);
      if (e == "both" || e == ear) {
        out.push_back({v.layer, ear, v.gamma_mult, v.theta_mult, v.beat_mult, v.center_hz, v.low_hz, v.high_hz,
                       v.level});
      }
    }
  }
  REQUIRE(out.size() == c.components);
  return out;
}

// Problems of `got` against `want` (empty when it holds): the same rows in
// the same order, layer, ear, and multipliers equal, every frequency strictly
// within row component-frequency-error and every level strictly within row
// component-level-error.
std::vector<std::string> compare(const std::vector<Line>& got, const std::vector<Line>& want) {
  const double ltol = level_error();
  const double ftol = frequency_error();
  std::vector<std::string> problems;
  if (got.size() != want.size()) {
    problems.push_back(std::to_string(got.size()) + " rows, the vectors have " + std::to_string(want.size()));
  }
  for (std::size_t i = 0; i < got.size() && i < want.size(); ++i) {
    const Line& g = got[i];
    const Line& w = want[i];
    std::ostringstream where;
    where << "row " << i << " (" << w.layer << ", " << w.ear << ", " << w.gamma_mult << ", " << w.theta_mult << ", "
          << w.beat_mult << ")";
    if (g.layer != w.layer || g.ear != w.ear || g.gamma_mult != w.gamma_mult || g.theta_mult != w.theta_mult ||
        g.beat_mult != w.beat_mult) {
      std::ostringstream is;
      is << where.str() << ": is (" << g.layer << ", " << g.ear << ", " << g.gamma_mult << ", " << g.theta_mult
         << ", " << g.beat_mult << ")";
      problems.push_back(is.str());
      continue;
    }
    const double fg[] = {g.center_hz, g.low_hz, g.high_hz};
    const double fw[] = {w.center_hz, w.low_hz, w.high_hz};
    const char* const names[] = {"center_hz", "low_hz", "high_hz"};
    for (int k = 0; k < 3; ++k) {
      if (!(std::fabs(fg[k] - fw[k]) < ftol)) {
        std::ostringstream m;
        m.precision(17);
        m << where.str() << ": " << names[k] << " " << fg[k] << ", vector " << fw[k];
        problems.push_back(m.str());
      }
    }
    if (!(std::fabs(g.level - w.level) < ltol)) {
      std::ostringstream m;
      m.precision(17);
      m << where.str() << ": level " << g.level << ", vector " << w.level;
      problems.push_back(m.str());
    }
  }
  return problems;
}

std::string joined(const std::vector<std::string>& problems) {
  std::string out;
  for (const auto& p : problems) {
    out += p + "\n";
  }
  return out;
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

plan::MuteEar plan_mute(std::string_view mute) {
  if (mute == "left") {
    return plan::MuteEar::Left;
  }
  if (mute == "right") {
    return plan::MuteEar::Right;
  }
  return plan::MuteEar::None;
}

Line from_api(const arc_component& c) {
  const int layer = static_cast<int>(c.layer);
  const int ear = static_cast<int>(c.ear);
  REQUIRE(layer >= 0);
  REQUIRE(layer < 3);
  REQUIRE(ear >= 0);
  REQUIRE(ear < 2);
  return {kLayerNames[layer], kEarNames[ear], static_cast<int>(c.gamma_mult), static_cast<int>(c.theta_mult),
          static_cast<int>(c.beat_mult), c.center_hz, c.low_hz, c.high_hz, c.level};
}

Line from_engine(const validate::Component& c) {
  const int layer = static_cast<int>(c.layer);
  const int ear = static_cast<int>(c.ear);
  REQUIRE(layer >= 0);
  REQUIRE(layer < 3);
  REQUIRE(ear >= 0);
  REQUIRE(ear < 2);
  return {kLayerNames[layer], kEarNames[ear], static_cast<int>(c.gamma_mult), static_cast<int>(c.theta_mult),
          static_cast<int>(c.beat_mult), c.center_hz, c.low_hz, c.high_hz, c.level};
}

// The whole table of a plan through the C API.
std::vector<Line> api_table(const arc_plan* p) {
  const std::size_t count = arc_plan_component_count(p);
  std::vector<Line> out;
  for (std::size_t i = 0; i < count; ++i) {
    arc_component c;
    std::memset(&c, 0xA5, sizeof c);
    arc_error e;
    api::poison(e);
    const arc_status s = arc_plan_component(p, i, &c, &e);
    INFO("index " << i << ": " << api::describe(e));
    REQUIRE(s == ARC_OK);
    out.push_back(from_api(c));
  }
  return out;
}

std::vector<Line> compiled_table(const std::string& text, std::uint32_t fs, arc_mute_ear mute) {
  auto p = api::compile_ok(text, api::options(ARC_MODE_MEASURE, fs, mute));
  return api_table(p.get());
}

bool same_bits(const std::vector<Line>& a, const std::vector<Line>& b) {
  if (a.size() != b.size()) {
    return false;
  }
  for (std::size_t i = 0; i < a.size(); ++i) {
    const Line& x = a[i];
    const Line& y = b[i];
    if (x.layer != y.layer || x.ear != y.ear || x.gamma_mult != y.gamma_mult || x.theta_mult != y.theta_mult ||
        x.beat_mult != y.beat_mult || api::bits(x.center_hz) != api::bits(y.center_hz) ||
        api::bits(x.low_hz) != api::bits(y.low_hz) || api::bits(x.high_hz) != api::bits(y.high_hz) ||
        api::bits(x.level) != api::bits(y.level)) {
      return false;
    }
  }
  return true;
}

const spec::ComponentCaseVector& find_case(std::string_view name) {
  for (const auto& c : spec::kComponentCases) {
    if (name == c.name) {
      return c;
    }
  }
  FAIL("no component case " << name);
  return spec::kComponentCases[0];
}

// A recipe text made here: the given layer member texts, 10 s.
std::string recipe_with(const std::string& layers) {
  return "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
         "\"author\": \"Arcani test\", \"date\": \"2026-11-16\", "
         "\"rationale\": \"Component test, made in the test.\", "
         "\"length_s\": 10, \"loudness_target_lufs\": -36, " +
         layers + "}";
}

const std::string kThetaSine =
    "\"theta_reference\": {\"carrier_hz\": 450, \"rate_hz\": 6, \"am_depth_percent\": 75, \"shape\": \"sine\"}";
const std::string kThetaCustom =
    "\"theta_reference\": {\"carrier_hz\": 450, \"rate_hz\": 6, \"am_depth_percent\": 75, \"shape\": \"custom\"}";
const std::string kGammaSine =
    "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": 40, \"am_depth_percent\": 100, \"carrier_wave\": \"sine\", "
    "\"coupling\": \"uncoupled\"}";
std::string gamma_wave(const std::string& wave) {
  return "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": 40, \"am_depth_percent\": 100, \"carrier_wave\": \"" +
         wave + "\", \"coupling\": \"uncoupled\"}";
}
// Story 3.2: 100 and 106 Hz (it was 400 and 406 Hz, 38 Hz from the 444 Hz
// theta line), so the muted-ear recipe passes the spacing rule.
const std::string kBinauralSine = "\"binaural\": {\"carrier_left_hz\": 100, \"beat_rate_hz\": 6}";
const std::string kBinauralTriangle =
    "\"binaural\": {\"carrier_left_hz\": 400, \"beat_rate_hz\": 6, \"waveform\": \"triangle\"}";

recipe::Recipe parsed(const std::string& text) {
  recipe::ParseResult r = recipe::parse(text);
  INFO(text << "\n" << r.error.parameter << " " << r.error.rule);
  REQUIRE(r.recipe.has_value());
  return *r.recipe;
}

struct WantError {
  std::string parameter, value, rule, limit;
};

void expect_no_model(const std::string& text, const WantError& want) {
  INFO(text);
  const recipe::Recipe r = parsed(text);
  for (const validate::MutedEar mute : {validate::MutedEar::None, validate::MutedEar::Left,
                                        validate::MutedEar::Right}) {
    const validate::ComponentResult result = validate::build_components(r, mute);
    CHECK(result.components.empty());
    REQUIRE(result.error.has_value());
    CHECK(result.error->parameter == want.parameter);
    CHECK(result.error->value == want.value);
    CHECK(result.error->rule == want.rule);
    CHECK(result.error->limit == want.limit);
  }
}

void expect_compile_rejected(const std::string& text, const WantError& want) {
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs << "\n" << text);
    const api::Compiled c = api::compile(text, api::options(ARC_MODE_MEASURE, fs));
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

void require_null_argument(arc_status s, const arc_error& e, const char* parameter) {
  INFO(api::describe(e));
  CHECK(s == ARC_ERR_INVALID_ARGUMENT);
  REQUIRE(api::all_written(e));
  CHECK(std::string(e.parameter) == parameter);
  CHECK(std::string(e.value) == "null");
  CHECK(std::string(e.rule) == "argument.null");
  CHECK(std::string(e.limit) == "non-null");
}

}  // namespace

// ------------------------------------------------------------ constants and types

TEST_CASE("components: the engine constants equal the vectors and row spectral-component-level",
          "[components]") {
  CHECK(validate::kNoComponentModelRule == std::string_view(spec::kComponent_no_model_rule));
  CHECK(validate::kNoComponentModelRule == "no component model");
  const spec::Row& r = spec::row("spectral-component-level");
  CHECK(r.value() == spec::kComponent_level_db);
  CHECK(validate::kComponentLevelDb == r.value());
  CHECK(api::bits(validate::kComponentThreshold) == api::bits(spec::kComponent_threshold_binary64));
  // The binary64 nearest 10^(-L / 20) for the row's L.
  CHECK(std::fabs(validate::kComponentThreshold - std::pow(10.0, -r.value() / 20.0)) <=
        validate::kComponentThreshold * 0x1p-52);
  CHECK(spec::row("component-level-error").value() == spec::kComponent_level_error);
  CHECK(spec::row("component-frequency-error").value() == spec::kComponent_frequency_error);
  REQUIRE(std::size(spec::kComponent_layers) == 3);
  REQUIRE(std::size(spec::kComponent_ears) == 2);
  for (int i = 0; i < 3; ++i) {
    CHECK(std::string_view(spec::kComponent_layers[i]) == kLayerNames[i]);
  }
  for (int i = 0; i < 2; ++i) {
    CHECK(std::string_view(spec::kComponent_ears[i]) == kEarNames[i]);
  }
}

TEST_CASE("components: the C API enums and struct hold the contract types and values", "[components][api]") {
  CHECK(static_cast<int>(ARC_COMPONENT_THETA_REFERENCE) == 0);
  CHECK(static_cast<int>(ARC_COMPONENT_GAMMA_PAC) == 1);
  CHECK(static_cast<int>(ARC_COMPONENT_BINAURAL) == 2);
  CHECK(static_cast<int>(ARC_EAR_LEFT) == 0);
  CHECK(static_cast<int>(ARC_EAR_RIGHT) == 1);
  CHECK(static_cast<int>(validate::ComponentLayer::ThetaReference) == 0);
  CHECK(static_cast<int>(validate::ComponentLayer::GammaPac) == 1);
  CHECK(static_cast<int>(validate::ComponentLayer::Binaural) == 2);
  CHECK(static_cast<int>(validate::Ear::Left) == 0);
  CHECK(static_cast<int>(validate::Ear::Right) == 1);
  CHECK(std::is_same_v<decltype(arc_component::layer), arc_component_layer>);
  CHECK(std::is_same_v<decltype(arc_component::ear), arc_ear>);
  CHECK(std::is_same_v<decltype(arc_component::center_hz), double>);
  CHECK(std::is_same_v<decltype(arc_component::low_hz), double>);
  CHECK(std::is_same_v<decltype(arc_component::high_hz), double>);
  CHECK(std::is_same_v<decltype(arc_component::level), double>);
  CHECK(std::is_same_v<decltype(arc_component::gamma_mult), std::int32_t>);
  CHECK(std::is_same_v<decltype(arc_component::theta_mult), std::int32_t>);
  CHECK(std::is_same_v<decltype(arc_component::beat_mult), std::int32_t>);
  CHECK(std::is_same_v<decltype(&arc_plan_component_count), std::size_t (*)(const arc_plan*)>);
  CHECK(std::is_same_v<decltype(&arc_plan_component),
                       arc_status (*)(const arc_plan*, std::size_t, arc_component*, arc_error*)>);
  CHECK(std::is_same_v<decltype(plan::Plan::components), std::vector<validate::Component>>);
}

// ------------------------------------------------------------ the vectors

TEST_CASE("components: every vector case through the C API equals the vectors within the error rows",
          "[components][vectors]") {
  REQUIRE(std::size(spec::kComponentCases) > 0);
  for (const auto& c : spec::kComponentCases) {
    const std::vector<Line> want = want_rows(c);
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO("case " << c.name << ", fs " << fs << ", mute " << c.mute);
      const std::vector<Line> got = compiled_table(c.recipe, fs, api_mute(c.mute));
      const std::vector<std::string> problems = compare(got, want);
      INFO(joined(problems));
      CHECK(problems.empty());
    }
  }
}

TEST_CASE("components: every fixture case compiled from its fixture file equals the vectors",
          "[components][vectors]") {
  int fixtures = 0;
  for (const auto& c : spec::kComponentCases) {
    if (std::string_view(c.fixture) == "none") {
      continue;
    }
    ++fixtures;
    const std::string text = api::valid(c.fixture);
    const std::vector<Line> want = want_rows(c);
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO("case " << c.name << ", fixture " << c.fixture << ", fs " << fs << ", mute " << c.mute);
      const std::vector<std::string> problems = compare(compiled_table(text, fs, api_mute(c.mute)), want);
      INFO(joined(problems));
      CHECK(problems.empty());
    }
  }
  CHECK(fixtures > 0);
}

TEST_CASE("components: the table is the same bits at both sample rates and in both modes",
          "[components][vectors]") {
  const std::vector<std::uint32_t> rates = spec::sample_rates();
  REQUIRE(rates.size() >= 2);
  for (const auto& c : spec::kComponentCases) {
    INFO("case " << c.name);
    const std::vector<Line> first = compiled_table(c.recipe, rates[0], api_mute(c.mute));
    CHECK(!first.empty());
    for (std::size_t k = 1; k < rates.size(); ++k) {
      CHECK(same_bits(first, compiled_table(c.recipe, rates[k], api_mute(c.mute))));
    }
  }
  // Final mode with a stored gain: the same table as measure mode.
  const std::string text = std::string(find_case("three-layers").recipe);
  const auto at = text.find('{');
  const std::string with_gain = text.substr(0, at + 1) +
                                "\"loudness_gain_db\": -1.5, "
                                "\"loudness_hash\": "
                                "\"6a29ccd608e4c1945bfff95af078a97daea48eca54a38e065ae33dfa9c2d83a6\", " +
                                text.substr(at + 1);
  auto final_plan = api::compile_ok(with_gain, api::options(ARC_MODE_FINAL, rates[0]));
  CHECK(same_bits(api_table(final_plan.get()), compiled_table(text, rates[0], ARC_MUTE_NONE)));
}

TEST_CASE("components: plan::Plan::components is the table the C API gives", "[components]") {
  for (const auto& c : spec::kComponentCases) {
    INFO("case " << c.name);
    const std::uint32_t fs = spec::sample_rates().back();
    plan::CompileResult r = plan::compile(c.recipe, plan::Mode::Measure, fs, plan_mute(c.mute));
    INFO(r.error.parameter << " " << r.error.rule);
    REQUIRE(r.plan.has_value());
    std::vector<Line> engine;
    for (const validate::Component& comp : r.plan->components) {
      engine.push_back(from_engine(comp));
    }
    CHECK(same_bits(engine, compiled_table(c.recipe, fs, api_mute(c.mute))));
  }
}

TEST_CASE("components: build_components gives the vector table for every case", "[components][vectors]") {
  for (const auto& c : spec::kComponentCases) {
    INFO("case " << c.name);
    const recipe::Recipe r = parsed(c.recipe);
    const std::string_view m(c.mute);
    const validate::MutedEar mute = m == "left"    ? validate::MutedEar::Left
                                    : m == "right" ? validate::MutedEar::Right
                                                   : validate::MutedEar::None;
    const validate::ComponentResult result = validate::build_components(r, mute);
    CHECK_FALSE(result.error.has_value());
    std::vector<Line> got;
    for (const validate::Component& comp : result.components) {
      got.push_back(from_engine(comp));
    }
    const std::vector<std::string> problems = compare(got, want_rows(c));
    INFO(joined(problems));
    CHECK(problems.empty());
  }
}

TEST_CASE("components: every level is in (0, 1], at least the threshold, and a carrier line is 1",
          "[components]") {
  const double t = validate::kComponentThreshold;
  const double ltol = level_error();
  for (const auto& c : spec::kComponentCases) {
    INFO("case " << c.name);
    const std::vector<Line> got = compiled_table(c.recipe, spec::sample_rates()[0], api_mute(c.mute));
    for (const Line& l : got) {
      INFO(l.layer << " " << l.ear << " " << l.gamma_mult << " " << l.theta_mult);
      CHECK(l.level > 0.0);
      CHECK(l.level <= 1.0);
      CHECK(l.level >= t - ltol);
      CHECK(l.low_hz >= 0.0);
      CHECK(l.low_hz <= l.center_hz);
      CHECK(l.center_hz <= l.high_hz);
      if (l.gamma_mult == 0 && l.theta_mult == 0) {
        CHECK(l.level == 1.0);
      }
    }
  }
}

// ------------------------------------------------------------ matrix rows

TEST_CASE("components: sine theta, 450 Hz carrier amplitude-modulated at 6 Hz, 75 percent", "[components][matrix]") {
  const std::vector<Line> got =
      compiled_table(find_case("theta-sine-6hz").recipe, spec::sample_rates()[0], ARC_MUTE_NONE);
  REQUIRE(got.size() == 6);
  const double centers[] = {444.0, 450.0, 456.0};
  const double levels[] = {0.3, 1.0, 0.3};
  for (int ear = 0; ear < 2; ++ear) {
    for (int k = 0; k < 3; ++k) {
      const Line& l = got[static_cast<std::size_t>(3 * ear + k)];
      CHECK(l.layer == "theta_reference");
      CHECK(l.ear == kEarNames[ear]);
      CHECK(std::fabs(l.center_hz - centers[k]) < frequency_error());
      CHECK(std::fabs(l.level - levels[k]) < level_error());
    }
  }
}

TEST_CASE("components: smooth swell, 250 Hz carrier AM at 40 Hz, 100 percent, theta 6 Hz", "[components][matrix]") {
  const std::vector<Line> got =
      compiled_table(find_case("swell-sine-0deg-100pct").recipe, spec::sample_rates()[0], ARC_MUTE_NONE);
  for (const char* ear : kEarNames) {
    std::vector<Line> gamma;
    for (const Line& l : got) {
      if (l.layer == "gamma_pac" && l.ear == ear) {
        gamma.push_back(l);
      }
    }
    REQUIRE(gamma.size() == 9);
    CHECK(std::fabs(gamma.front().center_hz - 204.0) < frequency_error());
    CHECK(std::fabs(gamma.back().center_hz - 296.0) < frequency_error());
    for (const Line& l : gamma) {
      const int order = std::abs(l.gamma_mult) + std::abs(l.theta_mult);
      const double want = order == 0 ? 1.0 : order == 1 ? 1.0 / 6.0 : 1.0 / 12.0;
      CHECK(std::fabs(l.level - want) < level_error());
    }
  }
}

TEST_CASE("components: depth 0 leaves the carrier alone", "[components][matrix]") {
  const char* const shapes[] = {"sine", "smoothed_on_off", "sawtooth", "reverse_saw"};
  for (const char* shape : shapes) {
    const std::string text = recipe_with(
        std::string("\"theta_reference\": {\"carrier_hz\": 450, \"rate_hz\": 6, \"am_depth_percent\": 0, \"shape\": \"") +
        shape + "\"}, \"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": 40, \"am_depth_percent\": 0, "
                "\"carrier_wave\": \"sine\", \"coupling\": \"uncoupled\"}");
    INFO(shape);
    const std::vector<Line> got = compiled_table(text, spec::sample_rates()[0], ARC_MUTE_NONE);
    REQUIRE(got.size() == 4);
    for (const Line& l : got) {
      CHECK(l.gamma_mult == 0);
      CHECK(l.theta_mult == 0);
      CHECK(l.level == 1.0);
      CHECK(l.center_hz == (l.layer == "theta_reference" ? 450.0 : 250.0));
    }
  }
}

TEST_CASE("components: muted ear has no binaural row; the other ear keeps it", "[components][matrix]") {
  const std::string text = recipe_with(kThetaSine + ", " + kBinauralSine);
  const std::uint32_t fs = spec::sample_rates()[0];
  const std::vector<Line> none = compiled_table(text, fs, ARC_MUTE_NONE);
  const auto count = [](const std::vector<Line>& t, const char* ear) {
    int n = 0;
    for (const Line& l : t) {
      n += (l.layer == "binaural" && l.ear == ear) ? 1 : 0;
    }
    return n;
  };
  CHECK(count(none, "left") == 1);
  CHECK(count(none, "right") == 1);
  const std::vector<Line> right_muted = compiled_table(text, fs, ARC_MUTE_RIGHT);
  CHECK(count(right_muted, "left") == 1);
  CHECK(count(right_muted, "right") == 0);
  CHECK(right_muted.size() + 1 == none.size());
  const std::vector<Line> left_muted = compiled_table(text, fs, ARC_MUTE_LEFT);
  CHECK(count(left_muted, "left") == 0);
  CHECK(count(left_muted, "right") == 1);
  CHECK(left_muted.size() + 1 == none.size());
}

// ------------------------------------------------------------ unmodeled shapes

TEST_CASE("components: build_components refuses an unmodeled shape with rule no component model",
          "[components][no-model]") {
  const std::string rule(validate::kNoComponentModelRule);
  expect_no_model(recipe_with(kThetaCustom),
                  {"/theta_reference/shape", "custom", rule, "sine, smoothed_on_off, sawtooth, reverse_saw"});
  for (const char* wave : {"triangle", "softened_square"}) {
    expect_no_model(recipe_with(gamma_wave(wave)), {"/gamma_pac/carrier_wave", wave, rule, "sine"});
  }
  expect_no_model(recipe_with(kBinauralTriangle), {"/binaural/waveform", "triangle", rule, "sine"});
  // Order: theta shape, then gamma carrier wave, then binaural waveform.
  expect_no_model(recipe_with(kThetaCustom + ", " + gamma_wave("triangle") + ", " + kBinauralTriangle),
                  {"/theta_reference/shape", "custom", rule, "sine, smoothed_on_off, sawtooth, reverse_saw"});
  expect_no_model(recipe_with(kThetaSine + ", " + gamma_wave("triangle") + ", " + kBinauralTriangle),
                  {"/gamma_pac/carrier_wave", "triangle", rule, "sine"});
  // Must-pass twin: the modeled shapes build a table and no error.
  const validate::ComponentResult ok =
      validate::build_components(parsed(recipe_with(kThetaSine + ", " + kGammaSine + ", " + kBinauralSine)),
                                 validate::MutedEar::None);
  CHECK_FALSE(ok.error.has_value());
  CHECK(ok.components.size() == 14);
}

TEST_CASE("components: compile still rejects unmodeled shapes with their earlier texts", "[components][no-model]") {
  expect_compile_rejected(recipe_with(kThetaCustom), {"/theta_reference/shape", "custom",
                                                      "shape not modeled in the signal spec",
                                                      "sine, smoothed_on_off, sawtooth, reverse_saw"});
  for (const char* wave : {"triangle", "softened_square"}) {
    expect_compile_rejected(recipe_with(gamma_wave(wave)),
                            {"/gamma_pac/carrier_wave", wave, "non-sine carrier not modeled", "sine"});
  }
  expect_compile_rejected(recipe_with(kBinauralTriangle),
                          {"/binaural/waveform", "triangle", "non-sine binaural not modeled", "sine"});
  expect_compile_rejected(recipe_with(kThetaCustom + ", " + gamma_wave("triangle") + ", " + kBinauralTriangle),
                          {"/theta_reference/shape", "custom", "shape not modeled in the signal spec",
                           "sine, smoothed_on_off, sawtooth, reverse_saw"});
}

// ------------------------------------------------------------ C API arguments

TEST_CASE("components: arc_plan_component refuses a NULL plan, a NULL output, and an index past the table",
          "[components][api]") {
  auto p = api::compile_ok(find_case("theta-sine-6hz").recipe, api::options(ARC_MODE_MEASURE, 48000));
  const std::size_t count = arc_plan_component_count(p.get());
  REQUIRE(count == 6);
  CHECK(arc_plan_component_count(nullptr) == 0);
  arc_component c;
  arc_error e;
  api::poison(e);
  require_null_argument(arc_plan_component(nullptr, 0, &c, &e), e, "plan");
  api::poison(e);
  require_null_argument(arc_plan_component(p.get(), 0, nullptr, &e), e, "out_component");
  for (const std::size_t index : {count, count + 1, static_cast<std::size_t>(-1)}) {
    api::poison(e);
    CHECK(arc_plan_component(p.get(), index, &c, &e) == ARC_ERR_INVALID_ARGUMENT);
    REQUIRE(api::all_written(e));
    CHECK(std::string(e.parameter) == "index");
    CHECK(std::string(e.value) == std::to_string(index));
    CHECK(std::string(e.rule) == "argument.index");
    CHECK(std::string(e.limit) == std::to_string(count));
  }
  // A NULL error pointer is allowed.
  CHECK(arc_plan_component(p.get(), count, &c, nullptr) == ARC_ERR_INVALID_ARGUMENT);
  CHECK(arc_plan_component(p.get(), 0, &c, nullptr) == ARC_OK);
  // The last valid index is fine.
  api::poison(e);
  CHECK(arc_plan_component(p.get(), count - 1, &c, &e) == ARC_OK);
}

TEST_CASE("components: a plan without layers has an empty table", "[components][api]") {
  auto p = api::compile_ok(api::valid(api::kNoLayers), api::options(ARC_MODE_MEASURE, 48000));
  CHECK(arc_plan_component_count(p.get()) == 0);
  arc_component c;
  arc_error e;
  api::poison(e);
  CHECK(arc_plan_component(p.get(), 0, &c, &e) == ARC_ERR_INVALID_ARGUMENT);
  REQUIRE(api::all_written(e));
  CHECK(std::string(e.rule) == "argument.index");
  CHECK(std::string(e.limit) == "0");
}

// ------------------------------------------------------------ must-fail of the comparison

TEST_CASE("components: the comparison catches a doctored table", "[components][must-fail]") {
  const auto& c = find_case("bursts-60hz");
  const std::vector<Line> want = want_rows(c);
  REQUIRE(compare(want, want).empty());
  const double ltol = level_error();
  const double ftol = frequency_error();
  {
    std::vector<Line> t = want;  // one side frequency dropped
    for (std::size_t i = 0; i < t.size(); ++i) {
      if (t[i].layer == "gamma_pac" && (t[i].gamma_mult != 0 || t[i].theta_mult != 0)) {
        t.erase(t.begin() + static_cast<std::ptrdiff_t>(i));
        break;
      }
    }
    CHECK_FALSE(compare(t, want).empty());
  }
  {
    std::vector<Line> t = want;
    t[3].level += 2.0 * ltol;
    CHECK_FALSE(compare(t, want).empty());
    t[3].level = want[3].level + 0.5 * ltol;
    CHECK(compare(t, want).empty());
  }
  {
    std::vector<Line> t = want;
    t[4].center_hz += 2.0 * ftol;
    CHECK_FALSE(compare(t, want).empty());
    t = want;
    t[4].high_hz -= 2.0 * ftol;
    CHECK_FALSE(compare(t, want).empty());
  }
  {
    std::vector<Line> t = want;
    std::swap(t[1], t[2]);
    CHECK_FALSE(compare(t, want).empty());
  }
  {
    std::vector<Line> t = want;
    t[0].theta_mult += 1;
    CHECK_FALSE(compare(t, want).empty());
    t = want;
    t[0].ear = "right";
    CHECK_FALSE(compare(t, want).empty());
  }
}

#else

TEST_CASE("spectral component table is implemented", "[components]") {
  FAIL("not implemented: validate/components.hpp, Plan::components, or arc_plan_component (Story 3.1)");
}

#endif
