// Recipe field table (Story 1.1): every property of recipes/recipe.schema.json
// with its JSON type, x-arcani-tag, and whether its parent requires it.
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
};

// Every schema property, objects included, parents before their children,
// in schema order.
std::span<const Field> fields() noexcept;

}  // namespace arcani::recipe

#endif  // ARCANI_RECIPE_FIELD_TABLE_HPP
