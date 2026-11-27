// Recipe field table. Keep in step with recipes/recipe.schema.json; the
// field-table test fails on any difference.

#include "recipe/field_table.hpp"

namespace arcani::recipe {

namespace {

using enum FieldType;
using enum FieldTag;

constexpr Field kFields[] = {
    {"/schema_version", String, None, true, "", 1.0},
    {"/engine_version", String, None, true, "", 1.0},
    // Schema-bounded (0 to 2^53 - 1); no range row.
    {"/seed", Integer, None, true, "", 1.0},
    {"/author", String, HashExcluded, true, "", 1.0},
    {"/date", String, HashExcluded, true, "", 1.0},
    {"/rationale", String, HashExcluded, true, "", 1.0},
    {"/length_s", Number, LoudnessRelevant, true, "session-length", 3600.0},  // 8 h = 28800 s
    {"/loudness_target_lufs", Number, LoudnessRelevant, true, "loudness-tones", 1.0},
    // Written by arcani-render --store-gain, not authored; Story 4.2: held to
    // row loudness-gain in both modes (docs/signal-spec.md, Loudness gain).
    {"/loudness_gain_db", Number, HashExcluded, false, "loudness-gain", 1.0},
    {"/loudness_hash", String, HashExcluded, false, "", 1.0},
    {"/theta_reference", Object, LoudnessRelevant, false, "", 1.0},
    {"/theta_reference/carrier_hz", Number, LoudnessRelevant, true, "theta-carrier", 1.0},
    // Story 2.1. The carrier rule (carrier_hz >= 4 x rate_hz) runs after
    // every range check; see validate/validate.hpp.
    {"/theta_reference/rate_hz", Number, LoudnessRelevant, true, "theta-rate", 1.0},
    {"/theta_reference/am_depth_percent", Number, LoudnessRelevant, true, "theta-depth", 1.0},
    // One of the schema enum members (recipe::kThetaShapeEnum); custom is
    // schema-valid and rejected at compile.
    {"/theta_reference/shape", String, LoudnessRelevant, true, "", 1.0},
    // Story 2.6 (docs/signal-spec.md, Rate curve). swing_hz has no row: the
    // worst-case checks (swing >= 0, rate_hz -/+ swing_hz against theta-rate)
    // run when the validator reaches it (validate/validate.hpp).
    {"/theta_reference/rate_cycle", Object, LoudnessRelevant, false, "", 1.0},
    {"/theta_reference/rate_cycle/swing_hz", Number, LoudnessRelevant, true, "", 1.0},
    {"/theta_reference/rate_cycle/period_s", Number, LoudnessRelevant, true, "rate-cycle-period", 1.0},
    {"/theta_reference/rate_cycle/start_phase_deg", Number, LoudnessRelevant, true, "rate-cycle-start-phase", 1.0},
    // Story 4.4 (docs/signal-spec.md, Gain ramps): the gain schedule, last in
    // its object. The ramp count is checked by name against row
    // gain-ramp-count; start_s and duration_s are bounded by the gain rules.
    {"/theta_reference/gain", Object, LoudnessRelevant, false, "", 1.0},
    {"/theta_reference/gain/initial", Number, LoudnessRelevant, true, "layer-gain", 1.0},
    {"/theta_reference/gain/ramps", Array, LoudnessRelevant, false, "", 1.0},
    {"/theta_reference/gain/ramps/*/start_s", Number, LoudnessRelevant, true, "", 1.0},
    {"/theta_reference/gain/ramps/*/duration_s", Number, LoudnessRelevant, true, "", 1.0},
    {"/theta_reference/gain/ramps/*/to", Number, LoudnessRelevant, true, "layer-gain", 1.0},
    // Story 2.2, uncoupled only. The carrier rule (carrier_hz >= 4 x rate_hz)
    // and the carrier wave rule run after every range check; see
    // validate/validate.hpp.
    {"/gamma_pac", Object, LoudnessRelevant, false, "", 1.0},
    {"/gamma_pac/carrier_hz", Number, LoudnessRelevant, true, "gamma-carrier", 1.0},
    {"/gamma_pac/rate_hz", Number, LoudnessRelevant, true, "gamma-rate", 1.0},
    {"/gamma_pac/am_depth_percent", Number, LoudnessRelevant, true, "coupling-depth", 1.0},
    // One of the schema enum members (recipe::kGammaCarrierWaveEnum); triangle
    // and softened_square are schema-valid and rejected at compile.
    {"/gamma_pac/carrier_wave", String, LoudnessRelevant, true, "", 1.0},
    // One of the schema enum members (recipe::kGammaCouplingEnum).
    {"/gamma_pac/coupling", String, LoudnessRelevant, true, "", 1.0},
    // Story 2.3. Required with smooth_swell and (Story 2.4) bursts, and
    // rejected with uncoupled; both rules run after every range check
    // (validate/validate.hpp).
    {"/gamma_pac/coupling_phase_deg", Number, LoudnessRelevant, false, "coupling-phase", 1.0},
    // Story 2.6 (docs/signal-spec.md, Rate curve). swing_hz has no row: the
    // worst-case checks (swing >= 0, rate_hz -/+ swing_hz against gamma-rate)
    // run when the validator reaches it (validate/validate.hpp).
    {"/gamma_pac/rate_cycle", Object, LoudnessRelevant, false, "", 1.0},
    {"/gamma_pac/rate_cycle/swing_hz", Number, LoudnessRelevant, true, "", 1.0},
    {"/gamma_pac/rate_cycle/period_s", Number, LoudnessRelevant, true, "rate-cycle-period", 1.0},
    {"/gamma_pac/rate_cycle/start_phase_deg", Number, LoudnessRelevant, true, "rate-cycle-start-phase", 1.0},
    // Story 4.4 (docs/signal-spec.md, Gain ramps): the gain schedule, last in
    // its object. The ramp count is checked by name against row
    // gain-ramp-count; start_s and duration_s are bounded by the gain rules.
    {"/gamma_pac/gain", Object, LoudnessRelevant, false, "", 1.0},
    {"/gamma_pac/gain/initial", Number, LoudnessRelevant, true, "layer-gain", 1.0},
    {"/gamma_pac/gain/ramps", Array, LoudnessRelevant, false, "", 1.0},
    {"/gamma_pac/gain/ramps/*/start_s", Number, LoudnessRelevant, true, "", 1.0},
    {"/gamma_pac/gain/ramps/*/duration_s", Number, LoudnessRelevant, true, "", 1.0},
    {"/gamma_pac/gain/ramps/*/to", Number, LoudnessRelevant, true, "layer-gain", 1.0},
    {"/binaural", Object, LoudnessRelevant, false, "", 1.0},
    {"/binaural/carrier_left_hz", Number, LoudnessRelevant, true, "binaural-carrier", 1.0},
    // The derived right carrier (carrier_left_hz + beat_rate_hz, row
    // binaural-carrier-right) is checked after this field and reported on it.
    {"/binaural/beat_rate_hz", Number, LoudnessRelevant, true, "beat-rate", 1.0},
    // Story 2.5 (docs/signal-spec.md, Rate curve). swing_hz has no row: the
    // worst-case checks (swing >= 0, beat_rate_hz -/+ swing_hz against
    // beat-rate, the highest right carrier against binaural-carrier-right)
    // run when the validator reaches it (validate/validate.hpp).
    {"/binaural/beat_rate_cycle", Object, LoudnessRelevant, false, "", 1.0},
    {"/binaural/beat_rate_cycle/swing_hz", Number, LoudnessRelevant, true, "", 1.0},
    {"/binaural/beat_rate_cycle/period_s", Number, LoudnessRelevant, true, "rate-cycle-period", 1.0},
    {"/binaural/beat_rate_cycle/start_phase_deg", Number, LoudnessRelevant, true, "rate-cycle-start-phase", 1.0},
    // One of the schema enum members (recipe::kBinauralWaveformEnum); triangle
    // is schema-valid and rejected at compile.
    {"/binaural/waveform", String, LoudnessRelevant, false, "", 1.0},
    // Story 4.4 (docs/signal-spec.md, Gain ramps): the gain schedule, last in
    // its object. The ramp count is checked by name against row
    // gain-ramp-count; start_s and duration_s are bounded by the gain rules.
    {"/binaural/gain", Object, LoudnessRelevant, false, "", 1.0},
    {"/binaural/gain/initial", Number, LoudnessRelevant, true, "layer-gain", 1.0},
    {"/binaural/gain/ramps", Array, LoudnessRelevant, false, "", 1.0},
    {"/binaural/gain/ramps/*/start_s", Number, LoudnessRelevant, true, "", 1.0},
    {"/binaural/gain/ramps/*/duration_s", Number, LoudnessRelevant, true, "", 1.0},
    {"/binaural/gain/ramps/*/to", Number, LoudnessRelevant, true, "layer-gain", 1.0},
    // Story 2.7 (docs/signal-spec.md, Loop). No member names a row: the mode
    // picks max-run-time-focus or max-run-time-learn for max_run_time_min,
    // and the loop rules run after every range check (validate/validate.hpp).
    {"/loop", Object, LoudnessRelevant, false, "", 1.0},
    // One of the schema enum members (recipe::kLoopModeEnum).
    {"/loop/mode", String, LoudnessRelevant, true, "", 1.0},
    {"/loop/opening_s", Number, LoudnessRelevant, true, "", 1.0},
    {"/loop/body_s", Number, LoudnessRelevant, true, "", 1.0},
    {"/loop/max_run_time_min", Number, LoudnessRelevant, true, "", 1.0},
    // Story 4.4: the master gain schedule, after the loudness gain.
    {"/master", Object, LoudnessRelevant, false, "", 1.0},
    {"/master/gain", Object, LoudnessRelevant, false, "", 1.0},
    {"/master/gain/initial", Number, LoudnessRelevant, true, "layer-gain", 1.0},
    {"/master/gain/ramps", Array, LoudnessRelevant, false, "", 1.0},
    {"/master/gain/ramps/*/start_s", Number, LoudnessRelevant, true, "", 1.0},
    {"/master/gain/ramps/*/duration_s", Number, LoudnessRelevant, true, "", 1.0},
    {"/master/gain/ramps/*/to", Number, LoudnessRelevant, true, "layer-gain", 1.0},
};

}  // namespace

std::span<const Field> fields() noexcept {
  return kFields;
}

}  // namespace arcani::recipe
