// Binaural layer and rate curve (Story 2.5; docs/signal-spec.md, Binaural
// layer and Rate curve).
//
// Two pure sines, one per ear. The right carrier is the left carrier plus
// the beat rate; with a beat rate cycle the beat rate follows
// rate(t) = r + s * sin(2 * pi * t / P + phi0) and the right phase is the
// closed-form integral:
//
//   f_C = carrier_left_hz + beat_rate_hz           one binary64 addition
//   phase_L[n] = n * inc_L,  phase_C[n] = n * inc_C        mod 2^64
//   P0 = coupling phase rule (start_phase_deg),  inc_P = inc(1.0 / period_s)
//   K = (swing_hz * period_s) * kInvTwoPi,  c0 = sine(P0 + 2^62)
//   p_P[n] = P0 + n * inc_P,  c[n] = sine(p_P[n] + 2^62)
//   v[n] = K * (c0 - c[n]),  U[n] = cycles-to-units rule (v[n])
//   phase_R[n] = phase_C[n] + U[n] mod 2^64          (U = 0 without a cycle)
//   bin[c][n] = a_c * sine(phase_c[n])
//
// Expected interface, engine/src/core/envelope.hpp, namespace arcani::core:
//
//   std::uint64_t cycles_to_units(double v) noexcept;
//   std::uint64_t rate_cycle_offset(std::uint64_t cycle_phase, double k,
//                                   double c0) noexcept;
//   // U = cycles_to_units(k * (c0 - sine(cycle_phase + 2^62)))
//
// and engine/src/plan/plan.hpp, plan::BinauralEars keeps increment
// {inc_L, inc_C} and amplitude, and gains
//
//   bool cycle = false;
//   std::uint64_t cycle_start = 0;      // P0
//   std::uint64_t cycle_increment = 0;  // inc_P
//   double cycle_k = 0.0;               // K
//   double cycle_c0 = 0.0;              // c0
//
// A muted right ear has cycle false, increment 0, and amplitude 0.0; a muted
// left ear leaves the right ear's cycle in place.
//
// AD-5 structural: a static_assert pins the exact type of
// &core::rate_cycle_offset, so its only signal input is the cycle phase (k
// and c0 are plan constants). The core functions are reached through a lookup
// probe (a global fallback the real declaration hides) and the plan members
// through a requires-expression, so the suite builds before they exist and
// the missing pieces show as failing test cases.
//
// Every render check reaches the engine through the public C API. Vectors
// come from the generated spec_tables.hpp (kInvTwoPi, kSeekSeconds,
// kCyclesToUnits, kRateCycles, kBinauralSamples); rows from the tables
// through the assertion call. Fixtures (recipes/fixtures/valid/):
// binaural-beat-0.json, binaural-beat-6.json, binaural-beat-29.json (a 400 Hz
// pure sine in the left ear and a pure sine at 400 Hz plus 0, 6, or 29 Hz in
// the right ear, 5 s) and binaural-cycle-sleep.json (a 100 Hz pure sine in
// the left ear and a pure sine in the right ear whose beat rate cycles over 0
// to 3 Hz every 60 s from 0 Hz rising, 120 s). None has another layer.

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
#include <initializer_list>
#include <limits>
#include <set>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

// ------------------------------------------------------------ lookup probe
//
// Global fallbacks. Inside arcani::binaural_probe a using-directive makes the
// names of arcani::core visible as members of arcani, which unqualified
// lookup reaches before the global namespace: a real core::cycles_to_units
// or core::rate_cycle_offset hides its fallback. Each fallback is callable,
// so the calls below compile either way; it returns a value no vector holds.

namespace binaural_missing {
struct MissingUnits {
  template <class... A>
  std::uint64_t operator()(A...) const noexcept {
    return UINT64_C(0xdeadbeefdeadbeef);
  }
};
struct MissingOffset {
  template <class... A>
  std::uint64_t operator()(A...) const noexcept {
    return UINT64_C(0xdeadbeefdeadbeef);
  }
};
}  // namespace binaural_missing

inline constexpr binaural_missing::MissingUnits cycles_to_units{};
inline constexpr binaural_missing::MissingOffset rate_cycle_offset{};

namespace arcani::binaural_probe {

using namespace arcani::core;

using UnitsFn = std::uint64_t (*)(double) noexcept;
using OffsetFn = std::uint64_t (*)(std::uint64_t, double, double) noexcept;

inline constexpr bool kUnitsDeclared =
    !std::is_same_v<std::remove_cvref_t<decltype(cycles_to_units)>, ::binaural_missing::MissingUnits>;
inline constexpr bool kUnitsExact = std::is_same_v<decltype(&cycles_to_units), UnitsFn>;
inline constexpr bool kOffsetDeclared =
    !std::is_same_v<std::remove_cvref_t<decltype(rate_cycle_offset)>, ::binaural_missing::MissingOffset>;
inline constexpr bool kOffsetExact = std::is_same_v<decltype(&rate_cycle_offset), OffsetFn>;

static_assert(!kUnitsDeclared || kUnitsExact,
              "arcani::core::cycles_to_units must be exactly std::uint64_t(double) noexcept");
// AD-5 structural: the rate-curve offset is one function of (cycle phase,
// plan constants K and c0) and nothing else; no other layer's value enters.
static_assert(!kOffsetDeclared || kOffsetExact,
              "arcani::core::rate_cycle_offset must be exactly "
              "std::uint64_t(std::uint64_t, double, double) noexcept (its only signal input is the "
              "cycle phase)");

inline std::uint64_t call_units(double v) { return cycles_to_units(v); }

inline std::uint64_t call_offset(std::uint64_t cycle_phase, double k, double c0) {
  return rate_cycle_offset(cycle_phase, k, c0);
}

}  // namespace arcani::binaural_probe

namespace api = arcani::test::api;
namespace core = arcani::core;
namespace plan = arcani::plan;
namespace probe = arcani::binaural_probe;
namespace spec = arcani::test::spec;

namespace {

constexpr std::uint64_t kQuarter = UINT64_C(1) << 62;

const char* const kFixed[] = {"binaural-beat-0.json", "binaural-beat-6.json", "binaural-beat-29.json"};
constexpr const char* kCycleFixture = "binaural-cycle-sleep.json";

// (fixture, fs) pairs of kBinauralSamples, in vector order.
std::vector<std::pair<std::string, std::uint32_t>> fixture_rates() {
  std::vector<std::pair<std::string, std::uint32_t>> out;
  for (const auto& v : spec::kBinauralSamples) {
    const std::pair<std::string, std::uint32_t> key{v.fixture, v.fs};
    if (std::find(out.begin(), out.end(), key) == out.end()) {
      out.push_back(key);
    }
  }
  return out;
}

const spec::BinauralSampleVector& first_vector(const std::string& name, std::uint32_t fs) {
  for (const auto& v : spec::kBinauralSamples) {
    if (name == v.fixture && fs == v.fs) {
      return v;
    }
  }
  FAIL("no binaural sample vector for " << name << " at " << fs);
  return spec::kBinauralSamples[0];
}

const spec::RateCycleVector& rate_cycle_row(double deg, std::uint32_t fs) {
  for (const auto& r : spec::kRateCycles) {
    if (r.start_phase_deg == deg && r.fs == fs) {
      return r;
    }
  }
  FAIL("no rate cycle vector for " << deg << " degrees at " << fs);
  return spec::kRateCycles[0];
}

// The c0 bits of the Sleep swing and period at this start phase and rate.
std::uint64_t c0_bits_of(const spec::BinauralSampleVector& v) {
  return rate_cycle_row(v.start_phase_deg, v.fs).c0_bits;
}

// U[n] by the spec's operations, from the vector constants and the engine
// sine; 0 without a cycle.
std::uint64_t law_units(const spec::BinauralSampleVector& v, std::uint64_t n) {
  if (!v.has_cycle) {
    return 0;
  }
  const double c0 = core::sine(v.p0 + kQuarter);
  const double c = core::sine(v.p0 + n * v.inc_cycle + kQuarter);
  const double d = c0 - c;
  const double value = v.k * d;
  return probe::call_units(value);
}

// ------------------------------------------------------------ recipes

// A recipe made here from JSON members (empty members are left out).
std::string recipe_text(std::initializer_list<std::string> members, const std::string& length = "3") {
  std::string s =
      "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
      "\"author\": \"Arcani test\", \"date\": \"2026-11-12\", "
      "\"rationale\": \"Binaural layer test, made in the test.\", "
      "\"length_s\": " + length + ", \"loudness_target_lufs\": -36";
  for (const auto& m : members) {
    if (!m.empty()) {
      s += ", " + m;
    }
  }
  return s + "}";
}

std::string cycle_member(const std::string& swing, const std::string& period, const std::string& phase) {
  return ", \"beat_rate_cycle\": {\"swing_hz\": " + swing + ", \"period_s\": " + period +
         ", \"start_phase_deg\": " + phase + "}";
}

std::string binaural_member(const std::string& left, const std::string& beat, const std::string& extra = "") {
  return "\"binaural\": {\"carrier_left_hz\": " + left + ", \"beat_rate_hz\": " + beat + extra + "}";
}

// The Sleep cycle (center 1.5 Hz, swing 1.5 Hz, 60 s period) at a start phase,
// on a 100 Hz left carrier.
std::string sleep_member(const std::string& phase, const std::string& waveform = "") {
  return binaural_member("100", "1.5", cycle_member("1.5", "60", phase) + waveform);
}

// A 450 Hz carrier amplitude-modulated at 6 Hz by the sine envelope, 75
// percent AM depth.
const std::string kTheta =
    "\"theta_reference\": {\"carrier_hz\": 450, \"rate_hz\": 6, \"am_depth_percent\": 75, "
    "\"shape\": \"sine\"}";
// A 250 Hz sine carrier amplitude-modulated at 40 Hz whose AM depth swells
// to 100 percent at coupling phase 0 degrees.
const std::string kGamma =
    "\"gamma_pac\": {\"carrier_hz\": 250, \"rate_hz\": 40, \"am_depth_percent\": 100, "
    "\"carrier_wave\": \"sine\", \"coupling\": \"smooth_swell\", \"coupling_phase_deg\": 0}";

// ------------------------------------------------------------ renders

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

// Renders `total` frames continuously in chunks into reused buffers and calls
// visit(start, count, out, taps) for each chunk, so a 120 s render needs no
// whole-length buffer.
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

// ------------------------------------------------------------ plan

template <class E>
concept EarsHaveCycle = requires(const E& e) {
  { e.cycle } -> std::convertible_to<bool>;
  { e.cycle_start } -> std::convertible_to<std::uint64_t>;
  { e.cycle_increment } -> std::convertible_to<std::uint64_t>;
  { e.cycle_k } -> std::convertible_to<double>;
  { e.cycle_c0 } -> std::convertible_to<double>;
};

struct CycleConstants {
  bool cycle = false;
  std::uint64_t start = 0;
  std::uint64_t increment = 0;
  std::uint64_t k_bits = 0;
  std::uint64_t c0_bits = 0;
};

// The plan's cycle constants, or a failed check when plan::BinauralEars does
// not have them yet.
template <class E>
CycleConstants cycle_of(const E& ears) {
  CycleConstants c;
  if constexpr (EarsHaveCycle<E>) {
    c.cycle = static_cast<bool>(ears.cycle);
    c.start = static_cast<std::uint64_t>(ears.cycle_start);
    c.increment = static_cast<std::uint64_t>(ears.cycle_increment);
    c.k_bits = api::bits(static_cast<double>(ears.cycle_k));
    c.c0_bits = api::bits(static_cast<double>(ears.cycle_c0));
  } else {
    FAIL("not implemented: plan::BinauralEars has no cycle, cycle_start, cycle_increment, cycle_k, "
         "cycle_c0 (Story 2.5)");
  }
  return c;
}

plan::Plan compile_plan(const std::string& text, std::uint32_t fs, plan::MuteEar mute = plan::MuteEar::None) {
  auto r = plan::compile(text, plan::Mode::Measure, fs, mute);
  INFO("rule '" << r.error.rule << "', parameter '" << r.error.parameter << "', value '"
                << r.error.value << "', limit '" << r.error.limit << "'");
  REQUIRE(r.plan.has_value());
  return std::move(*r.plan);
}

}  // namespace

// ------------------------------------------------------------ core

TEST_CASE("binaural: the cycles-to-units rule and the rate-curve offset have their signatures",
          "[binaural][ad5]") {
  // The static_asserts above fix the exact types once the functions exist;
  // here their absence fails.
  CHECK(probe::kUnitsDeclared);
  CHECK(probe::kUnitsExact);
  CHECK(probe::kOffsetDeclared);
  CHECK(probe::kOffsetExact);
}

TEST_CASE("binaural: the cycles-to-units rule reproduces every vector row", "[binaural][rate-curve]") {
  bool nan = false;
  bool tie_even = false;
  bool negative_wrap = false;
  for (const auto& v : spec::kCyclesToUnits) {
    INFO(v.label << ": v " << v.v);
    CHECK(probe::call_units(v.v) == v.units);
    nan = nan || std::isnan(v.v);
    tie_even = tie_even || (v.v == 0x1.8p-64 && v.units == 2);
    negative_wrap = negative_wrap || (v.v == -0x1.8p-64 && v.units == UINT64_C(18446744073709551614));
  }
  CHECK(nan);            // the domain check covers NaN
  CHECK(tie_even);       // 3/2 units rounds to 2
  CHECK(negative_wrap);  // -3/2 units rounds to -2, modulo 2^64
  // Whole cycles, NaN, and both infinities are the same point as 0.
  for (const double v : {1.0, -1.0, 2.0, 0x1p52, 0x1p63, std::numeric_limits<double>::infinity(),
                         -std::numeric_limits<double>::infinity(),
                         std::numeric_limits<double>::quiet_NaN()}) {
    INFO("v " << v);
    CHECK(probe::call_units(v) == 0);
  }
  // v and v + 1 are the same point of the cycle (exact for these v).
  for (const double v : {0.25, 0.125, 0.3, -0.3, 0.7}) {
    INFO("v " << v);
    CHECK(probe::call_units(v) == probe::call_units(v + 1.0));
    CHECK(probe::call_units(v) == probe::call_units(v - 2.0));
  }
}

TEST_CASE("binaural: the rate-curve offset is the cycles-to-units rule of K * (c0 - cosine)",
          "[binaural][rate-curve]") {
  const double ks[] = {0.0, 1.0, 0x1.ca5dc1a63c1f8p+3, 27.5};
  const double c0s[] = {0.0, core::sine(kQuarter), core::sine(UINT64_C(0x8000000000000000) + kQuarter), 0.5};
  for (const double k : ks) {
    for (const double c0 : c0s) {
      INFO("k " << k << ", c0 " << c0);
      std::size_t mismatches = 0;
      for (std::uint64_t i = 0; i < 4096; ++i) {
        const std::uint64_t p = i * UINT64_C(0x0010000000000123) + UINT64_C(987654321);
        const double c = core::sine(p + kQuarter);
        const double d = c0 - c;
        const double value = k * d;
        mismatches += probe::call_offset(p, k, c0) != probe::call_units(value) ? 1 : 0;
      }
      CHECK(mismatches == 0);
    }
  }
  // At the start phase the offset is 0: c[0] is c0 bit for bit.
  for (const auto& r : spec::kRateCycles) {
    double c0 = 0.0;
    const std::uint64_t bits = r.c0_bits;
    std::memcpy(&c0, &bits, sizeof c0);
    INFO("start phase " << r.start_phase_deg << " degrees");
    CHECK(probe::call_offset(r.p0, r.k, c0) == 0);
  }
}

TEST_CASE("binaural: the rate cycle vectors follow the once-per-plan constants", "[binaural][rate-curve]") {
  std::set<double> phases;
  for (const auto& r : spec::kRateCycles) {
    INFO("start phase " << r.start_phase_deg << " degrees at " << r.fs);
    CHECK(r.start_phase_deg / 360.0 == r.x);
    CHECK(core::coupling_phase_units(r.start_phase_deg) == r.p0);
    CHECK(1.0 / r.period_s == r.inv_period);
    CHECK(core::phase_increment(r.inv_period, r.fs) == r.inc_cycle);
    CHECK(r.swing_hz * r.period_s == r.swing_period);
    CHECK(api::bits(r.swing_period * spec::kInvTwoPi) == api::bits(r.k));
    CHECK(api::bits(core::sine(r.p0 + kQuarter)) == r.c0_bits);
    phases.insert(r.start_phase_deg);
  }
  CHECK(phases == std::set<double>{0.0, 90.0, 180.0, 270.0, 360.0});
  // The constant is the binary64 nearest 1 / (2 pi).
  CHECK(std::fabs(spec::kInvTwoPi * 6.283185307179586 - 1.0) < 0x1p-51);
  // Start phase 360 is the same point as 0.
  for (const std::uint32_t fs : spec::sample_rates()) {
    CHECK(rate_cycle_row(360.0, fs).p0 == rate_cycle_row(0.0, fs).p0);
    CHECK(rate_cycle_row(360.0, fs).c0_bits == rate_cycle_row(0.0, fs).c0_bits);
    CHECK(rate_cycle_row(90.0, fs).c0_bits == 0);   // +0.0 exactly
    CHECK(rate_cycle_row(270.0, fs).c0_bits == 0);  // +0.0 exactly
  }
}

TEST_CASE("binaural: sample vector rows follow the spec's operations", "[binaural][rate-curve]") {
  std::set<std::pair<std::string, std::uint32_t>> signal, past;
  for (const auto& v : spec::kBinauralSamples) {
    INFO(v.fixture << " at " << v.fs << ", n " << v.n);
    (v.past_end ? past : signal).insert({v.fixture, v.fs});
    CHECK(v.past_end == (v.n >= v.frames));
    CHECK(v.carrier_left_hz + v.beat_rate_hz == v.center_hz);
    CHECK(v.inc_left == core::phase_increment(v.carrier_left_hz, v.fs));
    CHECK(v.inc_center == core::phase_increment(v.center_hz, v.fs));
    CHECK(v.frames == core::seconds_to_samples(v.length_s, v.fs));
    CHECK(v.phase_left == v.n * v.inc_left);
    CHECK(v.phase_center == v.n * v.inc_center);
    CHECK(v.phase_right == v.phase_center + v.u_units);
    CHECK(v.has_cycle == (std::string(v.fixture) == kCycleFixture));
    if (!v.has_cycle) {
      CHECK(v.u_units == 0);
      CHECK(v.phase_right == v.phase_center);
      continue;
    }
    CHECK(v.p0 == core::coupling_phase_units(v.start_phase_deg));
    CHECK(v.inc_cycle == core::phase_increment(1.0 / v.period_s, v.fs));
    CHECK(api::bits(v.k) == api::bits((v.swing_hz * v.period_s) * spec::kInvTwoPi));
    CHECK(v.phase_cycle == v.p0 + v.n * v.inc_cycle);
    const double c = core::sine(v.phase_cycle + kQuarter);
    CHECK(api::bits(c) == v.c_bits);
    const double c0 = core::sine(v.p0 + kQuarter);
    CHECK(api::bits(c0) == c0_bits_of(v));
    const double d = c0 - c;
    const double value = v.k * d;
    CHECK(api::bits(value) == v.v_bits);
    CHECK(probe::call_units(value) == v.u_units);
    CHECK(probe::call_offset(v.phase_cycle, v.k, c0) == v.u_units);
  }
  CHECK(signal.size() == 8);  // four fixtures at two sample rates
  CHECK(past == signal);
}

// ------------------------------------------------------------ plan

TEST_CASE("binaural: the plan holds the increments, amplitudes, and cycle constants of the vectors",
          "[binaural][plan]") {
  const auto pairs = fixture_rates();
  REQUIRE(pairs.size() == 8);
  for (const auto& [name, fs] : pairs) {
    INFO(name << " at " << fs);
    const auto& v = first_vector(name, fs);
    const plan::Plan p = compile_plan(api::valid(name), fs);
    CHECK(p.frame_count == v.frames);
    CHECK(p.binaural.increment[0] == v.inc_left);
    CHECK(p.binaural.increment[1] == v.inc_center);
    CHECK(api::bits(p.binaural.amplitude[0]) == api::bits(1.0));
    CHECK(api::bits(p.binaural.amplitude[1]) == api::bits(1.0));
    CHECK_FALSE(p.theta.present);
    CHECK_FALSE(p.gamma.present);
    const CycleConstants c = cycle_of(p.binaural);
    CHECK(c.cycle == v.has_cycle);
    if (v.has_cycle) {
      CHECK(c.start == v.p0);
      CHECK(c.increment == v.inc_cycle);
      CHECK(c.k_bits == api::bits(v.k));
      CHECK(c.c0_bits == c0_bits_of(v));
    }
  }
}

TEST_CASE("binaural: the plan cycle constants equal the rate cycle vectors at every start phase",
          "[binaural][plan]") {
  for (const auto& r : spec::kRateCycles) {
    const std::string phase = r.start_phase_deg == 0.0     ? "0"
                              : r.start_phase_deg == 90.0  ? "90"
                              : r.start_phase_deg == 180.0 ? "180"
                              : r.start_phase_deg == 270.0 ? "270"
                                                           : "360";
    INFO("start phase " << phase << " degrees at " << r.fs);
    REQUIRE(r.swing_hz == 1.5);
    REQUIRE(r.period_s == 60.0);
    const plan::Plan p = compile_plan(recipe_text({sleep_member(phase)}), r.fs);
    const CycleConstants c = cycle_of(p.binaural);
    CHECK(c.cycle);
    CHECK(c.start == r.p0);
    CHECK(c.increment == r.inc_cycle);
    CHECK(c.k_bits == api::bits(r.k));
    CHECK(c.c0_bits == r.c0_bits);
    CHECK(p.binaural.increment[0] == core::phase_increment(100.0, r.fs));
    CHECK(p.binaural.increment[1] == core::phase_increment(100.0 + 1.5, r.fs));
  }
}

TEST_CASE("binaural: a muted right ear has no cycle; a muted left ear keeps it", "[binaural][plan][isolation]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const auto& v = first_vector(kCycleFixture, fs);
    const std::string text = api::valid(kCycleFixture);
    {
      const plan::Plan p = compile_plan(text, fs, plan::MuteEar::Right);
      CHECK(p.binaural.increment[1] == 0);
      CHECK(api::bits(p.binaural.amplitude[1]) == api::bits(0.0));
      CHECK(p.binaural.increment[0] == v.inc_left);
      CHECK(api::bits(p.binaural.amplitude[0]) == api::bits(1.0));
      CHECK_FALSE(cycle_of(p.binaural).cycle);
    }
    {
      const plan::Plan p = compile_plan(text, fs, plan::MuteEar::Left);
      CHECK(p.binaural.increment[0] == 0);
      CHECK(api::bits(p.binaural.amplitude[0]) == api::bits(0.0));
      CHECK(p.binaural.increment[1] == v.inc_center);
      const CycleConstants c = cycle_of(p.binaural);
      CHECK(c.cycle);
      CHECK(c.start == v.p0);
      CHECK(c.increment == v.inc_cycle);
      CHECK(c.k_bits == api::bits(v.k));
    }
    {
      // No binaural field: no cycle, increments 0, amplitudes 0.0.
      const plan::Plan p = compile_plan(recipe_text({kTheta}), fs);
      CHECK_FALSE(cycle_of(p.binaural).cycle);
      CHECK(p.binaural.increment[0] == 0);
      CHECK(p.binaural.increment[1] == 0);
    }
    {
      // A fixed beat has no cycle.
      const plan::Plan p = compile_plan(api::valid("binaural-beat-6.json"), fs);
      CHECK_FALSE(cycle_of(p.binaural).cycle);
    }
  }
}

// ------------------------------------------------------------ renders

TEST_CASE("binaural: fixtures render the vector bits through the C API", "[binaural][render]") {
  const auto pairs = fixture_rates();
  REQUIRE(pairs.size() == 8);  // four fixtures at two sample rates
  for (const auto& [name, fs] : pairs) {
    INFO(name << " at " << fs);
    const auto& first = first_vector(name, fs);
    auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
    REQUIRE(arc_plan_frame_count(p.get()) == first.frames);
    std::uint64_t last = 0;
    for (const auto& v : spec::kBinauralSamples) {
      if (name == v.fixture && fs == v.fs) {
        last = std::max(last, v.n);
      }
    }
    std::size_t rows = 0;
    std::size_t other_layer_chunks = 0;
    const std::string fixture_name = name;
    const std::uint32_t rate = fs;
    auto renderer = api::renderer(p.get());
    render_chunks(renderer.get(), last + 1,
                  [&](std::uint64_t start, std::size_t count, const std::vector<double>& out,
                      const api::TapBuffers& taps) {
                    for (const auto& v : spec::kBinauralSamples) {
                      if (fixture_name != v.fixture || rate != v.fs || v.n < start || v.n >= start + count) {
                        continue;
                      }
                      ++rows;
                      INFO("n " << v.n << (v.past_end ? " (past end)" : ""));
                      const auto i = static_cast<std::size_t>(2 * (v.n - start));
                      CHECK(api::bits(out[i]) == v.left_bits);
                      CHECK(api::bits(out[i + 1]) == v.right_bits);
                      CHECK(api::bits(taps.binaural_join[i]) == v.left_bits);
                      CHECK(api::bits(taps.binaural_join[i + 1]) == v.right_bits);
                      CHECK(api::bits(taps.master[i]) == v.left_bits);
                      CHECK(api::bits(taps.master[i + 1]) == v.right_bits);
                    }
                    // No other layer: the stereo bus, theta, and gamma taps are +0.0.
                    const bool silent = api::all_exact_zero(taps.stereo_bus.data(), 2 * count) &&
                                        api::all_exact_zero(taps.theta_reference.data(), 2 * count) &&
                                        api::all_exact_zero(taps.gamma_pac.data(), 2 * count);
                    other_layer_chunks += silent ? 0 : 1;
                  });
    CHECK(rows >= 12);
    CHECK(other_layer_chunks == 0);
  }
}

TEST_CASE("binaural: each ear equals the law sample by sample, never -0.0", "[binaural][render]") {
  constexpr std::uint64_t kNegativeZero = UINT64_C(0x8000000000000000);
  for (const auto& [name, fs] : fixture_rates()) {
    INFO(name << " at " << fs);
    const auto& v = first_vector(name, fs);
    // Fixed beat: the right carrier is the stub's, inc(f_L + beat).
    CHECK(v.inc_center == core::phase_increment(v.carrier_left_hz + v.beat_rate_hz, fs));
    auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
    REQUIRE(arc_plan_frame_count(p.get()) == v.frames);
    auto renderer = api::renderer(p.get());
    std::size_t left_mismatches = 0;
    std::size_t right_mismatches = 0;
    std::size_t offset_mismatches = 0;
    std::size_t negative_zero = 0;
    double c0 = 0.0;
    if (v.has_cycle) {
      c0 = core::sine(v.p0 + kQuarter);
    }
    render_chunks(renderer.get(), v.frames,
                  [&](std::uint64_t start, std::size_t count, const std::vector<double>& out,
                      const api::TapBuffers&) {
                    for (std::size_t i = 0; i < count; ++i) {
                      const std::uint64_t n = start + i;
                      const std::uint64_t u = law_units(v, n);
                      if (v.has_cycle) {
                        offset_mismatches +=
                            probe::call_offset(v.p0 + n * v.inc_cycle, v.k, c0) != u ? 1 : 0;
                      }
                      const std::uint64_t want_l = api::bits(core::sine(n * v.inc_left));
                      const std::uint64_t want_r = api::bits(core::sine(n * v.inc_center + u));
                      left_mismatches += api::bits(out[2 * i]) != want_l ? 1 : 0;
                      right_mismatches += api::bits(out[2 * i + 1]) != want_r ? 1 : 0;
                      negative_zero += api::bits(out[2 * i]) == kNegativeZero ? 1 : 0;
                      negative_zero += api::bits(out[2 * i + 1]) == kNegativeZero ? 1 : 0;
                    }
                  });
    CHECK(left_mismatches == 0);
    CHECK(right_mismatches == 0);
    CHECK(offset_mismatches == 0);
    CHECK(negative_zero == 0);
  }
}

TEST_CASE("binaural: the cycle really moves the right ear; swing 0 is the fixed beat bit for bit",
          "[binaural][render]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const Rendered fixed = render_text(recipe_text({binaural_member("100", "1.5")}), fs);
    const Rendered zero_swing =
        render_text(recipe_text({binaural_member("100", "1.5", cycle_member("0", "60", "270"))}), fs);
    const Rendered sleep = render_text(recipe_text({sleep_member("270")}), fs);
    CHECK(api::same_bytes(zero_swing.out, fixed.out));
    CHECK(api::same_bytes(zero_swing.taps.binaural_join, fixed.taps.binaural_join));
    // The left ears are equal; the right ears differ.
    CHECK(api::same_bytes(api::channel(sleep.out, 0), api::channel(fixed.out, 0)));
    CHECK_FALSE(api::same_bytes(api::channel(sleep.out, 1), api::channel(fixed.out, 1)));
  }
}

TEST_CASE("binaural: waveform sine and an absent waveform render the same bits", "[binaural][waveform]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    for (const bool cycle : {false, true}) {
      INFO("fs " << fs << ", cycle " << cycle);
      const std::string sine_text =
          cycle ? sleep_member("270", ", \"waveform\": \"sine\"")
                : binaural_member("400", "6", ", \"waveform\": \"sine\"");
      const std::string absent_text = cycle ? sleep_member("270") : binaural_member("400", "6");
      const Rendered with = render_text(recipe_text({sine_text}), fs);
      const Rendered without = render_text(recipe_text({absent_text}), fs);
      CHECK(api::same_bytes(with.out, without.out));
      CHECK(api::same_bytes(with.taps.binaural_join, without.taps.binaural_join));
      CHECK(api::same_bytes(with.taps.master, without.taps.master));
    }
  }
}

TEST_CASE("binaural: start phase 0 and 360 render the same bytes", "[binaural][rate-curve]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const Rendered zero = render_text(recipe_text({sleep_member("0")}), fs);
    const Rendered full = render_text(recipe_text({sleep_member("360")}), fs);
    CHECK(api::same_bytes(zero.out, full.out));
    CHECK(api::same_bytes(zero.taps.binaural_join, full.taps.binaural_join));
    // 359.99 degrees is another point: its right ear differs.
    const Rendered near = render_text(recipe_text({sleep_member("359.99")}), fs);
    CHECK_FALSE(api::same_bytes(api::channel(near.out, 1), api::channel(zero.out, 1)));
  }
}

TEST_CASE("binaural: a muted ear renders +0.0 and leaves the other ear's bits", "[binaural][isolation]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const std::string text = recipe_text({sleep_member("270")}, "5");
    const Rendered both = render_text(text, fs);
    const Rendered no_right = render_text(text, fs, 0, ARC_MUTE_RIGHT);
    const Rendered no_left = render_text(text, fs, 0, ARC_MUTE_LEFT);
    CHECK(api::all_exact_zero(api::channel(no_right.taps.binaural_join, 1)));
    CHECK(api::all_exact_zero(api::channel(no_left.taps.binaural_join, 0)));
    CHECK(api::same_bytes(api::channel(no_right.out, 0), api::channel(both.out, 0)));
    CHECK(api::same_bytes(api::channel(no_left.out, 1), api::channel(both.out, 1)));
  }
}

TEST_CASE("binaural: seek to a vector index renders that index's bits", "[binaural][seek]") {
  for (const auto& [name, fs] : fixture_rates()) {
    auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
    auto renderer = api::renderer(p.get());
    for (const auto& v : spec::kBinauralSamples) {
      if (name != v.fixture || fs != v.fs) {
        continue;
      }
      INFO(name << " at " << fs << ", seek to " << v.n);
      api::seek(renderer.get(), v.n);
      api::TapBuffers taps(1);
      arc_taps t = taps.taps();
      const auto out = api::render(renderer.get(), 1, &t);
      CHECK(api::bits(out[0]) == v.left_bits);
      CHECK(api::bits(out[1]) == v.right_bits);
      CHECK(api::bits(taps.binaural_join[0]) == v.left_bits);
      CHECK(api::bits(taps.binaural_join[1]) == v.right_bits);
    }
  }
}

TEST_CASE("binaural: every block size of row block-sizes gives the same bytes with a beat rate cycle",
          "[binaural][blocks]") {
  const auto& sizes = spec::row("block-sizes");
  const double allowed = spec::row("block-size-invariance").value();
  REQUIRE_FALSE(sizes.values.empty());
  for (const std::string& phase : {std::string("270"), std::string("0")}) {
    const std::string text = recipe_text({kTheta, kGamma, sleep_member(phase)}, "3");
    for (const std::uint32_t fs : spec::sample_rates()) {
      const Rendered whole = render_text(text, fs);
      for (const double size : sizes.values) {
        INFO("start phase " << phase << " at " << fs << ", " << size << " frames per call");
        const Rendered r = render_in_blocks(text, fs, static_cast<std::size_t>(size));
        CHECK(static_cast<double>(differing_bytes(r.out, whole.out)) <= allowed);
        CHECK(static_cast<double>(differing_bytes(r.taps.binaural_join, whole.taps.binaural_join)) <= allowed);
        CHECK(static_cast<double>(differing_bytes(r.taps.gamma_pac, whole.taps.gamma_pac)) <= allowed);
      }
    }
  }
}

// ------------------------------------------------------------ AD-5: nothing reads the binaural layer

TEST_CASE("binaural: the theta and gamma taps are the same with and without a binaural layer",
          "[binaural][ad5]") {
  const std::string binaurals[] = {"", binaural_member("100", "0"), binaural_member("100", "10"),
                                   sleep_member("0"), sleep_member("90"), sleep_member("270")};
  for (const std::uint32_t fs : spec::sample_rates()) {
    const Rendered alone = render_text(recipe_text({kTheta, kGamma}), fs);
    for (const auto& b : binaurals) {
      INFO("fs " << fs << ", " << (b.empty() ? std::string("no binaural") : b));
      const Rendered r = render_text(recipe_text({kTheta, kGamma, b}), fs);
      CHECK(api::same_bytes(r.taps.gamma_pac, alone.taps.gamma_pac));
      CHECK(api::same_bytes(r.taps.theta_reference, alone.taps.theta_reference));
      CHECK(api::same_bytes(r.taps.stereo_bus, alone.taps.stereo_bus));
    }
  }
}

TEST_CASE("binaural: the binaural ears are the same with and without the theta and gamma layers",
          "[binaural][ad5]") {
  // join = bus + bin per channel (Stub chain, Per sample); with no other
  // layer the join is bin bit for bit, so with the layers it must be the bus
  // plus that same bin.
  for (const std::uint32_t fs : spec::sample_rates()) {
    for (const auto& b : {binaural_member("100", "4"), sleep_member("270"), sleep_member("90")}) {
      INFO("fs " << fs << ", " << b);
      const Rendered bin = render_text(recipe_text({b}), fs);
      for (const auto& layers : {std::vector<std::string>{kTheta}, std::vector<std::string>{kTheta, kGamma}}) {
        const std::string text = layers.size() == 1 ? recipe_text({layers[0], b})
                                                    : recipe_text({layers[0], layers[1], b});
        const Rendered with = render_text(text, fs);
        REQUIRE(with.frames == bin.frames);
        std::size_t mismatches = 0;
        for (std::size_t k = 0; k < with.taps.binaural_join.size(); ++k) {
          const double want = with.taps.stereo_bus[k] + bin.taps.binaural_join[k];
          mismatches += api::bits(with.taps.binaural_join[k]) != api::bits(want) ? 1 : 0;
        }
        CHECK(mismatches == 0);
        CHECK(api::same_bytes(with.out, with.taps.binaural_join));  // master is the identity stub
      }
    }
  }
}

#else

TEST_CASE("binaural layer is implemented", "[binaural]") {
  FAIL("not implemented: core/envelope.hpp or plan/plan.hpp (Story 2.5)");
}

#endif
