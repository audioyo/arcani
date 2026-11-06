// Determinism and block-size invariance, in one process (Story 1.6).
//
// Contract:
//
// - For each stub chain fixture (recipes/fixtures/valid/stub-chain-1s-beat-0
//   and -beat-6) at each rate of row `sample-rates`, compiled in measure mode,
//   the full WAV bytes are built in memory exactly as arcani-render builds
//   them: arcani::cli::wav_header(frames, rate), then
//   arcani::cli::append_samples after every arc_render call (cli/wav.hpp,
//   library arcani_cli_core). The engine is reached through the public
//   header arcani/arcani.h only.
// - Block sizes come from row `block-sizes` (unit "frames per call"). The
//   row holds 1, 64, 512, 4096, and the AC's odd size (Story 1.6 decision:
//   997, not a multiple of 64 and above 64, so calls cross internal block
//   boundaries at varying offsets). The
//   4096-frame bytes are the reference.
// - Block-size invariance: at every member, the differing-byte count
//   (determinism_helpers.hpp, differing_bytes) against the 4096-frame bytes
//   is at most row `block-size-invariance` (unit "differing bytes").
// - Repeat: two independent compiles and renders in one process give a
//   differing-byte count of at most row `determinism` (unit "differing
//   bytes").
// - Must-fail: a harness copy with one doctored data byte, and one with a
//   frame dropped (header for frames - 1, that frame's 6 bytes removed),
//   each exceed both rows.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <vector>

#include "api_helpers.hpp"
#include "determinism_helpers.hpp"
#include "tables.hpp"
#include "wav.hpp"

namespace api = arcani::test::api;
namespace det = arcani::test::determinism;
namespace tables = arcani::test::tables;

namespace {

constexpr std::size_t kReferenceBlock = 4096;

std::vector<std::size_t> block_sizes() {
  const tables::Row& r = tables::row("block-sizes");
  REQUIRE(r.unit == "frames per call");
  std::vector<std::size_t> out;
  for (double v : r.values) {
    REQUIRE(v >= 1.0);
    out.push_back(static_cast<std::size_t>(v));
  }
  return out;
}

std::vector<std::uint32_t> sample_rates() {
  const tables::Row& r = tables::row("sample-rates");
  REQUIRE(r.unit == "Hz");
  std::vector<std::uint32_t> out;
  for (double v : r.values) {
    out.push_back(static_cast<std::uint32_t>(v));
  }
  return out;
}

double differing_bytes_row(const char* id) {
  const tables::Row& r = tables::row(id);
  REQUIRE(r.unit == "differing bytes");
  return r.value();
}

struct Wav {
  std::uint64_t frames = 0;
  std::vector<std::uint8_t> bytes;
};

// A fresh compile and renderer, then the whole session in `block`-frame
// calls, into WAV bytes as arcani-render writes them.
Wav wav_bytes(const std::string& fixture, std::uint32_t rate, std::size_t block) {
  api::PlanPtr plan = api::compile_ok(api::valid(fixture), api::options(ARC_MODE_MEASURE, rate));
  Wav w;
  w.frames = arc_plan_frame_count(plan.get());
  w.bytes = arcani::cli::wav_header(w.frames, rate);
  api::RendererPtr r = api::renderer(plan.get());
  const std::string failure = det::render_in_blocks(
      r.get(), w.frames, block, [&w](const double* samples, std::size_t n) {
        arcani::cli::append_samples(w.bytes, std::span<const double>(samples, 2 * n));
      });
  INFO(fixture << " at " << rate << " Hz, " << block << " frames per call");
  REQUIRE(failure.empty());
  return w;
}

const char* const kFixtures[] = {api::kBeat0, api::kBeat6};

}  // namespace

TEST_CASE("row block-sizes holds 1, 64, 512, 4096, and an odd size", "[determinism]") {
  const std::vector<std::size_t> sizes = block_sizes();
  for (std::size_t want : {std::size_t{1}, std::size_t{64}, std::size_t{512}, std::size_t{4096}}) {
    INFO("block size " << want);
    CHECK(std::count(sizes.begin(), sizes.end(), want) == 1);
  }
  // The AC's odd size: odd, above 64, and not a multiple of 64, so calls
  // cross internal block boundaries at varying offsets.
  CHECK(std::any_of(sizes.begin(), sizes.end(),
                    [](std::size_t s) { return s > 64 && s % 2 == 1 && s % 64 != 0; }));
}

TEST_CASE("every block-sizes member gives the 4096-frame WAV bytes", "[determinism]") {
  const std::vector<std::size_t> sizes = block_sizes();
  REQUIRE(std::count(sizes.begin(), sizes.end(), kReferenceBlock) == 1);
  const double allowed = differing_bytes_row("block-size-invariance");
  for (const char* fixture : kFixtures) {
    for (std::uint32_t rate : sample_rates()) {
      const Wav reference = wav_bytes(fixture, rate, kReferenceBlock);
      INFO(fixture << " at " << rate << " Hz");
      REQUIRE(reference.frames == rate);  // 1 s fixtures
      REQUIRE(reference.bytes.size() == 44 + 6 * reference.frames);
      // The data is not silent, so the comparison compares a real signal.
      CHECK(std::any_of(reference.bytes.begin() + 44, reference.bytes.end(),
                        [](std::uint8_t b) { return b != 0; }));
      for (std::size_t block : sizes) {
        const Wav w = wav_bytes(fixture, rate, block);
        const std::uint64_t count = det::differing_bytes(w.bytes, reference.bytes);
        INFO(block << " frames per call: " << count << " differing bytes, row allows " << allowed);
        CHECK(static_cast<double>(count) <= allowed);
      }
    }
  }
}

TEST_CASE("two compiles and renders in one process give the same WAV bytes", "[determinism]") {
  const double allowed = differing_bytes_row("determinism");
  for (const char* fixture : kFixtures) {
    for (std::uint32_t rate : sample_rates()) {
      const Wav first = wav_bytes(fixture, rate, kReferenceBlock);
      const Wav second = wav_bytes(fixture, rate, kReferenceBlock);
      const std::uint64_t count = det::differing_bytes(first.bytes, second.bytes);
      INFO(fixture << " at " << rate << " Hz: " << count << " differing bytes, row allows " << allowed);
      CHECK(static_cast<double>(count) <= allowed);
    }
  }
}

TEST_CASE("the differing-byte count catches a doctored byte and a dropped frame", "[determinism]") {
  const double invariance = differing_bytes_row("block-size-invariance");
  const double repeat = differing_bytes_row("determinism");
  const std::uint32_t rate = sample_rates().front();
  const Wav reference = wav_bytes(api::kBeat6, rate, kReferenceBlock);
  REQUIRE(det::differing_bytes(reference.bytes, reference.bytes) == 0);

  // One doctored data byte in the middle of the session.
  std::vector<std::uint8_t> doctored = reference.bytes;
  const std::size_t at = 44 + 6 * static_cast<std::size_t>(reference.frames / 2) + 1;
  doctored[at] = static_cast<std::uint8_t>(doctored[at] ^ 0x01u);
  const std::uint64_t doctored_count = det::differing_bytes(doctored, reference.bytes);
  CHECK(doctored_count == 1);
  CHECK_FALSE(static_cast<double>(doctored_count) <= invariance);
  CHECK_FALSE(static_cast<double>(doctored_count) <= repeat);

  // One frame dropped: the header for frames - 1, and that frame's bytes gone.
  const std::size_t drop = static_cast<std::size_t>(reference.frames / 3);
  std::vector<std::uint8_t> dropped = arcani::cli::wav_header(reference.frames - 1, rate);
  dropped.insert(dropped.end(), reference.bytes.begin() + 44,
                 reference.bytes.begin() + 44 + static_cast<std::ptrdiff_t>(6 * drop));
  dropped.insert(dropped.end(), reference.bytes.begin() + 44 + static_cast<std::ptrdiff_t>(6 * (drop + 1)),
                 reference.bytes.end());
  REQUIRE(dropped.size() + 6 == reference.bytes.size());
  const std::uint64_t dropped_count = det::differing_bytes(dropped, reference.bytes);
  CHECK_FALSE(static_cast<double>(dropped_count) <= invariance);
  CHECK_FALSE(static_cast<double>(dropped_count) <= repeat);
}

