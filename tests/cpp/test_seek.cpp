// Seek (Story 1.2; docs/signal-spec.md, Internal block size, Seek). Public
// header only.
//
// Seek to frame k, then render to the end: the samples from k onward equal
// the full render's byte for byte. k covers the start (0), inside the first
// 64-frame block (37), a block boundary (64), and a later frame (1000), plus
// the frame just before a boundary (63), a backward seek after rendering, and
// seeks at and past the session end. The output and every tap are compared.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#ifdef ARC_ERROR_FIELD_BYTES

#include "api_helpers.hpp"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <vector>

namespace api = arcani::test::api;

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
