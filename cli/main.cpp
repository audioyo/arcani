// arcani-render: compiles a recipe through the public C API, renders it to a
// 2-channel 24-bit WAV (docs/signal-spec.md, 24-bit rounding), and writes a
// JSON report (Story 1.4).
//
//   arcani-render --version
//   arcani-render RECIPE --out WAV [--report JSON] [--rate N] [--mode measure|final]
//
// Exit codes: 0 rendered, every assertion pass or not applicable; 1 the
// engine rejected the recipe or an option; 2 usage; 3 file or internal
// error; 4 rendered but an assertion failed (WAV and report written).

#include <arcani/arcani.h>

#include "report.hpp"
#include "tables.hpp"
#include "wav.hpp"

#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <filesystem>
#include <optional>
#include <span>
#include <string>
#include <system_error>
#include <utility>
#include <vector>

namespace {

namespace fs = std::filesystem;
namespace cli = arcani::cli;

constexpr int kExitOk = 0;
constexpr int kExitRejected = 1;
constexpr int kExitUsage = 2;
constexpr int kExitFile = 3;

// Frames per arc_render call (a member of row block-sizes; the engine output
// does not depend on it).
constexpr std::size_t kBlockFrames = 4096;

const char* const kUsage =
    "usage: arcani-render RECIPE --out WAV [--report JSON] [--rate 44100|48000]"
    " [--mode measure|final]\n"
    "       arcani-render --version\n";

int usage() {
  std::fputs(kUsage, stderr);
  return kExitUsage;
}

int file_error(const std::string& what) {
  std::fprintf(stderr, "error: %s\n", what.c_str());
  return kExitFile;
}

struct Args {
  std::string recipe;
  std::string out;
  std::optional<std::string> report;
  std::uint32_t rate = 48000;
  arc_mode mode = ARC_MODE_MEASURE;
};

// ASCII digits only, and the value fits in 32 bits.
std::optional<std::uint32_t> parse_rate(const std::string& text) {
  if (text.empty()) {
    return std::nullopt;
  }
  for (char c : text) {
    if (c < '0' || c > '9') {
      return std::nullopt;
    }
  }
  std::uint32_t v = 0;
  const auto r = std::from_chars(text.data(), text.data() + text.size(), v);
  if (r.ec != std::errc() || r.ptr != text.data() + text.size()) {
    return std::nullopt;
  }
  return v;
}

// RECIPE first, then each option at most once, in any order.
std::optional<Args> parse_args(int argc, char** argv) {
  if (argc < 2) {
    return std::nullopt;
  }
  Args a;
  a.recipe = argv[1];
  if (a.recipe.empty() || a.recipe[0] == '-') {
    return std::nullopt;
  }
  bool have_out = false;
  bool have_rate = false;
  bool have_mode = false;
  for (int i = 2; i < argc; i += 2) {
    const std::string flag = argv[i];
    if (i + 1 >= argc) {
      return std::nullopt;
    }
    const std::string value = argv[i + 1];
    if (flag == "--out" && !have_out) {
      have_out = true;
      a.out = value;
    } else if (flag == "--report" && !a.report) {
      if (value.empty()) {
        return std::nullopt;
      }
      a.report = value;
    } else if (flag == "--rate" && !have_rate) {
      have_rate = true;
      const std::optional<std::uint32_t> rate = parse_rate(value);
      if (!rate) {
        return std::nullopt;
      }
      a.rate = *rate;
    } else if (flag == "--mode" && !have_mode) {
      have_mode = true;
      if (value == "measure") {
        a.mode = ARC_MODE_MEASURE;
      } else if (value == "final") {
        a.mode = ARC_MODE_FINAL;
      } else {
        return std::nullopt;
      }
    } else {
      return std::nullopt;
    }
  }
  if (!have_out || a.out.empty()) {
    return std::nullopt;
  }
  return a;
}

// The WAV path with its last extension replaced by .report.json.
std::string default_report_path(const std::string& wav) {
  fs::path p(wav);
  p.replace_extension(".report.json");
  return p.string();
}

// True when a and b name the same file: the same text, or, where both
// exist, the same file on disk.
bool same_file(const std::string& a, const std::string& b) {
  if (a == b) {
    return true;
  }
  std::error_code ec;
  return fs::equivalent(fs::path(a), fs::path(b), ec) && !ec;
}

// The WAV, its partial file, the report, and the recipe must be four
// different files.
bool paths_collide(const Args& args, const std::string& report) {
  const std::string partial = args.out + ".partial";
  return same_file(args.out, args.recipe) || same_file(report, args.recipe) ||
         same_file(partial, args.recipe) || same_file(report, args.out) ||
         same_file(report, partial);
}

std::optional<std::string> read_file(const std::string& path) {
  std::FILE* f = std::fopen(path.c_str(), "rb");
  if (f == nullptr) {
    return std::nullopt;
  }
  std::string text;
  char buffer[65536];
  std::size_t n = 0;
  while ((n = std::fread(buffer, 1, sizeof buffer, f)) > 0) {
    text.append(buffer, n);
  }
  const bool ok = std::ferror(f) == 0;
  std::fclose(f);
  if (!ok) {
    return std::nullopt;
  }
  return text;
}

bool write_all(std::FILE* f, const std::vector<std::uint8_t>& bytes) {
  return bytes.empty() || std::fwrite(bytes.data(), 1, bytes.size(), f) == bytes.size();
}

bool write_text_file(const std::string& path, const std::string& text) {
  std::FILE* f = std::fopen(path.c_str(), "wb");
  if (f == nullptr) {
    return false;
  }
  const bool wrote = text.empty() || std::fwrite(text.data(), 1, text.size(), f) == text.size();
  const bool closed = std::fclose(f) == 0;
  return wrote && closed;
}

// The open <WAV>.partial file: closed on every exit path, and removed unless
// it was renamed onto the WAV path.
struct PartialFile {
  std::string path;
  std::FILE* file = nullptr;
  bool opened = false;
  bool renamed = false;

  explicit PartialFile(std::string p) : path(std::move(p)) {}
  PartialFile(const PartialFile&) = delete;
  PartialFile& operator=(const PartialFile&) = delete;
  ~PartialFile() {
    close();
    if (opened && !renamed) {
      std::remove(path.c_str());
    }
  }
  bool open() {
    file = std::fopen(path.c_str(), "wb");
    opened = file != nullptr;
    return opened;
  }
  bool close() {
    if (file == nullptr) {
      return true;
    }
    const bool ok = std::fclose(file) == 0;
    file = nullptr;
    return ok;
  }
};

struct PlanHandle {
  arc_plan* plan = nullptr;
  ~PlanHandle() { arc_plan_release(plan); }
};

struct RendererHandle {
  arc_renderer* renderer = nullptr;
  ~RendererHandle() { arc_renderer_destroy(renderer); }
};

int run(const Args& args) {
  const std::string report_path = args.report ? *args.report : default_report_path(args.out);
  // Read before any output is opened, so a missing table writes nothing.
  const arcani::test::tables::Row& speed_row = arcani::test::tables::row("render-speed");

  const std::optional<std::string> text = read_file(args.recipe);
  if (!text) {
    return file_error("cannot read recipe " + args.recipe);
  }

  // Compile before any output file is opened, so a rejection leaves nothing.
  arc_compile_options options;
  std::memset(&options, 0, sizeof options);
  options.mode = args.mode;
  options.sample_rate = args.rate;
  options.mute_binaural_ear = ARC_MUTE_NONE;
  PlanHandle plan;
  arc_error error;
  std::memset(&error, 0, sizeof error);
  const arc_status status = arc_compile(text->data(), text->size(), &options, &plan.plan, &error);
  if (status == ARC_ERR_REJECTED) {
    std::fprintf(stderr, "rejected: parameter=%s value=%s rule=%s limit=%s\n", error.parameter,
                 error.value, error.rule, error.limit);
    return kExitRejected;
  }
  if (status != ARC_OK) {
    return file_error(std::string("compile failed: rule=") + error.rule);
  }

  const std::uint64_t frames = arc_plan_frame_count(plan.plan);
  RendererHandle renderer;
  if (frames > 0 && arc_renderer_create(plan.plan, &renderer.renderer, &error) != ARC_OK) {
    return file_error(std::string("renderer creation failed: rule=") + error.rule);
  }

  PartialFile wav(args.out + ".partial");
  const std::string& partial = wav.path;
  if (!wav.open()) {
    return file_error("cannot write " + partial);
  }

  if (!write_all(wav.file, cli::wav_header(frames, args.rate))) {
    return file_error("cannot write " + partial);
  }
  std::vector<double> samples(kBlockFrames * 2);
  std::vector<std::uint8_t> bytes;
  bytes.reserve(samples.size() * 3);
  std::chrono::steady_clock::duration render_time{0};
  for (std::uint64_t done = 0; done < frames;) {
    const std::uint64_t left = frames - done;
    const std::size_t n = left < kBlockFrames ? static_cast<std::size_t>(left) : kBlockFrames;
    const auto start = std::chrono::steady_clock::now();
    const arc_status s = arc_render(renderer.renderer, samples.data(), n, nullptr, &error);
    render_time += std::chrono::steady_clock::now() - start;
    if (s != ARC_OK) {
      return file_error(std::string("render failed: rule=") + error.rule);
    }
    bytes.clear();
    cli::append_samples(bytes, std::span<const double>(samples.data(), n * 2));
    if (!write_all(wav.file, bytes)) {
      return file_error("cannot write " + partial);
    }
    done += n;
  }
  if (!wav.close()) {
    return file_error("cannot write " + partial);
  }

  cli::Report report;
  report.engine_version = arc_engine_version();
  report.seed = arc_plan_seed(plan.plan);
  report.sample_rate = args.rate;
  report.mode = args.mode == ARC_MODE_FINAL ? "final" : "measure";
  report.frames = frames;
  report.determinism_key.recipe_hash = arc_plan_recipe_hash(plan.plan);
  report.determinism_key.engine_version = report.engine_version;
  report.determinism_key.sample_rate = args.rate;
  report.assertions.push_back(cli::render_speed(
      speed_row, frames, args.rate, cli::elapsed_seconds(render_time),
      cli::is_reference_machine(std::getenv("ARCANI_REFERENCE_MACHINE"))));

  if (!write_text_file(report_path, cli::report_json(report))) {
    std::remove(report_path.c_str());
    return file_error("cannot write " + report_path);
  }

  std::error_code ec;
  fs::rename(partial, args.out, ec);
  wav.renamed = !ec;
  if (ec) {
    std::remove(report_path.c_str());
    return file_error("cannot rename " + partial + " to " + args.out + ": " + ec.message());
  }
  return cli::assertions_exit_code(report.assertions);
}

}  // namespace

int main(int argc, char** argv) {
  if (argc >= 2 && std::strcmp(argv[1], "--version") == 0) {
    if (argc != 2) {
      return usage();
    }
    std::printf("%s\n", arc_engine_version());
    return kExitOk;
  }
  const std::optional<Args> args = parse_args(argc, argv);
  if (!args) {
    return usage();
  }
  if (paths_collide(*args, args->report ? *args->report : default_report_path(args->out))) {
    std::fputs("error: RECIPE, --out, its .partial file, and --report must be different files\n",
               stderr);
    return usage();
  }
  try {
    return run(*args);
  } catch (const std::exception& e) {
    return file_error(e.what());
  }
}
