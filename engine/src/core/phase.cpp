// Phase accumulator rules (docs/signal-spec.md, Core).

#include "core/phase.hpp"

namespace arcani::core {

namespace {

constexpr double kTwoPow52 = 0x1p52;
constexpr double kTwoPow64 = 0x1p64;
constexpr double kMaxFinite = 0x1.fffffffffffffp+1023;

// Nearest integer to x, ties to even, for 0 <= x < 2^64. Every step is
// exact: at or above 2^52 a binary64 value is already an integer, and below
// it the truncation and the subtraction lose nothing.
std::uint64_t round_half_even(double x) noexcept {
  if (x >= kTwoPow52) {
    return static_cast<std::uint64_t>(x);
  }
  const std::uint64_t whole = static_cast<std::uint64_t>(x);
  const double fraction = x - static_cast<double>(whole);
  if (fraction > 0.5) {
    return whole + 1u;
  }
  if (fraction < 0.5) {
    return whole;
  }
  return whole + (whole & 1u);
}

}  // namespace

std::uint64_t phase_increment(double f_hz, std::uint32_t fs) noexcept {
  const double rate = static_cast<double>(fs);
  // Written as a negated in-range test so NaN falls out as well.
  if (!(f_hz >= 0.0 && f_hz < rate * 0.5)) {
    return 0u;
  }
  const double q = (f_hz * kTwoPow64) / rate;
  return round_half_even(q);
}

std::uint64_t seconds_to_samples(double t_s, std::uint32_t fs) noexcept {
  if (!(t_s >= 0.0 && t_s <= kMaxFinite)) {
    return 0u;
  }
  const double x = t_s * static_cast<double>(fs);
  if (!(x < kTwoPow64)) {
    return 0u;
  }
  return round_half_even(x);
}

}  // namespace arcani::core
