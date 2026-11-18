// Listening preview helpers of the command-line renderer (Story 3.3;
// docs/signal-spec.md, Preview). No render: compiles and pure functions only.
//
// Contracts (spec Implementation Notes, CLI helpers and Report): new
// cli/preview.hpp in arcani_cli_core, namespace arcani::cli:
//   std::uint64_t seconds_to_samples(double t_s, std::uint32_t fs) noexcept;
//   bool preview_peak_valid(double peak_dbfs) noexcept;
//   double preview_amplitude(double peak_dbfs);           // throws TableError
//   double preview_gain(double peak_dbfs, std::uint32_t layers_max);  // throws
//   struct PreviewRows { double length_s, seam_tail_s, peak_dbfs; };
//   PreviewRows preview_rows(const Row& length, const Row& seam_tail, const Row& peak);
//   struct PreviewLayers { std::uint32_t left, right; std::uint32_t max() const noexcept; };
//   bool preview_layers(const arc_plan* plan, PreviewLayers& out, std::string& rule);
//   std::uint64_t preview_frames(const arc_loop_frames& loop, std::uint64_t end_frame,
//                                std::uint64_t length_frames, std::uint64_t tail_frames) noexcept;
//   void apply_gain(std::span<double> interleaved, double g) noexcept;
// cli/report.hpp: struct PreviewReport { double peak_dbfs; std::uint32_t
// layers_per_ear; double gain; double seconds; }; Report gains
// std::optional<PreviewReport> preview after spacing; report_json writes it
// after spacing (or loop, or frames) and before determinism_key.
//
// Vectors come from the generated spec_tables.hpp (kPreviewGains,
// kPreviewLayers, kPreviewFrames, kPreview_*, kLoopWholeSamples); the rows
// preview-length, preview-seam-tail, and preview-peak-level from the tables
// through the assertion call. The kPreview_* row constants are cross-checked
// against the rows, never used in their place. Must-fail cases are made here
// by doctoring a vector, a Row, or an expected text.
//
// The report check of the harness (cli_helpers.hpp report_problems with a
// preview member) runs now; until cli/preview.hpp exists the rest of the
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

json::Value parse_preview_text(const std::string& text) {
  json::ParseResult r = json::parse(text);
  INFO("JSON: " << text);
  REQUIRE(r.value.has_value());
  return *r.value;
}

std::string replaced_text(const std::string& text, const std::string& from, const std::string& to) {
  const auto at = text.find(from);
  REQUIRE(at != std::string::npos);
  std::string out = text;
  out.replace(at, from.size(), to);
  return out;
}

// A looping preview report: frames F below the loop's end N, the spacing
// block, then preview. seconds = 9261000 / 44100 = 210 exactly.
const char* const kGoodPreviewReport = R"({
  "engine_version": "0.0.1",
  "seed": 42,
  "sample_rate": 44100,
  "mode": "measure",
  "frames": 9261000,
  "loop": {
    "opening_end_frame": 2646000,
    "seam_frames": [7938000, 13230000],
    "end_frame": 119070000
  },
  "spacing": {
    "left": {"min_distance_hz": 118, "margin_hz": 68, "component_1": 0, "component_2": 35, "pair": "x"},
    "right": null
  },
  "preview": {
    "signed": false,
    "peak_dbfs": -30,
    "layers_per_ear": 2,
    "gain": 0.015811388300841896,
    "seconds": 210
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

TEST_CASE("report check: a preview report passes, doctored preview members fail", "[preview][report][mustfail]") {
  const std::string good = kGoodPreviewReport;
  for (const std::string& p : h::report_problems(parse_preview_text(good))) {
    UNSCOPED_INFO(p);
  }
  CHECK(h::report_problems(parse_preview_text(good)).empty());
  // Placement without spacing, and without loop and spacing.
  const std::string spacing_block = R"(
  "spacing": {
    "left": {"min_distance_hz": 118, "margin_hz": 68, "component_1": 0, "component_2": 35, "pair": "x"},
    "right": null
  },)";
  const std::string loop_block = R"(
  "loop": {
    "opening_end_frame": 2646000,
    "seam_frames": [7938000, 13230000],
    "end_frame": 119070000
  },)";
  const std::string loop_only = replaced_text(good, spacing_block, "");
  CHECK(h::report_problems(parse_preview_text(loop_only)).empty());
  const std::string neither = replaced_text(loop_only, loop_block, "");
  CHECK(h::report_problems(parse_preview_text(neither)).empty());
  const std::vector<std::pair<std::string, std::string>> doctors = {
      {R"("signed": false)", R"("signed": true)"},
      {R"("signed": false)", R"("signed": "false")"},
      {R"("signed": false)", R"("signed": 0)"},
      {R"("signed": false,
    "peak_dbfs")", R"("peak_dbfs")"},
      {R"("peak_dbfs": -30)", R"("peak_dbfs": 10)"},
      {R"("layers_per_ear": 2)", R"("layers_per_ear": 2.5)"},
      {R"("layers_per_ear": 2)", R"("layers_per_ear": -1)"},
      {R"("gain": 0.015811388300841896)", R"("gain": 0)"},
      {R"("gain": 0.015811388300841896)", R"("gain": "0.015811388300841896")"},
      {R"("seconds": 210)", R"("seconds": 210.00000000000003)"},
      {R"("seconds": 210)", R"("seconds": 2700)"},
      {R"("seconds": 210
  })", R"("seconds": 210,
    "extra": 1
  })"},
      {R"("preview": {)", R"("previews": {)"},
      {R"("end_frame": 119070000)", R"("end_frame": 9260999)"},
  };
  for (const auto& [from, to] : doctors) {
    INFO("doctored: " << from << " -> " << to);
    CHECK_FALSE(h::report_problems(parse_preview_text(replaced_text(good, from, to))).empty());
  }
  // preview before spacing, and after determinism_key.
  {
    const std::string preview_block = R"(
  "preview": {
    "signed": false,
    "peak_dbfs": -30,
    "layers_per_ear": 2,
    "gain": 0.015811388300841896,
    "seconds": 210
  },)";
    std::string moved = replaced_text(good, preview_block, "");
    moved = replaced_text(moved, R"(
  "spacing": {)", preview_block + R"(
  "spacing": {)");
    CHECK_FALSE(h::report_problems(parse_preview_text(moved)).empty());
    std::string late = replaced_text(good, preview_block, "");
    late = replaced_text(late, R"(  "assertions": [])", R"(  "preview": {"signed": false, "peak_dbfs": -30, "layers_per_ear": 2, "gain": 0.015811388300841896, "seconds": 210},
  "assertions": [])");
    CHECK_FALSE(h::report_problems(parse_preview_text(late)).empty());
  }
  // Without preview, the loop end must equal frames again.
  {
    const std::string preview_block = R"(
  "preview": {
    "signed": false,
    "peak_dbfs": -30,
    "layers_per_ear": 2,
    "gain": 0.015811388300841896,
    "seconds": 210
  },)";
    CHECK_FALSE(h::report_problems(parse_preview_text(replaced_text(good, preview_block, ""))).empty());
  }
}

#if defined(ARCANI_HAVE_CLI_CORE) && __has_include("preview.hpp")

#include "api_helpers.hpp"
#include "preview.hpp"
#include "report.hpp"
#include "spec_tables.hpp"
#include "tables.hpp"

#include <cerrno>
#include <charconv>
#include <cmath>
#include <concepts>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <optional>
#include <span>
#include <string_view>
#include <system_error>

namespace api = arcani::test::api;
namespace cli = arcani::cli;
namespace spec = arcani::test::spec;
namespace tables = arcani::test::tables;

namespace {

// ------------------------------------------------------------ rows

constexpr const char* kLengthRow = "preview-length";
constexpr const char* kSeamTailRow = "preview-seam-tail";
constexpr const char* kPeakRow = "preview-peak-level";

const tables::Row& length_row() {
  const tables::Row& r = tables::row(kLengthRow);
  REQUIRE(r.unit == "s");
  return r;
}

const tables::Row& seam_tail_row() {
  const tables::Row& r = tables::row(kSeamTailRow);
  REQUIRE(r.unit == "s");
  return r;
}

const tables::Row& peak_row() {
  const tables::Row& r = tables::row(kPeakRow);
  REQUIRE(r.unit == "dBFS");
  return r;
}

double peak_dbfs() { return peak_row().value(); }

// ------------------------------------------------------------ helpers

std::uint64_t bits_of(double x) { return api::bits(x); }

// std::strtod, as spacing_helpers.hpp parses numbers: the pinned macOS libc++
// has no floating-point std::from_chars. The whole text must be consumed and
// the value in range.
double parse_double(std::string_view text) {
  const std::string s(text);
  REQUIRE(!s.empty());
  char* end = nullptr;
  errno = 0;
  const double v = std::strtod(s.c_str(), &end);
  REQUIRE(errno == 0);
  REQUIRE(end == s.c_str() + s.size());
  return v;
}

std::string shortest(double x) {
  char buf[64];
  const auto r = std::to_chars(buf, buf + sizeof buf, x);
  REQUIRE(r.ec == std::errc());
  return std::string(buf, r.ptr);
}

arc_mute_ear mute_of(std::string_view mute) {
  if (mute == "left") {
    return ARC_MUTE_LEFT;
  }
  if (mute == "right") {
    return ARC_MUTE_RIGHT;
  }
  REQUIRE(mute == "none");
  return ARC_MUTE_NONE;
}

api::PlanPtr compile_fixture(const char* fixture, std::uint32_t fs, arc_mute_ear mute = ARC_MUTE_NONE) {
  INFO("fixture " << fixture << " at " << fs << " Hz");
  return api::compile_ok(api::valid(fixture), api::options(ARC_MODE_MEASURE, fs, mute));
}

arc_loop_frames loop_of(const arc_plan* plan) {
  arc_loop_frames loop;
  std::memset(&loop, 0, sizeof loop);
  arc_error e;
  api::poison(e);
  REQUIRE(arc_plan_loop(plan, &loop, &e) == ARC_OK);
  return loop;
}

// Problems of a gain against its vector: bits exact, and the ideal within 2
// units in the last place of the vector gain.
std::vector<std::string> gain_problems(double got, const spec::PreviewGainVector& v) {
  std::vector<std::string> p;
  if (bits_of(got) != v.gain_bits) {
    p.push_back("gain bits differ from the vector");
  }
  const double ulp = std::nextafter(v.gain, std::numeric_limits<double>::infinity()) - v.gain;
  if (!(std::fabs(v.ideal - got) <= 2.0 * ulp)) {
    p.push_back("gain is not within 2 ulp of the ideal");
  }
  return p;
}

struct FrameResult {
  std::uint64_t end_frame = 0;
  bool looping = false;
  std::uint64_t opening_end_frame = 0;
  std::uint64_t first_seam_frame = 0;
  std::uint64_t length_frames = 0;
  std::uint64_t tail_frames = 0;
  std::uint64_t preview_frames = 0;
  double seconds = 0.0;
  std::uint32_t layers_max = 0;
  std::uint64_t gain_bits = 0;
};

std::vector<std::string> frame_problems(const FrameResult& r, const spec::PreviewFrameVector& v) {
  std::vector<std::string> p;
  if (r.end_frame != v.end_frame) p.push_back("end frame N differs");
  if (r.looping != v.looping) p.push_back("looping differs");
  if (r.opening_end_frame != v.opening_end_frame) p.push_back("opening end O differs");
  if (r.first_seam_frame != v.first_seam_frame) p.push_back("first body seam O + B differs");
  if (r.length_frames != v.length_frames) p.push_back("L differs");
  if (r.tail_frames != v.tail_frames) p.push_back("T differs");
  if (r.preview_frames != v.preview_frames) p.push_back("preview frames F differ");
  if (bits_of(r.seconds) != bits_of(v.seconds)) p.push_back("seconds F / fs differ");
  if (r.layers_max != v.layers_max) p.push_back("n_max differs");
  if (r.gain_bits != v.gain_bits) p.push_back("gain bits differ");
  return p;
}

FrameResult frames_of(const spec::PreviewFrameVector& v) {
  const cli::PreviewRows rows = cli::preview_rows(length_row(), seam_tail_row(), peak_row());
  api::PlanPtr plan = compile_fixture(v.fixture, v.fs);
  FrameResult r;
  r.end_frame = arc_plan_frame_count(plan.get());
  const arc_loop_frames loop = loop_of(plan.get());
  r.looping = loop.looping != 0;
  if (r.looping) {
    r.opening_end_frame = loop.opening_end_frame;
    r.first_seam_frame = loop.opening_end_frame + loop.body_frames;
  }
  r.length_frames = cli::seconds_to_samples(rows.length_s, v.fs);
  r.tail_frames = cli::seconds_to_samples(rows.seam_tail_s, v.fs);
  r.preview_frames = cli::preview_frames(loop, r.end_frame, r.length_frames, r.tail_frames);
  r.seconds = static_cast<double>(r.preview_frames) / static_cast<double>(v.fs);
  cli::PreviewLayers layers;
  std::string rule;
  REQUIRE(cli::preview_layers(plan.get(), layers, rule));
  r.layers_max = layers.max();
  r.gain_bits = bits_of(cli::preview_gain(rows.peak_dbfs, layers.max()));
  return r;
}

}  // namespace

// ------------------------------------------------------------ rows

TEST_CASE("preview rows: the three rows are read through the assertion call and equal the vector constants",
          "[preview]") {
  CHECK(length_row().value() == spec::kPreview_length_s);
  CHECK(seam_tail_row().value() == spec::kPreview_seam_tail_s);
  CHECK(peak_row().value() == spec::kPreview_peak_dbfs);
  const cli::PreviewRows rows = cli::preview_rows(length_row(), seam_tail_row(), peak_row());
  CHECK(bits_of(rows.length_s) == bits_of(length_row().value()));
  CHECK(bits_of(rows.seam_tail_s) == bits_of(seam_tail_row().value()));
  CHECK(bits_of(rows.peak_dbfs) == bits_of(peak_row().value()));
}

TEST_CASE("preview rows: a doctored peak level row is a table error naming the row and the value",
          "[preview][mustfail]") {
  for (const char* text : spec::kPreview_invalid_peaks) {
    INFO("row preview-peak-level doctored to " << text);
    tables::Row bad = peak_row();
    bad.value_text = text;
    bad.values = {parse_double(text)};
    bool threw = false;
    try {
      (void)cli::preview_rows(length_row(), seam_tail_row(), bad);
    } catch (const tables::TableError& e) {
      threw = true;
      const std::string what = e.what();
      INFO("message: " << what);
      CHECK(what.find(kPeakRow) != std::string::npos);
      CHECK(what.find(text) != std::string::npos);
    }
    CHECK(threw);
  }
  // A doctored valid value passes through (the check is on the value, not the id).
  for (const auto& g : spec::kPreviewGains) {
    tables::Row other = peak_row();
    other.values = {g.peak_dbfs};
    other.value_text = shortest(g.peak_dbfs);
    CHECK(bits_of(cli::preview_rows(length_row(), seam_tail_row(), other).peak_dbfs) == bits_of(g.peak_dbfs));
  }
}

// ------------------------------------------------------------ gain

TEST_CASE("preview gain: every gain vector, bits exact, within 2 ulp of the ideal", "[preview]") {
  for (const auto& v : spec::kPreviewGains) {
    INFO("P " << v.peak_dbfs << " dB, n_max " << v.layers_max);
    CHECK(cli::preview_peak_valid(v.peak_dbfs));
    CHECK(bits_of(cli::preview_amplitude(v.peak_dbfs)) == bits_of(v.amplitude));
    const double g = cli::preview_gain(v.peak_dbfs, v.layers_max);
    for (const std::string& p : gain_problems(g, v)) {
      UNSCOPED_INFO(p);
    }
    CHECK(gain_problems(g, v).empty());
  }
  // The row value is one of the vector peak levels, and the sqrt(10) constant
  // is the binary64 the steps multiply by.
  bool row_has_vector = false;
  for (const auto& v : spec::kPreviewGains) {
    row_has_vector = row_has_vector || v.peak_dbfs == peak_dbfs();
  }
  CHECK(row_has_vector);
  CHECK(bits_of(std::sqrt(10.0)) == bits_of(spec::kPreview_sqrt10));
}

TEST_CASE("preview gain: n_max 0 counts as 1", "[preview]") {
  for (const auto& v : spec::kPreviewGains) {
    if (v.layers_max == 1) {
      INFO("P " << v.peak_dbfs);
      CHECK(bits_of(cli::preview_gain(v.peak_dbfs, 0)) == v.gain_bits);
    }
  }
}

TEST_CASE("preview gain: must-fail, a gain with its last bit flipped or off by 3 ulp fails", "[preview][mustfail]") {
  for (const auto& v : spec::kPreviewGains) {
    INFO("P " << v.peak_dbfs << " dB, n_max " << v.layers_max);
    const std::uint64_t flipped = v.gain_bits ^ 1u;
    double f = 0.0;
    std::memcpy(&f, &flipped, sizeof f);
    CHECK_FALSE(gain_problems(f, v).empty());
    double far = v.gain;
    for (int i = 0; i < 3; ++i) {
      far = std::nextafter(far, std::numeric_limits<double>::infinity());
    }
    CHECK_FALSE(gain_problems(far, v).empty());
    CHECK(gain_problems(v.gain, v).empty());
  }
}

TEST_CASE("preview peak level: invalid values are refused and throw a table error", "[preview][mustfail]") {
  std::vector<double> bad;
  for (const char* text : spec::kPreview_invalid_peaks) {
    bad.push_back(parse_double(text));
  }
  // Just outside the bounds, NaN, and the infinities.
  bad.push_back(std::nextafter(spec::kPreview_peak_max_dbfs, std::numeric_limits<double>::infinity()));
  bad.push_back(std::nextafter(spec::kPreview_peak_min_dbfs, -std::numeric_limits<double>::infinity()));
  bad.push_back(std::nextafter(peak_dbfs(), 0.0));
  bad.push_back(std::numeric_limits<double>::quiet_NaN());
  bad.push_back(std::numeric_limits<double>::infinity());
  bad.push_back(-std::numeric_limits<double>::infinity());
  for (double p : bad) {
    INFO("P " << p);
    CHECK_FALSE(cli::preview_peak_valid(p));
    CHECK_THROWS_AS(cli::preview_amplitude(p), tables::TableError);
    CHECK_THROWS_AS(cli::preview_gain(p, 2), tables::TableError);
  }
  // The bounds themselves are valid, and so is -0.0.
  CHECK(cli::preview_peak_valid(spec::kPreview_peak_min_dbfs));
  CHECK(cli::preview_peak_valid(spec::kPreview_peak_max_dbfs));
  CHECK(cli::preview_peak_valid(-0.0));
  CHECK(cli::preview_peak_valid(peak_dbfs()));
  // The message names the row and the value.
  try {
    (void)cli::preview_amplitude(parse_double(spec::kPreview_invalid_peaks[0]));
    FAIL("no table error");
  } catch (const tables::TableError& e) {
    const std::string what = e.what();
    INFO(what);
    CHECK(what.find(kPeakRow) != std::string::npos);
    CHECK(what.find(spec::kPreview_invalid_peaks[0]) != std::string::npos);
  }
}

// ------------------------------------------------------------ frames

TEST_CASE("seconds_to_samples equals the whole-sample vectors and the preview L and T columns", "[preview]") {
  for (const auto& v : spec::kLoopWholeSamples) {
    INFO("t " << v.t_s);
    CHECK(cli::seconds_to_samples(v.t_s, 44100) == v.n_44100);
    CHECK(cli::seconds_to_samples(v.t_s, 48000) == v.n_48000);
  }
  for (const auto& v : spec::kPreviewFrames) {
    INFO(v.fixture << " at " << v.fs);
    CHECK(cli::seconds_to_samples(length_row().value(), v.fs) == v.length_frames);
    CHECK(cli::seconds_to_samples(seam_tail_row().value(), v.fs) == v.tail_frames);
    CHECK(cli::seconds_to_samples(v.length_s, v.fs) == v.end_frame);
  }
  // Outside the domain: 0.
  for (double t : {-1.0, -0.0 - 1e-300, std::numeric_limits<double>::quiet_NaN(),
                   std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity(), 0x1p64,
                   0x1p70}) {
    INFO("t " << t);
    CHECK(cli::seconds_to_samples(t, 48000) == 0);
  }
}

TEST_CASE("preview frames: every frame vector from the fixture compiled at its rate", "[preview]") {
  for (const auto& v : spec::kPreviewFrames) {
    INFO(v.fixture << " at " << v.fs << " Hz");
    const FrameResult r = frames_of(v);
    for (const std::string& p : frame_problems(r, v)) {
      UNSCOPED_INFO(p);
    }
    CHECK(frame_problems(r, v).empty());
    if (v.looping) {
      CHECK(bits_of(static_cast<double>(r.opening_end_frame) / static_cast<double>(v.fs)) ==
            bits_of(v.opening_end_s));
      CHECK(bits_of(static_cast<double>(r.first_seam_frame) / static_cast<double>(v.fs)) ==
            bits_of(v.first_seam_s));
      // Both seams are inside the preview.
      CHECK(r.opening_end_frame < r.preview_frames);
      CHECK(r.first_seam_frame < r.preview_frames);
    }
  }
}

TEST_CASE("preview frames: must-fail, a frame vector with F + 1 or a wrong seam fails", "[preview][mustfail]") {
  const spec::PreviewFrameVector& v = spec::kPreviewFrames[0];
  REQUIRE(v.looping);
  const FrameResult r = frames_of(v);
  REQUIRE(frame_problems(r, v).empty());
  spec::PreviewFrameVector bad = v;
  bad.preview_frames += 1;
  CHECK_FALSE(frame_problems(r, bad).empty());
  bad = v;
  bad.first_seam_frame += 1;
  CHECK_FALSE(frame_problems(r, bad).empty());
  bad = v;
  bad.gain_bits ^= 1u;
  CHECK_FALSE(frame_problems(r, bad).empty());
}

TEST_CASE("preview frames: a session shorter than the preview is previewed whole", "[preview]") {
  const cli::PreviewRows rows = cli::preview_rows(length_row(), seam_tail_row(), peak_row());
  for (const char* fixture : {api::kBeat6, "theta-gamma-uncoupled.json"}) {
    for (std::uint32_t fs : {44100u, 48000u}) {
      INFO(fixture << " at " << fs);
      api::PlanPtr plan = compile_fixture(fixture, fs);
      const std::uint64_t n = arc_plan_frame_count(plan.get());
      const std::uint64_t l = cli::seconds_to_samples(rows.length_s, fs);
      REQUIRE(n < l);
      CHECK(cli::preview_frames(loop_of(plan.get()), n, l, cli::seconds_to_samples(rows.seam_tail_s, fs)) == n);
    }
  }
  // A looping session with one body pass only (O + B = N) or a cap inside the
  // tail: F = N. A loop with room past the tail: O + B + T.
  arc_loop_frames loop;
  std::memset(&loop, 0, sizeof loop);
  loop.looping = 1;
  loop.opening_end_frame = 100;
  loop.body_frames = 200;
  loop.end_frame = 300;
  CHECK(cli::preview_frames(loop, 300, 1000, 50) == 300);
  loop.end_frame = 320;
  CHECK(cli::preview_frames(loop, 320, 1000, 50) == 320);
  loop.end_frame = 900;
  CHECK(cli::preview_frames(loop, 900, 10, 50) == 350);
  // No loop: min(L, N); L does not apply to a looping recipe.
  loop.looping = 0;
  CHECK(cli::preview_frames(loop, 900, 10, 50) == 10);
  CHECK(cli::preview_frames(loop, 9, 10, 50) == 9);
  CHECK(cli::preview_frames(loop, 0, 10, 50) == 0);
}

// ------------------------------------------------------------ layers

namespace {

std::vector<std::string> layer_problems(const cli::PreviewLayers& got, const spec::PreviewLayerVector& v) {
  std::vector<std::string> p;
  if (got.left != v.left) p.push_back("left count differs");
  if (got.right != v.right) p.push_back("right count differs");
  if (got.max() != v.layers_max) p.push_back("n_max differs");
  return p;
}

}  // namespace

TEST_CASE("preview layers: every layer vector, compiled with its muted ear, at both rates", "[preview]") {
  for (const auto& v : spec::kPreviewLayers) {
    for (std::uint32_t fs : {44100u, 48000u}) {
      INFO(v.name << " (" << v.fixture << ", mute " << v.mute << ") at " << fs);
      api::PlanPtr plan = compile_fixture(v.fixture, fs, mute_of(v.mute));
      cli::PreviewLayers got;
      std::string rule;
      REQUIRE(cli::preview_layers(plan.get(), got, rule));
      for (const std::string& p : layer_problems(got, v)) {
        UNSCOPED_INFO(p);
      }
      CHECK(layer_problems(got, v).empty());
      CHECK(bits_of(cli::preview_gain(peak_dbfs(), got.max())) == v.gain_bits);
      CHECK(bits_of(v.gain) == v.gain_bits);
    }
  }
}

TEST_CASE("preview layers: must-fail, a layer vector with one ear off by one fails", "[preview][mustfail]") {
  for (const auto& v : spec::kPreviewLayers) {
    if (std::string_view(v.mute) == "none") {
      continue;
    }
    INFO(v.name);
    api::PlanPtr plan = compile_fixture(v.fixture, 48000, mute_of(v.mute));
    cli::PreviewLayers got;
    std::string rule;
    REQUIRE(cli::preview_layers(plan.get(), got, rule));
    REQUIRE(layer_problems(got, v).empty());
    spec::PreviewLayerVector bad = v;
    bad.left += 1;
    CHECK_FALSE(layer_problems(got, bad).empty());
    bad = v;
    bad.right = v.right == 0 ? 1 : v.right - 1;
    CHECK_FALSE(layer_problems(got, bad).empty());
    // The same fixture unmuted has a different count in the muted ear.
    api::PlanPtr open = compile_fixture(v.fixture, 48000);
    cli::PreviewLayers both;
    REQUIRE(cli::preview_layers(open.get(), both, rule));
    CHECK_FALSE(layer_problems(both, v).empty());
  }
  cli::PreviewLayers l;
  l.left = 1;
  l.right = 3;
  CHECK(l.max() == 3);
  l.left = 4;
  CHECK(l.max() == 4);
}

// ------------------------------------------------------------ apply_gain

TEST_CASE("apply_gain multiplies every sample by g once, in place", "[preview]") {
  const double g = spec::kPreviewLayers[0].gain;
  const double q = 0x1p-23;
  std::vector<double> s = {0.0,
                           -0.0,
                           std::numeric_limits<double>::quiet_NaN(),
                           1.0,
                           -1.0,
                           2.0,
                           -2.0,
                           8388607.0 * q / g,
                           -8388608.0 * q / g,
                           std::nextafter(8388607.0 * q / g, 0.0),
                           0.5 * q / g,
                           std::numeric_limits<double>::denorm_min(),
                           std::numeric_limits<double>::max(),
                           std::numeric_limits<double>::infinity(),
                           0.1 + 0.2};
  std::vector<double> want;
  for (double x : s) {
    want.push_back(x * g);
  }
  std::vector<double> got = s;
  cli::apply_gain(std::span<double>(got), g);
  REQUIRE(got.size() == want.size());
  for (std::size_t i = 0; i < got.size(); ++i) {
    INFO("sample " << i << " " << s[i]);
    if (std::isnan(want[i])) {
      CHECK(std::isnan(got[i]));
      CHECK(h::spec_quantize_24(got[i]) == 0);
    } else {
      CHECK(bits_of(got[i]) == bits_of(want[i]));
    }
  }
  CHECK(std::signbit(got[1]));
  // Must-fail: g applied twice, or g rounded through float, differs somewhere.
  std::vector<double> twice = got;
  cli::apply_gain(std::span<double>(twice), g);
  CHECK_FALSE(api::same_bytes(twice, got));
  std::vector<double> through_float = s;
  cli::apply_gain(std::span<double>(through_float), static_cast<double>(static_cast<float>(g)));
  CHECK_FALSE(api::same_bytes(through_float, got));
  // An empty span is a no-op.
  cli::apply_gain(std::span<double>(), g);
}

// ------------------------------------------------------------ report

namespace {

template <class R>
concept ReportHasPreview = requires(R r) {
  { r.preview.has_value() } -> std::convertible_to<bool>;
  r.preview->peak_dbfs;
  r.preview->layers_per_ear;
  r.preview->gain;
  r.preview->seconds;
  r.preview.reset();
};

cli::Report base_report() {
  cli::Report r;
  r.engine_version = "0.0.1";
  r.seed = 42;
  r.sample_rate = 48000;
  r.mode = "measure";
  r.frames = 10080000;
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

std::string preview_block(double peak, std::uint32_t layers, double gain, double seconds, const char* signed_text) {
  return std::string("  \"preview\": {\n") + "    \"signed\": " + signed_text + ",\n" +
         "    \"peak_dbfs\": " + shortest(peak) + ",\n" + "    \"layers_per_ear\": " + std::to_string(layers) +
         ",\n" + "    \"gain\": " + shortest(gain) + ",\n" + "    \"seconds\": " + shortest(seconds) + "\n" + "  },\n";
}

std::string insert_before_key(const std::string& text, const std::string& block) {
  const std::string key = "  \"determinism_key\": {";
  const auto at = text.find(key);
  REQUIRE(at != std::string::npos);
  std::string out = text;
  out.insert(at, block);
  return out;
}

template <class R = cli::Report>
void check_preview_report() {
  if constexpr (ReportHasPreview<R>) {
    using PreviewReport = typename decltype(R::preview)::value_type;
    // The Focus preview at 48 kHz from the frame vectors.
    const spec::PreviewFrameVector* focus = nullptr;
    for (const auto& v : spec::kPreviewFrames) {
      if (std::string_view(v.fixture) == spec::kPreview_fixtures[0] && v.fs == spec::kPreview_listening_rate) {
        focus = &v;
      }
    }
    REQUIRE(focus != nullptr);
    REQUIRE(focus->looping);

    cli::SpacingEar ear;
    ear.min_distance_hz = 118.0;
    ear.margin_hz = 68.0;
    ear.component_1 = 0;
    ear.component_2 = 35;
    ear.pair = "x";
    cli::SpacingReport spacing;
    spacing.left = ear;
    cli::LoopReport loop;
    loop.opening_end_frame = focus->opening_end_frame;
    loop.seam_frames = {focus->first_seam_frame};
    loop.end_frame = focus->end_frame;

    PreviewReport pr;
    pr.peak_dbfs = peak_dbfs();
    pr.layers_per_ear = focus->layers_max;
    pr.gain = focus->gain;
    pr.seconds = focus->seconds;
    const std::string block = preview_block(peak_dbfs(), focus->layers_max, focus->gain, focus->seconds, "false");
    // The spec's own example numbers.
    CHECK(block == std::string("  \"preview\": {\n    \"signed\": false,\n    \"peak_dbfs\": -30,\n"
                               "    \"layers_per_ear\": 2,\n    \"gain\": 0.015811388300841896,\n"
                               "    \"seconds\": 210\n  },\n"));

    struct Placement {
      const char* name;
      bool loop;
      bool spacing;
    };
    for (const Placement& place : {Placement{"loop and spacing", true, true}, Placement{"loop only", true, false},
                                   Placement{"neither", false, false}, Placement{"spacing only", false, true}}) {
      INFO("placement: " << place.name);
      R r = base_report();
      r.frames = focus->preview_frames;
      if (place.loop) r.loop = loop;
      if (place.spacing) r.spacing = spacing;
      const std::string without = cli::report_json(r);
      CHECK(without.find("\"preview\"") == std::string::npos);
      r.preview = pr;
      const std::string with = cli::report_json(r);
      const std::string want = insert_before_key(without, block);
      INFO(with << "\nwant:\n" << want);
      CHECK(with == want);
      // Must-fail: the same text with "signed": true is not what is written.
      CHECK(with != insert_before_key(without,
                                      preview_block(peak_dbfs(), focus->layers_max, focus->gain, focus->seconds, "true")));
      const json::Value v = parse_preview_text(with);
      for (const std::string& p : h::report_problems(v)) {
        UNSCOPED_INFO(p);
      }
      CHECK(h::report_problems(v).empty());
      // Removed again: the bytes of the report without it.
      r.preview.reset();
      CHECK(cli::report_json(r) == without);
    }
  } else {
    FAIL("not implemented: cli::Report has no std::optional<cli::PreviewReport> preview (Story 3.3)");
  }
}

}  // namespace

TEST_CASE("report_json writes the preview member before determinism_key, and nothing without it",
          "[preview][report]") {
  check_preview_report();
}

#else

TEST_CASE("preview helpers are implemented", "[preview]") {
  FAIL("not implemented: cli/preview.hpp (seconds_to_samples, preview_peak_valid, preview_amplitude, preview_gain, "
       "preview_rows, preview_layers, preview_frames, apply_gain) and cli::Report::preview (Story 3.3)");
}

#endif
