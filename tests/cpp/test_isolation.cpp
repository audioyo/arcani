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
//
// Story 1.5: the theta reference stub (a 300 Hz unmodulated sine in both
// channels of beat-6) is not binaural and is not muted; the rows still pass
// with it in the muted channel.
//
// Story 2.5 (binaural layer): a band mode for a beat rate cycle, whose right
// carrier sweeps a band instead of sitting on one bin. Expected interface,
// tests/cpp/isolation.hpp:
//
//   inline constexpr int kBandGuardBins = 2;
//   Measurement measure_band(const std::vector<double>& stereo, Channel active,
//                            double band_lo_hz, double band_hi_hz, std::uint32_t fs);
//
// Hann window over the whole render as in bin mode, FFT zero-padded to the
// next power of two at or above the frame count N, the band extended by
// kBandGuardBins * fs / N on each side, energy E = sum of |X[k]|^2 over the
// FFT bins inside the guarded band, level_db = 10 * log10(E_muted /
// E_active); silent when E_active is 0, -inf when E_muted is 0. Measurement
// gains band, band_lo_hz, band_hi_hz; CalibrationSetup gains the same three,
// read from an optional per-setup "mode" ("bin", the default, or "band" with
// "band_lo_hz" and "band_hi_hz"). judge() is unchanged. The calibration file
// gains two band setups, sweep-100-103hz-48000-left-active and
// sweep-403-406hz-44100-right-active (swept unit sines, levels -100, -91,
// -89, -60 dB). The new pieces are reached through a lookup probe and
// requires-expressions, so the suite builds before they exist.
//
// Engine renders: binaural-beat-0, -6, -29 (bin mode at the active carrier)
// and binaural-cycle-sleep (band mode: the active right ear spans f_C - s to
// f_C + s, the active left ear its own carrier) at both rates pass both rows;
// 0.1 % crosstalk added here fails the engine row in band mode.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#include "isolation.hpp"
#include "spec_helpers.hpp"

#include <cmath>
#include <concepts>
#include <cstdint>
#include <limits>
#include <optional>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

#ifndef ARCANI_TEST_DATA_DIR
#error "ARCANI_TEST_DATA_DIR must name tests/data"
#endif

// Story 2.5 lookup probe. Inside arcani::isolation_probe the using-directive
// makes the names of arcani::test::isolation visible as members of arcani,
// which unqualified lookup reaches before these global fallbacks: a real
// measure_band or kBandGuardBins hides its fallback. The fallback
// measurement is silent, so every band check fails until the mode exists.
namespace isolation_missing {
struct MissingBand {
  template <class... A>
  arcani::test::isolation::Measurement operator()(A...) const {
    arcani::test::isolation::Measurement m;
    m.silent = true;
    m.level_db = std::numeric_limits<double>::quiet_NaN();
    return m;
  }
};
}  // namespace isolation_missing

inline constexpr isolation_missing::MissingBand measure_band{};
inline constexpr int kBandGuardBins = -1;

namespace arcani::isolation_probe {
using namespace arcani::test::isolation;
inline constexpr bool kBandDeclared =
    !std::is_same_v<std::remove_cvref_t<decltype(measure_band)>, ::isolation_missing::MissingBand>;
inline constexpr int guard_bins = kBandGuardBins;
inline Measurement call_band(const std::vector<double>& stereo, Channel active, double lo_hz, double hi_hz,
                             std::uint32_t fs) {
  return measure_band(stereo, active, lo_hz, hi_hz, fs);
}
}  // namespace arcani::isolation_probe

namespace iso = arcani::test::isolation;
namespace iprobe = arcani::isolation_probe;
namespace spec = arcani::test::spec;

namespace {

template <class M>
concept MeasurementHasBand = requires(const M& m) {
  { m.band } -> std::convertible_to<bool>;
  { m.band_lo_hz } -> std::convertible_to<double>;
  { m.band_hi_hz } -> std::convertible_to<double>;
};

template <class S>
concept SetupHasBand = requires(const S& s) {
  { s.band } -> std::convertible_to<bool>;
  { s.band_lo_hz } -> std::convertible_to<double>;
  { s.band_hi_hz } -> std::convertible_to<double>;
};

bool names_a_sweep(const std::string& id) { return id.rfind("sweep-", 0) == 0; }

// The band of a band-mode setup, nothing for a bin-mode setup. A setup whose
// id names a sweep but that the loader cannot read as a band fails.
template <class S>
std::optional<std::pair<double, double>> band_of(const S& s) {
  if constexpr (SetupHasBand<S>) {
    if (s.band) {
      return std::make_pair(static_cast<double>(s.band_lo_hz), static_cast<double>(s.band_hi_hz));
    }
    CHECK_FALSE(names_a_sweep(s.id));
  } else {
    if (names_a_sweep(s.id)) {
      FAIL("not implemented: CalibrationSetup has no band, band_lo_hz, band_hi_hz (Story 2.5)");
    }
  }
  return std::nullopt;
}

// A template, so the band members are looked up only once they exist.
template <class M>
void check_band_fields(const M& m, double lo_hz, double hi_hz) {
  if constexpr (MeasurementHasBand<M>) {
    CHECK(m.band);
    CHECK(m.band_lo_hz == lo_hz);
    CHECK(m.band_hi_hz == hi_hz);
  } else {
    FAIL("not implemented: Measurement has no band, band_lo_hz, band_hi_hz (Story 2.5)");
  }
}

// Band mode, checking that the measurement says so.
iso::Measurement band(const std::vector<double>& stereo, iso::Channel active, double lo_hz, double hi_hz,
                      std::uint32_t fs) {
  const iso::Measurement m = iprobe::call_band(stereo, active, lo_hz, hi_hz, fs);
  check_band_fields(m, lo_hz, hi_hz);
  return m;
}

// Either mode, by the setup.
template <class S>
iso::Measurement measure_setup(const S& s, const std::vector<double>& stereo, iso::Channel active) {
  if (const auto b = band_of(s)) {
    return band(stereo, active, b->first, b->second, s.fs);
  }
  return iso::measure(stereo, active, s.carrier_hz, s.fs);
}

}  // namespace

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
      const iso::Measurement m = measure_setup(s, c.stereo, s.active);
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

TEST_CASE("calibration: the band mode reads each swept leak within 0.5 dB", "[isolation][calibration][band]") {
  CHECK(iprobe::kBandDeclared);
  CHECK(iprobe::guard_bins == 2);
  const auto setups = iso::load_calibration(std::string(ARCANI_TEST_DATA_DIR) + "/isolation_calibration.json");
  struct Want {
    const char* id;
    std::uint32_t fs;
    iso::Channel active;
    double lo_hz;
    double hi_hz;
  };
  const Want wants[] = {{"sweep-100-103hz-48000-left-active", 48000, iso::Channel::Left, 100.0, 103.0},
                        {"sweep-403-406hz-44100-right-active", 44100, iso::Channel::Right, 400.0, 406.0}};
  for (const auto& w : wants) {
    INFO(w.id);
    const iso::CalibrationSetup* found = nullptr;
    for (const auto& s : setups) {
      if (s.id == w.id) {
        found = &s;
      }
    }
    REQUIRE(found != nullptr);
    const auto& s = *found;
    CHECK(s.fs == w.fs);
    CHECK(s.active == w.active);
    const auto b = band_of(s);
    REQUIRE(b.has_value());
    CHECK(b->first == w.lo_hz);
    CHECK(b->second == w.hi_hz);
    std::vector<std::string> verdicts;
    for (const auto& c : s.cases) {
      INFO("known level " << c.level_db << " dB");
      const iso::Measurement m = band(c.stereo, s.active, w.lo_hz, w.hi_hz, s.fs);
      CHECK_FALSE(m.silent);
      CHECK(std::fabs(m.level_db - c.level_db) <= kCalibrationToleranceDb);
      const iso::Verdict v = iso::judge(m, kEngineRow);
      INFO(iso::describe(v));
      verdicts.push_back(v.pass ? "pass" : "fail");
    }
    CHECK(verdicts == std::vector<std::string>{"pass", "pass", "fail", "fail"});

    // Must-fail for the band mode: the ears swapped read the leak inverted,
    // and a muted channel raised by 1 dB reads outside the tolerance.
    REQUIRE_FALSE(s.cases.empty());
    const auto& c = s.cases.front();
    const iso::Measurement swapped = band(c.stereo, iso::other(s.active), w.lo_hz, w.hi_hz, s.fs);
    CHECK(std::fabs(swapped.level_db - c.level_db) > kCalibrationToleranceDb);
    std::vector<double> raised = c.stereo;
    const std::size_t muted = s.active == iso::Channel::Left ? 1 : 0;
    for (std::size_t n = muted; n < raised.size(); n += 2) {
      raised[n] *= std::pow(10.0, 1.0 / 20.0);
    }
    const iso::Measurement doctored = band(raised, s.active, w.lo_hz, w.hi_hz, s.fs);
    CHECK(std::fabs(doctored.level_db - c.level_db) > kCalibrationToleranceDb);
  }
}

TEST_CASE("band mode: a silent active channel fails, an exact-zero muted channel passes",
          "[isolation][calibration][band]") {
  std::vector<double> stereo(2 * 24000, 0.0);
  const iso::Measurement silent = band(stereo, iso::Channel::Right, 100.0, 103.0, 48000);
  CHECK(silent.silent);
  CHECK_FALSE(iso::judge(silent, kEngineRow).pass);
  for (std::size_t n = 0; n < 24000; ++n) {
    const double t = static_cast<double>(n) / 48000.0;
    stereo[2 * n + 1] = std::sin(2.0 * 3.141592653589793 * 101.5 * t);
  }
  const iso::Measurement live = band(stereo, iso::Channel::Right, 100.0, 103.0, 48000);
  CHECK_FALSE(live.silent);
  CHECK(std::isinf(live.level_db));
  CHECK(live.level_db < 0.0);
  CHECK(iso::judge(live, kEngineRow).pass);
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
        // Story 1.5: beat-6 has a 300 Hz unmodulated theta reference, which
        // reaches both channels. The muted channel then carries it and is
        // not silent, so the rows pass with another layer present.
        if (v.has_theta) {
          const std::size_t muted = active == iso::Channel::Left ? 1 : 0;
          bool muted_has_signal = false;
          for (std::size_t n = muted; n < m.join.size(); n += 2) {
            muted_has_signal = muted_has_signal || m.join[n] != 0.0;
          }
          CHECK(muted_has_signal);
        }
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

// ------------------------------------------- binaural layer fixtures (Story 2.5)

namespace {

const char* const kBinauralFixed[] = {"binaural-beat-0.json", "binaural-beat-6.json", "binaural-beat-29.json"};
constexpr const char* kBinauralCycle = "binaural-cycle-sleep.json";

const spec::BinauralSampleVector& binaural_vector(const char* fixture, std::uint32_t fs) {
  for (const auto& v : spec::kBinauralSamples) {
    if (v.fs == fs && std::string(v.fixture) == fixture) {
      return v;
    }
  }
  FAIL("no binaural sample vector for " << fixture << " at " << fs);
  return spec::kBinauralSamples[0];
}

// The band the active ear's carrier spans: f_C - s to f_C + s for the right
// ear with a beat rate cycle, the carrier itself otherwise.
std::pair<double, double> active_band(const spec::BinauralSampleVector& v, iso::Channel active) {
  if (active == iso::Channel::Left) {
    return {v.carrier_left_hz, v.carrier_left_hz};
  }
  if (!v.has_cycle) {
    return {v.center_hz, v.center_hz};
  }
  return {v.center_hz - v.swing_hz, v.center_hz + v.swing_hz};
}

}  // namespace

TEST_CASE("isolation: binaural fixed-beat fixtures pass both rows in bin mode", "[isolation][engine][binaural]") {
  for (const std::uint32_t fs : {44100u, 48000u}) {
    for (const char* fixture : kBinauralFixed) {
      const auto& v = binaural_vector(fixture, fs);
      REQUIRE_FALSE(v.has_cycle);
      for (const arc_mute_ear mute : {ARC_MUTE_LEFT, ARC_MUTE_RIGHT}) {
        const iso::Channel active = mute == ARC_MUTE_LEFT ? iso::Channel::Right : iso::Channel::Left;
        const double carrier = active == iso::Channel::Left ? v.carrier_left_hz : v.center_hz;
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

TEST_CASE("isolation: the beat rate cycle fixture passes both rows in band mode",
          "[isolation][engine][binaural][band]") {
  for (const std::uint32_t fs : {44100u, 48000u}) {
    const auto& v = binaural_vector(kBinauralCycle, fs);
    REQUIRE(v.has_cycle);
    for (const arc_mute_ear mute : {ARC_MUTE_LEFT, ARC_MUTE_RIGHT}) {
      const iso::Channel active = mute == ARC_MUTE_LEFT ? iso::Channel::Right : iso::Channel::Left;
      const auto span = active_band(v, active);
      INFO(kBinauralCycle << " at " << fs << ", active " << iso::name(active) << " ear, band " << span.first
                          << " to " << span.second << " Hz");
      const MutedRender m = render_muted(kBinauralCycle, fs, mute);
      const iso::Verdict engine = iso::judge(band(m.join, active, span.first, span.second, fs), kEngineRow);
      const iso::Verdict master = iso::judge(band(m.master, active, span.first, span.second, fs), kMasterRow);
      INFO(iso::describe(engine));
      INFO(iso::describe(master));
      CHECK(engine.pass);
      CHECK(master.pass);
    }
    // The right ear's band is the Sleep cycle's 0 to 3 Hz on the 100 Hz carrier.
    const auto right = active_band(v, iso::Channel::Right);
    CHECK(right.first == v.carrier_left_hz);
    CHECK(right.second == v.carrier_left_hz + 2.0 * v.swing_hz);
  }
}

TEST_CASE("isolation: 0.1 % crosstalk on the beat rate cycle fixture fails the engine row in band mode",
          "[isolation][engine][binaural][band]") {
  for (const std::uint32_t fs : {44100u, 48000u}) {
    const auto& v = binaural_vector(kBinauralCycle, fs);
    for (const arc_mute_ear mute : {ARC_MUTE_LEFT, ARC_MUTE_RIGHT}) {
      const iso::Channel active = mute == ARC_MUTE_LEFT ? iso::Channel::Right : iso::Channel::Left;
      const auto span = active_band(v, active);
      INFO(kBinauralCycle << " at " << fs << ", active " << iso::name(active) << " ear");
      MutedRender m = render_muted(kBinauralCycle, fs, mute);
      iso::add_crosstalk(m.join, active, 0.001);
      const iso::Verdict engine = iso::judge(band(m.join, active, span.first, span.second, fs), kEngineRow);
      INFO(iso::describe(engine));
      CHECK_FALSE(engine.silent);
      CHECK_FALSE(engine.pass);
      CHECK(std::fabs(engine.measured_db - -60.0) <= kCalibrationToleranceDb);
    }
  }
}

#else  // ARC_ERROR_FIELD_BYTES

TEST_CASE("isolation: muted-ear renders pass both rows at beat 0 and 6 Hz", "[isolation][engine]") {
  FAIL("arcani/arcani.h does not declare the Story 1.2 C API yet (no ARC_ERROR_FIELD_BYTES)");
}

#endif  // ARC_ERROR_FIELD_BYTES
