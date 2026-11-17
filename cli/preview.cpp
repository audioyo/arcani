// The listening preview helpers (Story 3.3). See preview.hpp and
// docs/signal-spec.md, Preview.

#include "preview.hpp"

#include <charconv>
#include <cmath>
#include <cstring>
#include <system_error>

namespace arcani::cli {

namespace {

// Preview, Gain: the peak level row lies in [-440, 0] dB. Above 0 dB the
// summed layers would clip at 24-bit rounding; 10^22 (P = -440) is the
// largest power of ten binary64 holds exactly.
constexpr double kPeakMinDbfs = -440.0;
constexpr double kPeakMaxDbfs = 0.0;
constexpr const char* kPeakRow = "preview-peak-level";

constexpr double kTwoTo53 = 9007199254740992.0;          // 2^53
constexpr double kTwoTo64 = 18446744073709551616.0;      // 2^64

std::string shortest(double x) {
  char buf[64];
  const auto r = std::to_chars(buf, buf + sizeof buf, x);
  if (r.ec != std::errc()) {
    return "?";  // not reached: 64 bytes hold any binary64
  }
  return std::string(buf, r.ptr);
}

[[noreturn]] void throw_peak(const std::string& text) {
  throw arcani::test::tables::TableError(std::string("row ") + kPeakRow + ": value " + text +
                                         " is not a whole multiple of 10 dB from -440 to 0 dB "
                                         "(docs/signal-spec.md, Preview, Gain)");
}

}  // namespace

std::uint64_t seconds_to_samples(double t_s, std::uint32_t fs) noexcept {
  if (!(t_s >= 0.0) || std::isinf(t_s)) {
    return 0;
  }
  const double x = t_s * static_cast<double>(fs);
  if (!(x < kTwoTo64)) {
    return 0;
  }
  if (x >= kTwoTo53) {
    return static_cast<std::uint64_t>(x);  // every binary64 here is an integer
  }
  // Below 2^53 the truncation and the fraction are exact.
  std::uint64_t n = static_cast<std::uint64_t>(x);
  const double frac = x - static_cast<double>(n);
  if (frac > 0.5 || (frac == 0.5 && (n & 1u) != 0)) {
    ++n;
  }
  return n;
}

bool preview_peak_valid(double peak_dbfs) noexcept {
  if (!(peak_dbfs >= kPeakMinDbfs && peak_dbfs <= kPeakMaxDbfs)) {
    return false;  // NaN too
  }
  const double m = peak_dbfs / 10.0;
  const double k = -m;  // 0 to 44
  const bool integer = static_cast<double>(static_cast<std::uint64_t>(k)) == k;
  return integer && m * 10.0 == peak_dbfs;
}

double preview_amplitude(double peak_dbfs) {
  if (!preview_peak_valid(peak_dbfs)) {
    throw_peak(shortest(peak_dbfs));
  }
  const std::uint64_t k = static_cast<std::uint64_t>(-(peak_dbfs / 10.0));
  double x = 1.0;
  for (std::uint64_t i = 0; i < k / 2; ++i) {
    x = x * 10.0;  // exact: 10^j for j <= 22
  }
  if (k % 2 != 0) {
    x = x * std::sqrt(10.0);  // one correctly rounded square root, then one rounding
  }
  return 1.0 / x;
}

double preview_gain(double peak_dbfs, std::uint32_t layers_max) {
  const double a = preview_amplitude(peak_dbfs);
  return a / static_cast<double>(layers_max == 0 ? 1u : layers_max);
}

PreviewRows preview_rows(const arcani::test::tables::Row& length, const arcani::test::tables::Row& seam_tail,
                         const arcani::test::tables::Row& peak) {
  PreviewRows rows;
  rows.length_s = length.value();
  rows.seam_tail_s = seam_tail.value();
  rows.peak_dbfs = peak.value();
  if (!preview_peak_valid(rows.peak_dbfs)) {
    throw_peak(peak.value_text.empty() ? shortest(rows.peak_dbfs) : peak.value_text);
  }
  return rows;
}

std::uint32_t PreviewLayers::max() const noexcept { return left > right ? left : right; }

bool preview_layers(const arc_plan* plan, PreviewLayers& out, std::string& rule) {
  out = PreviewLayers{};
  bool seen[2][3] = {{false, false, false}, {false, false, false}};
  const std::size_t count = arc_plan_component_count(plan);
  for (std::size_t i = 0; i < count; ++i) {
    arc_component c;
    arc_error e;
    std::memset(&c, 0, sizeof c);
    std::memset(&e, 0, sizeof e);
    if (arc_plan_component(plan, i, &c, &e) != ARC_OK) {
      rule = e.rule;
      return false;
    }
    const int layer = static_cast<int>(c.layer);
    const int ear = static_cast<int>(c.ear);
    if (layer < 0 || layer > 2 || ear < 0 || ear > 1) {
      rule = "component layer or ear out of range";
      return false;
    }
    seen[ear][layer] = true;
  }
  for (int layer = 0; layer < 3; ++layer) {
    out.left += seen[ARC_EAR_LEFT][layer] ? 1u : 0u;
    out.right += seen[ARC_EAR_RIGHT][layer] ? 1u : 0u;
  }
  return true;
}

std::uint64_t preview_frames(const arc_loop_frames& loop, std::uint64_t end_frame, std::uint64_t length_frames,
                             std::uint64_t tail_frames) noexcept {
  const std::uint64_t want =
      loop.looping == 0 ? length_frames : loop.opening_end_frame + loop.body_frames + tail_frames;
  return want < end_frame ? want : end_frame;
}

void apply_gain(std::span<double> interleaved, double g) noexcept {
  for (double& s : interleaved) {
    s = s * g;
  }
}

}  // namespace arcani::cli
