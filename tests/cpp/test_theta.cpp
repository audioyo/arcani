// Theta reference envelopes (Story 2.1; docs/signal-spec.md, Theta reference).
//
// Expected interface, engine/src/core/envelope.hpp, namespace arcani::core
// (no libm, no long double, no fused multiply-add, AD-9):
//
//   enum class EnvelopeShape { Sine, SmoothedOnOff, Sawtooth, ReverseSaw };
//   inline constexpr double kThetaOnSharePercent = 50.0;  // range row theta-on-share
//   inline constexpr double kThetaEdgeMs = 10.0;          // range row theta-edge
//   // Ratio-to-phase rule: P = r * 2^63 rounded to the nearest integer, ties
//   // to even; 0 when !(r > 0), 2^63 when r >= 1.
//   std::uint64_t ratio_to_phase(double r) noexcept;
//   // H = (kThetaOnSharePercent / 100) * 2^63, rounded (2^62).
//   std::uint64_t theta_half_on_units() noexcept;
//   // W: w = (kThetaEdgeMs / 1000) * rate_hz (one rounding), then w * 2^64 rounded.
//   std::uint64_t theta_edge_units(double rate_hz) noexcept;
//   // The engine envelope e of an envelope phase, in [0, 1], by the spec's
//   // segments and operation order.
//   double envelope(EnvelopeShape shape, std::uint64_t phase, std::uint64_t edge_units,
//                   std::uint64_t half_on_units) noexcept;
//
// Vectors come from the generated spec_tables.hpp (kRatioToPhase,
// kThetaEdges, kThetaEnvelopes, kThetaSamples); rows from the tables through
// the assertion call. The render checks reach the engine through the public C
// API only: each theta fixture (recipes/fixtures/valid/theta-*.json) at both
// sample rates holds the vector bits in the theta tap (both channels) and in
// the output (no binaural layer), the gamma tap is +0.0, and everything past
// the end is +0.0. Seek to a vector index renders that index's bits, so seek
// sets the envelope phase as well as the carrier phase. Rendering in calls of
// odd sizes gives the same bytes as one call. At depth 0 every shape is the
// unmodulated engine sine bit for bit.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#if __has_include("core/envelope.hpp") && defined(ARC_ERROR_FIELD_BYTES)

#include "api_helpers.hpp"
#include "core/envelope.hpp"
#include "core/phase.hpp"
#include "core/sine.hpp"
#include "spec_helpers.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace api = arcani::test::api;
namespace core = arcani::core;
namespace spec = arcani::test::spec;

namespace {

constexpr std::uint64_t kHalf = UINT64_C(1) << 63;
constexpr std::uint64_t kQuarter = UINT64_C(1) << 62;
constexpr double kPi = 3.141592653589793238462643383279502884;

core::EnvelopeShape shape_of(std::string_view name) {
  if (name == "sine") {
    return core::EnvelopeShape::Sine;
  }
  if (name == "smoothed_on_off") {
    return core::EnvelopeShape::SmoothedOnOff;
  }
  if (name == "sawtooth") {
    return core::EnvelopeShape::Sawtooth;
  }
  if (name == "reverse_saw") {
    return core::EnvelopeShape::ReverseSaw;
  }
  FAIL("unknown shape in the vectors: " << std::string(name));
  return core::EnvelopeShape::Sine;
}

// The ideal envelope in binary64 with the test library cosine (tests may use
// libm; the engine may not).
double ideal_envelope(core::EnvelopeShape shape, std::uint64_t p, std::uint64_t w, std::uint64_t h) {
  const auto rc = [w](std::uint64_t u) {
    return 0.5 + 0.5 * std::cos(kPi * (static_cast<double>(u) / static_cast<double>(w)));
  };
  switch (shape) {
    case core::EnvelopeShape::Sine: {
      const double s = static_cast<double>(static_cast<std::int64_t>(p));
      return 0.5 + 0.5 * std::cos(2.0 * kPi * (s / 0x1p64));
    }
    case core::EnvelopeShape::SmoothedOnOff: {
      const std::uint64_t m = p < kHalf ? p : 0 - p;
      if (m <= h - w) {
        return 1.0;
      }
      if (m >= h) {
        return 0.0;
      }
      return rc(m - (h - w));
    }
    case core::EnvelopeShape::Sawtooth:
    case core::EnvelopeShape::ReverseSaw: {
      const std::uint64_t q = shape == core::EnvelopeShape::Sawtooth ? p : 0 - p;
      if (q < w) {
        return rc(q);
      }
      return static_cast<double>(q - w) / static_cast<double>(0 - w);
    }
  }
  return -1.0;
}

// |e - e_ideal| <= b / 2 + 2^-48 (signal spec, Theta reference, Error bound).
double envelope_bound() { return spec::sine_error_bound_linear() / 2.0 + 0x1p-48; }

struct Rendered {
  std::uint64_t frames = 0;
  std::vector<double> out;
  api::TapBuffers taps{0};
};

Rendered render_fixture(const std::string& name, std::uint32_t fs, std::uint64_t extra) {
  auto plan = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
  Rendered r;
  r.frames = arc_plan_frame_count(plan.get());
  const auto total = static_cast<std::size_t>(r.frames + extra);
  r.taps = api::TapBuffers(total);
  auto renderer = api::renderer(plan.get());
  arc_taps t = r.taps.taps();
  r.out = api::render(renderer.get(), total, &t);
  return r;
}

std::set<std::pair<std::string, std::uint32_t>> fixture_rates() {
  std::set<std::pair<std::string, std::uint32_t>> out;
  for (const auto& v : spec::kThetaSamples) {
    out.insert({v.fixture, v.fs});
  }
  return out;
}

}  // namespace

TEST_CASE("theta constants equal the fixed range rows", "[theta]") {
  const auto& on_share = spec::row("theta-on-share");
  const auto& edge = spec::row("theta-edge");
  CHECK(on_share.kind == "ranges");
  CHECK(on_share.unit == "percent");
  CHECK(on_share.min == on_share.max);
  CHECK(edge.kind == "ranges");
  CHECK(edge.unit == "ms");
  CHECK(edge.min == edge.max);
  CHECK(core::kThetaOnSharePercent == on_share.min);
  CHECK(core::kThetaEdgeMs == edge.min);
  CHECK(spec::kThetaOnSharePercent == core::kThetaOnSharePercent);
  CHECK(spec::kThetaEdgeMs == core::kThetaEdgeMs);
  CHECK(core::theta_half_on_units() == spec::kThetaHalfOnUnits);
}

TEST_CASE("theta ratio-to-phase rule matches the vectors", "[theta]") {
  for (const auto& v : spec::kRatioToPhase) {
    INFO(v.label);
    CHECK(core::ratio_to_phase(v.r) == v.phase);
  }
}

TEST_CASE("theta edge length matches the vectors", "[theta]") {
  for (const auto& v : spec::kThetaEdges) {
    INFO(v.rate_hz);
    CHECK(core::theta_edge_units(v.rate_hz) == v.w_units);
  }
  for (const auto& v : spec::kThetaEnvelopes) {
    CHECK(core::theta_edge_units(v.rate_hz) == v.w_units);
    CHECK(v.h_units == spec::kThetaHalfOnUnits);
  }
}

TEST_CASE("theta envelope bits match the vectors", "[theta]") {
  std::map<std::string, int> per_shape;
  for (const auto& v : spec::kThetaEnvelopes) {
    INFO(v.shape << " at " << v.rate_hz << " Hz, phase " << v.phase << " (" << v.segment << ")");
    const double e = core::envelope(shape_of(v.shape), v.phase, v.w_units, v.h_units);
    CHECK(api::bits(e) == v.e_bits);
    CHECK(std::fabs(e - v.ideal_e) <= envelope_bound());
    ++per_shape[v.shape];
  }
  CHECK(per_shape.size() == 4);
}

TEST_CASE("theta envelope stays in [0, 1] and within the bound across the cycle", "[theta]") {
  const double bound = envelope_bound();
  const std::uint64_t h = core::theta_half_on_units();
  const auto& rate = spec::hz_range("theta-rate");
  for (const double rate_hz : {rate.min, rate.max}) {
    const std::uint64_t w = core::theta_edge_units(rate_hz);
    for (const auto shape : {core::EnvelopeShape::Sine, core::EnvelopeShape::SmoothedOnOff,
                             core::EnvelopeShape::Sawtooth, core::EnvelopeShape::ReverseSaw}) {
      double worst = 0.0;
      bool in_range = true;
      for (std::uint64_t k = 0; k < (UINT64_C(1) << 16); ++k) {
        const std::uint64_t p = k * (UINT64_C(1) << 48) + UINT64_C(0x9e3779b97f4a7c15) % (UINT64_C(1) << 48);
        const double e = core::envelope(shape, p, w, h);
        in_range = in_range && e >= 0.0 && e <= 1.0;
        worst = std::fmax(worst, std::fabs(e - ideal_envelope(shape, p, w, h)));
      }
      // Every segment boundary and its neighbours.
      for (const std::uint64_t b : {UINT64_C(0), w, h - w, h, kHalf, 0 - h, 0 - (h - w), 0 - w, kQuarter}) {
        for (const std::uint64_t p : {b - 1, b, b + 1}) {
          const double e = core::envelope(shape, p, w, h);
          in_range = in_range && e >= 0.0 && e <= 1.0;
          worst = std::fmax(worst, std::fabs(e - ideal_envelope(shape, p, w, h)));
        }
      }
      INFO("shape " << static_cast<int>(shape) << ", rate " << rate_hz << " Hz, worst " << worst);
      CHECK(in_range);
      CHECK(worst <= bound);
    }
  }
}

TEST_CASE("theta envelope must-fail: a mirrored shape misses the vectors", "[theta]") {
  int misses = 0;
  for (const auto& v : spec::kThetaEnvelopes) {
    if (std::string_view(v.shape) != "sawtooth") {
      continue;
    }
    const double e = core::envelope(core::EnvelopeShape::ReverseSaw, v.phase, v.w_units, v.h_units);
    misses += std::fabs(e - v.ideal_e) > envelope_bound() ? 1 : 0;
  }
  CHECK(misses > 0);
}

TEST_CASE("theta fixtures render the vector bits through the C API", "[theta][render]") {
  constexpr std::uint64_t kExtra = 64;
  for (const auto& [name, fs] : fixture_rates()) {
    INFO(name << " at " << fs);
    const Rendered r = render_fixture(name, fs, kExtra);
    std::uint64_t frames = 0;
    for (const auto& v : spec::kThetaSamples) {
      if (name != v.fixture || fs != v.fs) {
        continue;
      }
      frames = v.frames;
      INFO("n " << v.n << (v.past_end ? " (past end)" : ""));
      const auto i = static_cast<std::size_t>(2 * v.n);
      CHECK(api::bits(r.taps.theta_reference[i]) == v.theta_bits);
      CHECK(api::bits(r.taps.theta_reference[i + 1]) == v.theta_bits);
      CHECK(api::bits(r.out[i]) == v.theta_bits);
      CHECK(api::bits(r.out[i + 1]) == v.theta_bits);
    }
    REQUIRE(r.frames == frames);
    CHECK(api::all_exact_zero(r.taps.gamma_pac));
    CHECK(api::same_bytes(r.out, r.taps.theta_reference));  // no binaural layer, 75 percent depth
    CHECK(api::all_exact_zero(r.out.data() + 2 * frames, 2 * kExtra));
  }
}

TEST_CASE("theta seek sets the envelope phase", "[theta][seek]") {
  for (const auto& [name, fs] : fixture_rates()) {
    auto plan = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
    auto renderer = api::renderer(plan.get());
    for (const auto& v : spec::kThetaSamples) {
      if (name != v.fixture || fs != v.fs) {
        continue;
      }
      INFO(name << " at " << fs << ", seek to " << v.n);
      api::seek(renderer.get(), v.n);
      api::TapBuffers taps(1);
      arc_taps t = taps.taps();
      const auto out = api::render(renderer.get(), 1, &t);
      CHECK(api::bits(taps.theta_reference[0]) == v.theta_bits);
      CHECK(api::bits(out[1]) == v.theta_bits);
    }
  }
}

TEST_CASE("theta renders the same bytes in odd-sized calls", "[theta][blocks]") {
  for (const auto& [name, fs] : fixture_rates()) {
    if (fs != 44100) {
      continue;
    }
    INFO(name);
    auto plan = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, fs));
    const auto frames = static_cast<std::size_t>(arc_plan_frame_count(plan.get()));
    auto one = api::renderer(plan.get());
    const auto whole = api::render(one.get(), frames);
    auto pieces = api::renderer(plan.get());
    std::vector<double> joined;
    joined.reserve(2 * frames);
    std::size_t done = 0;
    for (std::size_t call = 0; done < frames; ++call) {
      const std::size_t n = std::min<std::size_t>(call % 2 == 0 ? 997 : 3, frames - done);
      const auto part = api::render(pieces.get(), n);
      joined.insert(joined.end(), part.begin(), part.end());
      done += n;
    }
    CHECK(api::same_bytes(whole, joined));
  }
}

TEST_CASE("theta at depth 0 is the unmodulated carrier for every shape", "[theta][depth]") {
  for (const char* shape : {"sine", "smoothed_on_off", "sawtooth", "reverse_saw"}) {
    const std::string text = std::string(
        "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
        "\"author\": \"Arcani test\", \"date\": \"2026-11-06\", "
        "\"rationale\": \"Depth 0 theta test, made in the test.\", "
        "\"length_s\": 1, \"loudness_target_lufs\": -36, "
        "\"theta_reference\": {\"carrier_hz\": 300, \"rate_hz\": 6, \"am_depth_percent\": 0, "
        "\"shape\": \"") + shape + "\"}}";
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(shape << " at " << fs);
      auto plan = api::compile_ok(text, api::options(ARC_MODE_MEASURE, fs));
      const auto frames = static_cast<std::size_t>(arc_plan_frame_count(plan.get()));
      auto renderer = api::renderer(plan.get());
      api::TapBuffers taps(frames);
      arc_taps t = taps.taps();
      api::render(renderer.get(), frames, &t);
      const std::uint64_t inc = core::phase_increment(300.0, fs);
      bool same = true;
      for (std::size_t n = 0; n < frames; ++n) {
        const std::uint64_t want = api::bits(core::sine(static_cast<std::uint64_t>(n) * inc));
        same = same && api::bits(taps.theta_reference[2 * n]) == want &&
               api::bits(taps.theta_reference[2 * n + 1]) == want;
      }
      CHECK(same);
    }
  }
}

TEST_CASE("theta edge fits inside its segment at the top theta rate", "[theta]") {
  // W < H - W (signal spec, Theta reference, Fixed constants): at the
  // theta-rate max the smoothed on-off plateau and every edge stay apart.
  const auto& rate = spec::hz_range("theta-rate");
  const std::uint64_t w = core::theta_edge_units(rate.max);
  const std::uint64_t h = core::theta_half_on_units();
  CHECK(w < h - w);
}

TEST_CASE("theta at 100 percent depth: -0.0 theta tap, +0.0 bus and out", "[theta][depth]") {
  // Signal spec, Theta reference, Per sample: where a = 0 (the off segment)
  // and the carrier sine is negative, theta = 0.0 * negative = -0.0; the
  // stereo bus (theta + gamma) and the output are +0.0 there.
  const std::string text =
      "{\"schema_version\": \"1.0\", \"engine_version\": \"0.0.1\", \"seed\": 42, "
      "\"author\": \"Arcani test\", \"date\": \"2026-11-06\", "
      "\"rationale\": \"Full depth theta test, made in the test.\", "
      "\"length_s\": 1, \"loudness_target_lufs\": -36, "
      "\"theta_reference\": {\"carrier_hz\": 450, \"rate_hz\": 6, \"am_depth_percent\": 100, "
      "\"shape\": \"smoothed_on_off\"}}";
  constexpr std::uint64_t kNegativeZero = UINT64_C(0x8000000000000000);
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    auto plan = api::compile_ok(text, api::options(ARC_MODE_MEASURE, fs));
    const auto frames = static_cast<std::size_t>(arc_plan_frame_count(plan.get()));
    auto renderer = api::renderer(plan.get());
    api::TapBuffers taps(frames);
    arc_taps t = taps.taps();
    const auto out = api::render(renderer.get(), frames, &t);
    const std::uint64_t inc_t = core::phase_increment(450.0, fs);
    const std::uint64_t inc_e = core::phase_increment(6.0, fs);
    const std::uint64_t w = core::theta_edge_units(6.0);
    const std::uint64_t h = core::theta_half_on_units();
    std::size_t found = 0;
    bool ok = true;
    for (std::size_t n = 0; n < frames; ++n) {
      const auto k = static_cast<std::uint64_t>(n);
      const bool off = core::envelope(core::EnvelopeShape::SmoothedOnOff, k * inc_e, w, h) == 0.0;
      if (!off || !(core::sine(k * inc_t) < 0.0)) {
        continue;
      }
      ++found;
      for (std::size_t c = 0; c < 2; ++c) {
        const std::size_t i = 2 * n + c;
        ok = ok && api::bits(taps.theta_reference[i]) == kNegativeZero &&
             api::bits(taps.stereo_bus[i]) == 0 && api::bits(out[i]) == 0 &&
             api::bits(taps.master[i]) == 0;
      }
    }
    CHECK(found > 0);
    CHECK(ok);
  }
}

#else

TEST_CASE("theta reference envelopes are implemented", "[theta]") {
  FAIL("not implemented: core/envelope.hpp (Story 2.1)");
}

#endif
