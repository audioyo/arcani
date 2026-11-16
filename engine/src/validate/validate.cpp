// Recipe validator: locked ranges and the carrier rule.

#include "validate/validate.hpp"

#include <cstddef>
#include <cstdint>
#include <iterator>
#include <optional>
#include <string>
#include <utility>

#include "json/number.hpp"
#include "recipe/field_table.hpp"

namespace arcani::validate {

// The integer test of a binary64 x >= 0 (docs/signal-spec.md, Loop,
// Whole-sample rule): every binary64 at or above 2^53 (or infinite) counts
// as whole, and below 2^53 x converts to an unsigned 64-bit integer and back
// exactly when it is one.
bool is_whole(double x) noexcept {
  if (!(x < 0x1p53)) {
    return true;
  }
  const auto u = static_cast<std::uint64_t>(x);  // 0 <= x < 2^53: in range
  return static_cast<double>(u) == x;
}

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
    {"max-run-time-focus", 45.0, 45.0, false, "min"},
    {"max-run-time-learn", 20.0, 20.0, false, "min"},
};

constexpr std::string_view kRightCarrierRow = "binaural-carrier-right";
constexpr std::string_view kBeatRateRow = "beat-rate";
constexpr std::string_view kBeatRatePath = "/binaural/beat_rate_hz";
constexpr std::string_view kSwingPath = "/binaural/beat_rate_cycle/swing_hz";
constexpr std::string_view kThetaSwingPath = "/theta_reference/rate_cycle/swing_hz";
constexpr std::string_view kGammaSwingPath = "/gamma_pac/rate_cycle/swing_hz";
constexpr std::string_view kThetaRateRow = "theta-rate";
constexpr std::string_view kGammaRateRow = "gamma-rate";
constexpr std::string_view kFocusCapRow = "max-run-time-focus";
constexpr std::string_view kLearnCapRow = "max-run-time-learn";

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
static_assert(row_index(kThetaRateRow) < std::size(kRows));
static_assert(row_index(kGammaRateRow) < std::size(kRows));
static_assert(row_index(kFocusCapRow) < std::size(kRows));
static_assert(row_index(kLearnCapRow) < std::size(kRows));

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
  if (path == "/theta_reference/rate_cycle/period_s") {
    if (r.theta_reference && r.theta_reference->rate_cycle) {
      return {true, r.theta_reference->rate_cycle->period_s};
    }
    return {true, std::nullopt};
  }
  if (path == "/theta_reference/rate_cycle/start_phase_deg") {
    if (r.theta_reference && r.theta_reference->rate_cycle) {
      return {true, r.theta_reference->rate_cycle->start_phase_deg};
    }
    return {true, std::nullopt};
  }
  if (path == "/gamma_pac/rate_cycle/period_s") {
    if (r.gamma_pac && r.gamma_pac->rate_cycle) {
      return {true, r.gamma_pac->rate_cycle->period_s};
    }
    return {true, std::nullopt};
  }
  if (path == "/gamma_pac/rate_cycle/start_phase_deg") {
    if (r.gamma_pac && r.gamma_pac->rate_cycle) {
      return {true, r.gamma_pac->rate_cycle->start_phase_deg};
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

// Worst case of a rate cycle about the center rate_hz (docs/signal-spec.md,
// Rate curve, Range checks), in order: the swing itself, then the lowest and
// highest rate against the layer's rate row, each reported on the swing's
// path. Each sum is the one binary64 rounding the spec names.
std::optional<recipe::Error> check_rate_worst_case(std::string_view swing_path, std::string_view rate_row,
                                                   double rate_hz, const recipe::RateCycle& cycle) {
  const double swing = cycle.swing_hz;
  if (!(swing >= 0.0)) {
    return recipe::Error{std::string(swing_path), json::format_number(swing), "range.min", ">= 0 Hz"};
  }
  const std::size_t i = row_index(rate_row);
  const double lowest = rate_hz - swing;
  if (auto e = check_row(swing_path, lowest, i, 1.0, kRows[i].unit)) {
    return e;
  }
  const double highest = rate_hz + swing;
  return check_row(swing_path, highest, i, 1.0, kRows[i].unit);
}

// Worst case of a beat rate cycle: the rate worst case against beat-rate,
// then the highest right carrier against binaural-carrier-right.
std::optional<recipe::Error> check_cycle_worst_case(const recipe::Binaural& b) {
  const recipe::RateCycle& cycle = *b.beat_rate_cycle;
  if (auto e = check_rate_worst_case(kSwingPath, kBeatRateRow, b.beat_rate_hz, cycle)) {
    return e;
  }
  const double swing = cycle.swing_hz;
  const double center = b.carrier_left_hz + b.beat_rate_hz;  // f_C, as compile sums it
  const double right = center + swing;
  const std::size_t j = row_index(kRightCarrierRow);
  return check_row(kSwingPath, right, j, 1.0, kRows[j].unit);
}

// Loop, Whole-sample rule: 4 * t_s (an exact power-of-two scale) is an
// integer, so t_s * 44100 and t_s * 48000 are both integers.
bool whole_samples(double t_s) noexcept { return is_whole(t_s * 4.0); }

// Loop, Cycle rule: body_s / period_s (one rounding) is an integer, and that
// integer times period_s (one rounding) gives body_s back.
bool whole_cycles(double body_s, double period_s) noexcept {
  const double q = body_s / period_s;
  return is_whole(q) && q * period_s == body_s;
}

}  // namespace

std::span<const RangeRow> range_rows() noexcept { return kRows; }

std::optional<recipe::Error> check_loop(const recipe::Recipe& r) {
  if (!r.loop) {
    return std::nullopt;
  }
  const recipe::Loop& loop = *r.loop;
  // 1. The cap against the mode's row.
  const std::size_t i = row_index(loop.mode == recipe::LoopMode::Focus ? kFocusCapRow : kLearnCapRow);
  if (auto e = check_row("/loop/max_run_time_min", loop.max_run_time_min, i, 1.0, kRows[i].unit)) {
    return e;
  }
  // 2. The session ends at the cap.
  const double end = loop.max_run_time_min * 60.0;
  if (!(r.length_s == end)) {
    return recipe::Error{"/length_s", json::format_number(r.length_s), std::string(kLoopLengthRule),
                         "= " + json::format_number(end) + " s (" + json::format_number(loop.max_run_time_min) +
                             " min x 60)"};
  }
  // 3. and 4. The opening may be empty; the body may not.
  if (!(loop.opening_s >= 0.0)) {
    return recipe::Error{"/loop/opening_s", json::format_number(loop.opening_s), "range.min", ">= 0 s"};
  }
  if (!(loop.body_s > 0.0)) {
    return recipe::Error{"/loop/body_s", json::format_number(loop.body_s), "range.min", "> 0 s"};
  }
  // 5. Whole samples at both native rates, the opening then the body.
  if (!whole_samples(loop.opening_s)) {
    return recipe::Error{"/loop/opening_s", json::format_number(loop.opening_s),
                         std::string(kLoopWholeSamplesRule), std::string(kLoopWholeSamplesLimit)};
  }
  if (!whole_samples(loop.body_s)) {
    return recipe::Error{"/loop/body_s", json::format_number(loop.body_s), std::string(kLoopWholeSamplesRule),
                         std::string(kLoopWholeSamplesLimit)};
  }
  // 6. A body of whole rate cycles, every cycle in field order.
  struct CycleRef {
    std::string_view path;
    const recipe::RateCycle* cycle;
  };
  const CycleRef cycles[] = {
      {"/theta_reference/rate_cycle/period_s",
       r.theta_reference && r.theta_reference->rate_cycle ? &*r.theta_reference->rate_cycle : nullptr},
      {"/gamma_pac/rate_cycle/period_s", r.gamma_pac && r.gamma_pac->rate_cycle ? &*r.gamma_pac->rate_cycle : nullptr},
      {"/binaural/beat_rate_cycle/period_s",
       r.binaural && r.binaural->beat_rate_cycle ? &*r.binaural->beat_rate_cycle : nullptr},
  };
  for (const CycleRef& c : cycles) {
    if (c.cycle != nullptr && !whole_cycles(loop.body_s, c.cycle->period_s)) {
      return recipe::Error{"/loop/body_s", json::format_number(loop.body_s), std::string(kLoopWholeCyclesRule),
                           "a whole multiple of " + json::format_number(c.cycle->period_s) + " s (" +
                               std::string(c.path) + ")"};
    }
  }
  // 7. At least one whole body pass fits in the session.
  const double total = loop.opening_s + loop.body_s;
  if (!(total <= r.length_s)) {
    return recipe::Error{"/loop/body_s", json::format_number(total), std::string(kLoopExceedsRule),
                         "<= " + json::format_number(r.length_s) + " s (length_s)"};
  }
  return std::nullopt;
}

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
    if (f.path == kThetaSwingPath) {
      // Story 2.6: the theta rate cycle worst case, after the theta fields.
      if (r.theta_reference && r.theta_reference->rate_cycle) {
        if (auto e = check_rate_worst_case(kThetaSwingPath, kThetaRateRow, r.theta_reference->rate_hz,
                                           *r.theta_reference->rate_cycle)) {
          return e;
        }
      }
      continue;
    }
    if (f.path == kGammaSwingPath) {
      // Story 2.6: the gamma rate cycle worst case, after the gamma fields.
      if (r.gamma_pac && r.gamma_pac->rate_cycle) {
        if (auto e = check_rate_worst_case(kGammaSwingPath, kGammaRateRow, r.gamma_pac->rate_hz,
                                           *r.gamma_pac->rate_cycle)) {
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
  // Story 2.7: the loop rules, after every range check above.
  return check_loop(r);
}

std::optional<recipe::Error> check_rules(const recipe::Recipe& r) {
  if (r.theta_reference) {
    const recipe::ThetaReference& theta = *r.theta_reference;
    // A fixed rate is the one value; a rate cycle spans r - s to r + s.
    const double swing = theta.rate_cycle ? theta.rate_cycle->swing_hz : 0.0;
    const double lo = theta.rate_cycle ? theta.rate_hz - swing : theta.rate_hz;
    const double hi = theta.rate_cycle ? theta.rate_hz + swing : theta.rate_hz;
    if (auto e = check_carrier_rule("/theta_reference/carrier_hz", theta.carrier_hz, lo, hi)) {
      return e;
    }
    if (theta.shape == recipe::ThetaShape::Custom) {
      return recipe::Error{"/theta_reference/shape", "custom", std::string(kShapeNotModeledRule),
                           std::string(kModeledThetaShapes)};
    }
  }
  if (r.gamma_pac) {
    const recipe::GammaPac& gamma = *r.gamma_pac;
    // A fixed rate is the one value; a rate cycle spans r - s to r + s.
    const double swing = gamma.rate_cycle ? gamma.rate_cycle->swing_hz : 0.0;
    const double lo = gamma.rate_cycle ? gamma.rate_hz - swing : gamma.rate_hz;
    const double hi = gamma.rate_cycle ? gamma.rate_hz + swing : gamma.rate_hz;
    if (auto e = check_carrier_rule("/gamma_pac/carrier_hz", gamma.carrier_hz, lo, hi)) {
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
