// Loudness meter of the command-line renderer (Story 4.1;
// docs/signal-spec.md, Loudness). No render: the meter on signals made
// here, the window rule on frame numbers, and the report member.
//
// Contracts (spec Implementation Notes, C++ meter and Report): new
// cli/loudness.hpp in arcani_cli_core, namespace arcani::cli:
//   struct Biquad { double b0, b1, b2, a1, a2; };
//   struct KWeighting { Biquad shelf; Biquad highpass; };
//   KWeighting k_weighting(std::uint32_t fs);  // std::invalid_argument unless fs is a positive multiple of 10
//   class LoudnessMeter {
//    public:
//     explicit LoudnessMeter(std::uint32_t fs);              // throws as k_weighting
//     void add(std::span<const double> interleaved_stereo);  // odd size: std::invalid_argument
//     std::uint64_t frames() const noexcept;
//     std::uint64_t block_count() const noexcept;            // J
//     double integrated(bool gating = true) const;           // LUFS-I, -inf when no block passes
//   };
//   struct LoudnessWindow { bool accepted; std::uint64_t start_frame, body_frames, repeats, window_frames; };
//   LoudnessWindow loudness_window(const arc_loop_frames& loop, std::uint64_t end_frame,
//                                  std::uint64_t min_frames) noexcept;
//   std::uint64_t loudness_window_min_frames(const Row& row, std::uint32_t fs);  // TableError unless unit "s",
//                                                                                // finite, > 0
//   std::string loudness_window_limit(const Row& row);  // ">= 60 s (row loudness-window-min)"
// cli/report.hpp: struct LoudnessReport { std::uint64_t window_start_frame,
// window_body_frames, window_repeats, window_frames; double window_lufs_i,
// whole_lufs_i; }; Report gains std::optional<LoudnessReport> loudness after
// preview; report_json writes it after preview (or spacing, loop, frames)
// and before determinism_key, -inf as null.
//
// Vectors come from the generated spec_tables.hpp (kLoudness_*,
// kLoudnessCoefficients, kLoudnessBlocks, kTech3341, kLoudnessWindowCases,
// kLoudnessWindows); the rows loudness-meter-calibration and
// loudness-window-min from the tables through the assertion call. The
// Tech 3341 cases are synthesized here by the spec rule (Loudness,
// Calibration, Signal); no EBU file is read. Must-fail cases are made here
// by doctoring a coefficient, a reading, a vector, or a Row.
//
// The report check of the harness (cli_helpers.hpp report_problems with a
// loudness member) runs now; until cli/loudness.hpp exists the rest of the
// file compiles to one failing test case, so the rest of the suite still
// runs.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#include "cli_helpers.hpp"
#include "json/value.hpp"

#include <string>
#include <utility>
#include <vector>

namespace h = arcani::test::cli;
namespace json = arcani::json;

namespace {

json::Value parse_loudness_text(const std::string& text) {
  json::ParseResult r = json::parse(text);
  INFO("JSON: " << text);
  REQUIRE(r.value.has_value());
  return *r.value;
}

std::string replaced_in(const std::string& text, const std::string& from, const std::string& to) {
  const auto at = text.find(from);
  REQUIRE(at != std::string::npos);
  std::string out = text;
  out.replace(at, from.size(), to);
  return out;
}

// A looping --loudness report (starter-focus-layers.json at 48 kHz, its
// window numbers from Vectors: loudness windows; the readings an example).
const char* const kGoodLoudnessReport = R"({
  "engine_version": "0.0.1",
  "seed": 42,
  "sample_rate": 48000,
  "mode": "measure",
  "frames": 129600000,
  "loop": {
    "opening_end_frame": 2880000,
    "seam_frames": [8640000, 14400000],
    "end_frame": 129600000
  },
  "spacing": {
    "left": {"min_distance_hz": 118, "margin_hz": 68, "component_1": 0, "component_2": 35, "pair": "x"},
    "right": null
  },
  "loudness": {
    "window_start_frame": 2880000,
    "window_body_frames": 5760000,
    "window_repeats": 1,
    "window_frames": 5760000,
    "window_lufs_i": -3.5,
    "whole_lufs_i": -3.25
  },
  "determinism_key": {
    "recipe_hash": "779404f0e1b2c3d4779404f0e1b2c3d4779404f0e1b2c3d4779404f0e1b2c3d4",
    "asset_hashes": [],
    "engine_version": "0.0.1",
    "sample_rate": 48000
  },
  "assertions": []
})";

// A non-looping --loudness report: the window is the whole render.
const char* const kGoodPlainLoudnessReport = R"({
  "engine_version": "0.0.1",
  "seed": 42,
  "sample_rate": 44100,
  "mode": "measure",
  "frames": 5292000,
  "loudness": {
    "window_start_frame": 0,
    "window_body_frames": 5292000,
    "window_repeats": 1,
    "window_frames": 5292000,
    "window_lufs_i": null,
    "whole_lufs_i": null
  },
  "determinism_key": {
    "recipe_hash": "779404f0e1b2c3d4779404f0e1b2c3d4779404f0e1b2c3d4779404f0e1b2c3d4",
    "asset_hashes": [],
    "engine_version": "0.0.1",
    "sample_rate": 44100
  },
  "assertions": []
})";

}  // namespace

TEST_CASE("report check: a loudness report passes, doctored loudness members fail", "[loudness][report][mustfail]") {
  const std::string good = kGoodLoudnessReport;
  for (const std::string& p : h::report_problems(parse_loudness_text(good))) {
    UNSCOPED_INFO(p);
  }
  CHECK(h::report_problems(parse_loudness_text(good)).empty());
  const std::string spacing_block = R"(
  "spacing": {
    "left": {"min_distance_hz": 118, "margin_hz": 68, "component_1": 0, "component_2": 35, "pair": "x"},
    "right": null
  },)";
  CHECK(h::report_problems(parse_loudness_text(replaced_in(good, spacing_block, ""))).empty());
  // k = 3 of a 25 s body at 48 kHz.
  CHECK(h::report_problems(parse_loudness_text(replaced_in(
                               replaced_in(replaced_in(good, R"("window_body_frames": 5760000)",
                                                       R"("window_body_frames": 1200000)"),
                                           R"("window_repeats": 1)", R"("window_repeats": 3)"),
                               R"("window_frames": 5760000)", R"("window_frames": 3600000)")))
            .empty());
  const std::string plain = kGoodPlainLoudnessReport;
  for (const std::string& p : h::report_problems(parse_loudness_text(plain))) {
    UNSCOPED_INFO(p);
  }
  CHECK(h::report_problems(parse_loudness_text(plain)).empty());
  CHECK(h::report_problems(parse_loudness_text(replaced_in(
                               replaced_in(plain, R"("window_lufs_i": null)", R"("window_lufs_i": -12.5)"),
                               R"("whole_lufs_i": null)", R"("whole_lufs_i": -12.5)")))
            .empty());

  const std::vector<std::pair<std::string, std::string>> doctors = {
      {R"("window_repeats": 1)", R"("window_repeats": 0)"},
      {R"("window_repeats": 1)", R"("window_repeats": 1.5)"},
      {R"("window_frames": 5760000)", R"("window_frames": 5760001)"},
      {R"("window_body_frames": 5760000)", R"("window_body_frames": 0)"},
      {R"("window_start_frame": 2880000)", R"("window_start_frame": 2879999)"},
      {R"("window_start_frame": 2880000)", R"("window_start_frame": "2880000")"},
      {R"("window_lufs_i": -3.5)", R"("window_lufs_i": "-inf")"},
      {R"("window_lufs_i": -3.5)", R"("window_lufs_i": false)"},
      {R"("whole_lufs_i": -3.25)", R"("whole_lufs_i": "null")"},
      {R"("window_lufs_i": -3.5,
    "whole_lufs_i")", R"("whole_lufs_i")"},
      {R"("whole_lufs_i": -3.25
  })", R"("whole_lufs_i": -3.25,
    "extra": 1
  })"},
      {R"("loudness": {)", R"("loudnes": {)"},
      {R"("end_frame": 129600000)", R"("end_frame": 8000000)"},
  };
  for (const auto& [from, to] : doctors) {
    INFO("doctored: " << from << " -> " << to);
    CHECK_FALSE(h::report_problems(parse_loudness_text(replaced_in(good, from, to))).empty());
  }
  const std::vector<std::pair<std::string, std::string>> plain_doctors = {
      {R"("window_start_frame": 0)", R"("window_start_frame": 1)"},
      {R"("window_body_frames": 5292000,
    "window_repeats": 1,
    "window_frames": 5292000)", R"("window_body_frames": 2646000,
    "window_repeats": 2,
    "window_frames": 5292000)"},
      {R"("window_body_frames": 5292000,
    "window_repeats": 1,
    "window_frames": 5292000)", R"("window_body_frames": 5291999,
    "window_repeats": 1,
    "window_frames": 5291999)"},
      {R"("whole_lufs_i": null)", R"("whole_lufs_i": -12.5)"},
  };
  for (const auto& [from, to] : plain_doctors) {
    INFO("doctored plain: " << from << " -> " << to);
    CHECK_FALSE(h::report_problems(parse_loudness_text(replaced_in(plain, from, to))).empty());
  }
  // loudness after determinism_key, before spacing, and with a preview member.
  const std::string loudness_block = R"(
  "loudness": {
    "window_start_frame": 2880000,
    "window_body_frames": 5760000,
    "window_repeats": 1,
    "window_frames": 5760000,
    "window_lufs_i": -3.5,
    "whole_lufs_i": -3.25
  },)";
  const std::string without = replaced_in(good, loudness_block, "");
  CHECK(h::report_problems(parse_loudness_text(without)).empty());
  CHECK_FALSE(h::report_problems(parse_loudness_text(replaced_in(without, R"(
  "spacing": {)", loudness_block + R"(
  "spacing": {)"))).empty());
  CHECK_FALSE(h::report_problems(parse_loudness_text(replaced_in(without, R"(
  "assertions": [])", loudness_block + R"(
  "assertions": [])"))).empty());
  const std::string preview_block = R"(
  "preview": {
    "signed": false,
    "peak_dbfs": -30,
    "layers_per_ear": 2,
    "gain": 0.015811388300841896,
    "seconds": 2700
  },)";
  CHECK_FALSE(h::report_problems(parse_loudness_text(replaced_in(good, R"(
  "loudness": {)", preview_block + R"(
  "loudness": {)"))).empty());
}

#if defined(ARCANI_HAVE_CLI_CORE) && __has_include("loudness.hpp")

#include "api_helpers.hpp"
#include "loudness.hpp"
#include "preview.hpp"
#include "report.hpp"
#include "spec_tables.hpp"
#include "tables.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <concepts>
#include <cstdint>
#include <cstring>
#include <iterator>
#include <limits>
#include <optional>
#include <span>
#include <stdexcept>
#include <string_view>
#include <system_error>

namespace api = arcani::test::api;
namespace cli = arcani::cli;
namespace spec = arcani::test::spec;
namespace tables = arcani::test::tables;

namespace {

constexpr const char* kCalibrationRow = "loudness-meter-calibration";
constexpr const char* kWindowMinRow = "loudness-window-min";
constexpr double kInf = std::numeric_limits<double>::infinity();
constexpr double kPi = 3.141592653589793;  // the binary64 nearest pi
constexpr double kDoctorLu = 0.2;

const tables::Row& calibration_row() {
  const tables::Row& r = tables::row(kCalibrationRow);
  REQUIRE(r.unit == "LU");
  return r;
}

const tables::Row& window_min_row() {
  const tables::Row& r = tables::row(kWindowMinRow);
  REQUIRE(r.unit == "s");
  return r;
}

// Half a unit in the last decimal place BS.1770 prints (5e-15 for 14
// places): the printed precision of the standard (spec, K-weighting).
double coefficient_bound() { return 0.5 * std::pow(10.0, -static_cast<double>(spec::kLoudness_published_decimals)); }

std::string shortest(double x) {
  char buf[64];
  const auto r = std::to_chars(buf, buf + sizeof buf, x);
  REQUIRE(r.ec == std::errc());
  return std::string(buf, r.ptr);
}

std::vector<std::uint32_t> table_rates() {
  const tables::Row& row = tables::row("sample-rates");
  REQUIRE(row.unit == "Hz");
  std::vector<std::uint32_t> out;
  for (double v : row.values) {
    out.push_back(static_cast<std::uint32_t>(v));
  }
  return out;
}

// ------------------------------------------------------------ coefficients

double coefficient(const cli::KWeighting& k, std::string_view stage, std::string_view name) {
  const cli::Biquad& b = stage == "shelf" ? k.shelf : k.highpass;
  if (name == "b0") return b.b0;
  if (name == "b1") return b.b1;
  if (name == "b2") return b.b2;
  if (name == "a1") return b.a1;
  REQUIRE(name == "a2");
  return b.a2;
}

std::vector<std::string> coefficient_problems(const cli::KWeighting& k, std::uint32_t fs) {
  std::vector<std::string> p;
  const double bound = coefficient_bound();
  for (const auto& v : spec::kLoudnessCoefficients) {
    if (v.fs != fs) {
      continue;
    }
    const double got = coefficient(k, v.stage, v.coefficient);
    const std::string where = std::to_string(fs) + " " + v.stage + " " + v.coefficient + " " + shortest(got);
    if (!(std::fabs(got - v.ideal) <= bound)) p.push_back(where + " is not within the bound of the ideal");
    if (v.has_published && !(std::fabs(got - v.published) <= bound)) {
      p.push_back(where + " is not within the bound of the published value");
    }
  }
  return p;
}

// ------------------------------------------------------------ Tech 3341

const spec::Tech3341Vector& tech_case(int number, std::uint32_t fs) {
  for (const auto& v : spec::kTech3341) {
    if (v.number == number && v.fs == fs) {
      return v;
    }
  }
  FAIL("no Tech 3341 vector for case " << number << " at " << fs);
  return spec::kTech3341[0];
}

// Loudness, Calibration, Signal: x[n] = 10^(P_s / 20) * sin(2 * pi * ((1000 * n)
// mod fs) / fs), both channels, n counted from 0 across every segment.
std::vector<double> tech_signal(const spec::Tech3341Vector& v) {
  std::vector<double> out;
  out.reserve(static_cast<std::size_t>(2 * v.total_frames));
  std::uint64_t n = 0;
  std::uint64_t total = 0;
  for (std::size_t s = 0; s < v.segment_count; ++s) {
    REQUIRE(cli::seconds_to_samples(v.durations_s[s], v.fs) == v.frames[s]);
    total += v.frames[s];
    const double a = std::pow(10.0, v.levels_dbfs[s] / 20.0);
    for (std::uint64_t i = 0; i < v.frames[s]; ++i, ++n) {
      const std::uint64_t r = (std::uint64_t{spec::kLoudness_test_hz} * n) % v.fs;
      const double x = a * std::sin(2.0 * kPi * static_cast<double>(r) / static_cast<double>(v.fs));
      out.push_back(x);
      out.push_back(x);
    }
  }
  REQUIRE(total == v.total_frames);
  return out;
}

std::vector<std::string> calibration_problems(double reading, double want, double tol) {
  std::vector<std::string> p;
  if (!std::isfinite(reading)) {
    p.push_back("reading " + shortest(reading) + " is not finite");
  } else if (!(std::fabs(reading - want) <= tol)) {
    p.push_back("reading " + shortest(reading) + " LUFS is beyond " + shortest(tol) + " LU of " + shortest(want));
  }
  return p;
}

std::uint64_t block_frames(std::uint32_t fs) {
  for (const auto& b : spec::kLoudnessBlocks) {
    if (b.fs == fs) {
      return b.block_frames;
    }
  }
  FAIL("no block vector for " << fs);
  return 0;
}

std::uint64_t step_frames(std::uint32_t fs) {
  for (const auto& b : spec::kLoudnessBlocks) {
    if (b.fs == fs) {
      return b.step_frames;
    }
  }
  FAIL("no block vector for " << fs);
  return 0;
}

std::uint64_t expected_blocks(std::uint64_t t, std::uint32_t fs) {
  const std::uint64_t s = step_frames(fs);
  return t / s >= 3 ? t / s - 3 : 0;
}

// ------------------------------------------------------------ windows

std::vector<std::string> window_problems(const cli::LoudnessWindow& w, bool accepted, std::uint64_t start,
                                         std::uint64_t body, std::uint64_t repeats, std::uint64_t frames) {
  std::vector<std::string> p;
  if (w.accepted != accepted) p.push_back("accepted differs");
  if (w.start_frame != start) p.push_back("start frame differs");
  if (w.body_frames != body) p.push_back("body frames differ");
  if (w.repeats != repeats) p.push_back("repeats differ");
  if (w.window_frames != frames) p.push_back("window frames differ");
  return p;
}

std::vector<std::string> window_problems(const cli::LoudnessWindow& w, const spec::LoudnessWindowCaseVector& v) {
  return window_problems(w, v.accepted, v.start_frame, v.body_frames, v.repeats, v.window_frames);
}

arc_loop_frames loop_of_case(const spec::LoudnessWindowCaseVector& v) {
  arc_loop_frames loop;
  std::memset(&loop, 0, sizeof loop);
  if (v.looping) {
    loop.looping = 1;
    loop.opening_end_frame = cli::seconds_to_samples(v.opening_s, v.fs);
    loop.body_frames = cli::seconds_to_samples(v.body_s, v.fs);
    loop.end_frame = v.end_frame;
    REQUIRE(loop.body_frames >= 1);
    REQUIRE(loop.opening_end_frame + loop.body_frames <= loop.end_frame);
    loop.seam_count = (loop.end_frame - loop.opening_end_frame - 1) / loop.body_frames;
  }
  return loop;
}

}  // namespace

// ------------------------------------------------------------ rows

TEST_CASE("loudness rows: read through the assertion call, equal to the vector constants", "[loudness]") {
  CHECK(calibration_row().value() > 0.0);
  CHECK(window_min_row().value() == spec::kLoudness_window_min_s);
  CHECK(std::string(spec::kLoudness_window_min_row) == kWindowMinRow);
  const tables::Row& period = tables::row("rate-cycle-period");
  CHECK(period.unit == "s");
  CHECK(period.min == period.max);
  CHECK(window_min_row().value() == period.min);
}

// ------------------------------------------------------------ K-weighting

TEST_CASE("k_weighting: every coefficient within the printed precision of the vectors, both rates", "[loudness]") {
  for (std::uint32_t fs : table_rates()) {
    INFO("fs " << fs);
    const cli::KWeighting k = cli::k_weighting(fs);
    std::size_t rows = 0;
    for (const auto& v : spec::kLoudnessCoefficients) {
      if (v.fs == fs) {
        ++rows;
        CHECK(v.has_published == (fs == spec::kLoudness_published_fs));
      }
    }
    CHECK(rows == 10);
    for (const std::string& p : coefficient_problems(k, fs)) {
      UNSCOPED_INFO(p);
    }
    CHECK(coefficient_problems(k, fs).empty());
  }
}

TEST_CASE("k_weighting: must-fail, a coefficient off by 1e-13 fails the bound", "[loudness][mustfail]") {
  const cli::KWeighting good = cli::k_weighting(spec::kLoudness_published_fs);
  REQUIRE(coefficient_problems(good, spec::kLoudness_published_fs).empty());
  for (int stage = 0; stage < 2; ++stage) {
    for (int c = 0; c < 5; ++c) {
      INFO("stage " << stage << " coefficient " << c);
      cli::KWeighting bad = good;
      cli::Biquad& b = stage == 0 ? bad.shelf : bad.highpass;
      double* fields[] = {&b.b0, &b.b1, &b.b2, &b.a1, &b.a2};
      *fields[c] += 1e-13;
      CHECK_FALSE(coefficient_problems(bad, spec::kLoudness_published_fs).empty());
    }
  }
}

TEST_CASE("k_weighting and LoudnessMeter refuse a rate that is not a positive multiple of 10", "[loudness]") {
  for (std::uint32_t fs : {0u, 7u, 44101u, 44105u, 48001u}) {
    INFO("fs " << fs);
    CHECK_THROWS_AS(cli::k_weighting(fs), std::invalid_argument);
    CHECK_THROWS_AS(cli::LoudnessMeter(fs), std::invalid_argument);
  }
  for (std::uint32_t fs : {10u, 8000u, 96000u}) {
    INFO("fs " << fs);
    const cli::KWeighting k = cli::k_weighting(fs);
    CHECK(std::isfinite(k.shelf.b0 + k.shelf.b1 + k.shelf.b2 + k.shelf.a1 + k.shelf.a2));
    CHECK(std::isfinite(k.highpass.b0 + k.highpass.b1 + k.highpass.b2 + k.highpass.a1 + k.highpass.a2));
  }
}

// ------------------------------------------------------------ blocks

TEST_CASE("LoudnessMeter: block and step frames from the vectors, J = floor(T / S) - 3", "[loudness]") {
  for (std::uint32_t fs : table_rates()) {
    INFO("fs " << fs);
    const std::uint64_t b = block_frames(fs);
    const std::uint64_t s = step_frames(fs);
    CHECK(b == cli::seconds_to_samples(spec::kLoudness_block_s, fs));
    CHECK(s * 100 == b * (100 - spec::kLoudness_overlap_percent));
    for (std::uint64_t t : {std::uint64_t{0}, std::uint64_t{1}, b - 1, b, b + s - 1, b + s, b + 3 * s + 7,
                            std::uint64_t{10} * fs}) {
      INFO("T " << t);
      std::vector<double> x(static_cast<std::size_t>(2 * t));
      for (std::size_t i = 0; i < x.size(); ++i) {
        x[i] = 0.25 * std::sin(0.001 * static_cast<double>(i * 37 % 1000));
      }
      cli::LoudnessMeter m(fs);
      m.add(std::span<const double>(x));
      CHECK(m.frames() == t);
      CHECK(m.block_count() == expected_blocks(t, fs));
    }
  }
}

TEST_CASE("LoudnessMeter: an odd number of samples throws, an empty span is a no-op", "[loudness]") {
  cli::LoudnessMeter m(48000);
  const std::vector<double> three = {0.1, 0.2, 0.3};
  CHECK_THROWS_AS(m.add(std::span<const double>(three)), std::invalid_argument);
  m.add(std::span<const double>());
  CHECK(m.frames() == 0);
  CHECK(m.block_count() == 0);
}

// ------------------------------------------------------------ Tech 3341

TEST_CASE("LoudnessMeter: Tech 3341 cases 1 to 5 at both rates within row loudness-meter-calibration",
          "[loudness]") {
  const double tol = calibration_row().value();
  std::size_t cases = 0;
  for (std::uint32_t fs : table_rates()) {
    for (const auto& v : spec::kTech3341) {
      if (v.fs != fs) {
        continue;
      }
      ++cases;
      INFO("case " << v.number << " (" << v.tests << ") at " << fs);
      const std::vector<double> x = tech_signal(v);
      cli::LoudnessMeter m(fs);
      m.add(std::span<const double>(x));
      CHECK(m.frames() == v.total_frames);
      CHECK(m.block_count() == expected_blocks(v.total_frames, fs));
      const double gated = m.integrated();
      const double ungated = m.integrated(false);
      INFO("gated " << shortest(gated) << ", gating off " << shortest(ungated));
      CHECK(calibration_problems(gated, v.expected_lufs, tol).empty());
      CHECK(calibration_problems(gated, v.ideal_gated, tol).empty());
      CHECK(calibration_problems(ungated, v.ideal_ungated, tol).empty());
      bool listed = false;
      for (int c : spec::kLoudness_gating_cases) {
        listed = listed || c == v.number;
      }
      CHECK(listed == v.gating_case);
      if (v.gating_case) {
        // Must-fail: gating off fails the relative and absolute gate cases.
        CHECK_FALSE(calibration_problems(ungated, v.expected_lufs, tol).empty());
      } else {
        CHECK(calibration_problems(ungated, v.expected_lufs, tol).empty());
        CHECK(calibration_problems(ungated, gated, tol).empty());
      }
      // Must-fail: the reading moved 0.2 LU.
      CHECK_FALSE(calibration_problems(gated + kDoctorLu, v.expected_lufs, tol).empty());
      CHECK_FALSE(calibration_problems(gated - kDoctorLu, v.expected_lufs, tol).empty());
    }
  }
  CHECK(cases == 10);
}

TEST_CASE("LoudnessMeter: Tech 3341 case 1 with the right channel silent reads 10 log10(2) LU lower",
          "[loudness][mustfail]") {
  // Different channels: a meter that reads one channel twice or drops one
  // fails here, where the in-phase cases cannot tell.
  const double tol = calibration_row().value();
  for (std::uint32_t fs : table_rates()) {
    INFO("case 1, right channel silent, at " << fs);
    const spec::Tech3341Vector& v = tech_case(1, fs);
    std::vector<double> x = tech_signal(v);
    for (std::size_t i = 1; i < x.size(); i += 2) {
      x[i] = 0.0;
    }
    const double want = v.expected_lufs - 10.0 * std::log10(2.0);
    cli::LoudnessMeter m(fs);
    m.add(std::span<const double>(x));
    const double reading = m.integrated();
    INFO("reading " << shortest(reading));
    CHECK(calibration_problems(reading, want, tol).empty());
    CHECK(calibration_problems(reading, v.ideal_gated - 10.0 * std::log10(2.0), tol).empty());
    // Must-fail, doctored in the harness: the left channel read twice.
    std::vector<double> doubled = x;
    for (std::size_t i = 1; i < doubled.size(); i += 2) {
      doubled[i] = doubled[i - 1];
    }
    cli::LoudnessMeter d(fs);
    d.add(std::span<const double>(doubled));
    CHECK_FALSE(calibration_problems(d.integrated(), want, tol).empty());
  }
}

TEST_CASE("LoudnessMeter: the same samples in any chunk sizes give the same bits", "[loudness]") {
  for (std::uint32_t fs : table_rates()) {
    INFO("fs " << fs);
    const spec::Tech3341Vector& v = tech_case(5, fs);
    const std::vector<double> x = tech_signal(v);
    cli::LoudnessMeter whole(fs);
    whole.add(std::span<const double>(x));
    const std::size_t sizes[] = {1, 7, 4409, 4411, 17641, 2, 19201, 3, 100003};
    cli::LoudnessMeter chunks(fs);
    std::size_t at = 0;
    std::size_t i = 0;
    const std::size_t frames = x.size() / 2;
    while (at < frames) {
      const std::size_t n = std::min(sizes[i++ % std::size(sizes)], frames - at);
      chunks.add(std::span<const double>(x.data() + 2 * at, 2 * n));
      at += n;
    }
    CHECK(chunks.frames() == whole.frames());
    CHECK(chunks.block_count() == whole.block_count());
    CHECK(api::bits(chunks.integrated()) == api::bits(whole.integrated()));
    CHECK(api::bits(chunks.integrated(false)) == api::bits(whole.integrated(false)));
  }
}

TEST_CASE("LoudnessMeter: silence, a signal shorter than one block, and every block below -70 read -inf",
          "[loudness]") {
  for (std::uint32_t fs : table_rates()) {
    INFO("fs " << fs);
    {
      cli::LoudnessMeter m(fs);
      CHECK(m.integrated() == -kInf);
      CHECK(m.integrated(false) == -kInf);
    }
    {
      const std::vector<double> zeros(static_cast<std::size_t>(2 * 10 * fs), 0.0);
      cli::LoudnessMeter m(fs);
      m.add(std::span<const double>(zeros));
      CHECK(m.block_count() == expected_blocks(10 * fs, fs));
      CHECK(m.integrated() == -kInf);
      CHECK(m.integrated(false) == -kInf);
    }
    const std::vector<double> tone = tech_signal(tech_case(1, fs));
    {
      const std::uint64_t short_frames = block_frames(fs) - 1;
      cli::LoudnessMeter m(fs);
      m.add(std::span<const double>(tone.data(), static_cast<std::size_t>(2 * short_frames)));
      CHECK(m.block_count() == 0);
      CHECK(m.integrated() == -kInf);
      CHECK(m.integrated(false) == -kInf);
    }
    {
      // -80 dBFS: every block below the absolute gate.
      std::vector<double> quiet(tone.begin(), tone.begin() + static_cast<std::ptrdiff_t>(2 * 5 * fs));
      const double g = std::pow(10.0, (-80.0 + 23.0) / 20.0);
      for (double& s : quiet) {
        s *= g;
      }
      cli::LoudnessMeter m(fs);
      m.add(std::span<const double>(quiet));
      CHECK(m.integrated() == -kInf);
      CHECK(std::isfinite(m.integrated(false)));
      CHECK(m.integrated(false) < spec::kLoudness_absolute_gate_lufs);
    }
  }
}

// ------------------------------------------------------------ window

TEST_CASE("loudness_window_min_frames and loudness_window_limit from the row", "[loudness]") {
  const tables::Row& row = window_min_row();
  for (const auto& v : spec::kLoudnessWindowCases) {
    INFO(v.name << " at " << v.fs);
    CHECK(cli::loudness_window_min_frames(row, v.fs) == v.min_frames);
    CHECK(cli::loudness_window_min_frames(row, v.fs) == cli::seconds_to_samples(row.value(), v.fs));
  }
  CHECK(cli::loudness_window_limit(row) == spec::kLoudness_window_limit);
  CHECK(cli::loudness_window_limit(row) == ">= " + row.value_text + " s (row " + row.id + ")");
  for (const auto& v : spec::kLoudnessWindowCases) {
    if (!v.accepted) {
      CHECK(std::string(v.limit) == cli::loudness_window_limit(row));
      CHECK(std::string(v.rule) == spec::kLoudness_window_rule);
      CHECK(std::string(v.parameter) == spec::kLoudness_window_parameter);
    }
  }
  // A doctored valid value passes through.
  tables::Row other = row;
  other.value_text = "90";
  other.values = {90.0};
  CHECK(cli::loudness_window_min_frames(other, 44100) == 90u * 44100u);
  CHECK(cli::loudness_window_limit(other) == ">= 90 s (row loudness-window-min)");
}

TEST_CASE("loudness_window_min_frames: must-fail, a doctored row is a table error", "[loudness][mustfail]") {
  const tables::Row& row = window_min_row();
  {
    tables::Row bad = row;
    bad.unit = "min";
    CHECK_THROWS_AS(cli::loudness_window_min_frames(bad, 48000), tables::TableError);
  }
  for (double value : {0.0, -60.0, std::numeric_limits<double>::quiet_NaN(), kInf, -kInf}) {
    INFO("value " << value);
    tables::Row bad = row;
    bad.values = {value};
    bad.value_text = shortest(value);
    CHECK_THROWS_AS(cli::loudness_window_min_frames(bad, 48000), tables::TableError);
  }
  {
    tables::Row bad = row;
    bad.values = {60.0, 120.0};
    bad.value_text = "60 120";
    CHECK_THROWS_AS(cli::loudness_window_min_frames(bad, 48000), tables::TableError);
  }
}

TEST_CASE("loudness_window: every window rule vector", "[loudness]") {
  for (const auto& v : spec::kLoudnessWindowCases) {
    INFO(v.name << " at " << v.fs);
    CHECK(cli::seconds_to_samples(v.length_s, v.fs) == v.end_frame);
    const std::uint64_t min_frames = cli::loudness_window_min_frames(window_min_row(), v.fs);
    REQUIRE(min_frames == v.min_frames);
    const arc_loop_frames loop = loop_of_case(v);
    const cli::LoudnessWindow w = cli::loudness_window(loop, v.end_frame, min_frames);
    for (const std::string& p : window_problems(w, v)) {
      UNSCOPED_INFO(p);
    }
    CHECK(window_problems(w, v).empty());
    if (v.accepted) {
      CHECK(api::bits(static_cast<double>(v.window_frames) / static_cast<double>(v.fs)) == api::bits(v.window_s));
      CHECK(w.window_frames >= min_frames);
      if (v.looping) {
        CHECK(w.start_frame == loop.opening_end_frame);
        CHECK(w.body_frames == loop.body_frames);
        CHECK((w.repeats - 1) * w.body_frames < min_frames);
      }
    } else {
      CHECK_FALSE(v.looping);
      CHECK(v.end_frame < min_frames);
      CHECK(shortest(static_cast<double>(v.end_frame) / static_cast<double>(v.fs)) == v.value);
    }
  }
}

TEST_CASE("loudness_window: the agreement and rejected fixture windows from the compiled plans", "[loudness]") {
  for (const auto& v : spec::kLoudnessWindows) {
    INFO(v.fixture << " at " << v.fs);
    api::PlanPtr plan = api::compile_ok(api::valid(v.fixture), api::options(ARC_MODE_MEASURE, v.fs));
    const std::uint64_t n = arc_plan_frame_count(plan.get());
    CHECK(n == v.end_frame);
    arc_loop_frames loop;
    std::memset(&loop, 0, sizeof loop);
    arc_error e;
    api::poison(e);
    REQUIRE(arc_plan_loop(plan.get(), &loop, &e) == ARC_OK);
    CHECK((loop.looping != 0) == v.looping);
    const cli::LoudnessWindow w =
        cli::loudness_window(loop, n, cli::loudness_window_min_frames(window_min_row(), v.fs));
    CHECK(window_problems(w, v.accepted, v.start_frame, v.body_frames, v.repeats, v.window_frames).empty());
  }
}

TEST_CASE("loudness_window: must-fail, a window off by one frame fails", "[loudness][mustfail]") {
  for (const auto& v : spec::kLoudnessWindowCases) {
    if (!v.accepted || !v.looping || v.repeats < 2) {
      continue;
    }
    INFO(v.name << " at " << v.fs);
    const std::uint64_t min_frames = cli::loudness_window_min_frames(window_min_row(), v.fs);
    const cli::LoudnessWindow w = cli::loudness_window(loop_of_case(v), v.end_frame, min_frames);
    REQUIRE(window_problems(w, v).empty());
    spec::LoudnessWindowCaseVector bad = v;
    bad.window_frames += 1;
    CHECK_FALSE(window_problems(w, bad).empty());
    bad = v;
    bad.start_frame += 1;
    CHECK_FALSE(window_problems(w, bad).empty());
    bad = v;
    bad.repeats -= 1;
    CHECK_FALSE(window_problems(w, bad).empty());
    // One frame short of W_min without a loop is rejected, at W_min accepted.
    arc_loop_frames none;
    std::memset(&none, 0, sizeof none);
    CHECK_FALSE(cli::loudness_window(none, min_frames - 1, min_frames).accepted);
    CHECK(window_problems(cli::loudness_window(none, min_frames - 1, min_frames), false, 0, 0, 0, 0).empty());
    CHECK(window_problems(cli::loudness_window(none, min_frames, min_frames), true, 0, min_frames, 1, min_frames)
              .empty());
  }
}

// ------------------------------------------------------------ report

namespace {

template <class R>
concept ReportHasLoudness = requires(R r) {
  { r.loudness.has_value() } -> std::convertible_to<bool>;
  r.loudness->window_start_frame;
  r.loudness->window_body_frames;
  r.loudness->window_repeats;
  r.loudness->window_frames;
  r.loudness->window_lufs_i;
  r.loudness->whole_lufs_i;
  r.loudness.reset();
};

cli::Report base_report(std::uint64_t frames) {
  cli::Report r;
  r.engine_version = "0.0.1";
  r.seed = 42;
  r.sample_rate = 48000;
  r.mode = "measure";
  r.frames = frames;
  r.determinism_key.recipe_hash = std::string(64, 'a');
  r.determinism_key.engine_version = r.engine_version;
  r.determinism_key.sample_rate = r.sample_rate;
  cli::Assertion na;
  na.name = "render speed";
  na.row = "render-speed";
  na.threshold = 20.0;
  na.unit = "times real time";
  na.result = cli::Result::not_applicable;
  na.note = "not the reference machine";
  r.assertions = {na};
  return r;
}

std::string reading_text(double x) { return x == -kInf ? std::string("null") : shortest(x); }

std::string loudness_block(std::uint64_t start, std::uint64_t body, std::uint64_t repeats, std::uint64_t frames,
                           double window, double whole) {
  return std::string("  \"loudness\": {\n") + "    \"window_start_frame\": " + std::to_string(start) + ",\n" +
         "    \"window_body_frames\": " + std::to_string(body) + ",\n" + "    \"window_repeats\": " +
         std::to_string(repeats) + ",\n" + "    \"window_frames\": " + std::to_string(frames) + ",\n" +
         "    \"window_lufs_i\": " + reading_text(window) + ",\n" + "    \"whole_lufs_i\": " + reading_text(whole) +
         "\n" + "  },\n";
}

std::string insert_before_key(const std::string& text, const std::string& block) {
  const std::string key = "  \"determinism_key\": {";
  const auto at = text.find(key);
  REQUIRE(at != std::string::npos);
  std::string out = text;
  out.insert(at, block);
  return out;
}

const spec::LoudnessWindowVector& window_vector(std::string_view fixture, std::uint32_t fs) {
  for (const auto& v : spec::kLoudnessWindows) {
    if (fixture == v.fixture && v.fs == fs) {
      return v;
    }
  }
  FAIL("no loudness window vector for " << fixture << " at " << fs);
  return spec::kLoudnessWindows[0];
}

template <class R = cli::Report>
void check_loudness_report() {
  if constexpr (ReportHasLoudness<R>) {
    using LoudnessReport = typename decltype(R::loudness)::value_type;
    const spec::LoudnessWindowVector& focus = window_vector(spec::kLoudness_assertion_fixture, 48000);
    REQUIRE(focus.looping);
    REQUIRE(focus.accepted);
    // The spec's own example (Loudness, Report).
    CHECK(loudness_block(focus.start_frame, focus.body_frames, focus.repeats, focus.window_frames, -3.5, -3.5) ==
          std::string("  \"loudness\": {\n    \"window_start_frame\": 2880000,\n"
                      "    \"window_body_frames\": 5760000,\n    \"window_repeats\": 1,\n"
                      "    \"window_frames\": 5760000,\n    \"window_lufs_i\": -3.5,\n"
                      "    \"whole_lufs_i\": -3.5\n  },\n"));

    cli::SpacingEar ear;
    ear.min_distance_hz = 118.0;
    ear.margin_hz = 68.0;
    ear.component_1 = 0;
    ear.component_2 = 35;
    ear.pair = "x";
    cli::SpacingReport spacing;
    spacing.left = ear;
    cli::LoopReport loop;
    loop.opening_end_frame = focus.start_frame;
    loop.seam_frames = {focus.start_frame + focus.body_frames};
    loop.end_frame = focus.end_frame;
    cli::PreviewReport preview;
    preview.peak_dbfs = -30.0;
    preview.layers_per_ear = 2;
    preview.gain = 0.015811388300841896;
    preview.seconds = 210.0;

    struct Readings {
      double window;
      double whole;
    };
    struct Placement {
      const char* name;
      bool loop;
      bool spacing;
      bool preview;
    };
    for (const Readings& rd : {Readings{-3.5, -3.25}, Readings{-kInf, -kInf}, Readings{-12.125, -kInf},
                               Readings{-0.1 - 0.2, 1e-300}}) {
      for (const Placement& place :
           {Placement{"loop and spacing", true, true, false}, Placement{"loop only", true, false, false},
            Placement{"neither", false, false, false}, Placement{"spacing only", false, true, false},
            Placement{"after preview", true, true, true}}) {
        INFO("placement: " << place.name << ", readings " << shortest(rd.window) << " " << shortest(rd.whole));
        R r = base_report(focus.end_frame);
        LoudnessReport lr;
        if (place.loop) {
          r.loop = loop;
          lr.window_start_frame = focus.start_frame;
          lr.window_body_frames = focus.body_frames;
          lr.window_repeats = focus.repeats;
          lr.window_frames = focus.window_frames;
          lr.window_lufs_i = rd.window;
          lr.whole_lufs_i = rd.whole;
        } else {
          lr.window_start_frame = 0;
          lr.window_body_frames = focus.end_frame;
          lr.window_repeats = 1;
          lr.window_frames = focus.end_frame;
          lr.window_lufs_i = rd.window;
          lr.whole_lufs_i = rd.window;
        }
        if (place.spacing) r.spacing = spacing;
        if (place.preview) r.preview = preview;
        const std::string without = cli::report_json(r);
        CHECK(without.find("\"loudness\"") == std::string::npos);
        r.loudness = lr;
        const std::string with = cli::report_json(r);
        const std::string want =
            insert_before_key(without, loudness_block(lr.window_start_frame, lr.window_body_frames,
                                                      lr.window_repeats, lr.window_frames, lr.window_lufs_i,
                                                      lr.whole_lufs_i));
        INFO(with << "\nwant:\n" << want);
        CHECK(with == want);
        CHECK(with.find("inf") == std::string::npos);
        CHECK(with.find("Infinity") == std::string::npos);
        const json::Value v = parse_loudness_text(with);
        if (!place.preview) {
          for (const std::string& p : h::report_problems(v)) {
            UNSCOPED_INFO(p);
          }
          CHECK(h::report_problems(v).empty());
        }
        // Removed again: the bytes of the report without it.
        r.loudness.reset();
        CHECK(cli::report_json(r) == without);
      }
    }
  } else {
    FAIL("not implemented: cli::Report has no std::optional<cli::LoudnessReport> loudness (Story 4.1)");
  }
}

}  // namespace

TEST_CASE("report_json writes the loudness member before determinism_key, null for -inf, and nothing without it",
          "[loudness][report]") {
  check_loudness_report();
}

#else

TEST_CASE("loudness meter is implemented", "[loudness]") {
  FAIL("not implemented: cli/loudness.hpp (k_weighting, LoudnessMeter, loudness_window, "
       "loudness_window_min_frames, loudness_window_limit) and cli::Report::loudness (Story 4.1)");
}

#endif
