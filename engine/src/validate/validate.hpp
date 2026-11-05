// Recipe validator (Story 1.3): locked ranges and the carrier rule.
//
// check_ranges() runs after parse in both compile modes. It walks the field
// table in order and checks every present field that names a range row
// against the engine copy of that row (range_rows()), then checks the derived
// right binaural carrier (carrier_left_hz + beat_rate_hz, row
// binaural-carrier-right) right after beat_rate_hz. The first failure wins.
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
std::span<const RangeRow> range_rows() noexcept;

// The first locked-range fault of a parsed recipe, or nothing.
std::optional<recipe::Error> check_ranges(const recipe::Recipe& r);

// Carrier rule: every modulated carrier is at least this many times its
// modulation rate (threshold row carrier-rule).
inline constexpr double kCarrierRatio = 4.0;

// Passes when carrier_hz >= kCarrierRatio * rate_max_hz: a rate interval is
// judged by its maximum, the worst case. Failure: parameter as given, value
// the carrier, rule carrier_rule, limit for example
// ">= 24 Hz (4 x 6 Hz, row carrier-rule)". No v0.1 recipe field pairs a
// carrier with a rate, so compile has no caller until Epic 2.
std::optional<recipe::Error> check_carrier_rule(std::string_view parameter, double carrier_hz,
                                                double rate_min_hz, double rate_max_hz);

}  // namespace arcani::validate

#endif  // ARCANI_VALIDATE_VALIDATE_HPP
