// Theta reference envelopes (docs/signal-spec.md, Theta reference).

#include "core/envelope.hpp"

#include "core/phase.hpp"
#include "core/sine.hpp"

namespace arcani::core {

namespace {

constexpr std::uint64_t kQuarter = std::uint64_t{1} << 62;  // 2^62: sine(p + 2^62) is cos(p)
constexpr std::uint64_t kHalf = std::uint64_t{1} << 63;     // 2^63: a half cycle

// Half raised cosine across one edge, 0 <= u <= w: (1 + cos(pi * u / w)) / 2.
double raised_cosine(std::uint64_t u, std::uint64_t w) noexcept {
  const double r = static_cast<double>(u) / static_cast<double>(w);
  const std::uint64_t p = ratio_to_phase(r);
  const double c = sine(p + kQuarter);  // mod 2^64
  return (1.0 + c) * 0.5;
}

// Drop edge, then the linear rise to 1 at the end of the cycle.
double sawtooth(std::uint64_t p, std::uint64_t w) noexcept {
  if (p < w) {
    return raised_cosine(p, w);
  }
  // p - w and 2^64 - w, exact in unsigned arithmetic.
  return static_cast<double>(p - w) / static_cast<double>(0 - w);
}

}  // namespace

std::uint64_t ratio_to_phase(double r) noexcept {
  if (!(r > 0.0)) {
    return 0u;
  }
  if (r >= 1.0) {
    return kHalf;
  }
  return round_half_even(r * 0x1p63);
}

std::uint64_t theta_half_on_units() noexcept {
  const double d = kThetaOnSharePercent / 100.0;
  return round_half_even(d * 0x1p63);
}

std::uint64_t theta_edge_units(double rate_hz) noexcept {
  const double e = kThetaEdgeMs / 1000.0;
  const double w = e * rate_hz;
  return round_half_even(w * 0x1p64);
}

double sine_envelope(std::uint64_t phase) noexcept {
  const double c = sine(phase + kQuarter);  // mod 2^64: the cosine of phase
  return (1.0 + c) * 0.5;
}

double envelope(EnvelopeShape shape, std::uint64_t phase, std::uint64_t edge_units,
                std::uint64_t half_on_units) noexcept {
  switch (shape) {
    case EnvelopeShape::Sine:
      return sine_envelope(phase);
    case EnvelopeShape::SmoothedOnOff: {
      // Distance from the 0 degree point: p, or 2^64 - p past the half cycle.
      const std::uint64_t m = phase < kHalf ? phase : 0 - phase;
      const std::uint64_t plateau_end = half_on_units - edge_units;
      if (m <= plateau_end) {
        return 1.0;
      }
      if (m < half_on_units) {
        return raised_cosine(m - plateau_end, edge_units);
      }
      return 0.0;
    }
    case EnvelopeShape::Sawtooth:
      return sawtooth(phase, edge_units);
    case EnvelopeShape::ReverseSaw:
      return sawtooth(0 - phase, edge_units);  // 2^64 - p mod 2^64
  }
  return 0.0;
}

}  // namespace arcani::core
