// Recipe validator (Story 1.3): locked ranges, the carrier rule, (Story 2.1)
// the theta shape rule, (Story 2.2) the gamma carrier wave rule, (Story 2.3)
// the coupling rules, and (Story 2.5) the beat rate cycle worst case and the
// binaural waveform rule.
//
// check_ranges() runs after parse in both compile modes. It walks the field
// table in order and checks every present field that names a range row
// against the engine copy of that row (range_rows()), then checks the derived
// right binaural carrier (carrier_left_hz + beat_rate_hz, row
// binaural-carrier-right) right after beat_rate_hz. (Story 2.5) At
// /binaural/beat_rate_cycle/swing_hz, which names no row, it runs the beat
// rate cycle worst case (docs/signal-spec.md, Rate curve, Range checks):
// swing_hz >= 0 (rule range.min, limit ">= 0 Hz"), beat_rate_hz - swing_hz
// and beat_rate_hz + swing_hz against beat-rate, and
// (carrier_left_hz + beat_rate_hz) + swing_hz against binaural-carrier-right,
// each reported on swing_hz with the derived value; period_s and
// start_phase_deg follow against their rows. The first failure wins.
//
// Bounds: min is always inclusive; max is inclusive or exclusive per the
// row's max_bound. Values are compared in binary64 against bound *
// range_scale, which is exact for every v0.1 row.
//
// Errors: rule range.min or range.max; value the shortest round-trip text of
// the field value; limit "<op> <bound> <unit> (row <id>)", for example
// ">= 100 Hz (row theta-carrier)" or "<= 28800 s (row session-length)".
// Rule range.row: a field names a range row but the validator has no mapping
// for it (no value lookup for its path, or no engine entry for its row);
// parameter the field path, value empty, limit naming the missing mapping.
// It means the field table and the validator are out of step, never a bad
// recipe value, and it rejects rather than let the field through unchecked.
//
// The engine range table is hand-written, one entry per row the field table
// names. tests/cpp/test_validate.cpp proves it equals tests/tables/ranges.tsv;
// the engine reads no file.

#ifndef ARCANI_VALIDATE_VALIDATE_HPP
#define ARCANI_VALIDATE_VALIDATE_HPP

#include <optional>
#include <span>
#include <string_view>

#include "recipe/recipe.hpp"

namespace arcani::validate {

struct RangeRow {
  std::string_view id;  // ranges.tsv row id
  double min;           // row units (h for session-length), always inclusive
  double max;           // row units
  bool max_exclusive;   // ranges.tsv max_bound == "exclusive"
  std::string_view unit = "Hz";  // ranges.tsv unit
};

// One entry per row the field table names, plus binaural-carrier-right.
// beat-rate is also the row of the beat rate cycle worst case.
std::span<const RangeRow> range_rows() noexcept;

// The first locked-range fault of a parsed recipe, or nothing.
std::optional<recipe::Error> check_ranges(const recipe::Recipe& r);

// Rules after the ranges (Stories 2.1 and 2.2), run by compile after
// check_ranges() and before final.required, first failure wins:
// 1. carrier rule on the theta reference: carrier_hz against rate_hz;
// 2. a custom theta shape: parameter /theta_reference/shape, value custom,
//    rule kShapeNotModeledRule, limit kModeledThetaShapes. The signal spec
//    models no custom envelope curve, so it does not exist;
// 3. carrier rule on the gamma PAC layer: /gamma_pac/carrier_hz against
//    rate_hz;
// 4. a non-sine gamma carrier: parameter /gamma_pac/carrier_wave, value the
//    text (triangle or softened_square), rule kNonSineCarrierRule, limit
//    kModeledGammaCarrierWaves. The signal spec models only the sine carrier;
// 5. (AD-5, docs/signal-spec.md, Coupling and Bursts) coupled gamma
//    (smooth_swell or bursts) with am_depth_percent > 0 and no theta
//    reference, or a theta reference at am_depth_percent 0: parameter
//    /gamma_pac/coupling, value the coupling (smooth_swell or bursts), rule
//    kCoupledNeedsThetaRule, limit kCoupledNeedsThetaLimit;
// 6. coupled gamma without coupling_phase_deg: parameter
//    /gamma_pac/coupling_phase_deg, value absent, rule kCoupledNeedsPhaseRule,
//    limit kCoupledNeedsPhaseLimit (smooth_swell) or kBurstsNeedsPhaseLimit
//    (bursts);
// 7. uncoupled with coupling_phase_deg: parameter
//    /gamma_pac/coupling_phase_deg, value the phase, rule
//    kPhaseNeedsCoupledRule, limit kPhaseNeedsCoupledLimit;
// 8. (Story 2.5, docs/signal-spec.md, Binaural layer) binaural waveform
//    triangle: parameter /binaural/waveform, value triangle, rule
//    kNonSineBinauralRule, limit kModeledBinauralWaveforms. The signal spec
//    models only the sine binaural layer.
std::optional<recipe::Error> check_rules(const recipe::Recipe& r);

inline constexpr std::string_view kShapeNotModeledRule = "shape not modeled in the signal spec";
inline constexpr std::string_view kModeledThetaShapes = "sine, smoothed_on_off, sawtooth, reverse_saw";
inline constexpr std::string_view kNonSineCarrierRule = "non-sine carrier not modeled";
inline constexpr std::string_view kModeledGammaCarrierWaves = "sine";
inline constexpr std::string_view kCoupledNeedsThetaRule = "coupled gamma needs a theta reference with AM depth";
inline constexpr std::string_view kCoupledNeedsThetaLimit = "theta_reference present with am_depth_percent > 0";
inline constexpr std::string_view kCoupledNeedsPhaseRule = "coupled gamma needs a coupling phase";
inline constexpr std::string_view kCoupledNeedsPhaseLimit = "present with coupling smooth_swell";
inline constexpr std::string_view kBurstsNeedsPhaseLimit = "present with coupling bursts";
inline constexpr std::string_view kPhaseNeedsCoupledRule = "coupling phase needs coupled gamma";
inline constexpr std::string_view kPhaseNeedsCoupledLimit = "absent with coupling uncoupled";
inline constexpr std::string_view kNonSineBinauralRule = "non-sine binaural not modeled";
inline constexpr std::string_view kModeledBinauralWaveforms = "sine";

// Carrier rule: every modulated carrier is at least this many times its
// modulation rate (threshold row carrier-rule).
inline constexpr double kCarrierRatio = 4.0;

// Passes when carrier_hz >= kCarrierRatio * rate_max_hz: a rate interval is
// judged by its maximum, the worst case. Failure: parameter as given, value
// the carrier, rule carrier_rule, limit for example
// ">= 24 Hz (4 x 6 Hz, row carrier-rule)". Compile calls it through
// check_rules() for the theta reference (Story 2.1) and the gamma PAC layer
// (Story 2.2).
std::optional<recipe::Error> check_carrier_rule(std::string_view parameter, double carrier_hz,
                                                double rate_min_hz, double rate_max_hz);

}  // namespace arcani::validate

#endif  // ARCANI_VALIDATE_VALIDATE_HPP
