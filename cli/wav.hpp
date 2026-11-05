// 24-bit rounding and the WAV header for arcani-render (Story 1.4;
// docs/signal-spec.md, 24-bit rounding).

#ifndef ARCANI_CLI_WAV_HPP
#define ARCANI_CLI_WAV_HPP

#include <cstdint>
#include <span>
#include <vector>

namespace arcani::cli {

// docs/signal-spec.md, 24-bit rounding: NaN gives 0; x = s * 0x1p23;
// x >= 8388607 gives 8388607; x <= -8388608 gives -8388608; else the nearest
// integer, ties to even. Every step is exact, so the result does not depend
// on the host rounding mode or flush mode.
std::int32_t quantize_24(double s) noexcept;

// Appends 3 bytes per sample, little-endian two's complement of
// quantize_24(s), in input order; keeps what `out` already holds.
void append_samples(std::vector<std::uint8_t>& out, std::span<const double> interleaved);

// The header for `frames` stereo frames at `rate`: RIFF (44 bytes) while
// 36 + 6 * frames fits in 32 bits, else RF64 (80 bytes, EBU Tech 3306).
// WAVE_FORMAT_PCM, 16-byte fmt, 2 channels, 24 bits, block align 6, then
// data; no other chunk. A pure function of its arguments.
std::vector<std::uint8_t> wav_header(std::uint64_t frames, std::uint32_t rate);

}  // namespace arcani::cli

#endif  // ARCANI_CLI_WAV_HPP
