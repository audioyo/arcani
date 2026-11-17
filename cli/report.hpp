// The JSON report and the render speed assertion for arcani-render
// (Story 1.4).

#ifndef ARCANI_CLI_REPORT_HPP
#define ARCANI_CLI_REPORT_HPP

#include <arcani/arcani.h>

#include "tables.hpp"

#include <chrono>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace arcani::cli {

enum class Result { pass, fail, not_applicable };

struct Assertion {
  std::string name;                // "render speed"
  std::string row;                 // table row id, "render-speed"
  double threshold = 0.0;          // the row's value
  std::string unit;                // the row's unit
  std::optional<double> measured;  // empty: written as null
  Result result = Result::not_applicable;
  std::string note;  // empty unless not_applicable
};

struct DeterminismKey {
  std::string recipe_hash;                // 64 lowercase hex digits
  std::vector<std::string> asset_hashes;  // empty in v0.1
  std::string engine_version;
  std::uint32_t sample_rate = 0;
};

// The loop block of a looping recipe (docs/signal-spec.md, Loop, Report;
// Story 2.7): the opening end, every seam in order, and the session end, in
// frames.
struct LoopReport {
  std::uint64_t opening_end_frame = 0;
  std::vector<std::uint64_t> seam_frames;
  std::uint64_t end_frame = 0;
};

// The spacing block of a recipe with a spacing pair in at least one ear
// (docs/signal-spec.md, Spacing, Report; Story 3.2): per ear the worst
// pair's minimum distance, margin, both component indices, and the pair
// named as in the error detail.
struct SpacingEar {
  double min_distance_hz = 0.0;
  double margin_hz = 0.0;
  std::uint64_t component_1 = 0;
  std::uint64_t component_2 = 0;
  std::string pair;
};

struct SpacingReport {
  std::optional<SpacingEar> left;
  std::optional<SpacingEar> right;
};

// The preview member of a preview render (docs/signal-spec.md, Preview,
// Report; Story 3.3). "signed" is always written false: no preview is ever
// signed off.
struct PreviewReport {
  double peak_dbfs = 0.0;           // P, row preview-peak-level
  std::uint32_t layers_per_ear = 0; // n_max
  double gain = 0.0;                // g
  double seconds = 0.0;             // F / fs
};

struct Report {
  std::string engine_version;
  std::uint64_t seed = 0;
  std::uint32_t sample_rate = 0;
  std::string mode;  // "measure" or "final"
  std::uint64_t frames = 0;
  std::optional<LoopReport> loop;  // written only when present
  std::optional<SpacingReport> spacing;  // Story 3.2; written only when present
  std::optional<PreviewReport> preview;  // Story 3.3; written only when present
  DeterminismKey determinism_key;
  std::vector<Assertion> assertions;
};

// A JSON string literal, quotes included. Escapes " and \, \b \t \n \f \r,
// every other byte below 0x20 as \u00xx (lowercase hex); nothing else.
std::string json_string(std::string_view utf8);

// Shortest round-trip text of a finite double (std::to_chars).
std::string json_number(double x);

// The loop block from the C API loop frames: seam k (1 to seam_count) is
// opening_end_frame + k * body_frames. Empty when looping is 0.
std::optional<LoopReport> loop_report(const arc_loop_frames& frames);

// The spacing block from arc_plan_spacing and arc_plan_component into
// `out`: empty when neither ear has a pair. Returns false, with `rule` set
// to the failing call's rule, when an engine call fails, so the caller fails
// loudly instead of reporting no pair.
bool spacing_report(const arc_plan* plan, std::optional<SpacingReport>& out, std::string& rule);

// The report as one UTF-8 JSON object, members in struct order. The loop,
// spacing, and preview members are left out when absent, so a report without
// them is unchanged.
std::string report_json(const Report& report);

// True only when the value of ARCANI_REFERENCE_MACHINE (nullptr when unset)
// is exactly "1".
bool is_reference_machine(const char* env_value) noexcept;

// The summed arc_render time in seconds; a total of 0 ticks counts as 1.
double elapsed_seconds(std::chrono::steady_clock::duration total) noexcept;

// The render speed assertion against `row` (render-speed). frames == 0 is
// not applicable ("no frames"), checked first; then a machine other than
// the reference one ("not the reference machine"); else measured =
// (frames / rate) / elapsed_s, pass when measured >= threshold.
Assertion render_speed(const arcani::test::tables::Row& row, std::uint64_t frames,
                       std::uint32_t rate, double elapsed_s, bool is_reference);

// 4 when any assertion failed, else 0.
int assertions_exit_code(const std::vector<Assertion>& assertions) noexcept;

}  // namespace arcani::cli

#endif  // ARCANI_CLI_REPORT_HPP
