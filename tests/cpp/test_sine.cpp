// Engine sine and SineOscillator (docs/signal-spec.md, Sine). The bound is
// the sine-error row of tests/tables/thresholds.json; the vectors are the
// exact-phase and 450 Hz carrier tables of tests/data/signal_spec_vectors.json.
// Signals: 450 Hz carrier, unmodulated, 44.1 kHz sample rate.

#include "core/phase.hpp"
#include "core/sine.hpp"
#include "spec_helpers.hpp"

#include <catch2/catch_test_macros.hpp>

#include <bit>
#include <cmath>
#include <cstdint>
#include <initializer_list>
#include <numbers>

namespace spec = arcani::test::spec;
using arcani::core::phase_increment;
using arcani::core::sine;
using arcani::core::SineOscillator;

static_assert(noexcept(sine(UINT64_C(0))), "sine must be noexcept");

namespace {

// Ideal sine for the test: sin(2*pi*phase/2^64) from the signed phase, so the
// argument lies in [-pi, pi) and keeps full binary64 precision near the
// cycle end. std::sin is fine here: tests are not engine code. Its error
// (a few units in the last place, under 1e-15) is 9 orders below the bound.
double ideal_sine(std::uint64_t phase) {
  const auto s = static_cast<std::int64_t>(phase);
  return std::sin(static_cast<double>(s) * (std::numbers::pi * 0x1p-63));
}

double to_dbfs(double linear) { return 20.0 * std::log10(linear); }

constexpr std::uint64_t kQuarter = UINT64_C(1) << 62;

// Max |f(p) - ideal(p)| over the spec's test resolution: the 2^24 phases
// k * 2^40, plus each quadrant edge 0, 2^62, 2^63, 3 * 2^62 and its
// neighbours edge - 1 and edge + 1, modulo 2^64.
template <typename F>
double max_error_over_test_resolution(F f) {
  double worst = 0.0;
  for (std::uint64_t k = 0; k < (UINT64_C(1) << 24); ++k) {
    const std::uint64_t p = k << 40;
    worst = std::fmax(worst, std::fabs(f(p) - ideal_sine(p)));
  }
  for (std::uint64_t q = 0; q < 4; ++q) {
    const std::uint64_t edge = q * kQuarter;
    for (const std::uint64_t p : {edge - 1, edge, edge + 1}) {
      worst = std::fmax(worst, std::fabs(f(p) - ideal_sine(p)));
    }
  }
  return worst;
}

bool same_bits(double a, double b) {
  return std::bit_cast<std::uint64_t>(a) == std::bit_cast<std::uint64_t>(b);
}

}  // namespace

TEST_CASE("sine coefficient table holds the binary64 nearest to +-1/k!", "[sine][vectors]") {
  // One division of two exact binary64 values is correctly rounded, so
  // 1.0 / k! (k! is exact in binary64 up to 11!) is the nearest binary64.
  for (const auto& c : spec::kSineCoefficients) {
    double factorial = 1.0;
    for (int k = 2; k <= c.power; ++k) {
      factorial *= k;
    }
    const double sign = ((c.power / 2) % 2 == 0) ? 1.0 : -1.0;
    INFO("power " << c.power);
    CHECK(same_bits(c.value, sign * (1.0 / factorial)));
  }
}

TEST_CASE("engine sine meets the bound at every exact phase", "[sine][vectors]") {
  const double bound = spec::sine_error_bound_linear();
  for (const auto& v : spec::kExactPhases) {
    INFO("phase " << v.label << ": engine " << sine(v.phase) << ", ideal " << v.sine);
    CHECK(std::fabs(sine(v.phase) - v.sine) <= bound);
  }
}

TEST_CASE("must fail: a vector off by twice the bound is caught", "[sine][vectors][mustfail]") {
  const double bound = spec::sine_error_bound_linear();
  for (const auto& v : spec::kExactPhases) {
    INFO("phase " << v.label);
    CHECK_FALSE(std::fabs(sine(v.phase) - (v.sine + 2.0 * bound)) <= bound);
  }
}

TEST_CASE("450 Hz carrier vectors: phase rule and engine sine", "[sine][vectors][carrier]") {
  const double bound = spec::sine_error_bound_linear();
  CHECK(phase_increment(spec::kCarrierHz, spec::kCarrierFs) == spec::kCarrierInc);
  for (const auto& v : spec::kCarrierSamples) {
    INFO(spec::kCarrierLabel << ", sample " << v.n);
    CHECK(static_cast<std::uint64_t>(v.n * spec::kCarrierInc) == v.phase);
    CHECK(std::fabs(sine(v.phase) - v.sine) <= bound);
  }
}

TEST_CASE("SineOscillator from phase 0 equals sine(n * inc) bit for bit",
          "[sine][oscillator][carrier]") {
  const double bound = spec::sine_error_bound_linear();
  const std::uint64_t inc = spec::kCarrierInc;
  SineOscillator osc(inc);
  REQUIRE(osc.phase() == 0);
  REQUIRE(osc.increment() == inc);
  // Samples 0 .. 98: one nominal cycle of the 450 Hz carrier plus one.
  constexpr std::uint64_t kSamples = 99;
  for (std::uint64_t n = 0; n < kSamples; ++n) {
    const std::uint64_t expected_phase = n * inc;
    INFO(spec::kCarrierLabel << ", sample " << n);
    REQUIRE(osc.phase() == expected_phase);
    const double y = osc.next();
    CHECK(same_bits(y, sine(expected_phase)));
    for (const auto& v : spec::kCarrierSamples) {
      if (v.n == n) {
        CHECK(std::fabs(y - v.sine) <= bound);
      }
    }
  }
  CHECK(osc.phase() == kSamples * inc);
}

TEST_CASE("SineOscillator start phase and set_increment", "[sine][oscillator]") {
  const std::uint64_t inc = spec::kCarrierInc;
  const std::uint64_t start = spec::kCarrierSamples[3].phase;
  SineOscillator osc(inc, start);
  CHECK(osc.phase() == start);
  CHECK(same_bits(osc.next(), sine(start)));
  CHECK(osc.phase() == start + inc);
  osc.set_increment(2 * inc);
  CHECK(osc.increment() == 2 * inc);
  CHECK(osc.phase() == start + inc);
  CHECK(same_bits(osc.next(), sine(start + inc)));
  CHECK(osc.phase() == start + 3 * inc);
}

TEST_CASE("engine sine error over the test resolution is at most the bound",
          "[sine][accuracy]") {
  const double worst = max_error_over_test_resolution([](std::uint64_t p) { return sine(p); });
  const double dbfs = to_dbfs(worst);
  INFO("max |engine - ideal| = " << worst << " (" << dbfs << " dBFS), bound "
                                 << spec::sine_error_bound_dbfs() << " dBFS");
  CHECK(dbfs <= spec::sine_error_bound_dbfs());
}

TEST_CASE("must fail: a sine off by twice the bound exceeds it", "[sine][accuracy][mustfail]") {
  const double offset = 2.0 * spec::sine_error_bound_linear();
  const double worst =
      max_error_over_test_resolution([offset](std::uint64_t p) { return sine(p) + offset; });
  CHECK(to_dbfs(worst) > spec::sine_error_bound_dbfs());
}

TEST_CASE("phase wraps modulo 2^64 and the sine stays continuous", "[sine][oscillator][wrap]") {
  const double bound = spec::sine_error_bound_linear();
  const std::uint64_t inc = spec::kCarrierInc;
  // Largest change of sin over one step: the step size in radians.
  const double max_step = 2.0 * std::numbers::pi * static_cast<double>(inc) * 0x1p-64;

  // Start half a step below the top of the cycle.
  const std::uint64_t start = UINT64_C(0) - inc / 2;
  SineOscillator osc(inc, start);
  const double y0 = osc.next();
  CHECK(osc.phase() == start + inc);
  CHECK(osc.phase() < inc);  // wrapped past 2^64
  const double y1 = osc.next();
  CHECK(y0 < 0.0);
  CHECK(y1 > 0.0);
  CHECK(std::fabs(y0 - ideal_sine(start)) <= bound);
  CHECK(std::fabs(y1 - ideal_sine(start + inc)) <= bound);
  CHECK(std::fabs(y1 - y0) <= max_step + 2.0 * bound);

  // Single phase units around the wrap point.
  const std::uint64_t top = ~UINT64_C(0);
  CHECK(std::fabs(sine(top) - ideal_sine(top)) <= bound);
  CHECK(std::fabs(sine(0) - ideal_sine(0)) <= bound);
  CHECK(std::fabs(sine(1) - ideal_sine(1)) <= bound);
  CHECK(std::fabs(sine(top) - sine(0)) <= 2.0 * bound);

  // Must fail: a quarter-cycle phase jump at the wrap is not continuous.
  CHECK_FALSE(std::fabs(sine(start + inc + kQuarter) - y0) <= max_step + 2.0 * bound);
}
