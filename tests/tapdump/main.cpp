// Engine tap dump for the Python reference match (Story 1.5). Test-only: not
// part of engine/ and not shipped. Public C API header only.
//
// Usage: arcani-tapdump RECIPE RATE OUT_DIR [EXTRA_FRAMES]
//
// Compiles the recipe file RECIPE in measure mode at sample rate RATE (decimal
// digits; the engine refuses any rate but 44100 and 48000), then renders the
// whole session plus EXTRA_FRAMES frames past its end (default 0) in one
// arc_render call with every tap. Writes into OUT_DIR, each file raw
// little-endian binary64, interleaved stereo (left, right per frame), the
// pre-quantization engine output and the five taps of docs/signal-spec.md,
// Stub chain, Output and taps:
//
//   out.f64     render output
//   theta.f64   theta reference tap
//   gamma.f64   gamma PAC tap
//   bus.f64     stereo bus tap
//   join.f64    binaural join tap
//   master.f64  master tap
//
// On success prints one line "arcani-tapdump: frames N total T" on stdout
// (N the session length in frames, T = N + EXTRA_FRAMES) and exits 0. Exit 2
// on a usage error, 1 when the recipe cannot be read, is rejected, or a file
// cannot be written (one line on stderr).

#include <arcani/arcani.h>

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

bool parse_u64(const char* text, std::uint64_t& out) {
  if (text == nullptr || *text == '\0') {
    return false;
  }
  std::uint64_t v = 0;
  for (const char* p = text; *p != '\0'; ++p) {
    if (*p < '0' || *p > '9') {
      return false;
    }
    const std::uint64_t d = static_cast<std::uint64_t>(*p - '0');
    if (v > (UINT64_MAX - d) / 10) {
      return false;
    }
    v = v * 10 + d;
  }
  out = v;
  return true;
}

bool read_file(const char* path, std::string& out) {
  std::FILE* f = std::fopen(path, "rb");
  if (f == nullptr) {
    return false;
  }
  char buffer[4096];
  std::size_t got = 0;
  while ((got = std::fread(buffer, 1, sizeof buffer, f)) > 0) {
    out.append(buffer, got);
  }
  const bool ok = std::ferror(f) == 0;
  std::fclose(f);
  return ok;
}

// Writes samples as little-endian binary64 regardless of host byte order.
bool write_f64(const std::string& path, const std::vector<double>& samples) {
  std::vector<unsigned char> bytes;
  bytes.reserve(samples.size() * 8);
  for (double v : samples) {
    std::uint64_t word = 0;
    std::memcpy(&word, &v, sizeof word);
    for (int k = 0; k < 8; ++k) {
      bytes.push_back(static_cast<unsigned char>((word >> (8 * k)) & 0xFFu));
    }
  }
  std::FILE* f = std::fopen(path.c_str(), "wb");
  if (f == nullptr) {
    return false;
  }
  const std::size_t written = bytes.empty() ? 0 : std::fwrite(bytes.data(), 1, bytes.size(), f);
  const bool closed = std::fclose(f) == 0;
  return written == bytes.size() && closed;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 4 && argc != 5) {
    std::fprintf(stderr, "usage: arcani-tapdump RECIPE RATE OUT_DIR [EXTRA_FRAMES]\n");
    return 2;
  }
  std::uint64_t rate = 0;
  std::uint64_t extra = 0;
  if (!parse_u64(argv[2], rate) || rate > UINT32_MAX || (argc == 5 && !parse_u64(argv[4], extra))) {
    std::fprintf(stderr, "usage: arcani-tapdump RECIPE RATE OUT_DIR [EXTRA_FRAMES]\n");
    return 2;
  }
  std::string recipe;
  if (!read_file(argv[1], recipe)) {
    std::fprintf(stderr, "arcani-tapdump: cannot read %s\n", argv[1]);
    return 1;
  }

  arc_compile_options options;
  std::memset(&options, 0, sizeof options);
  options.mode = ARC_MODE_MEASURE;
  options.sample_rate = static_cast<std::uint32_t>(rate);
  options.mute_binaural_ear = ARC_MUTE_NONE;
  arc_error error;
  std::memset(&error, 0, sizeof error);
  arc_plan* plan = nullptr;
  if (arc_compile(recipe.data(), recipe.size(), &options, &plan, &error) != ARC_OK) {
    std::fprintf(stderr, "arcani-tapdump: rejected: parameter=%s value=%s rule=%s limit=%s\n",
                 error.parameter, error.value, error.rule, error.limit);
    return 1;
  }
  const std::uint64_t frames = arc_plan_frame_count(plan);
  const std::uint64_t total = frames + extra;
  if (total < frames || total > SIZE_MAX / 16) {
    std::fprintf(stderr, "arcani-tapdump: too many frames\n");
    arc_plan_release(plan);
    return 1;
  }
  const auto count = static_cast<std::size_t>(total);
  struct Buffer {
    const char* name;
    std::vector<double> samples;
  };
  Buffer buffers[] = {
      {"out", std::vector<double>(2 * count)},    {"theta", std::vector<double>(2 * count)},
      {"gamma", std::vector<double>(2 * count)},  {"bus", std::vector<double>(2 * count)},
      {"join", std::vector<double>(2 * count)},   {"master", std::vector<double>(2 * count)},
  };
  arc_taps taps;
  std::memset(&taps, 0, sizeof taps);
  taps.theta_reference = buffers[1].samples.data();
  taps.gamma_pac = buffers[2].samples.data();
  taps.stereo_bus = buffers[3].samples.data();
  taps.binaural_join = buffers[4].samples.data();
  taps.master = buffers[5].samples.data();

  arc_renderer* renderer = nullptr;
  const bool ok = arc_renderer_create(plan, &renderer, &error) == ARC_OK &&
                  arc_render(renderer, buffers[0].samples.data(), count, &taps, &error) == ARC_OK;
  arc_renderer_destroy(renderer);
  arc_plan_release(plan);
  if (!ok) {
    std::fprintf(stderr, "arcani-tapdump: render failed: %s\n", error.rule);
    return 1;
  }
  const std::string out_dir = argv[3];
  for (const Buffer& b : buffers) {
    const std::string path = out_dir + "/" + b.name + ".f64";
    if (!write_f64(path, b.samples)) {
      std::fprintf(stderr, "arcani-tapdump: cannot write %s\n", path.c_str());
      return 1;
    }
  }
  std::printf("arcani-tapdump: frames %llu total %llu\n", static_cast<unsigned long long>(frames),
              static_cast<unsigned long long>(total));
  return 0;
}
