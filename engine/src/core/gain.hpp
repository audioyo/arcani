// Gain ramp law (docs/signal-spec.md, Gain ramps, Law; Story 4.4).

#ifndef ARCANI_CORE_GAIN_HPP
#define ARCANI_CORE_GAIN_HPP

#include <cstdint>

namespace arcani::core {

// The engine ramp for 0 <= k < length: r = k / L (two exact conversions, one
// division), P = ratio_to_phase(r), c = sine(P + 2^62), h = (1.0 - c) * 0.5,
// g = a + (b - a) * h, each one binary64 operation in that order.
double gain_ramp(double a, double b, std::uint64_t k, std::uint64_t length) noexcept;

}  // namespace arcani::core

#endif  // ARCANI_CORE_GAIN_HPP
