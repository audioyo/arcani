// The listening preview of arcani-render (Story 3.3; docs/signal-spec.md,
// Preview): the preview frame count, the layer count per ear, and the
// preview gain g = 10^(P / 20) / max(n_max, 1). The engine is not touched:
// the renderer keeps the first F frames of the recipe's own render and
// multiplies each output sample by g before 24-bit rounding.
//
// Every function is pure apart from preview_layers (C API reads). g is built
// from exact powers of ten and one correctly rounded square root, so it has
// the same bits on every platform; nothing here makes a transcendental call.

#ifndef ARCANI_CLI_PREVIEW_HPP
#define ARCANI_CLI_PREVIEW_HPP

#include <arcani/arcani.h>

#include "tables.hpp"

#include <cstdint>
#include <span>
#include <string>

namespace arcani::cli {

// Core, seconds-to-samples rule: x = t_s * fs (one rounding), then the
// nearest integer, ties to even; 0 for a negative, NaN, or infinite t_s and
// for x >= 2^64.
std::uint64_t seconds_to_samples(double t_s, std::uint32_t fs) noexcept;

// Preview, Gain: -440 <= P <= 0, m = P / 10.0 an integer, and m * 10.0 == P.
bool preview_peak_valid(double peak_dbfs) noexcept;

// 10^(P / 20) by the Preview, Gain steps. Throws tables::TableError naming
// row preview-peak-level and the value when !preview_peak_valid(peak_dbfs).
double preview_amplitude(double peak_dbfs);

// g = preview_amplitude(P) / double(max(layers_max, 1)). Throws as above.
double preview_gain(double peak_dbfs, std::uint32_t layers_max);

struct PreviewRows {
  double length_s = 0.0;     // row preview-length
  double seam_tail_s = 0.0;  // row preview-seam-tail
  double peak_dbfs = 0.0;    // row preview-peak-level
};

// The three values from the given rows (Row::value()). Throws
// tables::TableError, naming the peak row's id and its text, when the peak
// level is not valid. arcani-render passes row(id) for each.
PreviewRows preview_rows(const arcani::test::tables::Row& length, const arcani::test::tables::Row& seam_tail,
                         const arcani::test::tables::Row& peak);

// The layers present in each ear (Preview, Layers).
struct PreviewLayers {
  std::uint32_t left = 0;
  std::uint32_t right = 0;
  std::uint32_t max() const noexcept;  // the larger
};

// Per ear the distinct layers among that ear's rows of arc_plan_component
// (a muted ear has no binaural row). Returns false, with `rule` set to the
// failing call's rule, when an engine call fails.
bool preview_layers(const arc_plan* plan, PreviewLayers& out, std::string& rule);

// Preview, Frames: without a loop min(length_frames, end_frame); with one
// min(opening_end_frame + body_frames + tail_frames, end_frame).
std::uint64_t preview_frames(const arc_loop_frames& loop, std::uint64_t end_frame, std::uint64_t length_frames,
                             std::uint64_t tail_frames) noexcept;

// Each sample s becomes s * g (one binary64 multiplication), in place.
void apply_gain(std::span<double> interleaved, double g) noexcept;

}  // namespace arcani::cli

#endif  // ARCANI_CLI_PREVIEW_HPP
