// Helpers for the Story 4.3 true-peak tests (docs/signal-spec.md, True
// peak). Test code only, independent of cli/: the calibration synthesis
// rule (True peak, Calibration, Signal) in binary64, a harness integer meter
// (True peak, Meter, in std::int64_t) and its must-fail variants, the
// 24-bit WAV bytes of the integers, and a reader of the 24-bit samples of a
// CLI WAV. The filter integers come from the generated spec_tables.hpp
// (kTruePeakFilter), never as literals.

#pragma once

#include "spec_tables.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <string>
#include <vector>

namespace arcani::test::true_peak {

namespace spec = arcani::test::spec;

inline constexpr double kPi = 3.141592653589793;  // the binary64 nearest pi
inline constexpr std::int32_t kMax24 = 8388607;    // 2^23 - 1
inline constexpr std::int32_t kMin24 = -8388608;   // -2^23
inline constexpr int kPhases = 4;
inline constexpr int kTaps = 12;

using Filter = std::array<std::array<std::int64_t, kTaps>, kPhases>;

// n_p[k] from the vectors.
inline Filter filter_integers() {
  Filter n{};
  for (const auto& v : spec::kTruePeakFilter) {
    n.at(static_cast<std::size_t>(v.phase)).at(static_cast<std::size_t>(v.tap)) = v.integer;
  }
  return n;
}

// Core, seconds-to-samples rule, harness copy: t * fs, nearest, ties to even.
inline std::uint64_t seconds_to_samples(double t, std::uint32_t fs) {
  return static_cast<std::uint64_t>(std::nearbyint(t * static_cast<double>(fs)));
}

// s * 2^23 to the nearest integer, ties to even, clamped (the spec's v[n]).
inline std::int32_t rounded_24(double s) {
  const double x = std::nearbyint(s * 8388608.0);
  if (x >= static_cast<double>(kMax24)) return kMax24;
  if (x <= static_cast<double>(kMin24)) return kMin24;
  return static_cast<std::int32_t>(x);
}

// The interleaved 24-bit integers (left, right per frame) of a signal vector:
// a stereo sine at fs / D, amplitude A, phase phi, with the 10 ms
// raised-cosine fades. fade_in / fade_out false: an abrupt start or end (a
// harness must-fail signal, never a vector).
inline std::vector<std::int32_t> synthesize(const spec::TruePeakSignalVector& v, bool fade_in = true,
                                            bool fade_out = true) {
  const std::uint64_t frames = seconds_to_samples(spec::kTruePeak_signal_s, v.fs);
  const std::uint64_t fade = seconds_to_samples(spec::kTruePeak_fade_s, v.fs);
  std::vector<std::int32_t> out;
  out.reserve(static_cast<std::size_t>(2 * frames));
  const double d = static_cast<double>(v.divisor);
  const double f = static_cast<double>(fade);
  for (std::uint64_t i = 0; i < frames; ++i) {
    const double n = static_cast<double>(i);
    double w = 1.0;
    if (i < fade && (fade_in || i >= frames / 2)) {
      w = (1.0 - std::cos(kPi * n / f)) / 2.0;
    } else if (i >= frames - fade && (fade_out || i < frames / 2)) {
      w = (1.0 - std::cos(kPi * (static_cast<double>(frames - 1) - n) / f)) / 2.0;
    }
    const double s = v.amplitude * w * std::sin(2.0 * kPi * n / d + v.phase_deg * kPi / 180.0);
    const std::int32_t x = rounded_24(s);
    out.push_back(x);
    out.push_back(x);
  }
  return out;
}

// 3 bytes per sample, little-endian two's complement, in order (the WAV data).
inline std::string data_bytes(const std::vector<std::int32_t>& interleaved) {
  std::string out;
  out.reserve(interleaved.size() * 3);
  for (const std::int32_t v : interleaved) {
    const std::uint32_t u = static_cast<std::uint32_t>(v) & 0xFFFFFFu;
    out.push_back(static_cast<char>(u & 0xFFu));
    out.push_back(static_cast<char>((u >> 8) & 0xFFu));
    out.push_back(static_cast<char>((u >> 16) & 0xFFu));
  }
  return out;
}

// max |sum n_p[k] v[m - k]| over m = 0 .. L + 10, every phase and channel of
// interleaved stereo integers. phase_mask limits the phases (bit p); drop_head
// / drop_tail drop that many outputs per phase at the start / end (must-fails).
inline std::int64_t harness_peak_integer(const std::vector<std::int32_t>& interleaved, unsigned phase_mask = 0xFu,
                                         std::uint64_t drop_head = 0, std::uint64_t drop_tail = 0) {
  const Filter n = filter_integers();
  const std::uint64_t frames = interleaved.size() / 2;
  const std::uint64_t outputs = frames == 0 ? 0 : frames + kTaps - 1;
  std::int64_t best = 0;
  for (std::size_t c = 0; c < 2; ++c) {
    for (int p = 0; p < kPhases; ++p) {
      if ((phase_mask & (1u << p)) == 0) {
        continue;
      }
      for (std::uint64_t m = drop_head; m + drop_tail < outputs; ++m) {
        std::int64_t sum = 0;
        for (int k = 0; k < kTaps; ++k) {
          if (m < static_cast<std::uint64_t>(k) || m - static_cast<std::uint64_t>(k) >= frames) {
            continue;
          }
          sum += n[static_cast<std::size_t>(p)][static_cast<std::size_t>(k)] *
                 static_cast<std::int64_t>(interleaved[static_cast<std::size_t>(2 * (m - k) + c)]);
        }
        best = std::max(best, sum < 0 ? -sum : sum);
      }
    }
  }
  return best;
}

inline double harness_true_peak(const std::vector<std::int32_t>& interleaved, unsigned phase_mask = 0xFu,
                                std::uint64_t drop_head = 0, std::uint64_t drop_tail = 0) {
  return static_cast<double>(harness_peak_integer(interleaved, phase_mask, drop_head, drop_tail)) /
         68719476736.0;  // 2^36, exact
}

inline double harness_dbtp(double linear) {
  return linear == 0.0 ? -std::numeric_limits<double>::infinity() : 20.0 * std::log10(linear);
}

// The 24-bit samples of the data bytes of a CLI WAV (after `header` bytes).
inline std::vector<std::int32_t> wav_samples(const std::vector<std::uint8_t>& bytes, std::size_t header) {
  std::vector<std::int32_t> out;
  if (bytes.size() < header) {
    return out;
  }
  out.reserve((bytes.size() - header) / 3);
  for (std::size_t i = header; i + 3 <= bytes.size(); i += 3) {
    std::int32_t v = static_cast<std::int32_t>(bytes[i]) | (static_cast<std::int32_t>(bytes[i + 1]) << 8) |
                     (static_cast<std::int32_t>(bytes[i + 2]) << 16);
    if (v >= (1 << 23)) {
      v -= (1 << 24);
    }
    out.push_back(v);
  }
  return out;
}

}  // namespace arcani::test::true_peak
