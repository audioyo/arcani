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

namespace arcani::recipe {

struct Error {
  std::string parameter;  // JSON Pointer of the field ("" = whole document), or for a
                          // syntax fault the byte offset in decimal digits
  std::string value;      // the offending value as text, may be empty
  std::string rule;       // unknown_property, required, type, pattern, minimum, maximum,
                          // schema_version.major, or the json.* parser rule
  std::string limit;      // what the rule allows, for example the supported majors "1"
};

struct ThetaReference {
  double carrier_hz = 0.0;
};

struct Binaural {
  double carrier_left_hz = 0.0;
  double beat_rate_hz = 0.0;
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
  std::optional<Binaural> binaural;
  std::string hash;  // recipe hash, 64 lowercase hex digits
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
