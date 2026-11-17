// Spectral component table (Story 3.1; docs/signal-spec.md, Components).
//
// build_components() lists, per ear and per layer, every spectral line of a
// recipe's layers whose level is at least kComponentThreshold re its layer's
// carrier line: the closed-form line model of every v0.1 shape. Compile calls
// it after check_rules() and stores the table in the plan; the renderer never
// reads it. Story 3.2's spacing rule reads it.
//
// Arithmetic: basic binary64 operations, square root, integer arithmetic, and
// the cycle cosine (docs/signal-spec.md, Rate curve) only, so the table has
// the same bytes on every platform (AD-9). No transcendental call.

#ifndef ARCANI_VALIDATE_COMPONENTS_HPP
#define ARCANI_VALIDATE_COMPONENTS_HPP

#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

#include "recipe/recipe.hpp"

namespace arcani::validate {

// Values equal arc_component_layer and arc_ear in arcani/arcani.h.
enum class ComponentLayer : int { ThetaReference = 0, GammaPac = 1, Binaural = 2 };
enum class Ear : int { Left = 0, Right = 1 };

// One row of the table (docs/signal-spec.md, Components, Table). The line's
// frequency at any moment is f_c + gamma_mult * gamma rate(t) + theta_mult *
// theta rate(t) + beat_mult * beat rate(t), with f_c the layer's carrier (the
// left carrier for both binaural ears); [low_hz, high_hz] is the range it
// covers over a whole rate cycle, and level its amplitude re the layer's
// carrier line, in (0, 1].
struct Component {
  ComponentLayer layer = ComponentLayer::ThetaReference;
  Ear ear = Ear::Left;
  double center_hz = 0.0;
  double low_hz = 0.0;
  double high_hz = 0.0;
  double level = 0.0;
  std::int32_t gamma_mult = 0;
  std::int32_t theta_mult = 0;
  std::int32_t beat_mult = 0;
  // Story 3.2: the unmirrored interval reaches below 0 Hz (center - half < 0),
  // so the row is listed mirrored (Components, Frequencies below 0).
  bool mirrored = false;
};

// The compile option mute_binaural_ear: a muted ear has no binaural row.
enum class MutedEar { None, Left, Right };

struct ComponentResult {
  std::vector<Component> components;    // table order: left ear, then right
  std::optional<recipe::Error> error;   // set, with no rows, on an unmodeled shape
};

inline constexpr std::string_view kNoComponentModelRule = "no component model";

// Row spectral-component-level (dB) and T, the binary64 nearest 10^(-L / 20).
inline constexpr double kComponentLevelDb = 40.0;
inline constexpr double kComponentThreshold = 0x1.47ae147ae147bp-7;

// The table of a parsed recipe. It reads the three layer objects and the
// muted ear only. On a custom theta shape, a non-sine gamma carrier wave, or
// a non-sine binaural waveform (checked in that order) it returns no rows and
// the error /theta_reference/shape, /gamma_pac/carrier_wave, or
// /binaural/waveform, rule kNoComponentModelRule, limit the modeled shapes.
// Throws only std::bad_alloc.
ComponentResult build_components(const recipe::Recipe& r, MutedEar mute);

}  // namespace arcani::validate

#endif  // ARCANI_VALIDATE_COMPONENTS_HPP
