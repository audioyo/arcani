// Cross-platform hash probe (Story 0.1 part 3, AD-9). Test-only: not part of
// engine/ and not shipped.
//
// Usage: arcani-hashprobe OUT_DIR
//
// Writes one raw little-endian float32 file per component into OUT_DIR. No
// hashing here: tools/hash_manifest.py hashes the files on the host.
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
// Story 0.2 adds the engine sine as a second component.

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
  const std::string path = out_dir + "/probe-arith.f32";
  if (!write_f32(path, probe_arith())) {
    std::fprintf(stderr, "arcani-hashprobe: cannot write %s\n", path.c_str());
    return 1;
  }
  std::printf("arcani-hashprobe: wrote %s (%d samples)\n", path.c_str(), kProbeArithSamples);
  return 0;
}
