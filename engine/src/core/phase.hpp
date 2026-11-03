// Phase accumulator rules (docs/signal-spec.md, Core).
//
// One cycle is 2^64 phase units; phase[n+1] = phase[n] + inc mod 2^64
// (unsigned wraparound). Both rules here are pure binary64 and integer
// arithmetic: no libm, no long double, no fused multiply-add (AD-9).

#ifndef ARCANI_CORE_PHASE_HPP
#define ARCANI_CORE_PHASE_HPP

#include <cstdint>

namespace arcani::core {

// Increment rule: q = (f_hz * 2^64) / fs in binary64 (the multiply is
// exact, the division rounds once); the result is q rounded to the nearest
// integer, ties to even. Domain 0 <= f_hz < fs / 2; anything else, NaN and
// infinities included, returns 0.
std::uint64_t phase_increment(double f_hz, std::uint32_t fs) noexcept;

// Seconds-to-samples rule: x = t_s * fs in binary64 (one rounding), then x
// rounded to the nearest integer, ties to even. Domain t_s >= 0, finite, and
// x < 2^64; anything else returns 0.
std::uint64_t seconds_to_samples(double t_s, std::uint32_t fs) noexcept;

}  // namespace arcani::core

#endif  // ARCANI_CORE_PHASE_HPP
