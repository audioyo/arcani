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
// any difference, unit included.
constexpr RangeRow kRows[] = {
    {"session-length", 0.0, 8.0, false, "h"},
    {"loudness-tones", -36.0, -36.0, false, "LUFS-I"},
    {"theta-rate", 1.0, 6.0, false, "Hz"},
    {"theta-carrier", 100.0, 500.0, false, "Hz"},
    {"theta-depth", 0.0, 100.0, false, "percent"},
    {"gamma-rate", 30.0, 60.0, false, "Hz"},
    {"gamma-carrier", 200.0, 500.0, false, "Hz"},
    {"coupling-depth", 0.0, 100.0, false, "percent"},
    {"coupling-phase", 0.0, 360.0, false, "degrees"},
    {"binaural-carrier", 0.0, 1000.0, true, "Hz"},
    {"beat-rate", 0.0, 30.0, true, "Hz"},
    {"binaural-carrier-right", 0.0, 1030.0, true, "Hz"},
    {"rate-cycle-period", 60.0, 60.0, false, "s"},
    {"rate-cycle-start-phase", 0.0, 360.0, false, "degrees"},
};

constexpr std::string_view kRightCarrierRow = "binaural-carrier-right";
constexpr std::string_view kBeatRateRow = "beat-rate";
constexpr std::string_view kBeatRatePath = "/binaural/beat_rate_hz";
constexpr std::string_view kSwingPath = "/binaural/beat_rate_cycle/swing_hz";

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
static_assert(row_index(kBeatRateRow) < std::size(kRows));

// A range-governed field's value lookup. known is false for a path the
// validator has no mapping for; value is empty when the field's layer is
// absent.
struct Lookup {
  bool known;
  std::optional<double> value;
};

Lookup field_value(const recipe::Recipe& r, std::string_view path) {
  if (path == "/length_s") {
    return {true, r.length_s};
  }
  if (path == "/loudness_target_lufs") {
    return {true, r.loudness_target_lufs};
  }
  if (path == "/theta_reference/carrier_hz") {
    if (r.theta_reference) {
      return {true, r.theta_reference->carrier_hz};
    }
    return {true, std::nullopt};
  }
  if (path == "/theta_reference/rate_hz") {
    if (r.theta_reference) {
      return {true, r.theta_reference->rate_hz};
    }
    return {true, std::nullopt};
  }
  if (path == "/theta_reference/am_depth_percent") {
    if (r.theta_reference) {
      return {true, r.theta_reference->am_depth_percent};
    }
    return {true, std::nullopt};
  }
  if (path == "/gamma_pac/carrier_hz") {
    if (r.gamma_pac) {
      return {true, r.gamma_pac->carrier_hz};
    }
    return {true, std::nullopt};
  }
  if (path == "/gamma_pac/rate_hz") {
    if (r.gamma_pac) {
      return {true, r.gamma_pac->rate_hz};
    }
    return {true, std::nullopt};
  }
  if (path == "/gamma_pac/am_depth_percent") {
    if (r.gamma_pac) {
      return {true, r.gamma_pac->am_depth_percent};
    }
    return {true, std::nullopt};
  }
  if (path == "/gamma_pac/coupling_phase_deg") {
    if (r.gamma_pac && r.gamma_pac->coupling_phase_deg) {
      return {true, *r.gamma_pac->coupling_phase_deg};
    }
    return {true, std::nullopt};
  }
  if (path == "/binaural/carrier_left_hz") {
    if (r.binaural) {
      return {true, r.binaural->carrier_left_hz};
    }
    return {true, std::nullopt};
  }
  if (path == kBeatRatePath) {
    if (r.binaural) {
      return {true, r.binaural->beat_rate_hz};
    }
    return {true, std::nullopt};
  }
  if (path == "/binaural/beat_rate_cycle/period_s") {
    if (r.binaural && r.binaural->beat_rate_cycle) {
      return {true, r.binaural->beat_rate_cycle->period_s};
    }
    return {true, std::nullopt};
  }
  if (path == "/binaural/beat_rate_cycle/start_phase_deg") {
    if (r.binaural && r.binaural->beat_rate_cycle) {
      return {true, r.binaural->beat_rate_cycle->start_phase_deg};
    }
    return {true, std::nullopt};
  }
  return {false, std::nullopt};
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

// Worst case of a beat rate cycle (docs/signal-spec.md, Rate curve, Range
// checks), in order: the swing itself, the lowest and highest rate against
// beat-rate, then the highest right carrier against binaural-carrier-right.
// Each sum is the one binary64 rounding the spec names.
std::optional<recipe::Error> check_cycle_worst_case(const recipe::Binaural& b) {
  const recipe::BeatRateCycle& cycle = *b.beat_rate_cycle;
  const double swing = cycle.swing_hz;
  if (!(swing >= 0.0)) {
    return recipe::Error{std::string(kSwingPath), json::format_number(swing), "range.min", ">= 0 Hz"};
  }
  const std::size_t beat = row_index(kBeatRateRow);
  const double lowest = b.beat_rate_hz - swing;
  if (auto e = check_row(kSwingPath, lowest, beat, 1.0, kRows[beat].unit)) {
    return e;
  }
  const double highest = b.beat_rate_hz + swing;
  if (auto e = check_row(kSwingPath, highest, beat, 1.0, kRows[beat].unit)) {
    return e;
  }
  const double center = b.carrier_left_hz + b.beat_rate_hz;  // f_C, as compile sums it
  const double right = center + swing;
  const std::size_t j = row_index(kRightCarrierRow);
  return check_row(kSwingPath, right, j, 1.0, kRows[j].unit);
}

}  // namespace

std::span<const RangeRow> range_rows() noexcept { return kRows; }

std::optional<recipe::Error> check_ranges(const recipe::Recipe& r) {
  for (const recipe::Field& f : recipe::fields()) {
    if (f.path == kSwingPath) {
      // No range row of its own: the worst-case checks bound it.
      if (r.binaural && r.binaural->beat_rate_cycle) {
        if (auto e = check_cycle_worst_case(*r.binaural)) {
          return e;
        }
      }
      continue;
    }
    if (f.range_row.empty()) {
      continue;
    }
    const Lookup found = field_value(r, f.path);
    if (!found.known) {
      return recipe::Error{std::string(f.path), "", "range.row",
                           "a value lookup for the field (row " + std::string(f.range_row) + ")"};
    }
    if (!found.value) {
      continue;  // layer absent
    }
    const double value = *found.value;
    const std::size_t i = row_index(f.range_row);
    if (i == std::size(kRows)) {
      return recipe::Error{std::string(f.path), "", "range.row",
                           "an engine range table entry for row " + std::string(f.range_row)};
    }
    // A seconds field over a row in h (scale 3600) reports in s; any other
    // field reports in its row unit.
    const std::string_view unit =
        (f.range_scale != 1.0 && ends_with(f.path, "_s")) ? std::string_view("s") : kRows[i].unit;
    if (auto e = check_row(f.path, value, i, f.range_scale, unit)) {
      return e;
    }
    if (f.path == kBeatRatePath) {
      // Derived right carrier, summed in binary64 as compile does, so the
      // check sees the exact frequency the binaural stub plays.
      const double right = r.binaural->carrier_left_hz + r.binaural->beat_rate_hz;
      const std::size_t j = row_index(kRightCarrierRow);
      if (auto e = check_row(kBeatRatePath, right, j, 1.0, kRows[j].unit)) {
        return e;
      }
    }
  }
  return std::nullopt;
}

std::optional<recipe::Error> check_rules(const recipe::Recipe& r) {
  if (r.theta_reference) {
    const recipe::ThetaReference& theta = *r.theta_reference;
    // A fixed rate: the interval is the one value.
    if (auto e = check_carrier_rule("/theta_reference/carrier_hz", theta.carrier_hz, theta.rate_hz,
                                    theta.rate_hz)) {
      return e;
    }
    if (theta.shape == recipe::ThetaShape::Custom) {
      return recipe::Error{"/theta_reference/shape", "custom", std::string(kShapeNotModeledRule),
                           std::string(kModeledThetaShapes)};
    }
  }
  if (r.gamma_pac) {
    const recipe::GammaPac& gamma = *r.gamma_pac;
    // A fixed rate: the interval is the one value.
    if (auto e = check_carrier_rule("/gamma_pac/carrier_hz", gamma.carrier_hz, gamma.rate_hz,
                                    gamma.rate_hz)) {
      return e;
    }
    if (gamma.carrier_wave == recipe::GammaCarrierWave::Triangle) {
      return recipe::Error{"/gamma_pac/carrier_wave", "triangle", std::string(kNonSineCarrierRule),
                           std::string(kModeledGammaCarrierWaves)};
    }
    if (gamma.carrier_wave == recipe::GammaCarrierWave::SoftenedSquare) {
      return recipe::Error{"/gamma_pac/carrier_wave", "softened_square",
                           std::string(kNonSineCarrierRule), std::string(kModeledGammaCarrierWaves)};
    }
    const bool bursts = gamma.coupling == recipe::GammaCoupling::Bursts;
    const bool coupled = bursts || gamma.coupling == recipe::GammaCoupling::SmoothSwell;
    // AD-5: coupled gamma with depth reads the theta reference phase, so the
    // theta reference must exist and carry AM depth. Depth 0 scales nothing.
    if (coupled && gamma.am_depth_percent > 0.0 &&
        !(r.theta_reference && r.theta_reference->am_depth_percent > 0.0)) {
      return recipe::Error{"/gamma_pac/coupling", bursts ? "bursts" : "smooth_swell",
                           std::string(kCoupledNeedsThetaRule), std::string(kCoupledNeedsThetaLimit)};
    }
    if (coupled && !gamma.coupling_phase_deg) {
      return recipe::Error{"/gamma_pac/coupling_phase_deg", "absent", std::string(kCoupledNeedsPhaseRule),
                           std::string(bursts ? kBurstsNeedsPhaseLimit : kCoupledNeedsPhaseLimit)};
    }
    if (!coupled && gamma.coupling_phase_deg) {
      return recipe::Error{"/gamma_pac/coupling_phase_deg", json::format_number(*gamma.coupling_phase_deg),
                           std::string(kPhaseNeedsCoupledRule), std::string(kPhaseNeedsCoupledLimit)};
    }
  }
  if (r.binaural && r.binaural->waveform == recipe::BinauralWaveform::Triangle) {
    return recipe::Error{"/binaural/waveform", "triangle", std::string(kNonSineBinauralRule),
                         std::string(kModeledBinauralWaveforms)};
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
