// Cross-platform hash probe (Story 0.1 part 3, Story 0.2, AD-9). Test-only:
// not part of engine/ and not shipped.
//
// Usage: arcani-hashprobe OUT_DIR
//
// Writes one raw little-endian float32 file per component into OUT_DIR
// (probe-arith.f32, sine-44100.f32, sine-48000.f32). No hashing here:
// tools/hash_manifest.py hashes the files on the host.
//
// Component probe-arith: a fixed sequence of float32 multiplies and adds whose
// bits change if multiply-add contraction or fast-math is on. Its float32
// reference is tools/probe_reference.py, which uses the same operation order:
//
//   s = 0.3125                       (seed, read through a volatile)
//   repeat 4096 times:
//     t = R * s                      (R = 3.8984375)
//     s = t - t * s                  (contractable: one fused multiply-subtract)
//     out = s * A + B                (A = 0.7109375, B = 0.1015625; contractable)
//
// Every constant is exact in float32 and in decimal, so both sides start from
// the same bits. s stays inside (0, 1) (a logistic map), so a single rounding
// difference spreads to almost every later sample.
//
// Components sine-44100 and sine-48000 (Story 0.2): the engine sine
// (arcani::core::sine, docs/signal-spec.md, Sine), unmodulated, 1 s each of a
// 1 Hz, a 450 Hz, and a 1000 Hz carrier at that sample rate, in that order.
// Each segment starts at phase 0 and steps by the spec's increment rule; each
// sample is the binary64 engine sine converted to float32. The sine is
// computed inside the engine library, so ARCANI_HASHPROBE_EXTRA_FLAGS (which
// reaches this file only) does not change these components. Their ideal
// reference is reference/ideal.py (tests/python/test_probe_sine.py); across
// platforms they are compared exactly against windows-x64.

#include "core/phase.hpp"
#include "core/sine.hpp"

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

constexpr int kProbeArithSamples = 4096;

std::vector<float> probe_arith() {
  volatile float seed = 0.3125f;
  const float r = 3.8984375f;
  const float a = 0.7109375f;
  const float b = 0.1015625f;
  float s = seed;
  std::vector<float> out(kProbeArithSamples);
  for (int i = 0; i < kProbeArithSamples; ++i) {
    const float t = r * s;
    s = t - t * s;
    out[static_cast<std::size_t>(i)] = s * a + b;
  }
  return out;
}

constexpr double kSineCarriersHz[] = {1.0, 450.0, 1000.0};

std::vector<float> probe_sine(std::uint32_t fs) {
  std::vector<float> out;
  out.reserve(static_cast<std::size_t>(fs) * (sizeof kSineCarriersHz / sizeof kSineCarriersHz[0]));
  for (double carrier_hz : kSineCarriersHz) {
    arcani::core::SineOscillator osc(arcani::core::phase_increment(carrier_hz, fs));
    for (std::uint32_t n = 0; n < fs; ++n) {
      out.push_back(static_cast<float>(osc.next()));
    }
  }
  return out;
}

// Writes samples as little-endian float32 regardless of host byte order.
bool write_f32(const std::string& path, const std::vector<float>& samples) {
  std::vector<unsigned char> bytes;
  bytes.reserve(samples.size() * 4);
  for (float v : samples) {
    std::uint32_t word = 0;
    std::memcpy(&word, &v, sizeof word);
    for (int k = 0; k < 4; ++k) {
      bytes.push_back(static_cast<unsigned char>((word >> (8 * k)) & 0xFFu));
    }
  }
  std::FILE* f = std::fopen(path.c_str(), "wb");
  if (f == nullptr) {
    return false;
  }
  const std::size_t written = std::fwrite(bytes.data(), 1, bytes.size(), f);
  const bool closed = std::fclose(f) == 0;
  return written == bytes.size() && closed;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 2) {
    std::fprintf(stderr, "usage: arcani-hashprobe OUT_DIR\n");
    return 2;
  }
  const std::string out_dir = argv[1];
  struct Component {
    const char* name;
    std::vector<float> samples;
  };
  const Component components[] = {
      {"probe-arith", probe_arith()},
      {"sine-44100", probe_sine(44100)},
      {"sine-48000", probe_sine(48000)},
  };
  for (const Component& c : components) {
    const std::string path = out_dir + "/" + c.name + ".f32";
    if (!write_f32(path, c.samples)) {
      std::fprintf(stderr, "arcani-hashprobe: cannot write %s\n", path.c_str());
      return 1;
    }
    std::printf("arcani-hashprobe: wrote %s (%zu samples)\n", path.c_str(), c.samples.size());
  }
  return 0;
}
