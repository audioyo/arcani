// Helpers for the determinism and block-size tests (Story 1.6): the
// differing-byte count and a render loop in host blocks of a given size.
// Reaches the engine only through the public header arcani/arcani.h. Test
// code only; no part of it lives in cli/ or engine/.

#pragma once

#include <arcani/arcani.h>

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace arcani::test::determinism {

// The number of differing bytes between two byte strings: positions below
// the shorter length whose bytes differ, plus the length difference. Equal
// strings give 0; a dropped or added frame always gives more than 0.
inline std::uint64_t differing_bytes(const std::vector<std::uint8_t>& a,
                                     const std::vector<std::uint8_t>& b) {
  const std::size_t common = a.size() < b.size() ? a.size() : b.size();
  std::uint64_t count = 0;
  for (std::size_t i = 0; i < common; ++i) {
    if (a[i] != b[i]) {
      ++count;
    }
  }
  const std::size_t longer = a.size() < b.size() ? b.size() : a.size();
  return count + static_cast<std::uint64_t>(longer - common);
}

// Renders `frames` frames from `r` in successive arc_render calls of
// `block` frames (the last one shortened to the frames left), calling
// on_block(samples, frames_in_block) after each call with the interleaved
// stereo output. Returns an empty string on success, else a description of
// the first failing call.
template <typename OnBlock>
std::string render_in_blocks(arc_renderer* r, std::uint64_t frames, std::size_t block,
                             OnBlock&& on_block) {
  if (block == 0) {
    return "block size 0";
  }
  std::vector<double> buffer(2 * block);
  for (std::uint64_t done = 0; done < frames;) {
    const std::uint64_t left = frames - done;
    const std::size_t n = left < block ? static_cast<std::size_t>(left) : block;
    arc_error e;
    const arc_status s = arc_render(r, buffer.data(), n, nullptr, &e);
    if (s != ARC_OK) {
      return "arc_render failed at frame " + std::to_string(done) + " with " +
             std::to_string(n) + " frames: rule " + std::string(e.rule);
    }
    on_block(static_cast<const double*>(buffer.data()), n);
    done += n;
  }
  return {};
}

}  // namespace arcani::test::determinism
