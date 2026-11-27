// The loudness meter of arcani-render (Story 4.1; docs/signal-spec.md,
// Loudness): ITU-R BS.1770-5 integrated loudness of the binary64 render
// output, and the measurement window. A measurement in the tooling, not an
// engine stage: nothing here changes a sample.
//
// K-weighting is a high shelf, then a high-pass, per channel, each the
// bilinear transform of the analog prototype the spec derives from the
// BS.1770 48 kHz coefficients. Each channel runs the difference equation
// from zero state. The meter is streaming: add() takes any number of frames
// per call and keeps only the summed K-weighted energy of each 100 ms step,
// so the same samples split into different calls give the same bits. It is
// not bit exact across platforms (the filter design calls std::tan); the
// Python meter (tests/assertions/loudness.py) is the independent second meter.

#ifndef ARCANI_CLI_LOUDNESS_HPP
#define ARCANI_CLI_LOUDNESS_HPP

#include <arcani/arcani.h>

#include "tables.hpp"

#include <cstdint>
#include <span>
#include <string>
#include <vector>

namespace arcani::cli {

struct Biquad {
  double b0 = 0.0;
  double b1 = 0.0;
  double b2 = 0.0;
  double a1 = 0.0;
  double a2 = 0.0;
};

struct KWeighting {
  Biquad shelf;     // stage 1
  Biquad highpass;  // stage 2
};

// Loudness, K-weighting: the coefficients at fs by the spec's binary64
// formulas. Throws std::invalid_argument unless fs is a positive multiple of
// 10 (so a 400 ms block and a 100 ms step are whole frames).
KWeighting k_weighting(std::uint32_t fs);

class LoudnessMeter {
 public:
  // Throws as k_weighting.
  explicit LoudnessMeter(std::uint32_t fs);

  // Interleaved stereo (left, right per frame), any number of frames. An odd
  // size throws std::invalid_argument and adds nothing.
  void add(std::span<const double> interleaved_stereo);

  std::uint64_t frames() const noexcept { return frames_; }

  // J, the number of whole 400 ms blocks so far.
  std::uint64_t block_count() const noexcept;

  // Loudness, Integrated loudness: L in LUFS-I, -infinity when no block
  // passes the gates (or no block exists). gating = false takes every block:
  // the must-fail meter.
  double integrated(bool gating = true) const;

 private:
  struct State {
    double x1 = 0.0, x2 = 0.0, y1 = 0.0, y2 = 0.0;
  };
  KWeighting k_;
  std::uint64_t block_frames_ = 0;
  std::uint64_t step_frames_ = 0;
  State shelf_[2];
  State highpass_[2];
  std::uint64_t frames_ = 0;
  std::uint64_t in_step_ = 0;  // frames of the current step so far
  double step_energy_ = 0.0;   // their summed y^2, both channels
  std::vector<double> steps_;  // summed y^2 of every whole step
};

// One gain ramp [start, end) in frames (Story 4.4; arc_plan_gain_ramp).
struct FrameSpan {
  std::uint64_t start = 0;
  std::uint64_t end = 0;
};

// Loudness, Window. Without a loop: the steady stretches are the maximal
// runs of [0, end_frame) inside no ramp (spans may overlap and come in any
// order); the window is the longest, the earliest on a tie, measured once,
// accepted when it is at least min_frames (without ramps, [0, end_frame)).
// With a loop: always accepted, frames [O, O + B) repeated
// k = max(1, ceil(min_frames / B)) times (loop rule 8 keeps the body
// ramp-free, so the ramps are not read). A rejected window has every number
// 0 but steady_frames, the length of the longest steady stretch (Story 4.4),
// which is set without a loop whether accepted or not, and 0 with one.
// Without a loop, more than 32 spans (4 schedules of 8 ramps) is refused
// with every number 0.
struct LoudnessWindow {
  bool accepted = false;
  std::uint64_t start_frame = 0;
  std::uint64_t body_frames = 0;
  std::uint64_t repeats = 0;
  std::uint64_t window_frames = 0;
  std::uint64_t steady_frames = 0;
};

LoudnessWindow loudness_window(const arc_loop_frames& loop, std::uint64_t end_frame, std::uint64_t min_frames,
                               std::span<const FrameSpan> ramps) noexcept;

// The same without ramps.
LoudnessWindow loudness_window(const arc_loop_frames& loop, std::uint64_t end_frame,
                               std::uint64_t min_frames) noexcept;

// Every ramp of the plan's schedules (arc_plan_gain_ramp). False, with the
// failing rule, when the C API refuses.
bool gain_ramp_spans(const arc_plan* plan, std::vector<FrameSpan>& out, std::string& rule);

// W_min = seconds_to_samples(row value, fs). Throws tables::TableError,
// naming the row, unless its unit is "s" and its value is finite and above 0.
std::uint64_t loudness_window_min_frames(const arcani::test::tables::Row& row, std::uint32_t fs);

// The rejection limit: ">= <row value text> s (row <id>)".
std::string loudness_window_limit(const arcani::test::tables::Row& row);

}  // namespace arcani::cli

#endif  // ARCANI_CLI_LOUDNESS_HPP
