// Spacing rule per ear, whole session (Story 3.2; docs/signal-spec.md,
// Spacing).
//
// check_spacing() reads the component table (Story 3.1) and compares, in each
// ear, every row of one layer with every row of another layer. Every rate
// cycle has the one period of row rate-cycle-period, so the frequency
// difference of two rows is c + X sin(theta) + Y cos(theta), whose minimum
// magnitude over a whole cycle is max(0, |c| - H), H = sqrt(X^2 + Y^2): a
// closed-form worst case over the whole session, never a sampled one. A row
// listed mirrored below 0 Hz is compared by its listed interval. A pair
// passes when its minimum distance is at least kSpacingRuleHz (row
// spacing-rule); exactly the row value passes.
//
// Arithmetic: basic binary64 operations, square root, integer arithmetic, and
// the cycle cosine (docs/signal-spec.md, Rate curve) only. No transcendental
// call (AD-9).

#ifndef ARCANI_VALIDATE_SPACING_HPP
#define ARCANI_VALIDATE_SPACING_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <string_view>

#include "recipe/recipe.hpp"
#include "validate/components.hpp"

namespace arcani::validate {

inline constexpr std::string_view kSpacingRule = "spacing_rule";
inline constexpr double kSpacingRuleHz = 50.0;  // row spacing-rule

// The worst pair of one ear: the smallest minimum distance (ties to the
// smaller index of row 1, then of row 2), its margin (min distance less
// kSpacingRuleHz, one subtraction), and both table indices.
struct SpacingPair {
  double min_distance_hz = 0.0;
  double margin_hz = 0.0;
  std::size_t component_1 = 0;
  std::size_t component_2 = 0;
};

struct SpacingResult {
  std::array<std::optional<SpacingPair>, 2> ears;  // [Ear::Left], [Ear::Right]; empty with no pair
  std::optional<recipe::Error> error;              // the reported failure, detail filled
};

// The margins of both ears and, when a pair fails, the error of the smallest
// failing distance (ties to the left ear, then the smaller index of row 1,
// then of row 2). The margins are filled for a failing table too. The
// recipe gives each rate's center, swing, start phase, and period; `table`
// is a component table in table order. Throws only std::bad_alloc.
SpacingResult check_spacing(const recipe::Recipe& r, std::span<const Component> table);

// The closed form alone (Vectors: spacing pairs): two rows that differ by
// c_hz in center and by di, dj, db in multipliers, each cycle a swing (0 is
// no cycle) and a start phase. first_units is the cycle phase advance of the
// first time of the minimum, valid when sweeps.
struct SpacingPairInput {
  double c_hz = 0.0;
  int di = 0;
  int dj = 0;
  int db = 0;
  double swing_gamma_hz = 0.0;
  double start_gamma_deg = 0.0;
  double swing_theta_hz = 0.0;
  double start_theta_deg = 0.0;
  double swing_beat_hz = 0.0;
  double start_beat_deg = 0.0;
};

struct SpacingPairForm {
  double x = 0.0;
  double y = 0.0;
  double h = 0.0;
  double min_distance_hz = 0.0;
  bool sweeps = false;
  std::uint64_t first_units = 0;
};

SpacingPairForm spacing_pair_form(const SpacingPairInput& in);

// The smallest integer x in [0, 2^63] with cycle_cosine(x) <= v, by integer
// bisection (docs/signal-spec.md, Spacing, Engine).
std::uint64_t acos_units(double v);

// The shortest round-trip text of a finite binary64, as std::to_chars
// writes it (fixed or scientific, whichever is shorter, ties to fixed).
std::string shortest_text(double x);

}  // namespace arcani::validate

#endif  // ARCANI_VALIDATE_SPACING_HPP
