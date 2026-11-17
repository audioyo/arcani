// Rate curves on the theta and gamma rates (Story 2.6; docs/signal-spec.md,
// Rate curve, Theta reference, Gamma PAC layer, Coupling, and Bursts).
//
// The Story 2.5 law, integral, cycle cosine, and cycles-to-units rule,
// unchanged, now curve the theta envelope phase and the gamma envelope phase
// through an optional rate_cycle on each layer:
//
//   P0 = coupling phase rule (start_phase_deg),  inc_P = inc(1.0 / period_s)
//   K = (swing_hz * period_s) * kInvTwoPi,  c0 = cycle_cosine(P0)
//   p_P[n] = P0 + n * inc_P,  U[n] = rate_cycle_offset(p_P[n], K, c0)
//   phase_E[n] = n * inc_E + U_E[n] mod 2^64     theta envelope phase
//   phase_M[n] = n * inc_M + U_M[n] mod 2^64     gamma envelope phase
//
// The carriers phase_T and phase_G take no U. The theta envelope, the smooth
// swell, and the burst gate read the curved phase_E; W, Hb, and Wb stay set at
// the center rate_hz. Without a cycle a layer is bit for bit what it was.
//
// Expected interface (spec Implementation Notes):
//
//   engine/src/core/rate_cycle.hpp, namespace arcani::core: kInvTwoPi,
//   cycles_to_units, cycle_cosine, and rate_cycle_offset, moved unchanged
//   from core/envelope.hpp, which no longer declares them (checked below by a
//   lookup probe on core/envelope.hpp alone, so it must not pull them in).
//
//   plan::ThetaOscillator and plan::GammaOscillator each gain
//     bool cycle = false;
//     std::uint64_t cycle_start = 0;      // P0
//     std::uint64_t cycle_increment = 0;  // inc_P
//     double cycle_k = 0.0;               // K
//     double cycle_c0 = 0.0;              // c0 = cycle_cosine(cycle_start)
//   all zero without a rate_cycle; a muted ear changes none of them.
//
// The plan members are read through a requires-expression, so the missing
// pieces show as failing test cases. Every render check reaches the engine
// through the public C API. Vectors come from the generated spec_tables.hpp
// (kLayerRateCycles, kRateCurveSamples, kCyclesToUnits, kCycleCosines,
// kRateCycles, kInvTwoPi, kSeekSeconds); rows from the tables through the
// assertion call (theta-rate, gamma-rate, block-sizes, block-size-invariance,
// sample-rates).
//
// Fixtures (recipes/fixtures/valid/, 120 s, no binaural layer):
// theta-cycle-sine.json and theta-cycle-smoothed-on-off.json (a 450 Hz
// carrier amplitude-modulated by the sine or smoothed on-off envelope at a
// theta rate that cycles over 1 to 6 Hz every 60 s, 3.5 +- 2.5 Hz from the
// center rising, 75 percent depth); gamma-cycle-uncoupled.json (a 250 Hz sine
// carrier amplitude-modulated at a gamma rate that cycles over 30 to 60 Hz
// every 60 s, 45 +- 15 Hz, 100 percent depth); swell-theta-cycle.json and
// bursts-theta-cycle.json (a 450 Hz carrier amplitude-modulated by the sine
// envelope at a theta rate of 4 +- 2 Hz, 75 percent depth, and a 250 Hz sine
// carrier amplitude-modulated at 40 Hz with a smooth swell or 50 ms bursts at
// 0 degrees, 100 percent depth); gamma-cycle-swell-theta-cycle.json (the
// swell fixture with the gamma rate also cycling, 45 +- 15 Hz).

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#if __has_include("core/rate_cycle.hpp") && __has_include("core/envelope.hpp") && \
    __has_include("plan/plan.hpp") && defined(ARC_ERROR_FIELD_BYTES)

#include <type_traits>

// core/envelope.hpp alone, before anything else that could declare the
// moved names.
#include "core/envelope.hpp"

// ------------------------------------------------------------ lookup probe
//
// Inside arcani::rate_curves_envelope_probe the using-directive for
// arcani::core makes its names visible as members of arcani, found before
// these fallbacks (visible as members of the global namespace). A name that
// core/envelope.hpp still declares hides its fallback.

namespace rate_curves_fallback {
struct Missing {};
inline constexpr Missing cycles_to_units{};
inline constexpr Missing cycle_cosine{};
inline constexpr Missing rate_cycle_offset{};
inline constexpr Missing kInvTwoPi{};
}  // namespace rate_curves_fallback

namespace arcani::rate_curves_envelope_probe {
using namespace ::rate_curves_fallback;
using namespace arcani::core;
template <class T>
inline constexpr bool kMissing = std::is_same_v<std::remove_cvref_t<T>, ::rate_curves_fallback::Missing>;
inline constexpr bool kEnvelopeDeclaresUnits = !kMissing<decltype(cycles_to_units)>;
inline constexpr bool kEnvelopeDeclaresCosine = !kMissing<decltype(cycle_cosine)>;
inline constexpr bool kEnvelopeDeclaresOffset = !kMissing<decltype(rate_cycle_offset)>;
inline constexpr bool kEnvelopeDeclaresInvTwoPi = !kMissing<decltype(kInvTwoPi)>;
}  // namespace arcani::rate_curves_envelope_probe

#include "core/rate_cycle.hpp"

#include "api_helpers.hpp"
#include "core/phase.hpp"
#include "core/sine.hpp"
#include "plan/plan.hpp"
#include "spec_helpers.hpp"

#include <algorithm>
#include <cmath>
#include <concepts>
#include <cstdint>
#include <cstring>
#include <initializer_list>
#include <limits>
#include <map>
#include <set>
#include <string>
#include <string_view>
#include <tuple>
#include <utility>
#include <vector>

namespace api = arcani::test::api;
namespace core = arcani::core;
namespace plan = arcani::plan;
namespace spec = arcani::test::spec;
namespace envprobe = arcani::rate_curves_envelope_probe;

// AD-5 structural: the moved functions keep their exact Story 2.5 types, so
// the offset's only signal input is the cycle phase (K and c0 are plan
// constants).
static_assert(std::is_same_v<decltype(&core::cycles_to_units), std::uint64_t (*)(double) noexcept>,
              "arcani::core::cycles_to_units must be exactly std::uint64_t(double) noexcept");
static_assert(std::is_same_v<decltype(&core::cycle_cosine), double (*)(std::uint64_t) noexcept>,
              "arcani::core::cycle_cosine must be exactly double(std::uint64_t) noexcept");
static_assert(std::is_same_v<decltype(&core::rate_cycle_offset),
                             std::uint64_t (*)(std::uint64_t, double, double) noexcept>,
              "arcani::core::rate_cycle_offset must be exactly std::uint64_t(std::uint64_t, double, double) "
              "noexcept");
static_assert(std::is_same_v<std::remove_cvref_t<decltype(core::kInvTwoPi)>, double>,
              "arcani::core::kInvTwoPi must be a double constant");

namespace {

constexpr std::uint64_t kNegativeZero = UINT64_C(0x8000000000000000);

const char* const kCurvedFixtures[] = {"theta-cycle-sine.json",  "theta-cycle-smoothed-on-off.json",
                                       "gamma-cycle-uncoupled.json", "swell-theta-cycle.json",
                                       "bursts-theta-cycle.json", "gamma-cycle-swell-theta-cycle.json"};

// Fixtures written before Story 2.6, one per layer kind: none has a rate_cycle.
const char* const kEarlierFixtures[] = {"theta-sine-6hz.json",        "theta-smoothed-on-off-1hz.json",
                                        "gamma-uncoupled-40hz-25pct.json", "theta-gamma-uncoupled.json",
                                        "swell-sine-0deg-100pct.json", "bursts-40hz.json",
                                        "binaural-cycle-sleep.json",  "both-layers.json"};

double from_bits(std::uint64_t b) {
  double x = 0.0;
  std::memcpy(&x, &b, sizeof x);
  return x;
}

// ------------------------------------------------------------ plan members

template <class O>
concept OscillatorHasCycle = requires(const O& o) {
  { o.cycle } -> std::convertible_to<bool>;
  { o.cycle_start } -> std::convertible_to<std::uint64_t>;
  { o.cycle_increment } -> std::convertible_to<std::uint64_t>;
  { o.cycle_k } -> std::convertible_to<double>;
  { o.cycle_c0 } -> std::convertible_to<double>;
};

struct CycleConstants {
  bool cycle = false;
  std::uint64_t start = 0;
  std::uint64_t increment = 0;
  std::uint64_t k_bits = 0;
  std::uint64_t c0_bits = 0;
};

// The plan's cycle constants of one oscillator, or a failed check when it
// does not have them yet.
template <class O>
CycleConstants cycle_of(const O& o, const char* which) {
  CycleConstants c;
  if constexpr (OscillatorHasCycle<O>) {
    c.cycle = static_cast<bool>(o.cycle);
    c.start = static_cast<std::uint64_t>(o.cycle_start);
    c.increment = static_cast<std::uint64_t>(o.cycle_increment);
    c.k_bits = api::bits(static_cast<double>(o.cycle_k));
    c.c0_bits = api::bits(static_cast<double>(o.cycle_c0));
  } else {
    FAIL("not implemented: plan::" << which
                                   << " has no cycle, cycle_start, cycle_increment, cycle_k, cycle_c0 (Story 2.6)");
  }
  return c;
}

bool all_zero(const CycleConstants& c) {
  return !c.cycle && c.start == 0 && c.increment == 0 && c.k_bits == 0 && c.c0_bits == 0;
}

plan::Plan compile_plan(const std::string& text, std::uint32_t fs, plan::MuteEar mute = plan::MuteEar::None) {
  auto r = plan::compile(text, plan::Mode::Measure, fs, mute);
  INFO("rule '" << r.error.rule << "', parameter '" << r.error.parameter << "', value '" << r.error.value
                << "', limit '" << r.error.limit << "'");
  REQUIRE(r.plan.has_value());
  return std::move(*r.plan);
}

// The U of one oscillator at sample n by the plan's own constants (0 without
// a cycle): the Story 2.5 offset of the cycle phase P0 + n * inc_P.
template <class O>
std::uint64_t plan_offset(const O& o, std::uint64_t n) {
  if constexpr (OscillatorHasCycle<O>) {
    if (!o.cycle) {
      return 0;
    }
    return core::rate_cycle_offset(o.cycle_start + n * o.cycle_increment, o.cycle_k, o.cycle_c0);
  } else {
    return 0;
  }
}

// ------------------------------------------------------------ the law

// The theta tap at sample n by the spec's operations from the plan constants.
double theta_law(const plan::ThetaOscillator& t, std::uint64_t n) {
  if (!t.present) {
    return 0.0;
  }
  const std::uint64_t phase_e = n * t.envelope_increment + plan_offset(t, n);
  const double e = core::envelope(t.shape, phase_e, t.edge_units, t.half_on_units);
  const double a = 1.0 - t.depth * (1.0 - e);
  return a * core::sine(n * t.increment);
}

// The gamma tap at sample n: its own curved envelope phase, and the coupled
// factor of the curved theta envelope phase.
double gamma_law(const plan::GammaOscillator& g, const plan::ThetaOscillator& t, std::uint64_t n) {
  if (!g.present) {
    return 0.0;
  }
  const std::uint64_t phase_m = n * g.envelope_increment + plan_offset(g, n);
  const double e = core::sine_envelope(phase_m);
  double a = 0.0;
  if (g.coupling == arcani::recipe::GammaCoupling::Uncoupled) {
    a = 1.0 - g.depth * (1.0 - e);
  } else {
    const std::uint64_t phase_e = n * t.envelope_increment + plan_offset(t, n);
    const double f = g.coupling == arcani::recipe::GammaCoupling::SmoothSwell
                         ? core::swell(phase_e, g.coupling_phase_units)
                         : core::burst(phase_e, g.coupling_phase_units, g.burst_half_width_units,
                                       g.burst_edge_units);
    const double df = g.depth * f;
    const double one_minus_e = 1.0 - e;
    a = 1.0 - df * one_minus_e;
  }
  return a * core::sine(n * g.increment);
}

// ------------------------------------------------------------ vectors

std::vector<std::pair<std::string, std::uint32_t>> sample_fixture_rates() {
  std::vector<std::pair<std::string, std::uint32_t>> out;
  for (const auto& v : spec::kRateCurveSamples) {
    const std::pair<std::string, std::uint32_t> key{v.fixture, v.fs};
    if (std::find(out.begin(), out.end(), key) == out.end()) {
      out.push_back(key);
    }
  }
  return out;
}

const spec::RateCurveSampleVector& first_sample(const std::string& name, std::uint32_t fs) {
  for (const auto& v : spec::kRateCurveSamples) {
    if (name == v.fixture && fs == v.fs) {
      return v;
    }
  }
  FAIL("no rate curve sample vector for " << name << " at " << fs);
  return spec::kRateCurveSamples[0];
}

const spec::LayerRateCycleVector* layer_cycle(const std::string& name, const std::string& layer, std::uint32_t fs) {
  for (const auto& r : spec::kLayerRateCycles) {
    if (name == r.fixture && layer == r.layer && fs == r.fs) {
      return &r;
    }
  }
  return nullptr;
}

std::uint64_t last_index(const std::string& name, std::uint32_t fs) {
  std::uint64_t last = 0;
  for (const auto& v : spec::kRateCurveSamples) {
    if (name == v.fixture && fs == v.fs) {
      last = std::max(last, v.n);
    }
  }
  return last;
}

// ------------------------------------------------------------ recipes

std::string recipe_text(std::initializer_list<std::string> members, const std::string& length = "3") {
  std::string s =
      "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
      "\"author\": \"Arcani test\", \"date\": \"2026-11-14\", "
      "\"rationale\": \"Rate curve test, made in the test.\", "
      "\"length_s\": " + length + ", \"loudness_target_lufs\": -36";
  for (const auto& m : members) {
    if (!m.empty()) {
      s += ", " + m;
    }
  }
  return s + "}";
}

// A rate_cycle member, appended last inside a layer.
std::string cycle_member(const std::string& swing, const std::string& phase = "0", const std::string& period = "60") {
  return ", \"rate_cycle\": {\"swing_hz\": " + swing + ", \"period_s\": " + period +
         ", \"start_phase_deg\": " + phase + "}";
}

// A carrier amplitude-modulated at `rate` Hz by `shape`, with an optional
// rate_cycle after shape.
std::string theta_member(const std::string& rate, const std::string& cycle = "", const std::string& shape = "sine",
                         const std::string& carrier = "450", const std::string& depth = "75") {
  return "\"theta_reference\": {\"carrier_hz\": " + carrier + ", \"rate_hz\": " + rate +
         ", \"am_depth_percent\": " + depth + ", \"shape\": \"" + shape + "\"" + cycle + "}";
}

// A 250 Hz sine carrier amplitude-modulated at `rate` Hz, 100 percent depth,
// coupled at 0 degrees unless uncoupled, with an optional rate_cycle after the
// coupling phase.
std::string gamma_member(const std::string& coupling, const std::string& rate = "40", const std::string& cycle = "") {
  std::string s = "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": " + rate +
                  ", \"am_depth_percent\": 100, \"carrier_wave\": \"sine\", \"coupling\": \"" + coupling + "\"";
  if (coupling != "uncoupled") {
    s += ", \"coupling_phase_deg\": 0";
  }
  return s + cycle + "}";
}

// ------------------------------------------------------------ renders

struct Rendered {
  std::uint64_t frames = 0;
  std::vector<double> out;
  api::TapBuffers taps{0};
};

Rendered render_text(const std::string& text, std::uint32_t fs, arc_mute_ear mute = ARC_MUTE_NONE) {
  auto p = api::compile_ok(text, api::options(ARC_MODE_MEASURE, fs, mute));
  Rendered r;
  r.frames = arc_plan_frame_count(p.get());
  const auto total = static_cast<std::size_t>(r.frames);
  r.taps = api::TapBuffers(total);
  auto renderer = api::renderer(p.get());
  arc_taps t = r.taps.taps();
  r.out = api::render(renderer.get(), total, &t);
  return r;
}

// Renders `total` frames continuously in chunks into reused buffers and calls
// visit(start, count, out, taps) for each chunk.
template <class Visit>
void render_chunks(arc_renderer* renderer, std::uint64_t total, Visit visit) {
  constexpr std::size_t kChunk = 65536;
  api::TapBuffers taps(kChunk);
  for (std::uint64_t start = 0; start < total;) {
    const auto count = static_cast<std::size_t>(std::min<std::uint64_t>(kChunk, total - start));
    arc_taps t = taps.taps();
    const auto out = api::render(renderer, count, &t);
    visit(start, count, out, taps);
    start += count;
  }
}

Rendered render_in_blocks(const std::string& text, std::uint32_t fs, std::size_t block) {
  auto p = api::compile_ok(text, api::options(ARC_MODE_MEASURE, fs));
  Rendered r;
  r.frames = arc_plan_frame_count(p.get());
  const auto frames = static_cast<std::size_t>(r.frames);
  r.taps = api::TapBuffers(frames);
  r.out.assign(2 * frames, -7.0);
  auto renderer = api::renderer(p.get());
  for (std::size_t done = 0; done < frames;) {
    const std::size_t n = std::min(block, frames - done);
    arc_taps t = r.taps.taps();
    const std::size_t at = 2 * done;
    t.theta_reference += at;
    t.gamma_pac += at;
    t.stereo_bus += at;
    t.binaural_join += at;
    t.master += at;
    arc_error e;
    api::poison(e);
    const arc_status s = arc_render(renderer.get(), r.out.data() + at, n, &t, &e);
    INFO(api::describe(e));
    REQUIRE(s == ARC_OK);
    done += n;
  }
  return r;
}

std::size_t differing_bytes(const std::vector<double>& a, const std::vector<double>& b) {
  if (a.size() != b.size()) {
    return std::max(a.size(), b.size()) * sizeof(double);
  }
  const auto* x = reinterpret_cast<const unsigned char*>(a.data());
  const auto* y = reinterpret_cast<const unsigned char*>(b.data());
  std::size_t n = 0;
  for (std::size_t i = 0; i < a.size() * sizeof(double); ++i) {
    n += x[i] != y[i] ? 1 : 0;
  }
  return n;
}

bool all_taps_same(const Rendered& a, const Rendered& b) {
  return api::same_bytes(a.out, b.out) && api::same_bytes(a.taps.theta_reference, b.taps.theta_reference) &&
         api::same_bytes(a.taps.gamma_pac, b.taps.gamma_pac) && api::same_bytes(a.taps.stereo_bus, b.taps.stereo_bus) &&
         api::same_bytes(a.taps.master, b.taps.master);
}

}  // namespace

// ------------------------------------------------------------ the code move

TEST_CASE("rate curves: core/rate_cycle.hpp holds the moved cycle functions; core/envelope.hpp no longer does",
          "[rate-curves][ad5]") {
  // The static_asserts above pin the types from core/rate_cycle.hpp.
  CHECK_FALSE(envprobe::kEnvelopeDeclaresUnits);
  CHECK_FALSE(envprobe::kEnvelopeDeclaresCosine);
  CHECK_FALSE(envprobe::kEnvelopeDeclaresOffset);
  CHECK_FALSE(envprobe::kEnvelopeDeclaresInvTwoPi);
  CHECK(api::bits(core::kInvTwoPi) == api::bits(spec::kInvTwoPi));
}

TEST_CASE("rate curves: the moved functions are unchanged on every Story 2.5 vector", "[rate-curves][vectors]") {
  for (const auto& v : spec::kCyclesToUnits) {
    INFO(v.label);
    CHECK(core::cycles_to_units(v.v) == v.units);
  }
  for (const auto& v : spec::kCycleCosines) {
    INFO(v.label);
    CHECK(api::bits(core::cycle_cosine(v.phase)) == v.bits);
  }
  for (const auto& r : spec::kRateCycles) {
    INFO("start phase " << r.start_phase_deg << " at " << r.fs);
    CHECK(api::bits(core::cycle_cosine(r.p0)) == r.c0_bits);
    CHECK(core::rate_cycle_offset(r.p0, r.k, from_bits(r.c0_bits)) == 0);
  }
}

// ------------------------------------------------------------ cycle vectors

TEST_CASE("rate curves: the layer rate cycle vectors follow the once-per-plan constants",
          "[rate-curves][vectors]") {
  std::set<std::tuple<std::string, std::string, std::uint32_t>> seen;
  for (const auto& r : spec::kLayerRateCycles) {
    INFO(r.fixture << " " << r.layer << " at " << r.fs);
    seen.insert({r.fixture, r.layer, r.fs});
    const std::string layer = r.layer;
    REQUIRE((layer == "theta" || layer == "gamma"));
    CHECK(r.center_hz - r.swing_hz == r.lowest_hz);
    CHECK(r.center_hz + r.swing_hz == r.highest_hz);
    // Every Story 2.6 cycle lies inside its layer's locked rate range.
    const auto& rate_row = spec::row(layer == "theta" ? "theta-rate" : "gamma-rate");
    CHECK(r.lowest_hz >= rate_row.min);
    CHECK(r.highest_hz <= rate_row.max);
    CHECK(r.swing_hz >= 0.0);
    CHECK(r.period_s == 60.0);
    CHECK(r.start_phase_deg == 0.0);
    CHECK(r.inc_rate == core::phase_increment(r.center_hz, r.fs));
    CHECK(r.p0 == core::coupling_phase_units(r.start_phase_deg));
    CHECK(1.0 / r.period_s == r.inv_period);
    CHECK(r.inc_cycle == core::phase_increment(r.inv_period, r.fs));
    CHECK(r.swing_hz * r.period_s == r.swing_period);
    CHECK(api::bits(r.swing_period * spec::kInvTwoPi) == api::bits(r.k));
    CHECK(api::bits(core::cycle_cosine(r.p0)) == r.c0_bits);
    CHECK(r.frames == core::seconds_to_samples(120.0, r.fs));
  }
  // Six fixtures, seven curved layers, two sample rates.
  CHECK(seen.size() == 14);
}

TEST_CASE("rate curves: the plan holds each curved layer's cycle constants and none for the others",
          "[rate-curves][plan]") {
  for (const char* name : kCurvedFixtures) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(name << " at " << fs);
      const plan::Plan p = compile_plan(api::valid(name), fs);
      const auto* theta_row = layer_cycle(name, "theta", fs);
      const auto* gamma_row = layer_cycle(name, "gamma", fs);
      const CycleConstants t = cycle_of(p.theta, "ThetaOscillator");
      const CycleConstants g = cycle_of(p.gamma, "GammaOscillator");
      if (theta_row != nullptr) {
        CHECK(p.theta.present);
        CHECK(p.frame_count == theta_row->frames);
        CHECK(t.cycle);
        CHECK(t.start == theta_row->p0);
        CHECK(t.increment == theta_row->inc_cycle);
        CHECK(t.k_bits == api::bits(theta_row->k));
        CHECK(t.c0_bits == theta_row->c0_bits);
        CHECK(p.theta.envelope_increment == theta_row->inc_rate);
      } else {
        CHECK(all_zero(t));
      }
      if (gamma_row != nullptr) {
        CHECK(p.gamma.present);
        CHECK(p.frame_count == gamma_row->frames);
        CHECK(g.cycle);
        CHECK(g.start == gamma_row->p0);
        CHECK(g.increment == gamma_row->inc_cycle);
        CHECK(g.k_bits == api::bits(gamma_row->k));
        CHECK(g.c0_bits == gamma_row->c0_bits);
        CHECK(p.gamma.envelope_increment == gamma_row->inc_rate);
      } else {
        CHECK(all_zero(g));
      }
      // No binaural layer in any rate-curve fixture.
      CHECK(p.binaural.increment[0] == 0);
      CHECK(p.binaural.increment[1] == 0);
    }
  }
}

TEST_CASE("rate curves: no earlier fixture has a theta or gamma cycle", "[rate-curves][plan][regression]") {
  for (const char* name : kEarlierFixtures) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(name << " at " << fs);
      const plan::Plan p = compile_plan(api::valid(name), fs);
      CHECK(all_zero(cycle_of(p.theta, "ThetaOscillator")));
      CHECK(all_zero(cycle_of(p.gamma, "GammaOscillator")));
    }
  }
}

TEST_CASE("rate curves: W, Hb, and Wb stay set at the center theta rate", "[rate-curves][plan]") {
  for (const auto& [name, fs] : sample_fixture_rates()) {
    INFO(name << " at " << fs);
    const auto& v = first_sample(name, fs);
    const plan::Plan p = compile_plan(api::valid(name), fs);
    if (!v.has_theta) {
      CHECK_FALSE(p.theta.present);
      continue;
    }
    const auto* theta_row = layer_cycle(name, "theta", fs);
    REQUIRE(theta_row != nullptr);
    const double center = theta_row->center_hz;
    CHECK(p.theta.edge_units == v.w_units);
    CHECK(v.w_units == core::theta_edge_units(center));
    // Not at either end of the cycle.
    CHECK(v.w_units != core::theta_edge_units(theta_row->lowest_hz));
    CHECK(v.w_units != core::theta_edge_units(theta_row->highest_hz));
    if (std::string_view(v.coupling) == "bursts") {
      CHECK(p.gamma.burst_half_width_units == v.hb_units);
      CHECK(p.gamma.burst_edge_units == v.wb_units);
      CHECK(v.hb_units == core::burst_half_width_units(center));
      CHECK(v.wb_units == core::burst_edge_units(center));
    }
    if (v.has_gamma && std::string_view(v.coupling) != "uncoupled") {
      CHECK(p.gamma.coupling_phase_units == v.c_units);
    }
  }
}

TEST_CASE("rate curves: a muted ear leaves the theta and gamma cycles", "[rate-curves][plan][isolation]") {
  // Story 3.2: the binaural pair is 100 and 106 Hz (it was 400 and 406 Hz,
  // 38 Hz from the 444 Hz theta line), 50 Hz from every other layer's line.
  const std::string text =
      recipe_text({theta_member("4", cycle_member("2")), gamma_member("smooth_swell", "45", cycle_member("15")),
                   "\"binaural\": {\"carrier_left_hz\": 100, \"beat_rate_hz\": 6}"});
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const plan::Plan both = compile_plan(text, fs);
    const CycleConstants t = cycle_of(both.theta, "ThetaOscillator");
    const CycleConstants g = cycle_of(both.gamma, "GammaOscillator");
    CHECK(t.cycle);
    CHECK(g.cycle);
    for (const plan::MuteEar mute : {plan::MuteEar::Left, plan::MuteEar::Right}) {
      const plan::Plan m = compile_plan(text, fs, mute);
      const CycleConstants mt = cycle_of(m.theta, "ThetaOscillator");
      const CycleConstants mg = cycle_of(m.gamma, "GammaOscillator");
      CHECK(std::tie(mt.cycle, mt.start, mt.increment, mt.k_bits, mt.c0_bits) ==
            std::tie(t.cycle, t.start, t.increment, t.k_bits, t.c0_bits));
      CHECK(std::tie(mg.cycle, mg.start, mg.increment, mg.k_bits, mg.c0_bits) ==
            std::tie(g.cycle, g.start, g.increment, g.k_bits, g.c0_bits));
    }
  }
}

// ------------------------------------------------------------ sample vectors

TEST_CASE("rate curves: sample vector rows follow the spec's operations", "[rate-curves][vectors]") {
  std::map<std::pair<std::string, std::uint32_t>, plan::Plan> plans;
  std::set<std::pair<std::string, std::uint32_t>> signal, past;
  for (const auto& v : spec::kRateCurveSamples) {
    INFO(v.fixture << " at " << v.fs << ", n " << v.n);
    const std::pair<std::string, std::uint32_t> key{v.fixture, v.fs};
    (v.past_end ? past : signal).insert(key);
    CHECK(v.past_end == (v.n >= v.frames));
    CHECK(v.phase_theta == v.n * v.inc_theta);
    CHECK(v.phase_gamma == v.n * v.inc_gamma);
    if (v.theta_cycle) {
      CHECK(v.theta_cycle_phase == v.theta_p0 + v.n * v.theta_inc_cycle);
      const double c0 = core::cycle_cosine(v.theta_p0);
      CHECK(core::rate_cycle_offset(v.theta_cycle_phase, v.theta_k, c0) == v.theta_u);
    } else {
      CHECK(v.theta_u == 0);
    }
    if (v.gamma_cycle) {
      CHECK(v.gamma_cycle_phase == v.gamma_p0 + v.n * v.gamma_inc_cycle);
      const double c0 = core::cycle_cosine(v.gamma_p0);
      CHECK(core::rate_cycle_offset(v.gamma_cycle_phase, v.gamma_k, c0) == v.gamma_u);
    } else {
      CHECK(v.gamma_u == 0);
    }
    CHECK(v.phase_theta_envelope == v.n * v.inc_theta_envelope + v.theta_u);
    CHECK(v.phase_gamma_envelope == v.n * v.inc_gamma_envelope + v.gamma_u);
    if (v.n == 0) {
      CHECK(v.theta_u == 0);  // sample 0 stays the 0 degree point
      CHECK(v.gamma_u == 0);
    }
    const std::string coupling = v.coupling;
    if (v.has_factor && !v.past_end) {
      const double f = coupling == "smooth_swell"
                           ? core::swell(v.phase_theta_envelope, v.c_units)
                           : core::burst(v.phase_theta_envelope, v.c_units, v.hb_units, v.wb_units);
      CHECK(api::bits(f) == v.factor_bits);
    }
    if (v.past_end) {
      CHECK(v.theta_bits == 0);
      CHECK(v.gamma_bits == 0);
      CHECK(v.bus_bits == 0);
      continue;
    }
    // The tap bits are the law of the plan constants at n.
    auto it = plans.find(key);
    if (it == plans.end()) {
      it = plans.emplace(key, compile_plan(api::valid(v.fixture), v.fs)).first;
    }
    const plan::Plan& p = it->second;
    const double theta = theta_law(p.theta, v.n);
    const double gamma = gamma_law(p.gamma, p.theta, v.n);
    CHECK(api::bits(theta) == v.theta_bits);
    CHECK(api::bits(gamma) == v.gamma_bits);
    CHECK(api::bits(theta + gamma) == v.bus_bits);
  }
  CHECK(signal.size() == 12);  // six fixtures at two sample rates
  CHECK(past == signal);
}

// ------------------------------------------------------------ renders

TEST_CASE("rate curves: fixtures render the vector bits through the C API, +0.0 past the end",
          "[rate-curves][render]") {
  const auto pairs = sample_fixture_rates();
  REQUIRE(pairs.size() == 12);
  for (const auto& [name, fs] : pairs) {
    INFO(name << " at " << fs);
    const auto& first = first_sample(name, fs);
    auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
    REQUIRE(arc_plan_frame_count(p.get()) == first.frames);
    std::size_t rows = 0;
    const std::string fixture_name = name;
    const std::uint32_t rate = fs;
    auto renderer = api::renderer(p.get());
    render_chunks(renderer.get(), last_index(name, fs) + 1,
                  [&](std::uint64_t start, std::size_t count, const std::vector<double>& out,
                      const api::TapBuffers& taps) {
                    for (const auto& v : spec::kRateCurveSamples) {
                      if (fixture_name != v.fixture || rate != v.fs || v.n < start || v.n >= start + count) {
                        continue;
                      }
                      ++rows;
                      INFO("n " << v.n << (v.past_end ? " (past end)" : ""));
                      const auto i = static_cast<std::size_t>(2 * (v.n - start));
                      for (std::size_t c = 0; c < 2; ++c) {
                        CHECK(api::bits(taps.theta_reference[i + c]) == v.theta_bits);
                        CHECK(api::bits(taps.gamma_pac[i + c]) == v.gamma_bits);
                        CHECK(api::bits(taps.stereo_bus[i + c]) == v.bus_bits);
                        CHECK(api::bits(taps.binaural_join[i + c]) == v.bus_bits);
                        CHECK(api::bits(taps.master[i + c]) == v.bus_bits);
                        CHECK(api::bits(out[i + c]) == v.bus_bits);
                      }
                    }
                  });
    CHECK(rows == 26);  // 24 signal rows and 2 past the end
  }
}

TEST_CASE("rate curves: every tap equals the curved law sample by sample, never -0.0", "[rate-curves][render]") {
  for (const char* name : kCurvedFixtures) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(name << " at " << fs);
      const plan::Plan p = compile_plan(api::valid(name), fs);
      auto compiled = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
      REQUIRE(arc_plan_frame_count(compiled.get()) == p.frame_count);
      auto renderer = api::renderer(compiled.get());
      std::size_t theta_mismatches = 0;
      std::size_t gamma_mismatches = 0;
      std::size_t bus_mismatches = 0;
      std::size_t channel_differs = 0;
      std::size_t negative_zero = 0;
      std::size_t curved = 0;  // samples whose envelope phase U is nonzero
      render_chunks(renderer.get(), p.frame_count,
                    [&](std::uint64_t start, std::size_t count, const std::vector<double>& out,
                        const api::TapBuffers& taps) {
                      for (std::size_t i = 0; i < count; ++i) {
                        const std::uint64_t n = start + i;
                        const double theta = theta_law(p.theta, n);
                        const double gamma = gamma_law(p.gamma, p.theta, n);
                        const std::size_t k = 2 * i;
                        theta_mismatches += api::bits(taps.theta_reference[k]) != api::bits(theta) ? 1 : 0;
                        gamma_mismatches += api::bits(taps.gamma_pac[k]) != api::bits(gamma) ? 1 : 0;
                        bus_mismatches += api::bits(taps.stereo_bus[k]) != api::bits(theta + gamma) ? 1 : 0;
                        bus_mismatches += api::bits(out[k]) != api::bits(theta + gamma) ? 1 : 0;
                        channel_differs += api::bits(taps.theta_reference[k]) != api::bits(taps.theta_reference[k + 1]);
                        channel_differs += api::bits(taps.gamma_pac[k]) != api::bits(taps.gamma_pac[k + 1]);
                        channel_differs += api::bits(out[k]) != api::bits(out[k + 1]);
                        negative_zero += api::bits(taps.gamma_pac[k]) == kNegativeZero ? 1 : 0;
                        curved += (plan_offset(p.theta, n) | plan_offset(p.gamma, n)) != 0 ? 1 : 0;
                      }
                    });
      CHECK(theta_mismatches == 0);
      CHECK(gamma_mismatches == 0);
      CHECK(bus_mismatches == 0);
      CHECK(channel_differs == 0);
      CHECK(negative_zero == 0);
      CHECK(curved > p.frame_count / 2);  // the cycle really moves the envelope phase
    }
  }
}

TEST_CASE("rate curves: swing 0 is the layer without a cycle bit for bit; a swing moves it",
          "[rate-curves][render]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    // Theta, alone and coupled.
    for (const std::string& gamma : {std::string(""), gamma_member("smooth_swell"), gamma_member("bursts")}) {
      INFO("gamma '" << gamma << "'");
      const Rendered fixed = render_text(recipe_text({theta_member("4"), gamma}), fs);
      const Rendered zero = render_text(recipe_text({theta_member("4", cycle_member("0")), gamma}), fs);
      const Rendered curved = render_text(recipe_text({theta_member("4", cycle_member("2")), gamma}), fs);
      CHECK(all_taps_same(zero, fixed));
      CHECK_FALSE(api::same_bytes(curved.taps.theta_reference, fixed.taps.theta_reference));
      if (!gamma.empty()) {
        // The coupled factor follows the curved theta envelope phase.
        CHECK_FALSE(api::same_bytes(curved.taps.gamma_pac, fixed.taps.gamma_pac));
      }
    }
    // Gamma, uncoupled and coupled; the theta tap never moves with it.
    for (const std::string& coupling : {std::string("uncoupled"), std::string("smooth_swell"), std::string("bursts")}) {
      INFO("coupling " << coupling);
      const std::string theta = theta_member("4");
      const Rendered fixed = render_text(recipe_text({theta, gamma_member(coupling, "45")}), fs);
      const Rendered zero = render_text(recipe_text({theta, gamma_member(coupling, "45", cycle_member("0"))}), fs);
      const Rendered curved = render_text(recipe_text({theta, gamma_member(coupling, "45", cycle_member("15"))}), fs);
      CHECK(all_taps_same(zero, fixed));
      CHECK_FALSE(api::same_bytes(curved.taps.gamma_pac, fixed.taps.gamma_pac));
      CHECK(api::same_bytes(curved.taps.theta_reference, fixed.taps.theta_reference));
    }
  }
}

TEST_CASE("rate curves: the carriers take no rate curve", "[rate-curves][render]") {
  // The plan carrier increments are those of carrier_hz with and without a
  // cycle, and the envelope increments those of the center rate_hz.
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const plan::Plan with =
        compile_plan(recipe_text({theta_member("4", cycle_member("2")), gamma_member("uncoupled", "45", cycle_member("15"))}),
                     fs);
    const plan::Plan without = compile_plan(recipe_text({theta_member("4"), gamma_member("uncoupled", "45")}), fs);
    CHECK(with.theta.increment == without.theta.increment);
    CHECK(with.gamma.increment == without.gamma.increment);
    CHECK(with.theta.increment == core::phase_increment(450.0, fs));
    CHECK(with.gamma.increment == core::phase_increment(250.0, fs));
    CHECK(with.theta.envelope_increment == core::phase_increment(4.0, fs));
    CHECK(with.gamma.envelope_increment == core::phase_increment(45.0, fs));
  }
}

TEST_CASE("rate curves: start phase 0 and 360 render the same bytes; 359.99 differs", "[rate-curves][render]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const auto theta_with = [](const std::string& phase) {
      return recipe_text({theta_member("4", cycle_member("2", phase)), gamma_member("bursts")});
    };
    const auto gamma_with = [](const std::string& phase) {
      return recipe_text({theta_member("4"), gamma_member("uncoupled", "45", cycle_member("15", phase))});
    };
    CHECK(all_taps_same(render_text(theta_with("0"), fs), render_text(theta_with("360"), fs)));
    CHECK(all_taps_same(render_text(gamma_with("0"), fs), render_text(gamma_with("360"), fs)));
    CHECK_FALSE(api::same_bytes(render_text(theta_with("359.99"), fs).taps.theta_reference,
                                render_text(theta_with("0"), fs).taps.theta_reference));
    CHECK_FALSE(api::same_bytes(render_text(gamma_with("359.99"), fs).taps.gamma_pac,
                                render_text(gamma_with("0"), fs).taps.gamma_pac));
  }
}

// ------------------------------------------------------------ AD-5

TEST_CASE("rate curves: the theta tap reads no gamma layer or gamma cycle", "[rate-curves][ad5]") {
  const std::string theta = theta_member("4", cycle_member("2"));
  const std::string gammas[] = {"",
                                gamma_member("uncoupled", "45"),
                                gamma_member("uncoupled", "45", cycle_member("15")),
                                gamma_member("smooth_swell", "45", cycle_member("15")),
                                gamma_member("bursts", "40", cycle_member("10", "270"))};
  for (const std::uint32_t fs : spec::sample_rates()) {
    const Rendered alone = render_text(recipe_text({theta}), fs);
    for (const auto& g : gammas) {
      INFO("fs " << fs << ", '" << g << "'");
      CHECK(api::same_bytes(render_text(recipe_text({theta, g}), fs).taps.theta_reference,
                            alone.taps.theta_reference));
    }
  }
}

TEST_CASE("rate curves: the coupled gamma tap reads only the curved theta envelope phase", "[rate-curves][ad5]") {
  // Another theta carrier, depth, or shape with the same rate and cycle
  // leaves the coupled gamma tap bit for bit.
  struct Theta {
    const char* shape;
    const char* carrier;
    const char* depth;
  };
  // Story 3.2: each other theta stays at least 50 Hz from the gamma lines
  // (the 250 Hz carrier at 45 +- 15 Hz with its theta lines); it was 300 Hz
  // sawtooth and 100 Hz reverse_saw.
  const Theta others[] = {{"sawtooth", "420", "25"}, {"reverse_saw", "500", "100"}, {"smoothed_on_off", "500", "50"}};
  for (const std::string& coupling : {std::string("smooth_swell"), std::string("bursts")}) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      const std::string gamma = gamma_member(coupling, "45", cycle_member("15"));
      const Rendered base = render_text(recipe_text({theta_member("4", cycle_member("2")), gamma}), fs);
      for (const auto& o : others) {
        INFO(coupling << " at " << fs << ", theta " << o.shape << " " << o.carrier << " Hz " << o.depth << " percent");
        const Rendered r =
            render_text(recipe_text({theta_member("4", cycle_member("2"), o.shape, o.carrier, o.depth), gamma}), fs);
        CHECK(api::same_bytes(r.taps.gamma_pac, base.taps.gamma_pac));
      }
    }
  }
}

TEST_CASE("rate curves: a binaural layer and a muted ear leave the curved theta and gamma taps",
          "[rate-curves][ad5][isolation]") {
  const std::string layers[] = {theta_member("4", cycle_member("2")),
                                gamma_member("bursts", "45", cycle_member("15"))};
  const std::string binaural =
      "\"binaural\": {\"carrier_left_hz\": 100, \"beat_rate_hz\": 1.5, \"beat_rate_cycle\": "
      "{\"swing_hz\": 1.5, \"period_s\": 60, \"start_phase_deg\": 270}}";
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const Rendered alone = render_text(recipe_text({layers[0], layers[1]}), fs);
    for (const arc_mute_ear mute : {ARC_MUTE_NONE, ARC_MUTE_LEFT, ARC_MUTE_RIGHT}) {
      const Rendered r = render_text(recipe_text({layers[0], layers[1], binaural}), fs, mute);
      CHECK(api::same_bytes(r.taps.theta_reference, alone.taps.theta_reference));
      CHECK(api::same_bytes(r.taps.gamma_pac, alone.taps.gamma_pac));
      CHECK(api::same_bytes(r.taps.stereo_bus, alone.taps.stereo_bus));
    }
  }
}

// ------------------------------------------------------------ seek and blocks

TEST_CASE("rate curves: seek to a vector index renders that index's bits", "[rate-curves][seek]") {
  for (const auto& [name, fs] : sample_fixture_rates()) {
    auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
    auto renderer = api::renderer(p.get());
    for (const auto& v : spec::kRateCurveSamples) {
      if (name != v.fixture || fs != v.fs) {
        continue;
      }
      INFO(name << " at " << fs << ", seek to " << v.n);
      api::seek(renderer.get(), v.n);
      api::TapBuffers taps(1);
      arc_taps t = taps.taps();
      const auto out = api::render(renderer.get(), 1, &t);
      CHECK(api::bits(taps.theta_reference[0]) == v.theta_bits);
      CHECK(api::bits(taps.gamma_pac[1]) == v.gamma_bits);
      CHECK(api::bits(taps.stereo_bus[0]) == v.bus_bits);
      CHECK(api::bits(out[1]) == v.bus_bits);
    }
  }
}

TEST_CASE("rate curves: seek to arbitrary frames equals the continuous render", "[rate-curves][seek]") {
  constexpr std::size_t kLen = 4096;
  for (const char* name : kCurvedFixtures) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
      const std::uint64_t frames = arc_plan_frame_count(p.get());
      const auto seek_k = static_cast<std::uint64_t>(std::llround(spec::kSeekSeconds * static_cast<double>(fs)));
      // Sorted and more than kLen apart: the continuous renderer only moves forward.
      // 63 + kLen and 64 + 2 * kLen sit on each side of a 64-frame block boundary.
      const std::vector<std::uint64_t> ks = {1,
                                             63 + kLen,
                                             64 + 2 * kLen,
                                             std::uint64_t{15} * fs + 1,
                                             seek_k,
                                             seek_k + 37 + kLen,
                                             std::uint64_t{90} * fs + 64,
                                             frames - kLen};
      REQUIRE(std::is_sorted(ks.begin(), ks.end()));
      auto continuous = api::renderer(p.get());
      auto sought = api::renderer(p.get());
      std::uint64_t at = 0;
      for (const std::uint64_t k : ks) {
        INFO(name << " at " << fs << ", seek to " << k);
        REQUIRE(k >= at);
        while (at < k) {
          const auto n = static_cast<std::size_t>(std::min<std::uint64_t>(65536, k - at));
          (void)api::render(continuous.get(), n);
          at += n;
        }
        api::TapBuffers a(kLen);
        api::TapBuffers b(kLen);
        const arc_taps ta = a.taps();
        const arc_taps tb = b.taps();
        const auto out_a = api::render(continuous.get(), kLen, &ta);
        api::seek(sought.get(), k);
        const auto out_b = api::render(sought.get(), kLen, &tb);
        at += kLen;
        CHECK(api::same_bytes(out_a, out_b));
        CHECK(api::same_bytes(a.theta_reference, b.theta_reference));
        CHECK(api::same_bytes(a.gamma_pac, b.gamma_pac));
        CHECK(api::same_bytes(a.stereo_bus, b.stereo_bus));
      }
    }
  }
}

TEST_CASE("rate curves: every block size of row block-sizes gives the same bytes with theta and gamma cycles",
          "[rate-curves][blocks]") {
  const auto& sizes = spec::row("block-sizes");
  const double allowed = spec::row("block-size-invariance").value();
  REQUIRE_FALSE(sizes.values.empty());
  const std::string texts[] = {
      recipe_text({theta_member("4", cycle_member("2")), gamma_member("bursts", "45", cycle_member("15"))}),
      recipe_text({theta_member("3.5", cycle_member("2.5", "270"), "smoothed_on_off"),
                   gamma_member("smooth_swell", "40", cycle_member("10", "90"))}),
  };
  for (const auto& text : texts) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      const Rendered whole = render_text(text, fs);
      for (const double size : sizes.values) {
        INFO(fs << ", " << size << " frames per call\n" << text);
        const Rendered r = render_in_blocks(text, fs, static_cast<std::size_t>(size));
        CHECK(static_cast<double>(differing_bytes(r.out, whole.out)) <= allowed);
        CHECK(static_cast<double>(differing_bytes(r.taps.theta_reference, whole.taps.theta_reference)) <= allowed);
        CHECK(static_cast<double>(differing_bytes(r.taps.gamma_pac, whole.taps.gamma_pac)) <= allowed);
      }
    }
  }
}

#else

TEST_CASE("rate curves on the theta and gamma rates are implemented", "[rate-curves]") {
  FAIL("not implemented: core/rate_cycle.hpp (Story 2.6)");
}

#endif
