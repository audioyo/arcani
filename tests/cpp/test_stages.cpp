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
        REQUIRE(f.frames == v.frames);
        const auto i = static_cast<std::size_t>(2 * v.n);
        REQUIRE(i + 1 < f.out.size());
        CHECK(api::bits(f.out[i]) == v.left_bits);
        CHECK(api::bits(f.out[i + 1]) == v.right_bits);
        CHECK(api::bits(f.taps.master[i]) == v.left_bits);
        CHECK(api::bits(f.taps.master[i + 1]) == v.right_bits);
        CHECK(api::bits(f.taps.binaural_join[i]) == v.left_bits);
        CHECK(api::bits(f.taps.binaural_join[i + 1]) == v.right_bits);
      }
      CHECK(rows >= 10);
      // Theta reference and gamma PAC stubs, and so the stereo bus, are +0.0.
      CHECK(api::all_exact_zero(f.taps.theta_reference));
      CHECK(api::all_exact_zero(f.taps.gamma_pac));
      CHECK(api::all_exact_zero(f.taps.stereo_bus));
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
  REQUIRE(api::bits(f.out[static_cast<std::size_t>(2 * v.n)]) == v.left_bits);
  std::vector<double> doctored = f.out;
  std::uint64_t b = api::bits(doctored[static_cast<std::size_t>(2 * v.n)]) ^ 1u;
  std::memcpy(&doctored[static_cast<std::size_t>(2 * v.n)], &b, sizeof b);
  CHECK(api::bits(doctored[static_cast<std::size_t>(2 * v.n)]) != v.left_bits);
}

TEST_CASE("muted ear: that channel is exact zeros at every tap, the other ear is unchanged", "[stages][mute]") {
  for (const std::uint32_t fs : {44100u, 48000u}) {
    for (const char* fixture : {api::kBeat0, api::kBeat6}) {
      INFO(fixture << " at " << fs);
      const FullRender both = render_session(fixture, fs, ARC_MUTE_NONE);
      for (const arc_mute_ear mute : {ARC_MUTE_LEFT, ARC_MUTE_RIGHT}) {
        const int muted = mute == ARC_MUTE_LEFT ? 0 : 1;
        INFO("muted channel " << muted);
        const FullRender m = render_session(fixture, fs, mute);
        CHECK(api::all_exact_zero(api::channel(m.out, muted)));
        CHECK(api::all_exact_zero(api::channel(m.taps.binaural_join, muted)));
        CHECK(api::all_exact_zero(api::channel(m.taps.master, muted)));
        CHECK(api::same_bytes(api::channel(m.out, 1 - muted), api::channel(both.out, 1 - muted)));
        CHECK(api::same_bytes(api::channel(m.taps.binaural_join, 1 - muted),
                              api::channel(both.taps.binaural_join, 1 - muted)));
      }
    }
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
    CHECK(api::all_exact_zero(f.out.data() + end, 2000));
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
