// Theta reference envelopes (docs/signal-spec.md, Theta reference), the smooth
// swell (Coupling), the burst gate (Bursts), and the rate cycle offset (Rate
// curve).

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

// Smoothed on-off segments of a distance m from the 0 degree point (Theta
// reference, Envelope shapes): 1 for m <= h - w, the edge for h - w < m < h,
// 0 for m >= h. The theta smoothed on-off shape and the burst gate.
double on_off(std::uint64_t m, std::uint64_t w, std::uint64_t h) noexcept {
  const std::uint64_t plateau_end = h - w;
  if (m <= plateau_end) {
    return 1.0;
  }
  if (m < h) {
    return raised_cosine(m - plateau_end, w);
  }
  return 0.0;
}

// Distance from the 0 degree point: p, or 2^64 - p past the half cycle.
std::uint64_t distance(std::uint64_t p) noexcept { return p < kHalf ? p : 0 - p; }

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

std::uint64_t coupling_phase_units(double coupling_phase_deg) noexcept {
  const double x = coupling_phase_deg / 360.0;
  // Negated in-range test, so NaN falls out as well; x = 1 is 2^64 = 0 mod 2^64.
  if (!(x >= 0.0 && x < 1.0)) {
    return 0u;
  }
  return round_half_even(x * 0x1p64);
}

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

double swell(std::uint64_t theta_envelope_phase, std::uint64_t coupling_phase_units) noexcept {
  return sine_envelope(theta_envelope_phase - coupling_phase_units);  // mod 2^64
}

std::uint64_t burst_half_width_units(double rate_hz) noexcept {
  const double half_width_s = kBurstWidthMs / 1000.0 / 2;  // one rounding, then an exact halving
  const double w = half_width_s * rate_hz;
  return round_half_even(w * 0x1p64);
}

std::uint64_t burst_edge_units(double rate_hz) noexcept {
  const double e = kBurstEdgeMs / 1000.0;
  const double w = e * rate_hz;
  return round_half_even(w * 0x1p64);
}

double burst(std::uint64_t theta_envelope_phase, std::uint64_t coupling_phase_units,
             std::uint64_t half_width_units, std::uint64_t edge_units) noexcept {
  const std::uint64_t u = theta_envelope_phase - coupling_phase_units;  // mod 2^64
  return on_off(distance(u), edge_units, half_width_units);
}

double envelope(EnvelopeShape shape, std::uint64_t phase, std::uint64_t edge_units,
                std::uint64_t half_on_units) noexcept {
  switch (shape) {
    case EnvelopeShape::Sine:
      return sine_envelope(phase);
    case EnvelopeShape::SmoothedOnOff:
      return on_off(distance(phase), edge_units, half_on_units);
    case EnvelopeShape::Sawtooth:
      return sawtooth(phase, edge_units);
    case EnvelopeShape::ReverseSaw:
      return sawtooth(0 - phase, edge_units);  // 2^64 - p mod 2^64
  }
  return 0.0;
}

}  // namespace arcani::core
