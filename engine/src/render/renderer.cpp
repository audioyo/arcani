// Renderer: the stub chain, per sample in the spec's operation order
// (docs/signal-spec.md, Stub chain, Per sample).

#include "render/renderer.hpp"

#include <algorithm>
#include <cstring>
#include <initializer_list>
#include <limits>

#include "core/sine.hpp"

namespace arcani::render {

namespace {

void copy_out(double* dest, const double* block, std::size_t count) noexcept {
  if (dest != nullptr) {
    std::memcpy(dest, block, 2 * count * sizeof(double));
  }
}

}  // namespace

Renderer::Renderer(const plan::Plan& plan) noexcept : plan_(plan) {}

void Renderer::seek(std::uint64_t frame) noexcept {
  position_ = frame;
  theta_phase_ = frame * plan_.theta.increment;  // mod 2^64 (unsigned wraparound)
  for (std::size_t c = 0; c < 2; ++c) {
    phase_[c] = frame * plan_.binaural.increment[c];  // mod 2^64 (unsigned wraparound)
  }
}

void Renderer::render_block(std::size_t count) noexcept {
  const std::uint64_t end = plan_.frame_count;
  const std::uint64_t live_left = position_ < end ? end - position_ : 0;
  const std::size_t live = static_cast<std::size_t>(std::min<std::uint64_t>(live_left, count));
  const auto& ears = plan_.binaural;
  const auto& osc = plan_.theta;
  for (std::size_t i = 0; i < count; ++i) {
    const double theta_sample = i < live ? osc.amplitude * core::sine(theta_phase_) : 0.0;
    for (std::size_t c = 0; c < 2; ++c) {
      const std::size_t k = 2 * i + c;
      if (i < live) {
        const double theta = theta_sample;                       // theta reference stub, same in both channels
        const double gamma = 0.0;                                // gamma PAC stub
        const double bus = theta + gamma;                        // stereo bus, within channel c
        const double bin = ears.amplitude[c] * core::sine(phase_[c]);  // binaural oscillator of ear c
        const double join = bus + bin;                           // binaural join, ear c to channel c only
        const double master = join * 1.0;                        // per-channel gain (stored gain is Epic 4)
        theta_[k] = theta;
        gamma_[k] = gamma;
        bus_[k] = bus;
        join_[k] = join;
        master_[k] = master;  // stereo-linked limiter stub: identity
      } else {
        theta_[k] = 0.0;
        gamma_[k] = 0.0;
        bus_[k] = 0.0;
        join_[k] = 0.0;
        master_[k] = 0.0;
      }
      phase_[c] += ears.increment[c];
    }
    theta_phase_ += osc.increment;
  }
}

void Renderer::render(double* out, std::size_t frames, Taps taps) noexcept {
  constexpr std::uint64_t kMax = std::numeric_limits<std::uint64_t>::max();
  while (frames > 0) {
    const std::size_t in_block = kBlockFrames - static_cast<std::size_t>(position_ % kBlockFrames);
    const std::size_t count = std::min(frames, in_block);
    render_block(count);
    copy_out(out, master_.data(), count);
    copy_out(taps.theta_reference, theta_.data(), count);
    copy_out(taps.gamma_pac, gamma_.data(), count);
    copy_out(taps.stereo_bus, bus_.data(), count);
    copy_out(taps.binaural_join, join_.data(), count);
    copy_out(taps.master, master_.data(), count);
    out += 2 * count;
    for (double** tap : {&taps.theta_reference, &taps.gamma_pac, &taps.stereo_bus, &taps.binaural_join,
                         &taps.master}) {
      if (*tap != nullptr) {
        *tap += 2 * count;
      }
    }
    position_ = position_ > kMax - count ? kMax : position_ + count;
    frames -= count;
  }
}

}  // namespace arcani::render
