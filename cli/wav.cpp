// 24-bit rounding and the WAV header (Story 1.4). See wav.hpp.

#include "wav.hpp"

#include <cmath>

namespace arcani::cli {

namespace {

constexpr std::int32_t kMax = 8388607;
constexpr std::int32_t kMin = -8388608;
constexpr std::uint16_t kChannels = 2;
constexpr std::uint16_t kBits = 24;
constexpr std::uint16_t kBlockAlign = kChannels * (kBits / 8);
constexpr std::uint64_t kRiffLimit = 0xFFFFFFFFull;

// Nearest integer to x, ties to even, for 0 <= x < 2^23. The truncating
// cast and the subtraction are exact in this range, whatever the rounding
// mode (same pattern as engine/src/core/phase.cpp, not shared with it).
std::int32_t round_half_even(double x) noexcept {
  const std::int32_t whole = static_cast<std::int32_t>(x);
  const double fraction = x - static_cast<double>(whole);
  if (fraction > 0.5) {
    return whole + 1;
  }
  if (fraction < 0.5) {
    return whole;
  }
  return whole + (whole & 1);
}

void put_tag(std::vector<std::uint8_t>& out, const char (&tag)[5]) {
  out.insert(out.end(), tag, tag + 4);
}

void put_le(std::vector<std::uint8_t>& out, std::uint64_t v, int bytes) {
  for (int i = 0; i < bytes; ++i) {
    out.push_back(static_cast<std::uint8_t>((v >> (8 * i)) & 0xFFu));
  }
}

void put_fmt(std::vector<std::uint8_t>& out, std::uint32_t rate) {
  put_tag(out, "fmt ");
  put_le(out, 16, 4);
  put_le(out, 1, 2);  // WAVE_FORMAT_PCM
  put_le(out, kChannels, 2);
  put_le(out, rate, 4);
  put_le(out, static_cast<std::uint64_t>(rate) * kBlockAlign, 4);
  put_le(out, kBlockAlign, 2);
  put_le(out, kBits, 2);
}

}  // namespace

std::int32_t quantize_24(double s) noexcept {
  if (std::isnan(s)) {
    return 0;
  }
  const double x = s * 0x1p23;  // exact: a power-of-two scale
  if (x >= 8388607.0) {
    return kMax;
  }
  if (x <= -8388608.0) {
    return kMin;
  }
  // Here -2^23 < x < 2^23 - 1. Ties to even is symmetric about zero.
  return x < 0.0 ? -round_half_even(-x) : round_half_even(x);
}

void append_samples(std::vector<std::uint8_t>& out, std::span<const double> interleaved) {
  out.reserve(out.size() + interleaved.size() * 3);
  for (double s : interleaved) {
    const std::uint32_t v = static_cast<std::uint32_t>(quantize_24(s));
    out.push_back(static_cast<std::uint8_t>(v & 0xFFu));
    out.push_back(static_cast<std::uint8_t>((v >> 8) & 0xFFu));
    out.push_back(static_cast<std::uint8_t>((v >> 16) & 0xFFu));
  }
}

std::vector<std::uint8_t> wav_header(std::uint64_t frames, std::uint32_t rate) {
  const std::uint64_t data = frames * kBlockAlign;
  std::vector<std::uint8_t> h;
  // 715827876 frames is the largest count with 36 + data <= 0xFFFFFFFF.
  if (frames <= (kRiffLimit - 36) / kBlockAlign) {
    put_tag(h, "RIFF");
    put_le(h, 36 + data, 4);
    put_tag(h, "WAVE");
    put_fmt(h, rate);
    put_tag(h, "data");
    put_le(h, data, 4);
    return h;
  }
  // EBU Tech 3306: RF64 with a ds64 chunk, 32-bit sizes 0xFFFFFFFF.
  put_tag(h, "RF64");
  put_le(h, kRiffLimit, 4);
  put_tag(h, "WAVE");
  put_tag(h, "ds64");
  put_le(h, 28, 4);
  put_le(h, 72 + data, 8);  // riffSize: 80-byte header plus data, less 8
  put_le(h, data, 8);       // dataSize
  put_le(h, frames, 8);     // sampleCount: frames, as in a PCM fact chunk
  put_le(h, 0, 4);          // table length
  put_fmt(h, rate);
  put_tag(h, "data");
  put_le(h, kRiffLimit, 4);
  return h;
}

}  // namespace arcani::cli
