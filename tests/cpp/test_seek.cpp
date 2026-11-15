// Seek (Story 1.2; docs/signal-spec.md, Internal block size, Seek). Public
// header only.
//
// Seek to frame k, then render to the end: the samples from k onward equal
// the full render's byte for byte. k covers the start (0), inside the first
// 64-frame block (37), a block boundary (64), and a later frame (1000), plus
// the frame just before a boundary (63), a backward seek after rendering, and
// seeks at and past the session end. The output and every tap are compared.
// Story 1.5: seek also sets the theta reference phase, checked against the
// stub chain vectors.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#ifdef ARC_ERROR_FIELD_BYTES

#include "api_helpers.hpp"
#include "spec_helpers.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

namespace api = arcani::test::api;
namespace spec = arcani::test::spec;

namespace {

struct Session {
  api::PlanPtr plan;
  std::uint64_t frames = 0;
  std::vector<double> out;
  api::TapBuffers taps{0};
};

Session full(const char* fixture, std::uint32_t fs) {
  Session s;
  s.plan = api::compile_ok(api::valid(fixture), api::options(ARC_MODE_MEASURE, fs));
  s.frames = arc_plan_frame_count(s.plan.get());
  auto r = api::renderer(s.plan.get());
  s.taps = api::TapBuffers(static_cast<std::size_t>(s.frames));
  const arc_taps t = s.taps.taps();
  s.out = api::render(r.get(), static_cast<std::size_t>(s.frames), &t);
  return s;
}

bool tail_matches(const std::vector<double>& whole, std::uint64_t k, const std::vector<double>& tail) {
  const auto offset = static_cast<std::size_t>(2 * k);
  return whole.size() - offset == tail.size() && api::same_bytes(whole.data() + offset, tail.data(), tail.size());
}

}  // namespace

TEST_CASE("seek to k then render to the end equals the full render from k", "[seek]") {
  for (const std::uint32_t fs : {44100u, 48000u}) {
    for (const char* fixture : {api::kBeat0, api::kBeat6}) {
      const Session s = full(fixture, fs);
      for (const std::uint64_t k : {0ull, 37ull, 63ull, 64ull, 1000ull}) {
        INFO(fixture << " at " << fs << ", k = " << k);
        auto r = api::renderer(s.plan.get());
        api::seek(r.get(), k);
        const auto n = static_cast<std::size_t>(s.frames - k);
        api::TapBuffers taps(n);
        const arc_taps t = taps.taps();
        const auto tail = api::render(r.get(), n, &t);
        CHECK(tail_matches(s.out, k, tail));
        CHECK(tail_matches(s.taps.binaural_join, k, taps.binaural_join));
        CHECK(tail_matches(s.taps.master, k, taps.master));
        CHECK(tail_matches(s.taps.stereo_bus, k, taps.stereo_bus));
        CHECK(tail_matches(s.taps.theta_reference, k, taps.theta_reference));
        CHECK(tail_matches(s.taps.gamma_pac, k, taps.gamma_pac));
      }
    }
  }
}

TEST_CASE("seek sets the theta phase: the theta tap after a seek to k equals the vector at k", "[seek][theta]") {
  // Story 1.5: seek sets phase_T = k * inc_T mod 2^64 like the binaural
  // phases (signal spec, Stub chain, Seek). For every beat-6 vector row k,
  // a fresh renderer seeks to k and renders one frame: the theta tap holds
  // the row's theta bits in both channels and the output its output bits.
  // A theta phase left at 0 by seek fails every row past n = 0.
  for (const std::uint32_t fs : {44100u, 48000u}) {
    const Session s = full(api::kBeat6, fs);
    int rows = 0;
    for (const auto& v : spec::kStubChain) {
      if (v.fs != fs || std::string(v.fixture) != api::kBeat6) {
        continue;
      }
      ++rows;
      INFO(fs << ", k = " << v.n);
      REQUIRE(v.has_theta);
      auto r = api::renderer(s.plan.get());
      api::seek(r.get(), v.n);
      api::TapBuffers taps(1);
      const arc_taps t = taps.taps();
      const auto one = api::render(r.get(), 1, &t);
      CHECK(api::bits(taps.theta_reference[0]) == v.theta_bits);
      CHECK(api::bits(taps.theta_reference[1]) == v.theta_bits);
      CHECK(api::bits(one[0]) == v.left_bits);
      CHECK(api::bits(one[1]) == v.right_bits);
    }
    CHECK(rows >= 10);
    // The theta tap of the full render is not silent, so the tail
    // comparisons above compare a real signal.
    CHECK_FALSE(api::all_exact_zero(s.taps.theta_reference));
  }
}

TEST_CASE("seek then render in uneven chunks still equals the full render", "[seek]") {
  const Session s = full(api::kBeat6, 48000);
  auto r = api::renderer(s.plan.get());
  const std::uint64_t k = 37;
  api::seek(r.get(), k);
  std::vector<double> joined;
  std::uint64_t at = k;
  const std::size_t chunks[] = {1, 26, 64, 65, 1, 4000};
  std::size_t c = 0;
  while (at < s.frames) {
    const std::size_t n =
        static_cast<std::size_t>(std::min<std::uint64_t>(chunks[c++ % 6], s.frames - at));
    const auto part = api::render(r.get(), n);
    joined.insert(joined.end(), part.begin(), part.end());
    at += n;
  }
  CHECK(tail_matches(s.out, k, joined));
}

TEST_CASE("seek backward after rendering restarts at the seek frame", "[seek]") {
  const Session s = full(api::kBeat6, 44100);
  auto r = api::renderer(s.plan.get());
  (void)api::render(r.get(), 5000);
  api::seek(r.get(), 64);
  const auto n = static_cast<std::size_t>(s.frames - 64);
  CHECK(tail_matches(s.out, 64, api::render(r.get(), n)));
  api::seek(r.get(), 0);
  CHECK(api::same_bytes(s.out, api::render(r.get(), static_cast<std::size_t>(s.frames))));
}

TEST_CASE("seek at or past the session end renders exact zeros", "[seek]") {
  const Session s = full(api::kBeat6, 48000);
  auto r = api::renderer(s.plan.get());
  for (const std::uint64_t k : {s.frames, s.frames + 1, s.frames + 100000, std::uint64_t{1} << 40}) {
    INFO("k = " << k);
    api::seek(r.get(), k);
    CHECK(api::all_exact_zero(api::render(r.get(), 256)));
  }
  // Seek back inside the session: the signal returns.
  api::seek(r.get(), s.frames - 10);
  const auto last = api::render(r.get(), 20);
  CHECK(api::same_bytes(last.data(), s.out.data() + 2 * (s.frames - 10), 20));
  CHECK(api::all_exact_zero(last.data() + 20, 20));
}

// Story 2.5: with a beat rate cycle, seek also sets the cycle phase to
// P0 + k * inc_P (signal spec, Rate curve, Seek). binaural-cycle-sleep.json
// (a 100 Hz pure sine in the left ear and a pure sine in the right ear whose
// beat rate cycles over 0 to 3 Hz every 60 s from 0 Hz rising, 120 s) is
// sought to kSeekSeconds (55 s) and compared, chunk by chunk, with a second
// renderer that renders continuously from frame 0, so neither needs a
// whole-length buffer.

namespace {

constexpr const char* kCycleFixture = "binaural-cycle-sleep.json";

// Frames [k, end) of a renderer sought to k against the same frames of a
// continuous render from 0. Returns the number of chunks that differ in the
// output, the binaural join tap, or the master tap.
std::size_t seek_differences(const api::PlanPtr& plan, std::uint64_t k, std::uint64_t end) {
  constexpr std::size_t kChunk = 32768;
  auto continuous = api::renderer(plan.get());
  auto sought = api::renderer(plan.get());
  for (std::uint64_t at = 0; at < k;) {
    const auto n = static_cast<std::size_t>(std::min<std::uint64_t>(kChunk, k - at));
    (void)api::render(continuous.get(), n);
    at += n;
  }
  api::seek(sought.get(), k);
  std::size_t differing = 0;
  for (std::uint64_t at = k; at < end;) {
    const auto n = static_cast<std::size_t>(std::min<std::uint64_t>(kChunk, end - at));
    api::TapBuffers a(n);
    api::TapBuffers b(n);
    const arc_taps ta = a.taps();
    const arc_taps tb = b.taps();
    const auto out_a = api::render(continuous.get(), n, &ta);
    const auto out_b = api::render(sought.get(), n, &tb);
    const bool same = api::same_bytes(out_a, out_b) && api::same_bytes(a.binaural_join, b.binaural_join) &&
                      api::same_bytes(a.master, b.master);
    differing += same ? 0 : 1;
    at += n;
  }
  return differing;
}

}  // namespace

TEST_CASE("seek: the beat rate cycle fixture sought to 55 s equals the continuous render", "[seek][binaural]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO(kCycleFixture << " at " << fs);
    auto plan = api::compile_ok(api::valid(kCycleFixture), api::options(ARC_MODE_MEASURE, fs));
    const std::uint64_t frames = arc_plan_frame_count(plan.get());
    const std::uint64_t k =
        static_cast<std::uint64_t>(std::llround(spec::kSeekSeconds * static_cast<double>(fs)));
    REQUIRE(k > 0);
    REQUIRE(k < frames);
    CHECK(seek_differences(plan, k, frames + 64) == 0);
    // Other seek points: block boundaries, a quarter of the first cycle, and
    // just before the end.
    for (const std::uint64_t other : {std::uint64_t{63}, std::uint64_t{64}, std::uint64_t{15} * fs + 1,
                                      frames - 100}) {
      INFO("seek to " << other);
      CHECK(seek_differences(plan, other, std::min<std::uint64_t>(other + 3 * fs, frames + 64)) == 0);
    }
  }
}

// Story 2.6: with a theta or gamma rate cycle, seek also sets each cycle phase
// to its own P0 + k * inc_P beside the envelope accumulator k * inc_E or
// k * inc_M (signal spec, Rate curve, Seek). Each rate-curve fixture (120 s;
// recipes/fixtures/valid/, signal spec Vectors: theta and gamma rate cycles)
// is sought to kSeekSeconds (55 s) and to a few other frames, and compared
// chunk by chunk, every tap included, with a renderer that renders
// continuously from frame 0.

namespace {

const char* const kCurvedFixtures[] = {"theta-cycle-sine.json",  "theta-cycle-smoothed-on-off.json",
                                       "gamma-cycle-uncoupled.json", "swell-theta-cycle.json",
                                       "bursts-theta-cycle.json", "gamma-cycle-swell-theta-cycle.json"};

// Frames [k, end) of a renderer sought to k against a continuous render from
// 0: the number of chunks that differ in the output or in any tap.
std::size_t seek_differences_all_taps(const api::PlanPtr& plan, std::uint64_t k, std::uint64_t end) {
  constexpr std::size_t kChunk = 32768;
  auto continuous = api::renderer(plan.get());
  auto sought = api::renderer(plan.get());
  for (std::uint64_t at = 0; at < k;) {
    const auto n = static_cast<std::size_t>(std::min<std::uint64_t>(kChunk, k - at));
    (void)api::render(continuous.get(), n);
    at += n;
  }
  api::seek(sought.get(), k);
  std::size_t differing = 0;
  for (std::uint64_t at = k; at < end;) {
    const auto n = static_cast<std::size_t>(std::min<std::uint64_t>(kChunk, end - at));
    api::TapBuffers a(n);
    api::TapBuffers b(n);
    const arc_taps ta = a.taps();
    const arc_taps tb = b.taps();
    const auto out_a = api::render(continuous.get(), n, &ta);
    const auto out_b = api::render(sought.get(), n, &tb);
    const bool same = api::same_bytes(out_a, out_b) && api::same_bytes(a.theta_reference, b.theta_reference) &&
                      api::same_bytes(a.gamma_pac, b.gamma_pac) && api::same_bytes(a.stereo_bus, b.stereo_bus) &&
                      api::same_bytes(a.binaural_join, b.binaural_join) && api::same_bytes(a.master, b.master);
    differing += same ? 0 : 1;
    at += n;
  }
  return differing;
}

}  // namespace

TEST_CASE("seek: each theta and gamma rate-curve fixture sought to 55 s equals the continuous render",
          "[seek][rate-curves]") {
  for (const char* fixture : kCurvedFixtures) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(fixture << " at " << fs);
      auto plan = api::compile_ok(api::valid(fixture), api::options(ARC_MODE_MEASURE, fs));
      const std::uint64_t frames = arc_plan_frame_count(plan.get());
      const std::uint64_t k =
          static_cast<std::uint64_t>(std::llround(spec::kSeekSeconds * static_cast<double>(fs)));
      REQUIRE(k > 0);
      REQUIRE(k < frames);
      CHECK(seek_differences_all_taps(plan, k, frames + 64) == 0);
      // Other seek points: block boundaries, a quarter of the first cycle and
      // the cycle's peak rate, half a cycle, and just before the end.
      for (const std::uint64_t other : {std::uint64_t{63}, std::uint64_t{64}, std::uint64_t{15} * fs + 1,
                                        std::uint64_t{30} * fs + 37, frames - 100}) {
        INFO("seek to " << other);
        CHECK(seek_differences_all_taps(plan, other, std::min<std::uint64_t>(other + 3 * fs, frames + 64)) == 0);
      }
    }
  }
}

TEST_CASE("seek: the curved theta and gamma taps after a seek are not the unsought start", "[seek][rate-curves]") {
  // Must-fail guard for the comparison above: the theta and gamma taps from
  // 55 s differ from those from 0 s, so a seek that left the cycle phase at P0
  // would not pass by accident.
  for (const std::uint32_t fs : spec::sample_rates()) {
    auto plan = api::compile_ok(api::valid("gamma-cycle-swell-theta-cycle.json"), api::options(ARC_MODE_MEASURE, fs));
    const std::uint64_t k = static_cast<std::uint64_t>(std::llround(spec::kSeekSeconds * static_cast<double>(fs)));
    auto start = api::renderer(plan.get());
    auto sought = api::renderer(plan.get());
    api::seek(sought.get(), k);
    api::TapBuffers a(4096);
    api::TapBuffers b(4096);
    const arc_taps ta = a.taps();
    const arc_taps tb = b.taps();
    (void)api::render(start.get(), 4096, &ta);
    (void)api::render(sought.get(), 4096, &tb);
    CHECK_FALSE(api::same_bytes(a.theta_reference, b.theta_reference));
    CHECK_FALSE(api::same_bytes(a.gamma_pac, b.gamma_pac));
  }
}

// Story 2.7: a looping recipe repeats its parameter schedule, never stored
// samples, and seek stays a pure function of the frame (signal spec, Loop,
// Seek). loop-swell-theta-cycle.json (a 450 Hz carrier amplitude-modulated by
// the sine envelope at a theta rate of 4 +- 2 Hz cycling every 60 s, 75
// percent depth, and a 250 Hz sine carrier amplitude-modulated at 40 Hz with
// a smooth swell peaking at the 0 degree coupling phase, 100 percent depth;
// opening 60 s, body 120 s, 20 min) is sought into body pass 5 (from seam 5,
// O + 5 * B) and compared with a renderer that renders continuously from
// frame 0 in blocks, keeping only the compared window. Seam frames come from
// the spec vectors (kLoopFrames).

namespace {

const spec::LoopFrameVector& loop_frames(const char* fixture, std::uint32_t fs) {
  for (const auto& v : spec::kLoopFrames) {
    if (std::string(v.fixture) == fixture && v.fs == fs) {
      return v;
    }
  }
  FAIL("no loop frame vector for " << fixture << " at " << fs);
  return spec::kLoopFrames[0];
}

std::size_t loop_differing_bytes(const std::vector<double>& a, const std::vector<double>& b) {
  if (a.size() != b.size()) {
    return std::max(a.size(), b.size()) * sizeof(double);
  }
  const auto* x = reinterpret_cast<const unsigned char*>(a.data());
  const auto* y = reinterpret_cast<const unsigned char*>(b.data());
  std::size_t n = 0;
  for (std::size_t i = 0; i < a.size() * sizeof(double); ++i) {
    n += x[i] != y[i] ? 1 : 0;
  }
  return n;
}

bool slice_matches(const std::vector<double>& whole, std::size_t first_frame, const std::vector<double>& part) {
  const std::size_t at = 2 * first_frame;
  return at + part.size() <= whole.size() && api::same_bytes(whole.data() + at, part.data(), part.size());
}

}  // namespace

TEST_CASE("seek: a seek into body pass 5 of the looping swell fixture equals the continuous render",
          "[seek][loop]") {
  constexpr std::size_t kChunk = 65536;
  for (const std::uint32_t fs : spec::sample_rates()) {
    const auto& v = loop_frames(spec::kLoop_full_render_fixture, fs);
    INFO(v.fixture << " at " << fs);
    REQUIRE(v.seam_count >= 6);
    const std::uint64_t pass5 = v.seams[4];  // seam 5 starts body pass 5
    REQUIRE(pass5 == v.opening_end_frame + 5 * v.body_frames);
    auto plan = api::compile_ok(api::valid(v.fixture), api::options(ARC_MODE_MEASURE, fs));
    REQUIRE(arc_plan_frame_count(plan.get()) == v.end_frame);
    const std::uint64_t window_start = pass5 - fs / 2;
    const auto window = static_cast<std::size_t>(2 * fs);

    // Continuous from frame 0, output only, in blocks up to the window.
    auto continuous = api::renderer(plan.get());
    std::vector<double> scratch(2 * kChunk);
    for (std::uint64_t at = 0; at < window_start;) {
      const auto n = static_cast<std::size_t>(std::min<std::uint64_t>(kChunk, window_start - at));
      arc_error e;
      api::poison(e);
      const arc_status s = arc_render(continuous.get(), scratch.data(), n, nullptr, &e);
      INFO(api::describe(e));
      REQUIRE(s == ARC_OK);
      at += n;
    }
    api::TapBuffers want_taps(window);
    const arc_taps wt = want_taps.taps();
    const std::vector<double> want = api::render(continuous.get(), window, &wt);

    // Seeks: the window start, the frame before seam 5, seam 5 itself, and
    // two frames inside pass 5.
    for (const std::uint64_t k : {window_start, pass5 - 1, pass5, pass5 + 12345, pass5 + fs}) {
      INFO("seek to " << k);
      auto sought = api::renderer(plan.get());
      api::seek(sought.get(), k);
      const auto n = static_cast<std::size_t>(window_start + window - k);
      api::TapBuffers taps(n);
      const arc_taps t = taps.taps();
      const std::vector<double> got = api::render(sought.get(), n, &t);
      const auto first = static_cast<std::size_t>(k - window_start);
      CHECK(slice_matches(want, first, got));
      CHECK(slice_matches(want_taps.theta_reference, first, taps.theta_reference));
      CHECK(slice_matches(want_taps.gamma_pac, first, taps.gamma_pac));
      CHECK(slice_matches(want_taps.stereo_bus, first, taps.stereo_bus));
      CHECK(slice_matches(want_taps.binaural_join, first, taps.binaural_join));
      CHECK(slice_matches(want_taps.master, first, taps.master));
    }
  }
}

TEST_CASE("seek: a window across a seam renders the same bytes at every block size", "[seek][loop][blocks]") {
  const auto& sizes = spec::row("block-sizes");
  const double allowed = spec::row("block-size-invariance").value();
  REQUIRE_FALSE(sizes.values.empty());
  for (const std::uint32_t fs : spec::sample_rates()) {
    const auto& v = loop_frames(spec::kLoop_full_render_fixture, fs);
    REQUIRE(v.seam_count >= 1);
    auto plan = api::compile_ok(api::valid(v.fixture), api::options(ARC_MODE_MEASURE, fs));
    const std::uint64_t start = v.seams[0] - fs / 4;
    const auto frames = static_cast<std::size_t>(fs / 2);
    auto one = api::renderer(plan.get());
    api::seek(one.get(), start);
    api::TapBuffers whole_taps(frames);
    const arc_taps wt = whole_taps.taps();
    const std::vector<double> whole = api::render(one.get(), frames, &wt);
    for (const double size : sizes.values) {
      const auto block = static_cast<std::size_t>(size);
      INFO(v.fixture << " at " << fs << ", " << block << " frames per call across seam 1");
      auto r = api::renderer(plan.get());
      api::seek(r.get(), start);
      api::TapBuffers taps(frames);
      std::vector<double> out(2 * frames, -7.0);
      for (std::size_t done = 0; done < frames;) {
        const std::size_t n = std::min(block, frames - done);
        arc_taps t = taps.taps();
        const std::size_t at = 2 * done;
        t.theta_reference += at;
        t.gamma_pac += at;
        t.stereo_bus += at;
        t.binaural_join += at;
        t.master += at;
        arc_error e;
        api::poison(e);
        const arc_status s = arc_render(r.get(), out.data() + at, n, &t, &e);
        INFO(api::describe(e));
        REQUIRE(s == ARC_OK);
        done += n;
      }
      CHECK(static_cast<double>(loop_differing_bytes(out, whole)) <= allowed);
      CHECK(static_cast<double>(loop_differing_bytes(taps.theta_reference, whole_taps.theta_reference)) <= allowed);
      CHECK(static_cast<double>(loop_differing_bytes(taps.gamma_pac, whole_taps.gamma_pac)) <= allowed);
      CHECK(static_cast<double>(loop_differing_bytes(taps.stereo_bus, whole_taps.stereo_bus)) <= allowed);
      CHECK(static_cast<double>(loop_differing_bytes(taps.master, whole_taps.master)) <= allowed);
    }
  }
}

TEST_CASE("seek comparison catches a one-sample offset", "[seek]") {
  // Must-fail for tail_matches: the tail from k + 1 does not match at k.
  const Session s = full(api::kBeat6, 48000);
  auto r = api::renderer(s.plan.get());
  api::seek(r.get(), 38);
  const auto tail = api::render(r.get(), static_cast<std::size_t>(s.frames - 37));
  CHECK_FALSE(tail_matches(s.out, 37, tail));
}

#else  // ARC_ERROR_FIELD_BYTES

TEST_CASE("seek to k then render to the end equals the full render from k", "[seek]") {
  FAIL("arcani/arcani.h does not declare the Story 1.2 C API yet (no ARC_ERROR_FIELD_BYTES)");
}

#endif  // ARC_ERROR_FIELD_BYTES
