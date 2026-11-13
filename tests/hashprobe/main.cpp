// Cross-platform hash probe (Story 0.1 part 3, Story 0.2, AD-9). Test-only:
// not part of engine/ and not shipped.
//
// Usage: arcani-hashprobe OUT_DIR
//
// Writes one raw little-endian float32 file per component into OUT_DIR
// (probe-arith.f32, sine-44100.f32, sine-48000.f32, stub-chain-44100.f32,
// stub-chain-48000.f32, stub-chain-blocks-44100.f32,
// stub-chain-blocks-48000.f32, theta-envelopes-44100.f32,
// theta-envelopes-48000.f32, gamma-uncoupled-44100.f32,
// gamma-uncoupled-48000.f32, gamma-swell-44100.f32, gamma-swell-48000.f32,
// binaural-cycle-44100.f32, binaural-cycle-48000.f32, gamma-bursts-44100.f32,
// gamma-bursts-48000.f32).
// No hashing here:
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
//
// Components stub-chain-44100 and stub-chain-48000 (Story 1.2): the embedded
// recipe kStubChainRecipe (1 s, a 300 Hz unmodulated theta reference sine in
// both channels (Story 1.5; since Story 2.1 the theta reference at 0 percent
// AM depth, the same bits), a 400 Hz unmodulated binaural sine in the left ear
// and a 406 Hz unmodulated binaural sine in the right ear) compiled in measure mode and
// rendered through the public C API (arc_compile, arc_render) in one call,
// interleaved stereo (left, right per frame), each binary64 sample converted
// to float32 (docs/signal-spec.md, Stub chain). Like the sine components they
// are compared per run against windows-x64, and ci/hash_expected.json pins
// them (Story 1.6, scope engine).
//
// Components stub-chain-blocks-44100 and stub-chain-blocks-48000 (Story 1.6):
// the same recipe compiled the same way, rendered in successive arc_render
// calls whose frame counts cycle through kBlockSizes (the members of threshold
// row block-sizes, in order; the last call is shortened to the frames left).
// Block-size invariance means they equal stub-chain-<fs> byte for byte. Android
// runs no ctest, so this carries the proof to every platform.
// tests/python/test_probe_determinism.py checks kBlockSizes against the row.
//
// Components theta-envelopes-44100 and theta-envelopes-48000 (Story 2.1):
// the eight theta fixtures (recipes/fixtures/valid/theta-<shape>-<rate>hz.json,
// docs/signal-spec.md, Vectors: theta fixtures, in that order: sine,
// smoothed_on_off, sawtooth, reverse_saw, each at 1 Hz then 6 Hz), each a
// 450 Hz carrier amplitude-modulated at the theta rate by that shape at
// 75 percent AM depth, 10 s, theta reference only. The recipes are embedded
// (kThetaFixtures; the probe reads no file), with the fixtures' values. Each
// is compiled in measure mode at that rate and rendered in one call,
// interleaved stereo, each binary64 sample converted to float32, one fixture
// after another. Android runs no ctest, so this carries the theta reference
// to every platform. tests/python/test_probe_theta.py checks each segment
// against reference/theta.py.
//
// Components gamma-uncoupled-44100 and gamma-uncoupled-48000 (Story 2.2):
// the five gamma fixtures (docs/signal-spec.md, Vectors: gamma fixtures, in
// that order: recipes/fixtures/valid/gamma-uncoupled-40hz-25pct.json,
// -40hz-100pct, -60hz-25pct, -60hz-100pct, each a 250 Hz sine carrier
// amplitude-modulated at the gamma rate with a constant AM depth, gamma PAC
// layer only, then theta-gamma-uncoupled.json, that 40 Hz, 100 percent layer
// plus a theta reference: 450 Hz carrier amplitude-modulated at 6 Hz by the
// sine envelope, 75 percent depth), each 10 s. Embedded (kGammaFixtures) with
// the fixtures' values, compiled in measure mode, rendered in one call,
// interleaved stereo, each binary64 sample converted to float32, one fixture
// after another. tests/python/test_probe_gamma.py checks each segment against
// reference/stub_chain.py.
//
// Components gamma-swell-44100 and gamma-swell-48000 (Story 2.3): the four
// committed smooth-swell fixtures (docs/signal-spec.md, Vectors: swell
// fixtures, in that order: recipes/fixtures/valid/swell-sine-0deg-100pct.json,
// swell-sawtooth-90deg-25pct, swell-smoothed-on-off-180deg-100pct,
// swell-reverse-saw-270deg-25pct), each a 250 Hz sine carrier
// amplitude-modulated at 40 Hz with its AM depth a smooth swell at that
// coupling phase and peak depth, plus a theta reference (450 Hz carrier
// amplitude-modulated at 6 Hz by that shape, 75 percent depth), 5 s.
// Embedded (kSwellFixtures) with the fixtures' values, compiled in measure
// mode, rendered in one call, interleaved stereo, each binary64 sample
// converted to float32, one fixture after another.
// tests/python/test_probe_swell.py checks each segment against
// reference/stub_chain.py.
//
// Components gamma-bursts-44100 and gamma-bursts-48000 (Story 2.4): the three
// committed burst fixtures (docs/signal-spec.md, Vectors: burst fixtures, in
// that order: recipes/fixtures/valid/bursts-40hz.json, bursts-45hz,
// bursts-60hz), each a 250 Hz sine carrier amplitude-modulated at that gamma
// rate with its AM depth opening to 100 percent for 50 ms bursts at the 0
// degree coupling phase, plus a theta reference (450 Hz carrier
// amplitude-modulated at 6 Hz by the sine shape, 75 percent depth), 5 s.
// Embedded (kBurstRates) with the fixtures' values, compiled in measure mode,
// rendered in one call, interleaved stereo, each binary64 sample converted
// to float32, one fixture after another. tests/python/test_probe_bursts.py
// checks each segment against reference/stub_chain.py.
//
// Components binaural-cycle-44100 and binaural-cycle-48000 (Story 2.5): the
// fixture recipes/fixtures/valid/binaural-cycle-sleep.json (docs/signal-spec.md,
// Vectors: binaural fixtures), a 100 Hz pure sine in the left ear and a pure
// sine in the right ear whose beat rate cycles over 0 to 3 Hz every 60 s
// from 0 Hz rising, 120 s, binaural only. Embedded (kBinauralCycleRecipe)
// with the fixture's values, compiled in measure mode, then 5 s rendered
// from frame 0 and, after arc_seek to frame seconds_to_samples(55, fs),
// 5 s more, interleaved stereo, each binary64 sample converted to float32,
// the two parts in that order. The seek lands mid-cycle, so the component
// carries both the closed-form phase and seek to every platform.
// tests/python/test_probe_binaural.py checks each part against
// reference/binaural.py.

#include <arcani/arcani.h>

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

constexpr char kStubChainRecipe[] = R"({
  "schema_version": "1.0",
  "engine_version": "0.0.1",
  "seed": 42,
  "author": "Arcani hash probe",
  "date": "2026-11-04",
  "rationale": "Hash probe stub chain component (Stories 1.2 and 1.5): 300 Hz unmodulated theta reference sine in both channels (0 percent AM depth), 400 Hz unmodulated sine in the left ear, 406 Hz unmodulated sine in the right ear, 1 s.",
  "length_s": 1,
  "loudness_target_lufs": -36,
  "theta_reference": {
    "carrier_hz": 300,
    "rate_hz": 6,
    "am_depth_percent": 0,
    "shape": "sine"
  },
  "binaural": {
    "carrier_left_hz": 400,
    "beat_rate_hz": 6
  }
})";

constexpr std::size_t kBlockSizes[] = {1, 64, 512, 4096, 997};

// Theta fixtures in probe order: shape, theta rate in Hz (as JSON text).
struct ThetaFixture {
  const char* shape;
  const char* rate_hz;
};
constexpr ThetaFixture kThetaFixtures[] = {
    {"sine", "1"},     {"sine", "6"},     {"smoothed_on_off", "1"}, {"smoothed_on_off", "6"},
    {"sawtooth", "1"}, {"sawtooth", "6"}, {"reverse_saw", "1"},     {"reverse_saw", "6"},
};

// The recipe of one theta fixture, with the fixture file's values.
std::string theta_recipe(const ThetaFixture& f) {
  return std::string(R"({
  "schema_version": "1.0",
  "engine_version": "0.0.1",
  "seed": 42,
  "author": "Arcani hash probe",
  "date": "2026-11-06",
  "rationale": "Hash probe theta envelope component (Story 2.1): 450 Hz carrier amplitude-modulated at the theta rate, 75 percent AM depth, 10 s.",
  "length_s": 10,
  "loudness_target_lufs": -36,
  "theta_reference": {
    "carrier_hz": 450,
    "rate_hz": )") +
         f.rate_hz + R"(,
    "am_depth_percent": 75,
    "shape": ")" + f.shape + R"("
  }
})";
}

// Gamma fixtures in probe order: gamma rate and AM depth (as JSON text), and
// whether the fixture also has the theta reference.
struct GammaFixture {
  const char* rate_hz;
  const char* depth_percent;
  bool with_theta;
};
constexpr GammaFixture kGammaFixtures[] = {
    {"40", "25", false}, {"40", "100", false}, {"60", "25", false},
    {"60", "100", false}, {"40", "100", true},
};

// The recipe of one gamma fixture, with the fixture file's values.
std::string gamma_recipe(const GammaFixture& f) {
  std::string theta;
  if (f.with_theta) {
    theta = R"(
  "theta_reference": {
    "carrier_hz": 450,
    "rate_hz": 6,
    "am_depth_percent": 75,
    "shape": "sine"
  },)";
  }
  return std::string(R"({
  "schema_version": "1.0",
  "engine_version": "0.0.1",
  "seed": 42,
  "author": "Arcani hash probe",
  "date": "2026-11-07",
  "rationale": "Hash probe gamma PAC component (Story 2.2): 250 Hz sine carrier amplitude-modulated at the gamma rate with a constant AM depth (uncoupled), 10 s.",
  "length_s": 10,
  "loudness_target_lufs": -36,)") +
         theta + R"(
  "gamma_pac": {
    "carrier_hz": 250,
    "rate_hz": )" + f.rate_hz + R"(,
    "am_depth_percent": )" + f.depth_percent + R"(,
    "carrier_wave": "sine",
    "coupling": "uncoupled"
  }
})";
}

// Smooth-swell fixtures in probe order: theta shape, coupling phase, and gamma
// AM depth (as JSON text).
struct SwellFixture {
  const char* shape;
  const char* phase_deg;
  const char* depth_percent;
};
constexpr SwellFixture kSwellFixtures[] = {
    {"sine", "0", "100"},
    {"sawtooth", "90", "25"},
    {"smoothed_on_off", "180", "100"},
    {"reverse_saw", "270", "25"},
};

// The recipe of one smooth-swell fixture, with the fixture file's values.
std::string swell_recipe(const SwellFixture& f) {
  return std::string(R"({
  "schema_version": "1.0",
  "engine_version": "0.0.1",
  "seed": 42,
  "author": "Arcani hash probe",
  "date": "2026-11-10",
  "rationale": "Hash probe smooth-swell component (Story 2.3): 250 Hz sine carrier amplitude-modulated at 40 Hz, its AM depth a smooth swell at the coupling phase of a 450 Hz theta reference amplitude-modulated at 6 Hz, 75 percent depth, 5 s.",
  "length_s": 5,
  "loudness_target_lufs": -36,
  "theta_reference": {
    "carrier_hz": 450,
    "rate_hz": 6,
    "am_depth_percent": 75,
    "shape": ")") +
         f.shape + R"("
  },
  "gamma_pac": {
    "carrier_hz": 250,
    "rate_hz": 40,
    "am_depth_percent": )" + f.depth_percent + R"(,
    "carrier_wave": "sine",
    "coupling": "smooth_swell",
    "coupling_phase_deg": )" + f.phase_deg + R"(
  }
})";
}

// Burst fixtures in probe order: the gamma rate (as JSON text).
constexpr const char* kBurstRates[] = {"40", "45", "60"};

// The recipe of one burst fixture (bursts-<rate>hz), with the fixture file's
// values.
std::string bursts_recipe(const char* rate_hz) {
  return std::string(R"({
  "schema_version": "1.0",
  "engine_version": "0.0.1",
  "seed": 42,
  "author": "Arcani hash probe",
  "date": "2026-11-13",
  "rationale": "Hash probe burst component (Story 2.4): 250 Hz sine carrier amplitude-modulated at the gamma rate, its AM depth opening to 100 percent for 50 ms bursts at the 0 degree coupling phase of a 450 Hz theta reference amplitude-modulated at 6 Hz by the sine envelope, 75 percent depth, 5 s.",
  "length_s": 5,
  "loudness_target_lufs": -36,
  "theta_reference": {
    "carrier_hz": 450,
    "rate_hz": 6,
    "am_depth_percent": 75,
    "shape": "sine"
  },
  "gamma_pac": {
    "carrier_hz": 250,
    "rate_hz": )") +
         rate_hz + R"(,
    "am_depth_percent": 100,
    "carrier_wave": "sine",
    "coupling": "bursts",
    "coupling_phase_deg": 0
  }
})";
}

constexpr char kBinauralCycleRecipe[] = R"({
  "schema_version": "1.0",
  "engine_version": "0.0.1",
  "seed": 42,
  "author": "Arcani hash probe",
  "date": "2026-11-12",
  "rationale": "Hash probe binaural cycle component (Story 2.5): 100 Hz pure sine in the left ear, a pure sine in the right ear whose beat rate cycles over 0 to 3 Hz every 60 s from 0 Hz rising, 120 s.",
  "length_s": 120,
  "loudness_target_lufs": -36,
  "binaural": {
    "carrier_left_hz": 100,
    "beat_rate_hz": 1.5,
    "beat_rate_cycle": {
      "swing_hz": 1.5,
      "period_s": 60,
      "start_phase_deg": 270
    }
  }
})";

constexpr double kBinauralPartSeconds = 5.0;
constexpr double kBinauralSeekSeconds = 55.0;

// Empty on any API failure (main reports it). With cycle_block_sizes false the
// whole recipe renders in one call; with it true, in calls cycling through
// kBlockSizes.
std::vector<float> render_recipe(const std::string& recipe, std::uint32_t fs, bool cycle_block_sizes) {
  arc_compile_options options;
  std::memset(&options, 0, sizeof options);
  options.mode = ARC_MODE_MEASURE;
  options.sample_rate = fs;
  options.mute_binaural_ear = ARC_MUTE_NONE;
  arc_error error;
  arc_plan* plan = nullptr;
  if (arc_compile(recipe.data(), recipe.size(), &options, &plan, &error) != ARC_OK) {
    std::fprintf(stderr, "arcani-hashprobe: compile failed: %s %s %s %s\n", error.parameter, error.value,
                 error.rule, error.limit);
    return {};
  }
  const auto frames = static_cast<std::size_t>(arc_plan_frame_count(plan));
  arc_renderer* renderer = nullptr;
  std::vector<double> stereo(2 * frames);
  bool ok = arc_renderer_create(plan, &renderer, &error) == ARC_OK;
  if (ok && !cycle_block_sizes) {
    ok = arc_render(renderer, stereo.data(), frames, nullptr, &error) == ARC_OK;
  }
  if (ok && cycle_block_sizes) {
    constexpr std::size_t kCount = sizeof kBlockSizes / sizeof kBlockSizes[0];
    std::size_t done = 0;
    for (std::size_t call = 0; ok && done < frames; ++call) {
      std::size_t n = kBlockSizes[call % kCount];
      if (n > frames - done) {
        n = frames - done;
      }
      ok = arc_render(renderer, stereo.data() + 2 * done, n, nullptr, &error) == ARC_OK;
      done += n;
    }
  }
  arc_renderer_destroy(renderer);
  arc_plan_release(plan);
  if (!ok) {
    std::fprintf(stderr, "arcani-hashprobe: render failed: %s\n", error.rule);
    return {};
  }
  std::vector<float> out(stereo.size());
  for (std::size_t i = 0; i < stereo.size(); ++i) {
    out[i] = static_cast<float>(stereo[i]);
  }
  return out;
}

std::vector<float> probe_stub_chain(std::uint32_t fs, bool cycle_block_sizes) {
  return render_recipe(std::string(kStubChainRecipe, sizeof kStubChainRecipe - 1), fs, cycle_block_sizes);
}

// The theta fixtures in turn; empty if any one fails.
std::vector<float> probe_theta(std::uint32_t fs) {
  std::vector<float> out;
  for (const ThetaFixture& f : kThetaFixtures) {
    const std::vector<float> part = render_recipe(theta_recipe(f), fs, false);
    if (part.empty()) {
      return {};
    }
    out.insert(out.end(), part.begin(), part.end());
  }
  return out;
}

// The gamma fixtures in turn; empty if any one fails.
std::vector<float> probe_gamma(std::uint32_t fs) {
  std::vector<float> out;
  for (const GammaFixture& f : kGammaFixtures) {
    const std::vector<float> part = render_recipe(gamma_recipe(f), fs, false);
    if (part.empty()) {
      return {};
    }
    out.insert(out.end(), part.begin(), part.end());
  }
  return out;
}

// The smooth-swell fixtures in turn; empty if any one fails.
std::vector<float> probe_swell(std::uint32_t fs) {
  std::vector<float> out;
  for (const SwellFixture& f : kSwellFixtures) {
    const std::vector<float> part = render_recipe(swell_recipe(f), fs, false);
    if (part.empty()) {
      return {};
    }
    out.insert(out.end(), part.begin(), part.end());
  }
  return out;
}

// The burst fixtures in turn; empty if any one fails.
std::vector<float> probe_bursts(std::uint32_t fs) {
  std::vector<float> out;
  for (const char* rate : kBurstRates) {
    const std::vector<float> part = render_recipe(bursts_recipe(rate), fs, false);
    if (part.empty()) {
      return {};
    }
    out.insert(out.end(), part.begin(), part.end());
  }
  return out;
}

// The binaural cycle fixture: 5 s from frame 0, then 5 s after a seek to
// 55 s; empty on any API failure.
std::vector<float> probe_binaural_cycle(std::uint32_t fs) {
  const std::string recipe(kBinauralCycleRecipe, sizeof kBinauralCycleRecipe - 1);
  arc_compile_options options;
  std::memset(&options, 0, sizeof options);
  options.mode = ARC_MODE_MEASURE;
  options.sample_rate = fs;
  options.mute_binaural_ear = ARC_MUTE_NONE;
  arc_error error;
  arc_plan* plan = nullptr;
  if (arc_compile(recipe.data(), recipe.size(), &options, &plan, &error) != ARC_OK) {
    std::fprintf(stderr, "arcani-hashprobe: compile failed: %s %s %s %s\n", error.parameter, error.value,
                 error.rule, error.limit);
    return {};
  }
  const auto part = static_cast<std::size_t>(arcani::core::seconds_to_samples(kBinauralPartSeconds, fs));
  const std::uint64_t seek = arcani::core::seconds_to_samples(kBinauralSeekSeconds, fs);
  arc_renderer* renderer = nullptr;
  std::vector<double> stereo(4 * part);
  bool ok = arc_renderer_create(plan, &renderer, &error) == ARC_OK;
  ok = ok && arc_render(renderer, stereo.data(), part, nullptr, &error) == ARC_OK;
  ok = ok && arc_seek(renderer, seek, &error) == ARC_OK;
  ok = ok && arc_render(renderer, stereo.data() + 2 * part, part, nullptr, &error) == ARC_OK;
  arc_renderer_destroy(renderer);
  arc_plan_release(plan);
  if (!ok) {
    std::fprintf(stderr, "arcani-hashprobe: render failed: %s\n", error.rule);
    return {};
  }
  std::vector<float> out(stereo.size());
  for (std::size_t i = 0; i < stereo.size(); ++i) {
    out[i] = static_cast<float>(stereo[i]);
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
      {"stub-chain-44100", probe_stub_chain(44100, false)},
      {"stub-chain-48000", probe_stub_chain(48000, false)},
      {"stub-chain-blocks-44100", probe_stub_chain(44100, true)},
      {"stub-chain-blocks-48000", probe_stub_chain(48000, true)},
      {"theta-envelopes-44100", probe_theta(44100)},
      {"theta-envelopes-48000", probe_theta(48000)},
      {"gamma-uncoupled-44100", probe_gamma(44100)},
      {"gamma-uncoupled-48000", probe_gamma(48000)},
      {"gamma-swell-44100", probe_swell(44100)},
      {"gamma-swell-48000", probe_swell(48000)},
      {"binaural-cycle-44100", probe_binaural_cycle(44100)},
      {"binaural-cycle-48000", probe_binaural_cycle(48000)},
      {"gamma-bursts-44100", probe_bursts(44100)},
      {"gamma-bursts-48000", probe_bursts(48000)},
  };
  for (const Component& c : components) {
    if (c.samples.empty()) {
      std::fprintf(stderr, "arcani-hashprobe: component %s is empty\n", c.name);
      return 1;
    }
    const std::string path = out_dir + "/" + c.name + ".f32";
    if (!write_f32(path, c.samples)) {
      std::fprintf(stderr, "arcani-hashprobe: cannot write %s\n", path.c_str());
      return 1;
    }
    std::printf("arcani-hashprobe: wrote %s (%zu samples)\n", path.c_str(), c.samples.size());
  }
  return 0;
}
