// Gamma PAC layer, uncoupled (Story 2.2; docs/signal-spec.md, Gamma PAC layer).
//
// The uncoupled gamma layer is a separate sine carrier amplitude-modulated
// at the gamma rate with a constant AM depth, the same value in both
// channels. Two phase accumulators, each 0 at n = 0:
//
//   inc_G = phase increment rule (carrier_hz, fs)   carrier phase_G[n] = n * inc_G
//   inc_M = phase increment rule (rate_hz, fs)      envelope phase_M[n] = n * inc_M
//   c = sine(phase_M + 2^62), e = (1.0 + c) * 0.5   the theta sine shape at the gamma rate
//   d = am_depth_percent / 100.0                    once per plan
//   a = 1.0 - d * (1.0 - e)
//   gamma[c][n] = a * sine(phase_G)                 both channels
//   bus[c][n] = theta[c][n] + gamma[c][n]
//
// Expected interface, engine/src/plan/plan.hpp, namespace arcani::plan:
//
//   struct GammaOscillator {
//     bool present = false;
//     std::uint64_t increment = 0;           // phase increment rule (carrier_hz, fs)
//     std::uint64_t envelope_increment = 0;  // phase increment rule (rate_hz, fs)
//     double depth = 0.0;                    // am_depth_percent / 100.0
//   };
//   struct Plan { ...; GammaOscillator gamma; ... };
//
// The plan member is read through a template with a requires-expression, so
// the suite still builds before it exists and the missing member shows as a
// failing test case. Every render check reaches the engine through the
// public C API only.
//
// Vectors come from the generated spec_tables.hpp (kGammaEnvelopes,
// kGammaSamples, kGammaBus); rows from the tables through the assertion
// call. Fixtures (recipes/fixtures/valid/): gamma-uncoupled-40hz-25pct.json,
// gamma-uncoupled-40hz-100pct.json, gamma-uncoupled-60hz-25pct.json,
// gamma-uncoupled-60hz-100pct.json (a 250 Hz sine carrier
// amplitude-modulated at 40 or 60 Hz, 25 or 100 percent AM depth, 10 s,
// gamma only) and theta-gamma-uncoupled.json (adds a 450 Hz carrier
// amplitude-modulated at 6 Hz by the sine envelope, 75 percent AM depth, to
// the 40 Hz, 100 percent gamma layer).
//
// Checks: the engine envelope and depth law against kGammaEnvelopes; each
// fixture at both sample rates holds the vector bits in the gamma tap (both
// channels), and for the gamma-only fixtures in the bus and the output; the
// theta and gamma fixture holds the kGammaBus theta, gamma, and bus bits;
// everything past the end is +0.0; every gamma tap sample equals the AM law
// recomputed here from the engine sine; seek to a vector index renders that
// index's bits (seek sets both gamma phases); odd-sized calls give the same
// bytes; the gamma tap is never -0.0, even at 100 percent depth; depth 0 is
// the unmodulated carrier bit for bit; a recipe without gamma_pac keeps a
// +0.0 gamma tap; the plan holds the increments and the depth.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#if __has_include("core/envelope.hpp") && __has_include("plan/plan.hpp") && \
    defined(ARC_ERROR_FIELD_BYTES)

#include "api_helpers.hpp"
#include "core/envelope.hpp"
#include "core/phase.hpp"
#include "core/sine.hpp"
#include "plan/plan.hpp"
#include "spec_helpers.hpp"

#include <algorithm>
#include <cmath>
#include <concepts>
#include <cstdint>
#include <cstring>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace api = arcani::test::api;
namespace core = arcani::core;
namespace plan = arcani::plan;
namespace spec = arcani::test::spec;

namespace {

constexpr std::uint64_t kQuarter = UINT64_C(1) << 62;
constexpr std::uint64_t kNegativeZero = UINT64_C(0x8000000000000000);
constexpr const char* kThetaGamma = "theta-gamma-uncoupled.json";

// The engine gamma envelope, recomputed here from the engine sine in the
// spec's operation order: c = sine(p + 2^62 mod 2^64), e = (1.0 + c) * 0.5.
double law_envelope(std::uint64_t phase) {
  const double c = core::sine(phase + kQuarter);
  return (1.0 + c) * 0.5;
}

// a = 1.0 - d * (1.0 - e), three binary64 operations in this order.
double law_amplitude(double d, double e) { return 1.0 - d * (1.0 - e); }

double value_of(std::uint64_t bits) {
  double x = 0.0;
  std::memcpy(&x, &bits, sizeof x);
  return x;
}

// |e - e_ideal| <= b / 2 + 2^-52 (signal spec, Gamma PAC layer, Error bound).
double envelope_bound() { return spec::sine_error_bound_linear() / 2.0 + 0x1p-52; }

// |a - a_ideal| <= d * (b / 2 + 2^-52) + 2^-52.
double amplitude_bound(double d) { return d * envelope_bound() + 0x1p-52; }

struct Rendered {
  std::uint64_t frames = 0;
  std::vector<double> out;
  api::TapBuffers taps{0};
};

Rendered render_fixture(const std::string& name, std::uint32_t fs, std::uint64_t extra) {
  auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
  Rendered r;
  r.frames = arc_plan_frame_count(p.get());
  const auto total = static_cast<std::size_t>(r.frames + extra);
  r.taps = api::TapBuffers(total);
  auto renderer = api::renderer(p.get());
  arc_taps t = r.taps.taps();
  r.out = api::render(renderer.get(), total, &t);
  return r;
}

// (fixture, fs) pairs of kGammaSamples, in vector order.
std::vector<std::pair<std::string, std::uint32_t>> fixture_rates() {
  std::vector<std::pair<std::string, std::uint32_t>> out;
  for (const auto& v : spec::kGammaSamples) {
    const std::pair<std::string, std::uint32_t> key{v.fixture, v.fs};
    if (std::find(out.begin(), out.end(), key) == out.end()) {
      out.push_back(key);
    }
  }
  return out;
}

// The first sample vector of a (fixture, fs) pair: the layer's values.
const spec::GammaSampleVector& first_vector(const std::string& name, std::uint32_t fs) {
  for (const auto& v : spec::kGammaSamples) {
    if (name == v.fixture && fs == v.fs) {
      return v;
    }
  }
  FAIL("no gamma sample vector for " << name << " at " << fs);
  return spec::kGammaSamples[0];
}

std::string gamma_recipe(const char* carrier, const char* rate, const char* depth,
                         const char* wave = "sine", const char* coupling = "uncoupled") {
  return std::string(
             "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
             "\"author\": \"Arcani test\", \"date\": \"2026-11-07\", "
             "\"rationale\": \"Gamma PAC layer test, made in the test.\", "
             "\"length_s\": 1, \"loudness_target_lufs\": -36, "
             "\"gamma_pac\": {\"carrier_hz\": ") +
         carrier + ", \"rate_hz\": " + rate + ", \"am_depth_percent\": " + depth +
         ", \"carrier_wave\": \"" + wave + "\", \"coupling\": \"" + coupling + "\"}}";
}

template <class P>
concept PlanHasGamma = requires(const P& p) {
  { p.gamma.present } -> std::convertible_to<bool>;
  { p.gamma.increment } -> std::convertible_to<std::uint64_t>;
  { p.gamma.envelope_increment } -> std::convertible_to<std::uint64_t>;
  { p.gamma.depth } -> std::convertible_to<double>;
};

template <class P>
void check_gamma_plan(const P& p, bool present, std::uint64_t inc, std::uint64_t env_inc,
                      double depth) {
  if constexpr (PlanHasGamma<P>) {
    CHECK(p.gamma.present == present);
    CHECK(p.gamma.increment == inc);
    CHECK(p.gamma.envelope_increment == env_inc);
    CHECK(api::bits(p.gamma.depth) == api::bits(depth));
  } else {
    FAIL("not implemented: plan::Plan has no GammaOscillator gamma member (Story 2.2)");
  }
}

plan::Plan compile_plan(const std::string& text, std::uint32_t fs) {
  auto r = plan::compile(text, plan::Mode::Measure, fs, plan::MuteEar::None);
  INFO("rule '" << r.error.rule << "', parameter '" << r.error.parameter << "', value '"
                << r.error.value << "', limit '" << r.error.limit << "'");
  REQUIRE(r.plan.has_value());
  return std::move(*r.plan);
}

}  // namespace

TEST_CASE("gamma envelope and depth law match the vectors", "[gamma]") {
  std::set<double> depths;
  for (const auto& v : spec::kGammaEnvelopes) {
    INFO("depth " << v.depth_percent << " percent, envelope phase " << v.phase);
    const double e = law_envelope(v.phase);
    // The theta sine shape is the same envelope; W and H do not enter it.
    const double theta_sine = core::envelope(core::EnvelopeShape::Sine, v.phase,
                                             core::theta_edge_units(6.0), core::theta_half_on_units());
    CHECK(api::bits(e) == v.e_bits);
    CHECK(api::bits(theta_sine) == v.e_bits);
    const double d = v.depth_percent / 100.0;
    const double a = law_amplitude(d, e);
    CHECK(api::bits(a) == v.a_bits);
    CHECK(e > 0.0);  // the engine envelope is never 0
    CHECK(e <= 1.0);
    CHECK(std::fabs(e - v.ideal_e) <= envelope_bound());
    CHECK(std::fabs(a - v.ideal_a) <= amplitude_bound(d));
    depths.insert(v.depth_percent);
  }
  const auto& depth = spec::row("coupling-depth");
  CHECK(depth.kind == "ranges");
  CHECK(depth.unit == "percent");
  CHECK(depths.count(depth.min) == 1);
  CHECK(depths.count(depth.max) == 1);
}

TEST_CASE("gamma envelope must-fail: the unmodulated stub misses the amplitude vectors",
          "[gamma]") {
  // a = 1 (no envelope) misses the ideal amplitude at 25 and 100 percent.
  int misses = 0;
  for (const auto& v : spec::kGammaEnvelopes) {
    const double d = v.depth_percent / 100.0;
    misses += std::fabs(1.0 - v.ideal_a) > amplitude_bound(d) ? 1 : 0;
  }
  CHECK(misses > 0);
}

TEST_CASE("gamma fixtures render the vector bits through the C API", "[gamma][render]") {
  constexpr std::uint64_t kExtra = 64;
  const auto pairs = fixture_rates();
  REQUIRE(pairs.size() == 10);  // five fixtures at two sample rates
  for (const auto& [name, fs] : pairs) {
    INFO(name << " at " << fs);
    const Rendered r = render_fixture(name, fs, kExtra);
    const auto& first = first_vector(name, fs);
    REQUIRE(r.frames == first.frames);
    for (const auto& v : spec::kGammaSamples) {
      if (name != v.fixture || fs != v.fs) {
        continue;
      }
      INFO("n " << v.n << (v.past_end ? " (past end)" : ""));
      const auto i = static_cast<std::size_t>(2 * v.n);
      for (std::size_t c = 0; c < 2; ++c) {
        CHECK(api::bits(r.taps.gamma_pac[i + c]) == v.gamma_bits);
        if (!v.has_theta) {
          CHECK(api::bits(r.taps.stereo_bus[i + c]) == v.gamma_bits);
          CHECK(api::bits(r.out[i + c]) == v.gamma_bits);
        }
      }
    }
    const auto live = static_cast<std::size_t>(2 * r.frames);
    if (!first.has_theta) {
      CHECK(api::all_exact_zero(r.taps.theta_reference));
      CHECK(api::same_bytes(r.out, r.taps.gamma_pac));  // gamma only, no binaural layer
    }
    CHECK(api::same_bytes(r.out, r.taps.stereo_bus));  // no binaural layer
    CHECK(api::same_bytes(r.out, r.taps.master));
    CHECK(api::all_exact_zero(r.taps.gamma_pac.data() + live, 2 * kExtra));
    CHECK(api::all_exact_zero(r.out.data() + live, 2 * kExtra));
  }
}

TEST_CASE("gamma tap equals the AM law sample by sample, never -0.0", "[gamma][render]") {
  for (const auto& [name, fs] : fixture_rates()) {
    INFO(name << " at " << fs);
    const auto& v = first_vector(name, fs);
    const Rendered r = render_fixture(name, fs, 0);
    REQUIRE(r.frames == v.frames);
    const double d = v.depth_percent / 100.0;
    std::size_t mismatches = 0;
    std::size_t negative_zero = 0;
    std::size_t channel_differs = 0;
    for (std::uint64_t n = 0; n < r.frames; ++n) {
      const double e = law_envelope(n * v.inc_rate);
      const double want = law_amplitude(d, e) * core::sine(n * v.inc_carrier);
      const auto i = static_cast<std::size_t>(2 * n);
      mismatches += api::bits(r.taps.gamma_pac[i]) != api::bits(want) ? 1 : 0;
      negative_zero += api::bits(r.taps.gamma_pac[i]) == kNegativeZero ? 1 : 0;
      channel_differs += api::bits(r.taps.gamma_pac[i]) != api::bits(r.taps.gamma_pac[i + 1]) ? 1 : 0;
    }
    CHECK(mismatches == 0);
    CHECK(negative_zero == 0);
    CHECK(channel_differs == 0);
  }
}

TEST_CASE("theta and gamma fixture: theta, gamma, and bus taps hold the bus vector bits",
          "[gamma][bus]") {
  std::set<std::uint32_t> rates;
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO(kThetaGamma << " at " << fs);
    const Rendered r = render_fixture(kThetaGamma, fs, 64);
    std::size_t rows = 0;
    for (const auto& v : spec::kGammaBus) {
      if (std::string_view(v.fixture) != kThetaGamma || v.fs != fs) {
        continue;
      }
      ++rows;
      INFO("n " << v.n << (v.past_end ? " (past end)" : ""));
      const auto i = static_cast<std::size_t>(2 * v.n);
      for (std::size_t c = 0; c < 2; ++c) {
        CHECK(api::bits(r.taps.theta_reference[i + c]) == v.theta_bits);
        CHECK(api::bits(r.taps.gamma_pac[i + c]) == v.gamma_bits);
        CHECK(api::bits(r.taps.stereo_bus[i + c]) == v.bus_bits);
        CHECK(api::bits(r.out[i + c]) == v.bus_bits);  // no binaural layer
      }
      if (!v.past_end) {
        // One binary64 addition of the two taps.
        const double sum = value_of(v.theta_bits) + value_of(v.gamma_bits);
        CHECK(api::bits(sum) == v.bus_bits);
      }
    }
    CHECK(rows > 0);
    rates.insert(fs);
    // Every bus sample is the one-rounding sum of its two taps.
    std::size_t sum_mismatches = 0;
    for (std::size_t i = 0; i < 2 * static_cast<std::size_t>(r.frames); ++i) {
      const double sum = r.taps.theta_reference[i] + r.taps.gamma_pac[i];
      sum_mismatches += api::bits(sum) != api::bits(r.taps.stereo_bus[i]) ? 1 : 0;
    }
    CHECK(sum_mismatches == 0);
  }
  CHECK(rates.size() == 2);
}

TEST_CASE("gamma seek sets both gamma phases", "[gamma][seek]") {
  for (const auto& [name, fs] : fixture_rates()) {
    auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
    auto renderer = api::renderer(p.get());
    for (const auto& v : spec::kGammaSamples) {
      if (name != v.fixture || fs != v.fs) {
        continue;
      }
      INFO(name << " at " << fs << ", seek to " << v.n);
      api::seek(renderer.get(), v.n);
      api::TapBuffers taps(1);
      arc_taps t = taps.taps();
      const auto out = api::render(renderer.get(), 1, &t);
      CHECK(api::bits(taps.gamma_pac[0]) == v.gamma_bits);
      CHECK(api::bits(taps.gamma_pac[1]) == v.gamma_bits);
      if (!v.has_theta) {
        CHECK(api::bits(out[0]) == v.gamma_bits);
      }
    }
    for (const auto& v : spec::kGammaBus) {
      if (name != v.fixture || fs != v.fs) {
        continue;
      }
      INFO(name << " at " << fs << ", seek to " << v.n << " (bus)");
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

TEST_CASE("gamma renders the same bytes in odd-sized calls", "[gamma][blocks]") {
  for (const auto& [name, fs] : fixture_rates()) {
    if (fs != 48000) {
      continue;
    }
    INFO(name);
    auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
    const auto frames = static_cast<std::size_t>(arc_plan_frame_count(p.get()));
    auto one = api::renderer(p.get());
    const auto whole = api::render(one.get(), frames);
    auto pieces = api::renderer(p.get());
    std::vector<double> joined;
    joined.reserve(2 * frames);
    std::size_t done = 0;
    for (std::size_t call = 0; done < frames; ++call) {
      const std::size_t n = std::min<std::size_t>(call % 2 == 0 ? 1009 : 5, frames - done);
      const auto part = api::render(pieces.get(), n);
      joined.insert(joined.end(), part.begin(), part.end());
      done += n;
    }
    CHECK(api::same_bytes(whole, joined));
  }
}

TEST_CASE("gamma at depth 0 is the unmodulated carrier", "[gamma][depth]") {
  // 250 Hz carrier amplitude-modulated at 40 Hz with 0 percent AM depth:
  // a = 1.0 exactly, so the tap is the engine sine of the carrier phase.
  const std::string text = gamma_recipe("250", "40", "0");
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    auto p = api::compile_ok(text, api::options(ARC_MODE_MEASURE, fs));
    const auto frames = static_cast<std::size_t>(arc_plan_frame_count(p.get()));
    auto renderer = api::renderer(p.get());
    api::TapBuffers taps(frames);
    arc_taps t = taps.taps();
    api::render(renderer.get(), frames, &t);
    const std::uint64_t inc = core::phase_increment(250.0, fs);
    bool same = true;
    for (std::size_t n = 0; n < frames; ++n) {
      const std::uint64_t want = api::bits(core::sine(static_cast<std::uint64_t>(n) * inc));
      same = same && api::bits(taps.gamma_pac[2 * n]) == want &&
             api::bits(taps.gamma_pac[2 * n + 1]) == want;
    }
    CHECK(same);
  }
}

TEST_CASE("gamma range edges render: 200 Hz carrier at 30 Hz, 500 Hz at 60 Hz", "[gamma][render]") {
  // The locked-range corners the carrier rule permits, made here.
  const auto& carrier = spec::hz_range("gamma-carrier");
  const auto& rate = spec::hz_range("gamma-rate");
  REQUIRE(carrier.min >= spec::row("carrier-rule").value() * rate.min);
  struct Corner {
    const char* carrier;
    const char* rate;
    double carrier_hz;
    double rate_hz;
  };
  const Corner corners[] = {{"200", "30", carrier.min, rate.min}, {"500", "60", carrier.max, rate.max}};
  for (const auto& k : corners) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(k.carrier << " Hz carrier at " << k.rate << " Hz, fs " << fs);
      auto p = api::compile_ok(gamma_recipe(k.carrier, k.rate, "100"), api::options(ARC_MODE_MEASURE, fs));
      const auto frames = static_cast<std::size_t>(arc_plan_frame_count(p.get()));
      auto renderer = api::renderer(p.get());
      api::TapBuffers taps(frames);
      arc_taps t = taps.taps();
      api::render(renderer.get(), frames, &t);
      const std::uint64_t inc_g = core::phase_increment(k.carrier_hz, fs);
      const std::uint64_t inc_m = core::phase_increment(k.rate_hz, fs);
      bool same = true;
      for (std::size_t n = 0; n < frames; ++n) {
        const auto m = static_cast<std::uint64_t>(n);
        const double want = law_amplitude(1.0, law_envelope(m * inc_m)) * core::sine(m * inc_g);
        same = same && api::bits(taps.gamma_pac[2 * n]) == api::bits(want);
      }
      CHECK(same);
    }
  }
}

TEST_CASE("a recipe without gamma_pac keeps a +0.0 gamma tap and an unchanged bus",
          "[gamma][stub]") {
  for (const char* name : {api::kBeat0, api::kBeat6, api::kNoLayers, "theta-sine-6hz.json",
                           "theta-smoothed-on-off-6hz.json"}) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(name << " at " << fs);
      const Rendered r = render_fixture(name, fs, 0);
      CHECK(api::all_exact_zero(r.taps.gamma_pac));
      // bus = theta + (+0.0): theta bit for bit, except -0.0 becomes +0.0.
      bool same = true;
      for (std::size_t i = 0; i < r.taps.stereo_bus.size(); ++i) {
        const double theta = r.taps.theta_reference[i];
        const std::uint64_t want = api::bits(theta) == kNegativeZero ? 0 : api::bits(theta);
        same = same && api::bits(r.taps.stereo_bus[i]) == want;
      }
      CHECK(same);
    }
  }
}

TEST_CASE("gamma plan holds the increments and the depth", "[gamma][plan]") {
  for (const auto& [name, fs] : fixture_rates()) {
    INFO(name << " at " << fs);
    const auto& v = first_vector(name, fs);
    const plan::Plan p = compile_plan(api::valid(name), fs);
    CHECK(p.frame_count == v.frames);
    CHECK(v.inc_carrier == core::phase_increment(v.carrier_hz, fs));
    CHECK(v.inc_rate == core::phase_increment(v.rate_hz, fs));
    check_gamma_plan(p, true, v.inc_carrier, v.inc_rate, v.depth_percent / 100.0);
    CHECK(p.theta.present == v.has_theta);
  }
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("no gamma_pac, fs " << fs);
    const plan::Plan p = compile_plan(api::valid("theta-sine-6hz.json"), fs);
    check_gamma_plan(p, false, 0, 0, 0.0);
  }
}

namespace {

// Theta, gamma, and binaural together, made in the test (no stored fixture):
// a 450 Hz carrier amplitude-modulated at 6 Hz by the sine envelope at
// 75 percent depth, a 250 Hz sine carrier amplitude-modulated at 40 Hz at
// 100 percent depth (uncoupled), and a 400 Hz unmodulated sine in the left
// ear with a 406 Hz unmodulated sine in the right ear (a 6 Hz binaural
// beat), 1 s.
std::string theta_gamma_binaural_recipe() {
  return "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
         "\"author\": \"Arcani test\", \"date\": \"2026-11-07\", "
         "\"rationale\": \"Theta, gamma, and binaural layers together, made in the test.\", "
         "\"length_s\": 1, \"loudness_target_lufs\": -36, "
         "\"theta_reference\": {\"carrier_hz\": 450, \"rate_hz\": 6, \"am_depth_percent\": 75, "
         "\"shape\": \"sine\"}, "
         "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": 40, \"am_depth_percent\": 100, "
         "\"carrier_wave\": \"sine\", \"coupling\": \"uncoupled\"}, "
         "\"binaural\": {\"carrier_left_hz\": 400, \"beat_rate_hz\": 6}}";
}

Rendered render_text(const std::string& text, std::uint32_t fs, arc_mute_ear mute) {
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

}  // namespace

TEST_CASE("muting a binaural ear leaves the gamma tap and the other channel unchanged",
          "[gamma][isolation]") {
  const std::string text = theta_gamma_binaural_recipe();
  for (const std::uint32_t fs : spec::sample_rates()) {
    const Rendered full = render_text(text, fs, ARC_MUTE_NONE);
    for (const auto& [mute, muted] : {std::pair{ARC_MUTE_LEFT, 0}, std::pair{ARC_MUTE_RIGHT, 1}}) {
      INFO("fs " << fs << ", muted channel " << muted);
      const Rendered r = render_text(text, fs, mute);
      CHECK(api::same_bytes(r.taps.gamma_pac, full.taps.gamma_pac));
      CHECK(api::same_bytes(r.taps.theta_reference, full.taps.theta_reference));
      const int open = 1 - muted;
      CHECK(api::same_bytes(api::channel(r.taps.binaural_join, open),
                            api::channel(full.taps.binaural_join, open)));
      CHECK(api::same_bytes(api::channel(r.taps.master, open), api::channel(full.taps.master, open)));
      CHECK(api::same_bytes(api::channel(r.out, open), api::channel(full.out, open)));
      // The muted channel: join, master, and out equal its stereo bus
      // (theta + gamma) bit for bit.
      const auto bus = api::channel(r.taps.stereo_bus, muted);
      CHECK(api::same_bytes(api::channel(r.taps.binaural_join, muted), bus));
      CHECK(api::same_bytes(api::channel(r.taps.master, muted), bus));
      CHECK(api::same_bytes(api::channel(r.out, muted), bus));
      // And the gamma layer is really in that bus: it differs from theta.
      CHECK_FALSE(api::same_bytes(bus, api::channel(r.taps.theta_reference, muted)));
    }
  }
}

TEST_CASE("gamma vector rows cover both rates, the block edges, and past the end", "[gamma]") {
  std::set<std::pair<std::string, std::uint32_t>> signal, past;
  for (const auto& v : spec::kGammaSamples) {
    (v.past_end ? past : signal).insert({v.fixture, v.fs});
    CHECK(v.past_end == (v.n >= v.frames));
    CHECK(v.phase_carrier == v.n * v.inc_carrier);
    CHECK(v.phase_rate == v.n * v.inc_rate);
  }
  CHECK(signal.size() == 10);
  CHECK(past == signal);
}

#else

TEST_CASE("gamma PAC layer is implemented", "[gamma]") {
  FAIL("not implemented: core/envelope.hpp or plan/plan.hpp (Story 2.2)");
}

#endif
