// Rate cycle: cycle cosine, cycles-to-units rule, and the offset U
// (docs/signal-spec.md, Rate curve).

#include "core/rate_cycle.hpp"

#include "core/phase.hpp"

namespace arcani::core {

namespace {

constexpr std::uint64_t kQuarter = std::uint64_t{1} << 62;  // 2^62: sine(p + 2^62) is cos(p)
constexpr std::uint64_t kHalf = std::uint64_t{1} << 63;     // 2^63: a half cycle

}  // namespace

std::uint64_t cycles_to_units(double v) noexcept {
  // Negated in-range test, so NaN falls out as well. At or above 2^52 every
  // binary64 value is an integer: 0 mod 1.
  if (!(v > -0x1p52 && v < 0x1p52)) {
    return 0u;
  }
  const auto whole = static_cast<std::int64_t>(v);  // toward zero; fits, |v| < 2^52
  const double f = v - static_cast<double>(whole);  // exact: the fraction bits of v
  // f * 2^64 is exact and its magnitude is below 2^64. Ties to even is
  // symmetric, so a negative fraction wraps to 2^64 minus the rounded
  // magnitude (0 when that rounds to 0).
  if (f < 0.0) {
    return 0 - round_half_even(-f * 0x1p64);  // mod 2^64
  }
  return round_half_even(f * 0x1p64);
}

double cycle_cosine(std::uint64_t phase) noexcept {
  // Step 1: the quarter turn and the engine sine's exact fold to [-2^62, 2^62].
  const std::uint64_t q = phase + kQuarter;  // mod 2^64: cos(p) is sin(p + 2^62)
  std::uint64_t folded = q;
  if (q > kQuarter && q < kHalf + kQuarter) {
    folded = kHalf - q;  // mod 2^64
  }
  const auto s = static_cast<std::int64_t>(folded);
  // Step 2: one conversion, one multiply (the engine sine's constant).
  const double x = static_cast<double>(s) * 0x1.921fb54442d18p-62;
  // Step 3: odd Taylor polynomial to x^15, the binary64 nearest +-1/k!.
  constexpr double kD1 = 0x1.0000000000000p+0;
  constexpr double kD3 = -0x1.5555555555555p-3;
  constexpr double kD5 = 0x1.1111111111111p-7;
  constexpr double kD7 = -0x1.a01a01a01a01ap-13;
  constexpr double kD9 = 0x1.71de3a556c734p-19;
  constexpr double kD11 = -0x1.ae64567f544e4p-26;
  constexpr double kD13 = 0x1.6124613a86d09p-33;
  constexpr double kD15 = -0x1.ae7f3e733b81fp-41;
  const double z = x * x;
  double r = kD15;
  r = r * z + kD13;
  r = r * z + kD11;
  r = r * z + kD9;
  r = r * z + kD7;
  r = r * z + kD5;
  r = r * z + kD3;
  r = r * z + kD1;
  return r * x;
}

std::uint64_t rate_cycle_offset(std::uint64_t cycle_phase, double k, double c0) noexcept {
  const double c = cycle_cosine(cycle_phase);  // the cosine of the cycle phase
  const double v = k * (c0 - c);               // c0 - c, then K times it
  return cycles_to_units(v);
}

}  // namespace arcani::core
