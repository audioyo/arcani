// Looping body and seams (Story 2.7; docs/signal-spec.md, Loop).
//
// A looping recipe carries a top-level `loop` {mode, opening_s, body_s,
// max_run_time_min}. Looping repeats the parameter schedule, never stored
// samples: every phase keeps running on the one engine clock, so a seam is
// only a frame number and a looping recipe renders sample for sample what
// the same recipe without `loop` renders. Frames, once per plan:
//
//   O = seconds_to_samples(opening_s, fs)   opening end (the join)
//   B = seconds_to_samples(body_s, fs)      body length
//   N = seconds_to_samples(length_s, fs)    session end
//   seam k = O + k * B, k = 1 to M, M = (N - O - 1) div B
//
// Expected interface (spec Implementation Notes):
//
//   arcani/arcani.h:
//     typedef struct arc_loop_frames { int looping; uint64_t opening_end_frame;
//       uint64_t body_frames; uint64_t seam_count; uint64_t end_frame; } arc_loop_frames;
//     arc_status arc_plan_loop(const arc_plan* plan, arc_loop_frames* out_loop, arc_error* error);
//   ARC_ERR_INVALID_ARGUMENT for a NULL plan or out_loop (parameter "plan" or
//   "out_loop", value "null", rule "argument.null", limit "non-null", as
//   every null argument of the C API); without `loop`, ARC_OK with every
//   field 0.
//
//   plan/plan.hpp: plan::LoopFrames { bool present; std::uint64_t
//   opening_end_frame, body_frames, seam_count; } as Plan::loop.
//
//   validate/validate.hpp: range_rows() gains max-run-time-focus and
//   max-run-time-learn (unit min); check_loop(const recipe::Recipe&) holds
//   the seven loop rules (nothing without `loop`); check_ranges() calls it
//   after its field walk, so the loop rules follow every range check and
//   precede check_rules(). Rule texts kLoopLengthRule,
//   kLoopWholeSamplesRule, kLoopWholeSamplesLimit, kLoopWholeCyclesRule,
//   kLoopExceedsRule equal the spec's loop_constants.
//
// The new C API is reached through a dependent call (found by argument
// dependent lookup once arcani/arcani.h declares it) and an elaborated type
// specifier, the plan member through a requires-expression, and the
// validator constants and check_loop through a lookup probe, so the suite
// builds before they exist and the missing pieces fail as test cases.
//
// Vectors come from the generated spec_tables.hpp (kLoopFrames,
// kLoopCompileCases, kLoopWholeSamples, kLoop_*); rows from the tables
// through the assertion call (max-run-time-focus, max-run-time-learn,
// rate-cycle-period, theta-rate, theta-carrier, beat-rate, sample-rates).
// No threshold or range value is written here as a literal.
//
// Fixtures (recipes/fixtures/valid/): loop-swell-theta-cycle.json (mode
// learn; a 450 Hz carrier amplitude-modulated by the sine envelope at a
// theta rate of 4 +- 2 Hz cycling every 60 s, 75 percent depth, and a 250 Hz
// sine carrier amplitude-modulated at 40 Hz with a smooth swell peaking at
// the 0 degree coupling phase, 100 percent depth; opening 60 s, body 120 s,
// 20 min cap), loop-bursts-theta-cycle.json (the same with 50 ms bursts),
// loop-focus-no-cycle.json (mode focus; the 450 Hz carrier
// amplitude-modulated by the sine envelope at a fixed 4 Hz theta rate alone;
// opening 0 s, body 90.25 s, 45 min cap), and twelve compile-rejected ones.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#if defined(ARC_ERROR_FIELD_BYTES) && __has_include("plan/plan.hpp") && __has_include("validate/validate.hpp") && \
    __has_include("recipe/recipe.hpp")

#include "api_helpers.hpp"
#include "loudness_gain_helpers.hpp"
#include "core/phase.hpp"
#include "plan/plan.hpp"
#include "recipe/recipe.hpp"
#include "spec_helpers.hpp"
#include "tables.hpp"
#include "validate/validate.hpp"

#include <algorithm>
#include <cctype>
#include <charconv>
#include <concepts>
#include <cstdint>
#include <cstring>
#include <iterator>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>

// ------------------------------------------------------------ lookup probe
//
// Inside arcani::validate_loop_probe the using-directive makes the names of
// arcani::validate visible as members of arcani, which unqualified lookup
// reaches before these global fallbacks: a real constant or check_loop
// hides its fallback, and a missing one reads as "(missing)" or as
// LoopCheckMissing.
inline constexpr std::string_view kLoopLengthRule = "(missing)";
inline constexpr std::string_view kLoopWholeSamplesRule = "(missing)";
inline constexpr std::string_view kLoopWholeSamplesLimit = "(missing)";
inline constexpr std::string_view kLoopWholeCyclesRule = "(missing)";
inline constexpr std::string_view kLoopExceedsRule = "(missing)";

struct LoopCheckMissing {};
template <class R>
LoopCheckMissing check_loop(const R&) {
  return {};
}

namespace arcani::validate_loop_probe {
using namespace arcani::validate;
inline const std::string length_rule(kLoopLengthRule);
inline const std::string whole_samples_rule(kLoopWholeSamplesRule);
inline const std::string whole_samples_limit(kLoopWholeSamplesLimit);
inline const std::string whole_cycles_rule(kLoopWholeCyclesRule);
inline const std::string exceeds_rule(kLoopExceedsRule);
template <class R>
auto run_check_loop(const R& r) {
  return check_loop(r);
}
}  // namespace arcani::validate_loop_probe

// The C API type: an elaborated type specifier finds ::arc_loop_frames once
// arcani/arcani.h declares it, and otherwise declares an incomplete
// loop_api_probe::arc_loop_frames, so kComplete reads false.
namespace loop_api_probe {
using Frames = struct arc_loop_frames;
template <class T>
inline constexpr bool kComplete = requires { sizeof(T); };
template <class P, class L>
concept HasPlanLoop = requires(const P* p, L* l, arc_error* e) {
  { arc_plan_loop(p, l, e) } -> std::same_as<arc_status>;
};
template <class L>
concept HasMembers = requires(const L& l) {
  l.looping;
  l.opening_end_frame;
  l.body_frames;
  l.seam_count;
  l.end_frame;
};
}  // namespace loop_api_probe

namespace api = arcani::test::api;
namespace core = arcani::core;
namespace plan = arcani::plan;
namespace recipe = arcani::recipe;
namespace spec = arcani::test::spec;
namespace tables = arcani::test::tables;
namespace validate = arcani::validate;
namespace lprobe = arcani::validate_loop_probe;

namespace {

constexpr arc_mode kModes[] = {ARC_MODE_MEASURE, ARC_MODE_FINAL};

// Fixtures written before Story 2.7: none has a loop.
const char* const kEarlierFixtures[] = {"theta-sine-6hz.json",       "both-layers.json",
                                        "swell-theta-cycle.json",    "bursts-theta-cycle.json",
                                        "binaural-cycle-sleep.json", "gamma-cycle-swell-theta-cycle.json"};

// Shortest round-trip text of a binary64, as every range error writes it.
std::string num(double x) {
  char buf[64];
  const auto r = std::to_chars(buf, buf + sizeof buf, x);
  REQUIRE(r.ec == std::errc());
  return std::string(buf, r.ptr);
}

const tables::Row& cap_row(const std::string& mode) {
  return spec::row(mode == "focus" ? "max-run-time-focus" : "max-run-time-learn");
}

// The fixture text with a stored loudness gain and hash added as the first
// members, so final mode compiles too (as the range matrix base recipe does).
std::string with_gain(const std::string& text) {
  const auto at = text.find('{');
  REQUIRE(at != std::string::npos);
  // Story 4.2: the engine's loudness hash in place of the placeholder.
  return arcani::test::loudness::stored_hash_text(
      text.substr(0, at + 1) +
      "\"loudness_gain_db\": -1.5, "
      "\"loudness_hash\": \"6a29ccd608e4c1945bfff95af078a97daea48eca54a38e065ae33dfa9c2d83a6\", " +
      text.substr(at + 1));
}

// The same recipe text with the top-level loop object and its comma removed.
std::string without_loop(const std::string& text) {
  const auto key = text.find("\"loop\"");
  REQUIRE(key != std::string::npos);
  const auto open = text.find('{', key);
  REQUIRE(open != std::string::npos);
  int depth = 0;
  std::size_t close = open;
  for (; close < text.size(); ++close) {
    if (text[close] == '{') {
      ++depth;
    } else if (text[close] == '}' && --depth == 0) {
      break;
    }
  }
  REQUIRE(close < text.size());
  std::size_t from = key;
  while (from > 0 && std::isspace(static_cast<unsigned char>(text[from - 1])) != 0) {
    --from;
  }
  std::string out;
  if (from > 0 && text[from - 1] == ',') {
    out = text.substr(0, from - 1) + text.substr(close + 1);
  } else {
    std::size_t to = close + 1;
    while (to < text.size() && std::isspace(static_cast<unsigned char>(text[to])) != 0) {
      ++to;
    }
    if (to < text.size() && text[to] == ',') {
      ++to;
    }
    out = text.substr(0, key) + text.substr(to);
  }
  REQUIRE(out.find("\"loop\"") == std::string::npos);
  REQUIRE(recipe::parse(out).recipe.has_value());
  return out;
}

const spec::LoopFrameVector& frame_row(const std::string& fixture, std::uint32_t fs) {
  for (const auto& v : spec::kLoopFrames) {
    if (fixture == v.fixture && fs == v.fs) {
      return v;
    }
  }
  FAIL("no loop frame vector for " << fixture << " at " << fs);
  return spec::kLoopFrames[0];
}

// ------------------------------------------------------------ recipes made here

const char* const kSwellGamma =
    "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": 40, \"am_depth_percent\": 100, "
    "\"carrier_wave\": \"sine\", \"coupling\": \"smooth_swell\", \"coupling_phase_deg\": 0}";

// A looping recipe: a 450 Hz carrier amplitude-modulated by the sine envelope
// at 4 Hz, 75 percent depth, with a theta rate cycle of +- theta_swing Hz
// over the period of row rate-cycle-period (empty swing: no cycle), plus the
// gamma and binaural member texts as given. Empty cap or length: the mode's
// row value, and cap * 60.
struct LoopRecipe {
  std::string mode = "learn";
  std::string opening = "60";
  std::string body = "120";
  std::string cap;
  std::string length;
  std::string theta_carrier = "450";
  std::string theta_swing = "2";
  std::string gamma_cycle;  // whole rate_cycle member text inside gamma_pac, or empty
  std::string gamma = kSwellGamma;
  std::string binaural;
  bool loop = true;
};

std::string period_text() { return num(spec::row("rate-cycle-period").min); }

std::string make(const LoopRecipe& r) {
  const std::string cap = r.cap.empty() ? num(cap_row(r.mode).max) : r.cap;
  const std::string length = r.length.empty() ? num(cap_row(r.mode).max * 60.0) : r.length;
  std::string s =
      "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
      "\"author\": \"Arcani test\", \"date\": \"2026-11-14\", "
      "\"rationale\": \"Loop test, made in the test.\", "
      "\"length_s\": " + length + ", \"loudness_target_lufs\": -36, "
      "\"loudness_gain_db\": -1.5, "
      "\"loudness_hash\": \"6a29ccd608e4c1945bfff95af078a97daea48eca54a38e065ae33dfa9c2d83a6\", "
      "\"theta_reference\": {\"carrier_hz\": " + r.theta_carrier +
      ", \"rate_hz\": 4, \"am_depth_percent\": 75, \"shape\": \"sine\"";
  if (!r.theta_swing.empty()) {
    s += ", \"rate_cycle\": {\"swing_hz\": " + r.theta_swing + ", \"period_s\": " + period_text() +
         ", \"start_phase_deg\": 0}";
  }
  s += "}";
  if (!r.gamma.empty()) {
    std::string g = r.gamma;
    if (!r.gamma_cycle.empty()) {
      g.insert(g.size() - 1, ", " + r.gamma_cycle);
    }
    s += ", " + g;
  }
  if (!r.binaural.empty()) {
    s += ", " + r.binaural;
  }
  if (r.loop) {
    s += ", \"loop\": {\"mode\": \"" + r.mode + "\", \"opening_s\": " + r.opening + ", \"body_s\": " + r.body +
         ", \"max_run_time_min\": " + cap + "}";
  }
  // Story 4.2: the engine's loudness hash in place of the placeholder.
  return arcani::test::loudness::stored_hash_text(s + "}");
}

struct Want {
  std::string parameter, value, rule, limit;
};

void expect_ok(const std::string& text) {
  for (const arc_mode mode : kModes) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO("mode " << mode << ", fs " << fs << "\n" << text);
      const api::Compiled c = api::compile(text, api::options(mode, fs));
      INFO(api::describe(c.error));
      CHECK(c.status == ARC_OK);
    }
  }
}

void expect_rejected(const std::string& text, const Want& want) {
  for (const arc_mode mode : kModes) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO("mode " << mode << ", fs " << fs << "\n" << text);
      const api::Compiled c = api::compile(text, api::options(mode, fs));
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
}

// The cap error of a recipe whose max run time is one minute above its row.
Want cap_error(const std::string& mode) {
  const tables::Row& r = cap_row(mode);
  return {"/loop/max_run_time_min", num(r.max + 1.0), "range.max",
          "<= " + num(r.max) + " " + r.unit + " (row " + r.id + ")"};
}

// ------------------------------------------------------------ the C API

struct LoopInfo {
  arc_status status = ARC_ERR_INTERNAL;
  arc_error error{};
  long long looping = -1;
  std::uint64_t opening_end_frame = 0;
  std::uint64_t body_frames = 0;
  std::uint64_t seam_count = 0;
  std::uint64_t end_frame = 0;
};

// arc_plan_loop on `plan`, with the output poisoned first so every field
// the call does not write shows; a failed check when the API is missing.
template <class P = arc_plan, class L = loop_api_probe::Frames>
LoopInfo plan_loop(const P* plan) {
  LoopInfo info;
  if constexpr (loop_api_probe::kComplete<L> && loop_api_probe::HasPlanLoop<P, L> &&
                loop_api_probe::HasMembers<L>) {
    L out;
    std::memset(&out, 0xA5, sizeof out);
    api::poison(info.error);
    info.status = arc_plan_loop(plan, &out, &info.error);
    info.looping = static_cast<long long>(out.looping);
    info.opening_end_frame = static_cast<std::uint64_t>(out.opening_end_frame);
    info.body_frames = static_cast<std::uint64_t>(out.body_frames);
    info.seam_count = static_cast<std::uint64_t>(out.seam_count);
    info.end_frame = static_cast<std::uint64_t>(out.end_frame);
  } else {
    FAIL("not implemented: arc_loop_frames and arc_plan_loop in arcani/arcani.h (Story 2.7)");
  }
  return info;
}

[[maybe_unused]] void require_null_argument(arc_status s, const arc_error& e, const char* parameter) {
  INFO(api::describe(e));
  CHECK(s == ARC_ERR_INVALID_ARGUMENT);
  REQUIRE(api::all_written(e));
  CHECK(std::string(e.parameter) == parameter);
  CHECK(std::string(e.value) == "null");
  CHECK(std::string(e.rule) == "argument.null");
  CHECK(std::string(e.limit) == "non-null");
}

template <class P = arc_plan, class L = loop_api_probe::Frames>
void check_null_arguments(const P* plan) {
  if constexpr (loop_api_probe::kComplete<L> && loop_api_probe::HasPlanLoop<P, L>) {
    L out;
    arc_error e;
    api::poison(e);
    const P* none = nullptr;
    require_null_argument(arc_plan_loop(none, &out, &e), e, "plan");
    api::poison(e);
    L* no_out = nullptr;
    require_null_argument(arc_plan_loop(plan, no_out, &e), e, "out_loop");
  } else {
    FAIL("not implemented: arc_loop_frames and arc_plan_loop in arcani/arcani.h (Story 2.7)");
  }
}

template <class L = loop_api_probe::Frames>
void check_frames_layout() {
  if constexpr (loop_api_probe::kComplete<L> && loop_api_probe::HasMembers<L>) {
    CHECK(std::is_same_v<decltype(L::looping), int>);
    CHECK(std::is_same_v<decltype(L::opening_end_frame), std::uint64_t>);
    CHECK(std::is_same_v<decltype(L::body_frames), std::uint64_t>);
    CHECK(std::is_same_v<decltype(L::seam_count), std::uint64_t>);
    CHECK(std::is_same_v<decltype(L::end_frame), std::uint64_t>);
    CHECK(std::is_standard_layout_v<L>);
    CHECK(std::is_trivially_copyable_v<L>);
  } else {
    FAIL("not implemented: arc_loop_frames {looping, opening_end_frame, body_frames, seam_count, end_frame} "
         "(Story 2.7)");
  }
}

// ------------------------------------------------------------ the plan

template <class P>
concept PlanHasLoop = requires(const P& p) {
  { p.loop.present } -> std::convertible_to<bool>;
  { p.loop.opening_end_frame } -> std::convertible_to<std::uint64_t>;
  { p.loop.body_frames } -> std::convertible_to<std::uint64_t>;
  { p.loop.seam_count } -> std::convertible_to<std::uint64_t>;
};

struct PlanLoop {
  bool present = false;
  std::uint64_t opening_end_frame = 0, body_frames = 0, seam_count = 0, frame_count = 0;
};

template <class P = plan::Plan>
PlanLoop plan_member(const std::string& text, std::uint32_t fs) {
  PlanLoop out;
  auto r = plan::compile(text, plan::Mode::Measure, fs, plan::MuteEar::None);
  INFO("rule '" << r.error.rule << "', parameter '" << r.error.parameter << "', value '" << r.error.value
                << "', limit '" << r.error.limit << "'");
  REQUIRE(r.plan.has_value());
  const P& p = *r.plan;
  out.frame_count = p.frame_count;
  if constexpr (PlanHasLoop<P>) {
    out.present = static_cast<bool>(p.loop.present);
    out.opening_end_frame = static_cast<std::uint64_t>(p.loop.opening_end_frame);
    out.body_frames = static_cast<std::uint64_t>(p.loop.body_frames);
    out.seam_count = static_cast<std::uint64_t>(p.loop.seam_count);
  } else {
    FAIL("not implemented: plan::Plan has no loop {present, opening_end_frame, body_frames, seam_count} "
         "(Story 2.7)");
  }
  return out;
}

// ------------------------------------------------------------ renders

struct Window {
  std::vector<double> out;
  api::TapBuffers taps{0};
};

Window render_window(arc_plan* p, std::uint64_t start, std::size_t frames) {
  auto r = api::renderer(p);
  api::seek(r.get(), start);
  Window w;
  w.taps = api::TapBuffers(frames);
  const arc_taps t = w.taps.taps();
  w.out = api::render(r.get(), frames, &t);
  return w;
}

bool same_window(const Window& a, const Window& b) {
  return api::same_bytes(a.out, b.out) && api::same_bytes(a.taps.theta_reference, b.taps.theta_reference) &&
         api::same_bytes(a.taps.gamma_pac, b.taps.gamma_pac) && api::same_bytes(a.taps.stereo_bus, b.taps.stereo_bus) &&
         api::same_bytes(a.taps.binaural_join, b.taps.binaural_join) && api::same_bytes(a.taps.master, b.taps.master);
}

// Every sample of the window from frame `from` (window-relative) on is +0.0.
bool silent_from(const Window& w, std::size_t from) {
  const std::size_t at = 2 * from;
  const std::size_t n = w.out.size() - at;
  return api::all_exact_zero(w.out.data() + at, n) && api::all_exact_zero(w.taps.theta_reference.data() + at, n) &&
         api::all_exact_zero(w.taps.gamma_pac.data() + at, n) &&
         api::all_exact_zero(w.taps.stereo_bus.data() + at, n) &&
         api::all_exact_zero(w.taps.binaural_join.data() + at, n) &&
         api::all_exact_zero(w.taps.master.data() + at, n);
}

}  // namespace

// ------------------------------------------------------------ vectors

TEST_CASE("loop: the frame vectors follow the spec's frame rules", "[loop][vectors]") {
  std::set<std::string> fixtures;
  for (const auto& v : spec::kLoopFrames) {
    INFO(v.fixture << " at " << v.fs);
    fixtures.insert(v.fixture);
    REQUIRE(v.body_frames > 0);
    REQUIRE(v.opening_end_frame + v.body_frames <= v.end_frame);
    CHECK(v.seam_count == (v.end_frame - v.opening_end_frame - 1) / v.body_frames);
    REQUIRE(v.seam_count <= spec::kLoopMaxSeams);
    for (std::uint64_t k = 1; k <= v.seam_count; ++k) {
      CHECK(v.seams[k - 1] == v.opening_end_frame + k * v.body_frames);
      CHECK(v.seams[k - 1] < v.end_frame);
    }
    for (std::size_t k = static_cast<std::size_t>(v.seam_count); k < spec::kLoopMaxSeams; ++k) {
      CHECK(v.seams[k] == 0);
    }
    const std::uint64_t last_start = v.seam_count > 0 ? v.seams[v.seam_count - 1] : v.opening_end_frame;
    CHECK(v.last_pass_frames == v.end_frame - last_start);
    CHECK(v.last_pass_frames <= v.body_frames);
  }
  // The three compile-accepted loop fixtures, each at both rates.
  CHECK(fixtures.size() == 3);
  CHECK(std::size(spec::kLoopFrames) == 3 * spec::sample_rates().size());
  CHECK(fixtures.count(spec::kLoop_full_render_fixture) == 1);
  CHECK(fixtures.count(spec::kLoop_probe_fixture) == 1);
  // The probe seam exists in the probe fixture at both rates.
  for (const std::uint32_t fs : spec::sample_rates()) {
    CHECK(frame_row(spec::kLoop_probe_fixture, fs).seam_count >= spec::kLoop_probe_seam);
  }
}

TEST_CASE("loop: the whole-sample vectors hold the seconds-to-samples rule", "[loop][vectors]") {
  for (const auto& v : spec::kLoopWholeSamples) {
    INFO("t_s " << num(v.t_s));
    CHECK(core::seconds_to_samples(v.t_s, 44100) == v.n_44100);
    CHECK(core::seconds_to_samples(v.t_s, 48000) == v.n_48000);
    // Whole at both rates exactly when 4 * t_s is an integer (exact scale).
    const double x = v.t_s * 4.0;
    CHECK(v.whole == (x == static_cast<double>(static_cast<std::uint64_t>(x))));
  }
}

// ------------------------------------------------------------ validator constants and rows

TEST_CASE("loop: the validator rule constants hold the spec text", "[loop][validate]") {
  CHECK(lprobe::length_rule == spec::kLoop_length_rule);
  CHECK(lprobe::whole_samples_rule == spec::kLoop_whole_samples_rule);
  CHECK(lprobe::whole_samples_limit == spec::kLoop_whole_samples_limit);
  CHECK(lprobe::whole_cycles_rule == spec::kLoop_whole_cycles_rule);
  CHECK(lprobe::exceeds_rule == spec::kLoop_exceeds_rule);
}

TEST_CASE("loop: the engine range table holds both max run time rows as in ranges.tsv", "[loop][validate][ranges]") {
  for (const char* id : {"max-run-time-focus", "max-run-time-learn"}) {
    INFO(id);
    // The assertion call: records the id for the row coverage check.
    const tables::Row& r = tables::row(id);
    CHECK(r.kind == "ranges");
    CHECK(r.unit == "min");
    // Story 2.7 lands both rows: neither is pending any more.
    CHECK(r.pending.empty());
    // A single value: min equals max.
    CHECK(r.min == r.max);
    int found = 0;
    for (const auto& e : validate::range_rows()) {
      if (e.id != id) {
        continue;
      }
      ++found;
      CHECK(e.min == r.min);
      CHECK(e.max == r.max);
      CHECK(e.max_exclusive == (r.max_bound == "exclusive"));
      CHECK(std::string(e.unit) == r.unit);
    }
    CHECK(found == 1);
  }
  // The spec vectors name the same max run times as the rows.
  CHECK(spec::kLoop_max_run_time_min_focus == tables::row("max-run-time-focus").max);
  CHECK(spec::kLoop_max_run_time_min_learn == tables::row("max-run-time-learn").max);
}

// ------------------------------------------------------------ compile cases

TEST_CASE("loop: every loop compile case compiles or is rejected with its rule, both modes, both rates",
          "[loop][validate][compile]") {
  std::size_t accepted = 0;
  std::size_t rejected = 0;
  for (const auto& c : spec::kLoopCompileCases) {
    const std::string raw = api::valid(c.fixture);
    const std::string text = with_gain(raw);
    for (const arc_mode mode : kModes) {
      for (const std::uint32_t fs : spec::sample_rates()) {
        INFO(c.fixture << ", mode " << mode << ", fs " << fs);
        const api::Compiled r = api::compile(text, api::options(mode, fs));
        INFO(api::describe(r.error));
        if (c.accepted) {
          CHECK(r.status == ARC_OK);
          continue;
        }
        CHECK(r.status == ARC_ERR_REJECTED);
        CHECK(r.plan == nullptr);
        REQUIRE(api::all_written(r.error));
        CHECK(std::string(r.error.parameter) == c.parameter);
        CHECK(std::string(r.error.value) == c.value);
        CHECK(std::string(r.error.rule) == c.rule);
        CHECK(std::string(r.error.limit) == c.limit);
      }
    }
    // The fixture as committed has no stored gain: in final mode a loop
    // rule still comes before final.required.
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(c.fixture << " as committed, final mode, fs " << fs);
      const api::Compiled r = api::compile(raw, api::options(ARC_MODE_FINAL, fs));
      INFO(api::describe(r.error));
      REQUIRE(api::all_written(r.error));
      CHECK(r.status == ARC_ERR_REJECTED);
      CHECK(std::string(r.error.rule) == (c.accepted ? std::string("final.required") : std::string(c.rule)));
    }
    ++(c.accepted ? accepted : rejected);
  }
  CHECK(accepted == 3);
  CHECK(rejected == 12);
}

namespace {

// The check_loop result against a compile case (nullptr: expect nothing).
// A template, so the missing function reads as a failed check.
template <class Result>
void check_loop_result(const Result& got, const spec::LoopCompileVector* want) {
  if constexpr (std::is_same_v<Result, LoopCheckMissing>) {
    FAIL("not implemented: validate::check_loop(const recipe::Recipe&) (Story 2.7)");
  } else {
    const bool rejected = want != nullptr && !want->accepted;
    REQUIRE(got.has_value() == rejected);
    if (got.has_value()) {
      CHECK(got->parameter == want->parameter);
      CHECK(got->value == want->value);
      CHECK(got->rule == want->rule);
      CHECK(got->limit == want->limit);
    }
  }
}

}  // namespace

TEST_CASE("loop: check_loop holds the seven rules and finds nothing without loop", "[loop][validate]") {
  for (const auto& c : spec::kLoopCompileCases) {
    INFO(c.fixture);
    const auto parsed = recipe::parse(api::valid(c.fixture));
    REQUIRE(parsed.recipe.has_value());
    check_loop_result(lprobe::run_check_loop(*parsed.recipe), &c);
    // check_ranges runs the loop rules after its field walk.
    const auto ranges = validate::check_ranges(*parsed.recipe);
    REQUIRE(ranges.has_value() == !c.accepted);
    if (ranges.has_value()) {
      CHECK(ranges->parameter == c.parameter);
      CHECK(ranges->value == c.value);
      CHECK(ranges->rule == c.rule);
      CHECK(ranges->limit == c.limit);
    }
  }
  for (const char* name : kEarlierFixtures) {
    INFO(name);
    const auto parsed = recipe::parse(api::valid(name));
    REQUIRE(parsed.recipe.has_value());
    check_loop_result(lprobe::run_check_loop(*parsed.recipe), nullptr);
  }
}

TEST_CASE("loop: the loop rules follow every range check and precede the rules after the ranges",
          "[loop][validate][order]") {
  const std::string learn = "learn";
  const std::string cap_off = num(cap_row(learn).max + 1.0);
  const std::string length_off = num((cap_row(learn).max + 1.0) * 60.0);
  {
    // A theta carrier range fault wins over a cap off its row.
    LoopRecipe r;
    r.cap = cap_off;
    r.length = length_off;
    r.theta_carrier = "50";
    const tables::Row& carrier = spec::row("theta-carrier");
    expect_rejected(make(r), {"/theta_reference/carrier_hz", "50", "range.min",
                              ">= " + num(carrier.min) + " " + carrier.unit + " (row theta-carrier)"});
  }
  {
    // A theta rate cycle worst case (a range check) wins too: 4 + 3 Hz above row theta-rate.
    LoopRecipe r;
    r.cap = cap_off;
    r.length = length_off;
    r.theta_swing = "3";
    const tables::Row& rate = spec::row("theta-rate");
    REQUIRE(4.0 + 3.0 > rate.max);
    REQUIRE(4.0 - 3.0 >= rate.min);
    expect_rejected(make(r), {"/theta_reference/rate_cycle/swing_hz", num(4.0 + 3.0), "range.max",
                              "<= " + num(rate.max) + " " + rate.unit + " (row theta-rate)"});
  }
  {
    // The binaural checks run before the loop rules as well.
    LoopRecipe r;
    r.cap = cap_off;
    r.length = length_off;
    const tables::Row& beat = spec::row("beat-rate");
    REQUIRE(beat.max_bound == "exclusive");
    r.binaural = "\"binaural\": {\"carrier_left_hz\": 100, \"beat_rate_hz\": " + num(beat.max) + "}";
    expect_rejected(make(r), {"/binaural/beat_rate_hz", num(beat.max), "range.max",
                              "< " + num(beat.max) + " " + beat.unit + " (row beat-rate)"});
  }
  {
    // A cap off its row wins over a coupling rule (check_rules runs later).
    LoopRecipe r;
    r.cap = cap_off;
    r.length = length_off;
    r.gamma = "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": 40, \"am_depth_percent\": 100, "
              "\"carrier_wave\": \"sine\", \"coupling\": \"smooth_swell\"}";
    expect_rejected(make(r), cap_error(learn));
  }
  {
    // So does the session-end rule.
    LoopRecipe r;
    r.length = "1100";
    r.gamma = "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": 40, \"am_depth_percent\": 100, "
              "\"carrier_wave\": \"sine\", \"coupling\": \"smooth_swell\"}";
    const double cap = cap_row(learn).max;
    expect_rejected(make(r), {"/length_s", "1100", spec::kLoop_length_rule,
                              "= " + num(cap * 60.0) + " s (" + num(cap) + " min x 60)"});
  }
}

TEST_CASE("loop: inside the loop rules the first failure wins", "[loop][validate][order]") {
  const std::string learn = "learn";
  const double cap = cap_row(learn).max;
  const double length = cap * 60.0;
  {
    // 1 before 2: the cap, then the session end.
    LoopRecipe r;
    r.cap = num(cap + 1.0);
    r.length = "1100";
    expect_rejected(make(r), cap_error(learn));
  }
  {
    // A cap below its row: range.min.
    LoopRecipe r;
    r.cap = num(cap - 1.0);
    r.length = num((cap - 1.0) * 60.0);
    const tables::Row& row = cap_row(learn);
    expect_rejected(make(r), {"/loop/max_run_time_min", num(cap - 1.0), "range.min",
                              ">= " + num(row.min) + " " + row.unit + " (row " + row.id + ")"});
  }
  {
    // A focus cap one minute above its row, with the length at that cap.
    LoopRecipe r;
    r.mode = "focus";
    r.cap = num(cap_row("focus").max + 1.0);
    r.length = num((cap_row("focus").max + 1.0) * 60.0);
    expect_rejected(make(r), cap_error("focus"));
  }
  {
    // 2 before 3.
    LoopRecipe r;
    r.length = "1100";
    r.opening = "-60";
    expect_rejected(make(r), {"/length_s", "1100", spec::kLoop_length_rule,
                              "= " + num(length) + " s (" + num(cap) + " min x 60)"});
  }
  {
    // 3 before 4.
    LoopRecipe r;
    r.opening = "-60";
    r.body = "0";
    expect_rejected(make(r), {"/loop/opening_s", "-60", "range.min", ">= 0 s"});
  }
  {
    LoopRecipe r;
    r.body = "-1";
    expect_rejected(make(r), {"/loop/body_s", "-1", "range.min", "> 0 s"});
  }
  {
    // 5: the opening before the body.
    LoopRecipe r;
    r.opening = "60.1";
    r.body = "120.125";
    expect_rejected(make(r), {"/loop/opening_s", "60.1", spec::kLoop_whole_samples_rule,
                              spec::kLoop_whole_samples_limit});
  }
  {
    // 5 before 6: a body of neither whole samples nor whole cycles names whole samples.
    LoopRecipe r;
    r.body = "90.1";
    expect_rejected(make(r), {"/loop/body_s", "90.1", spec::kLoop_whole_samples_rule,
                              spec::kLoop_whole_samples_limit});
  }
  {
    // 6 before 7: a body off its cycle that would also exceed the session.
    LoopRecipe r;
    r.opening = "1140";
    r.body = "90";
    expect_rejected(make(r), {"/loop/body_s", "90", spec::kLoop_whole_cycles_rule,
                              "a whole multiple of " + period_text() + " s (/theta_reference/rate_cycle/period_s)"});
  }
  {
    // 6 in cycle path order: theta before gamma.
    LoopRecipe r;
    r.body = "90";
    r.gamma = "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": 45, \"am_depth_percent\": 100, "
              "\"carrier_wave\": \"sine\", \"coupling\": \"uncoupled\"}";
    r.gamma_cycle = "\"rate_cycle\": {\"swing_hz\": 15, \"period_s\": " + period_text() + ", \"start_phase_deg\": 0}";
    expect_rejected(make(r), {"/loop/body_s", "90", spec::kLoop_whole_cycles_rule,
                              "a whole multiple of " + period_text() + " s (/theta_reference/rate_cycle/period_s)"});
    r.theta_swing.clear();
    expect_rejected(make(r), {"/loop/body_s", "90", spec::kLoop_whole_cycles_rule,
                              "a whole multiple of " + period_text() + " s (/gamma_pac/rate_cycle/period_s)"});
  }
  {
    // Without a rate cycle there is no cycle rule.
    LoopRecipe r;
    r.theta_swing.clear();
    r.gamma.clear();
    r.body = "90";
    expect_ok(make(r));
  }
  {
    // 7: opening + body equal to the session passes; a quarter second more fails.
    LoopRecipe r;
    r.opening = num(length - 120.0);
    expect_ok(make(r));
    r.opening = num(length - 120.0 + 0.25);
    expect_rejected(make(r), {"/loop/body_s", num(length - 120.0 + 0.25 + 120.0), spec::kLoop_exceeds_rule,
                              "<= " + num(length) + " s (length_s)"});
  }
}

TEST_CASE("loop: the whole-sample rule on every whole-sample vector", "[loop][validate]") {
  // A focus recipe with no rate cycle, so only the whole-sample rule and the
  // session bound judge the times.
  const double length = cap_row("focus").max * 60.0;
  for (const auto& v : spec::kLoopWholeSamples) {
    INFO("t_s " << num(v.t_s));
    LoopRecipe r;
    r.mode = "focus";
    r.theta_swing.clear();
    r.gamma.clear();
    if (v.t_s > 0.0 && v.t_s <= length) {
      r.opening = "0";
      r.body = num(v.t_s);
      if (v.whole) {
        expect_ok(make(r));
      } else {
        expect_rejected(make(r), {"/loop/body_s", num(v.t_s), spec::kLoop_whole_samples_rule,
                                  spec::kLoop_whole_samples_limit});
      }
    }
    if (v.t_s + 0.25 <= length) {
      r.opening = num(v.t_s);
      r.body = "0.25";
      if (v.whole) {
        expect_ok(make(r));
      } else {
        expect_rejected(make(r), {"/loop/opening_s", num(v.t_s), spec::kLoop_whole_samples_rule,
                                  spec::kLoop_whole_samples_limit});
      }
    }
  }
}

// ------------------------------------------------------------ plan and C API

TEST_CASE("loop: arc_loop_frames has the C layout of the contract", "[loop][api]") { check_frames_layout(); }

TEST_CASE("loop: arc_plan_loop gives the opening end, body, seams, and end of every loop frame vector",
          "[loop][api]") {
  for (const auto& v : spec::kLoopFrames) {
    const std::string raw = api::valid(v.fixture);
    for (const arc_mode mode : kModes) {
      INFO(v.fixture << " at " << v.fs << ", mode " << mode);
      // Final mode needs the stored gain, which the fixtures leave to Epic 4.
      const std::string text = mode == ARC_MODE_FINAL ? with_gain(raw) : raw;
      auto p = api::compile_ok(text, api::options(mode, v.fs));
      CHECK(arc_plan_frame_count(p.get()) == v.end_frame);
      const LoopInfo info = plan_loop(p.get());
      INFO(api::describe(info.error));
      CHECK(info.status == ARC_OK);
      CHECK(info.looping == 1);
      CHECK(info.opening_end_frame == v.opening_end_frame);
      CHECK(info.body_frames == v.body_frames);
      CHECK(info.seam_count == v.seam_count);
      CHECK(info.end_frame == v.end_frame);
      // Seam k is O + k * B, each below the end.
      for (std::uint64_t k = 1; k <= info.seam_count && k <= spec::kLoopMaxSeams; ++k) {
        CHECK(info.opening_end_frame + k * info.body_frames == v.seams[k - 1]);
      }
      CHECK(info.opening_end_frame + (info.seam_count + 1) * info.body_frames >= info.end_frame);
    }
  }
}

TEST_CASE("loop: the plan holds the loop frames; none without loop", "[loop][plan]") {
  for (const auto& v : spec::kLoopFrames) {
    INFO(v.fixture << " at " << v.fs);
    const PlanLoop p = plan_member(api::valid(v.fixture), v.fs);
    CHECK(p.present);
    CHECK(p.opening_end_frame == v.opening_end_frame);
    CHECK(p.body_frames == v.body_frames);
    CHECK(p.seam_count == v.seam_count);
    CHECK(p.frame_count == v.end_frame);
  }
  for (const char* name : kEarlierFixtures) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(name << " at " << fs);
      const PlanLoop p = plan_member(api::valid(name), fs);
      CHECK_FALSE(p.present);
      CHECK(p.opening_end_frame == 0);
      CHECK(p.body_frames == 0);
      CHECK(p.seam_count == 0);
    }
  }
}

TEST_CASE("loop: a plan without loop gives looping 0 and every field 0", "[loop][api]") {
  for (const char* name : kEarlierFixtures) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(name << " at " << fs);
      auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
      const LoopInfo info = plan_loop(p.get());
      INFO(api::describe(info.error));
      CHECK(info.status == ARC_OK);
      CHECK(info.looping == 0);
      CHECK(info.opening_end_frame == 0);
      CHECK(info.body_frames == 0);
      CHECK(info.seam_count == 0);
      CHECK(info.end_frame == 0);
    }
  }
}

TEST_CASE("loop: arc_plan_loop refuses a NULL plan or output", "[loop][api]") {
  auto p = api::compile_ok(api::valid(spec::kLoop_full_render_fixture), api::options(ARC_MODE_MEASURE, 48000));
  check_null_arguments(p.get());
}

TEST_CASE("loop: seams stop before the end; a seam at the end is the end", "[loop][api]") {
  const double length = cap_row("learn").max * 60.0;
  struct Case {
    double opening, body;
  };
  // A body that divides the session exactly from frame 0, the opening and
  // body filling the session (no seam), and an opening of a quarter second.
  const Case cases[] = {{0.0, 120.0}, {length - 120.0, 120.0}, {0.25, 120.0}};
  for (const auto& c : cases) {
    LoopRecipe r;
    r.opening = num(c.opening);
    r.body = num(c.body);
    const std::string text = make(r);
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(text << "\nfs " << fs);
      const std::uint64_t o = core::seconds_to_samples(c.opening, fs);
      const std::uint64_t b = core::seconds_to_samples(c.body, fs);
      const std::uint64_t n = core::seconds_to_samples(length, fs);
      std::uint64_t seams = 0;
      while (o + (seams + 1) * b < n) {
        ++seams;
      }
      auto p = api::compile_ok(text, api::options(ARC_MODE_MEASURE, fs));
      const LoopInfo info = plan_loop(p.get());
      CHECK(info.status == ARC_OK);
      CHECK(info.looping == 1);
      CHECK(info.opening_end_frame == o);
      CHECK(info.body_frames == b);
      CHECK(info.seam_count == seams);
      CHECK(info.seam_count == (n - o - 1) / b);
      CHECK(info.end_frame == n);
    }
  }
}

// ------------------------------------------------------------ renders

TEST_CASE("loop: a looping recipe renders byte for byte what the same recipe without loop renders",
          "[loop][render]") {
  for (const auto& v : spec::kLoopFrames) {
    const std::string text = api::valid(v.fixture);
    const std::string plain = without_loop(text);
    INFO(v.fixture << " at " << v.fs);
    auto looping = api::compile_ok(text, api::options(ARC_MODE_MEASURE, v.fs));
    auto unlooped = api::compile_ok(plain, api::options(ARC_MODE_MEASURE, v.fs));
    REQUIRE(arc_plan_frame_count(looping.get()) == v.end_frame);
    REQUIRE(arc_plan_frame_count(unlooped.get()) == v.end_frame);
    const std::uint64_t half = v.fs / 2;
    // Windows around the join, the first seam, the last seam, and the end.
    std::vector<std::uint64_t> centers;
    if (v.opening_end_frame > 0) {
      centers.push_back(v.opening_end_frame);
    }
    if (v.seam_count > 0) {
      centers.push_back(v.seams[0]);
      centers.push_back(v.seams[v.seam_count - 1]);
    }
    for (const std::uint64_t c : centers) {
      INFO("window around frame " << c);
      const Window a = render_window(looping.get(), c - half, static_cast<std::size_t>(2 * half));
      const Window b = render_window(unlooped.get(), c - half, static_cast<std::size_t>(2 * half));
      CHECK(same_window(a, b));
    }
    // The end: half a second before it, then 64 frames past it, all +0.0.
    const std::size_t frames = static_cast<std::size_t>(half + 64);
    const Window a = render_window(looping.get(), v.end_frame - half, frames);
    const Window b = render_window(unlooped.get(), v.end_frame - half, frames);
    CHECK(same_window(a, b));
    CHECK(silent_from(a, static_cast<std::size_t>(half)));
    CHECK_FALSE(api::all_exact_zero(a.out.data(), static_cast<std::size_t>(2 * half)));
  }
}

#else

TEST_CASE("looping body and seams are implemented", "[loop]") {
  FAIL("not implemented: plan/plan.hpp, validate/validate.hpp, or the Story 1.2 C API");
}

#endif
