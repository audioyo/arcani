// Recipe field table. Keep in step with recipes/recipe.schema.json; the
// field-table test fails on any difference.

#include "recipe/field_table.hpp"

namespace arcani::recipe {

namespace {

using enum FieldType;
using enum FieldTag;

constexpr Field kFields[] = {
    {"/schema_version", String, None, true},
    {"/engine_version", String, None, true},
    {"/seed", Integer, None, true},
    {"/author", String, HashExcluded, true},
    {"/date", String, HashExcluded, true},
    {"/rationale", String, HashExcluded, true},
    {"/length_s", Number, LoudnessRelevant, true},
    {"/loudness_target_lufs", Number, LoudnessRelevant, true},
    {"/loudness_gain_db", Number, HashExcluded, false},
    {"/loudness_hash", String, HashExcluded, false},
    {"/theta_reference", Object, LoudnessRelevant, false},
    {"/theta_reference/carrier_hz", Number, LoudnessRelevant, true},
    {"/binaural", Object, LoudnessRelevant, false},
    {"/binaural/carrier_left_hz", Number, LoudnessRelevant, true},
    {"/binaural/beat_rate_hz", Number, LoudnessRelevant, true},
};

}  // namespace

std::span<const Field> fields() noexcept {
  return kFields;
}

}  // namespace arcani::recipe
