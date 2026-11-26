// Gain ramps (Story 4.4; docs/signal-spec.md, Gain ramps, and its edits to
// Stub chain, Coupling, Loop, and Loudness, Window).
//
// Contracts (spec Implementation Notes):
// - engine/src/core/gain.hpp, namespace arcani::core:
//     double gain_ramp(double a, double b, std::uint64_t k, std::uint64_t length) noexcept;
//   the engine law a + (b - a) * h, h = (1.0 - sine(ratio_to_phase(k / L) + 2^62)) * 0.5.
// - engine/src/plan/plan.hpp, namespace arcani::plan:
//     inline constexpr std::size_t kMaxGainRamps = 8;   // row gain-ramp-count
//     struct GainRamp { std::uint64_t start_frame, length_frames, end_frame; double from, to; };
//     struct GainSchedule { double initial = 1.0; std::size_t count = 0;
//                           std::array<GainRamp, kMaxGainRamps> ramps{}; };
//     double gain_at(const GainSchedule& s, std::uint64_t n) noexcept;  // 1.0 for a default schedule
// - arcani/arcani.h: arc_taps gains, after master and in this order,
//   theta_reference_gained, gamma_pac_gained, binaural (before gain),
//   binaural_gained; arc_gain_target (THETA_REFERENCE 0, GAMMA_PAC 1,
//   BINAURAL 2, MASTER 3); arc_gain_ramp { target, start_frame, end_frame,
//   from, to }; size_t arc_plan_gain_ramp_count(const arc_plan*) (0 for
//   NULL); arc_status arc_plan_gain_ramp(const arc_plan*, size_t index,
//   arc_gain_ramp* out_ramp, arc_error*) (schedule order theta, gamma,
//   binaural, master, each in array order; ARC_ERR_INVALID_ARGUMENT for a
//   NULL plan or out_ramp, or an index at or past the count).
// - cli/loudness.hpp (arcani_cli_core): struct FrameSpan { std::uint64_t
//   start, end; }; LoudnessWindow gains std::uint64_t steady_frames (without
//   a loop the longest steady stretch, set whether accepted or not; 0 with a
//   loop); LoudnessWindow loudness_window(const arc_loop_frames&, std::uint64_t
//   end_frame, std::uint64_t min_frames, std::span<const FrameSpan> ramps).
//
// Vectors from the generated spec_tables.hpp (kGain_*, kGainLaw,
// kGainFixtureRamps, kGainWindows, kGainCompileCases); rows gain-ramp-min,
// layer-gain, gain-ramp-count from the tables through the assertion call.
// The harness copy of the law (gain_helpers.hpp) runs now and must give
// every law vector bit for bit; every engine part is reached through
// __has_include or compile-time detection, so the suite builds before it
// exists and the missing parts fail as test cases.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#ifdef ARC_ERROR_FIELD_BYTES

#include "api_helpers.hpp"
#include "core/phase.hpp"
#include "gain_helpers.hpp"
#include "loudness_gain_helpers.hpp"
#include "spec_helpers.hpp"
#include "spec_tables.hpp"
#include "tables.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <span>
#include <string>
#include <vector>

#if __has_include("core/gain.hpp")
#include "core/gain.hpp"
#include "plan/plan.hpp"
#define ARCANI_TEST_HAVE_GAIN_CORE 1
#endif

#if defined(ARCANI_HAVE_CLI_CORE) && __has_include("loudness.hpp")
#include "loudness.hpp"
#define ARCANI_TEST_HAVE_CLI_LOUDNESS 1
#endif

namespace api = arcani::test::api;
namespace spec = arcani::test::spec;
namespace tables = arcani::test::tables;
namespace gain = arcani::test::gain;

namespace {

std::uint64_t bits(double x) { return api::bits(x); }

const char* const kModeNames[] = {"measure", "final"};

std::string compile_case_text(const spec::GainCompileCaseVector& v) {
  if (std::string(v.recipe) == "fixture") {
    return api::valid(v.name);
  }
  return v.recipe;
}

// N, from the windows table.
const spec::GainWindowVector& window_of(const std::string& fixture, std::uint32_t fs) {
  for (const auto& w : spec::kGainWindows) {
    if (w.fs == fs && fixture == w.fixture) {
      return w;
    }
  }
  FAIL("no gain window vector for " << fixture << " at " << fs);
  return spec::kGainWindows[0];
}

std::vector<const spec::GainFixtureRampVector*> fixture_ramps(const std::string& fixture, std::uint32_t fs) {
  std::vector<const spec::GainFixtureRampVector*> out;
  for (const auto& v : spec::kGainFixtureRamps) {
    if (v.fs == fs && fixture == v.fixture) {
      out.push_back(&v);
    }
  }
  return out;
}

// Every frame of a window of a render, all taps.
struct Window {
  std::uint64_t start = 0;
  std::size_t frames = 0;
  std::vector<double> out;
  api::TapBuffers taps{0};
};

Window render_window(arc_plan* plan, std::uint64_t start, std::size_t frames) {
  Window w;
  w.start = start;
  w.frames = frames;
  w.taps = api::TapBuffers(frames);
  auto r = api::renderer(plan);
  api::seek(r.get(), start);
  const arc_taps t = w.taps.taps();
  w.out = api::render(r.get(), frames, &t);
  return w;
}

// Per sample, the spec's Gain ramps, Per sample lines, bit for bit, with the
// harness gains of the four schedules; g the loudness gain. Returns the
// number of mismatching samples (each tap and channel counted).
std::size_t per_sample_mismatches(const Window& w, const gain::FixtureSchedules& s, double g) {
  std::size_t bad = 0;
  const auto& t = w.taps;
  for (std::size_t i = 0; i < w.frames; ++i) {
    const std::uint64_t n = w.start + i;
    const double gT = gain::harness_gain_at(s.s[0], n);
    const double gG = gain::harness_gain_at(s.s[1], n);
    const double gB = gain::harness_gain_at(s.s[2], n);
    const double gM = gain::harness_gain_at(s.s[3], n);
    for (std::size_t c = 0; c < 2; ++c) {
      const std::size_t k = 2 * i + c;
      bad += bits(t.theta_gained[k]) != bits(t.theta_reference[k] * gT);
      bad += bits(t.gamma_gained[k]) != bits(t.gamma_pac[k] * gG);
      bad += bits(t.stereo_bus[k]) != bits(t.theta_gained[k] + t.gamma_gained[k]);
      bad += bits(t.binaural_gained[k]) != bits(t.binaural[k] * gB);
      bad += bits(t.binaural_join[k]) != bits(t.stereo_bus[k] + t.binaural_gained[k]);
      bad += bits(t.master[k]) != bits((t.binaural_join[k] * g) * gM);
      bad += bits(w.out[k]) != bits(t.master[k]);
    }
  }
  return bad;
}

// The window starts of the hash probe: 1 s around every ramp edge.
std::vector<std::uint64_t> probe_starts(const spec::GainWindowVector& v) {
  return std::vector<std::uint64_t>(v.probe_starts, v.probe_starts + v.probe_count);
}

void require_gain_taps() {
  if (!gain::kHaveGainTaps) {
    FAIL(gain::kNoGainTaps);
  }
}

void require_gain_ramp_api() {
  if (!gain::kHaveGainRampApi) {
    FAIL(gain::kNoGainRampApi);
  }
}

// Out argument that converts to a NULL pointer of the declared type.
struct NullSink {
  template <class R>
  operator R*() const {
    return nullptr;
  }
};

template <class P>
int ramp_status_with_null_out(const P* plan, arc_error* e) {
  if constexpr (gain::HasGainRampApi<P>) {
    return static_cast<int>(arc_plan_gain_ramp(plan, std::size_t{0}, NullSink{}, e));
  } else {
    (void)plan;
    (void)e;
    return -1;
  }
}

template <class P>
concept HasExactRampSignatures = requires(const P* p, gain::RampSink& sink, arc_error* e) {
  { arc_plan_gain_ramp_count(p) } -> std::same_as<std::size_t>;
  { arc_plan_gain_ramp(p, std::size_t{0}, sink, e) } -> std::same_as<arc_status>;
};

// Tap order in arc_taps: the four Story 4.4 taps after master, in order.
template <class T>
std::vector<std::ptrdiff_t> tap_offsets() {
  if constexpr (gain::HasGainTaps<T>) {
    T t{};
    const auto at = [&](const void* p) { return static_cast<const char*>(p) - reinterpret_cast<const char*>(&t); };
    return {at(&t.theta_reference), at(&t.gamma_pac), at(&t.stereo_bus), at(&t.binaural_join), at(&t.master),
            at(&t.theta_reference_gained), at(&t.gamma_pac_gained), at(&t.binaural), at(&t.binaural_gained)};
  } else {
    return {};
  }
}

}  // namespace

// ------------------------------------------------------------ rows and vectors (run now)

TEST_CASE("gain ramps: the three rows agree with the vector constants", "[gain-ramps][rows]") {
  const tables::Row& ramp_min = tables::row(spec::kGain_ramp_min_row);
  CHECK(ramp_min.kind == "thresholds");
  CHECK(ramp_min.unit == "ms");
  CHECK(ramp_min.value() == spec::kGain_ramp_min_ms);
  CHECK(bits(ramp_min.value() / 1000.0) == bits(spec::kGain_ramp_min_s));
  CHECK(spec::unit_to_seconds(ramp_min.value(), ramp_min.unit) == spec::kGain_ramp_min_s);

  const tables::Row& layer = tables::row(spec::kGain_layer_gain_row);
  CHECK(layer.kind == "ranges");
  CHECK(layer.unit == spec::kGain_layer_gain_unit);
  CHECK(layer.min == spec::kGain_layer_gain_min);
  CHECK(layer.max == spec::kGain_layer_gain_max);
  CHECK(layer.max_bound == "inclusive");

  const tables::Row& count = tables::row(spec::kGain_ramp_count_row);
  CHECK(count.kind == "ranges");
  CHECK(count.unit == spec::kGain_ramp_count_unit);
  CHECK(count.min == 0.0);
  CHECK(count.max == static_cast<double>(spec::kGain_ramp_count_max));
  CHECK(count.max_bound == "inclusive");
}

TEST_CASE("gain ramps: the harness law gives every law vector bit for bit", "[gain-ramps][law]") {
  REQUIRE(std::size(spec::kGainLaw) > 0);
  for (const auto& v : spec::kGainLaw) {
    INFO(v.a << " to " << v.b << ", L " << v.length << ", k " << v.k);
    const double r = static_cast<double>(v.k) / static_cast<double>(v.length);
    CHECK(bits(r) == bits(v.r));
    CHECK(arcani::core::ratio_to_phase(r) == v.p);
    CHECK(bits(arcani::core::sine(v.p + (UINT64_C(1) << 62))) == v.c_bits);
    CHECK(bits((1.0 - arcani::core::sine(v.p + (UINT64_C(1) << 62))) * 0.5) == bits(v.h));
    CHECK(bits(gain::harness_ramp(v.a, v.b, v.k, v.length)) == v.g_bits);
    CHECK(bits(v.g) == v.g_bits);
    if (v.k == 0) {
      CHECK(v.c_bits == spec::kGain_start_cosine_bits);
    }
    // The ideal ramp is within 2^-50 + the engine sine bound of the engine ramp.
    CHECK(std::fabs(v.g - v.ideal) < 1e-7);
  }
}

TEST_CASE("gain ramps: must-fail, the ideal cosine at k = 0 is not the engine gain", "[gain-ramps][law][mustfail]") {
  for (const auto& v : spec::kGainLaw) {
    if (v.k != 0 || v.a == v.b) {
      continue;
    }
    INFO(v.a << " to " << v.b << ", L " << v.length);
    // The ideal ramp is a at k = 0; the engine is a + (b - a) * 2.8e-8.
    CHECK(bits(v.ideal) != v.g_bits);
    CHECK(bits(v.a) != bits(gain::harness_ramp(v.a, v.b, 0, v.length)));
  }
}

TEST_CASE("gain ramps: fixture ramp frames follow the seconds-to-samples rule", "[gain-ramps][frames]") {
  REQUIRE(std::size(spec::kGainFixtureRamps) > 0);
  for (const auto& v : spec::kGainFixtureRamps) {
    INFO(v.fixture << " at " << v.fs << ", " << v.schedule << " ramp " << v.ramp);
    CHECK(gain::schedule_index(v.schedule) >= 0);
    CHECK(arcani::core::seconds_to_samples(v.start_s, v.fs) == v.start_frame);
    CHECK(arcani::core::seconds_to_samples(v.duration_s, v.fs) == v.length_frames);
    CHECK(v.start_frame + v.length_frames == v.end_frame);
    CHECK(v.end_frame <= window_of(v.fixture, v.fs).end_frame);
  }
  // A 10 ms ramp is 441 frames at 44.1 kHz and 480 at 48 kHz.
  CHECK(arcani::core::seconds_to_samples(spec::kGain_ramp_min_s, 44100) == 441u);
  CHECK(arcani::core::seconds_to_samples(spec::kGain_ramp_min_s, 48000) == 480u);
}

TEST_CASE("gain ramps: probe window starts follow the spec rule", "[gain-ramps][probe]") {
  for (const auto& w : spec::kGainWindows) {
    INFO(w.fixture << " at " << w.fs);
    const std::uint64_t len = arcani::core::seconds_to_samples(spec::kGain_probe_window_s, w.fs);
    const std::uint64_t half = arcani::core::seconds_to_samples(spec::kGain_probe_half_s, w.fs);
    CHECK(w.probe_window_frames == len);
    std::vector<std::uint64_t> want;
    for (const auto* r : fixture_ramps(w.fixture, w.fs)) {
      for (const std::uint64_t edge : {r->start_frame, r->end_frame}) {
        const std::uint64_t a = edge >= half ? edge - half : 0;
        want.push_back(std::min(a, w.end_frame - len));
      }
    }
    CHECK(probe_starts(w) == want);
  }
}

// ------------------------------------------------------------ core and plan

#ifdef ARCANI_TEST_HAVE_GAIN_CORE

namespace plan = arcani::plan;

namespace {

plan::GainSchedule schedule_of(const gain::HarnessSchedule& h) {
  plan::GainSchedule s;
  s.initial = h.initial;
  s.count = h.ramps.size();
  REQUIRE(s.count <= plan::kMaxGainRamps);
  for (std::size_t i = 0; i < h.ramps.size(); ++i) {
    s.ramps[i] = plan::GainRamp{h.ramps[i].n0, h.ramps[i].length, h.ramps[i].n1, h.ramps[i].a, h.ramps[i].b};
  }
  return s;
}

}  // namespace

TEST_CASE("core::gain_ramp: every law vector bit for bit", "[gain-ramps][law][internal]") {
  for (const auto& v : spec::kGainLaw) {
    INFO(v.a << " to " << v.b << ", L " << v.length << ", k " << v.k);
    CHECK(bits(arcani::core::gain_ramp(v.a, v.b, v.k, v.length)) == v.g_bits);
  }
}

TEST_CASE("plan::gain_at: every fixture ramp at its edges and after; ends held exactly", "[gain-ramps][internal]") {
  CHECK(plan::kMaxGainRamps == static_cast<std::size_t>(tables::row(spec::kGain_ramp_count_row).max));
  CHECK(bits(plan::gain_at(plan::GainSchedule{}, 0)) == bits(1.0));
  CHECK(bits(plan::gain_at(plan::GainSchedule{}, UINT64_C(123456789))) == bits(1.0));
  for (const char* fixture : spec::kGain_render_fixtures) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      const gain::FixtureSchedules all = gain::fixture_schedules(fixture, fs);
      const std::uint64_t end = window_of(fixture, fs).end_frame;
      for (int i = 0; i < 4; ++i) {
        const gain::HarnessSchedule& h = all.s[i];
        if (!h.present) {
          continue;
        }
        const plan::GainSchedule s = schedule_of(h);
        for (const auto& r : h.ramps) {
          std::vector<std::uint64_t> at = {r.n0, r.n0 + 1, r.n0 + r.length / 2, r.n1 - 1, r.n1, r.n1 + 1, end - 1};
          if (r.n0 > 0) {
            at.push_back(r.n0 - 1);
          }
          for (const std::uint64_t n : at) {
            INFO(fixture << " at " << fs << ", " << spec::kGain_schedules[i] << ", n " << n);
            CHECK(bits(plan::gain_at(s, n)) == bits(gain::harness_gain_at(h, n)));
          }
          CHECK(bits(plan::gain_at(s, r.n1)) == bits(r.b));
          CHECK(bits(plan::gain_at(s, end - 1)) == bits(h.ramps.back().b));
          if (r.n0 > 0) {
            CHECK(bits(plan::gain_at(s, r.n0 - 1)) == bits(r.a));
          }
        }
      }
    }
  }
}

TEST_CASE("plan::gain_at: holds between ramps, adjacent ramps, must-fail doctored end", "[gain-ramps][internal][mustfail]") {
  gain::HarnessSchedule h;
  h.present = true;
  h.initial = 1.0;
  h.ramps = {{1000, 441, 1441, 1.0, 0.5}, {1441, 480, 1921, 0.5, 0.25}, {5000, 441, 5441, 0.25, 0.0}};
  const plan::GainSchedule s = schedule_of(h);
  for (const std::uint64_t n : {0u, 999u, 1000u, 1440u, 1441u, 1920u, 1921u, 4999u, 5000u, 5440u, 5441u, 90000u}) {
    INFO("n " << n);
    CHECK(bits(plan::gain_at(s, n)) == bits(gain::harness_gain_at(h, n)));
  }
  CHECK(bits(plan::gain_at(s, 3000)) == bits(0.25));
  CHECK(bits(plan::gain_at(s, 90000)) == bits(0.0));
  // Must-fail: a harness that holds one ulp off the end value disagrees.
  gain::HarnessSchedule doctored = h;
  doctored.ramps[1].b = std::nextafter(0.25, 1.0);
  doctored.ramps[2].a = doctored.ramps[1].b;
  CHECK(bits(plan::gain_at(s, 3000)) != bits(gain::harness_gain_at(doctored, 3000)));
}

#else

TEST_CASE("core::gain_ramp and plan::gain_at are implemented", "[gain-ramps][internal]") {
  FAIL("not implemented: engine/src/core/gain.hpp (core::gain_ramp) and plan::GainSchedule, plan::gain_at (Story 4.4)");
}

#endif  // ARCANI_TEST_HAVE_GAIN_CORE

// ------------------------------------------------------------ compile

TEST_CASE("gain compile cases: every case at both rates in both modes, accepted or the exact four texts",
          "[gain-ramps][compile]") {
  REQUIRE(std::size(spec::kGainCompileCases) > 0);
  std::size_t accepted = 0;
  std::size_t rejected = 0;
  for (const auto& v : spec::kGainCompileCases) {
    const std::string text = compile_case_text(v);
    for (const std::uint32_t fs : spec::sample_rates()) {
      for (const arc_mode mode : {ARC_MODE_MEASURE, ARC_MODE_FINAL}) {
        INFO(v.name << " at " << fs << ", " << kModeNames[mode]);
        const api::Compiled c = api::compile(text, api::options(mode, fs));
        INFO(api::describe(c.error));
        if (v.accepted) {
          if (mode == ARC_MODE_MEASURE) {
            CHECK(c.status == ARC_OK);
          } else {
            // Every gain rule passes; final mode then needs the stored gain.
            CHECK(c.status == ARC_ERR_REJECTED);
            CHECK(std::string(c.error.rule) == "final.required");
            CHECK(std::string(c.error.parameter) == "/loudness_gain_db");
          }
        } else {
          CHECK(c.status == ARC_ERR_REJECTED);
          REQUIRE(api::all_written(c.error));
          CHECK(std::string(c.error.parameter) == v.parameter);
          CHECK(std::string(c.error.value) == v.value);
          CHECK(std::string(c.error.rule) == v.rule);
          CHECK(std::string(c.error.limit) == v.limit);
        }
      }
    }
    (v.accepted ? accepted : rejected) += 1;
  }
  CHECK(accepted > 0);
  CHECK(rejected > 0);
}

TEST_CASE("gain compile cases: the limit texts use the rows and the rule constants", "[gain-ramps][compile]") {
  const tables::Row& ramp_min = tables::row(spec::kGain_ramp_min_row);
  CHECK(std::string(spec::kGain_ramp_min_limit) ==
        ">= " + ramp_min.value_text + " " + ramp_min.unit + " (row " + ramp_min.id + ")");
  const tables::Row& count = tables::row(spec::kGain_ramp_count_row);
  for (const auto& v : spec::kGainCompileCases) {
    if (v.accepted) {
      continue;
    }
    INFO(v.name);
    const std::string rule = v.rule;
    if (rule == spec::kGain_ramp_min_rule) {
      CHECK(std::string(v.limit) == spec::kGain_ramp_min_limit);
    } else if (rule == spec::kGain_theta_silent_rule) {
      CHECK(std::string(v.limit) == spec::kGain_theta_silent_limit);
      CHECK(std::string(v.parameter) == "/gamma_pac/coupling");
    } else if (rule == "range.max" && std::string(v.parameter).find("/ramps") + 6 == std::string(v.parameter).size()) {
      CHECK(std::string(v.limit) == "<= " + count.max_text + " " + count.unit + " (row " + count.id + ")");
    }
  }
}

// ------------------------------------------------------------ the C API: ramps

TEST_CASE("arc_plan_gain_ramp: the exact declarations", "[gain-ramps][api]") {
  require_gain_ramp_api();
  CHECK(HasExactRampSignatures<arc_plan>);
}

TEST_CASE("arc_plan_gain_ramp: every fixture's ramps equal the fixture ramp vectors, both rates and modes",
          "[gain-ramps][api]") {
  require_gain_ramp_api();
  for (const char* fixture : spec::kGain_render_fixtures) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO(fixture << " at " << fs);
      auto p = api::compile_ok(api::valid(fixture), api::options(ARC_MODE_MEASURE, fs));
      const auto want = fixture_ramps(fixture, fs);
      const auto count = gain::ramp_count(p.get());
      REQUIRE(count.has_value());
      CHECK(*count == want.size());
      for (std::size_t i = 0; i < want.size() && i < *count; ++i) {
        INFO("ramp " << i);
        arc_error e;
        api::poison(e);
        const gain::RampCall c = gain::ramp_at(p.get(), i, &e);
        CHECK(c.status == ARC_OK);
        CHECK(c.ramp.target == gain::schedule_index(want[i]->schedule));
        CHECK(c.ramp.start_frame == want[i]->start_frame);
        CHECK(c.ramp.end_frame == want[i]->end_frame);
        CHECK(bits(c.ramp.from) == bits(want[i]->from));
        CHECK(bits(c.ramp.to) == bits(want[i]->to));
      }
      // An index at the count is an invalid argument, with all four fields.
      arc_error e;
      api::poison(e);
      const gain::RampCall past = gain::ramp_at(p.get(), want.size(), &e);
      CHECK(past.status == ARC_ERR_INVALID_ARGUMENT);
      CHECK(api::all_written(e));
      api::poison(e);
      CHECK(ramp_status_with_null_out(p.get(), &e) == ARC_ERR_INVALID_ARGUMENT);
      CHECK(api::all_written(e));
    }
  }
  // A recipe without any gain member has no ramp; a NULL plan counts 0.
  auto plain = api::compile_ok(api::valid(api::kBeat6), api::options(ARC_MODE_MEASURE, 48000));
  CHECK(gain::ramp_count(plain.get()) == std::optional<std::size_t>(0));
  CHECK(gain::ramp_count(static_cast<const arc_plan*>(nullptr)) == std::optional<std::size_t>(0));
  arc_error e;
  api::poison(e);
  CHECK(gain::ramp_at(static_cast<const arc_plan*>(nullptr), 0, &e).status == ARC_ERR_INVALID_ARGUMENT);
  CHECK(api::all_written(e));
}

TEST_CASE("arc_plan_gain_ramp: schedule order and array order on a harness recipe", "[gain-ramps][api]") {
  require_gain_ramp_api();
  // The eight ramps case on binaural, plus theta, gamma, and master
  // schedules: theta first, then gamma, binaural in array order, master last.
  std::string text;
  for (const auto& v : spec::kGainCompileCases) {
    if (std::string(v.name) == "eight ramps") {
      text = v.recipe;
    }
  }
  REQUIRE_FALSE(text.empty());
  const std::string theta_at = "\"shape\":\"sine\"";
  const std::string gamma_at = "\"coupling_phase_deg\":0";
  REQUIRE(text.find(theta_at) != std::string::npos);
  REQUIRE(text.find(gamma_at) != std::string::npos);
  text.insert(text.find(theta_at) + theta_at.size(),
              ",\"gain\":{\"initial\":1,\"ramps\":[{\"start_s\":500,\"duration_s\":2,\"to\":0.75}]}");
  text.insert(text.find(gamma_at) + gamma_at.size(),
              ",\"gain\":{\"initial\":1,\"ramps\":[{\"start_s\":400,\"duration_s\":3,\"to\":0.5}]}");
  text.insert(text.size() - 1, ",\"master\":{\"gain\":{\"initial\":0.5,\"ramps\":[{\"start_s\":300,\"duration_s\":4,"
                               "\"to\":0.25}]}}");
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO(fs << "\n" << text);
    auto p = api::compile_ok(text, api::options(ARC_MODE_MEASURE, fs));
    REQUIRE(gain::ramp_count(p.get()) == std::optional<std::size_t>(11));
    std::vector<int> targets;
    std::vector<std::uint64_t> starts;
    for (std::size_t i = 0; i < 11; ++i) {
      arc_error e;
      const gain::RampCall c = gain::ramp_at(p.get(), i, &e);
      REQUIRE(c.status == ARC_OK);
      targets.push_back(c.ramp.target);
      starts.push_back(c.ramp.start_frame);
    }
    CHECK(targets == std::vector<int>{0, 1, 2, 2, 2, 2, 2, 2, 2, 2, 3});
    const auto s = [&](double t) { return arcani::core::seconds_to_samples(t, fs); };
    CHECK(starts == std::vector<std::uint64_t>{s(500), s(400), s(10), s(20), s(30), s(40), s(50), s(60), s(70),
                                               s(80), s(300)});
    arc_error e;
    const gain::RampCall master = gain::ramp_at(p.get(), 10, &e);
    CHECK(bits(master.ramp.from) == bits(0.5));
    CHECK(bits(master.ramp.to) == bits(0.25));
    CHECK(master.ramp.end_frame == s(300) + s(4));
  }
}

// ------------------------------------------------------------ the C API: taps and renders

TEST_CASE("arc_taps: the four Story 4.4 taps follow master in order", "[gain-ramps][api][taps]") {
  require_gain_taps();
  const auto off = tap_offsets<arc_taps>();
  REQUIRE(off.size() == 9);
  for (std::size_t i = 1; i < off.size(); ++i) {
    CHECK(off[i] == off[i - 1] + static_cast<std::ptrdiff_t>(sizeof(double*)));
  }
  CHECK(sizeof(arc_taps) == 9 * sizeof(double*));
}

TEST_CASE("unity schedule: the output equals the render without gain; every after-gain tap equals its partner",
          "[gain-ramps][api][taps]") {
  require_gain_taps();
  std::string unity;
  for (const auto& v : spec::kGainCompileCases) {
    if (std::string(v.name) == "unity schedule") {
      unity = v.recipe;
    }
  }
  REQUIRE_FALSE(unity.empty());
  const std::string member = ",\"gain\":{\"initial\":1}";
  std::string plain = unity;
  REQUIRE(plain.find(member) != std::string::npos);
  plain.erase(plain.find(member), member.size());
  // Also unity on every schedule, with an empty ramps array.
  std::string all = plain;
  all.insert(all.find("\"shape\":\"sine\"") + 14, ",\"gain\":{\"initial\":1,\"ramps\":[]}");
  all.insert(all.find("\"coupling_phase_deg\":0") + 22, ",\"gain\":{\"initial\":1}");
  all.insert(all.find("\"beat_rate_hz\":2") + 16, ",\"gain\":{\"initial\":1}");
  all.insert(all.size() - 1, ",\"master\":{\"gain\":{\"initial\":1}}");
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO(fs);
    auto p0 = api::compile_ok(plain, api::options(ARC_MODE_MEASURE, fs));
    const Window w0 = render_window(p0.get(), 0, fs);
    for (const std::string* text : {&unity, &all}) {
      INFO(*text);
      auto p = api::compile_ok(*text, api::options(ARC_MODE_MEASURE, fs));
      const Window w = render_window(p.get(), 0, fs);
      CHECK(api::same_bytes(w.out, w0.out));
      CHECK(api::same_bytes(w.taps.theta_gained, w.taps.theta_reference));
      CHECK(api::same_bytes(w.taps.gamma_gained, w.taps.gamma_pac));
      CHECK(api::same_bytes(w.taps.binaural_gained, w.taps.binaural));
      CHECK(api::same_bytes(w.taps.master, w.taps.binaural_join));
      CHECK(api::same_bytes(w.taps.theta_reference, w0.taps.theta_reference));
      CHECK(api::same_bytes(w.taps.binaural_join, w0.taps.binaural_join));
      CHECK_FALSE(api::all_exact_zero(w.taps.binaural));
    }
  }
}

TEST_CASE("gain fixtures: every tap follows the Per sample lines around every ramp edge, both rates",
          "[gain-ramps][api][taps]") {
  require_gain_taps();
  for (const char* fixture : spec::kGain_render_fixtures) {
    for (const std::uint32_t fs : spec::sample_rates()) {
      const spec::GainWindowVector& v = window_of(fixture, fs);
      const gain::FixtureSchedules s = gain::fixture_schedules(fixture, fs);
      auto p = api::compile_ok(api::valid(fixture), api::options(ARC_MODE_MEASURE, fs));
      REQUIRE(arc_plan_frame_count(p.get()) == v.end_frame);
      for (const std::uint64_t start : probe_starts(v)) {
        INFO(fixture << " at " << fs << ", window from " << start);
        const Window w = render_window(p.get(), start, static_cast<std::size_t>(v.probe_window_frames));
        CHECK(per_sample_mismatches(w, s, 1.0) == 0);
        // Must-fail: the same lines with a unity master or unity layer gains.
        gain::FixtureSchedules unity;
        bool ramping = false;
        for (int i = 0; i < 4; ++i) {
          for (const auto& r : s.s[i].ramps) {
            ramping = ramping || (start < r.n1 && r.n0 < start + v.probe_window_frames);
          }
        }
        if (ramping) {
          CHECK(per_sample_mismatches(w, unity, 1.0) > 0);
        }
      }
    }
  }
}

TEST_CASE("gain fixtures: final mode applies the loudness gain before the master gain", "[gain-ramps][api][taps]") {
  require_gain_taps();
  // gain-master-fade.json with a stored -10.00 dB gain and the engine's
  // loudness hash for it (loudness_gain_helpers.hpp).
  std::string text = api::valid(spec::kGain_fade_fixture);
  const std::string at = "\"loudness_target_lufs\": -36,\n";
  REQUIRE(text.find(at) != std::string::npos);
  text.insert(text.find(at) + at.size(), std::string("  \"loudness_gain_db\": -10.00,\n  \"loudness_hash\": \"") +
                                             arcani::test::loudness::kPlaceholderHash + "\",\n");
  text = arcani::test::loudness::stored_hash_text(text);
  const double g = arcani::test::loudness::harness_linear_gain(-1000, spec::kLoudnessGain_c);
  for (const std::uint32_t fs : spec::sample_rates()) {
    const spec::GainWindowVector& v = window_of(spec::kGain_fade_fixture, fs);
    const gain::FixtureSchedules s = gain::fixture_schedules(spec::kGain_fade_fixture, fs);
    auto p = api::compile_ok(text, api::options(ARC_MODE_FINAL, fs));
    for (const std::uint64_t start : probe_starts(v)) {
      INFO("fs " << fs << ", window from " << start);
      const Window w = render_window(p.get(), start, static_cast<std::size_t>(v.probe_window_frames));
      CHECK(per_sample_mismatches(w, s, g) == 0);
      // Must-fail: the gains multiplied in the other order, join * (g * gM).
      std::size_t other = 0;
      std::size_t live = 0;
      for (std::size_t i = 0; i < w.frames; ++i) {
        const double gM = gain::harness_gain_at(s.s[3], start + i);
        for (std::size_t c = 0; c < 2; ++c) {
          const double j = w.taps.binaural_join[2 * i + c];
          live += (j * g) * gM != 0.0;
          other += bits(w.taps.master[2 * i + c]) != bits(j * (g * gM));
        }
      }
      if (gain::harness_gain_at(s.s[3], start) != 1.0 && live > 0) {
        CHECK(other > 0);
      }
    }
  }
}

TEST_CASE("gain-master-fade.json: the output is exact zeros from the master fade's end frame",
          "[gain-ramps][api][fade]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO(fs);
    const spec::GainWindowVector& v = window_of(spec::kGain_fade_fixture, fs);
    const gain::FixtureSchedules s = gain::fixture_schedules(spec::kGain_fade_fixture, fs);
    REQUIRE(s.s[3].present);
    const std::uint64_t n1 = s.s[3].ramps.back().n1;
    REQUIRE(bits(s.s[3].ramps.back().b) == bits(0.0));
    auto p = api::compile_ok(api::valid(spec::kGain_fade_fixture), api::options(ARC_MODE_MEASURE, fs));
    const std::uint64_t before = 4096;
    auto r = api::renderer(p.get());
    api::seek(r.get(), n1 - before);
    const auto out = api::render(r.get(), static_cast<std::size_t>(v.end_frame - (n1 - before)));
    std::size_t live = 0;
    for (std::size_t i = 0; i < 2 * before; ++i) {
      live += out[i] != 0.0;
    }
    CHECK(live > 0);
    std::size_t nonzero = 0;
    for (std::size_t i = 2 * before; i < out.size(); ++i) {
      nonzero += out[i] != 0.0;  // +0.0 or -0.0: both quantize to 24-bit 0
    }
    CHECK(nonzero == 0);
    // Must-fail: one denormal past n1 is caught.
    std::vector<double> doctored(out.begin() + static_cast<std::ptrdiff_t>(2 * before), out.end());
    doctored[doctored.size() / 2] = 0x1p-1074;
    CHECK(std::count_if(doctored.begin(), doctored.end(), [](double x) { return x != 0.0; }) == 1);
  }
}

TEST_CASE("gain fixtures: a seek into a ramp renders the continuous render's samples", "[gain-ramps][api][seek]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO(fs);
    auto p = api::compile_ok(api::valid(spec::kGain_fade_fixture), api::options(ARC_MODE_MEASURE, fs));
    const gain::FixtureSchedules s = gain::fixture_schedules(spec::kGain_fade_fixture, fs);
    REQUIRE(s.s[2].present);
    REQUIRE(s.s[3].present);
    // The 10 ms binaural ramp from frame 0: one render from 0, against a seek
    // to its middle.
    {
      auto r0 = api::renderer(p.get());
      const auto whole = api::render(r0.get(), 2000);
      const std::uint64_t k = s.s[2].ramps[0].length / 2 + 7;
      auto r1 = api::renderer(p.get());
      api::seek(r1.get(), k);
      const auto part = api::render(r1.get(), static_cast<std::size_t>(2000 - k));
      CHECK(api::same_bytes(part.data(), whole.data() + 2 * k, part.size()));
    }
    // The 5 min master fade: a window from before its start, in one call and
    // in two, against a seek inside it.
    {
      const std::uint64_t n0 = s.s[3].ramps[0].n0;
      auto r0 = api::renderer(p.get());
      api::seek(r0.get(), n0 - 3000);
      const auto one = api::render(r0.get(), 9000);
      auto r1 = api::renderer(p.get());
      api::seek(r1.get(), n0 - 3000);
      auto two = api::render(r1.get(), 3333);
      const auto rest = api::render(r1.get(), 9000 - 3333);
      two.insert(two.end(), rest.begin(), rest.end());
      CHECK(api::same_bytes(one, two));
      auto r2 = api::renderer(p.get());
      api::seek(r2.get(), n0 + 1500);
      const auto inside = api::render(r2.get(), 4500);
      CHECK(api::same_bytes(inside.data(), one.data() + 2 * 4500, inside.size()));
    }
  }
}

TEST_CASE("gain fixtures: a muted ear is +0.0 before and after the binaural gain", "[gain-ramps][api][mute]") {
  require_gain_taps();
  for (const std::uint32_t fs : spec::sample_rates()) {
    for (const arc_mute_ear mute : {ARC_MUTE_LEFT, ARC_MUTE_RIGHT}) {
      const std::size_t muted = mute == ARC_MUTE_LEFT ? 0 : 1;
      INFO(fs << ", muted channel " << muted);
      auto p = api::compile_ok(api::valid(spec::kGain_fade_fixture), api::options(ARC_MODE_MEASURE, fs, mute));
      const Window w = render_window(p.get(), 0, 2000);
      std::size_t bad = 0;
      std::size_t other = 0;
      for (std::size_t i = 0; i < w.frames; ++i) {
        bad += bits(w.taps.binaural[2 * i + muted]) != 0;
        bad += bits(w.taps.binaural_gained[2 * i + muted]) != 0;
        other += w.taps.binaural[2 * i + (1 - muted)] != 0.0;
      }
      CHECK(bad == 0);
      CHECK(other > 0);
    }
  }
}

// ------------------------------------------------------------ the command-line window

#ifdef ARCANI_TEST_HAVE_CLI_LOUDNESS

namespace gain_window_fallback {
struct FrameSpan {
  int missing = 0;
};
}  // namespace gain_window_fallback

namespace arcani::cli_gain_probe {
using namespace ::gain_window_fallback;
using namespace arcani::cli;
using FrameSpanType = FrameSpan;
inline constexpr bool kFrameSpanDeclared =
    !std::is_same_v<FrameSpanType, ::gain_window_fallback::FrameSpan>;
}  // namespace arcani::cli_gain_probe

namespace {

namespace cli = arcani::cli;
using Span = arcani::cli_gain_probe::FrameSpanType;

template <class S, class W>
concept HasRampWindow = requires(const arc_loop_frames& loop, std::span<const S> ramps, S s, W w) {
  { cli::loudness_window(loop, std::uint64_t{0}, std::uint64_t{0}, ramps) } -> std::same_as<cli::LoudnessWindow>;
  { w.steady_frames } -> std::convertible_to<std::uint64_t>;
  s.start = std::uint64_t{0};
  s.end = std::uint64_t{0};
};

inline constexpr bool kHaveRampWindow =
    arcani::cli_gain_probe::kFrameSpanDeclared && HasRampWindow<Span, cli::LoudnessWindow>;

struct WindowRead {
  bool accepted = false;
  std::uint64_t start = 0, body = 0, repeats = 0, frames = 0, steady = 0;
};

template <class S>
WindowRead ramp_window(const arc_loop_frames& loop, std::uint64_t end, std::uint64_t min_frames,
                       const std::vector<std::pair<std::uint64_t, std::uint64_t>>& spans) {
  WindowRead out;
  if constexpr (HasRampWindow<S, cli::LoudnessWindow>) {
    std::vector<S> ramps;
    for (const auto& [a, b] : spans) {
      S s{};
      s.start = a;
      s.end = b;
      ramps.push_back(s);
    }
    const auto w = cli::loudness_window(loop, end, min_frames, std::span<const S>(ramps));
    out = {w.accepted, w.start_frame, w.body_frames, w.repeats, w.window_frames, w.steady_frames};
  } else {
    (void)loop;
    (void)end;
    (void)min_frames;
    (void)spans;
  }
  return out;
}

void require_ramp_window() {
  if (!kHaveRampWindow) {
    FAIL("not implemented: cli::FrameSpan, LoudnessWindow::steady_frames, and the loudness_window overload with "
         "ramps (Story 4.4)");
  }
}

std::uint64_t min_frames_at(std::uint32_t fs) {
  return cli::loudness_window_min_frames(tables::row("loudness-window-min"), fs);
}

arc_loop_frames no_loop(std::uint64_t end) {
  arc_loop_frames l;
  std::memset(&l, 0, sizeof l);
  l.end_frame = end;
  return l;
}

}  // namespace

TEST_CASE("loudness_window with ramps: every gain fixture window from its compiled plan", "[gain-ramps][loudness]") {
  require_ramp_window();
  require_gain_ramp_api();
  for (const auto& v : spec::kGainWindows) {
    INFO(v.fixture << " at " << v.fs);
    auto p = api::compile_ok(api::valid(v.fixture), api::options(ARC_MODE_MEASURE, v.fs));
    arc_loop_frames loop;
    arc_error e;
    REQUIRE(arc_plan_loop(p.get(), &loop, &e) == ARC_OK);
    CHECK((loop.looping == 1) == v.looping);
    std::vector<std::pair<std::uint64_t, std::uint64_t>> spans;
    const auto count = gain::ramp_count(p.get());
    REQUIRE(count.has_value());
    for (std::size_t i = 0; i < *count; ++i) {
      const gain::RampCall c = gain::ramp_at(p.get(), i, &e);
      REQUIRE(c.status == ARC_OK);
      spans.emplace_back(c.ramp.start_frame, c.ramp.end_frame);
    }
    const std::uint64_t min_frames = min_frames_at(v.fs);
    CHECK(min_frames == v.min_frames);
    const WindowRead w = ramp_window<Span>(loop, v.end_frame, min_frames, spans);
    CHECK(w.accepted);
    CHECK(w.start == v.start_frame);
    CHECK(w.body == v.body_frames);
    CHECK(w.repeats == v.repeats);
    CHECK(w.frames == v.window_frames);
    CHECK(w.steady == (v.looping ? 0 : v.body_frames));
  }
}

TEST_CASE("loudness_window with ramps: no ramp is the whole session; the longest stretch, ties to the earliest",
          "[gain-ramps][loudness]") {
  require_ramp_window();
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO(fs);
    const std::uint64_t m = min_frames_at(fs);
    const std::uint64_t n = 10 * m;
    const auto plain = cli::loudness_window(no_loop(n), n, m);
    const WindowRead none = ramp_window<Span>(no_loop(n), n, m, {});
    CHECK(none.accepted == plain.accepted);
    CHECK(none.start == plain.start_frame);
    CHECK(none.body == plain.body_frames);
    CHECK(none.repeats == plain.repeats);
    CHECK(none.frames == plain.window_frames);
    CHECK(none.steady == n);
    // Two stretches of equal length: [0, 3m) and [4m, 7m) around a ramp
    // [3m, 4m), and a ramp [7m, n): the earliest wins.
    const WindowRead tie = ramp_window<Span>(no_loop(n), n, m, {{3 * m, 4 * m}, {7 * m, n}});
    CHECK(tie.accepted);
    CHECK(tie.start == 0);
    CHECK(tie.body == 3 * m);
    CHECK(tie.steady == 3 * m);
    CHECK(tie.repeats == 1);
    CHECK(tie.frames == 3 * m);
    // Spans from different schedules may overlap and come in schedule
    // order, not time order: their union is left out.
    const WindowRead mixed = ramp_window<Span>(no_loop(n), n, m, {{5 * m, 6 * m}, {0, 2 * m}, {m, 3 * m}});
    CHECK(mixed.start == 6 * m);
    CHECK(mixed.body == 4 * m);
    CHECK(mixed.steady == 4 * m);
    // A ramp ending at N leaves the stretch before it.
    const WindowRead tail = ramp_window<Span>(no_loop(n), n, m, {{2 * m, n}});
    CHECK(tail.start == 0);
    CHECK(tail.body == 2 * m);
  }
}

TEST_CASE("loudness_window with ramps: must-fail, a steady stretch shorter than W_min is refused",
          "[gain-ramps][loudness][mustfail]") {
  require_ramp_window();
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO(fs);
    const std::uint64_t m = min_frames_at(fs);
    const std::uint64_t n = 10 * m;
    // Exactly W_min is accepted; one frame less is refused, steady_frames set.
    const WindowRead exact = ramp_window<Span>(no_loop(n), n, m, {{0, n - m}});
    CHECK(exact.accepted);
    CHECK(exact.start == n - m);
    CHECK(exact.steady == m);
    const WindowRead short_one = ramp_window<Span>(no_loop(n), n, m, {{0, n - m + 1}});
    CHECK_FALSE(short_one.accepted);
    CHECK(short_one.steady == m - 1);
    // A looping window ignores the ramps (loop rule 8 keeps the body free).
    arc_loop_frames loop;
    std::memset(&loop, 0, sizeof loop);
    loop.looping = 1;
    loop.opening_end_frame = m;
    loop.body_frames = 2 * m;
    loop.seam_count = 3;
    loop.end_frame = n;
    const auto plain = cli::loudness_window(loop, n, m);
    const WindowRead looped = ramp_window<Span>(loop, n, m, {{0, m}, {7 * m, n}});
    CHECK(looped.accepted);
    CHECK(looped.start == plain.start_frame);
    CHECK(looped.body == plain.body_frames);
    CHECK(looped.steady == 0);
  }
}

#else

TEST_CASE("loudness_window with ramps is implemented", "[gain-ramps][loudness]") {
  FAIL("not implemented: cli/loudness.hpp in arcani_cli_core (Story 4.1, extended by Story 4.4)");
}

#endif  // ARCANI_TEST_HAVE_CLI_LOUDNESS

#else  // ARC_ERROR_FIELD_BYTES

TEST_CASE("gain ramps through the C API", "[gain-ramps]") {
  FAIL("arcani/arcani.h does not declare the Story 1.2 C API yet (no ARC_ERROR_FIELD_BYTES)");
}

#endif  // ARC_ERROR_FIELD_BYTES
