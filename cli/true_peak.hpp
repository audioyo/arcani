// The true-peak meter of arcani-render (Story 4.3; docs/signal-spec.md,
// True peak): ITU-R BS.1770-5 Annex 2, 4x oversampling with the 48
// coefficients Annex 2 prints, on the 24-bit integers the WAV holds. A
// measurement in the tooling, not an engine stage: nothing here changes a
// sample.
//
// Each printed coefficient is an integer n_p[k] times 2^-13 and each sample
// v stands for v / 2^23, so the meter sums n_p[k] * v in 64-bit integers
// (every sum is below 2^38 in magnitude) and divides the largest |sum| by
// 2^36 once: the linear true peak is exact, and equals the Python meter
// (tests/assertions/true_peak.py) bit for bit. Only true_peak_dbtp calls
// log10.

#ifndef ARCANI_CLI_TRUE_PEAK_HPP
#define ARCANI_CLI_TRUE_PEAK_HPP

#include <cstddef>
#include <cstdint>

namespace arcani::cli {

class TruePeakMeter {
 public:
  static constexpr std::size_t kPhases = 4;
  static constexpr std::size_t kTaps = 12;

  // One frame of 24-bit integers (left, right), from zero filter state.
  void add(std::int32_t left, std::int32_t right) noexcept;

  // TP, the linear true peak of every frame so far, including the 11
  // trailing outputs that zero inputs after the last frame give. It does
  // not change the meter, so it may be called at any time; 0 with no frames.
  double linear() const noexcept;

 private:
  // The last kTaps inputs per channel, newest at index (head_ - 1) mod kTaps.
  std::int64_t history_[2][kTaps] = {};
  std::size_t head_ = 0;
  std::int64_t peak_ = 0;  // the largest |sum| of every output so far
};

// 20 * log10(linear) in dBTP; -infinity when linear is 0.
double true_peak_dbtp(double linear);

}  // namespace arcani::cli

#endif  // ARCANI_CLI_TRUE_PEAK_HPP
