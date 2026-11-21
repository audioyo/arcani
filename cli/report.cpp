// The JSON report and the render speed assertion (Story 1.4). See
// report.hpp.

#include "report.hpp"

#include <charconv>
#include <cmath>
#include <cstring>
#include <system_error>

namespace arcani::cli {

namespace {

const char* result_text(Result r) noexcept {
  switch (r) {
    case Result::pass:
      return "pass";
    case Result::fail:
      return "fail";
    case Result::not_applicable:
      break;
  }
  return "not_applicable";
}

std::string integer(std::uint64_t v) {
  char buf[32];
  const auto r = std::to_chars(buf, buf + sizeof buf, v);
  return std::string(buf, r.ptr);
}

// A loudness reading: null when it is not finite (-infinity: no block passed
// the gates).
std::string reading(double lufs) { return std::isfinite(lufs) ? json_number(lufs) : std::string("null"); }

}  // namespace

std::string json_string(std::string_view utf8) {
  static const char kHex[] = "0123456789abcdef";
  std::string out = "\"";
  for (char c : utf8) {
    const auto b = static_cast<unsigned char>(c);
    switch (c) {
      case '"':
        out += "\\\"";
        break;
      case '\\':
        out += "\\\\";
        break;
      case '\b':
        out += "\\b";
        break;
      case '\t':
        out += "\\t";
        break;
      case '\n':
        out += "\\n";
        break;
      case '\f':
        out += "\\f";
        break;
      case '\r':
        out += "\\r";
        break;
      default:
        if (b < 0x20) {
          out += "\\u00";
          out += kHex[b >> 4];
          out += kHex[b & 0xF];
        } else {
          out += c;
        }
    }
  }
  out += '"';
  return out;
}

std::string json_number(double x) {
  char buf[64];
  const auto r = std::to_chars(buf, buf + sizeof buf, x);
  if (r.ec != std::errc()) {
    return "null";  // not reached: 64 bytes hold any binary64
  }
  return std::string(buf, r.ptr);
}

std::optional<LoopReport> loop_report(const arc_loop_frames& frames) {
  if (frames.looping == 0) {
    return std::nullopt;
  }
  LoopReport loop;
  loop.opening_end_frame = frames.opening_end_frame;
  loop.end_frame = frames.end_frame;
  loop.seam_frames.reserve(static_cast<std::size_t>(frames.seam_count));
  for (std::uint64_t k = 1; k <= frames.seam_count; ++k) {
    loop.seam_frames.push_back(frames.opening_end_frame + k * frames.body_frames);
  }
  return loop;
}

namespace {

const char* const kLayerNames[] = {"theta_reference", "gamma_pac", "binaural"};

bool row_name(const arc_plan* plan, std::size_t index, std::string& out, std::string& rule) {
  arc_component c;
  arc_error e;
  std::memset(&e, 0, sizeof e);
  if (arc_plan_component(plan, index, &c, &e) != ARC_OK) {
    rule = e.rule;
    return false;
  }
  const int layer = static_cast<int>(c.layer);
  if (layer < 0 || layer > 2) {
    rule = "component layer out of range";
    return false;
  }
  out = std::string(kLayerNames[layer]) + " (" + std::to_string(c.gamma_mult) + ", " +
        std::to_string(c.theta_mult) + ", " + std::to_string(c.beat_mult) + ") at " + json_number(c.center_hz) +
        " Hz";
  return true;
}

std::string spacing_ear_json(const std::optional<SpacingEar>& e) {
  if (!e) {
    return "null";
  }
  return "{\"min_distance_hz\": " + json_number(e->min_distance_hz) + ", \"margin_hz\": " +
         json_number(e->margin_hz) + ", \"component_1\": " + integer(e->component_1) +
         ", \"component_2\": " + integer(e->component_2) + ", \"pair\": " + json_string(e->pair) + "}";
}

}  // namespace

bool spacing_report(const arc_plan* plan, std::optional<SpacingReport>& out_report, std::string& rule) {
  out_report.reset();
  SpacingReport report;
  bool any = false;
  for (const arc_ear ear : {ARC_EAR_LEFT, ARC_EAR_RIGHT}) {
    arc_spacing s;
    arc_error e;
    std::memset(&s, 0, sizeof s);
    std::memset(&e, 0, sizeof e);
    if (arc_plan_spacing(plan, ear, &s, &e) != ARC_OK) {
      rule = e.rule;
      return false;
    }
    if (s.has_pair == 0) {
      continue;  // no pair in this ear: the normal path
    }
    SpacingEar out;
    out.min_distance_hz = s.min_distance_hz;
    out.margin_hz = s.margin_hz;
    out.component_1 = s.component_1;
    out.component_2 = s.component_2;
    std::string a;
    std::string b;
    if (!row_name(plan, s.component_1, a, rule) || !row_name(plan, s.component_2, b, rule)) {
      return false;
    }
    out.pair = a + " and " + b;
    (ear == ARC_EAR_LEFT ? report.left : report.right) = out;
    any = true;
  }
  if (any) {
    out_report = report;
  }
  return true;
}

std::string report_json(const Report& report) {
  const DeterminismKey& key = report.determinism_key;
  std::string out = "{\n";
  out += "  \"engine_version\": " + json_string(report.engine_version) + ",\n";
  out += "  \"seed\": " + integer(report.seed) + ",\n";
  out += "  \"sample_rate\": " + integer(report.sample_rate) + ",\n";
  out += "  \"mode\": " + json_string(report.mode) + ",\n";
  out += "  \"frames\": " + integer(report.frames) + ",\n";
  if (report.loop) {
    const LoopReport& loop = *report.loop;
    out += "  \"loop\": {\n";
    out += "    \"opening_end_frame\": " + integer(loop.opening_end_frame) + ",\n";
    out += "    \"seam_frames\": [";
    for (std::size_t i = 0; i < loop.seam_frames.size(); ++i) {
      out += (i == 0 ? "" : ", ") + integer(loop.seam_frames[i]);
    }
    out += "],\n";
    out += "    \"end_frame\": " + integer(loop.end_frame) + "\n";
    out += "  },\n";
  }
  if (report.spacing) {
    out += "  \"spacing\": {\n";
    out += "    \"left\": " + spacing_ear_json(report.spacing->left) + ",\n";
    out += "    \"right\": " + spacing_ear_json(report.spacing->right) + "\n";
    out += "  },\n";
  }
  if (report.preview) {
    const PreviewReport& p = *report.preview;
    out += "  \"preview\": {\n";
    out += "    \"signed\": false,\n";
    out += "    \"peak_dbfs\": " + json_number(p.peak_dbfs) + ",\n";
    out += "    \"layers_per_ear\": " + integer(p.layers_per_ear) + ",\n";
    out += "    \"gain\": " + json_number(p.gain) + ",\n";
    out += "    \"seconds\": " + json_number(p.seconds) + "\n";
    out += "  },\n";
  }
  if (report.loudness) {
    const LoudnessReport& l = *report.loudness;
    out += "  \"loudness\": {\n";
    out += "    \"window_start_frame\": " + integer(l.window_start_frame) + ",\n";
    out += "    \"window_body_frames\": " + integer(l.window_body_frames) + ",\n";
    out += "    \"window_repeats\": " + integer(l.window_repeats) + ",\n";
    out += "    \"window_frames\": " + integer(l.window_frames) + ",\n";
    out += "    \"window_lufs_i\": " + reading(l.window_lufs_i) + ",\n";
    out += "    \"whole_lufs_i\": " + reading(l.whole_lufs_i) + "\n";
    out += "  },\n";
  }
  out += "  \"determinism_key\": {\n";
  out += "    \"recipe_hash\": " + json_string(key.recipe_hash) + ",\n";
  out += "    \"asset_hashes\": [";
  for (std::size_t i = 0; i < key.asset_hashes.size(); ++i) {
    out += (i == 0 ? "" : ", ") + json_string(key.asset_hashes[i]);
  }
  out += "],\n";
  out += "    \"engine_version\": " + json_string(key.engine_version) + ",\n";
  out += "    \"sample_rate\": " + integer(key.sample_rate) + "\n";
  out += "  },\n";
  out += "  \"assertions\": [";
  for (std::size_t i = 0; i < report.assertions.size(); ++i) {
    const Assertion& a = report.assertions[i];
    out += i == 0 ? "\n" : ",\n";
    out += "    {\"name\": " + json_string(a.name);
    out += ", \"row\": " + json_string(a.row);
    out += ", \"threshold\": " + json_number(a.threshold);
    out += ", \"unit\": " + json_string(a.unit);
    out += ", \"measured\": " + (a.measured ? json_number(*a.measured) : std::string("null"));
    out += ", \"result\": " + json_string(result_text(a.result));
    out += ", \"note\": " + json_string(a.note) + "}";
  }
  out += report.assertions.empty() ? "]\n" : "\n  ]\n";
  out += "}\n";
  return out;
}

bool is_reference_machine(const char* env_value) noexcept {
  return env_value != nullptr && std::strcmp(env_value, "1") == 0;
}

double elapsed_seconds(std::chrono::steady_clock::duration total) noexcept {
  using clock = std::chrono::steady_clock;
  const clock::duration counted = total.count() <= 0 ? clock::duration(1) : total;
  return std::chrono::duration<double>(counted).count();
}

Assertion render_speed(const arcani::test::tables::Row& row, std::uint64_t frames,
                       std::uint32_t rate, double elapsed_s, bool is_reference) {
  Assertion a;
  a.name = "render speed";
  a.row = row.id;
  a.threshold = row.value();
  a.unit = row.unit;
  if (frames == 0) {
    a.result = Result::not_applicable;
    a.note = "no frames";
    return a;
  }
  if (!is_reference) {
    a.result = Result::not_applicable;
    a.note = "not the reference machine";
    return a;
  }
  const double measured = (static_cast<double>(frames) / rate) / elapsed_s;
  a.measured = measured;
  a.result = measured >= a.threshold ? Result::pass : Result::fail;
  return a;
}

int assertions_exit_code(const std::vector<Assertion>& assertions) noexcept {
  for (const Assertion& a : assertions) {
    if (a.result == Result::fail) {
      return 4;
    }
  }
  return 0;
}

}  // namespace arcani::cli
