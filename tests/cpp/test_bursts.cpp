// Gamma PAC layer, coupled 50 ms bursts (Story 2.4; docs/signal-spec.md,
// Bursts).
//
// With coupling bursts the gamma AM depth opens once per theta cycle for
// 50 ms, centered on the coupling phase, with 10 ms raised-cosine edges
// inside (a 30 ms plateau), and is 0 for the rest of the cycle:
//
//   C  = coupling phase rule (coupling_phase_deg)            once per plan
//   Hb = nearest((50.0 / 1000.0 / 2) * rate_hz * 2^64)       half the width
//   Wb = nearest((10.0 / 1000.0) * rate_hz * 2^64)           one edge
//   p_E = n * inc_E mod 2^64                                 theta envelope phase
//   u = p_E - C mod 2^64; m = u < 2^63 ? u : 2^64 - u
//   g = 1.0 (m <= Hb - Wb), rc(m - (Hb - Wb)) (m < Hb), else 0.0
//   e = sine_envelope(phase_M)                               the free-running gamma envelope
//   a = 1.0 - (d * g) * (1.0 - e)                            four binary64 operations
//   gamma[c][n] = a * sine(phase_G)                          both channels
//
// rc is the theta reference's half raised cosine with W = Wb: r =
// double(v) / double(Wb), P = ratio_to_phase(r), c = sine(P + 2^62),
// rc = (1.0 + c) * 0.5.
//
// Expected interface (spec Implementation Notes), engine/src/core/envelope.hpp,
// namespace arcani::core:
//
//   inline constexpr double kBurstWidthMs = 50.0;
//   inline constexpr double kBurstEdgeMs = 10.0;
//   std::uint64_t burst_half_width_units(double rate_hz) noexcept;   // Hb
//   std::uint64_t burst_edge_units(double rate_hz) noexcept;         // Wb
//   double burst(std::uint64_t theta_envelope_phase, std::uint64_t coupling_phase_units,
//                std::uint64_t half_width_units, std::uint64_t edge_units) noexcept;
//
// recipe::GammaCoupling gains Bursts; plan::GammaOscillator keeps coupled
// (true for smooth_swell and bursts) and coupling_phase_units, and gains
//
//   recipe::GammaCoupling coupling;          // the kind
//   std::uint64_t burst_half_width_units;    // Hb, 0 unless bursts
//   std::uint64_t burst_edge_units;          // Wb, 0 unless bursts
//
// AD-5 structural: a static_assert pins the exact type of &core::burst, so its
// only signal input is the theta envelope phase (the other three arguments are
// the plan constants C, Hb, and Wb). The core names are reached through a
// lookup probe (a global fallback that the real declaration hides) and the
// plan members through a requires-expression, so the suite builds before they
// exist and the missing pieces show as failing test cases.
//
// Every render check reaches the engine through the public C API. Vectors
// come from the generated spec_tables.hpp (kBurstWidthMs, kBurstEdgeMs,
// kBurstEdges, kBurstGates, kBurstAmplitudes, kBurstSamples); rows from the
// tables through the assertion call. Fixtures (recipes/fixtures/valid/):
// bursts-40hz.json, bursts-45hz.json, bursts-60hz.json (a 450 Hz carrier
// amplitude-modulated at 6 Hz by the sine envelope, 75 percent AM depth, plus
// a 250 Hz sine carrier amplitude-modulated at 40, 45, or 60 Hz whose AM
// depth opens to 100 percent in 50 ms bursts centered on coupling phase 0
// degrees; 5 s).

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
#include <bit>
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
// Global fallbacks. Inside arcani::burst_probe a using-directive makes the
// names of arcani::core visible as members of arcani, which unqualified
// lookup reaches before the global namespace: a real core::burst,
// core::burst_half_width_units, core::burst_edge_units, core::kBurstWidthMs,
// or core::kBurstEdgeMs hides its fallback. Each fallback function is
// callable, so the calls below compile either way; it returns a value no
// vector holds.

namespace burst_missing {
struct MissingBurst {
  template <class... A>
  double operator()(A...) const noexcept {
    return std::numeric_limits<double>::quiet_NaN();
  }
};
struct MissingUnits {
  template <class... A>
  std::uint64_t operator()(A...) const noexcept {
    return UINT64_C(0xdeadbeefdeadbeef);
  }
};
struct MissingConstant {
  constexpr operator double() const noexcept { return -1.0; }
};
}  // namespace burst_missing

inline constexpr burst_missing::MissingBurst burst{};
inline constexpr burst_missing::MissingUnits burst_half_width_units{};
inline constexpr burst_missing::MissingUnits burst_edge_units{};
inline constexpr burst_missing::MissingConstant kBurstWidthMs{};
inline constexpr burst_missing::MissingConstant kBurstEdgeMs{};

namespace arcani::burst_probe {

using namespace arcani::core;

using BurstFn = double (*)(std::uint64_t, std::uint64_t, std::uint64_t, std::uint64_t) noexcept;
using UnitsFn = std::uint64_t (*)(double) noexcept;

inline constexpr bool kBurstDeclared =
    !std::is_same_v<std::remove_cvref_t<decltype(burst)>, ::burst_missing::MissingBurst>;
inline constexpr bool kBurstExact = std::is_same_v<decltype(&burst), BurstFn>;
inline constexpr bool kHalfWidthDeclared =
    !std::is_same_v<std::remove_cvref_t<decltype(burst_half_width_units)>, ::burst_missing::MissingUnits>;
inline constexpr bool kHalfWidthExact = std::is_same_v<decltype(&burst_half_width_units), UnitsFn>;
inline constexpr bool kEdgeDeclared =
    !std::is_same_v<std::remove_cvref_t<decltype(burst_edge_units)>, ::burst_missing::MissingUnits>;
inline constexpr bool kEdgeExact = std::is_same_v<decltype(&burst_edge_units), UnitsFn>;
inline constexpr bool kWidthDeclared =
    !std::is_same_v<std::remove_cvref_t<decltype(kBurstWidthMs)>, ::burst_missing::MissingConstant>;
inline constexpr bool kEdgeConstantDeclared =
    !std::is_same_v<std::remove_cvref_t<decltype(kBurstEdgeMs)>, ::burst_missing::MissingConstant>;

// AD-5 structural: the engine burst gate is one function of (theta envelope
// phase, plan constants C, Hb, Wb) and nothing else.
static_assert(!kBurstDeclared || kBurstExact,
              "arcani::core::burst must be exactly double(std::uint64_t, std::uint64_t, std::uint64_t, "
              "std::uint64_t) noexcept (AD-5: its only signal input is the theta envelope phase)");
static_assert(!kHalfWidthDeclared || kHalfWidthExact,
              "arcani::core::burst_half_width_units must be exactly std::uint64_t(double) noexcept");
static_assert(!kEdgeDeclared || kEdgeExact,
              "arcani::core::burst_edge_units must be exactly std::uint64_t(double) noexcept");

inline double call_burst(std::uint64_t theta_envelope_phase, std::uint64_t c, std::uint64_t hb,
                         std::uint64_t wb) {
  return burst(theta_envelope_phase, c, hb, wb);
}

inline std::uint64_t call_half_width(double rate_hz) { return burst_half_width_units(rate_hz); }

inline std::uint64_t call_edge(double rate_hz) { return burst_edge_units(rate_hz); }

inline double width_ms() { return static_cast<double>(kBurstWidthMs); }

inline double edge_ms() { return static_cast<double>(kBurstEdgeMs); }

}  // namespace arcani::burst_probe

namespace api = arcani::test::api;
namespace core = arcani::core;
namespace plan = arcani::plan;
namespace probe = arcani::burst_probe;
namespace spec = arcani::test::spec;

namespace {

constexpr std::uint64_t kQuarter = UINT64_C(1) << 62;
constexpr std::uint64_t kHalf = UINT64_C(1) << 63;
constexpr std::uint64_t kNegativeZero = UINT64_C(0x8000000000000000);

// b, the sine error bound (row sine-error), as a linear amplitude.
double b() { return spec::sine_error_bound_linear(); }

// |g - g_ideal| <= b / 2 + 2^-48 (signal spec, Bursts, Error bound).
double gate_bound() { return b() / 2.0 + 0x1p-48; }

// |a - a_ideal| <= d * b + 2^-47.
double amplitude_bound(double d) { return d * b() + 0x1p-47; }

// The coupled depth law, four binary64 operations in the spec's order.
double law_amplitude(double d, double g, double e) {
  const double dg = d * g;
  const double one_minus_e = 1.0 - e;
  return 1.0 - dg * one_minus_e;
}

// The uncoupled depth law (Gamma PAC layer, AM law).
double uncoupled_amplitude(double d, double e) { return 1.0 - d * (1.0 - e); }

// The burst gate built here from the spec text and the engine core pieces
// (sine, ratio_to_phase): segments by exact integer comparisons, the edge the
// theta reference's half raised cosine with W = Wb.
double spec_gate(std::uint64_t p, std::uint64_t c, std::uint64_t hb, std::uint64_t wb) {
  const std::uint64_t u = p - c;
  const std::uint64_t m = u < kHalf ? u : std::uint64_t{0} - u;
  if (m <= hb - wb) {
    return 1.0;
  }
  if (m < hb) {
    const std::uint64_t v = m - (hb - wb);
    const double r = static_cast<double>(v) / static_cast<double>(wb);
    const double cosine = core::sine(core::ratio_to_phase(r) + kQuarter);
    return (1.0 + cosine) * 0.5;
  }
  return 0.0;
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

// (fixture, fs) pairs of kBurstSamples, in vector order.
std::vector<std::pair<std::string, std::uint32_t>> fixture_rates() {
  std::vector<std::pair<std::string, std::uint32_t>> out;
  for (const auto& v : spec::kBurstSamples) {
    const std::pair<std::string, std::uint32_t> key{v.fixture, v.fs};
    if (std::find(out.begin(), out.end(), key) == out.end()) {
      out.push_back(key);
    }
  }
  return out;
}

const spec::BurstSampleVector& first_vector(const std::string& name, std::uint32_t fs) {
  for (const auto& v : spec::kBurstSamples) {
    if (name == v.fixture && fs == v.fs) {
      return v;
    }
  }
  FAIL("no burst sample vector for " << name << " at " << fs);
  return spec::kBurstSamples[0];
}

const char* const kBurstFixtures[] = {"bursts-40hz.json", "bursts-45hz.json", "bursts-60hz.json"};

// A recipe made here. theta and binaural are JSON members with a trailing
// ", " (empty drops the layer); an empty phase omits coupling_phase_deg.
std::string burst_recipe(const std::string& theta, const std::string& depth, const std::string& phase,
                         const std::string& coupling = "bursts", const std::string& binaural = "",
                         const std::string& length = "1", const std::string& gamma_rate = "40") {
  std::string gamma = "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": " + gamma_rate +
                      ", \"am_depth_percent\": " + depth +
                      ", \"carrier_wave\": \"sine\", \"coupling\": \"" + coupling + "\"";
  if (!phase.empty()) {
    gamma += ", \"coupling_phase_deg\": " + phase;
  }
  gamma += "}";
  return "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
         "\"author\": \"Arcani test\", \"date\": \"2026-11-13\", "
         "\"rationale\": \"Burst gamma test, made in the test.\", "
         "\"length_s\": " + length + ", \"loudness_target_lufs\": -36, " + theta + binaural +
         gamma + "}";
}

std::string theta_member(const char* carrier, const char* rate, const char* depth, const char* shape) {
  return std::string("\"theta_reference\": {\"carrier_hz\": ") + carrier + ", \"rate_hz\": " + rate +
         ", \"am_depth_percent\": " + depth + ", \"shape\": \"" + shape + "\"}, ";
}

const std::string kBaseTheta = theta_member("450", "6", "75", "sine");
const std::string kBinaural = "\"binaural\": {\"carrier_left_hz\": 400, \"beat_rate_hz\": 6}, ";

template <class E>
concept HasBursts = requires { E::Bursts; };

template <class P>
concept PlanHasBursts = requires(const P& p) {
  { p.gamma.coupled } -> std::convertible_to<bool>;
  { p.gamma.coupling_phase_units } -> std::convertible_to<std::uint64_t>;
  { p.gamma.burst_half_width_units } -> std::convertible_to<std::uint64_t>;
  { p.gamma.burst_edge_units } -> std::convertible_to<std::uint64_t>;
  p.gamma.coupling;
};

enum class Kind { Uncoupled, SmoothSwell, Bursts };

template <class P>
void check_burst_plan(const P& p, Kind kind, std::uint64_t c_units, std::uint64_t hb, std::uint64_t wb) {
  if constexpr (PlanHasBursts<P>) {
    using K = std::remove_cvref_t<decltype(p.gamma.coupling)>;
    if constexpr (HasBursts<K>) {
      const K want = kind == Kind::Bursts ? K::Bursts
                                          : (kind == Kind::SmoothSwell ? K::SmoothSwell : K::Uncoupled);
      CHECK(p.gamma.coupling == want);
    } else {
      FAIL("not implemented: recipe::GammaCoupling has no Bursts (Story 2.4)");
    }
    CHECK(p.gamma.coupled == (kind != Kind::Uncoupled));
    CHECK(p.gamma.coupling_phase_units == c_units);
    CHECK(p.gamma.burst_half_width_units == hb);
    CHECK(p.gamma.burst_edge_units == wb);
  } else {
    FAIL("not implemented: plan::GammaOscillator has no coupling, burst_half_width_units, and "
         "burst_edge_units (Story 2.4)");
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

bool is_edge(std::string_view segment) { return segment == "falling edge" || segment == "rising edge"; }

}  // namespace

// ------------------------------------------------------------ core

TEST_CASE("bursts: the gate and the width and edge rules have the AD-5 signatures", "[bursts][ad5]") {
  // The static_asserts above fix the exact types once the functions exist;
  // here their absence fails.
  CHECK(probe::kBurstDeclared);
  CHECK(probe::kBurstExact);
  CHECK(probe::kHalfWidthDeclared);
  CHECK(probe::kHalfWidthExact);
  CHECK(probe::kEdgeDeclared);
  CHECK(probe::kEdgeExact);
}

TEST_CASE("bursts: the fixed constants equal the vectors and rows burst-width and burst-edge",
          "[bursts]") {
  CHECK(probe::kWidthDeclared);
  CHECK(probe::kEdgeConstantDeclared);
  const auto& width = spec::row("burst-width");
  const auto& edge = spec::row("burst-edge");
  CHECK(width.kind == "ranges");
  CHECK(edge.kind == "ranges");
  CHECK(width.unit == "ms");
  CHECK(edge.unit == "ms");
  // Fixed rows: min equal to max.
  CHECK(width.min == width.max);
  CHECK(edge.min == edge.max);
  CHECK(spec::kBurstWidthMs == width.min);
  CHECK(spec::kBurstEdgeMs == edge.min);
  CHECK(probe::width_ms() == spec::kBurstWidthMs);
  CHECK(probe::edge_ms() == spec::kBurstEdgeMs);
  // Each edge fits beside the plateau: Wb < Hb - Wb (10 ms against 15 ms).
  CHECK(spec::kBurstEdgeMs < spec::kBurstWidthMs / 2.0 - spec::kBurstEdgeMs);
}

TEST_CASE("bursts: Hb and Wb reproduce every vector row", "[bursts]") {
  std::set<double> rates;
  for (const auto& v : spec::kBurstEdges) {
    INFO("theta rate " << v.rate_hz << " Hz");
    CHECK(probe::call_half_width(v.rate_hz) == v.hb_units);
    CHECK(probe::call_edge(v.rate_hz) == v.wb_units);
    // The spec rule, from the binary64 operations it names.
    const double w_h = (50.0 / 1000.0 / 2) * v.rate_hz;
    const double w_w = (10.0 / 1000.0) * v.rate_hz;
    CHECK(static_cast<std::uint64_t>(std::nearbyint(w_h * 0x1p64)) == v.hb_units);
    CHECK(static_cast<std::uint64_t>(std::nearbyint(w_w * 0x1p64)) == v.wb_units);
    // Wb < Hb - Wb, and a burst lies inside half a theta cycle.
    CHECK(v.wb_units < v.hb_units - v.wb_units);
    CHECK(v.hb_units < kHalf);
    rates.insert(v.rate_hz);
  }
  const auto& theta_rate = spec::hz_range("theta-rate");
  CHECK(rates.count(theta_rate.min) == 1);
  CHECK(rates.count(theta_rate.max) == 1);
}

TEST_CASE("bursts: the engine gate reproduces every gate vector bit for bit", "[bursts]") {
  std::set<std::string> segments;
  std::set<double> phases;
  for (const auto& v : spec::kBurstGates) {
    INFO("theta rate " << v.rate_hz << ", coupling phase " << v.deg << ", theta phase "
                       << v.phase_theta_envelope << ", segment " << v.segment);
    CHECK(probe::call_half_width(v.rate_hz) == v.hb_units);
    CHECK(probe::call_edge(v.rate_hz) == v.wb_units);
    CHECK(core::coupling_phase_units(v.deg) == v.c_units);
    CHECK(v.phase_theta_envelope - v.c_units == v.u);
    const double g = probe::call_burst(v.phase_theta_envelope, v.c_units, v.hb_units, v.wb_units);
    CHECK(api::bits(g) == v.g_bits);
    CHECK(api::bits(spec_gate(v.phase_theta_envelope, v.c_units, v.hb_units, v.wb_units)) == v.g_bits);
    CHECK(std::fabs(g - v.ideal_g) <= gate_bound());
    const std::string_view seg(v.segment);
    if (seg == "center" || seg == "plateau") {
      CHECK(api::bits(g) == api::bits(1.0));
    } else if (seg == "off") {
      CHECK(api::bits(g) == 0);  // +0.0, never -0.0
    } else {
      CHECK(is_edge(seg));
      CHECK(g >= 0.0);
      CHECK(g <= 1.0);
    }
    segments.insert(v.segment);
    phases.insert(v.deg);
  }
  CHECK(segments == std::set<std::string>{"center", "plateau", "falling edge", "rising edge", "off"});
  CHECK(phases.size() == 2);
}

TEST_CASE("bursts: the gate is centered on C, mirror-symmetric, and 0 half a cycle away",
          "[bursts]") {
  for (const auto& e : spec::kBurstEdges) {
    const std::uint64_t hb = e.hb_units;
    const std::uint64_t wb = e.wb_units;
    const std::uint64_t cs[] = {0, 1, kQuarter, kHalf, kHalf + kQuarter, UINT64_C(0xffffffffffffffff)};
    for (const std::uint64_t c : cs) {
      INFO("theta rate " << e.rate_hz << ", C " << c);
      CHECK(api::bits(probe::call_burst(c, c, hb, wb)) == api::bits(1.0));
      CHECK(api::bits(probe::call_burst(c + kHalf, c, hb, wb)) == 0);
      CHECK(api::bits(probe::call_burst(c + (hb - wb), c, hb, wb)) == api::bits(1.0));
      CHECK(api::bits(probe::call_burst(c - (hb - wb), c, hb, wb)) == api::bits(1.0));
      CHECK(api::bits(probe::call_burst(c + hb, c, hb, wb)) == 0);
      CHECK(api::bits(probe::call_burst(c - hb, c, hb, wb)) == 0);
      std::size_t mismatches = 0;
      std::size_t asymmetric = 0;
      for (std::uint64_t k = 0; k < 4096; ++k) {
        // Offsets across the whole burst and past it, both sides.
        const std::uint64_t m = k * (hb / 3000) + UINT64_C(987654321);
        const double up = probe::call_burst(c + m, c, hb, wb);
        const double down = probe::call_burst(c - m, c, hb, wb);
        mismatches += api::bits(up) != api::bits(spec_gate(c + m, c, hb, wb)) ? 1 : 0;
        asymmetric += api::bits(up) != api::bits(down) ? 1 : 0;
      }
      CHECK(mismatches == 0);
      CHECK(asymmetric == 0);
    }
  }
}

TEST_CASE("bursts: gate, gamma envelope, and amplitude match the amplitude vectors", "[bursts]") {
  std::set<double> depths;
  for (const auto& v : spec::kBurstAmplitudes) {
    INFO("depth " << v.depth_percent << " percent, theta phase " << v.phase_theta_envelope << ", gamma "
                  << v.phase_gamma_envelope << ", segment " << v.segment);
    const std::uint64_t hb = probe::call_half_width(v.rate_hz);
    const std::uint64_t wb = probe::call_edge(v.rate_hz);
    const double g = probe::call_burst(v.phase_theta_envelope, 0, hb, wb);  // C = 0
    CHECK(api::bits(g) == v.g_bits);
    const double e = core::sine_envelope(v.phase_gamma_envelope);
    CHECK(api::bits(e) == v.e_bits);
    const double d = v.depth_percent / 100.0;
    const double a = law_amplitude(d, g, e);
    // The vector's own g gives its a: the law alone, apart from the gate.
    CHECK(api::bits(law_amplitude(d, std::bit_cast<double>(v.g_bits), e)) == v.a_bits);
    CHECK(api::bits(a) == v.a_bits);
    CHECK(a > 0.0);
    CHECK(std::fabs(std::bit_cast<double>(v.g_bits) - v.ideal_g) <= gate_bound());
    CHECK(std::fabs(std::bit_cast<double>(v.a_bits) - v.ideal_a) <= amplitude_bound(d));
    const std::string_view seg(v.segment);
    if (seg == "off" || d == 0.0) {
      CHECK(api::bits(std::bit_cast<double>(v.a_bits)) == api::bits(1.0));  // a = 1.0 exactly
    }
    if (seg == "center") {
      // On the plateau the burst law is the uncoupled law, bit for bit.
      CHECK(v.a_bits == api::bits(uncoupled_amplitude(d, e)));
    }
    depths.insert(v.depth_percent);
  }
  const auto& depth = spec::row("coupling-depth");
  CHECK(depths.count(depth.min) == 1);
  CHECK(depths.count(depth.max) == 1);
}

// ------------------------------------------------------------ renders

TEST_CASE("bursts: burst fixtures render the vector bits through the C API", "[bursts][render]") {
  constexpr std::uint64_t kExtra = 64;
  const auto pairs = fixture_rates();
  REQUIRE(pairs.size() == 6);  // three fixtures at two sample rates
  for (const auto& [name, fs] : pairs) {
    INFO(name << " at " << fs);
    const Rendered r = render_fixture(name, fs, kExtra);
    const auto& first = first_vector(name, fs);
    REQUIRE(r.frames == first.frames);
    for (const auto& v : spec::kBurstSamples) {
      if (name != v.fixture || fs != v.fs) {
        continue;
      }
      INFO("n " << v.n << " (" << v.segment << ")");
      const auto i = static_cast<std::size_t>(2 * v.n);
      for (std::size_t c = 0; c < 2; ++c) {
        CHECK(api::bits(r.taps.gamma_pac[i + c]) == v.gamma_bits);
        CHECK(api::bits(r.taps.theta_reference[i + c]) == v.theta_bits);
        CHECK(api::bits(r.taps.stereo_bus[i + c]) == v.bus_bits);
        CHECK(api::bits(r.out[i + c]) == v.bus_bits);  // no binaural layer
      }
    }
    const auto live = static_cast<std::size_t>(2 * r.frames);
    CHECK(api::same_bytes(r.out, r.taps.stereo_bus));
    CHECK(api::same_bytes(r.out, r.taps.master));
    CHECK(api::all_exact_zero(r.taps.gamma_pac.data() + live, 2 * kExtra));
    CHECK(api::all_exact_zero(r.out.data() + live, 2 * kExtra));
  }
}

TEST_CASE("bursts: the gamma tap equals the burst law sample by sample, never -0.0",
          "[bursts][render]") {
  for (const auto& [name, fs] : fixture_rates()) {
    INFO(name << " at " << fs);
    const auto& v = first_vector(name, fs);
    const Rendered r = render_fixture(name, fs);
    REQUIRE(r.frames == v.frames);
    CHECK(core::coupling_phase_units(v.coupling_phase_deg) == v.c_units);
    CHECK(probe::call_half_width(v.theta_rate_hz) == v.hb_units);
    CHECK(probe::call_edge(v.theta_rate_hz) == v.wb_units);
    CHECK(v.inc_theta_envelope == core::phase_increment(v.theta_rate_hz, fs));
    const double d = v.depth_percent / 100.0;
    std::size_t mismatches = 0;
    std::size_t negative_zero = 0;
    std::size_t channel_differs = 0;
    std::size_t off = 0;
    std::size_t off_not_carrier = 0;
    std::size_t plateau = 0;
    std::size_t plateau_not_uncoupled = 0;
    std::size_t edge = 0;
    for (std::uint64_t n = 0; n < r.frames; ++n) {
      const std::uint64_t p = n * v.inc_theta_envelope;
      const double g = probe::call_burst(p, v.c_units, v.hb_units, v.wb_units);
      const double e = core::sine_envelope(n * v.inc_rate);
      const double carrier = core::sine(n * v.inc_carrier);
      const double want = law_amplitude(d, g, e) * carrier;
      const auto i = static_cast<std::size_t>(2 * n);
      const std::uint64_t got = api::bits(r.taps.gamma_pac[i]);
      mismatches += got != api::bits(want) ? 1 : 0;
      negative_zero += got == kNegativeZero ? 1 : 0;
      channel_differs += got != api::bits(r.taps.gamma_pac[i + 1]) ? 1 : 0;
      const double sg = spec_gate(p, v.c_units, v.hb_units, v.wb_units);
      if (sg == 0.0) {
        // Off the burst a = 1.0 exactly: the unmodulated carrier, bit for bit.
        ++off;
        off_not_carrier += got != api::bits(carrier) ? 1 : 0;
      } else if (sg == 1.0) {
        // On the plateau the uncoupled law, bit for bit.
        ++plateau;
        plateau_not_uncoupled += got != api::bits(uncoupled_amplitude(d, e) * carrier) ? 1 : 0;
      } else {
        ++edge;
      }
    }
    CHECK(mismatches == 0);
    CHECK(negative_zero == 0);
    CHECK(channel_differs == 0);
    CHECK(off > 0);
    CHECK(plateau > 0);
    CHECK(edge > 0);
    CHECK(off_not_carrier == 0);
    CHECK(plateau_not_uncoupled == 0);
  }
}

TEST_CASE("bursts: seek to a vector index renders that index's bits", "[bursts][seek]") {
  for (const auto& [name, fs] : fixture_rates()) {
    auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
    auto renderer = api::renderer(p.get());
    for (const auto& v : spec::kBurstSamples) {
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

TEST_CASE("bursts: seek to any frame equals the continuous render", "[bursts][seek]") {
  for (const char* name : kBurstFixtures) {
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

TEST_CASE("bursts: every block size of row block-sizes gives the same bytes", "[bursts][blocks]") {
  const auto& sizes = spec::row("block-sizes");
  const double allowed = spec::row("block-size-invariance").value();
  REQUIRE_FALSE(sizes.values.empty());
  for (const char* name : kBurstFixtures) {
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

TEST_CASE("bursts: another theta carrier, depth, or shape at the same rate leaves the gamma tap",
          "[bursts][ad5]") {
  struct Theta {
    const char* carrier;
    const char* depth;
    const char* shape;
  };
  const Theta others[] = {{"300", "25", "sawtooth"},
                          {"100", "100", "reverse_saw"},
                          {"500", "50", "smoothed_on_off"},
                          {"200", "75", "sine"}};
  for (const char* phase : {"0", "90", "270"}) {
    for (const char* depth : {"25", "100"}) {
      const std::string base = burst_recipe(kBaseTheta, depth, phase);
      for (const std::uint32_t fs : spec::sample_rates()) {
        const Rendered want = render_text(base, fs);
        for (const auto& o : others) {
          INFO("phase " << phase << ", gamma depth " << depth << ", fs " << fs << ", theta "
                        << o.carrier << " Hz " << o.depth << " percent " << o.shape);
          const Rendered r =
              render_text(burst_recipe(theta_member(o.carrier, "6", o.depth, o.shape), depth, phase), fs);
          CHECK(api::same_bytes(r.taps.gamma_pac, want.taps.gamma_pac));
          CHECK_FALSE(api::same_bytes(r.taps.theta_reference, want.taps.theta_reference));
        }
      }
    }
  }
}

TEST_CASE("bursts: changing the theta rate moves the bursts; bursts differ from the swell",
          "[bursts][ad5]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const Rendered six = render_text(burst_recipe(kBaseTheta, "100", "90"), fs);
    const Rendered five = render_text(burst_recipe(theta_member("450", "5", "75", "sine"), "100", "90"), fs);
    CHECK_FALSE(api::same_bytes(five.taps.gamma_pac, six.taps.gamma_pac));
    const Rendered swell = render_text(burst_recipe(kBaseTheta, "100", "90", "smooth_swell"), fs);
    CHECK_FALSE(api::same_bytes(swell.taps.gamma_pac, six.taps.gamma_pac));
    // The theta reference is the same in all of them.
    CHECK(api::same_bytes(swell.taps.theta_reference, six.taps.theta_reference));
  }
}

TEST_CASE("bursts: a binaural layer and a muted ear leave the burst gamma tap",
          "[bursts][ad5][isolation]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    const Rendered alone = render_text(burst_recipe(kBaseTheta, "100", "90"), fs);
    const std::string with = burst_recipe(kBaseTheta, "100", "90", "bursts", kBinaural);
    for (const arc_mute_ear mute : {ARC_MUTE_NONE, ARC_MUTE_LEFT, ARC_MUTE_RIGHT}) {
      INFO("fs " << fs << ", mute " << mute);
      const Rendered r = render_text(with, fs, 0, mute);
      CHECK(api::same_bytes(r.taps.gamma_pac, alone.taps.gamma_pac));
      CHECK(api::same_bytes(r.taps.theta_reference, alone.taps.theta_reference));
      CHECK(api::same_bytes(r.taps.stereo_bus, alone.taps.stereo_bus));
    }
    const Rendered r = render_text(with, fs);
    CHECK_FALSE(api::same_bytes(api::channel(r.out, 0), api::channel(r.out, 1)));
  }
}

// ------------------------------------------------------------ phase edges and depth 0

TEST_CASE("bursts: phase 0 and 360 render the same bytes", "[bursts][phase]") {
  for (const char* depth : {"25", "100"}) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO("depth " << depth << ", fs " << fs);
      const Rendered zero = render_text(burst_recipe(kBaseTheta, depth, "0"), fs);
      const Rendered full = render_text(burst_recipe(kBaseTheta, depth, "360"), fs);
      CHECK(api::same_bytes(zero.out, full.out));
      CHECK(api::same_bytes(zero.taps.gamma_pac, full.taps.gamma_pac));
      const Rendered near = render_text(burst_recipe(kBaseTheta, depth, "359.99"), fs);
      CHECK_FALSE(api::same_bytes(near.taps.gamma_pac, zero.taps.gamma_pac));
    }
  }
}

TEST_CASE("bursts: gamma depth 0 is the unmodulated carrier, a = 1.0 exactly, theta or not",
          "[bursts][depth][ad5]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    const std::uint64_t inc = core::phase_increment(250.0, fs);
    for (const bool theta : {false, true}) {
      INFO("fs " << fs << ", theta " << theta);
      // Accepted at compile without a theta reference (AD-5: depth 0 scales nothing).
      const Rendered r = render_text(burst_recipe(theta ? kBaseTheta : "", "0", "90"), fs);
      std::size_t mismatches = 0;
      for (std::uint64_t n = 0; n < r.frames; ++n) {
        const std::uint64_t want = api::bits(core::sine(n * inc));
        const auto i = static_cast<std::size_t>(2 * n);
        mismatches += api::bits(r.taps.gamma_pac[i]) != want ? 1 : 0;
        mismatches += api::bits(r.taps.gamma_pac[i + 1]) != want ? 1 : 0;
      }
      CHECK(mismatches == 0);
      const Rendered uncoupled = render_text(burst_recipe(theta ? kBaseTheta : "", "0", "", "uncoupled"), fs);
      CHECK(api::same_bytes(r.taps.gamma_pac, uncoupled.taps.gamma_pac));
      CHECK(api::same_bytes(r.out, uncoupled.out));
    }
  }
}

// ------------------------------------------------------------ plan

TEST_CASE("bursts: the plan holds the coupling kind, C, Hb, and Wb", "[bursts][plan]") {
  for (const auto& [name, fs] : fixture_rates()) {
    INFO(name << " at " << fs);
    const auto& v = first_vector(name, fs);
    const plan::Plan p = compile_plan(api::valid(name), fs);
    CHECK(p.frame_count == v.frames);
    CHECK(p.gamma.present);
    CHECK(p.gamma.increment == v.inc_carrier);
    CHECK(p.gamma.envelope_increment == v.inc_rate);
    CHECK(api::bits(p.gamma.depth) == api::bits(v.depth_percent / 100.0));
    CHECK(p.theta.present);
    CHECK(p.theta.envelope_increment == v.inc_theta_envelope);
    check_burst_plan(p, Kind::Bursts, v.c_units, v.hb_units, v.wb_units);
  }
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    // Hb and Wb are 0 unless bursts.
    const plan::Plan swell = compile_plan(api::valid("swell-sine-0deg-100pct.json"), fs);
    check_burst_plan(swell, Kind::SmoothSwell, 0, 0, 0);
    const plan::Plan uncoupled = compile_plan(api::valid("theta-gamma-uncoupled.json"), fs);
    check_burst_plan(uncoupled, Kind::Uncoupled, 0, 0, 0);
    // Without a theta reference (gamma depth 0) the gate never acts:
    // p_E = 0, and Hb and Wb come from no theta rate.
    const plan::Plan alone = compile_plan(burst_recipe("", "0", "90"), fs);
    CHECK_FALSE(alone.theta.present);
    check_burst_plan(alone, Kind::Bursts, core::coupling_phase_units(90.0), 0, 0);
  }
}

TEST_CASE("bursts: burst vector rows cover both rates, the fixtures, and past the end", "[bursts]") {
  std::set<std::pair<std::string, std::uint32_t>> signal, past;
  std::set<std::string> segments;
  for (const auto& v : spec::kBurstSamples) {
    (v.past_end ? past : signal).insert({v.fixture, v.fs});
    CHECK(v.past_end == (v.n >= v.frames));
    CHECK(v.phase_carrier == v.n * v.inc_carrier);
    CHECK(v.phase_rate == v.n * v.inc_rate);
    CHECK(v.phase_theta_envelope == v.n * v.inc_theta_envelope);
    if (!v.past_end) {
      segments.insert(v.segment);
    }
  }
  CHECK(signal.size() == 6);
  CHECK(past == signal);
  std::set<std::string> names;
  for (const auto& [name, fs] : signal) {
    names.insert(name);
  }
  for (const char* name : kBurstFixtures) {
    CHECK(names.count(name) == 1);
  }
  CHECK(segments == std::set<std::string>{"center", "plateau", "falling edge", "rising edge", "off"});
}

// ------------------------------------------------------------ earlier fixtures keep their bytes

TEST_CASE("bursts: every Story 2.2, 2.3, and 2.5 fixture keeps its vector bits", "[bursts][regression]") {
  // One frame at each vector index, reached by seek (cheap for the long
  // binaural fixtures): uncoupled gamma, smooth swell, and binaural output
  // are unchanged by the bursts.
  for (const auto& v : spec::kGammaSamples) {
    if (v.past_end) {
      continue;
    }
    INFO(v.fixture << " at " << v.fs << ", n " << v.n);
    auto p = api::compile_ok(api::valid(v.fixture), api::options(ARC_MODE_MEASURE, v.fs));
    auto renderer = api::renderer(p.get());
    api::seek(renderer.get(), v.n);
    api::TapBuffers taps(1);
    arc_taps t = taps.taps();
    api::render(renderer.get(), 1, &t);
    CHECK(api::bits(taps.gamma_pac[0]) == v.gamma_bits);
    CHECK(api::bits(taps.gamma_pac[1]) == v.gamma_bits);
  }
  for (const auto& v : spec::kSwellSamples) {
    if (v.past_end) {
      continue;
    }
    INFO(v.fixture << " at " << v.fs << ", n " << v.n);
    auto p = api::compile_ok(api::valid(v.fixture), api::options(ARC_MODE_MEASURE, v.fs));
    auto renderer = api::renderer(p.get());
    api::seek(renderer.get(), v.n);
    api::TapBuffers taps(1);
    arc_taps t = taps.taps();
    const auto out = api::render(renderer.get(), 1, &t);
    CHECK(api::bits(taps.gamma_pac[0]) == v.gamma_bits);
    CHECK(api::bits(out[0]) == v.bus_bits);
    CHECK(api::bits(out[1]) == v.bus_bits);
  }
  for (const auto& v : spec::kBinauralSamples) {
    if (v.past_end) {
      continue;
    }
    INFO(v.fixture << " at " << v.fs << ", n " << v.n);
    auto p = api::compile_ok(api::valid(v.fixture), api::options(ARC_MODE_MEASURE, v.fs));
    auto renderer = api::renderer(p.get());
    api::seek(renderer.get(), v.n);
    api::TapBuffers taps(1);
    arc_taps t = taps.taps();
    const auto out = api::render(renderer.get(), 1, &t);
    CHECK(api::bits(taps.binaural_join[0]) == v.left_bits);
    CHECK(api::bits(taps.binaural_join[1]) == v.right_bits);
    CHECK(api::bits(out[0]) == v.left_bits);
    CHECK(api::bits(out[1]) == v.right_bits);
  }
}

#else

TEST_CASE("burst gamma is implemented", "[bursts]") {
  FAIL("not implemented: core/envelope.hpp or plan/plan.hpp (Story 2.4)");
}

#endif
