// Binaural isolation (Story 1.2, FR-4): muted-ear measurement calibrated on
// Python signals, then asserted on engine renders through the public C API.
// Method and assertion: tests/cpp/isolation.hpp. Thresholds: rows
// binaural-isolation-engine (binaural join tap, the engine output point) and
// binaural-isolation-master (master output), read through the assertion call.
//
// Must-fail cases are doctored here, in the harness: 0.1 % of the active
// channel added to the muted channel at the join tap; crosstalk 1 dB above the
// master threshold at the master output; a render with no binaural layer
// (silent); an unmuted render at beat 0 (both ears carry the carrier).

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#include "isolation.hpp"
#include "spec_helpers.hpp"

#include <cmath>
#include <string>
#include <vector>

#ifndef ARCANI_TEST_DATA_DIR
#error "ARCANI_TEST_DATA_DIR must name tests/data"
#endif

namespace iso = arcani::test::isolation;
namespace spec = arcani::test::spec;

namespace {

constexpr const char* kEngineRow = "binaural-isolation-engine";
constexpr const char* kMasterRow = "binaural-isolation-master";
constexpr const char* kRowUnit = "dB below the ear's own binaural carrier";
// Acceptance criterion: each calibration level reads within 0.5 dB.
constexpr double kCalibrationToleranceDb = 0.5;

}  // namespace

// ------------------------------------------------------------ calibration

TEST_CASE("isolation rows are relative dB rows", "[isolation][calibration]") {
  CHECK(spec::db_row(kEngineRow).unit == kRowUnit);
  CHECK(spec::db_row(kMasterRow).unit == kRowUnit);
  CHECK_THROWS(spec::db_row("sine-error"));  // dBFS is not a relative dB unit
}

TEST_CASE("calibration: the measurement reads each known leakage within 0.5 dB", "[isolation][calibration]") {
  const auto setups = iso::load_calibration(std::string(ARCANI_TEST_DATA_DIR) + "/isolation_calibration.json");
  REQUIRE(setups.size() >= 2);
  bool left_active = false;
  bool right_active = false;
  for (const auto& s : setups) {
    left_active = left_active || s.active == iso::Channel::Left;
    right_active = right_active || s.active == iso::Channel::Right;
    std::vector<double> levels;
    std::vector<std::string> verdicts;
    for (const auto& c : s.cases) {
      INFO(s.id << ", known level " << c.level_db << " dB");
      const iso::Measurement m = iso::measure(c.stereo, s.active, s.carrier_hz, s.fs);
      CHECK_FALSE(m.silent);
      CHECK(std::fabs(m.level_db - c.level_db) <= kCalibrationToleranceDb);
      const iso::Verdict v = iso::judge(m, kEngineRow);
      INFO(iso::describe(v));
      const bool known_pass = c.level_db <= -v.threshold_db;
      CHECK(v.pass == known_pass);
      levels.push_back(c.level_db);
      verdicts.push_back(v.pass ? "pass" : "fail");
    }
    INFO(s.id);
    CHECK(levels == std::vector<double>{-100.0, -91.0, -89.0, -60.0});
    CHECK(verdicts == std::vector<std::string>{"pass", "pass", "fail", "fail"});
  }
  CHECK(left_active);
  CHECK(right_active);
}

TEST_CASE("calibration: measuring with the ears swapped or a doctored level is caught", "[isolation][calibration]") {
  // Must-fail for the measurement: swapping the active and muted ears reads
  // the leakage inverted (+level), and a muted channel raised by 1 dB reads
  // outside the tolerance.
  const auto setups = iso::load_calibration(std::string(ARCANI_TEST_DATA_DIR) + "/isolation_calibration.json");
  REQUIRE_FALSE(setups.empty());
  const auto& s = setups.front();
  REQUIRE_FALSE(s.cases.empty());
  const auto& c = s.cases.front();
  const iso::Measurement swapped = iso::measure(c.stereo, iso::other(s.active), s.carrier_hz, s.fs);
  CHECK(std::fabs(swapped.level_db - c.level_db) > kCalibrationToleranceDb);
  std::vector<double> raised = c.stereo;
  const std::size_t muted = s.active == iso::Channel::Left ? 1 : 0;
  for (std::size_t n = muted; n < raised.size(); n += 2) {
    raised[n] *= std::pow(10.0, 1.0 / 20.0);
  }
  const iso::Measurement doctored = iso::measure(raised, s.active, s.carrier_hz, s.fs);
  CHECK(std::fabs(doctored.level_db - c.level_db) > kCalibrationToleranceDb);
}

TEST_CASE("assertion fails as silent when the active carrier measures zero", "[isolation][calibration]") {
  std::vector<double> silent(2 * 4800, 0.0);
  const iso::Measurement m = iso::measure(silent, iso::Channel::Left, 400.0, 48000);
  CHECK(m.silent);
  const iso::Verdict v = iso::judge(m, kEngineRow);
  CHECK(v.silent);
  CHECK_FALSE(v.pass);
  // A muted channel of exact zeros next to a live carrier passes.
  for (std::size_t n = 0; n < 4800; ++n) {
    silent[2 * n] = std::sin(2.0 * 3.141592653589793 * 400.0 * static_cast<double>(n) / 48000.0);
  }
  const iso::Verdict live = iso::judge(iso::measure(silent, iso::Channel::Left, 400.0, 48000), kEngineRow);
  CHECK_FALSE(live.silent);
  CHECK(live.pass);
}

// ---------------------------------------------------------- engine renders

#ifdef ARC_ERROR_FIELD_BYTES

#include "api_helpers.hpp"

namespace api = arcani::test::api;

namespace {

struct MutedRender {
  std::vector<double> join;    // binaural join tap
  std::vector<double> master;  // render output
};

MutedRender render_muted(const char* fixture, std::uint32_t fs, arc_mute_ear mute) {
  auto p = api::compile_ok(api::valid(fixture), api::options(ARC_MODE_MEASURE, fs, mute));
  const auto frames = static_cast<std::size_t>(arc_plan_frame_count(p.get()));
  auto r = api::renderer(p.get());
  api::TapBuffers taps(frames);
  arc_taps t;
  std::memset(&t, 0, sizeof t);
  t.binaural_join = taps.binaural_join.data();
  MutedRender m;
  m.master = api::render(r.get(), frames, &t);
  m.join = taps.binaural_join;
  return m;
}

// The binaural carriers of a stub chain fixture, from the spec vectors.
const spec::StubChainVector& carriers(const char* fixture, std::uint32_t fs) {
  for (const auto& v : spec::kStubChain) {
    if (v.fs == fs && std::string(v.fixture) == fixture) {
      return v;
    }
  }
  FAIL("no stub chain vector for " << fixture << " at " << fs);
  return spec::kStubChain[0];
}

}  // namespace

TEST_CASE("isolation: muted-ear renders pass both rows at beat 0 and 6 Hz", "[isolation][engine]") {
  for (const std::uint32_t fs : {44100u, 48000u}) {
    for (const char* fixture : {api::kBeat0, api::kBeat6}) {
      const auto& v = carriers(fixture, fs);
      for (const arc_mute_ear mute : {ARC_MUTE_LEFT, ARC_MUTE_RIGHT}) {
        const iso::Channel active = mute == ARC_MUTE_LEFT ? iso::Channel::Right : iso::Channel::Left;
        const double carrier = active == iso::Channel::Left ? v.carrier_left_hz : v.carrier_right_hz;
        INFO(fixture << " at " << fs << ", active " << iso::name(active) << " ear, carrier " << carrier << " Hz");
        const MutedRender m = render_muted(fixture, fs, mute);
        const iso::Verdict engine = iso::judge(iso::measure(m.join, active, carrier, fs), kEngineRow);
        const iso::Verdict master = iso::judge(iso::measure(m.master, active, carrier, fs), kMasterRow);
        INFO(iso::describe(engine));
        INFO(iso::describe(master));
        CHECK(engine.pass);
        CHECK(master.pass);
      }
    }
  }
}

TEST_CASE("isolation: 0.1 % crosstalk at the join tap fails the engine row", "[isolation][engine]") {
  for (const std::uint32_t fs : {44100u, 48000u}) {
    for (const char* fixture : {api::kBeat0, api::kBeat6}) {
      const auto& v = carriers(fixture, fs);
      for (const arc_mute_ear mute : {ARC_MUTE_LEFT, ARC_MUTE_RIGHT}) {
        const iso::Channel active = mute == ARC_MUTE_LEFT ? iso::Channel::Right : iso::Channel::Left;
        const double carrier = active == iso::Channel::Left ? v.carrier_left_hz : v.carrier_right_hz;
        INFO(fixture << " at " << fs << ", active " << iso::name(active) << " ear");
        MutedRender m = render_muted(fixture, fs, mute);
        iso::add_crosstalk(m.join, active, 0.001);
        const iso::Verdict engine = iso::judge(iso::measure(m.join, active, carrier, fs), kEngineRow);
        INFO(iso::describe(engine));
        CHECK_FALSE(engine.silent);
        CHECK_FALSE(engine.pass);
        CHECK(std::fabs(engine.measured_db - -60.0) <= kCalibrationToleranceDb);
      }
    }
  }
}

TEST_CASE("isolation: crosstalk 1 dB above the master threshold fails the master row", "[isolation][engine]") {
  const double threshold = spec::db_row(kMasterRow).value();
  const double gain = std::pow(10.0, (-threshold + 1.0) / 20.0);
  for (const std::uint32_t fs : {44100u, 48000u}) {
    for (const char* fixture : {api::kBeat0, api::kBeat6}) {
      const auto& v = carriers(fixture, fs);
      for (const arc_mute_ear mute : {ARC_MUTE_LEFT, ARC_MUTE_RIGHT}) {
        const iso::Channel active = mute == ARC_MUTE_LEFT ? iso::Channel::Right : iso::Channel::Left;
        const double carrier = active == iso::Channel::Left ? v.carrier_left_hz : v.carrier_right_hz;
        INFO(fixture << " at " << fs << ", active " << iso::name(active) << " ear");
        MutedRender m = render_muted(fixture, fs, mute);
        iso::add_crosstalk(m.master, active, gain);
        const iso::Verdict master = iso::judge(iso::measure(m.master, active, carrier, fs), kMasterRow);
        INFO(iso::describe(master));
        CHECK_FALSE(master.pass);
      }
    }
  }
}

TEST_CASE("isolation: no binaural layer fails as silent", "[isolation][engine]") {
  const auto& v = carriers(api::kBeat6, 48000);
  for (const arc_mute_ear mute : {ARC_MUTE_NONE, ARC_MUTE_LEFT, ARC_MUTE_RIGHT}) {
    INFO("mute " << mute);
    const MutedRender m = render_muted(api::kNoLayers, 48000, mute);
    for (const iso::Channel active : {iso::Channel::Left, iso::Channel::Right}) {
      const double carrier = active == iso::Channel::Left ? v.carrier_left_hz : v.carrier_right_hz;
      const iso::Verdict engine = iso::judge(iso::measure(m.join, active, carrier, 48000), kEngineRow);
      const iso::Verdict master = iso::judge(iso::measure(m.master, active, carrier, 48000), kMasterRow);
      CHECK(engine.silent);
      CHECK_FALSE(engine.pass);
      CHECK(master.silent);
      CHECK_FALSE(master.pass);
    }
  }
}

TEST_CASE("isolation: an unmuted render at beat 0 fails, both ears carry the carrier", "[isolation][engine]") {
  const auto& v = carriers(api::kBeat0, 48000);
  const MutedRender m = render_muted(api::kBeat0, 48000, ARC_MUTE_NONE);
  const iso::Verdict engine = iso::judge(iso::measure(m.join, iso::Channel::Left, v.carrier_left_hz, 48000), kEngineRow);
  INFO(iso::describe(engine));
  CHECK_FALSE(engine.pass);
  CHECK(std::fabs(engine.measured_db) <= kCalibrationToleranceDb);
}

#else  // ARC_ERROR_FIELD_BYTES

TEST_CASE("isolation: muted-ear renders pass both rows at beat 0 and 6 Hz", "[isolation][engine]") {
  FAIL("arcani/arcani.h does not declare the Story 1.2 C API yet (no ARC_ERROR_FIELD_BYTES)");
}

#endif  // ARC_ERROR_FIELD_BYTES
