// Rate cycle (docs/signal-spec.md, Rate curve): the cycle cosine, the
// cycles-to-units rule, and the closed-form offset U of a sinusoidal rate
// cycle. Story 2.5 wrote them for the binaural beat rate; Story 2.6 moves
// them here unchanged and applies them to the theta and gamma envelope rates.
// No libm, no long double, no fused multiply-add (AD-9).

#ifndef ARCANI_CORE_RATE_CYCLE_HPP
#define ARCANI_CORE_RATE_CYCLE_HPP

#include <cstdint>

namespace arcani::core {

// The binary64 nearest to 1 / (2 pi) (docs/signal-spec.md, Rate curve,
// Engine): K = (swing_hz * period_s) * kInvTwoPi.
inline constexpr double kInvTwoPi = 0x1.45f306dc9c883p-3;

// Cycles-to-units rule (docs/signal-spec.md, Rate curve): (v mod 1) * 2^64,
// rounded to the nearest integer, ties to even, mod 2^64. The fraction
// v - trunc(v) is exact; NaN, infinities, and |v| >= 2^52 (an integer) give 0.
std::uint64_t cycles_to_units(double v) noexcept;

// Cycle cosine (docs/signal-spec.md, Rate curve, Cycle cosine): the cosine of
// a 64-bit phase, more exact than the engine sine because U scales its error
// by K: the engine sine's exact fold of phase + 2^62, its one conversion, and
// an odd Taylor polynomial to x^15 in fixed Horner order. Within 1e-10 of
// cos(2 pi phase / 2^64) (row cycle-cosine-error); exactly +0.0 at 2^62 and
// 3 * 2^62. The one function for both c0 and the per-sample cosine.
double cycle_cosine(std::uint64_t phase) noexcept;

// Rate curve offset U (docs/signal-spec.md, Rate curve, Engine):
// cycles_to_units(k * (c0 - cycle_cosine(cycle_phase))). Its only signal
// input is the rate cycle phase; k (K) and c0 (cycle_cosine of P0) are plan
// constants. The binaural right ear, the theta envelope, and the gamma
// envelope each add it to their own phase, with their own cycle.
std::uint64_t rate_cycle_offset(std::uint64_t cycle_phase, double k, double c0) noexcept;

}  // namespace arcani::core

#endif  // ARCANI_CORE_RATE_CYCLE_HPP
