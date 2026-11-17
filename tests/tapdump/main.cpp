// Engine tap dump for the Python reference match (Story 1.5). Test-only: not
// part of engine/ and not shipped. Public C API header only.
//
// Usage: arcani-tapdump RECIPE RATE OUT_DIR [EXTRA_FRAMES]
//        arcani-tapdump RECIPE RATE OUT_DIR --window START FRAMES
//        arcani-tapdump RECIPE RATE OUT_DIR --output-only
//
// Compiles the recipe file RECIPE in measure mode at sample rate RATE (decimal
// digits; the engine refuses any rate but 44100 and 48000), then renders the
// whole session plus EXTRA_FRAMES frames past its end (default 0) in one
// arc_render call with every tap. Writes into OUT_DIR, each file raw
// little-endian binary64, interleaved stereo (left, right per frame), the
// pre-quantization engine output and the five taps of docs/signal-spec.md,
// Stub chain, Output and taps:
//
//   out.f64     render output
//   theta.f64   theta reference tap
//   gamma.f64   gamma PAC tap
//   bus.f64     stereo bus tap
//   join.f64    binaural join tap
//   master.f64  master tap
//
// On success prints one line "arcani-tapdump: frames N total T" on stdout
// (N the session length in frames, T = N + EXTRA_FRAMES) and exits 0. Exit 2
// on a usage error, 1 when the recipe cannot be read, is rejected, or a file
// cannot be written (one line on stderr).
//
// Story 2.7 adds two modes for long looping sessions:
//
// --window START FRAMES: arc_seek to frame START, then FRAMES frames in one
//   arc_render call with every tap; the same six files. Prints
//   "arcani-tapdump: frames N start S total T" (T = FRAMES).
// --output-only: the whole session in arc_render calls of kChunkFrames frames
//   with no taps, streamed to out.f64 alone, so a 20 min session needs no
//   whole-session buffer. Prints "arcani-tapdump: frames N total N".
//
// Story 3.1 adds the component table (docs/signal-spec.md, Components):
//
// --components [--mute left|right]: compiles with that muted ear (none by
//   default), renders nothing, and writes OUT_DIR/components.tsv: the header
//   ear<TAB>layer<TAB>gamma_mult<TAB>theta_mult<TAB>beat_mult<TAB>center_hz
//   <TAB>low_hz<TAB>high_hz<TAB>level, then one line per row of
//   arc_plan_component in table order (ear left or right; layer
//   theta_reference, gamma_pac, or binaural; the four doubles as %.17g), LF
//   line ends. Prints "arcani-tapdump: components N".
//
// Story 3.2 adds the spacing margins (docs/signal-spec.md, Spacing):
//
// --spacing [--mute left|right]: compiles with that muted ear, renders
//   nothing, and writes OUT_DIR/spacing.tsv: the header
//   ear<TAB>has_pair<TAB>min_distance_hz<TAB>margin_hz<TAB>component_1
//   <TAB>component_2, then one line per ear of arc_plan_spacing (left, then
//   right; has_pair 0 or 1; the doubles as %.17g; 0 in every field without a
//   pair), LF line ends. Prints "arcani-tapdump: spacing".
//
// A rejection prints the rejected line, with " detail=<detail>" appended
// when the error's detail is not empty (the spacing rule).

#include <arcani/arcani.h>

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

constexpr std::size_t kChunkFrames = 65536;

const char* const kUsage =
    "usage: arcani-tapdump RECIPE RATE OUT_DIR [EXTRA_FRAMES]\n"
    "       arcani-tapdump RECIPE RATE OUT_DIR --window START FRAMES\n"
    "       arcani-tapdump RECIPE RATE OUT_DIR --output-only\n"
    "       arcani-tapdump RECIPE RATE OUT_DIR --components [--mute left|right]\n"
    "       arcani-tapdump RECIPE RATE OUT_DIR --spacing [--mute left|right]\n";

bool parse_u64(const char* text, std::uint64_t& out) {
  if (text == nullptr || *text == '\0') {
    return false;
  }
  std::uint64_t v = 0;
  for (const char* p = text; *p != '\0'; ++p) {
    if (*p < '0' || *p > '9') {
      return false;
    }
    const std::uint64_t d = static_cast<std::uint64_t>(*p - '0');
    if (v > (UINT64_MAX - d) / 10) {
      return false;
    }
    v = v * 10 + d;
  }
  out = v;
  return true;
}

bool read_file(const char* path, std::string& out) {
  std::FILE* f = std::fopen(path, "rb");
  if (f == nullptr) {
    return false;
  }
  char buffer[4096];
  std::size_t got = 0;
  while ((got = std::fread(buffer, 1, sizeof buffer, f)) > 0) {
    out.append(buffer, got);
  }
  const bool ok = std::ferror(f) == 0;
  std::fclose(f);
  return ok;
}

// Appends samples as little-endian binary64 regardless of host byte order.
bool append_f64(std::FILE* f, const double* samples, std::size_t count) {
  std::vector<unsigned char> bytes;
  bytes.reserve(count * 8);
  for (std::size_t i = 0; i < count; ++i) {
    std::uint64_t word = 0;
    std::memcpy(&word, &samples[i], sizeof word);
    for (int k = 0; k < 8; ++k) {
      bytes.push_back(static_cast<unsigned char>((word >> (8 * k)) & 0xFFu));
    }
  }
  return bytes.empty() || std::fwrite(bytes.data(), 1, bytes.size(), f) == bytes.size();
}

bool write_f64(const std::string& path, const std::vector<double>& samples) {
  std::FILE* f = std::fopen(path.c_str(), "wb");
  if (f == nullptr) {
    return false;
  }
  const bool written = append_f64(f, samples.data(), samples.size());
  const bool closed = std::fclose(f) == 0;
  return written && closed;
}

enum class Mode { Whole, Window, OutputOnly, Components, Spacing };

struct Args {
  Mode mode = Mode::Whole;
  std::uint64_t rate = 0;
  std::uint64_t extra = 0;   // Whole: frames past the session end
  std::uint64_t start = 0;   // Window: the seek frame
  std::uint64_t frames = 0;  // Window: the frames rendered
  arc_mute_ear mute = ARC_MUTE_NONE;  // Components: the muted binaural ear
};

bool parse_args(int argc, char** argv, Args& a) {
  if (argc < 4 || !parse_u64(argv[2], a.rate) || a.rate > UINT32_MAX) {
    return false;
  }
  if (argc == 4) {
    return true;
  }
  if (std::strcmp(argv[4], "--components") == 0 || std::strcmp(argv[4], "--spacing") == 0) {
    a.mode = std::strcmp(argv[4], "--spacing") == 0 ? Mode::Spacing : Mode::Components;
    if (argc == 5) {
      return true;
    }
    if (argc != 7 || std::strcmp(argv[5], "--mute") != 0) {
      return false;
    }
    if (std::strcmp(argv[6], "left") == 0) {
      a.mute = ARC_MUTE_LEFT;
      return true;
    }
    if (std::strcmp(argv[6], "right") == 0) {
      a.mute = ARC_MUTE_RIGHT;
      return true;
    }
    return false;
  }
  if (argc == 5 && std::strcmp(argv[4], "--output-only") == 0) {
    a.mode = Mode::OutputOnly;
    return true;
  }
  if (argc == 5) {
    return parse_u64(argv[4], a.extra);
  }
  if (argc == 7 && std::strcmp(argv[4], "--window") == 0) {
    a.mode = Mode::Window;
    return parse_u64(argv[5], a.start) && parse_u64(argv[6], a.frames);
  }
  return false;
}

// Renders `count` frames from the renderer's current frame with every tap
// and writes the six files.
int dump_taps(arc_renderer* renderer, std::size_t count, const std::string& out_dir, arc_error& error) {
  struct Buffer {
    const char* name;
    std::vector<double> samples;
  };
  Buffer buffers[] = {
      {"out", std::vector<double>(2 * count)},    {"theta", std::vector<double>(2 * count)},
      {"gamma", std::vector<double>(2 * count)},  {"bus", std::vector<double>(2 * count)},
      {"join", std::vector<double>(2 * count)},   {"master", std::vector<double>(2 * count)},
  };
  arc_taps taps;
  std::memset(&taps, 0, sizeof taps);
  taps.theta_reference = buffers[1].samples.data();
  taps.gamma_pac = buffers[2].samples.data();
  taps.stereo_bus = buffers[3].samples.data();
  taps.binaural_join = buffers[4].samples.data();
  taps.master = buffers[5].samples.data();
  if (arc_render(renderer, buffers[0].samples.data(), count, &taps, &error) != ARC_OK) {
    std::fprintf(stderr, "arcani-tapdump: render failed: %s\n", error.rule);
    return 1;
  }
  for (const Buffer& b : buffers) {
    const std::string path = out_dir + "/" + b.name + ".f64";
    if (!write_f64(path, b.samples)) {
      std::fprintf(stderr, "arcani-tapdump: cannot write %s\n", path.c_str());
      return 1;
    }
  }
  return 0;
}

// Writes the plan's component table to OUT_DIR/components.tsv.
int dump_components(const arc_plan* plan, const std::string& out_dir, arc_error& error) {
  static const char* const kLayers[] = {"theta_reference", "gamma_pac", "binaural"};
  static const char* const kEars[] = {"left", "right"};
  std::string text = "ear\tlayer\tgamma_mult\ttheta_mult\tbeat_mult\tcenter_hz\tlow_hz\thigh_hz\tlevel\n";
  const std::size_t count = arc_plan_component_count(plan);
  for (std::size_t i = 0; i < count; ++i) {
    arc_component c;
    if (arc_plan_component(plan, i, &c, &error) != ARC_OK) {
      std::fprintf(stderr, "arcani-tapdump: component %zu failed: %s\n", i, error.rule);
      return 1;
    }
    const int layer = static_cast<int>(c.layer);
    const int ear = static_cast<int>(c.ear);
    if (layer < 0 || layer > 2 || ear < 0 || ear > 1) {
      std::fprintf(stderr, "arcani-tapdump: component %zu has no layer or ear name\n", i);
      return 1;
    }
    char line[512];
    std::snprintf(line, sizeof line, "%s\t%s\t%ld\t%ld\t%ld\t%.17g\t%.17g\t%.17g\t%.17g\n", kEars[ear],
                  kLayers[layer], static_cast<long>(c.gamma_mult), static_cast<long>(c.theta_mult),
                  static_cast<long>(c.beat_mult), c.center_hz, c.low_hz, c.high_hz, c.level);
    text += line;
  }
  const std::string path = out_dir + "/components.tsv";
  std::FILE* f = std::fopen(path.c_str(), "wb");
  if (f == nullptr) {
    std::fprintf(stderr, "arcani-tapdump: cannot write %s\n", path.c_str());
    return 1;
  }
  const bool written = std::fwrite(text.data(), 1, text.size(), f) == text.size();
  const bool closed = std::fclose(f) == 0;
  if (!written || !closed) {
    std::fprintf(stderr, "arcani-tapdump: cannot write %s\n", path.c_str());
    return 1;
  }
  std::printf("arcani-tapdump: components %zu\n", count);
  return 0;
}

// Writes the plan's spacing margins to OUT_DIR/spacing.tsv.
int dump_spacing(const arc_plan* plan, const std::string& out_dir, arc_error& error) {
  static const char* const kEars[] = {"left", "right"};
  std::string text = "ear\thas_pair\tmin_distance_hz\tmargin_hz\tcomponent_1\tcomponent_2\n";
  for (int ear = 0; ear < 2; ++ear) {
    arc_spacing s;
    if (arc_plan_spacing(plan, ear == 0 ? ARC_EAR_LEFT : ARC_EAR_RIGHT, &s, &error) != ARC_OK) {
      std::fprintf(stderr, "arcani-tapdump: spacing failed: %s\n", error.rule);
      return 1;
    }
    char line[256];
    std::snprintf(line, sizeof line, "%s\t%d\t%.17g\t%.17g\t%llu\t%llu\n", kEars[ear], static_cast<int>(s.has_pair),
                  s.min_distance_hz, s.margin_hz, static_cast<unsigned long long>(s.component_1),
                  static_cast<unsigned long long>(s.component_2));
    text += line;
  }
  const std::string path = out_dir + "/spacing.tsv";
  std::FILE* f = std::fopen(path.c_str(), "wb");
  if (f == nullptr) {
    std::fprintf(stderr, "arcani-tapdump: cannot write %s\n", path.c_str());
    return 1;
  }
  const bool written = std::fwrite(text.data(), 1, text.size(), f) == text.size();
  const bool closed = std::fclose(f) == 0;
  if (!written || !closed) {
    std::fprintf(stderr, "arcani-tapdump: cannot write %s\n", path.c_str());
    return 1;
  }
  std::printf("arcani-tapdump: spacing\n");
  return 0;
}

// Streams the whole session's output, kChunkFrames frames per call, to out.f64.
int dump_output(arc_renderer* renderer, std::uint64_t frames, const std::string& out_dir, arc_error& error) {
  const std::string path = out_dir + "/out.f64";
  std::FILE* f = std::fopen(path.c_str(), "wb");
  if (f == nullptr) {
    std::fprintf(stderr, "arcani-tapdump: cannot write %s\n", path.c_str());
    return 1;
  }
  std::vector<double> samples(2 * kChunkFrames);
  bool ok = true;
  for (std::uint64_t done = 0; ok && done < frames;) {
    const std::uint64_t left = frames - done;
    const std::size_t n = left < kChunkFrames ? static_cast<std::size_t>(left) : kChunkFrames;
    if (arc_render(renderer, samples.data(), n, nullptr, &error) != ARC_OK) {
      std::fprintf(stderr, "arcani-tapdump: render failed: %s\n", error.rule);
      std::fclose(f);
      return 1;
    }
    ok = append_f64(f, samples.data(), 2 * n);
    done += n;
  }
  const bool closed = std::fclose(f) == 0;
  if (!ok || !closed) {
    std::fprintf(stderr, "arcani-tapdump: cannot write %s\n", path.c_str());
    return 1;
  }
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  Args args;
  if (!parse_args(argc, argv, args)) {
    std::fputs(kUsage, stderr);
    return 2;
  }
  std::string recipe;
  if (!read_file(argv[1], recipe)) {
    std::fprintf(stderr, "arcani-tapdump: cannot read %s\n", argv[1]);
    return 1;
  }

  arc_compile_options options;
  std::memset(&options, 0, sizeof options);
  options.mode = ARC_MODE_MEASURE;
  options.sample_rate = static_cast<std::uint32_t>(args.rate);
  options.mute_binaural_ear = args.mute;
  arc_error error;
  std::memset(&error, 0, sizeof error);
  arc_plan* plan = nullptr;
  if (arc_compile(recipe.data(), recipe.size(), &options, &plan, &error) != ARC_OK) {
    if (error.detail[0] != '\0') {
      std::fprintf(stderr, "arcani-tapdump: rejected: parameter=%s value=%s rule=%s limit=%s detail=%s\n",
                   error.parameter, error.value, error.rule, error.limit, error.detail);
    } else {
      std::fprintf(stderr, "arcani-tapdump: rejected: parameter=%s value=%s rule=%s limit=%s\n",
                   error.parameter, error.value, error.rule, error.limit);
    }
    return 1;
  }
  if (args.mode == Mode::Spacing) {
    const int status = dump_spacing(plan, argv[3], error);
    arc_plan_release(plan);
    return status;
  }
  if (args.mode == Mode::Components) {
    const int status = dump_components(plan, argv[3], error);
    arc_plan_release(plan);
    return status;
  }
  const std::uint64_t frames = arc_plan_frame_count(plan);
  std::uint64_t total = frames;  // OutputOnly
  bool wrapped = false;
  if (args.mode == Mode::Whole) {
    total = frames + args.extra;
    wrapped = total < frames;
  } else if (args.mode == Mode::Window) {
    total = args.frames;
  }
  if (wrapped || total > SIZE_MAX / 16) {
    std::fprintf(stderr, "arcani-tapdump: too many frames\n");
    arc_plan_release(plan);
    return 1;
  }

  arc_renderer* renderer = nullptr;
  if (arc_renderer_create(plan, &renderer, &error) != ARC_OK) {
    std::fprintf(stderr, "arcani-tapdump: render failed: %s\n", error.rule);
    arc_plan_release(plan);
    return 1;
  }
  const std::string out_dir = argv[3];
  int status = 0;
  if (args.mode == Mode::OutputOnly) {
    status = dump_output(renderer, frames, out_dir, error);
  } else {
    if (args.mode == Mode::Window && arc_seek(renderer, args.start, &error) != ARC_OK) {
      std::fprintf(stderr, "arcani-tapdump: seek failed: %s\n", error.rule);
      status = 1;
    }
    if (status == 0) {
      status = dump_taps(renderer, static_cast<std::size_t>(total), out_dir, error);
    }
  }
  arc_renderer_destroy(renderer);
  arc_plan_release(plan);
  if (status != 0) {
    return status;
  }
  if (args.mode == Mode::Window) {
    std::printf("arcani-tapdump: frames %llu start %llu total %llu\n", static_cast<unsigned long long>(frames),
                static_cast<unsigned long long>(args.start), static_cast<unsigned long long>(total));
  } else {
    std::printf("arcani-tapdump: frames %llu total %llu\n", static_cast<unsigned long long>(frames),
                static_cast<unsigned long long>(total));
  }
  return 0;
}
