// The loudness meter (Story 4.1). See loudness.hpp and docs/signal-spec.md,
// Loudness.

#include "loudness.hpp"

#include "preview.hpp"

#include <cmath>
#include <limits>
#include <numbers>
#include <stdexcept>

namespace arcani::cli {

namespace {

// BS.1770-5, Annex 1.
constexpr double kOffsetDb = -0.691;
constexpr double kAbsoluteGateLufs = -70.0;
constexpr double kRelativeGateLu = -10.0;
constexpr std::uint64_t kStepsPerBlock = 4;  // 400 ms blocks, 75 percent overlap

// docs/signal-spec.md, Loudness, Vectors: K-weighting prototype (binary64).
constexpr double kShelfF0 = 0x1.a47e5d678a647p+10;
constexpr double kShelfQ = 0x1.6a12df668776cp-1;
constexpr double kShelfVh = 0x1.95b9b16bf11c5p+0;
constexpr double kShelfVb = 0x1.423b88ee23b99p+0;
constexpr double kHighpassF0 = 0x1.311571c130af0p+5;
constexpr double kHighpassQ = 0x1.002add8d38a3cp-1;
constexpr double kHighpassG = 0x1.0147587ea05d0p+0;

void check_fs(std::uint32_t fs) {
  if (fs == 0 || fs % 10 != 0) {
    throw std::invalid_argument("loudness meter: sample rate " + std::to_string(fs) +
                                " is not a positive multiple of 10 Hz");
  }
}

double lufs(double z) {
  return z > 0.0 ? kOffsetDb + 10.0 * std::log10(z) : -std::numeric_limits<double>::infinity();
}

}  // namespace

KWeighting k_weighting(std::uint32_t fs) {
  check_fs(fs);
  const double rate = static_cast<double>(fs);
  KWeighting w;
  {
    const double k = std::tan(std::numbers::pi * kShelfF0 / rate);
    const double kq = k / kShelfQ;
    const double d = 1.0 + kq + k * k;
    w.shelf.a1 = 2.0 * (k * k - 1.0) / d;
    w.shelf.a2 = (1.0 - kq + k * k) / d;
    w.shelf.b0 = (kShelfVh + kShelfVb * kq + k * k) / d;
    w.shelf.b1 = 2.0 * (k * k - kShelfVh) / d;
    w.shelf.b2 = (kShelfVh - kShelfVb * kq + k * k) / d;
  }
  {
    const double k = std::tan(std::numbers::pi * kHighpassF0 / rate);
    const double kq = k / kHighpassQ;
    const double d = 1.0 + kq + k * k;
    w.highpass.a1 = 2.0 * (k * k - 1.0) / d;
    w.highpass.a2 = (1.0 - kq + k * k) / d;
    w.highpass.b0 = kHighpassG / d;
    w.highpass.b1 = -2.0 * kHighpassG / d;
    w.highpass.b2 = kHighpassG / d;
  }
  return w;
}

LoudnessMeter::LoudnessMeter(std::uint32_t fs) : k_(k_weighting(fs)) {
  block_frames_ = static_cast<std::uint64_t>(fs) * 4 / 10;
  step_frames_ = block_frames_ / kStepsPerBlock;
}

void LoudnessMeter::add(std::span<const double> interleaved_stereo) {
  if (interleaved_stereo.size() % 2 != 0) {
    throw std::invalid_argument("loudness meter: interleaved stereo needs an even number of samples");
  }
  const std::size_t n = interleaved_stereo.size() / 2;
  for (std::size_t i = 0; i < n; ++i) {
    double energy = 0.0;
    for (int c = 0; c < 2; ++c) {
      const double x = interleaved_stereo[2 * i + static_cast<std::size_t>(c)];
      State& s = shelf_[c];
      const Biquad& a = k_.shelf;
      const double y = a.b0 * x + a.b1 * s.x1 + a.b2 * s.x2 - a.a1 * s.y1 - a.a2 * s.y2;
      s.x2 = s.x1;
      s.x1 = x;
      s.y2 = s.y1;
      s.y1 = y;
      State& t = highpass_[c];
      const Biquad& b = k_.highpass;
      const double v = b.b0 * y + b.b1 * t.x1 + b.b2 * t.x2 - b.a1 * t.y1 - b.a2 * t.y2;
      t.x2 = t.x1;
      t.x1 = y;
      t.y2 = t.y1;
      t.y1 = v;
      energy += v * v;
    }
    step_energy_ += energy;
    if (++in_step_ == step_frames_) {
      steps_.push_back(step_energy_);
      step_energy_ = 0.0;
      in_step_ = 0;
    }
  }
  frames_ += n;
}

std::uint64_t LoudnessMeter::block_count() const noexcept {
  const std::uint64_t steps = steps_.size();
  return steps < kStepsPerBlock ? 0 : steps - (kStepsPerBlock - 1);
}

double LoudnessMeter::integrated(bool gating) const {
  const std::uint64_t blocks = block_count();
  if (blocks == 0) {
    return -std::numeric_limits<double>::infinity();
  }
  const double b = static_cast<double>(block_frames_);
  std::vector<double> z(static_cast<std::size_t>(blocks));
  for (std::size_t j = 0; j < z.size(); ++j) {
    z[j] = (steps_[j] + steps_[j + 1] + steps_[j + 2] + steps_[j + 3]) / b;
  }
  if (!gating) {
    double sum = 0.0;
    for (const double v : z) {
      sum += v;
    }
    return lufs(sum / static_cast<double>(z.size()));
  }
  double sum = 0.0;
  std::uint64_t count = 0;
  for (const double v : z) {
    if (lufs(v) > kAbsoluteGateLufs) {
      sum += v;
      ++count;
    }
  }
  if (count == 0) {
    return -std::numeric_limits<double>::infinity();
  }
  const double gate = lufs(sum / static_cast<double>(count)) + kRelativeGateLu;
  sum = 0.0;
  count = 0;
  for (const double v : z) {
    const double l = lufs(v);
    if (l > kAbsoluteGateLufs && l > gate) {
      sum += v;
      ++count;
    }
  }
  if (count == 0) {
    return -std::numeric_limits<double>::infinity();
  }
  return lufs(sum / static_cast<double>(count));
}

LoudnessWindow loudness_window(const arc_loop_frames& loop, std::uint64_t end_frame,
                               std::uint64_t min_frames) noexcept {
  LoudnessWindow w;
  if (loop.looping == 0) {
    if (end_frame < min_frames) {
      return w;
    }
    w.accepted = true;
    w.start_frame = 0;
    w.body_frames = end_frame;
    w.repeats = 1;
    w.window_frames = end_frame;
    return w;
  }
  if (loop.body_frames == 0) {
    return w;  // not reached: the loop rules keep B >= 1
  }
  std::uint64_t k = min_frames / loop.body_frames;
  if (k * loop.body_frames < min_frames) {
    ++k;
  }
  if (k == 0) {
    k = 1;
  }
  w.accepted = true;
  w.start_frame = loop.opening_end_frame;
  w.body_frames = loop.body_frames;
  w.repeats = k;
  w.window_frames = k * loop.body_frames;
  return w;
}

std::uint64_t loudness_window_min_frames(const arcani::test::tables::Row& row, std::uint32_t fs) {
  const double s = row.value();
  if (row.unit != "s" || !std::isfinite(s) || !(s > 0.0)) {
    throw arcani::test::tables::TableError("row " + row.id + ": value " + row.value_text + " " + row.unit +
                                           " is not a positive number of seconds (docs/signal-spec.md, "
                                           "Loudness, Window)");
  }
  return seconds_to_samples(s, fs);
}

std::string loudness_window_limit(const arcani::test::tables::Row& row) {
  return ">= " + row.value_text + " s (row " + row.id + ")";
}

}  // namespace arcani::cli
