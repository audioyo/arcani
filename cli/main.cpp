// arcani-render: compiles a recipe through the public C API, renders it to a
// 2-channel 24-bit WAV (docs/signal-spec.md, 24-bit rounding), and writes a
// JSON report (Story 1.4).
//
//   arcani-render --version
//   arcani-render RECIPE --out WAV [--report JSON] [--rate N] [--mode measure|final] [--preview] [--loudness]
//   arcani-render RECIPE --store-gain [--rate N]
//
// --preview (Story 3.3; docs/signal-spec.md, Preview) keeps the first F
// frames of the recipe's own render, each sample times the preview gain g
// before 24-bit rounding, and adds the report member "preview". Measure mode
// only: with --mode final it is a usage error.
//
// --loudness (Story 4.1; docs/signal-spec.md, Loudness) measures the BS.1770
// integrated loudness of the binary64 output over the window and over the
// whole render, and adds the report member "loudness". The WAV is unchanged.
// A non-looping recipe whose steady part (the longest stretch with no gain
// ramp, Story 4.4) is shorter than row loudness-window-min is rejected
// (exit 1, nothing written). Not with --preview.
//
// In final mode, --loudness also adds the assertions loudness and
// loudness_whole (Story 4.2; docs/signal-spec.md, Loudness gain, Final-mode
// checks) after render speed.
//
// Every final-mode render (Story 4.3; docs/signal-spec.md, True peak)
// meters the 24-bit samples it writes with the BS.1770 Annex 2 true-peak
// meter and adds the report member "true_peak" and the assertion true_peak
// (row true-peak), the last one. Measure-mode reports are unchanged.
//
// --store-gain (Story 4.2; docs/signal-spec.md, Loudness gain, Store)
// compiles RECIPE in measure mode, renders only the loudness window,
// rounds the gain to 0.01 dB, and rewrites only the members
// loudness_gain_db and loudness_hash of RECIPE (RECIPE.partial, then a
// rename; nothing when the bytes are unchanged). Before writing it renders
// the whole session in final mode with the new gain and refuses a gain
// whose true peak is above row true-peak (Story 4.3). With --out, --report,
// --preview, --mode, or --loudness it is a usage error. Prints
// "stored: loudness_gain_db=<gain> loudness_hash=<hash> window_lufs_i=<L>".
//
// Exit codes: 0 rendered (or stored), every assertion pass or not
// applicable; 1 the engine rejected the recipe or an option, or (with
// --loudness or --store-gain) the window rule loudness_window_rule rejected
// it, or (--store-gain) the gain is outside row loudness-gain or its
// final render's true peak is above row true-peak; 2 usage; 3
// file or internal error; 4 rendered but an assertion failed (WAV and report
// written).

#include <arcani/arcani.h>

#include "loudness.hpp"
#include "preview.hpp"
#include "recipe_write.hpp"
#include "report.hpp"
#include "tables.hpp"
#include "true_peak.hpp"
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
    " [--mode measure|final] [--preview] [--loudness]\n"
    "       arcani-render RECIPE --store-gain [--rate 44100|48000]\n"
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
  bool preview = false;
  bool loudness = false;
  bool store_gain = false;  // Story 4.2
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

// RECIPE first, then each option at most once, in any order. --preview and
// --loudness are the options without a value; every other option's value is
// the next argument, whatever it is.
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
    if (flag == "--preview") {
      if (a.preview) {
        return std::nullopt;
      }
      a.preview = true;
      --i;  // no value: the loop step moves to the next argument
      continue;
    }
    if (flag == "--loudness") {
      if (a.loudness) {
        return std::nullopt;
      }
      a.loudness = true;
      --i;
      continue;
    }
    if (flag == "--store-gain") {
      if (a.store_gain) {
        return std::nullopt;
      }
      a.store_gain = true;
      --i;
      continue;
    }
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
  if (a.store_gain) {
    // Story 4.2: --rate alone may go with it.
    if (have_out || a.report || have_mode || a.preview || a.loudness) {
      return std::nullopt;
    }
    return a;
  }
  if (!have_out || a.out.empty()) {
    return std::nullopt;
  }
  if (a.preview && a.mode == ARC_MODE_FINAL) {
    return std::nullopt;  // a preview is made in measure mode only
  }
  if (a.preview && a.loudness) {
    return std::nullopt;  // a preview is scaled and cut; it is never measured
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

// The engine's rejected line on stderr (Story 3.2: the detail only when it
// is not empty).
void print_rejected(const arc_error& error) {
  if (error.detail[0] != '\0') {
    std::fprintf(stderr, "rejected: parameter=%s value=%s rule=%s limit=%s detail=%s\n", error.parameter,
                 error.value, error.rule, error.limit, error.detail);
  } else {
    std::fprintf(stderr, "rejected: parameter=%s value=%s rule=%s limit=%s\n", error.parameter, error.value,
                 error.rule, error.limit);
  }
}

arc_status compile_text(const std::string& text, arc_mode mode, std::uint32_t rate, PlanHandle& plan,
                        arc_error& error) {
  arc_compile_options options;
  std::memset(&options, 0, sizeof options);
  options.mode = mode;
  options.sample_rate = rate;
  options.mute_binaural_ear = ARC_MUTE_NONE;
  std::memset(&error, 0, sizeof error);
  return arc_compile(text.data(), text.size(), &options, &plan.plan, &error);
}

// arcani-render RECIPE --store-gain (Story 4.2; docs/signal-spec.md,
// Loudness gain, Store, steps 1 to 10; step 8 is Story 4.3, True peak,
// Store step).
int run_store(const Args& args) {
  namespace tables = arcani::test::tables;
  // 1. The rows, before anything is opened.
  const tables::Row& window_row = tables::row("loudness-window-min");
  const std::uint64_t window_min_frames = cli::loudness_window_min_frames(window_row, args.rate);
  const std::string window_limit = cli::loudness_window_limit(window_row);
  const tables::Row& gain_row = tables::row("loudness-gain");
  const tables::Row& true_peak_row = tables::row("true-peak");

  // 2. Read and compile in measure mode.
  const std::optional<std::string> text = read_file(args.recipe);
  if (!text) {
    return file_error("cannot read recipe " + args.recipe);
  }
  PlanHandle plan;
  arc_error error;
  const arc_status status = compile_text(*text, ARC_MODE_MEASURE, args.rate, plan, error);
  if (status == ARC_ERR_REJECTED) {
    print_rejected(error);
    return kExitRejected;
  }
  if (status != ARC_OK) {
    return file_error(std::string("compile failed: rule=") + error.rule);
  }

  // 3. The window rule.
  const std::uint64_t frames = arc_plan_frame_count(plan.plan);
  arc_loop_frames loop;
  std::memset(&loop, 0, sizeof loop);
  if (arc_plan_loop(plan.plan, &loop, &error) != ARC_OK) {
    return file_error(std::string("loop frames failed: rule=") + error.rule);
  }
  // Story 4.4: the non-looping window is the longest stretch with no ramp.
  std::vector<cli::FrameSpan> ramps;
  std::string ramps_rule;
  if (!cli::gain_ramp_spans(plan.plan, ramps, ramps_rule)) {
    return file_error("gain ramps failed: rule=" + ramps_rule);
  }
  const cli::LoudnessWindow window = cli::loudness_window(loop, frames, window_min_frames, ramps);
  if (!window.accepted) {
    const double length_s = static_cast<double>(window.steady_frames) / static_cast<double>(args.rate);
    std::fprintf(stderr, "rejected: parameter=/length_s value=%s rule=loudness_window_rule limit=%s\n",
                 cli::json_number(length_s).c_str(), window_limit.c_str());
    return kExitRejected;
  }

  // 4. Render the window only: every pass from arc_seek to its start.
  cli::LoudnessMeter meter(args.rate);
  RendererHandle renderer;
  if (arc_renderer_create(plan.plan, &renderer.renderer, &error) != ARC_OK) {
    return file_error(std::string("renderer creation failed: rule=") + error.rule);
  }
  std::vector<double> samples(kBlockFrames * 2);
  for (std::uint64_t pass = 0; pass < window.repeats; ++pass) {
    if (arc_seek(renderer.renderer, window.start_frame, &error) != ARC_OK) {
      return file_error(std::string("seek failed: rule=") + error.rule);
    }
    for (std::uint64_t done = 0; done < window.body_frames;) {
      const std::uint64_t left = window.body_frames - done;
      const std::size_t n = left < kBlockFrames ? static_cast<std::size_t>(left) : kBlockFrames;
      if (arc_render(renderer.renderer, samples.data(), n, nullptr, &error) != ARC_OK) {
        return file_error(std::string("render failed: rule=") + error.rule);
      }
      meter.add(std::span<const double>(samples.data(), n * 2));
      done += n;
    }
  }
  if (meter.frames() != window.window_frames) {
    return file_error("loudness: the window meter read " + std::to_string(meter.frames()) + " frames, not " +
                      std::to_string(window.window_frames));
  }
  const double reading = meter.integrated();

  // 5. The gain rounding against the recipe's target.
  const std::optional<double> target = cli::top_level_number(*text, "loudness_target_lufs");
  if (!target) {
    return file_error("cannot read loudness_target_lufs");
  }
  const cli::GainStep step = cli::gain_step(reading, *target, gain_row);
  if (!step.stored) {
    std::fprintf(stderr, "rejected: parameter=/loudness_gain_db value=%s rule=%s limit=%s\n", step.value.c_str(),
                 step.rule.c_str(), step.limit.c_str());
    return kExitRejected;
  }

  // 6. The file rewrite with the measure plan's loudness hash.
  char hash[65];
  if (arc_plan_loudness_hash(plan.plan, hash, &error) != ARC_OK) {
    return file_error(std::string("loudness hash failed: rule=") + error.rule);
  }
  const std::string stored = cli::rewrite_loudness_members(*text, step.gain_text, hash);

  // 7. The new bytes must compile in final mode.
  PlanHandle check;
  const arc_status final_status = compile_text(stored, ARC_MODE_FINAL, args.rate, check, error);
  if (final_status == ARC_ERR_REJECTED) {
    print_rejected(error);
    return file_error("the rewritten recipe does not compile in final mode");
  }
  if (final_status != ARC_OK) {
    return file_error(std::string("final-mode compile of the rewritten recipe failed: rule=") + error.rule);
  }

  // 8. True peak (Story 4.3): the whole session in final mode with the new
  // gain, rounded to 24 bits, against row true-peak. Nothing is written when
  // it is above the ceiling.
  {
    RendererHandle final_renderer;
    if (arc_renderer_create(check.plan, &final_renderer.renderer, &error) != ARC_OK) {
      return file_error(std::string("renderer creation failed: rule=") + error.rule);
    }
    const std::uint64_t final_frames = arc_plan_frame_count(check.plan);
    cli::TruePeakMeter true_peak;
    for (std::uint64_t done = 0; done < final_frames;) {
      const std::uint64_t left = final_frames - done;
      const std::size_t n = left < kBlockFrames ? static_cast<std::size_t>(left) : kBlockFrames;
      if (arc_render(final_renderer.renderer, samples.data(), n, nullptr, &error) != ARC_OK) {
        return file_error(std::string("render failed: rule=") + error.rule);
      }
      for (std::size_t i = 0; i < n; ++i) {
        true_peak.add(cli::quantize_24(samples[2 * i]), cli::quantize_24(samples[2 * i + 1]));
      }
      done += n;
    }
    const cli::TruePeakStep tp_step = cli::true_peak_step(true_peak_row, true_peak.linear(), *target, step.gain_text);
    if (!tp_step.stored) {
      std::fprintf(stderr, "%s\n", tp_step.line.c_str());
      return kExitRejected;
    }
  }

  // 9. Write through RECIPE.partial and a rename, unless nothing changed.
  if (stored != *text) {
    const std::string partial = args.recipe + ".partial";
    if (!write_text_file(partial, stored)) {
      std::remove(partial.c_str());
      return file_error("cannot write " + partial);
    }
    std::error_code ec;
    fs::rename(partial, args.recipe, ec);
    if (ec) {
      std::remove(partial.c_str());
      return file_error("cannot rename " + partial + " to " + args.recipe + ": " + ec.message());
    }
  }

  // 10. The stored line.
  std::printf("stored: loudness_gain_db=%s loudness_hash=%s window_lufs_i=%s\n", step.gain_text.c_str(), hash,
              cli::json_number(reading).c_str());
  return kExitOk;
}

int run(const Args& args) {
  const std::string report_path = args.report ? *args.report : default_report_path(args.out);
  // Read before any output is opened, so a missing table writes nothing.
  const arcani::test::tables::Row& speed_row = arcani::test::tables::row("render-speed");
  // Story 3.3: the preview rows, read and checked before anything is opened,
  // so a table error (a TableError, exit 3 through main) writes nothing.
  std::optional<cli::PreviewRows> preview_rows;
  if (args.preview) {
    namespace tables = arcani::test::tables;
    preview_rows = cli::preview_rows(tables::row("preview-length"), tables::row("preview-seam-tail"),
                                     tables::row("preview-peak-level"));
  }

  // Story 4.2: the final-mode loudness assertions' row, read before anything
  // is opened.
  const arcani::test::tables::Row* tolerance_row = nullptr;
  if (args.loudness && args.mode == ARC_MODE_FINAL) {
    tolerance_row = &arcani::test::tables::row("loudness-tolerance");
  }

  // Story 4.3: the true-peak ceiling of a final-mode render, read before
  // anything is opened.
  const arcani::test::tables::Row* true_peak_row = nullptr;
  if (args.mode == ARC_MODE_FINAL) {
    true_peak_row = &arcani::test::tables::row("true-peak");
  }

  // Story 4.1: the window minimum, read before anything is opened.
  std::uint64_t window_min_frames = 0;
  std::string window_limit;
  if (args.loudness) {
    const arcani::test::tables::Row& window_row = arcani::test::tables::row("loudness-window-min");
    window_min_frames = cli::loudness_window_min_frames(window_row, args.rate);
    window_limit = cli::loudness_window_limit(window_row);
  }

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
    // Story 3.2: the detail follows only when it is not empty, so every
    // other rejection prints the same bytes as before. detail= is always the
    // last field and runs to the end of the line (it may hold spaces, ';',
    // and '='), so a reader takes everything after " detail=" as the detail.
    if (error.detail[0] != '\0') {
      std::fprintf(stderr, "rejected: parameter=%s value=%s rule=%s limit=%s detail=%s\n", error.parameter,
                   error.value, error.rule, error.limit, error.detail);
    } else {
      std::fprintf(stderr, "rejected: parameter=%s value=%s rule=%s limit=%s\n", error.parameter,
                   error.value, error.rule, error.limit);
    }
    return kExitRejected;
  }
  if (status != ARC_OK) {
    return file_error(std::string("compile failed: rule=") + error.rule);
  }

  const std::uint64_t frames = arc_plan_frame_count(plan.plan);
  // Story 3.2: the spacing block, read before any output file is opened, so
  // an engine call that fails here leaves no WAV and no report.
  std::optional<cli::SpacingReport> spacing;
  std::string spacing_rule;
  if (!cli::spacing_report(plan.plan, spacing, spacing_rule)) {
    return file_error("spacing report failed: rule=" + spacing_rule);
  }
  // Story 2.7: the loop frames for the report's seam list.
  arc_loop_frames loop;
  std::memset(&loop, 0, sizeof loop);
  if (arc_plan_loop(plan.plan, &loop, &error) != ARC_OK) {
    return file_error(std::string("loop frames failed: rule=") + error.rule);
  }
  // Story 4.1: the loudness window, or the window rule's rejection, before
  // any output file is opened.
  cli::LoudnessWindow window;
  std::optional<cli::LoudnessMeter> whole_meter;
  std::optional<cli::LoudnessMeter> window_meter;
  if (args.loudness) {
    // Story 4.4: the non-looping window is the longest stretch with no ramp.
    std::vector<cli::FrameSpan> ramps;
    std::string ramps_rule;
    if (!cli::gain_ramp_spans(plan.plan, ramps, ramps_rule)) {
      return file_error("gain ramps failed: rule=" + ramps_rule);
    }
    window = cli::loudness_window(loop, frames, window_min_frames, ramps);
    if (!window.accepted) {
      const double length_s = static_cast<double>(window.steady_frames) / static_cast<double>(args.rate);
      std::fprintf(stderr, "rejected: parameter=/length_s value=%s rule=loudness_window_rule limit=%s\n",
                   cli::json_number(length_s).c_str(), window_limit.c_str());
      return kExitRejected;
    }
    whole_meter.emplace(args.rate);
    // A looping body, or (Story 4.4) a non-looping steady stretch that is
    // not the whole session, has a meter of its own.
    if (loop.looping != 0 || window.start_frame != 0 || window.body_frames != frames) {
      window_meter.emplace(args.rate);
    }
  }
  // Story 3.3: a preview renders frames [0, F) and scales them by g.
  std::uint64_t out_frames = frames;
  std::optional<cli::PreviewReport> preview;
  double gain = 1.0;
  if (preview_rows) {
    cli::PreviewLayers layers;
    std::string layers_rule;
    if (!cli::preview_layers(plan.plan, layers, layers_rule)) {
      return file_error("preview layers failed: rule=" + layers_rule);
    }
    out_frames = cli::preview_frames(loop, frames, cli::seconds_to_samples(preview_rows->length_s, args.rate),
                                     cli::seconds_to_samples(preview_rows->seam_tail_s, args.rate));
    gain = cli::preview_gain(preview_rows->peak_dbfs, layers.max());
    cli::PreviewReport p;
    p.peak_dbfs = preview_rows->peak_dbfs;
    p.layers_per_ear = layers.max();
    p.gain = gain;
    p.seconds = static_cast<double>(out_frames) / static_cast<double>(args.rate);
    preview = p;
  }
  RendererHandle renderer;
  if (out_frames > 0 && arc_renderer_create(plan.plan, &renderer.renderer, &error) != ARC_OK) {
    return file_error(std::string("renderer creation failed: rule=") + error.rule);
  }

  PartialFile wav(args.out + ".partial");
  const std::string& partial = wav.path;
  if (!wav.open()) {
    return file_error("cannot write " + partial);
  }

  if (!write_all(wav.file, cli::wav_header(out_frames, args.rate))) {
    return file_error("cannot write " + partial);
  }
  std::vector<double> samples(kBlockFrames * 2);
  std::vector<std::uint8_t> bytes;
  bytes.reserve(samples.size() * 3);
  // Story 4.3: every sample written, after 24-bit rounding, in final mode.
  std::optional<cli::TruePeakMeter> true_peak_meter;
  if (true_peak_row != nullptr) {
    true_peak_meter.emplace();
  }
  std::chrono::steady_clock::duration render_time{0};
  for (std::uint64_t done = 0; done < out_frames;) {
    const std::uint64_t left = out_frames - done;
    const std::size_t n = left < kBlockFrames ? static_cast<std::size_t>(left) : kBlockFrames;
    const auto start = std::chrono::steady_clock::now();
    const arc_status s = arc_render(renderer.renderer, samples.data(), n, nullptr, &error);
    render_time += std::chrono::steady_clock::now() - start;
    if (s != ARC_OK) {
      return file_error(std::string("render failed: rule=") + error.rule);
    }
    if (whole_meter) {
      whole_meter->add(std::span<const double>(samples.data(), n * 2));
    }
    if (window_meter) {
      // The first window pass is frames [O, O + B) (or [s, e)) of this render.
      const std::uint64_t lo = window.start_frame > done ? window.start_frame : done;
      const std::uint64_t end = window.start_frame + window.body_frames;
      const std::uint64_t hi = end < done + n ? end : done + n;
      if (lo < hi) {
        window_meter->add(std::span<const double>(samples.data() + 2 * (lo - done), 2 * (hi - lo)));
      }
    }
    if (preview) {
      cli::apply_gain(std::span<double>(samples.data(), n * 2), gain);
    }
    if (true_peak_meter) {
      for (std::size_t i = 0; i < n; ++i) {
        true_peak_meter->add(cli::quantize_24(samples[2 * i]), cli::quantize_24(samples[2 * i + 1]));
      }
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

  // Story 4.1: the window's other k - 1 passes, frames [O, O + B) rendered
  // again by a second renderer, into the same window meter.
  std::optional<cli::LoudnessReport> loudness;
  if (whole_meter) {
    if (window_meter && window.repeats > 1) {
      RendererHandle again;
      if (arc_renderer_create(plan.plan, &again.renderer, &error) != ARC_OK) {
        return file_error(std::string("renderer creation failed: rule=") + error.rule);
      }
      for (std::uint64_t pass = 1; pass < window.repeats; ++pass) {
        if (arc_seek(again.renderer, window.start_frame, &error) != ARC_OK) {
          return file_error(std::string("seek failed: rule=") + error.rule);
        }
        for (std::uint64_t done = 0; done < window.body_frames;) {
          const std::uint64_t left = window.body_frames - done;
          const std::size_t n = left < kBlockFrames ? static_cast<std::size_t>(left) : kBlockFrames;
          if (arc_render(again.renderer, samples.data(), n, nullptr, &error) != ARC_OK) {
            return file_error(std::string("render failed: rule=") + error.rule);
          }
          window_meter->add(std::span<const double>(samples.data(), n * 2));
          done += n;
        }
      }
    }
    // Every frame was metered: the whole render once, the window k * B times.
    if (whole_meter->frames() != frames) {
      return file_error("loudness: the whole-render meter read " + std::to_string(whole_meter->frames()) +
                        " frames, not " + std::to_string(frames));
    }
    const std::uint64_t window_read = window_meter ? window_meter->frames() : whole_meter->frames();
    if (window_read != window.window_frames) {
      return file_error("loudness: the window meter read " + std::to_string(window_read) + " frames, not " +
                        std::to_string(window.window_frames));
    }
    cli::LoudnessReport l;
    l.window_start_frame = window.start_frame;
    l.window_body_frames = window.body_frames;
    l.window_repeats = window.repeats;
    l.window_frames = window.window_frames;
    l.whole_lufs_i = whole_meter->integrated();
    l.window_lufs_i = window_meter ? window_meter->integrated() : l.whole_lufs_i;
    loudness = l;
  }

  cli::Report report;
  report.engine_version = arc_engine_version();
  report.seed = arc_plan_seed(plan.plan);
  report.sample_rate = args.rate;
  report.mode = args.mode == ARC_MODE_FINAL ? "final" : "measure";
  report.frames = out_frames;
  report.loop = cli::loop_report(loop);
  report.spacing = spacing;
  report.preview = preview;
  report.loudness = loudness;
  if (true_peak_meter) {
    cli::TruePeakReport t;
    t.linear = true_peak_meter->linear();
    t.dbtp = cli::true_peak_dbtp(t.linear);
    report.true_peak = t;
  }
  report.determinism_key.recipe_hash = arc_plan_recipe_hash(plan.plan);
  report.determinism_key.engine_version = report.engine_version;
  report.determinism_key.sample_rate = args.rate;
  report.assertions.push_back(cli::render_speed(
      speed_row, out_frames, args.rate, cli::elapsed_seconds(render_time),
      cli::is_reference_machine(std::getenv("ARCANI_REFERENCE_MACHINE"))));
  // Story 4.2: in final mode, the loudness checks against the recipe target.
  if (tolerance_row != nullptr && loudness) {
    const std::optional<double> target = cli::top_level_number(*text, "loudness_target_lufs");
    if (!target) {
      return file_error("cannot read loudness_target_lufs");
    }
    report.assertions.push_back(cli::loudness_assertion(*tolerance_row, loudness->window_lufs_i, *target));
    report.assertions.push_back(cli::loudness_whole_assertion(*tolerance_row, loudness->whole_lufs_i, *target));
  }
  // Story 4.3: in final mode, the true-peak ceiling, the last assertion.
  if (true_peak_meter) {
    report.assertions.push_back(cli::true_peak_assertion(*true_peak_row, report.true_peak->linear));
  }

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
  if (args->store_gain) {
    try {
      return run_store(*args);
    } catch (const std::exception& e) {
      return file_error(e.what());
    }
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
