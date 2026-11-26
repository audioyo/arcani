// docs/signal-spec.md, True peak, Meter (Story 4.3).

#include "true_peak.hpp"

#include <cmath>
#include <limits>

namespace arcani::cli {

namespace {

// docs/signal-spec.md, True peak, Vectors: true-peak filter: the printed
// coefficients times 2^13, phase 0 to 3, taps in printed order.
constexpr std::int64_t kFilter[TruePeakMeter::kPhases][TruePeakMeter::kTaps] = {
    {14, 90, -161, 272, -487, 1125, 7964, -838, 390, -218, 122, -68},
    {-239, 240, -424, 730, -1364, 3810, 6388, -1641, 832, -477, 271, -155},
    {-155, 271, -477, 832, -1641, 6388, 3810, -1364, 730, -424, 240, -239},
    {-68, 122, -218, 390, -838, 7964, 1125, -487, 272, -161, 90, 14},
};

constexpr double kScale = 68719476736.0;  // 2^36 = 2^13 (taps) * 2^23 (samples)

// The largest |y[4m + p]| over the 4 phases for one output m, where
// h[k] is x[m - k] (the newest input first).
std::int64_t largest_output(const std::int64_t (&h)[TruePeakMeter::kTaps]) noexcept {
  std::int64_t best = 0;
  for (const auto& phase : kFilter) {
    std::int64_t s = 0;
    for (std::size_t k = 0; k < TruePeakMeter::kTaps; ++k) {
      s += phase[k] * h[k];
    }
    const std::int64_t a = s < 0 ? -s : s;
    if (a > best) {
      best = a;
    }
  }
  return best;
}

}  // namespace

void TruePeakMeter::add(std::int32_t left, std::int32_t right) noexcept {
  history_[0][head_] = left;
  history_[1][head_] = right;
  head_ = (head_ + 1) % kTaps;
  for (const auto& channel : history_) {
    std::int64_t h[kTaps];
    for (std::size_t k = 0; k < kTaps; ++k) {
      h[k] = channel[(head_ + kTaps - 1 - k) % kTaps];
    }
    const std::int64_t a = largest_output(h);
    if (a > peak_) {
      peak_ = a;
    }
  }
}

double TruePeakMeter::linear() const noexcept {
  std::int64_t peak = peak_;
  // The 11 trailing outputs: zero inputs pushed after the last frame, on a
  // copy, so the meter itself is unchanged. Zero history gives zero outputs,
  // so a meter with no frames reads 0.
  for (const auto& channel : history_) {
    std::int64_t h[kTaps];
    for (std::size_t k = 0; k < kTaps; ++k) {
      h[k] = channel[(head_ + kTaps - 1 - k) % kTaps];
    }
    for (std::size_t z = 1; z < kTaps; ++z) {
      for (std::size_t k = kTaps - 1; k > 0; --k) {
        h[k] = h[k - 1];
      }
      h[0] = 0;
      const std::int64_t a = largest_output(h);
      if (a > peak) {
        peak = a;
      }
    }
  }
  return static_cast<double>(peak) / kScale;  // peak < 2^53: exact, one rounding-free division
}

double true_peak_dbtp(double linear) {
  if (linear == 0.0) {
    return -std::numeric_limits<double>::infinity();
  }
  return 20.0 * std::log10(linear);
}

}  // namespace arcani::cli
