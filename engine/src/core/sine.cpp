// Engine-owned sine (docs/signal-spec.md, Sine). No libm (AD-9).

#include "core/sine.hpp"

namespace arcani::core {

namespace {

constexpr std::uint64_t kQuarter = std::uint64_t{1} << 62;  // 2^62: a quarter cycle
constexpr std::uint64_t kHalf = std::uint64_t{1} << 63;     // 2^63: a half cycle

// Binary64 nearest to pi, times 2^-62 (exact): radians per phase unit.
constexpr double kRadiansPerUnit = 0x1.921fb54442d18p-62;

// Binary64 nearest to +-1/k! (signal spec, Sine, Coefficients).
constexpr double kC1 = 0x1.0000000000000p+0;
constexpr double kC3 = -0x1.5555555555555p-3;
constexpr double kC5 = 0x1.1111111111111p-7;
constexpr double kC7 = -0x1.a01a01a01a01ap-13;
constexpr double kC9 = 0x1.71de3a556c734p-19;
constexpr double kC11 = -0x1.ae64567f544e4p-26;

}  // namespace

double sine(std::uint64_t phase) noexcept {
  // Fold, exact integer steps (unsigned arithmetic mod 2^64, read as signed s
  // afterwards). Signed s > 2^62 is the bit range (2^62, 2^63), folded to
  // 2^63 - s; s < -2^62 is [2^63, 3 * 2^62), folded to -2^63 - s, which mod
  // 2^64 is the same bit pattern as 2^63 - phase. Both land in [-2^62, 2^62].
  std::uint64_t folded = phase;
  if (phase > kQuarter && phase < kHalf + kQuarter) {
    folded = kHalf - phase;
  }
  // C++20 defines unsigned-to-signed conversion as two's complement (mod 2^64).
  const std::int64_t s = static_cast<std::int64_t>(folded);

  // Convert once, then scale to radians: x in [-pi/2, pi/2].
  const double x = static_cast<double>(s) * kRadiansPerUnit;

  // Odd Taylor polynomial to x^11, fixed Horner order.
  const double z = x * x;
  double r = kC11;
  r = r * z + kC9;
  r = r * z + kC7;
  r = r * z + kC5;
  r = r * z + kC3;
  r = r * z + kC1;
  return r * x;
}

double SineOscillator::next() noexcept {
  const double y = sine(phase_);
  phase_ += increment_;
  return y;
}

}  // namespace arcani::core
