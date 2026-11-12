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
    // Written by the measure pass, not authored; Story 4.2 checks it.
    {"/loudness_gain_db", Number, HashExcluded, false, "", 1.0},
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
    // Story 2.3. Required with smooth_swell and rejected with uncoupled; both
    // rules run after every range check (validate/validate.hpp).
    {"/gamma_pac/coupling_phase_deg", Number, LoudnessRelevant, false, "coupling-phase", 1.0},
    {"/binaural", Object, LoudnessRelevant, false, "", 1.0},
    {"/binaural/carrier_left_hz", Number, LoudnessRelevant, true, "binaural-carrier", 1.0},
    // The derived right carrier (carrier_left_hz + beat_rate_hz, row
    // binaural-carrier-right) is checked after this field and reported on it.
    {"/binaural/beat_rate_hz", Number, LoudnessRelevant, true, "beat-rate", 1.0},
};

}  // namespace

std::span<const Field> fields() noexcept {
  return kFields;
}

}  // namespace arcani::recipe
