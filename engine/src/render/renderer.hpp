// Renderer over a compiled plan (Story 1.2; docs/signal-spec.md, Internal
// block size and Stub chain).
//
// Renders in internal blocks of kBlockFrames frames, buffered to any host
// request length. Every sample is a pure function of the plan and its sample
// index: the binaural oscillator phase at frame n is n * inc mod 2^64, so
// seek sets it directly and reads no earlier output. render() and seek()
// never allocate, throw, or do I/O; the constructor holds every buffer.

#ifndef ARCANI_RENDER_RENDERER_HPP
#define ARCANI_RENDER_RENDERER_HPP

#include <array>
#include <cstddef>
#include <cstdint>

#include "plan/plan.hpp"

namespace arcani::render {

// Internal block size in frames (docs/signal-spec.md, Internal block size).
inline constexpr std::size_t kBlockFrames = 64;

// Optional outputs of one render call; each null or 2 * frames doubles,
// interleaved left, right.
struct Taps {
  double* theta_reference = nullptr;
  double* gamma_pac = nullptr;
  double* stereo_bus = nullptr;
  double* binaural_join = nullptr;
  double* master = nullptr;
};

class Renderer {
 public:
  explicit Renderer(const plan::Plan& plan) noexcept;

  // Writes `frames` frames to `out` and to each non-null tap.
  void render(double* out, std::size_t frames, Taps taps) noexcept;

  // The next rendered frame is `frame`.
  void seek(std::uint64_t frame) noexcept;

 private:
  using Block = std::array<double, 2 * kBlockFrames>;

  // Renders frames [position_, position_ + count) of one internal block into
  // the block buffers; count <= kBlockFrames.
  void render_block(std::size_t count) noexcept;

  const plan::Plan& plan_;
  std::uint64_t position_ = 0;
  std::array<std::uint64_t, 2> phase_{0, 0};
  Block theta_{};
  Block gamma_{};
  Block bus_{};
  Block join_{};
  Block master_{};
};

}  // namespace arcani::render

#endif  // ARCANI_RENDER_RENDERER_HPP
