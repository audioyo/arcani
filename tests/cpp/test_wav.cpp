// 24-bit rounding and the WAV header (Story 1.4).
//
// Contract with cli/ (internal header, reached through the PUBLIC include
// directory of the static library arcani_cli_core, which is cli/ itself):
//
//   // cli/wav.hpp
//   namespace arcani::cli {
//   // docs/signal-spec.md, 24-bit rounding: NaN gives 0; x = s * 0x1p23;
//   // x >= 8388607 gives 8388607; x <= -8388608 gives -8388608; else the
//   // nearest integer, ties to even. Independent of the host rounding mode
//   // and flush mode.
//   std::int32_t quantize_24(double s) noexcept;
//   // Appends 3 bytes per sample, little-endian two's complement of
//   // quantize_24(s), in input order; keeps what `out` already holds.
//   void append_samples(std::vector<std::uint8_t>& out, std::span<const double> interleaved);
//   // The header for `frames` stereo frames at `rate`: RIFF (44 bytes) while
//   // 36 + 6 * frames fits in 32 bits, else RF64 (80 bytes, EBU Tech 3306:
//   // ds64 after WAVE with riffSize = 72 + data, dataSize = 6 * frames,
//   // sampleCount = frames, table length 0; RIFF and data size fields
//   // 0xFFFFFFFF). WAVE_FORMAT_PCM, 16-byte fmt, 2 channels, 24 bits, block
//   // align 6, then data; no other chunk. A pure function of its arguments.
//   std::vector<std::uint8_t> wav_header(std::uint64_t frames, std::uint32_t rate);
//   }
//
// tests/cpp/CMakeLists.txt links arcani_cli_core and defines
// ARCANI_HAVE_CLI_CORE only once that target exists, so before it does this
// file compiles its harness cases plus one failing case.
//
// The spec vectors come from tests/data/signal_spec_vectors.json through the
// generated spec_tables.hpp (kQuantize24); the harness rule, the naive
// conversions, and the header builder are in cli_helpers.hpp.

#include "cli_helpers.hpp"
#include "host_fp_mode.hpp"
#include "spec_tables.hpp"

#include <catch2/catch_test_macros.hpp>

#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <string>
#include <vector>

namespace spec = arcani::test::spec;
namespace h = arcani::test::cli;

namespace {

std::vector<std::uint8_t> vector_bytes() {
  std::vector<std::uint8_t> out;
  for (const auto& v : spec::kQuantize24) {
    out.insert(out.end(), v.bytes, v.bytes + 3);
  }
  return out;
}

bool same_double(double a, double b) { return std::memcmp(&a, &b, sizeof a) == 0; }

bool has_vector(double s) {
  for (const auto& v : spec::kQuantize24) {
    if (same_double(v.s, s)) {
      return true;
    }
  }
  return false;
}

using Conversion = std::int32_t (*)(double);

// Labels of the vectors of `rule` on which `f` differs from the spec value.
std::vector<std::string> caught(Conversion f, const char* rule) {
  std::vector<std::string> out;
  for (const auto& v : spec::kQuantize24) {
    if (std::string(v.rule) == rule && f(v.s) != v.value) {
      out.push_back(v.label);
    }
  }
  return out;
}

// Frame counts for the header tests. 715827876 is the largest that fits
// RIFF (36 + 6 * 715827876 = 0xFFFFFFFC); 8 h is 1382400000 frames at
// 48 kHz and 1270080000 at 44.1 kHz.
constexpr std::uint64_t kRiffMaxFrames = 715827876;
const std::uint64_t kHeaderFrames[] = {0,          1,          44100,        48000,
                                       kRiffMaxFrames, kRiffMaxFrames + 1, 1270080000,
                                       1382400000, std::uint64_t{1} << 40};
const std::uint32_t kRates[] = {44100, 48000};

}  // namespace

// ------------------------------------------------------------ harness

TEST_CASE("24-bit rounding: the harness rule and byte packing match every spec vector", "[wav]") {
  REQUIRE(std::size(spec::kQuantize24) > 0);
  for (const auto& v : spec::kQuantize24) {
    INFO(v.rule << ": " << v.label);
    CHECK(h::spec_quantize_24(v.s) == v.value);
    std::vector<std::uint8_t> b;
    h::put_le24(b, v.value);
    REQUIRE(b.size() == 3);
    CHECK(b[0] == v.bytes[0]);
    CHECK(b[1] == v.bytes[1]);
    CHECK(b[2] == v.bytes[2]);
  }
}

TEST_CASE("24-bit rounding: the vectors cover the spec matrix row", "[wav]") {
  const double lsb = 0x1p-23;
  CHECK(has_vector(1.0));
  CHECK(has_vector(std::nextafter(1.0, 2.0)));
  CHECK(has_vector(-1.0));
  CHECK(has_vector(std::nextafter(-1.0, -2.0)));
  CHECK(has_vector(std::numeric_limits<double>::infinity()));
  CHECK(has_vector(-std::numeric_limits<double>::infinity()));
  CHECK(has_vector(-0.0));
  for (double k : {0.5, 1.5, 2.5}) {
    CHECK(has_vector(k * lsb));
    CHECK(has_vector(-k * lsb));
  }
  bool nan = false;
  for (const auto& v : spec::kQuantize24) {
    nan = nan || std::isnan(v.s);
  }
  CHECK(nan);
}

TEST_CASE("24-bit rounding: each naive conversion fails a vector of the rule it breaks",
          "[wav][mustfail]") {
  CHECK_FALSE(caught(h::naive_no_clamp, "clamp").empty());
  CHECK_FALSE(caught(h::naive_no_nan_rule, "nan").empty());
  CHECK_FALSE(caught(h::naive_truncate, "tie").empty());
  CHECK_FALSE(caught(h::naive_half_away, "tie").empty());
  // The harness rule itself is caught by none.
  for (const char* rule : {"clamp", "nan", "tie", "round", "zero"}) {
    CHECK(caught(h::spec_quantize_24, rule).empty());
  }
}

TEST_CASE("WAV check: the spec header passes, doctored headers fail", "[wav][mustfail]") {
  for (std::uint32_t rate : kRates) {
    for (std::uint64_t frames : {std::uint64_t{0}, std::uint64_t{1}, std::uint64_t{37}}) {
      std::vector<std::uint8_t> file = h::expected_wav_header(frames, rate);
      REQUIRE(file.size() == 44);
      file.resize(file.size() + frames * 6, 0);
      INFO("frames " << frames << " rate " << rate);
      CHECK(h::wav_problems(file, frames, rate).empty());
    }
  }
  CHECK_FALSE(h::needs_rf64(kRiffMaxFrames));
  CHECK(h::needs_rf64(kRiffMaxFrames + 1));
  CHECK(h::expected_wav_header(kRiffMaxFrames, 48000).size() == 44);
  CHECK(h::expected_wav_header(kRiffMaxFrames + 1, 48000).size() == 80);

  const std::uint64_t frames = 37;
  const std::uint32_t rate = 48000;
  auto good = [&] {
    std::vector<std::uint8_t> f = h::expected_wav_header(frames, rate);
    f.resize(f.size() + frames * 6, 0);
    return f;
  };
  struct Doctor {
    const char* what;
    std::size_t at;
    std::uint8_t byte;
  };
  const Doctor doctors[] = {
      {"RIFF id", 0, 'X'},          {"RIFF size", 4, 0x00},   {"WAVE id", 8, 'X'},
      {"fmt id", 12, 'X'},          {"fmt size", 16, 18},     {"format tag 3", 20, 3},
      {"one channel", 22, 1},       {"rate", 24, 0x45},       {"byte rate", 28, 0x01},
      {"block align", 32, 4},       {"16 bits", 34, 16},      {"data id", 36, 'X'},
      {"data size", 40, 0x00},
  };
  for (const Doctor& d : doctors) {
    std::vector<std::uint8_t> f = good();
    REQUIRE(f[d.at] != d.byte);
    f[d.at] = d.byte;
    INFO(d.what);
    CHECK_FALSE(h::wav_problems(f, frames, rate).empty());
  }
  std::vector<std::uint8_t> truncated = good();
  truncated.pop_back();
  CHECK_FALSE(h::wav_problems(truncated, frames, rate).empty());
  std::vector<std::uint8_t> trailing = good();
  trailing.push_back(0);
  CHECK_FALSE(h::wav_problems(trailing, frames, rate).empty());
  CHECK_FALSE(h::wav_problems(good(), frames + 1, rate).empty());
  CHECK_FALSE(h::wav_problems(good(), frames, 44100).empty());
  // An extra chunk between fmt and data.
  std::vector<std::uint8_t> extra = good();
  const std::uint8_t list[] = {'L', 'I', 'S', 'T', 0, 0, 0, 0};
  extra.insert(extra.begin() + 36, list, list + 8);
  CHECK_FALSE(h::wav_problems(extra, frames, rate).empty());
  // An RF64 header for a size that fits RIFF.
  std::vector<std::uint8_t> rf64 = h::expected_wav_header(kRiffMaxFrames + 1, rate);
  rf64.resize(rf64.size() + frames * 6, 0);
  CHECK_FALSE(h::wav_problems(rf64, frames, rate).empty());
}

#if defined(ARCANI_HAVE_CLI_CORE) && __has_include("wav.hpp")

#include "wav.hpp"

#include <span>

namespace cli = arcani::cli;

// ---------------------------------------------------------- cli quantizer

TEST_CASE("quantize_24 matches every spec vector", "[wav][cli]") {
  for (const auto& v : spec::kQuantize24) {
    INFO(v.rule << ": " << v.label);
    CHECK(cli::quantize_24(v.s) == v.value);
  }
}

TEST_CASE("quantize_24 does not depend on the rounding mode or the flush mode", "[wav][cli]") {
  const int modes[] = {FE_TONEAREST, FE_UPWARD, FE_DOWNWARD, FE_TOWARDZERO};
  const int saved = std::fegetround();
  for (int mode : modes) {
    REQUIRE(std::fesetround(mode) == 0);
    for (const auto& v : spec::kQuantize24) {
      INFO("rounding mode " << mode << ", " << v.rule << ": " << v.label);
      CHECK(cli::quantize_24(v.s) == v.value);
    }
  }
  REQUIRE(std::fesetround(saved) == 0);
  if (arcani::test::fp::supported()) {
    namespace fp = arcani::test::fp;
    fp::HostMode flush(fp::get() | fp::flush_bits());
    for (const auto& v : spec::kQuantize24) {
      INFO("flush mode, " << v.rule << ": " << v.label);
      CHECK(cli::quantize_24(v.s) == v.value);
    }
  }
}

TEST_CASE("quantize_24 agrees with the spec rule around every tie near zero and full scale",
          "[wav][cli]") {
  std::vector<double> samples;
  for (int k = -40; k <= 40; ++k) {
    for (double base : {static_cast<double>(k), 8388560.0 + k, -8388560.0 + k}) {
      const double tie = (base + 0.5) * 0x1p-23;
      samples.push_back(tie);
      samples.push_back(std::nextafter(tie, 2.0));
      samples.push_back(std::nextafter(tie, -2.0));
      samples.push_back(base * 0x1p-23);
    }
  }
  for (double s : samples) {
    INFO("s = " << s);
    CHECK(cli::quantize_24(s) == h::spec_quantize_24(s));
  }
}

TEST_CASE("append_samples writes 3 little-endian bytes per sample and keeps earlier bytes",
          "[wav][cli]") {
  std::vector<double> samples;
  for (const auto& v : spec::kQuantize24) {
    samples.push_back(v.s);
  }
  std::vector<std::uint8_t> out = {0xAB, 0xCD};
  cli::append_samples(out, std::span<const double>(samples));
  std::vector<std::uint8_t> want = {0xAB, 0xCD};
  const std::vector<std::uint8_t> bytes = vector_bytes();
  want.insert(want.end(), bytes.begin(), bytes.end());
  CHECK(out == want);
  std::vector<std::uint8_t> empty;
  cli::append_samples(empty, std::span<const double>());
  CHECK(empty.empty());
}

// --------------------------------------------------------------- header

TEST_CASE("wav_header is RIFF or RF64 by the spec layout at both rates", "[wav][cli]") {
  for (std::uint32_t rate : kRates) {
    for (std::uint64_t frames : kHeaderFrames) {
      INFO("frames " << frames << " rate " << rate);
      const std::vector<std::uint8_t> got = cli::wav_header(frames, rate);
      CHECK(got == h::expected_wav_header(frames, rate));
      CHECK(got.size() == (h::needs_rf64(frames) ? 80u : 44u));
      CHECK(cli::wav_header(frames, rate) == got);  // pure
    }
  }
}

TEST_CASE("wav_header at the RIFF limit: one frame more switches to RF64", "[wav][cli]") {
  const std::vector<std::uint8_t> riff = cli::wav_header(kRiffMaxFrames, 48000);
  const std::vector<std::uint8_t> rf64 = cli::wav_header(kRiffMaxFrames + 1, 48000);
  REQUIRE(riff.size() == 44);
  REQUIRE(rf64.size() == 80);
  CHECK(h::tag_at(riff, 0, "RIFF"));
  CHECK(h::get_le(riff, 4, 4) == 36 + kRiffMaxFrames * 6);
  CHECK(h::get_le(riff, 40, 4) == kRiffMaxFrames * 6);
  CHECK(h::tag_at(rf64, 0, "RF64"));
  CHECK(h::tag_at(rf64, 12, "ds64"));
  CHECK(h::get_le(rf64, 20, 8) == 72 + (kRiffMaxFrames + 1) * 6);
  CHECK(h::get_le(rf64, 28, 8) == (kRiffMaxFrames + 1) * 6);
  CHECK(h::get_le(rf64, 36, 8) == kRiffMaxFrames + 1);
}

TEST_CASE("a header-only WAV for 0 frames passes the WAV check", "[wav][cli]") {
  for (std::uint32_t rate : kRates) {
    CHECK(h::wav_problems(cli::wav_header(0, rate), 0, rate).empty());
  }
}

#else

TEST_CASE("not implemented: cli/wav.hpp (arcani_cli_core)", "[wav][cli]") {
  FAIL("arcani_cli_core with cli/wav.hpp (quantize_24, append_samples, wav_header) does not "
       "exist yet");
}

#endif
