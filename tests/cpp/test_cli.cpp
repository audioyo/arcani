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
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <optional>
#include <string>
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
}
