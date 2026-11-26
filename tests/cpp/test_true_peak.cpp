// True-peak meter of the command-line renderer (Story 4.3;
// docs/signal-spec.md, True peak). No render: the meter on signals made
// here, the store step on chosen readings, and the report member.
//
// Contracts (spec Implementation Notes, command-line tooling and Report):
// new cli/true_peak.hpp in arcani_cli_core, namespace arcani::cli (no
// engine/src include):
//   class TruePeakMeter {                         // streaming, both channels, zero state
//    public:
//     void add(std::int32_t left, std::int32_t right);  // one frame of 24-bit integers
//     double linear() const;                      // TP after the 11 trailing zeros; does not
//                                                 // depend on when it is called
//   };
//   double true_peak_dbtp(double linear);         // 20 * log10(linear); -inf at 0
// cli/recipe_write.hpp:
//   struct TruePeakStep { bool stored; double dbtp; std::string line; };  // line empty when stored
//   TruePeakStep true_peak_step(const Row& row, double tp_linear, double target_lufs,
//                               std::string_view gain_text);
//     throws TableError unless a thresholds row in dBTP with a finite value
// cli/report.hpp:
//   struct TruePeakReport { double linear; double dbtp; };
//   Report gains std::optional<TruePeakReport> true_peak, written after
//   loudness (or spacing, loop, frames) and before determinism_key, dbtp
//   null when not finite;
//   Assertion true_peak_assertion(const Row& row, double linear);
//     name "true_peak", measured dbtp, pass when dbtp <= row value;
//     linear 0: measured null, pass, note "silent".
//
// Vectors come from the generated spec_tables.hpp (kTruePeak_*,
// kTruePeakFilter, kTruePeakSignals, kTruePeakSteps); rows true-peak,
// true-peak-meter-over, true-peak-meter-under from the tables through the
// assertion call. The calibration signals are synthesized here by the spec
// rule (true_peak_helpers.hpp) and their 24-bit bytes must hash to the
// vector's SHA-256. Must-fails are made here: meters without oversampling
// or without the edge outputs, a doctored row, doctored rows of the wrong
// unit or kind.
//
// The harness checks run now; until cli/true_peak.hpp exists the rest of the
// file compiles to one failing test case, so the rest of the suite still
// runs.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#include "api_helpers.hpp"
#include "cli_helpers.hpp"
#include "crypto/sha256.hpp"
#include "json/value.hpp"
#include "spec_helpers.hpp"
#include "spec_tables.hpp"
#include "tables.hpp"
#include "true_peak_helpers.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <string>
#include <string_view>
#include <vector>

namespace spec = arcani::test::spec;
namespace tables = arcani::test::tables;
namespace tp = arcani::test::true_peak;

namespace {

constexpr double kInf = std::numeric_limits<double>::infinity();

const tables::Row& ceiling_row() {
  const tables::Row& r = tables::row(spec::kTruePeak_row);
  REQUIRE(r.kind == "thresholds");
  REQUIRE(r.unit == "dBTP");
  return r;
}

const tables::Row& over_row() {
  const tables::Row& r = tables::row(spec::kTruePeak_over_row);
  REQUIRE(r.kind == "thresholds");
  REQUIRE(r.unit == "dB");
  return r;
}

const tables::Row& under_row() {
  const tables::Row& r = tables::row(spec::kTruePeak_under_row);
  REQUIRE(r.kind == "thresholds");
  REQUIRE(r.unit == "dB");
  return r;
}

const spec::TruePeakSignalVector& signal_vector(std::string_view name, std::uint32_t fs) {
  for (const auto& v : spec::kTruePeakSignals) {
    if (name == v.signal && v.fs == fs) {
      return v;
    }
  }
  FAIL("no true-peak signal vector " << name << " at " << fs);
  return spec::kTruePeakSignals[0];
}

}  // namespace

// ------------------------------------------------------------ rows and harness

TEST_CASE("true peak: rows and vector constants agree", "[true-peak][rows]") {
  const tables::Row& c = ceiling_row();
  CHECK(c.value() == spec::kTruePeak_ceiling_dbtp);
  CHECK(over_row().value() == spec::kTruePeak_over_db);
  CHECK(under_row().value() == spec::kTruePeak_under_db);
  CHECK(std::string("<= ") + c.value_text + " " + c.unit + " (row " + c.id + ")" == spec::kTruePeak_limit);
  CHECK(spec::kTruePeak_oversampling == static_cast<std::uint32_t>(tp::kPhases));
  CHECK(spec::kTruePeak_taps == static_cast<std::uint32_t>(tp::kTaps));
  CHECK(spec::kTruePeak_trailing_zeros == spec::kTruePeak_taps - 1);
  CHECK(std::size(spec::kTruePeakFilter) == spec::kTruePeak_oversampling * spec::kTruePeak_taps);
}

TEST_CASE("true peak: the filter is the printed integers times 2^-13; phases 2 and 3 are reversals",
          "[true-peak]") {
  const tp::Filter n = tp::filter_integers();
  for (const auto& v : spec::kTruePeakFilter) {
    INFO("phase " << v.phase << " tap " << v.tap);
    CHECK(v.value == static_cast<double>(v.integer) / 8192.0);
    CHECK(std::strtod(v.printed, nullptr) == v.value);
  }
  for (int k = 0; k < tp::kTaps; ++k) {
    CHECK(n[2][static_cast<std::size_t>(k)] == n[1][static_cast<std::size_t>(tp::kTaps - 1 - k)]);
    CHECK(n[3][static_cast<std::size_t>(k)] == n[0][static_cast<std::size_t>(tp::kTaps - 1 - k)]);
  }
  for (int p = 0; p < tp::kPhases; ++p) {
    std::int64_t sum = 0;
    for (const std::int64_t x : n[static_cast<std::size_t>(p)]) {
      sum += x;
    }
    CHECK(sum == spec::kTruePeak_phase_sums[p]);
  }
}

TEST_CASE("true peak: the harness synthesizes every signal vector and its meter gives the vector peak",
          "[true-peak]") {
  for (const auto& v : spec::kTruePeakSignals) {
    INFO("signal " << v.signal << " at " << v.fs);
    const std::vector<std::int32_t> x = tp::synthesize(v);
    REQUIRE(x.size() == 2 * v.frames);
    CHECK(tp::seconds_to_samples(spec::kTruePeak_fade_s, v.fs) == v.fade_frames);
    CHECK(arcani::crypto::sha256_hex(tp::data_bytes(x)) == v.samples_sha256);
    std::int64_t sample_peak = 0;
    for (const std::int32_t s : x) {
      sample_peak = std::max<std::int64_t>(sample_peak, std::llabs(s));
    }
    CHECK(sample_peak == v.sample_peak);
    CHECK(tp::harness_peak_integer(x) == v.peak_integer);
    CHECK(tp::harness_true_peak(x) == v.true_peak);
  }
}

#if defined(ARCANI_HAVE_CLI_CORE) && __has_include("true_peak.hpp")

#include "recipe_write.hpp"
#include "report.hpp"
#include "true_peak.hpp"

#include <charconv>
#include <optional>
#include <system_error>

namespace cli = arcani::cli;
namespace h = arcani::test::cli;
namespace json = arcani::json;

namespace {

double feed(cli::TruePeakMeter& m, const std::vector<std::int32_t>& x, std::size_t from = 0,
            std::size_t to = std::numeric_limits<std::size_t>::max()) {
  to = std::min(to, x.size() / 2);
  for (std::size_t i = from; i < to; ++i) {
    m.add(x[2 * i], x[2 * i + 1]);
  }
  return m.linear();
}

double meter_reading(const std::vector<std::int32_t>& x) {
  cli::TruePeakMeter m;
  return feed(m, x);
}

std::string shortest(double x) {
  char buf[64];
  const auto r = std::to_chars(buf, buf + sizeof buf, x);
  REQUIRE(r.ec == std::errc());
  return std::string(buf, r.ptr);
}

// std::strtod: the pinned macOS libc++ has no floating-point std::from_chars.
double parse_number(const std::string& s) {
  char* end = nullptr;
  const double v = std::strtod(s.c_str(), &end);
  REQUIRE(end == s.c_str() + s.size());
  return v;
}

constexpr std::string_view kDbtpKey = " true_peak_dbtp=";

// A rejection line against the vector's: equal up to the true_peak_dbtp text,
// which is compared after parsing, within 1e-12 dB (exactly for 0 dBTP).
void check_line(const std::string& got, const std::string& want) {
  INFO("line " << got << "\nwant " << want);
  const auto g = got.rfind(kDbtpKey);
  const auto w = want.rfind(kDbtpKey);
  REQUIRE(g != std::string::npos);
  REQUIRE(w != std::string::npos);
  CHECK(got.substr(0, g) == want.substr(0, w));
  const std::string want_text = want.substr(w + kDbtpKey.size());
  const double got_db = parse_number(got.substr(g + kDbtpKey.size()));
  const double want_db = parse_number(want_text);
  if (want_text == "0") {
    CHECK(got.substr(g + kDbtpKey.size()) == "0");
  } else {
    CHECK(std::fabs(got_db - want_db) <= 1e-12);
  }
}

cli::Report base_report(std::uint64_t frames, const std::string& mode) {
  cli::Report r;
  r.engine_version = "0.0.1";
  r.seed = 42;
  r.sample_rate = 48000;
  r.mode = mode;
  r.frames = frames;
  r.determinism_key.recipe_hash = std::string(64, 'a');
  r.determinism_key.engine_version = "0.0.1";
  r.determinism_key.sample_rate = 48000;
  return r;
}

json::Value parse_ok(const std::string& text) {
  json::ParseResult r = json::parse(text);
  INFO("JSON: " << text);
  REQUIRE(r.value.has_value());
  return *r.value;
}

std::string true_peak_block(double linear, double dbtp) {
  return std::string("  \"true_peak\": {\n    \"linear\": ") + shortest(linear) + ",\n    \"dbtp\": " +
         (std::isfinite(dbtp) ? shortest(dbtp) : std::string("null")) + "\n  },\n";
}

std::string insert_before_key(const std::string& text, const std::string& block) {
  const std::string key = "  \"determinism_key\": {";
  const auto at = text.find(key);
  REQUIRE(at != std::string::npos);
  return text.substr(0, at) + block + text.substr(at);
}

}  // namespace

// ------------------------------------------------------------ meter

TEST_CASE("true peak meter: every signal vector bit for bit, within the calibration rows", "[true-peak]") {
  const double over = over_row().value();
  const double under = under_row().value();
  const double ceiling = ceiling_row().value();
  for (const auto& v : spec::kTruePeakSignals) {
    INFO("signal " << v.signal << " at " << v.fs);
    const std::vector<std::int32_t> x = tp::synthesize(v);
    const double got = meter_reading(x);
    CHECK(arcani::test::api::bits(got) == arcani::test::api::bits(v.true_peak));
    const double db = cli::true_peak_dbtp(got);
    if (v.has_expected) {
      const double diff = db - v.expected_dbtp;
      CHECK(-under <= diff);
      CHECK(diff <= over);
      CHECK(v.calibration_pass);
      CHECK(std::fabs(diff - v.reading_minus_expected_db) <= 1e-9);
    } else {
      CHECK(got == 0.0);
      CHECK(db == -kInf);
    }
    CHECK((db <= ceiling) == v.assertion_pass);
  }
}

TEST_CASE("true peak meter: frame-by-frame reading does not depend on when linear() is called", "[true-peak]") {
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const auto& v = signal_vector("case 18", fs);
    const std::vector<std::int32_t> x = tp::synthesize(v);
    cli::TruePeakMeter whole;
    const double once = feed(whole, x);
    CHECK(arcani::test::api::bits(once) == arcani::test::api::bits(v.true_peak));
    CHECK(arcani::test::api::bits(whole.linear()) == arcani::test::api::bits(once));  // called again
    // linear() called part way, then fed on: the same final reading.
    cli::TruePeakMeter split;
    const std::size_t half = x.size() / 4;
    const double early = feed(split, x, 0, half);
    CHECK(early == tp::harness_true_peak(std::vector<std::int32_t>(x.begin(), x.begin() + 2 * half)));
    const double late = feed(split, x, half);
    CHECK(arcani::test::api::bits(late) == arcani::test::api::bits(once));
    // A copy reads the same.
    const cli::TruePeakMeter copy = split;
    CHECK(arcani::test::api::bits(copy.linear()) == arcani::test::api::bits(once));
  }
}

TEST_CASE("true peak meter: silence, no frames, single impulses at either end", "[true-peak]") {
  cli::TruePeakMeter none;
  CHECK(none.linear() == 0.0);
  const tp::Filter n = tp::filter_integers();
  std::int64_t largest = 0;
  for (const auto& phase : n) {
    for (const std::int64_t c : phase) {
      largest = std::max<std::int64_t>(largest, c < 0 ? -c : c);
    }
  }
  for (const std::size_t at : {std::size_t{0}, std::size_t{99}}) {
    INFO("impulse at frame " << at);
    std::vector<std::int32_t> x(200, 0);
    x[2 * at + 1] = tp::kMin24;
    const double want = static_cast<double>(largest) * 8388608.0 / 68719476736.0;
    CHECK(meter_reading(x) == want);
    CHECK(tp::harness_true_peak(x) == want);
    x[2 * at + 1] = 0;
    x[2 * at] = tp::kMax24;
    CHECK(meter_reading(x) == static_cast<double>(largest) * 8388607.0 / 68719476736.0);
  }
  CHECK(meter_reading(std::vector<std::int32_t>(200, 0)) == 0.0);
}

TEST_CASE("true peak must-fail: meters without oversampling or without the edge outputs misread",
          "[true-peak][mustfail]") {
  const double ceiling = ceiling_row().value();
  const std::uint64_t edge = spec::kTruePeak_trailing_zeros;
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const auto& v = signal_vector("hidden overshoot", fs);
    CHECK_FALSE(v.assertion_pass);
    CHECK(v.sample_peak_check_pass);
    const std::vector<std::int32_t> x = tp::synthesize(v);
    // Phase 0 alone and the sample peak read it at or below the ceiling.
    CHECK(tp::harness_dbtp(tp::harness_true_peak(x, 0x1u)) <= ceiling);
    CHECK(20.0 * std::log10(static_cast<double>(v.sample_peak) / 8388608.0) <= ceiling);
    CHECK(cli::true_peak_dbtp(meter_reading(x)) > ceiling);
    // Cut short or started abruptly: dropping the edge outputs misreads it.
    const std::vector<std::int32_t> cut = tp::synthesize(v, true, false);
    CHECK(tp::harness_true_peak(cut, 0xFu, 0, edge) != tp::harness_true_peak(cut));
    CHECK(meter_reading(cut) == tp::harness_true_peak(cut));
    const std::vector<std::int32_t> abrupt = tp::synthesize(v, false, true);
    CHECK(tp::harness_true_peak(abrupt, 0xFu, edge, 0) != tp::harness_true_peak(abrupt));
    CHECK(meter_reading(abrupt) == tp::harness_true_peak(abrupt));
  }
}

TEST_CASE("true peak: true_peak_dbtp is 20 log10, -inf at 0", "[true-peak]") {
  CHECK(cli::true_peak_dbtp(0.0) == -kInf);
  CHECK(cli::true_peak_dbtp(1.0) == 0.0);
  CHECK(std::fabs(cli::true_peak_dbtp(0.5) - (-6.020599913279624)) <= 1e-12);
  for (const auto& v : spec::kTruePeakSteps) {
    INFO("step " << v.name);
    if (v.true_peak == 0.0) {
      CHECK(cli::true_peak_dbtp(v.true_peak) == -kInf);
    } else {
      CHECK(std::fabs(cli::true_peak_dbtp(v.true_peak) - v.true_peak_dbtp) <= 1e-12);
    }
  }
}

// ------------------------------------------------------------ store step

TEST_CASE("true peak store step: every step vector with row true-peak", "[true-peak][store-gain]") {
  const tables::Row& r = ceiling_row();
  for (const auto& v : spec::kTruePeakSteps) {
    INFO("step " << v.name);
    const cli::TruePeakStep s = cli::true_peak_step(r, v.true_peak, v.target_lufs, v.gain_text);
    CHECK(s.stored == v.stored);
    if (v.true_peak == 0.0) {
      CHECK(s.dbtp == -kInf);
    } else {
      CHECK(std::fabs(s.dbtp - v.true_peak_dbtp) <= 1e-12);
    }
    if (v.stored) {
      CHECK(s.line.empty());
    } else {
      check_line(s.line, v.line);
    }
  }
}

TEST_CASE("true peak store step: reads its ceiling and limit from the row", "[true-peak][store-gain][mustfail]") {
  const tables::Row& real = ceiling_row();
  SECTION("a doctored row at -7 dBTP rejects the half-scale case") {
    tables::Row r = real;
    r.values = {-7.0};
    r.value_text = "-7";
    const cli::TruePeakStep s = cli::true_peak_step(r, 0.5, -36.0, "-35.27");
    CHECK_FALSE(s.stored);
    CHECK(s.line.rfind("rejected: parameter=/loudness_gain_db value=-35.27 rule=true_peak limit=<= -7 dBTP "
                       "(row true-peak) target_lufs=-36 true_peak_dbtp=",
                       0) == 0);
    // With the real row the same case is stored.
    CHECK(cli::true_peak_step(real, 0.5, -36.0, "-35.27").stored);
  }
  SECTION("the ceiling itself is stored (inclusive)") {
    tables::Row r = real;
    const double at = cli::true_peak_dbtp(0.5);
    r.values = {at};
    r.value_text = shortest(at);
    CHECK(cli::true_peak_step(r, 0.5, -36.0, "-35.27").stored);
    r.values = {std::nextafter(at, -kInf)};
    CHECK_FALSE(cli::true_peak_step(r, 0.5, -36.0, "-35.27").stored);
  }
  SECTION("a row in dB throws TableError") {
    tables::Row r = real;
    r.unit = "dB";
    CHECK_THROWS_AS(cli::true_peak_step(r, 0.5, -36.0, "-35.27"), tables::TableError);
  }
  SECTION("a ranges row throws TableError") {
    tables::Row r = real;
    r.kind = "ranges";
    CHECK_THROWS_AS(cli::true_peak_step(r, 0.5, -36.0, "-35.27"), tables::TableError);
  }
  SECTION("a non-finite value throws TableError") {
    tables::Row r = real;
    r.values = {std::numeric_limits<double>::quiet_NaN()};
    CHECK_THROWS_AS(cli::true_peak_step(r, 0.5, -36.0, "-35.27"), tables::TableError);
    r.values = {kInf};
    CHECK_THROWS_AS(cli::true_peak_step(r, 0.5, -36.0, "-35.27"), tables::TableError);
  }
}

// ------------------------------------------------------------ report

TEST_CASE("true peak assertion: pass at or below the ceiling, fail above, silent passes with null",
          "[true-peak][report]") {
  const tables::Row& r = ceiling_row();
  for (const auto& v : spec::kTruePeakSignals) {
    INFO("signal " << v.signal << " at " << v.fs);
    const cli::Assertion a = cli::true_peak_assertion(r, v.true_peak);
    CHECK(a.name == "true_peak");
    CHECK(a.row == r.id);
    CHECK(a.threshold == r.value());
    CHECK(a.unit == r.unit);
    CHECK(a.result == (v.assertion_pass ? cli::Result::pass : cli::Result::fail));
    if (v.true_peak == 0.0) {
      CHECK_FALSE(a.measured.has_value());
      CHECK(a.note == "silent");
    } else {
      REQUIRE(a.measured.has_value());
      CHECK(arcani::test::api::bits(*a.measured) == arcani::test::api::bits(cli::true_peak_dbtp(v.true_peak)));
      CHECK(a.note.empty());
    }
  }
  // Inclusive at the row value; a doctored row moves the result.
  tables::Row at = r;
  at.values = {cli::true_peak_dbtp(0.5)};
  CHECK(cli::true_peak_assertion(at, 0.5).result == cli::Result::pass);
  at.values = {std::nextafter(cli::true_peak_dbtp(0.5), -kInf)};
  CHECK(cli::true_peak_assertion(at, 0.5).result == cli::Result::fail);
  CHECK(cli::assertions_exit_code({cli::true_peak_assertion(r, 1.0)}) == 4);
  CHECK(cli::assertions_exit_code({cli::true_peak_assertion(r, 0.5), cli::true_peak_assertion(r, 0.0)}) == 0);
}

TEST_CASE("report_json writes the true_peak member before determinism_key, null dbtp at 0, nothing without it",
          "[true-peak][report]") {
  const tables::Row& row = ceiling_row();
  cli::LoudnessReport lr;
  lr.window_start_frame = 0;
  lr.window_body_frames = 48000;
  lr.window_repeats = 1;
  lr.window_frames = 48000;
  lr.window_lufs_i = -36.25;
  lr.whole_lufs_i = -36.25;
  cli::SpacingEar ear;
  ear.min_distance_hz = 118.0;
  ear.margin_hz = 68.0;
  ear.component_1 = 0;
  ear.component_2 = 35;
  ear.pair = "x";
  cli::SpacingReport spacing;
  spacing.left = ear;
  for (const double linear : {0.5, 0.0, 0.3162277660168379, 1.25}) {
    for (int place = 0; place < 3; ++place) {
      INFO("linear " << shortest(linear) << ", placement " << place);
      cli::Report r = base_report(48000, "final");
      if (place >= 1) r.spacing = spacing;
      if (place == 2) r.loudness = lr;
      r.assertions.push_back(cli::true_peak_assertion(row, linear));
      const std::string without = cli::report_json(r);
      CHECK(without.find("\"true_peak\": {") == std::string::npos);
      cli::TruePeakReport t;
      t.linear = linear;
      t.dbtp = cli::true_peak_dbtp(linear);
      r.true_peak = t;
      const std::string with = cli::report_json(r);
      const std::string want = insert_before_key(without, true_peak_block(t.linear, t.dbtp));
      INFO(with << "\nwant:\n" << want);
      CHECK(with == want);
      CHECK(with.find("inf") == std::string::npos);
      const json::Value v = parse_ok(with);
      for (const std::string& p : h::report_problems(v)) {
        UNSCOPED_INFO(p);
      }
      CHECK(h::report_problems(v).empty());
      r.true_peak.reset();
      CHECK(cli::report_json(r) == without);
    }
  }
}

#else

TEST_CASE("true peak meter is implemented", "[true-peak]") {
  FAIL("not implemented: cli/true_peak.hpp (TruePeakMeter, true_peak_dbtp), cli::true_peak_step, "
       "cli::TruePeakReport, Report::true_peak, and cli::true_peak_assertion (Story 4.3)");
}

#endif
