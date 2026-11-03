// Engine-owned sine (docs/signal-spec.md, Sine). No libm (AD-9).

#ifndef ARCANI_CORE_SINE_HPP
#define ARCANI_CORE_SINE_HPP

#include <cstdint>

namespace arcani::core {

// Engine sine of a 64-bit phase (one cycle = 2^64): exact integer fold to
// [-2^62, 2^62], one conversion to binary64 radians, odd Taylor polynomial to
// x^11 in the spec's fixed Horner order. Within -120 dBFS of
// sin(2 * pi * phase / 2^64).
double sine(std::uint64_t phase) noexcept;

// Unmodulated sine oscillator on the shared phase accumulator rule:
// next() returns sine(phase[n]), then sets phase[n+1] = phase[n] + increment
// mod 2^64.
class SineOscillator {
 public:
  explicit SineOscillator(std::uint64_t increment, std::uint64_t phase = 0) noexcept
      : increment_(increment), phase_(phase) {}

  double next() noexcept;

  std::uint64_t phase() const noexcept { return phase_; }
  std::uint64_t increment() const noexcept { return increment_; }
  void set_increment(std::uint64_t increment) noexcept { increment_ = increment; }

 private:
  std::uint64_t increment_;
  std::uint64_t phase_;
};

}  // namespace arcani::core

#endif  // ARCANI_CORE_SINE_HPP
