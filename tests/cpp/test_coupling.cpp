// Gamma PAC layer, coupled smooth swell (Story 2.3; docs/signal-spec.md,
// Coupling).
//
// With coupling smooth_swell the gamma AM depth follows the theta reference
// phase: one raised cosine per theta cycle, peak at the coupling phase.
//
//   C = coupling phase rule (coupling_phase_deg)     once per plan
//   p_E = n * inc_E mod 2^64                          the theta envelope phase
//   s = swell(p_E, C) = sine_envelope(p_E - C mod 2^64)
//   e = sine_envelope(phase_M)                        the gamma envelope
//   a = 1.0 - (d * s) * (1.0 - e)                     four binary64 operations
//   gamma[c][n] = a * sine(phase_G)                   both channels
//
// Expected interface, engine/src/core/envelope.hpp, namespace arcani::core:
//
//   std::uint64_t coupling_phase_units(double coupling_phase_deg) noexcept;
//   double swell(std::uint64_t theta_envelope_phase,
//                std::uint64_t coupling_phase_units) noexcept;
//
// and engine/src/plan/plan.hpp, plan::GammaOscillator gains
//
//   bool coupled = false;                    // true for smooth_swell
//   std::uint64_t coupling_phase_units = 0;  // C
//
// AD-5 structural: a static_assert pins the exact type of &core::swell, so
// its only signal input is the theta envelope phase (the second argument is
// the plan constant C). The two core functions are reached through a lookup
// probe (a global fallback that the real declaration hides), and the plan
// members through a requires-expression, so the suite builds before they
// exist and the missing pieces show as failing test cases. Once core::swell
// is declared, the static_assert holds the build to its exact signature.
//
// Every render check reaches the engine through the public C API. Vectors
// come from the generated spec_tables.hpp (kCouplingPhases, kSwells,
// kSwellSamples); rows from the tables through the assertion call.
// Fixtures (recipes/fixtures/valid/): swell-sine-0deg-100pct.json,
// swell-sawtooth-90deg-25pct.json, swell-smoothed-on-off-180deg-100pct.json,
// swell-reverse-saw-270deg-25pct.json (a 450 Hz carrier amplitude-modulated
// at 6 Hz by the named envelope shape, 75 percent AM depth, plus a 250 Hz
// sine carrier amplitude-modulated at 40 Hz whose AM depth swells once per
// theta cycle to the named depth at the named coupling phase; 5 s) and
// swell-gamma-depth-0-no-theta.json (the gamma layer alone at 0 percent AM
// depth, coupling phase 90 degrees).

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
#include <limits>
#include <set>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

// ------------------------------------------------------------ lookup probe
//
// Global fallbacks. Inside arcani::coupling_probe a using-directive makes the
// names of arcani::core visible as members of arcani, which unqualified
// lookup reaches before the global namespace: a real core::swell or
// core::coupling_phase_units hides the fallback. Each fallback is callable,
// so the calls below compile either way; it returns a value no vector holds.

namespace coupling_missing {
struct MissingSwell {
  template <class... A>
  double operator()(A...) const noexcept {
    return std::numeric_limits<double>::quiet_NaN();
  }
};
struct MissingPhase {
  template <class... A>
  std::uint64_t operator()(A...) const noexcept {
    return UINT64_C(0xdeadbeefdeadbeef);
  }
};
}  // namespace coupling_missing

inline constexpr coupling_missing::MissingSwell swell{};
inline constexpr coupling_missing::MissingPhase coupling_phase_units{};

namespace arcani::coupling_probe {

using namespace arcani::core;

using SwellFn = double (*)(std::uint64_t, std::uint64_t) noexcept;
using PhaseFn = std::uint64_t (*)(double) noexcept;

inline constexpr bool kSwellDeclared =
    !std::is_same_v<std::remove_cvref_t<decltype(swell)>, ::coupling_missing::MissingSwell>;
inline constexpr bool kSwellExact = std::is_same_v<decltype(&swell), SwellFn>;
inline constexpr bool kPhaseDeclared =
    !std::is_same_v<std::remove_cvref_t<decltype(coupling_phase_units)>, ::coupling_missing::MissingPhase>;
inline constexpr bool kPhaseExact = std::is_same_v<decltype(&coupling_phase_units), PhaseFn>;

// AD-5 structural: the engine swell is one function of (theta envelope
// phase, plan constant C) and nothing else.
static_assert(!kSwellDeclared || kSwellExact,
              "arcani::core::swell must be exactly double(std::uint64_t, std::uint64_t) noexcept "
              "(AD-5: its only signal input is the theta envelope phase)");
static_assert(!kPhaseDeclared || kPhaseExact,
              "arcani::core::coupling_phase_units must be exactly std::uint64_t(double) noexcept");

inline double call_swell(std::uint64_t theta_envelope_phase, std::uint64_t c) {
  return swell(theta_envelope_phase, c);
}

inline std::uint64_t call_phase_units(double deg) { return coupling_phase_units(deg); }

}  // namespace arcani::coupling_probe

namespace api = arcani::test::api;
namespace core = arcani::core;
namespace plan = arcani::plan;
namespace probe = arcani::coupling_probe;
namespace spec = arcani::test::spec;

namespace {

constexpr std::uint64_t kQuarter = UINT64_C(1) << 62;
constexpr std::uint64_t kHalf = UINT64_C(1) << 63;
constexpr std::uint64_t kNegativeZero = UINT64_C(0x8000000000000000);

// b, the sine error bound (row sine-error), as a linear amplitude.
double b() { return spec::sine_error_bound_linear(); }

// |s - s_ideal| <= b / 2 + 2^-52 (signal spec, Coupling, Error bound).
double swell_bound() { return b() / 2.0 + 0x1p-52; }

// |a - a_ideal| <= d * b + 2^-49.
double amplitude_bound(double d) { return d * b() + 0x1p-49; }

// The coupled depth law, four binary64 operations in the spec's order.
double law_amplitude(double d, double s, double e) {
  const double ds = d * s;
  const double one_minus_e = 1.0 - e;
  return 1.0 - ds * one_minus_e;
}

struct Rendered {
  std::uint64_t frames = 0;
  std::vector<double> out;
  api::TapBuffers taps{0};
};

Rendered render_text(const std::string& text, std::uint32_t fs, std::uint64_t extra = 0,
                     arc_mute_ear mute = ARC_MUTE_NONE) {
  auto p = api::compile_ok(text, api::options(ARC_MODE_MEASURE, fs, mute));
  Rendered r;
  r.frames = arc_plan_frame_count(p.get());
  const auto total = static_cast<std::size_t>(r.frames + extra);
  r.taps = api::TapBuffers(total);
  auto renderer = api::renderer(p.get());
  arc_taps t = r.taps.taps();
  r.out = api::render(renderer.get(), total, &t);
  return r;
}

Rendered render_fixture(const std::string& name, std::uint32_t fs, std::uint64_t extra = 0) {
  return render_text(api::valid(name), fs, extra);
}

// (fixture, fs) pairs of kSwellSamples, in vector order.
std::vector<std::pair<std::string, std::uint32_t>> fixture_rates() {
  std::vector<std::pair<std::string, std::uint32_t>> out;
  for (const auto& v : spec::kSwellSamples) {
    const std::pair<std::string, std::uint32_t> key{v.fixture, v.fs};
    if (std::find(out.begin(), out.end(), key) == out.end()) {
      out.push_back(key);
    }
  }
  return out;
}

const spec::SwellSampleVector& first_vector(const std::string& name, std::uint32_t fs) {
  for (const auto& v : spec::kSwellSamples) {
    if (name == v.fixture && fs == v.fs) {
      return v;
    }
  }
  FAIL("no swell sample vector for " << name << " at " << fs);
  return spec::kSwellSamples[0];
}

const char* const kCoupledFixtures[] = {
    "swell-sine-0deg-100pct.json", "swell-sawtooth-90deg-25pct.json",
    "swell-smoothed-on-off-180deg-100pct.json", "swell-reverse-saw-270deg-25pct.json"};
constexpr const char* kDepth0NoTheta = "swell-gamma-depth-0-no-theta.json";

// A recipe made here. theta and binaural are JSON members with a trailing
// ", " (empty drops the layer); an empty phase omits coupling_phase_deg.
std::string swell_recipe(const std::string& theta, const std::string& depth,
                         const std::string& phase, const std::string& coupling = "smooth_swell",
                         const std::string& binaural = "", const std::string& length = "1",
                         const std::string& gamma_rate = "40") {
  std::string gamma = "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": " + gamma_rate +
                      ", \"am_depth_percent\": " + depth +
                      ", \"carrier_wave\": \"sine\", \"coupling\": \"" + coupling + "\"";
  if (!phase.empty()) {
    gamma += ", \"coupling_phase_deg\": " + phase;
  }
  gamma += "}";
  return "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
         "\"author\": \"Arcani test\", \"date\": \"2026-11-10\", "
         "\"rationale\": \"Coupled gamma test, made in the test.\", "
         "\"length_s\": " + length + ", \"loudness_target_lufs\": -36, " + theta + binaural +
         gamma + "}";
}

std::string theta_member(const char* carrier, const char* rate, const char* depth,
                         const char* shape) {
  return std::string("\"theta_reference\": {\"carrier_hz\": ") + carrier + ", \"rate_hz\": " + rate +
         ", \"am_depth_percent\": " + depth + ", \"shape\": \"" + shape + "\"}, ";
}

const std::string kBaseTheta = theta_member("450", "6", "75", "sine");
const std::string kBinaural = "\"binaural\": {\"carrier_left_hz\": 400, \"beat_rate_hz\": 6}, ";

template <class P>
concept PlanHasCoupling = requires(const P& p) {
  { p.gamma.coupled } -> std::convertible_to<bool>;
  { p.gamma.coupling_phase_units } -> std::convertible_to<std::uint64_t>;
};

template <class P>
void check_coupling_plan(const P& p, bool coupled, std::uint64_t c_units) {
  if constexpr (PlanHasCoupling<P>) {
    CHECK(p.gamma.coupled == coupled);
    CHECK(p.gamma.coupling_phase_units == c_units);
  } else {
    FAIL("not implemented: plan::GammaOscillator has no coupled and coupling_phase_units (Story 2.3)");
  }
}

plan::Plan compile_plan(const std::string& text, std::uint32_t fs) {
  auto r = plan::compile(text, plan::Mode::Measure, fs, plan::MuteEar::None);
  INFO("rule '" << r.error.rule << "', parameter '" << r.error.parameter << "', value '"
                << r.error.value << "', limit '" << r.error.limit << "'");
  REQUIRE(r.plan.has_value());
  return std::move(*r.plan);
}

// Renders a compiled plan in calls of `block` frames into whole-length
// buffers, every tap written through offset pointers.
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

}  // namespace

// ------------------------------------------------------------ core

TEST_CASE("coupling: the swell and the coupling phase rule have the AD-5 signatures",
          "[coupling][ad5]") {
  // The static_asserts above fix the exact types once the functions exist;
  // here their absence fails.
  CHECK(probe::kSwellDeclared);
  CHECK(probe::kSwellExact);
  CHECK(probe::kPhaseDeclared);
  CHECK(probe::kPhaseExact);
}

TEST_CASE("coupling: the coupling phase rule reproduces every vector row", "[coupling]") {
  bool full_turn = false;
  bool tie_down = false;
  bool tie_even = false;
  for (const auto& v : spec::kCouplingPhases) {
    INFO("coupling phase " << v.deg << " degrees");
    CHECK(v.deg / 360.0 == v.x);  // one binary64 rounding
    CHECK(probe::call_phase_units(v.deg) == v.c_units);
    full_turn = full_turn || (v.deg == 360.0 && v.c_units == 0);
    tie_down = tie_down || (v.x * 0x1p64 == 0.5 && v.c_units == 0);
    tie_even = tie_even || (v.x * 0x1p64 == 1.5 && v.c_units == 2);
  }
  CHECK(full_turn);  // 360 degrees is the same point as 0
  CHECK(tie_down);   // ties to even: 1/2 gives 0
  CHECK(tie_even);   // and 3/2 gives 2
  const auto& r = spec::row("coupling-phase");
  CHECK(r.kind == "ranges");
  CHECK(r.unit == "degrees");
  CHECK(probe::call_phase_units(r.min) == 0);
  CHECK(probe::call_phase_units(r.max) == 0);
}

TEST_CASE("coupling: engine swell, gamma envelope, and coupled amplitude match the vectors",
          "[coupling]") {
  std::set<double> depths;
  std::set<double> phases;
  for (const auto& v : spec::kSwells) {
    INFO("depth " << v.depth_percent << " percent, coupling phase " << v.deg << " degrees, theta "
                  << v.phase_theta_envelope << ", gamma " << v.phase_gamma_envelope);
    CHECK(probe::call_phase_units(v.deg) == v.c_units);
    const double s = probe::call_swell(v.phase_theta_envelope, v.c_units);
    CHECK(api::bits(s) == v.s_bits);
    // s is the sine envelope of p_E - C mod 2^64, bit for bit.
    CHECK(api::bits(s) == api::bits(core::sine_envelope(v.phase_theta_envelope - v.c_units)));
    const double e = core::sine_envelope(v.phase_gamma_envelope);
    CHECK(api::bits(e) == v.e_bits);
    const double d = v.depth_percent / 100.0;
    const double a = law_amplitude(d, s, e);
    CHECK(api::bits(a) == v.a_bits);
    // The engine swell is never 0 or 1.
    CHECK(s > 0.0);
    CHECK(s < 1.0);
    CHECK(a > 0.0);
    CHECK(std::fabs(s - v.ideal_s) <= swell_bound());
    CHECK(std::fabs(a - v.ideal_a) <= amplitude_bound(d));
    depths.insert(v.depth_percent);
    phases.insert(v.deg);
  }
  const auto& depth = spec::row("coupling-depth");
  CHECK(depths.count(depth.min) == 1);
  CHECK(depths.count(depth.max) == 1);
  CHECK(phases.size() == 4);
}

TEST_CASE("coupling: the swell peaks at C and has its trough half a theta cycle on",
          "[coupling]") {
  const std::uint64_t cs[] = {0, 1, 2, kQuarter, kHalf, kHalf + kQuarter, UINT64_C(0xffffffffffffffff)};
  for (const std::uint64_t c : cs) {
    INFO("C " << c);
    CHECK(api::bits(probe::call_swell(c, c)) == api::bits(core::sine_envelope(0)));
    CHECK(api::bits(probe::call_swell(c + kHalf, c)) == api::bits(core::sine_envelope(kHalf)));
    std::size_t mismatches = 0;
    for (std::uint64_t k = 0; k < 4096; ++k) {
      const std::uint64_t p = k * UINT64_C(0x0010000000000123) + UINT64_C(987654321);
      mismatches += api::bits(probe::call_swell(p, c)) != api::bits(core::sine_envelope(p - c)) ? 1 : 0;
    }
    CHECK(mismatches == 0);
  }
}

// ------------------------------------------------------------ renders

TEST_CASE("coupling: swell fixtures render the vector bits through the C API",
          "[coupling][render]") {
  constexpr std::uint64_t kExtra = 64;
  const auto pairs = fixture_rates();
  REQUIRE(pairs.size() == 10);  // five fixtures at two sample rates
  for (const auto& [name, fs] : pairs) {
    INFO(name << " at " << fs);
    const Rendered r = render_fixture(name, fs, kExtra);
    const auto& first = first_vector(name, fs);
    REQUIRE(r.frames == first.frames);
    for (const auto& v : spec::kSwellSamples) {
      if (name != v.fixture || fs != v.fs) {
        continue;
      }
      INFO("n " << v.n << (v.past_end ? " (past end)" : ""));
      const auto i = static_cast<std::size_t>(2 * v.n);
      for (std::size_t c = 0; c < 2; ++c) {
        CHECK(api::bits(r.taps.gamma_pac[i + c]) == v.gamma_bits);
        CHECK(api::bits(r.taps.theta_reference[i + c]) == v.theta_bits);
        CHECK(api::bits(r.taps.stereo_bus[i + c]) == v.bus_bits);
        CHECK(api::bits(r.out[i + c]) == v.bus_bits);  // no binaural layer
      }
    }
    const auto live = static_cast<std::size_t>(2 * r.frames);
    if (!first.has_theta) {
      CHECK(api::all_exact_zero(r.taps.theta_reference));
    }
    CHECK(api::same_bytes(r.out, r.taps.stereo_bus));
    CHECK(api::same_bytes(r.out, r.taps.master));
    CHECK(api::all_exact_zero(r.taps.gamma_pac.data() + live, 2 * kExtra));
    CHECK(api::all_exact_zero(r.out.data() + live, 2 * kExtra));
  }
}

TEST_CASE("coupling: the coupled gamma tap equals the swell law sample by sample, never -0.0",
          "[coupling][render]") {
  for (const auto& [name, fs] : fixture_rates()) {
    INFO(name << " at " << fs);
    const auto& v = first_vector(name, fs);
    const Rendered r = render_fixture(name, fs);
    REQUIRE(r.frames == v.frames);
    CHECK(probe::call_phase_units(v.coupling_phase_deg) == v.c_units);
    CHECK(v.inc_theta_envelope == (v.has_theta ? core::phase_increment(6.0, fs) : 0));
    const double d = v.depth_percent / 100.0;
    std::size_t mismatches = 0;
    std::size_t negative_zero = 0;
    std::size_t channel_differs = 0;
    for (std::uint64_t n = 0; n < r.frames; ++n) {
      const double s = probe::call_swell(n * v.inc_theta_envelope, v.c_units);
      const double e = core::sine_envelope(n * v.inc_rate);
      const double want = law_amplitude(d, s, e) * core::sine(n * v.inc_carrier);
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

TEST_CASE("coupling: seek to a vector index renders that index's bits", "[coupling][seek]") {
  for (const auto& [name, fs] : fixture_rates()) {
    auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
    auto renderer = api::renderer(p.get());
    for (const auto& v : spec::kSwellSamples) {
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
      CHECK(api::bits(taps.theta_reference[0]) == v.theta_bits);
      CHECK(api::bits(taps.stereo_bus[1]) == v.bus_bits);
      CHECK(api::bits(out[0]) == v.bus_bits);
    }
  }
}

TEST_CASE("coupling: seek to any frame equals the continuous render", "[coupling][seek]") {
  for (const char* name : kCoupledFixtures) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(name << " at " << fs);
      const Rendered whole = render_fixture(name, fs);
      auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
      auto renderer = api::renderer(p.get());
      const std::uint64_t starts[] = {1, 63, 64, 65, whole.frames / 3, whole.frames / 2 + 7,
                                      whole.frames - 512};
      for (const std::uint64_t k : starts) {
        INFO("seek to " << k);
        constexpr std::size_t kLen = 512;
        api::seek(renderer.get(), k);
        api::TapBuffers taps(kLen);
        arc_taps t = taps.taps();
        const auto out = api::render(renderer.get(), kLen, &t);
        const auto at = static_cast<std::size_t>(2 * k);
        CHECK(api::same_bytes(out.data(), whole.out.data() + at, 2 * kLen));
        CHECK(api::same_bytes(taps.gamma_pac.data(), whole.taps.gamma_pac.data() + at, 2 * kLen));
        CHECK(api::same_bytes(taps.theta_reference.data(), whole.taps.theta_reference.data() + at,
                              2 * kLen));
      }
    }
  }
}

TEST_CASE("coupling: every block size of row block-sizes gives the same bytes",
          "[coupling][blocks]") {
  const auto& sizes = spec::row("block-sizes");
  const double allowed = spec::row("block-size-invariance").value();
  REQUIRE_FALSE(sizes.values.empty());
  for (const char* name : kCoupledFixtures) {
    const std::string text = api::valid(name);
    for (const std::uint32_t fs : spec::sample_rates()) {
      const Rendered whole = render_text(text, fs);
      for (const double size : sizes.values) {
        INFO(name << " at " << fs << ", " << size << " frames per call");
        const Rendered r = render_in_blocks(text, fs, static_cast<std::size_t>(size));
        CHECK(static_cast<double>(differing_bytes(r.out, whole.out)) <= allowed);
        CHECK(static_cast<double>(differing_bytes(r.taps.gamma_pac, whole.taps.gamma_pac)) <= allowed);
        CHECK(static_cast<double>(differing_bytes(r.taps.theta_reference, whole.taps.theta_reference)) <=
              allowed);
      }
    }
  }
}

// ------------------------------------------------------------ AD-5: only the theta envelope phase

TEST_CASE("coupling: another theta carrier, depth, or shape at the same rate leaves the gamma tap",
          "[coupling][ad5]") {
  struct Theta {
    const char* carrier;
    const char* depth;
    const char* shape;
  };
  const Theta others[] = {{"300", "25", "sawtooth"},
                          {"100", "100", "reverse_saw"},
                          {"500", "50", "smoothed_on_off"},
                          {"450", "75", "smoothed_on_off"},
                          {"200", "75", "sine"}};
  for (const char* phase : {"0", "90", "270"}) {
    for (const char* depth : {"25", "100"}) {
      const std::string base = swell_recipe(kBaseTheta, depth, phase);
      for (const std::uint32_t fs : spec::sample_rates()) {
        const Rendered want = render_text(base, fs);
        for (const auto& o : others) {
          INFO("phase " << phase << ", gamma depth " << depth << ", fs " << fs << ", theta "
                        << o.carrier << " Hz " << o.depth << " percent " << o.shape);
          const Rendered r =
              render_text(swell_recipe(theta_member(o.carrier, "6", o.depth, o.shape), depth, phase), fs);
          CHECK(api::same_bytes(r.taps.gamma_pac, want.taps.gamma_pac));
          // The theta reference really changed.
          CHECK_FALSE(api::same_bytes(r.taps.theta_reference, want.taps.theta_reference));
        }
      }
    }
  }
}

TEST_CASE("coupling: changing the theta rate changes the coupled gamma tap", "[coupling][ad5]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const Rendered six = render_text(swell_recipe(kBaseTheta, "100", "90"), fs);
    const Rendered five =
        render_text(swell_recipe(theta_member("450", "5", "75", "sine"), "100", "90"), fs);
    CHECK_FALSE(api::same_bytes(five.taps.gamma_pac, six.taps.gamma_pac));
    // Control: the uncoupled gamma tap reads nothing from the theta reference.
    const Rendered u6 = render_text(swell_recipe(kBaseTheta, "100", "", "uncoupled"), fs);
    const Rendered u5 =
        render_text(swell_recipe(theta_member("450", "5", "75", "sine"), "100", "", "uncoupled"), fs);
    CHECK(api::same_bytes(u5.taps.gamma_pac, u6.taps.gamma_pac));
  }
}

TEST_CASE("coupling: a binaural layer and a muted ear leave the coupled gamma tap",
          "[coupling][ad5][isolation]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    const Rendered alone = render_text(swell_recipe(kBaseTheta, "100", "90"), fs);
    const std::string with = swell_recipe(kBaseTheta, "100", "90", "smooth_swell", kBinaural);
    for (const arc_mute_ear mute : {ARC_MUTE_NONE, ARC_MUTE_LEFT, ARC_MUTE_RIGHT}) {
      INFO("fs " << fs << ", mute " << mute);
      const Rendered r = render_text(with, fs, 0, mute);
      CHECK(api::same_bytes(r.taps.gamma_pac, alone.taps.gamma_pac));
      CHECK(api::same_bytes(r.taps.theta_reference, alone.taps.theta_reference));
      CHECK(api::same_bytes(r.taps.stereo_bus, alone.taps.stereo_bus));
    }
    // The binaural layer is really in the output.
    const Rendered r = render_text(with, fs);
    CHECK_FALSE(api::same_bytes(api::channel(r.out, 0), api::channel(r.out, 1)));
  }
}

// ------------------------------------------------------------ phase edges and depth 0

TEST_CASE("coupling: phase 0 and 360 render the same bytes", "[coupling][phase]") {
  for (const char* depth : {"25", "100"}) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO("depth " << depth << ", fs " << fs);
      const Rendered zero = render_text(swell_recipe(kBaseTheta, depth, "0"), fs);
      const Rendered full = render_text(swell_recipe(kBaseTheta, depth, "360"), fs);
      CHECK(api::same_bytes(zero.out, full.out));
      CHECK(api::same_bytes(zero.taps.gamma_pac, full.taps.gamma_pac));
      CHECK(api::same_bytes(zero.taps.stereo_bus, full.taps.stereo_bus));
      // 359.99 degrees is another point: its gamma tap differs.
      const Rendered near = render_text(swell_recipe(kBaseTheta, depth, "359.99"), fs);
      CHECK_FALSE(api::same_bytes(near.taps.gamma_pac, zero.taps.gamma_pac));
    }
  }
}

TEST_CASE("coupling: coupled gamma at depth 0 is the unmodulated carrier, theta or not",
          "[coupling][depth]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    const std::uint64_t inc = core::phase_increment(250.0, fs);
    for (const bool theta : {false, true}) {
      INFO("fs " << fs << ", theta " << theta);
      const Rendered r = render_text(swell_recipe(theta ? kBaseTheta : "", "0", "90"), fs);
      std::size_t mismatches = 0;
      for (std::uint64_t n = 0; n < r.frames; ++n) {
        const std::uint64_t want = api::bits(core::sine(n * inc));
        const auto i = static_cast<std::size_t>(2 * n);
        mismatches += api::bits(r.taps.gamma_pac[i]) != want ? 1 : 0;
        mismatches += api::bits(r.taps.gamma_pac[i + 1]) != want ? 1 : 0;
      }
      CHECK(mismatches == 0);
    }
    // The committed fixture equals uncoupled gamma at depth 0, bit for bit.
    INFO(kDepth0NoTheta << " at " << fs);
    const Rendered fixture = render_fixture(kDepth0NoTheta, fs);
    const Rendered uncoupled =
        render_text(swell_recipe("", "0", "", "uncoupled", "", "5"), fs);
    REQUIRE(fixture.frames == uncoupled.frames);
    CHECK(api::same_bytes(fixture.taps.gamma_pac, uncoupled.taps.gamma_pac));
    CHECK(api::same_bytes(fixture.out, uncoupled.out));
  }
}

TEST_CASE("coupling: the coupled carrier never stops, only the AM depth varies",
          "[coupling][depth]") {
  const double tol = 4.0 * b();
  for (const char* name : kCoupledFixtures) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(name << " at " << fs);
      const auto& v = first_vector(name, fs);
      const Rendered r = render_fixture(name, fs);
      const double d = v.depth_percent / 100.0;
      double lowest = 2.0;
      double lowest_at_trough = 2.0;
      std::size_t at_trough = 0;
      for (std::uint64_t n = 0; n < r.frames; ++n) {
        const double carrier = core::sine(n * v.inc_carrier);
        if (std::fabs(carrier) < 0.5) {
          continue;
        }
        const double a = r.taps.gamma_pac[static_cast<std::size_t>(2 * n)] / carrier;
        lowest = std::min(lowest, a);
        // Within 1/64 theta cycle of the swell trough (C + 2^63).
        const auto off = static_cast<std::int64_t>(n * v.inc_theta_envelope - v.c_units - kHalf);
        if (off >= -(INT64_C(1) << 58) && off <= (INT64_C(1) << 58)) {
          lowest_at_trough = std::min(lowest_at_trough, a);
          ++at_trough;
        }
      }
      CHECK(lowest > 0.0);
      CHECK(lowest >= (1.0 - d) - tol);
      REQUIRE(at_trough > 0);
      // At the swell trough the AM depth is near 0: the carrier is nearly
      // unmodulated whatever the recipe depth.
      const double s_max = (1.0 - std::cos(2.0 * 3.14159265358979323846 / 64.0)) / 2.0;
      CHECK(lowest_at_trough >= 1.0 - d * s_max - tol);
    }
  }
}

// ------------------------------------------------------------ plan

TEST_CASE("coupling: the plan holds coupled and the coupling phase units", "[coupling][plan]") {
  for (const auto& [name, fs] : fixture_rates()) {
    INFO(name << " at " << fs);
    const auto& v = first_vector(name, fs);
    const plan::Plan p = compile_plan(api::valid(name), fs);
    CHECK(p.frame_count == v.frames);
    CHECK(p.gamma.present);
    CHECK(p.gamma.increment == v.inc_carrier);
    CHECK(p.gamma.envelope_increment == v.inc_rate);
    CHECK(api::bits(p.gamma.depth) == api::bits(v.depth_percent / 100.0));
    CHECK(p.theta.present == v.has_theta);
    if (v.has_theta) {
      CHECK(p.theta.envelope_increment == v.inc_theta_envelope);
    }
    check_coupling_plan(p, true, v.c_units);
  }
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("uncoupled, fs " << fs);
    const plan::Plan p = compile_plan(api::valid("theta-gamma-uncoupled.json"), fs);
    check_coupling_plan(p, false, 0);
  }
}

TEST_CASE("coupling: swell vector rows cover both rates, the fixtures, and past the end",
          "[coupling]") {
  std::set<std::pair<std::string, std::uint32_t>> signal, past;
  for (const auto& v : spec::kSwellSamples) {
    (v.past_end ? past : signal).insert({v.fixture, v.fs});
    CHECK(v.past_end == (v.n >= v.frames));
    CHECK(v.phase_carrier == v.n * v.inc_carrier);
    CHECK(v.phase_rate == v.n * v.inc_rate);
    CHECK(v.phase_theta_envelope == v.n * v.inc_theta_envelope);
    if (!v.has_theta) {
      CHECK(v.inc_theta_envelope == 0);
    }
  }
  CHECK(signal.size() == 10);
  CHECK(past == signal);
  std::set<std::string> names;
  for (const auto& [name, fs] : signal) {
    names.insert(name);
  }
  for (const char* name : kCoupledFixtures) {
    CHECK(names.count(name) == 1);
  }
  CHECK(names.count(kDepth0NoTheta) == 1);
}

#else

TEST_CASE("coupled gamma is implemented", "[coupling]") {
  FAIL("not implemented: core/envelope.hpp or plan/plan.hpp (Story 2.3)");
}

#endif
