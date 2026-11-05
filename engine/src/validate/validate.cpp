// Recipe validator: locked ranges and the carrier rule.

#include "validate/validate.hpp"

#include <cstddef>
#include <iterator>
#include <optional>
#include <string>
#include <utility>

#include "json/number.hpp"
#include "recipe/field_table.hpp"

namespace arcani::validate {

namespace {

// Engine copy of the ranges.tsv rows the field table names, in row units.
// Keep in step with tests/tables/ranges.tsv; the range table test fails on
// any difference. kRowUnits holds each row's unit, in the same order.
constexpr RangeRow kRows[] = {
    {"session-length", 0.0, 8.0, false},
    {"loudness-tones", -36.0, -36.0, false},
    {"theta-carrier", 100.0, 500.0, false},
    {"binaural-carrier", 0.0, 1000.0, true},
    {"beat-rate", 0.0, 30.0, true},
    {"binaural-carrier-right", 0.0, 1030.0, true},
};
constexpr std::string_view kRowUnits[] = {"h", "LUFS-I", "Hz", "Hz", "Hz", "Hz"};
static_assert(std::size(kRows) == std::size(kRowUnits));

constexpr std::string_view kRightCarrierRow = "binaural-carrier-right";
constexpr std::string_view kBeatRatePath = "/binaural/beat_rate_hz";

// Index of a row in kRows, or std::size(kRows) when absent.
constexpr std::size_t row_index(std::string_view id) noexcept {
  for (std::size_t i = 0; i < std::size(kRows); ++i) {
    if (kRows[i].id == id) {
      return i;
    }
  }
  return std::size(kRows);
}

// Every row the field table can name must be in kRows.
static_assert(row_index("session-length") < std::size(kRows));
static_assert(row_index(kRightCarrierRow) < std::size(kRows));

// The value of a range-governed field, or nothing when its layer is absent.
std::optional<double> field_value(const recipe::Recipe& r, std::string_view path) {
  if (path == "/length_s") {
    return r.length_s;
  }
  if (path == "/loudness_target_lufs") {
    return r.loudness_target_lufs;
  }
  if (path == "/theta_reference/carrier_hz") {
    if (r.theta_reference) {
      return r.theta_reference->carrier_hz;
    }
    return std::nullopt;
  }
  if (path == "/binaural/carrier_left_hz") {
    if (r.binaural) {
      return r.binaural->carrier_left_hz;
    }
    return std::nullopt;
  }
  if (path == kBeatRatePath) {
    if (r.binaural) {
      return r.binaural->beat_rate_hz;
    }
    return std::nullopt;
  }
  return std::nullopt;
}

bool ends_with(std::string_view s, std::string_view tail) noexcept {
  return s.size() >= tail.size() && s.substr(s.size() - tail.size()) == tail;
}

// Checks value against row i at the given scale. unit is the field unit.
std::optional<recipe::Error> check_row(std::string_view parameter, double value, std::size_t i,
                                       double scale, std::string_view unit) {
  const RangeRow& row = kRows[i];
  const double lo = row.min * scale;
  const double hi = row.max * scale;
  const auto limit = [&](std::string_view op, double bound) {
    std::string s(op);
    s += ' ';
    s += json::format_number(bound);
    s += ' ';
    s += unit;
    s += " (row ";
    s += row.id;
    s += ')';
    return s;
  };
  if (!(value >= lo)) {
    return recipe::Error{std::string(parameter), json::format_number(value), "range.min",
                         limit(">=", lo)};
  }
  const bool over = row.max_exclusive ? !(value < hi) : !(value <= hi);
  if (over) {
    return recipe::Error{std::string(parameter), json::format_number(value), "range.max",
                         limit(row.max_exclusive ? "<" : "<=", hi)};
  }
  return std::nullopt;
}

}  // namespace

std::span<const RangeRow> range_rows() noexcept { return kRows; }

std::optional<recipe::Error> check_ranges(const recipe::Recipe& r) {
  for (const recipe::Field& f : recipe::fields()) {
    if (f.range_row.empty()) {
      continue;
    }
    const std::optional<double> value = field_value(r, f.path);
    if (!value) {
      continue;
    }
    const std::size_t i = row_index(f.range_row);
    if (i == std::size(kRows)) {
      // A field names a row the engine table lacks: the range table test
      // fails on this; reject rather than let the value through unchecked.
      return recipe::Error{std::string(f.path), json::format_number(*value), "range.row",
                           std::string(f.range_row)};
    }
    // A seconds field over a row in h (scale 3600) reports in s; any other
    // field reports in its row unit.
    const std::string_view unit =
        (f.range_scale != 1.0 && ends_with(f.path, "_s")) ? std::string_view("s") : kRowUnits[i];
    if (auto e = check_row(f.path, *value, i, f.range_scale, unit)) {
      return e;
    }
    if (f.path == kBeatRatePath) {
      // Derived right carrier, summed in binary64 as compile does, so the
      // check sees the exact frequency the binaural stub plays.
      const double right = r.binaural->carrier_left_hz + r.binaural->beat_rate_hz;
      const std::size_t j = row_index(kRightCarrierRow);
      if (auto e = check_row(kBeatRatePath, right, j, 1.0, kRowUnits[j])) {
        return e;
      }
    }
  }
  return std::nullopt;
}

std::optional<recipe::Error> check_carrier_rule(std::string_view parameter, double carrier_hz,
                                                double rate_min_hz, double rate_max_hz) {
  // The interval minimum never decides: the maximum is the worst case.
  static_cast<void>(rate_min_hz);
  const double need = kCarrierRatio * rate_max_hz;
  if (carrier_hz >= need) {
    return std::nullopt;
  }
  std::string limit = ">= ";
  limit += json::format_number(need);
  limit += " Hz (";
  limit += json::format_number(kCarrierRatio);
  limit += " x ";
  limit += json::format_number(rate_max_hz);
  limit += " Hz, row carrier-rule)";
  return recipe::Error{std::string(parameter), json::format_number(carrier_hz), "carrier_rule",
                       std::move(limit)};
}

}  // namespace arcani::validate
