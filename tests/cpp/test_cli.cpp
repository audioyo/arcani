// arcani-render end to end (Story 1.4). Runs the built executable.
//
// Contract with the build: tests/cpp CMake defines ARCANI_RENDER_PATH (the
// absolute path of the built arcani-render), ARCANI_RECIPES_DIR,
// ARCANI_TEST_DATA_DIR, and ARCANI_TEST_OUT_DIR (a scratch directory in the
// build tree), and makes the test target depend on arcani-render.
//
// Expected behavior (spec decisions Usage, Exit codes, Rate refusal,
// Rejection, WAV layout, Report, Render speed):
//
//   arcani-render --version        prints arc_engine_version(), exit 0
//   arcani-render RECIPE --out WAV [--report JSON] [--rate N] [--mode measure|final]
//     RECIPE first, then the options in any order, each at most once.
//     Defaults: rate 48000, mode measure, report = WAV path with its last
//     extension replaced by .report.json (no extension: .report.json added).
//     exit 0  rendered, every assertion pass or not_applicable
//     exit 1  the engine rejected the recipe or an option (a numeric --rate
//             other than 44100 or 48000 goes to arc_compile and is refused
//             there); no WAV, no report, nothing at the WAV path touched;
//             stderr is exactly one line
//             "rejected: parameter=<p> value=<v> rule=<r> limit=<l>"
//             with the four arc_error fields of the engine
//     exit 2  any other argument shape (missing --out or a value, unknown
//             flag, non-numeric --rate, unknown --mode, a repeated option,
//             a second positional argument, --version with anything else):
//             usage text containing "usage" on stdout or stderr
//     exit 3  file or internal error (unreadable recipe, WAV directory
//             missing): no file at the WAV path
//     exit 4  rendered but an assertion failed; WAV and report written
//   The WAV is written to "<WAV>.partial" and renamed to WAV after the last
//   frame; no ".partial" file remains after any run.
//
// Speed: the CLI reads ARCANI_REFERENCE_MACHINE; these tests set it in their
// own environment (the child inherits it) and restore it afterwards. The
// reference-machine pass case runs only when the test process itself starts
// with ARCANI_REFERENCE_MACHINE=1 (the dev PC); everywhere else it skips, so
// no speed result gates CI.

#if defined(_WIN32) && !defined(_CRT_SECURE_NO_WARNINGS)
#define _CRT_SECURE_NO_WARNINGS  // getenv and fopen are the portable calls here; test code only
#endif

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <charconv>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <optional>
#include <string>
#include <system_error>
#include <vector>

#ifndef ARCANI_RENDER_PATH
#error "ARCANI_RENDER_PATH must be defined by the build (path to arcani-render)"
#endif
#ifndef ARCANI_TEST_OUT_DIR
#error "ARCANI_TEST_OUT_DIR must name a scratch directory in the build tree"
#endif
#ifndef ARCANI_TEST_DATA_DIR
#error "ARCANI_TEST_DATA_DIR must name tests/data"
#endif

#if defined(_WIN32)
#define ARC_POPEN _popen
#define ARC_PCLOSE _pclose
#else
#include <sys/wait.h>
#define ARC_POPEN popen
#define ARC_PCLOSE pclose
#endif

#include "api_helpers.hpp"
#include "cli_helpers.hpp"
#include "determinism_helpers.hpp"
#include "spec_tables.hpp"
#include "json/value.hpp"
#include "tables.hpp"

namespace fs = std::filesystem;
namespace h = arcani::test::cli;
namespace json = arcani::json;
namespace tables = arcani::test::tables;

namespace {

constexpr const char* kEnv = "ARCANI_REFERENCE_MACHINE";

struct RunResult {
  int exit_code = -1;
  std::string out;
  std::string err;
};

std::string quote(const std::string& s) { return "\"" + s + "\""; }

std::string read_text_file(const fs::path& p) {
  const auto b = h::read_bytes(p.string());
  if (!b) {
    return {};
  }
  std::string s = h::as_text(*b);
  std::string lf;
  for (char c : s) {
    if (c != '\r') {
      lf += c;
    }
  }
  return lf;
}

// Runs arcani-render with each argument quoted. stdout through the pipe,
// stderr through a file (CR LF folded to LF).
RunResult run_cli(const std::vector<std::string>& args) {
  static int counter = 0;
  const fs::path err_dir = fs::path(ARCANI_TEST_OUT_DIR) / "_stderr";
  fs::create_directories(err_dir);
  const fs::path err_file = err_dir / ("run-" + std::to_string(++counter) + ".txt");
  fs::remove(err_file);

  std::string cmd = quote(ARCANI_RENDER_PATH);
  for (const std::string& a : args) {
    cmd += " " + quote(a);
  }
  cmd += " 2>" + quote(err_file.string());
#if defined(_WIN32)
  // cmd /c strips one outer pair of quotes; wrap so the quoted path survives.
  cmd = "\"" + cmd + "\"";
#endif
  RunResult r;
  FILE* pipe = ARC_POPEN(cmd.c_str(), "r");
  REQUIRE(pipe != nullptr);
  char buffer[512];
  while (std::fgets(buffer, sizeof buffer, pipe) != nullptr) {
    r.out += buffer;
  }
  const int status = ARC_PCLOSE(pipe);
#if defined(_WIN32)
  r.exit_code = status;
#else
  r.exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : -1;
#endif
  r.err = read_text_file(err_file);
  return r;
}

std::string lower(std::string s) {
  for (char& c : s) {
    if (c >= 'A' && c <= 'Z') {
      c = static_cast<char>(c - 'A' + 'a');
    }
  }
  return s;
}

std::string trim(const std::string& s) {
  const char* ws = " \t\r\n";
  const auto begin = s.find_first_not_of(ws);
  if (begin == std::string::npos) {
    return {};
  }
  const auto end = s.find_last_not_of(ws);
  return s.substr(begin, end - begin + 1);
}

// Sets (or, for nullptr, removes) an environment variable for a scope.
class ScopedEnv {
 public:
  ScopedEnv(const char* name, const char* value) : name_(name) {
    if (const char* old = std::getenv(name)) {
      saved_ = std::string(old);
    }
    set(name, value);
  }
  ~ScopedEnv() { set(name_, saved_ ? saved_->c_str() : nullptr); }
  ScopedEnv(const ScopedEnv&) = delete;
  ScopedEnv& operator=(const ScopedEnv&) = delete;

 private:
  static void set(const char* name, const char* value) {
#if defined(_WIN32)
    _putenv_s(name, value ? value : "");  // "" removes the variable
#else
    if (value) {
      setenv(name, value, 1);
    } else {
      unsetenv(name);
    }
#endif
  }
  const char* name_;
  std::optional<std::string> saved_;
};

fs::path case_dir(const std::string& name) {
  const fs::path dir = fs::path(ARCANI_TEST_OUT_DIR) / name;
  fs::remove_all(dir);
  fs::create_directories(dir);
  return dir;
}

std::string fixture_path(const std::string& name) {
  return std::string(ARCANI_RECIPES_DIR) + "/fixtures/valid/" + name;
}

void write_text(const fs::path& p, const std::string& text) {
  std::FILE* f = std::fopen(p.string().c_str(), "wb");
  REQUIRE(f != nullptr);
  REQUIRE(std::fwrite(text.data(), 1, text.size(), f) == text.size());
  REQUIRE(std::fclose(f) == 0);
}

// The beat-6 fixture with its length_s text replaced.
std::string beat6_with_length(const std::string& length_text) {
  const std::string text = arcani::test::api::valid(arcani::test::api::kBeat6);
  const std::string from = "\"length_s\": 1,";
  const auto at = text.find(from);
  REQUIRE(at != std::string::npos);
  std::string out = text;
  out.replace(at, from.size(), "\"length_s\": " + length_text + ",");
  return out;
}

json::Value parse_ok(const std::string& text) {
  json::ParseResult r = json::parse(text);
  INFO("JSON: " << text);
  REQUIRE(r.value.has_value());
  return *r.value;
}

std::string recipe_hash_vector(const std::string& fixture) {
  const json::Value v = parse_ok(read_text_file(fs::path(ARCANI_TEST_DATA_DIR) / "recipe_hash_vectors.json"));
  const json::Value* hash = v.find(fixture);
  REQUIRE(hash != nullptr);
  return hash->string();
}

double fixture_seed(const std::string& text) {
  const json::Value v = parse_ok(text);
  const json::Value* seed = v.find("seed");
  REQUIRE(seed != nullptr);
  REQUIRE(seed->integral());
  return seed->number();
}

std::string rejected_line(const arc_error& e) {
  return std::string("rejected: parameter=") + e.parameter + " value=" + e.value +
         " rule=" + e.rule + " limit=" + e.limit;
}

// The engine output for `text` at `rate` in `mode`, every frame.
struct Expected {
  std::uint64_t frames = 0;
  std::vector<std::uint8_t> data;
};

Expected engine_render(const std::string& text, arc_mode mode, std::uint32_t rate) {
  namespace api = arcani::test::api;
  api::PlanPtr plan = api::compile_ok(text, api::options(mode, rate));
  Expected e;
  e.frames = arc_plan_frame_count(plan.get());
  if (e.frames == 0) {
    return e;  // nothing to render (arc_render refuses a null buffer)
  }
  api::RendererPtr r = api::renderer(plan.get());
  const std::vector<double> out = api::render(r.get(), static_cast<std::size_t>(e.frames));
  e.data = h::spec_data_bytes(out);
  return e;
}

void require_wav(const fs::path& wav, const Expected& want, std::uint32_t rate) {
  INFO("WAV " << wav.string());
  const auto bytes = h::read_bytes(wav.string());
  REQUIRE(bytes.has_value());
  for (const std::string& p : h::wav_problems(*bytes, want.frames, rate)) {
    UNSCOPED_INFO("WAV problem: " << p);
  }
  REQUIRE(h::wav_problems(*bytes, want.frames, rate).empty());
  const std::vector<std::uint8_t> header = h::expected_wav_header(want.frames, rate);
  REQUIRE(bytes->size() == header.size() + want.data.size());
  CHECK(std::equal(header.begin(), header.end(), bytes->begin()));
  CHECK(std::equal(want.data.begin(), want.data.end(), bytes->begin() + static_cast<std::ptrdiff_t>(header.size())));
}

json::Value require_report(const fs::path& report) {
  INFO("report " << report.string());
  REQUIRE(fs::exists(report));
  const json::Value v = parse_ok(read_text_file(report));
  for (const std::string& p : h::report_problems(v)) {
    UNSCOPED_INFO("report problem: " << p);
  }
  REQUIRE(h::report_problems(v).empty());
  return v;
}

// Checks the report members of a render of `fixture` (text as rendered).
void check_report_members(const json::Value& v, const std::string& fixture, const std::string& text,
                          std::uint32_t rate, const std::string& mode, std::uint64_t frames) {
  CHECK(v.find("engine_version")->string() == arc_engine_version());
  CHECK(v.find("seed")->number() == fixture_seed(text));
  CHECK(v.find("sample_rate")->number() == static_cast<double>(rate));
  CHECK(v.find("mode")->string() == mode);
  CHECK(v.find("frames")->number() == static_cast<double>(frames));
  const json::Value& key = *v.find("determinism_key");
  if (!fixture.empty()) {
    CHECK(key.find("recipe_hash")->string() == recipe_hash_vector(fixture));
  }
  CHECK(key.find("asset_hashes")->array().empty());
  CHECK(key.find("engine_version")->string() == arc_engine_version());
  CHECK(key.find("sample_rate")->number() == static_cast<double>(rate));
  const auto& list = v.find("assertions")->array();
  REQUIRE(list.size() == 1);
  const tables::Row& row = tables::row("render-speed");
  CHECK(list[0].find("name")->string() == "render speed");
  CHECK(list[0].find("row")->string() == row.id);
  CHECK(list[0].find("threshold")->number() == row.value());
  CHECK(list[0].find("unit")->string() == row.unit);
}

const json::Value& speed(const json::Value& report) {
  return report.find("assertions")->array().at(0);
}

void check_not_applicable(const json::Value& report, const std::string& note) {
  const json::Value& a = speed(report);
  CHECK(a.find("result")->string() == "not_applicable");
  CHECK(a.find("measured")->kind() == json::Kind::Null);
  CHECK(a.find("note")->string() == note);
}

// Files in dir, by name.
std::vector<std::string> listing(const fs::path& dir) {
  std::vector<std::string> names;
  for (const auto& e : fs::directory_iterator(dir)) {
    names.push_back(e.path().filename().string());
  }
  std::sort(names.begin(), names.end());
  return names;
}

void require_usage_exit_2(const std::vector<std::string>& args, const fs::path& dir) {
  std::string shown;
  for (const auto& a : args) {
    shown += "[" + a + "] ";
  }
  INFO("arguments: " << shown);
  const RunResult r = run_cli(args);
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  CHECK(r.exit_code == 2);
  CHECK(lower(r.out + r.err).find("usage") != std::string::npos);
  CHECK(listing(dir).empty());
}

}  // namespace

// ---------------------------------------------------------------- version

TEST_CASE("--version prints the engine version and exits 0", "[cli]") {
  const RunResult r = run_cli({"--version"});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  REQUIRE(r.exit_code == 0);
  REQUIRE(trim(r.out) == std::string(arc_engine_version()));
}

// ------------------------------------------------------------------ usage

TEST_CASE("wrong argument shapes print usage and exit 2", "[cli]") {
  const fs::path dir = case_dir("usage");
  const std::string recipe = fixture_path(arcani::test::api::kBeat6);
  const std::string wav = (dir / "x.wav").string();
  const std::vector<std::vector<std::string>> shapes = {
      {},
      {"--bogus"},
      {"render"},
      {"-v"},
      {"--VERSION"},
      {"--version", "extra"},
      {"--version", recipe, "--out", wav},
      {recipe},
      {recipe, "--out"},
      {recipe, "--out", wav, "--report"},
      {recipe, "--out", wav, "--rate"},
      {recipe, "--out", wav, "--mode"},
      {recipe, "--out", wav, "--rate", "fast"},
      {recipe, "--out", wav, "--rate", "48k"},
      {recipe, "--out", wav, "--rate", "-48000"},
      {recipe, "--out", wav, "--rate", "48000.0"},
      {recipe, "--out", wav, "--mode", "loud"},
      {recipe, "--out", wav, "--mode", "Final"},
      {recipe, "--out", wav, "--bogus"},
      {recipe, "--out", wav, "--out", wav},
      {recipe, "--out", wav, "--rate", "48000", "--rate", "44100"},
      {recipe, "--out", wav, "--mode", "measure", "--mode", "final"},
      {recipe, recipe, "--out", wav},
      {recipe, "--out", wav, "stray"},
  };
  for (const auto& args : shapes) {
    require_usage_exit_2(args, dir);
  }
}

TEST_CASE("an empty --report or colliding file paths print usage and exit 2", "[cli]") {
  const fs::path dir = case_dir("usage-paths");
  const std::string recipe = fixture_path(arcani::test::api::kBeat6);
  const std::string wav = (dir / "x.wav").string();
  const std::vector<std::vector<std::string>> shapes = {
      {recipe, "--out", wav, "--report", ""},
      {recipe, "--out", wav, "--report", wav},
      {recipe, "--out", wav, "--report", wav + ".partial"},
  };
  for (const auto& args : shapes) {
    require_usage_exit_2(args, dir);
  }
  // A copy of the recipe, so a collision bug cannot replace the fixture.
  const fs::path recipe_dir = case_dir("usage-paths-recipe");
  const fs::path copy = recipe_dir / "r.json";
  const std::string text = arcani::test::api::valid(arcani::test::api::kBeat6);
  write_text(copy, text);
  const std::vector<std::vector<std::string>> recipe_shapes = {
      {copy.string(), "--out", copy.string()},
      {copy.string(), "--out", wav, "--report", copy.string()},
      // The same file through another spelling of its path.
      {copy.string(), "--out", (recipe_dir / "." / "r.json").string()},
  };
  for (const auto& args : recipe_shapes) {
    require_usage_exit_2(args, dir);
    CHECK(listing(recipe_dir) == std::vector<std::string>{"r.json"});
    const auto bytes = h::read_bytes(copy.string());
    REQUIRE(bytes.has_value());
    CHECK(h::as_text(*bytes) == text);
  }
}

// ----------------------------------------------------------------- render

TEST_CASE("render at 48 kHz by default: WAV data is the 24-bit rounding of arc_render",
          "[cli]") {
  ScopedEnv env(kEnv, nullptr);
  const fs::path dir = case_dir("default");
  const std::string fixture = arcani::test::api::kBeat6;
  const std::string text = arcani::test::api::valid(fixture);
  const fs::path wav = dir / "x.wav";
  const RunResult r = run_cli({fixture_path(fixture), "--out", wav.string()});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  REQUIRE(r.exit_code == 0);
  const Expected want = engine_render(text, ARC_MODE_MEASURE, 48000);
  CHECK(want.frames == 48000);
  require_wav(wav, want, 48000);
  const json::Value report = require_report(dir / "x.report.json");
  check_report_members(report, fixture, text, 48000, "measure", want.frames);
  check_not_applicable(report, "not the reference machine");
  CHECK(listing(dir) == std::vector<std::string>{"x.report.json", "x.wav"});
}

TEST_CASE("render at 44.1 kHz", "[cli]") {
  ScopedEnv env(kEnv, nullptr);
  const fs::path dir = case_dir("rate-44100");
  const std::string fixture = arcani::test::api::kBeat6;
  const std::string text = arcani::test::api::valid(fixture);
  const fs::path wav = dir / "x.wav";
  const RunResult r = run_cli({fixture_path(fixture), "--out", wav.string(), "--rate", "44100"});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  REQUIRE(r.exit_code == 0);
  const Expected want = engine_render(text, ARC_MODE_MEASURE, 44100);
  CHECK(want.frames == 44100);
  require_wav(wav, want, 44100);
  const json::Value report = require_report(dir / "x.report.json");
  check_report_members(report, fixture, text, 44100, "measure", want.frames);
}

TEST_CASE("explicit 48 kHz, beat 0 fixture, and options in another order", "[cli]") {
  ScopedEnv env(kEnv, nullptr);
  const fs::path dir = case_dir("options-order");
  const std::string fixture = arcani::test::api::kBeat0;
  const std::string text = arcani::test::api::valid(fixture);
  const fs::path wav = dir / "b0.wav";
  const RunResult r = run_cli({fixture_path(fixture), "--mode", "measure", "--rate", "48000",
                               "--out", wav.string()});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  REQUIRE(r.exit_code == 0);
  const Expected want = engine_render(text, ARC_MODE_MEASURE, 48000);
  require_wav(wav, want, 48000);
  check_report_members(require_report(dir / "b0.report.json"), fixture, text, 48000, "measure",
                       want.frames);
}

TEST_CASE("final mode with the stored gain renders and reports mode final", "[cli]") {
  ScopedEnv env(kEnv, nullptr);
  const fs::path dir = case_dir("final");
  const std::string fixture = arcani::test::api::kBeat6;
  const std::string text = arcani::test::api::valid(fixture);
  const fs::path wav = dir / "x.wav";
  const RunResult r = run_cli({fixture_path(fixture), "--out", wav.string(), "--mode", "final"});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  REQUIRE(r.exit_code == 0);
  const Expected want = engine_render(text, ARC_MODE_FINAL, 48000);
  require_wav(wav, want, 48000);
  check_report_members(require_report(dir / "x.report.json"), fixture, text, 48000, "final",
                       want.frames);
}

// -------------------------------------------------------------- rejection

TEST_CASE("a numeric rate other than 44.1 or 48 kHz is refused by the engine", "[cli]") {
  namespace api = arcani::test::api;
  const std::string text = api::valid(api::kBeat6);
  for (const char* rate : {"96000", "22050", "0", "44101"}) {
    INFO("--rate " << rate);
    const fs::path dir = case_dir(std::string("rate-") + rate);
    const fs::path wav = dir / "x.wav";
    write_text(wav, "existing file");
    const RunResult r = run_cli({fixture_path(api::kBeat6), "--out", wav.string(), "--rate", rate});
    INFO("stdout: " << r.out << "\nstderr: " << r.err);
    CHECK(r.exit_code == 1);
    const api::Compiled c =
        api::compile(text, api::options(ARC_MODE_MEASURE, static_cast<std::uint32_t>(std::stoul(rate))));
    REQUIRE(c.status == ARC_ERR_REJECTED);
    CHECK(r.err == rejected_line(c.error) + "\n");
    CHECK(read_text_file(wav) == "existing file");
    CHECK(listing(dir) == std::vector<std::string>{"x.wav"});
  }
}

TEST_CASE("a rejected recipe writes nothing and leaves an existing file untouched", "[cli]") {
  namespace api = arcani::test::api;
  const fs::path dir = case_dir("rejected");
  const std::string text = beat6_with_length("-1");
  const fs::path recipe = dir / "length-minus-1.json";
  write_text(recipe, text);
  const fs::path wav = dir / "x.wav";
  write_text(wav, "existing file");
  const RunResult r = run_cli({recipe.string(), "--out", wav.string()});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  CHECK(r.exit_code == 1);
  const api::Compiled c = api::compile(text, api::options(ARC_MODE_MEASURE, 48000));
  REQUIRE(c.status == ARC_ERR_REJECTED);
  CHECK(std::string(c.error.parameter) == "/length_s");
  CHECK(std::string(c.error.value) == "-1");
  CHECK_FALSE(std::string(c.error.rule).empty());
  CHECK_FALSE(std::string(c.error.limit).empty());
  CHECK(r.err == rejected_line(c.error) + "\n");
  CHECK(read_text_file(wav) == "existing file");
  CHECK(listing(dir) == std::vector<std::string>{"length-minus-1.json", "x.wav"});
}

TEST_CASE("final mode without a stored gain is rejected with final.required", "[cli]") {
  namespace api = arcani::test::api;
  const fs::path dir = case_dir("final-no-gain");
  const fs::path wav = dir / "x.wav";
  const RunResult r = run_cli({fixture_path(api::kNoGain), "--out", wav.string(), "--mode", "final"});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  CHECK(r.exit_code == 1);
  const api::Compiled c = api::compile(api::valid(api::kNoGain), api::options(ARC_MODE_FINAL, 48000));
  REQUIRE(c.status == ARC_ERR_REJECTED);
  CHECK(std::string(c.error.rule) == "final.required");
  CHECK(r.err == rejected_line(c.error) + "\n");
  CHECK(listing(dir).empty());
}

// ------------------------------------------------------------ zero length

TEST_CASE("zero length writes a header-only WAV and speed is not applicable (no frames)",
          "[cli]") {
  const std::string text = beat6_with_length("0");
  for (const char* env_value : {static_cast<const char*>(nullptr), "1"}) {
    ScopedEnv env(kEnv, env_value);
    INFO("ARCANI_REFERENCE_MACHINE " << (env_value ? env_value : "unset"));
    const fs::path dir = case_dir(std::string("zero-") + (env_value ? "ref" : "unset"));
    const fs::path recipe = dir / "zero.json";
    write_text(recipe, text);
    const fs::path wav = dir / "zero.wav";
    const RunResult r = run_cli({recipe.string(), "--out", wav.string()});
    INFO("stdout: " << r.out << "\nstderr: " << r.err);
    REQUIRE(r.exit_code == 0);
    const Expected want = engine_render(text, ARC_MODE_MEASURE, 48000);
    REQUIRE(want.frames == 0);
    require_wav(wav, want, 48000);
    const auto bytes = h::read_bytes(wav.string());
    REQUIRE(bytes.has_value());
    CHECK(bytes->size() == 44);
    const json::Value report = require_report(dir / "zero.report.json");
    check_report_members(report, "", text, 48000, "measure", 0);
    check_not_applicable(report, "no frames");
  }
}

// ------------------------------------------------------------------- loop

// Story 2.7: a looping recipe's report gains loop {opening_end_frame,
// seam_frames, end_frame} right after frames (spec Implementation Notes,
// Report); a report without loop is unchanged. One looping render only, at
// 44.1 kHz (the swell loop fixture is 20 min, so its WAV is about 318 MB; it
// is removed after the check).
TEST_CASE("a looping recipe's report lists the opening end, every seam, and the end", "[cli][loop]") {
  ScopedEnv env(kEnv, nullptr);
  const std::uint32_t rate = 44100;
  const std::string fixture = "loop-swell-theta-cycle.json";
  const arcani::test::spec::LoopFrameVector* want = nullptr;
  for (const auto& v : arcani::test::spec::kLoopFrames) {
    if (fixture == v.fixture && v.fs == rate) {
      want = &v;
    }
  }
  REQUIRE(want != nullptr);
  const fs::path dir = case_dir("loop");
  const fs::path wav = dir / "x.wav";
  const RunResult r = run_cli({fixture_path(fixture), "--out", wav.string(), "--rate", "44100"});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  REQUIRE(r.exit_code == 0);
  CHECK(fs::file_size(wav) == h::expected_wav_header(want->end_frame, rate).size() + 6 * want->end_frame);
  fs::remove(wav);
  const json::Value report = require_report(dir / "x.report.json");
  CHECK(report.find("frames")->number() == static_cast<double>(want->end_frame));
  const json::Value* loop = report.find("loop");
  REQUIRE(loop != nullptr);
  CHECK(loop->find("opening_end_frame")->number() == static_cast<double>(want->opening_end_frame));
  CHECK(loop->find("end_frame")->number() == static_cast<double>(want->end_frame));
  const auto& seams = loop->find("seam_frames")->array();
  REQUIRE(seams.size() == want->seam_count);
  for (std::size_t k = 0; k < seams.size(); ++k) {
    INFO("seam " << k + 1);
    CHECK(seams[k].number() == static_cast<double>(want->seams[k]));
  }
  // A recipe without loop: no loop member.
  const fs::path plain_dir = case_dir("loop-absent");
  const RunResult p = run_cli({fixture_path(arcani::test::api::kBeat6), "--out", (plain_dir / "x.wav").string()});
  REQUIRE(p.exit_code == 0);
  CHECK(require_report(plain_dir / "x.report.json").find("loop") == nullptr);
}

// ------------------------------------------------------------------ speed

TEST_CASE("render speed is not applicable off the reference machine", "[cli]") {
  for (const char* env_value : {static_cast<const char*>(nullptr), "0", "true", "yes"}) {
    ScopedEnv env(kEnv, env_value);
    INFO("ARCANI_REFERENCE_MACHINE " << (env_value ? env_value : "unset"));
    const fs::path dir = case_dir("speed-not-reference");
    const fs::path wav = dir / "x.wav";
    const RunResult r = run_cli({fixture_path(arcani::test::api::kBeat6), "--out", wav.string()});
    INFO("stdout: " << r.out << "\nstderr: " << r.err);
    CHECK(r.exit_code == 0);
    check_not_applicable(require_report(dir / "x.report.json"), "not the reference machine");
  }
}

TEST_CASE("render speed is measured on the reference machine: pass exits 0, fail exits 4",
          "[cli]") {
  // Does not require a pass, so no speed result gates CI.
  ScopedEnv env(kEnv, "1");
  const fs::path dir = case_dir("speed-measured");
  const fs::path wav = dir / "x.wav";
  const RunResult r = run_cli({fixture_path(arcani::test::api::kBeat6), "--out", wav.string()});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  const json::Value report = require_report(dir / "x.report.json");
  const json::Value& a = speed(report);
  REQUIRE(a.find("measured")->kind() == json::Kind::Number);
  const std::string result = a.find("result")->string();
  CHECK((result == "pass" || result == "fail"));
  CHECK(a.find("note")->string().empty());
  CHECK(r.exit_code == (result == "pass" ? 0 : 4));
  CHECK(listing(dir) == std::vector<std::string>{"x.report.json", "x.wav"});
}

TEST_CASE("render speed passes on the reference machine (dev PC only)", "[cli][speed]") {
  const char* here = std::getenv(kEnv);
  if (here == nullptr || std::string(here) != "1") {
    SKIP("ARCANI_REFERENCE_MACHINE is not 1 in this environment: not the reference machine");
  }
  ScopedEnv env(kEnv, "1");
  const fs::path dir = case_dir("speed-reference");
  const fs::path wav = dir / "x.wav";
  const RunResult r = run_cli({fixture_path(arcani::test::api::kBeat6), "--out", wav.string()});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  CHECK(r.exit_code == 0);
  const json::Value report = require_report(dir / "x.report.json");
  const json::Value& a = speed(report);
  CHECK(a.find("result")->string() == "pass");
  REQUIRE(a.find("measured")->kind() == json::Kind::Number);
  CHECK(a.find("measured")->number() >= tables::row("render-speed").value());
  CHECK(a.find("note")->string().empty());
}

// ------------------------------------------------------------------ files

TEST_CASE("report path: the last extension is replaced, and --report overrides it", "[cli]") {
  ScopedEnv env(kEnv, nullptr);
  const std::string recipe = fixture_path(arcani::test::api::kBeat6);
  {
    const fs::path dir = case_dir("report-two-dots");
    const RunResult r = run_cli({recipe, "--out", (dir / "take.final.wav").string()});
    CHECK(r.exit_code == 0);
    CHECK(listing(dir) == std::vector<std::string>{"take.final.report.json", "take.final.wav"});
  }
  {
    const fs::path dir = case_dir("report-no-extension");
    const RunResult r = run_cli({recipe, "--out", (dir / "take").string()});
    CHECK(r.exit_code == 0);
    CHECK(listing(dir) == std::vector<std::string>{"take", "take.report.json"});
  }
  {
    const fs::path dir = case_dir("report-explicit");
    fs::create_directories(dir / "reports");
    const RunResult r = run_cli({recipe, "--out", (dir / "x.wav").string(), "--report",
                                 (dir / "reports" / "mine.json").string()});
    CHECK(r.exit_code == 0);
    CHECK(listing(dir) == std::vector<std::string>{"reports", "x.wav"});
    CHECK(listing(dir / "reports") == std::vector<std::string>{"mine.json"});
    require_report(dir / "reports" / "mine.json");
  }
}

TEST_CASE("a finished render replaces an existing WAV and leaves no partial file", "[cli]") {
  ScopedEnv env(kEnv, nullptr);
  const fs::path dir = case_dir("replace");
  const fs::path wav = dir / "x.wav";
  write_text(wav, "old take");
  write_text(dir / "x.report.json", "old report");
  const std::string text = arcani::test::api::valid(arcani::test::api::kBeat6);
  const RunResult r = run_cli({fixture_path(arcani::test::api::kBeat6), "--out", wav.string()});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  REQUIRE(r.exit_code == 0);
  require_wav(wav, engine_render(text, ARC_MODE_MEASURE, 48000), 48000);
  require_report(dir / "x.report.json");
  CHECK(listing(dir) == std::vector<std::string>{"x.report.json", "x.wav"});
}

TEST_CASE("file errors exit 3 and leave no file at the WAV path", "[cli]") {
  const fs::path dir = case_dir("file-errors");
  {
    const fs::path wav = dir / "x.wav";
    const RunResult r = run_cli({(dir / "no-such-recipe.json").string(), "--out", wav.string()});
    INFO("stdout: " << r.out << "\nstderr: " << r.err);
    CHECK(r.exit_code == 3);
    CHECK(listing(dir).empty());
  }
  {
    const fs::path wav = dir / "missing-dir" / "x.wav";
    const RunResult r = run_cli({fixture_path(arcani::test::api::kBeat6), "--out", wav.string()});
    INFO("stdout: " << r.out << "\nstderr: " << r.err);
    CHECK(r.exit_code == 3);
    CHECK(listing(dir).empty());
  }
  {
    // The report cannot be written: no WAV and no .partial remain.
    ScopedEnv env(kEnv, nullptr);
    const fs::path wav = dir / "x.wav";
    const RunResult r = run_cli({fixture_path(arcani::test::api::kBeat6), "--out", wav.string(),
                                 "--report", (dir / "missing-dir" / "r.json").string()});
    INFO("stdout: " << r.out << "\nstderr: " << r.err);
    CHECK(r.exit_code == 3);
    CHECK(listing(dir).empty());
  }
}

// ------------------------------------------------------------ determinism
//
// Story 1.6 contract: arcani-render run twice, as two separate processes, on
// the same recipe and rate writes WAVs whose differing-byte count
// (determinism_helpers.hpp, differing_bytes) is at most row `determinism`
// (unit "differing bytes"). The report's determinism_key has exactly the
// members recipe_hash, asset_hashes (empty), engine_version, sample_rate, in
// that order. It is equal across separate runs, and changes when the rate
// changes (only sample_rate differs then). arcani-render always renders in
// 4096-frame calls, and the key is a property of the plan, not of the host
// block size; so "equal across block sizes" is shown by the CLI WAV equaling
// the in-process render at every row `block-sizes` member (spec rounding
// rule from cli_helpers.hpp, independent of cli/), with the same key.

namespace {

std::string key_text(const json::Value& report) {
  const json::Value& key = *report.find("determinism_key");
  REQUIRE(h::members_are(key, {"recipe_hash", "asset_hashes", "engine_version", "sample_rate"}));
  CHECK(key.find("asset_hashes")->array().empty());
  return key.find("recipe_hash")->string() + "|" +
         std::to_string(key.find("asset_hashes")->array().size()) + "|" +
         key.find("engine_version")->string() + "|" +
         std::to_string(static_cast<std::uint64_t>(key.find("sample_rate")->number()));
}

struct CliRun {
  std::vector<std::uint8_t> wav;
  std::string key;
};

CliRun render_cli(const std::string& fixture, std::uint32_t rate, const std::string& name) {
  const fs::path dir = case_dir(name);
  const fs::path wav = dir / "x.wav";
  const RunResult r = run_cli({fixture_path(fixture), "--out", wav.string(), "--rate", std::to_string(rate)});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  REQUIRE(r.exit_code == 0);
  CliRun out;
  const auto bytes = h::read_bytes(wav.string());
  REQUIRE(bytes.has_value());
  out.wav = *bytes;
  out.key = key_text(require_report(dir / "x.report.json"));
  return out;
}

double determinism_row() {
  const tables::Row& row = tables::row("determinism");
  REQUIRE(row.unit == "differing bytes");
  return row.value();
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

}  // namespace

TEST_CASE("two separate arcani-render processes write byte-identical WAVs with one key",
          "[cli][determinism]") {
  ScopedEnv env(kEnv, nullptr);
  const double allowed = determinism_row();
  std::vector<std::string> keys;
  for (const char* fixture : {arcani::test::api::kBeat0, arcani::test::api::kBeat6}) {
    for (std::uint32_t rate : table_rates()) {
      const std::string tag = std::string(fixture == arcani::test::api::kBeat0 ? "b0-" : "b6-") +
                              std::to_string(rate);
      const CliRun first = render_cli(fixture, rate, "determinism-" + tag + "-a");
      const CliRun second = render_cli(fixture, rate, "determinism-" + tag + "-b");
      const std::uint64_t count = arcani::test::determinism::differing_bytes(first.wav, second.wav);
      INFO(fixture << " at " << rate << " Hz: " << count << " differing bytes, row allows " << allowed);
      CHECK(static_cast<double>(count) <= allowed);
      CHECK(first.key == second.key);
      CHECK(first.key.rfind(recipe_hash_vector(fixture) + "|0|" + arc_engine_version() + "|" +
                                std::to_string(rate),
                            0) == 0);
      if (fixture == arcani::test::api::kBeat6) {
        keys.push_back(first.key);
      }
    }
  }
  // The key changes with the rate.
  REQUIRE(keys.size() >= 2);
  for (std::size_t i = 1; i < keys.size(); ++i) {
    CHECK(keys[i] != keys[0]);
  }
}

TEST_CASE("the arcani-render WAV equals the in-process render at every block-sizes member",
          "[cli][determinism]") {
  ScopedEnv env(kEnv, nullptr);
  namespace api = arcani::test::api;
  const tables::Row& sizes = tables::row("block-sizes");
  REQUIRE(sizes.unit == "frames per call");
  const tables::Row& invariance = tables::row("block-size-invariance");
  REQUIRE(invariance.unit == "differing bytes");
  const double allowed = invariance.value();
  for (const char* fixture : {api::kBeat0, api::kBeat6}) {
    for (std::uint32_t rate : table_rates()) {
      const CliRun cli = render_cli(fixture, rate, std::string("determinism-blocks-") + fixture + "-" +
                                                       std::to_string(rate));
      for (double size : sizes.values) {
        const auto block = static_cast<std::size_t>(size);
        api::PlanPtr plan = api::compile_ok(api::valid(fixture), api::options(ARC_MODE_MEASURE, rate));
        const std::uint64_t frames = arc_plan_frame_count(plan.get());
        api::RendererPtr r = api::renderer(plan.get());
        std::vector<double> all;
        const std::string failure = arcani::test::determinism::render_in_blocks(
            r.get(), frames, block, [&all](const double* s, std::size_t n) { all.insert(all.end(), s, s + 2 * n); });
        INFO(fixture << ", " << rate << " Hz, " << block << " frames per call");
        REQUIRE(failure.empty());
        std::vector<std::uint8_t> bytes = h::expected_wav_header(frames, rate);
        const std::vector<std::uint8_t> data = h::spec_data_bytes(all);
        bytes.insert(bytes.end(), data.begin(), data.end());
        const std::uint64_t count = arcani::test::determinism::differing_bytes(cli.wav, bytes);
        INFO(count << " differing bytes, row allows " << allowed);
        CHECK(static_cast<double>(count) <= allowed);
      }
    }
  }
}

// ------------------------------------------------------------------ spacing

// Story 3.2 (docs/signal-spec.md, Spacing, Report and Compile order; spec
// Implementation Notes, Command-line renderer). A spacing rejection prints
// the rejected line with " detail=<detail>" before the newline and writes no
// WAV and no report; every other rejection prints the same bytes as before.
// A recipe with a spacing pair in an ear gets a spacing block in its report,
// each ear's values those of arc_plan_spacing and its pair named from
// arc_plan_component; a recipe without one gets no spacing member. Short
// renders only (10 s and 1 s recipes).

#ifdef ARC_ERROR_DETAIL_BYTES

#include "spacing_helpers.hpp"

namespace {

const arcani::test::spec::SpacingCaseVector& spacing_case(const std::string& name) {
  for (const auto& c : arcani::test::spec::kSpacingCases) {
    if (name == c.name) {
      return c;
    }
  }
  FAIL("no spacing case " << name);
  return arcani::test::spec::kSpacingCases[0];
}

std::string component_name(const arc_plan* p, std::size_t index) {
  namespace sp = arcani::test::spacing;
  arc_component c;
  arc_error e;
  arcani::test::api::poison(e);
  REQUIRE(arc_plan_component(p, index, &c, &e) == ARC_OK);
  return std::string(sp::kLayers[static_cast<int>(c.layer)]) + " (" + std::to_string(c.gamma_mult) + ", " +
         std::to_string(c.theta_mult) + ", " + std::to_string(c.beat_mult) + ") at " + sp::shortest(c.center_hz) +
         " Hz";
}

// The spacing block the report must hold for `text` at `rate`, built from the C API.
std::string expected_spacing_block(const std::string& text, std::uint32_t rate) {
  namespace api = arcani::test::api;
  namespace sp = arcani::test::spacing;
  api::PlanPtr plan = api::compile_ok(text, api::options(ARC_MODE_MEASURE, rate));
  std::string block = "  \"spacing\": {\n";
  const char* const names[] = {"left", "right"};
  for (int ear = 0; ear < 2; ++ear) {
    arc_spacing s;
    arc_error e;
    api::poison(e);
    REQUIRE(arc_plan_spacing(plan.get(), ear == 0 ? ARC_EAR_LEFT : ARC_EAR_RIGHT, &s, &e) == ARC_OK);
    block += std::string("    \"") + names[ear] + "\": ";
    if (s.has_pair == 0) {
      block += "null";
    } else {
      block += "{\"min_distance_hz\": " + sp::shortest(s.min_distance_hz) + ", \"margin_hz\": " +
               sp::shortest(s.margin_hz) + ", \"component_1\": " + std::to_string(s.component_1) +
               ", \"component_2\": " + std::to_string(s.component_2) + ", \"pair\": \"" +
               component_name(plan.get(), s.component_1) + " and " + component_name(plan.get(), s.component_2) +
               "\"}";
    }
    block += ear == 0 ? ",\n" : "\n";
  }
  return block + "  },\n";
}

}  // namespace

TEST_CASE("a spacing rejection prints the detail, writes nothing, and other rejections keep their bytes",
          "[cli][spacing]") {
  namespace api = arcani::test::api;
  namespace spec = arcani::test::spec;
  ScopedEnv env(kEnv, nullptr);
  const fs::path dir = case_dir("spacing-rejected");
  const fs::path wav = dir / "x.wav";
  const RunResult r = run_cli({fixture_path(spec::kSpacing_must_fail_fixture), "--out", wav.string()});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  CHECK(r.exit_code == 1);
  const api::Compiled c = api::compile(api::valid(spec::kSpacing_must_fail_fixture), api::options(ARC_MODE_MEASURE, 48000));
  REQUIRE(c.status == ARC_ERR_REJECTED);
  REQUIRE(api::written(c.error.detail));
  CHECK(std::string(c.error.rule) == "spacing_rule");
  CHECK_FALSE(std::string(c.error.detail).empty());
  CHECK(r.err == rejected_line(c.error) + " detail=" + c.error.detail + "\n");
  CHECK(r.err ==
        "rejected: parameter=/binaural/carrier_left_hz value=4 rule=spacing_rule limit=>= 50 Hz (row spacing-rule) "
        "detail=right ear: gamma_pac (-1, 0, 0) at 260 Hz and binaural (0, 0, 1) at 256 Hz; whole session\n");
  CHECK(listing(dir).empty());
  // A rejection by another rule: no detail suffix.
  const fs::path other = case_dir("spacing-other-rejection");
  const RunResult n = run_cli({fixture_path("gamma-carrier-wave-triangle.json"), "--out", (other / "x.wav").string()});
  CHECK(n.exit_code == 1);
  CHECK(n.err.find(" detail=") == std::string::npos);
  const api::Compiled t = api::compile(api::valid("gamma-carrier-wave-triangle.json"), api::options(ARC_MODE_MEASURE, 48000));
  REQUIRE(api::written(t.error.detail));
  CHECK(std::string(t.error.detail).empty());
  CHECK(n.err == rejected_line(t.error) + "\n");
}

TEST_CASE("a report holds the spacing block only when an ear has a pair", "[cli][spacing]") {
  namespace api = arcani::test::api;
  ScopedEnv env(kEnv, nullptr);
  const std::uint32_t rate = 48000;
  for (const char* name : {"spacing-exactly-50hz", "spacing-sweep-together", "ad5-swell-cycle-270deg"}) {
    INFO("case " << name);
    const std::string text = spacing_case(name).recipe;
    const fs::path dir = case_dir(std::string("spacing-report-") + name);
    const fs::path recipe = dir / "r.json";
    write_text(recipe, text);
    const RunResult r = run_cli({recipe.string(), "--out", (dir / "x.wav").string()});
    INFO("stdout: " << r.out << "\nstderr: " << r.err);
    REQUIRE(r.exit_code == 0);
    fs::remove(dir / "x.wav");
    const std::string report = read_text_file(dir / "x.report.json");
    require_report(dir / "x.report.json");
    const std::string block = expected_spacing_block(text, rate);
    INFO(report << "\nwant block:\n" << block);
    const auto at = report.find(block);
    REQUIRE(at != std::string::npos);
    CHECK(report.compare(at + block.size(), 22, "  \"determinism_key\": {") == 0);
  }
  // No pair in either ear (binaural only, or no layers): no spacing member.
  for (const char* fixture : {api::kBeat0, api::kNoLayers}) {
    INFO(fixture);
    const fs::path dir = case_dir(std::string("spacing-report-none-") + fixture);
    const RunResult r = run_cli({fixture_path(fixture), "--out", (dir / "x.wav").string()});
    REQUIRE(r.exit_code == 0);
    const std::string report = read_text_file(dir / "x.report.json");
    CHECK(report.find("\"spacing\"") == std::string::npos);
    CHECK(require_report(dir / "x.report.json").find("spacing") == nullptr);
  }
}

#else

TEST_CASE("arcani-render reports spacing (Story 3.2)", "[cli][spacing]") {
  FAIL("not implemented: arc_error::detail (ARC_ERROR_DETAIL_BYTES) and arc_plan_spacing (Story 3.2)");
}

#endif

// ------------------------------------------------------------------ preview

// Story 3.3 (docs/signal-spec.md, Preview; spec Implementation Notes, Command
// line). `--preview` takes no value, may appear once anywhere after RECIPE,
// and is a usage error (exit 2, nothing written) twice or with --mode final
// in either order; the usage text names it. A preview render keeps frames
// [0, F) of the recipe's own render, each sample times g before 24-bit
// rounding, g = 10^(P/20) / max(n_max, 1) with P row preview-peak-level; the
// report has frames F and a preview member before determinism_key, whose
// key is the recipe's own. g here is the gain vector for P and the layer
// count read from the recipe text, never computed by cli/. Short renders
// only (1 s fixtures).

namespace {

// Layers present in each ear of a recipe text, no ear muted (Preview, Layers).
std::uint32_t recipe_layers_per_ear(const std::string& text) {
  const json::Value v = parse_ok(text);
  std::uint32_t n = 0;
  for (const char* layer : {"theta_reference", "gamma_pac", "binaural"}) {
    n += v.find(layer) != nullptr ? 1u : 0u;
  }
  return n;
}

const arcani::test::spec::PreviewGainVector& preview_gain_vector(std::uint32_t layers) {
  const double p = tables::row("preview-peak-level").value();
  const std::uint32_t counted = layers == 0 ? 1u : layers;
  for (const auto& v : arcani::test::spec::kPreviewGains) {
    if (v.peak_dbfs == p && v.layers_max == counted) {
      return v;
    }
  }
  FAIL("no preview gain vector for P " << p << " and " << counted << " layers");
  return arcani::test::spec::kPreviewGains[0];
}

std::string shortest_text(double x) {
  char buf[64];
  const auto r = std::to_chars(buf, buf + sizeof buf, x);
  REQUIRE(r.ec == std::errc());
  return std::string(buf, r.ptr);
}

double gain_of(const arcani::test::spec::PreviewGainVector& v) {
  double g = 0.0;
  std::memcpy(&g, &v.gain_bits, sizeof g);
  return g;
}

// The engine output of `text` at `rate`, frames [0, frames), times g, by the
// spec 24-bit rounding rule; and the largest |quantized sample| before and
// after the gain.
struct PreviewExpected {
  Expected wav;
  std::int32_t peak_plain = 0;
  std::int32_t peak_preview = 0;
};

PreviewExpected preview_render(const std::string& text, std::uint32_t rate, std::uint64_t frames, double g) {
  namespace api = arcani::test::api;
  api::PlanPtr plan = api::compile_ok(text, api::options(ARC_MODE_MEASURE, rate));
  PreviewExpected e;
  e.wav.frames = frames;
  if (frames == 0) {
    return e;
  }
  api::RendererPtr r = api::renderer(plan.get());
  std::vector<double> out = api::render(r.get(), static_cast<std::size_t>(frames));
  for (double& s : out) {
    const std::int32_t q = h::spec_quantize_24(s);
    e.peak_plain = std::max(e.peak_plain, q < 0 ? -q : q);
    s = s * g;
    const std::int32_t w = h::spec_quantize_24(s);
    e.peak_preview = std::max(e.peak_preview, w < 0 ? -w : w);
  }
  e.wav.data = h::spec_data_bytes(out);
  return e;
}

std::string want_preview_block(double peak, std::uint32_t layers, double gain, double seconds) {
  return "  \"preview\": {\n    \"signed\": false,\n    \"peak_dbfs\": " + shortest_text(peak) +
         ",\n    \"layers_per_ear\": " + std::to_string(layers) + ",\n    \"gain\": " + shortest_text(gain) +
         ",\n    \"seconds\": " + shortest_text(seconds) + "\n  },\n";
}

}  // namespace

TEST_CASE("--preview usage errors exit 2 and write nothing; the usage text names --preview", "[cli][preview]") {
  const fs::path dir = case_dir("preview-usage");
  const std::string recipe = fixture_path(arcani::test::api::kBeat6);
  const std::string wav = (dir / "x.wav").string();
  const std::vector<std::vector<std::string>> shapes = {
      {recipe, "--out", wav, "--preview", "--mode", "final"},
      {recipe, "--out", wav, "--mode", "final", "--preview"},
      {recipe, "--preview", "--mode", "final", "--out", wav},
      {recipe, "--out", wav, "--preview", "--preview"},
      {recipe, "--preview", "--out", wav, "--preview"},
      {recipe, "--out", wav, "--preview", "stray"},
      {recipe, "--out", wav, "--preview", "--rate"},
      {"--preview", recipe, "--out", wav},
  };
  for (const auto& args : shapes) {
    require_usage_exit_2(args, dir);
  }
  const RunResult r = run_cli({});
  CHECK(r.exit_code == 2);
  CHECK((r.out + r.err).find("[--preview]") != std::string::npos);
}

TEST_CASE("--preview of a 1 s recipe: every sample is the 24-bit rounding of the engine output times g",
          "[cli][preview]") {
  namespace api = arcani::test::api;
  namespace spec = arcani::test::spec;
  ScopedEnv env(kEnv, nullptr);
  const tables::Row& length = tables::row("preview-length");
  const std::string fixture = api::kBeat6;
  const std::string text = api::valid(fixture);
  const std::uint32_t layers = recipe_layers_per_ear(text);
  REQUIRE(layers == 2);  // the fixture holds a theta reference and a binaural pair
  const spec::PreviewGainVector& gv = preview_gain_vector(layers);
  const double g = gain_of(gv);
  // The analytic peak bound: at most 10^(P/20) of full scale, within the
  // 24-bit rounding step (half a step).
  const double bound = gv.amplitude * 0x1p23 + 0.5;
  for (std::uint32_t rate : table_rates()) {
    INFO("rate " << rate);
    const fs::path dir = case_dir("preview-beat6-" + std::to_string(rate));
    const fs::path wav = dir / "x.wav";
    // --preview first, between the options, and last: the same bytes.
    const std::vector<std::vector<std::string>> orders = {
        {fixture_path(fixture), "--preview", "--out", wav.string(), "--rate", std::to_string(rate)},
        {fixture_path(fixture), "--out", wav.string(), "--preview", "--rate", std::to_string(rate)},
        {fixture_path(fixture), "--out", wav.string(), "--rate", std::to_string(rate), "--preview"},
    };
    std::vector<std::uint8_t> first;
    for (const auto& args : orders) {
      const RunResult r = run_cli(args);
      INFO("stdout: " << r.out << "\nstderr: " << r.err);
      REQUIRE(r.exit_code == 0);
      CHECK(r.err.empty());
      const auto bytes = h::read_bytes(wav.string());
      REQUIRE(bytes.has_value());
      if (first.empty()) {
        first = *bytes;
      } else {
        CHECK(*bytes == first);
      }
    }
    // The session (1 s) is shorter than the preview: F = N.
    api::PlanPtr plan = api::compile_ok(text, api::options(ARC_MODE_MEASURE, rate));
    const std::uint64_t n = arc_plan_frame_count(plan.get());
    REQUIRE(static_cast<double>(n) < length.value() * rate);
    const PreviewExpected want = preview_render(text, rate, n, g);
    require_wav(wav, want.wav, rate);
    // Real waveforms: the plain render peaks above the preview bound; the
    // preview stays under the analytic bound and is not silent.
    INFO("plain peak " << want.peak_plain << ", preview peak " << want.peak_preview << ", bound " << bound);
    CHECK(static_cast<double>(want.peak_plain) > bound);
    CHECK(want.peak_preview > 0);
    CHECK(static_cast<double>(want.peak_preview) <= bound);
    // Must-fail: the plain render's bytes, and g times 1.001, are not the preview WAV.
    const Expected plain = engine_render(text, ARC_MODE_MEASURE, rate);
    CHECK(plain.data != want.wav.data);
    const PreviewExpected off = preview_render(text, rate, n, g * 1.001);
    CHECK(off.wav.data != want.wav.data);

    // Report: frames F, the preview member, the recipe's own key.
    const fs::path report_path = dir / "x.report.json";
    const json::Value report = require_report(report_path);
    check_report_members(report, fixture, text, rate, "measure", n);
    const json::Value* preview = report.find("preview");
    REQUIRE(preview != nullptr);
    CHECK(preview->find("signed")->kind() == json::Kind::Bool);
    CHECK_FALSE(preview->find("signed")->boolean());
    CHECK(preview->find("peak_dbfs")->number() == tables::row("preview-peak-level").value());
    CHECK(preview->find("layers_per_ear")->number() == static_cast<double>(layers));
    CHECK(api::bits(preview->find("gain")->number()) == gv.gain_bits);
    CHECK(preview->find("seconds")->number() == static_cast<double>(n) / static_cast<double>(rate));
    const std::string report_text = read_text_file(report_path);
    const std::string block = want_preview_block(tables::row("preview-peak-level").value(), layers, g,
                                                 static_cast<double>(n) / static_cast<double>(rate));
    INFO(report_text << "\nwant block:\n" << block);
    const auto at = report_text.find(block);
    REQUIRE(at != std::string::npos);
    CHECK(report_text.compare(at + block.size(), 22, "  \"determinism_key\": {") == 0);

    // The same render without --preview: no preview member, the recipe's key,
    // and the plain bytes.
    const fs::path plain_dir = case_dir("preview-beat6-plain-" + std::to_string(rate));
    const RunResult p = run_cli({fixture_path(fixture), "--out", (plain_dir / "x.wav").string(), "--rate",
                                 std::to_string(rate)});
    REQUIRE(p.exit_code == 0);
    require_wav(plain_dir / "x.wav", plain, rate);
    const json::Value plain_report = require_report(plain_dir / "x.report.json");
    CHECK(plain_report.find("preview") == nullptr);
    CHECK(read_text_file(plain_dir / "x.report.json").find("\"preview\"") == std::string::npos);
    CHECK(key_text(plain_report) == key_text(report));
  }
}

TEST_CASE("--preview of a recipe with no layer: n_max 0 counts as 1 and the WAV is silent", "[cli][preview]") {
  namespace api = arcani::test::api;
  ScopedEnv env(kEnv, nullptr);
  const std::string fixture = api::kNoLayers;
  const std::string text = api::valid(fixture);
  REQUIRE(recipe_layers_per_ear(text) == 0);
  const arcani::test::spec::PreviewGainVector& gv = preview_gain_vector(0);
  const std::uint32_t rate = 48000;
  const fs::path dir = case_dir("preview-no-layers");
  const fs::path wav = dir / "x.wav";
  const RunResult r = run_cli({fixture_path(fixture), "--out", wav.string(), "--preview"});
  INFO("stdout: " << r.out << "\nstderr: " << r.err);
  REQUIRE(r.exit_code == 0);
  api::PlanPtr plan = api::compile_ok(text, api::options(ARC_MODE_MEASURE, rate));
  const std::uint64_t n = arc_plan_frame_count(plan.get());
  const PreviewExpected want = preview_render(text, rate, n, gain_of(gv));
  CHECK(want.peak_preview == 0);
  require_wav(wav, want.wav, rate);
  const json::Value report = require_report(dir / "x.report.json");
  const json::Value* preview = report.find("preview");
  REQUIRE(preview != nullptr);
  CHECK(preview->find("layers_per_ear")->number() == 0.0);
  CHECK(api::bits(preview->find("gain")->number()) == gv.gain_bits);
}

// ---------------------------------------------------------------- loudness
//
// Story 4.1 (docs/signal-spec.md, Loudness, Window and Report): --loudness
// (no value) may be given once; twice, or with --preview, is a usage error.
// A non-looping recipe shorter than row loudness-window-min is refused after
// compile with one stderr line "rejected: parameter=/length_s value=<N / fs>
// rule=loudness_window_rule limit=>= 60 s (row loudness-window-min)", exit 1,
// nothing written. Without --loudness the same recipe renders as before.

namespace {

const arcani::test::spec::LoudnessWindowVector& loudness_window_vector(const std::string& fixture,
                                                                       std::uint32_t rate) {
  for (const auto& v : arcani::test::spec::kLoudnessWindows) {
    if (fixture == v.fixture && v.fs == rate) {
      return v;
    }
  }
  FAIL("no loudness window vector for " << fixture << " at " << rate);
  return arcani::test::spec::kLoudnessWindows[0];
}

const arcani::test::spec::LoudnessWindowCaseVector& loudness_window_case(const std::string& name,
                                                                         std::uint32_t rate) {
  for (const auto& v : arcani::test::spec::kLoudnessWindowCases) {
    if (name == v.name && v.fs == rate) {
      return v;
    }
  }
  FAIL("no loudness window case " << name << " at " << rate);
  return arcani::test::spec::kLoudnessWindowCases[0];
}

std::string loudness_rejected_line(const char* parameter, const char* value, const char* rule, const char* limit) {
  return std::string("rejected: parameter=") + parameter + " value=" + value + " rule=" + rule + " limit=" + limit;
}

}  // namespace

TEST_CASE("--loudness usage errors exit 2 and write nothing", "[cli][loudness]") {
  const fs::path dir = case_dir("loudness-usage");
  const std::string recipe = fixture_path(arcani::test::api::kBeat6);
  const std::string wav = (dir / "x.wav").string();
  const std::vector<std::vector<std::string>> shapes = {
      {recipe, "--out", wav, "--loudness", "--loudness"},
      {recipe, "--loudness", "--out", wav, "--loudness"},
      {recipe, "--out", wav, "--loudness", "--preview"},
      {recipe, "--preview", "--out", wav, "--loudness"},
      {recipe, "--loudness", "--preview", "--out", wav},
      {recipe, "--out", wav, "--loudness", "stray"},
      {"--loudness", recipe, "--out", wav},
      {"--version", "--loudness"},
  };
  for (const auto& args : shapes) {
    require_usage_exit_2(args, dir);
  }
}

TEST_CASE("--loudness refuses a 10 s fixture with the window rule and writes nothing; without it, it renders",
          "[cli][loudness]") {
  namespace spec = arcani::test::spec;
  ScopedEnv env(kEnv, nullptr);
  const std::string fixture = "theta-sine-6hz.json";
  const tables::Row& min_row = tables::row("loudness-window-min");
  REQUIRE(min_row.unit == "s");
  for (std::uint32_t rate : table_rates()) {
    INFO("rate " << rate);
    const spec::LoudnessWindowVector& v = loudness_window_vector(fixture, rate);
    REQUIRE_FALSE(v.accepted);
    CHECK(std::string(v.limit) == ">= " + min_row.value_text + " s (row " + min_row.id + ")");
    CHECK(std::string(v.rule) == spec::kLoudness_window_rule);
    CHECK(std::string(v.parameter) == spec::kLoudness_window_parameter);
    const fs::path dir = case_dir("loudness-short-" + std::to_string(rate));
    const fs::path wav = dir / "x.wav";
    for (const auto& args : std::vector<std::vector<std::string>>{
             {fixture_path(fixture), "--out", wav.string(), "--rate", std::to_string(rate), "--loudness"},
             {fixture_path(fixture), "--loudness", "--out", wav.string(), "--rate", std::to_string(rate)}}) {
      const RunResult r = run_cli(args);
      INFO("stdout: " << r.out << "\nstderr: " << r.err);
      CHECK(r.exit_code == 1);
      CHECK(r.err == loudness_rejected_line(v.parameter, v.value, v.rule, v.limit) + "\n");
      CHECK(listing(dir).empty());
    }
    // The same fixture without --loudness renders as before.
    const std::string text = arcani::test::api::valid(fixture);
    const RunResult r = run_cli({fixture_path(fixture), "--out", wav.string(), "--rate", std::to_string(rate)});
    INFO("stdout: " << r.out << "\nstderr: " << r.err);
    REQUIRE(r.exit_code == 0);
    const Expected want = engine_render(text, ARC_MODE_MEASURE, rate);
    CHECK(want.frames == v.end_frame);
    require_wav(wav, want, rate);
    const json::Value report = require_report(dir / "x.report.json");
    CHECK(report.find("loudness") == nullptr);
    CHECK(read_text_file(dir / "x.report.json").find("\"loudness\"") == std::string::npos);
  }
}

TEST_CASE("--loudness at the window minimum: 60 s accepted, 59.75 s refused, the WAV unchanged",
          "[cli][loudness]") {
  ScopedEnv env(kEnv, nullptr);
  for (std::uint32_t rate : table_rates()) {
    INFO("rate " << rate);
    {
      const arcani::test::spec::LoudnessWindowCaseVector& c = loudness_window_case("no loop, 59.75 s", rate);
      REQUIRE_FALSE(c.accepted);
      const fs::path dir = case_dir("loudness-5975-" + std::to_string(rate));
      const fs::path recipe = dir / "beat6-59.75.json";
      write_text(recipe, beat6_with_length("59.75"));
      const RunResult r =
          run_cli({recipe.string(), "--out", (dir / "x.wav").string(), "--rate", std::to_string(rate), "--loudness"});
      INFO("stdout: " << r.out << "\nstderr: " << r.err);
      CHECK(r.exit_code == 1);
      CHECK(r.err == loudness_rejected_line(c.parameter, c.value, c.rule, c.limit) + "\n");
      CHECK(listing(dir) == std::vector<std::string>{"beat6-59.75.json"});
    }
    {
      const arcani::test::spec::LoudnessWindowCaseVector& c = loudness_window_case("no loop, 60 s", rate);
      REQUIRE(c.accepted);
      const fs::path dir = case_dir("loudness-60-" + std::to_string(rate));
      const fs::path recipe = dir / "beat6-60.json";
      const std::string text = beat6_with_length("60");
      write_text(recipe, text);
      const RunResult r =
          run_cli({recipe.string(), "--out", (dir / "x.wav").string(), "--rate", std::to_string(rate), "--loudness"});
      INFO("stdout: " << r.out << "\nstderr: " << r.err);
      REQUIRE(r.exit_code == 0);
      const Expected want = engine_render(text, ARC_MODE_MEASURE, rate);
      REQUIRE(want.frames == c.end_frame);
      require_wav(dir / "x.wav", want, rate);
      const json::Value report = require_report(dir / "x.report.json");
      check_report_members(report, "", text, rate, "measure", want.frames);
      const json::Value* l = report.find("loudness");
      REQUIRE(l != nullptr);
      CHECK(l->find("window_start_frame")->number() == static_cast<double>(c.start_frame));
      CHECK(l->find("window_body_frames")->number() == static_cast<double>(c.body_frames));
      CHECK(l->find("window_repeats")->number() == static_cast<double>(c.repeats));
      CHECK(l->find("window_frames")->number() == static_cast<double>(c.window_frames));
      REQUIRE(l->find("window_lufs_i")->kind() == json::Kind::Number);
      REQUIRE(l->find("whole_lufs_i")->kind() == json::Kind::Number);
      CHECK(arcani::test::api::bits(l->find("window_lufs_i")->number()) ==
            arcani::test::api::bits(l->find("whole_lufs_i")->number()));
      // Unit gain: far above the -70 LUFS absolute gate.
      CHECK(l->find("window_lufs_i")->number() > arcani::test::spec::kLoudness_absolute_gate_lufs);
    }
  }
}
