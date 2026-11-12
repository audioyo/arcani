// Theta reference envelopes (docs/signal-spec.md, Theta reference), the
// gamma PAC layer's sine envelope (Gamma PAC layer, AM law), which is the
// theta sine shape at the gamma rate, and the smooth swell (Coupling).
//
// Four envelope shapes of a 64-bit envelope phase (one cycle = 2^64), each
// in [0, 1] with its peak, the 0 degree point, at phase 0. Segments are
// chosen by exact integer comparisons; cosines are the engine sine a quarter
// cycle on. No libm, no long double, no fused multiply-add (AD-9).

#ifndef ARCANI_CORE_ENVELOPE_HPP
#define ARCANI_CORE_ENVELOPE_HPP

#include <cstdint>

namespace arcani::core {

enum class EnvelopeShape { Sine, SmoothedOnOff, Sawtooth, ReverseSaw };

// Fixed constants, in row units (range rows theta-on-share and theta-edge,
// min equal to max). Neither is a recipe field.
inline constexpr double kThetaOnSharePercent = 50.0;
inline constexpr double kThetaEdgeMs = 10.0;

// Ratio-to-phase rule: 0 when !(r > 0) (NaN, zeros, negatives), 2^63 when
// r >= 1, else r * 2^63 (exact) rounded to the nearest integer, ties to even.
std::uint64_t ratio_to_phase(double r) noexcept;

// H: (kThetaOnSharePercent / 100) * 2^63, rounded; half the on share in
// phase units (2^62).
std::uint64_t theta_half_on_units() noexcept;

// W: w = (kThetaEdgeMs / 1000) * rate_hz (one rounding), then w * 2^64
// (exact) rounded; the edge length in envelope phase units at rate_hz.
// Domain: the theta-rate range (W < H - W there).
std::uint64_t theta_edge_units(double rate_hz) noexcept;

// The sine envelope (1 + cos(2 pi p / 2^64)) / 2: c = sine(p + 2^62), then
// (1.0 + c) * 0.5. The theta sine shape and the gamma PAC layer's AM law.
double sine_envelope(std::uint64_t phase) noexcept;

// Coupling phase rule (docs/signal-spec.md, Coupling): x = deg / 360.0 (one
// rounding), C = x * 2^64 (exact) rounded to the nearest integer, ties to
// even, mod 2^64. Domain: the coupling-phase range, so x in [0, 1]; x = 1
// (360 degrees) gives 0. Anything outside [0, 1), NaN included, gives 0.
std::uint64_t coupling_phase_units(double coupling_phase_deg) noexcept;

// Smooth swell (docs/signal-spec.md, Coupling, Swell law): one raised cosine
// per theta cycle, sine_envelope(theta_envelope_phase - coupling_phase_units
// mod 2^64), 1 at the coupling phase and 0 half a theta cycle away. AD-5: its
// only signal input is the theta reference's envelope phase; the second
// argument is the plan constant C. tests/cpp/test_coupling.cpp pins this
// signature.
double swell(std::uint64_t theta_envelope_phase, std::uint64_t coupling_phase_units) noexcept;

// The engine envelope e of an envelope phase, by the spec's segments and
// operation order. edge_units is W, half_on_units is H.
double envelope(EnvelopeShape shape, std::uint64_t phase, std::uint64_t edge_units,
                std::uint64_t half_on_units) noexcept;

}  // namespace arcani::core

#endif  // ARCANI_CORE_ENVELOPE_HPP
