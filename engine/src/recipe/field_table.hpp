// Recipe field table (Story 1.1): every property of recipes/recipe.schema.json
// with its JSON type, x-arcani-tag, whether its parent requires it, and
// (Story 1.3) its locked-range row.
// tests/cpp/test_recipe.cpp checks this table against the schema file, so the
// engine and the Python hash tool (which reads the tags from the schema) agree.

#ifndef ARCANI_RECIPE_FIELD_TABLE_HPP
#define ARCANI_RECIPE_FIELD_TABLE_HPP

#include <span>
#include <string_view>

namespace arcani::recipe {

enum class FieldType { String, Number, Integer, Object };

enum class FieldTag { None, HashExcluded, LoudnessRelevant };

struct Field {
  std::string_view path;  // JSON Pointer, for example "/binaural/beat_rate_hz"
  FieldType type;
  FieldTag tag;   // schema x-arcani-tag: none, hash-excluded, loudness-relevant
  bool required;  // required within its parent object
  // Story 1.3: the locked-range row in tests/tables/ranges.tsv that governs
  // this field ("" when it is not range-governed), and the factor from the
  // row unit to the field unit (1, or 3600 for a row in h on a _s field).
  // validate/validate.hpp checks each present field against its row.
  std::string_view range_row = {};
  double range_scale = 1.0;
};

// Every schema property, objects included, parents before their children,
// in schema order.
std::span<const Field> fields() noexcept;

}  // namespace arcani::recipe

#endif  // ARCANI_RECIPE_FIELD_TABLE_HPP
