// Recipe parse stage and recipe hash (Story 1.1).
//
// parse() runs the strict JSON parser, checks the document against the
// field table (structure, types, and the schema's string patterns and seed
// bounds; locked ranges are Story 1.3's validator), and fills a Recipe. Every
// error names parameter, value, rule, and limit. No exceptions are thrown for
// bad input and there is no file I/O.
//
// Recipe hash: remove every hash-excluded field from the parsed tree, write
// the rest as RFC 8785 canonical JSON, SHA-256 the UTF-8 bytes, lowercase hex.
// tools/recipe_hash.py computes the same hash independently.

#ifndef ARCANI_RECIPE_RECIPE_HPP
#define ARCANI_RECIPE_RECIPE_HPP

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace arcani::recipe {

struct Error {
  std::string parameter;  // JSON Pointer of the field ("" = whole document), or for a
                          // syntax fault the byte offset in decimal digits
  std::string value;      // the offending value as text, may be empty
  std::string rule;       // unknown_property, required, type, pattern, enum, minimum,
                          // maximum, schema_version.major, or the json.* parser rule
  std::string limit;      // what the rule allows, for example the supported majors "1"
  std::string detail{};   // Story 3.2: the spacing rule's pair and where; empty for every other rule
};

// Theta reference envelope shape (docs/signal-spec.md, Theta reference).
// Custom is schema-valid only so that compile can reject it by name.
enum class ThetaShape { Sine, SmoothedOnOff, Sawtooth, ReverseSaw, Custom };

// The schema enum of theta_reference.shape, in schema order (the limit of an
// enum error).
inline constexpr std::string_view kThetaShapeEnum =
    "sine, smoothed_on_off, sawtooth, reverse_saw, custom";

// Rate cycle (docs/signal-spec.md, Rate curve): a rate r becomes
// r + swing_hz * sin(2 pi t / period_s + start_phase_deg). The binaural beat
// rate (Story 2.5) and the theta and gamma rates (Story 2.6) use it.
struct RateCycle {
  double swing_hz = 0.0;
  double period_s = 0.0;
  double start_phase_deg = 0.0;
};

// Gain schedule (docs/signal-spec.md, Gain ramps; Story 4.4): an initial gain
// and ramps in array order, as written. Compile applies the range checks and
// the gain rules; parse keeps the values.
struct GainRampField {
  double start_s = 0.0;
  double duration_s = 0.0;
  double to = 0.0;
};

struct Gain {
  double initial = 1.0;
  std::vector<GainRampField> ramps;  // empty when ramps is absent or []
};

struct ThetaReference {
  double carrier_hz = 0.0;
  double rate_hz = 0.0;  // the cycle's center with a rate cycle
  double am_depth_percent = 0.0;
  ThetaShape shape = ThetaShape::Sine;
  std::optional<RateCycle> rate_cycle;  // Story 2.6; absent when the field is absent
  std::optional<Gain> gain;             // Story 4.4; absent when the field is absent
};

// Gamma PAC carrier wave (docs/signal-spec.md, Gamma PAC layer). Triangle and
// SoftenedSquare are schema-valid only so that compile can reject them by name.
enum class GammaCarrierWave { Sine, Triangle, SoftenedSquare };

// Gamma PAC coupling (docs/signal-spec.md, Coupling and Bursts).
enum class GammaCoupling { Uncoupled, SmoothSwell, Bursts };

// The schema enums of gamma_pac.carrier_wave and gamma_pac.coupling, in
// schema order (the limit of an enum error).
inline constexpr std::string_view kGammaCarrierWaveEnum = "sine, triangle, softened_square";
inline constexpr std::string_view kGammaCouplingEnum = "uncoupled, smooth_swell, bursts";

struct GammaPac {
  double carrier_hz = 0.0;
  double rate_hz = 0.0;  // the cycle's center with a rate cycle
  double am_depth_percent = 0.0;
  GammaCarrierWave carrier_wave = GammaCarrierWave::Sine;
  GammaCoupling coupling = GammaCoupling::Uncoupled;
  std::optional<double> coupling_phase_deg;  // degrees; absent when the field is absent
  std::optional<RateCycle> rate_cycle;       // Story 2.6; absent when the field is absent
  std::optional<Gain> gain;                  // Story 4.4; absent when the field is absent
};

// Binaural waveform (docs/signal-spec.md, Binaural layer). Triangle is
// schema-valid only so that compile can reject it by name.
enum class BinauralWaveform { Sine, Triangle };

// The schema enum of binaural.waveform, in schema order (the limit of an enum
// error).
inline constexpr std::string_view kBinauralWaveformEnum = "sine, triangle";

struct Binaural {
  double carrier_left_hz = 0.0;
  double beat_rate_hz = 0.0;                  // the cycle's center with a beat rate cycle
  std::optional<RateCycle> beat_rate_cycle;  // absent when the field is absent
  BinauralWaveform waveform = BinauralWaveform::Sine;  // absent means sine
  std::optional<Gain> gain;                            // Story 4.4; one gain for both ears
};

// Looping session mode (docs/signal-spec.md, Loop, Story 2.7): it names the
// max run time row (focus: max-run-time-focus, learn: max-run-time-learn).
enum class LoopMode { Focus, Learn };

// The schema enum of loop.mode, in schema order (the limit of an enum error).
inline constexpr std::string_view kLoopModeEnum = "focus, learn";

// A looping session: the opening plays once, then the body repeats until the
// session ends at max_run_time_min. All four are required inside loop.
struct Loop {
  LoopMode mode = LoopMode::Focus;
  double opening_s = 0.0;
  double body_s = 0.0;
  double max_run_time_min = 0.0;
};

// The master chain settings (Story 4.4): only the master gain schedule.
struct Master {
  std::optional<Gain> gain;
};

struct Recipe {
  std::string schema_version;
  std::string engine_version;
  std::uint64_t seed = 0;
  std::string author;
  std::string date;
  std::string rationale;
  double length_s = 0.0;
  double loudness_target_lufs = 0.0;
  std::optional<double> loudness_gain_db;
  std::optional<std::string> loudness_hash;
  std::optional<ThetaReference> theta_reference;
  std::optional<GammaPac> gamma_pac;
  std::optional<Binaural> binaural;
  std::optional<Loop> loop;  // Story 2.7; absent when the field is absent
  std::optional<Master> master;  // Story 4.4; absent when the field is absent
  std::string hash;  // recipe hash, 64 lowercase hex digits
  // Story 4.2: the loudness hash of this recipe (docs/signal-spec.md,
  // Loudness gain), 64 lowercase hex digits; not the stored loudness_hash.
  std::string loudness_hash_computed;
};

struct ParseResult {
  std::optional<Recipe> recipe;  // empty on error
  Error error;
};

// Supported schema major versions, as written in a schema_version.major error.
inline constexpr std::string_view kSupportedSchemaMajors = "1";

ParseResult parse(std::string_view utf8);

}  // namespace arcani::recipe

#endif  // ARCANI_RECIPE_RECIPE_HPP
