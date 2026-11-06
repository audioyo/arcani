// Fixed stage list and the stub chain (Story 1.2; docs/signal-spec.md,
// Internal block size and Stub chain).
//
// Two parts:
//
// 1. The stage descriptor table, an engine-internal header (one of the two
//    internal-header tests this story allows; the other is the denormal
//    guard). Expected interface, engine/src/plan/plan.hpp, namespace
//    arcani::plan:
//
//      enum class StageKind : int {             // values equal arc_stage_kind
//        ThetaReference = 0, GammaPac = 1, StereoBus = 2, BinauralJoin = 3,
//        MasterChain = 4 };
//      enum class ChannelUse { PerChannel, LinkedGain };
//      struct StageDescriptor {
//        StageKind kind;
//        ChannelUse channel_use;          // LinkedGain: the stage reads both
//                                         // channels only to derive one gain
//                                         // applied to each channel
//        std::array<int, 2> input_channel;  // output channel c reads its audio
//                                           // from input channel input_channel[c]
//      };
//      std::span<const StageDescriptor> stage_descriptors() noexcept;  // in stage order
//
// 2. The stage list and the stub chain through the public C API: stage kinds
//    in order, every tap and the output against the spec vectors (generated
//    header spec_tables.hpp, kStubChain), the muted ear, no layers, optional
//    taps, and exact zeros past the session end.
//
// Story 1.5: the theta reference stub is an unmodulated sine at the theta
// carrier, unit amplitude, the same value in both channels (signal spec, Stub
// chain, Theta reference oscillator). The theta tap and the stereo bus hold
// the row's theta bits; a fixture without theta_reference keeps them at +0.0.
// Muting affects only the binaural oscillator, so a muted channel equals its
// theta tap bit for bit.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#include <string>
#include <utility>
#include <vector>

#if __has_include("plan/plan.hpp")

#include "plan/plan.hpp"

#include <array>
#include <span>

namespace plan = arcani::plan;

namespace {

std::vector<std::string> descriptor_problems(std::span<const plan::StageDescriptor> table) {
  std::vector<std::string> out;
  const plan::StageKind order[] = {plan::StageKind::ThetaReference, plan::StageKind::GammaPac,
                                   plan::StageKind::StereoBus, plan::StageKind::BinauralJoin,
                                   plan::StageKind::MasterChain};
  if (table.size() != 5) {
    out.push_back("stage count " + std::to_string(table.size()) + ", expected 5");
    return out;
  }
  for (std::size_t i = 0; i < table.size(); ++i) {
    const auto& d = table[i];
    const std::string at = "stage " + std::to_string(i);
    if (d.kind != order[i]) {
      out.push_back(at + ": kind out of order");
    }
    for (int c = 0; c < 2; ++c) {
      if (d.input_channel[static_cast<std::size_t>(c)] != c) {
        out.push_back(at + ": output channel " + std::to_string(c) + " reads input channel " +
                      std::to_string(d.input_channel[static_cast<std::size_t>(c)]));
      }
    }
    const bool limiter = d.kind == plan::StageKind::MasterChain;
    if (d.channel_use == plan::ChannelUse::LinkedGain && !limiter) {
      out.push_back(at + ": linked gain outside the master chain limiter");
    }
    if (d.channel_use != plan::ChannelUse::PerChannel && d.channel_use != plan::ChannelUse::LinkedGain) {
      out.push_back(at + ": unknown channel use");
    }
  }
  return out;
}

}  // namespace

TEST_CASE("stage descriptors: fixed order, per-channel, linked gain only in the limiter", "[stages][internal]") {
  const auto table = plan::stage_descriptors();
  const auto problems = descriptor_problems(table);
  for (const auto& p : problems) {
    UNSCOPED_INFO(p);
  }
  CHECK(problems.empty());
  REQUIRE(table.size() == 5);
  CHECK(static_cast<int>(table[0].kind) == ARC_STAGE_THETA_REFERENCE);
  CHECK(static_cast<int>(table[1].kind) == ARC_STAGE_GAMMA_PAC);
  CHECK(static_cast<int>(table[2].kind) == ARC_STAGE_STEREO_BUS);
  CHECK(static_cast<int>(table[3].kind) == ARC_STAGE_BINAURAL_JOIN);
  CHECK(static_cast<int>(table[4].kind) == ARC_STAGE_MASTER_CHAIN);
  CHECK(table[4].channel_use == plan::ChannelUse::LinkedGain);
  for (std::size_t i = 0; i < 4; ++i) {
    CHECK(table[i].channel_use == plan::ChannelUse::PerChannel);
  }
}

TEST_CASE("stage descriptor check catches a cross-channel map, a misplaced linked gain, and a reorder",
          "[stages][internal]") {
  const auto table = plan::stage_descriptors();
  REQUIRE(table.size() == 5);
  {
    std::vector<plan::StageDescriptor> doctored(table.begin(), table.end());
    doctored[2].input_channel = {1, 0};  // stereo bus swaps the ears
    CHECK_FALSE(descriptor_problems(doctored).empty());
  }
  {
    std::vector<plan::StageDescriptor> doctored(table.begin(), table.end());
    doctored[3].input_channel = {0, 0};  // binaural join copies left into right
    CHECK_FALSE(descriptor_problems(doctored).empty());
  }
  {
    std::vector<plan::StageDescriptor> doctored(table.begin(), table.end());
    doctored[2].channel_use = plan::ChannelUse::LinkedGain;
    CHECK_FALSE(descriptor_problems(doctored).empty());
  }
  {
    std::vector<plan::StageDescriptor> doctored(table.begin(), table.end());
    std::swap(doctored[2], doctored[3]);
    CHECK_FALSE(descriptor_problems(doctored).empty());
  }
}

#else  // plan/plan.hpp

TEST_CASE("stage descriptors: fixed order, per-channel, linked gain only in the limiter", "[stages][internal]") {
  FAIL("engine/src/plan/plan.hpp is missing (Story 1.2 stage descriptor table)");
}

#endif  // plan/plan.hpp

#ifdef ARC_ERROR_FIELD_BYTES

#include "api_helpers.hpp"
#include "spec_helpers.hpp"

#include <cstdint>
#include <cstring>
#include <utility>

namespace api = arcani::test::api;
namespace spec = arcani::test::spec;

TEST_CASE("stage list through the C API: five kinds in order", "[stages][api]") {
  for (const char* name : {api::kBeat6, api::kNoLayers}) {
    INFO(name);
    auto p = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, 48000));
    REQUIRE(arc_plan_stage_count(p.get()) == 5);
    const arc_stage_kind want[] = {ARC_STAGE_THETA_REFERENCE, ARC_STAGE_GAMMA_PAC, ARC_STAGE_STEREO_BUS,
                                   ARC_STAGE_BINAURAL_JOIN, ARC_STAGE_MASTER_CHAIN};
    for (std::size_t i = 0; i < 5; ++i) {
      arc_stage_kind kind = ARC_STAGE_MASTER_CHAIN;
      arc_error e;
      api::poison(e);
      INFO("stage " << i);
      REQUIRE(arc_plan_stage(p.get(), i, &kind, &e) == ARC_OK);
      CHECK(kind == want[i]);
    }
  }
}

TEST_CASE("spec vectors: internal block size", "[stages][spec]") {
  CHECK(spec::kBlockFrames == 64);
  for (const auto& v : spec::kBlocks) {
    CHECK(v.frame / spec::kBlockFrames == v.block);
    CHECK(v.frame % spec::kBlockFrames == v.offset);
  }
}

namespace {

struct FullRender {
  std::uint64_t frames = 0;
  std::vector<double> out;
  api::TapBuffers taps{0};
};

// Renders the whole session plus `extra` frames past its end in one call,
// with every tap.
FullRender render_session(const char* fixture, std::uint32_t fs, arc_mute_ear mute,
                          std::uint64_t extra = 64) {
  auto p = api::compile_ok(api::valid(fixture), api::options(ARC_MODE_MEASURE, fs, mute));
  FullRender f;
  f.frames = arc_plan_frame_count(p.get());
  const auto total = static_cast<std::size_t>(f.frames + extra);
  auto r = api::renderer(p.get());
  f.taps = api::TapBuffers(total);
  const arc_taps t = f.taps.taps();
  f.out = api::render(r.get(), total, &t);
  return f;
}

// True when the output and every tap at row v's sample equal its bits:
// output, master, and binaural join hold the row's output bits, the theta
// reference and stereo bus taps hold the row's theta bits in both channels,
// and the gamma PAC tap holds +0.0.
bool row_matches(const FullRender& f, const spec::StubChainVector& v) {
  const auto i = static_cast<std::size_t>(2 * v.n);
  if (f.frames != v.frames || i + 1 >= f.out.size()) {
    return false;
  }
  for (const std::vector<double>* buffer : {&f.out, &f.taps.master, &f.taps.binaural_join}) {
    if (api::bits((*buffer)[i]) != v.left_bits || api::bits((*buffer)[i + 1]) != v.right_bits) {
      return false;
    }
  }
  for (const std::vector<double>* buffer : {&f.taps.theta_reference, &f.taps.stereo_bus}) {
    if (api::bits((*buffer)[i]) != v.theta_bits || api::bits((*buffer)[i + 1]) != v.theta_bits) {
      return false;
    }
  }
  if (api::bits(f.taps.gamma_pac[i]) != 0 || api::bits(f.taps.gamma_pac[i + 1]) != 0) {
    return false;
  }
  return true;
}

// True when the two channels of an interleaved stereo buffer are equal bit
// for bit at every frame.
bool channels_equal(const std::vector<double>& stereo) {
  return api::same_bytes(api::channel(stereo, 0), api::channel(stereo, 1));
}

// Whether the spec vectors give fixture a theta reference.
bool fixture_has_theta(const char* fixture) {
  for (const auto& v : spec::kStubChain) {
    if (std::string(v.fixture) == fixture) {
      return v.has_theta;
    }
  }
  FAIL("no stub chain vector for " << fixture);
  return false;
}

}  // namespace

TEST_CASE("stub chain: output and every tap equal the spec vectors bit for bit", "[stages][spec]") {
  for (const std::uint32_t fs : {44100u, 48000u}) {
    for (const char* fixture : {api::kBeat0, api::kBeat6}) {
      INFO(fixture << " at " << fs);
      const FullRender f = render_session(fixture, fs, ARC_MUTE_NONE);
      int rows = 0;
      for (const auto& v : spec::kStubChain) {
        if (v.fs != fs || std::string(v.fixture) != fixture) {
          continue;
        }
        ++rows;
        INFO("n = " << v.n);
        CHECK(row_matches(f, v));
      }
      CHECK(rows >= 10);
      // The gamma PAC stub is +0.0; the stereo bus equals the theta tap bit
      // for bit; the theta tap is the same in both channels, and +0.0 only
      // without a theta_reference field.
      CHECK(api::all_exact_zero(f.taps.gamma_pac));
      CHECK(api::same_bytes(f.taps.stereo_bus, f.taps.theta_reference));
      CHECK(channels_equal(f.taps.theta_reference));
      if (fixture_has_theta(fixture)) {
        CHECK_FALSE(api::all_exact_zero(f.taps.theta_reference.data(), static_cast<std::size_t>(2 * f.frames)));
      } else {
        CHECK(api::all_exact_zero(f.taps.theta_reference));
      }
      // Master gain 1.0 and the identity limiter: master is the join, bit for bit.
      CHECK(api::same_bytes(f.taps.binaural_join, f.taps.master));
      CHECK(api::same_bytes(f.taps.master, f.out));
    }
  }
}

TEST_CASE("stub chain vector check catches a doctored sample", "[stages][spec]") {
  // Must-fail for the bit comparison: one flipped low bit shows.
  const FullRender f = render_session(api::kBeat6, 48000, ARC_MUTE_NONE);
  const spec::StubChainVector* row = nullptr;
  for (const auto& v : spec::kStubChain) {
    if (v.fs == 48000 && std::string(v.fixture) == api::kBeat6 && v.n == 37) {
      row = &v;
    }
  }
  REQUIRE(row != nullptr);
  const auto& v = *row;
  REQUIRE_FALSE(v.past_end);
  CHECK(row_matches(f, v));
  const auto i = static_cast<std::size_t>(2 * v.n);
  // One flipped low bit in the output, then in the join tap, then a stereo
  // bus tap that is not +0.0: each fails the comparison.
  {
    FullRender doctored = f;
    std::uint64_t b = api::bits(doctored.out[i]) ^ 1u;
    std::memcpy(&doctored.out[i], &b, sizeof b);
    CHECK_FALSE(row_matches(doctored, v));
  }
  {
    FullRender doctored = f;
    std::uint64_t b = api::bits(doctored.taps.binaural_join[i + 1]) ^ 1u;
    std::memcpy(&doctored.taps.binaural_join[i + 1], &b, sizeof b);
    CHECK_FALSE(row_matches(doctored, v));
  }
  {
    FullRender doctored = f;
    doctored.taps.stereo_bus[i] = -0.0;
    CHECK_FALSE(row_matches(doctored, v));
  }
  // A flipped low bit in the right theta tap, and a gamma tap that is not
  // +0.0, each fail too.
  {
    FullRender doctored = f;
    std::uint64_t b = api::bits(doctored.taps.theta_reference[i + 1]) ^ 1u;
    std::memcpy(&doctored.taps.theta_reference[i + 1], &b, sizeof b);
    CHECK_FALSE(row_matches(doctored, v));
  }
  {
    FullRender doctored = f;
    doctored.taps.gamma_pac[i + 1] = 0x1p-1074;
    CHECK_FALSE(row_matches(doctored, v));
  }
  // The Story 1.2 stub (theta reference at +0.0, output = binaural sine
  // alone) fails a beat-6 row: the vectors carry the theta oscillator.
  {
    REQUIRE(v.has_theta);
    FullRender doctored = f;
    for (std::vector<double>* buffer : {&doctored.out, &doctored.taps.master, &doctored.taps.binaural_join}) {
      (*buffer)[i] -= doctored.taps.theta_reference[i];
      (*buffer)[i + 1] -= doctored.taps.theta_reference[i + 1];
    }
    doctored.taps.theta_reference[i] = doctored.taps.theta_reference[i + 1] = 0.0;
    doctored.taps.stereo_bus[i] = doctored.taps.stereo_bus[i + 1] = 0.0;
    CHECK_FALSE(row_matches(doctored, v));
  }
}

TEST_CASE("theta reference: both channels equal, the bus equals it, its rows match", "[stages][spec][theta]") {
  // Theta tap of beat-6 at every vector row, both channels, both rates.
  for (const std::uint32_t fs : {44100u, 48000u}) {
    INFO(fs);
    const FullRender f = render_session(api::kBeat6, fs, ARC_MUTE_NONE);
    int rows = 0;
    for (const auto& v : spec::kStubChain) {
      if (v.fs != fs || std::string(v.fixture) != api::kBeat6) {
        continue;
      }
      ++rows;
      INFO("n = " << v.n);
      REQUIRE(v.has_theta);
      const auto i = static_cast<std::size_t>(2 * v.n);
      CHECK(api::bits(f.taps.theta_reference[i]) == v.theta_bits);
      CHECK(api::bits(f.taps.theta_reference[i + 1]) == v.theta_bits);
    }
    CHECK(rows >= 10);
    CHECK(channels_equal(f.taps.theta_reference));
    CHECK(api::same_bytes(f.taps.stereo_bus, f.taps.theta_reference));
  }
}

TEST_CASE("theta reference only: each channel of the output equals the theta tap", "[stages][theta]") {
  // theta-reference-only.json: a 200 Hz unmodulated sine, no binaural field.
  // The first 3000 frames: out, join, master, and the stereo bus equal the
  // theta tap in both channels, and the theta tap is not silent.
  auto p = api::compile_ok(api::valid("theta-reference-only.json"), api::options(ARC_MODE_MEASURE, 48000));
  constexpr std::size_t kFrames = 3000;
  REQUIRE(arc_plan_frame_count(p.get()) > kFrames);
  auto r = api::renderer(p.get());
  api::TapBuffers taps(kFrames);
  const arc_taps t = taps.taps();
  const auto out = api::render(r.get(), kFrames, &t);
  CHECK_FALSE(api::all_exact_zero(taps.theta_reference));
  CHECK(channels_equal(taps.theta_reference));
  CHECK(api::same_bytes(out, taps.theta_reference));
  CHECK(api::same_bytes(taps.binaural_join, taps.theta_reference));
  CHECK(api::same_bytes(taps.master, taps.theta_reference));
  CHECK(api::same_bytes(taps.stereo_bus, taps.theta_reference));
  CHECK(api::all_exact_zero(taps.gamma_pac));
}

TEST_CASE("muted ear: that channel equals its theta tap at every tap, the other ear is unchanged",
          "[stages][mute]") {
  // Muting affects only the binaural oscillator (signal spec, Stub chain,
  // Muted ear): the muted channel's out, join, and master equal its theta tap
  // bit for bit (+0.0 for beat-0, which has no theta reference; the 300 Hz
  // unmodulated theta sine for beat-6), and the theta tap does not change.
  for (const std::uint32_t fs : {44100u, 48000u}) {
    for (const char* fixture : {api::kBeat0, api::kBeat6}) {
      INFO(fixture << " at " << fs);
      const FullRender both = render_session(fixture, fs, ARC_MUTE_NONE);
      for (const arc_mute_ear mute : {ARC_MUTE_LEFT, ARC_MUTE_RIGHT}) {
        const int muted = mute == ARC_MUTE_LEFT ? 0 : 1;
        INFO("muted channel " << muted);
        const FullRender m = render_session(fixture, fs, mute);
        const auto theta = api::channel(m.taps.theta_reference, muted);
        CHECK(api::same_bytes(api::channel(m.out, muted), theta));
        CHECK(api::same_bytes(api::channel(m.taps.binaural_join, muted), theta));
        CHECK(api::same_bytes(api::channel(m.taps.master, muted), theta));
        CHECK(api::same_bytes(m.taps.theta_reference, both.taps.theta_reference));
        if (fixture_has_theta(fixture)) {
          CHECK_FALSE(api::all_exact_zero(theta.data(), static_cast<std::size_t>(m.frames)));
        } else {
          CHECK(api::all_exact_zero(api::channel(m.out, muted)));
        }
        CHECK(api::same_bytes(api::channel(m.out, 1 - muted), api::channel(both.out, 1 - muted)));
        CHECK(api::same_bytes(api::channel(m.taps.binaural_join, 1 - muted),
                              api::channel(both.taps.binaural_join, 1 - muted)));
      }
    }
  }
}

TEST_CASE("muted ear check catches a binaural sine left in the muted channel", "[stages][mute]") {
  // Must-fail for the muted-channel comparison: the unmuted render's channel
  // (theta plus binaural) is not its theta tap.
  const FullRender both = render_session(api::kBeat6, 48000, ARC_MUTE_NONE);
  for (const int c : {0, 1}) {
    INFO("channel " << c);
    CHECK_FALSE(api::same_bytes(api::channel(both.out, c), api::channel(both.taps.theta_reference, c)));
  }
}

TEST_CASE("no layer fields: every tap and the output are exact zeros", "[stages][mute]") {
  const FullRender f = render_session(api::kNoLayers, 48000, ARC_MUTE_NONE);
  CHECK(f.frames == 48000);
  CHECK(api::all_exact_zero(f.out));
  CHECK(api::all_exact_zero(f.taps.theta_reference));
  CHECK(api::all_exact_zero(f.taps.gamma_pac));
  CHECK(api::all_exact_zero(f.taps.stereo_bus));
  CHECK(api::all_exact_zero(f.taps.binaural_join));
  CHECK(api::all_exact_zero(f.taps.master));
}

TEST_CASE("exact-zero check catches negative zero and a tiny value", "[stages][mute]") {
  std::vector<double> x(16, 0.0);
  CHECK(api::all_exact_zero(x));
  x[3] = -0.0;
  CHECK_FALSE(api::all_exact_zero(x));
  x[3] = 0.0;
  x[9] = 0x1p-1074;
  CHECK_FALSE(api::all_exact_zero(x));
}

TEST_CASE("past the session end: output and taps are exact zeros", "[stages][end]") {
  for (const std::uint32_t fs : {44100u, 48000u}) {
    INFO(fs);
    const FullRender f = render_session(api::kBeat6, fs, ARC_MUTE_NONE, 1000);
    const auto end = static_cast<std::size_t>(2 * f.frames);
    REQUIRE(f.out.size() == end + 2000);
    CHECK(api::bits(f.out[end - 2]) != 0);  // the last session sample is not silent
    CHECK(api::bits(f.taps.theta_reference[end - 2]) != 0);  // beat-6 has a theta reference
    CHECK(api::all_exact_zero(f.out.data() + end, 2000));
    CHECK(api::all_exact_zero(f.taps.theta_reference.data() + end, 2000));
    CHECK(api::all_exact_zero(f.taps.gamma_pac.data() + end, 2000));
    CHECK(api::all_exact_zero(f.taps.stereo_bus.data() + end, 2000));
    CHECK(api::all_exact_zero(f.taps.binaural_join.data() + end, 2000));
    CHECK(api::all_exact_zero(f.taps.master.data() + end, 2000));
  }
}

TEST_CASE("taps are optional and independent; the output does not depend on them", "[stages][taps]") {
  auto p = api::compile_ok(api::valid(api::kBeat6), api::options(ARC_MODE_MEASURE, 48000));
  constexpr std::size_t kFrames = 3000;
  auto r0 = api::renderer(p.get());
  const auto plain = api::render(r0.get(), kFrames, nullptr);

  auto r1 = api::renderer(p.get());
  api::TapBuffers all(kFrames);
  const arc_taps t_all = all.taps();
  const auto with_all = api::render(r1.get(), kFrames, &t_all);
  CHECK(api::same_bytes(plain, with_all));

  auto r2 = api::renderer(p.get());
  api::TapBuffers some(kFrames);
  arc_taps t_some = some.taps();
  t_some.theta_reference = nullptr;
  t_some.stereo_bus = nullptr;
  t_some.master = nullptr;
  const auto with_some = api::render(r2.get(), kFrames, &t_some);
  CHECK(api::same_bytes(plain, with_some));
  CHECK(api::same_bytes(some.binaural_join, all.binaural_join));
  CHECK(api::same_bytes(some.gamma_pac, all.gamma_pac));
  // Unwanted taps are not written: their sentinel stays.
  for (const double x : some.theta_reference) {
    REQUIRE(x == -7.0);
  }
  for (const double x : some.master) {
    REQUIRE(x == -7.0);
  }

  auto r3 = api::renderer(p.get());
  arc_taps none;
  std::memset(&none, 0, sizeof none);
  CHECK(api::same_bytes(plain, api::render(r3.get(), kFrames, &none)));
}

TEST_CASE("render of zero frames succeeds and writes nothing", "[stages][taps]") {
  auto p = api::compile_ok(api::valid(api::kBeat6), api::options(ARC_MODE_MEASURE, 48000));
  auto r = api::renderer(p.get());
  double sentinel[2] = {-7.0, -7.0};
  arc_error e;
  api::poison(e);
  CHECK(arc_render(r.get(), sentinel, 0, nullptr, &e) == ARC_OK);
  CHECK(sentinel[0] == -7.0);
  // The next render still starts at sample 0.
  const auto out = api::render(r.get(), 2);
  CHECK(api::bits(out[0]) == 0);
  CHECK(api::bits(out[2]) != 0);
}

#else  // ARC_ERROR_FIELD_BYTES

TEST_CASE("stage list through the C API: five kinds in order", "[stages][api]") {
  FAIL("arcani/arcani.h does not declare the Story 1.2 C API yet (no ARC_ERROR_FIELD_BYTES)");
}

#endif  // ARC_ERROR_FIELD_BYTES
