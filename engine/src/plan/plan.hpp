// Plan compile and the fixed stage list (Story 1.2; docs/signal-spec.md,
// Stub chain).
//
// compile() turns recipe text into an immutable Plan, or one blocking error
// naming parameter, value, rule, and limit. The plan holds everything the
// renderer needs (session length, binaural oscillator increments and
// amplitudes), so render does no lookup and has no test branch: a muted ear
// is increment 0 and amplitude 0.0 in the plan.
//
// The stage order is fixed and is not a recipe field. Every stage writes
// channel c only from channel c of its inputs; the master chain limiter alone
// reads both channels, and only to derive one linked gain.

#ifndef ARCANI_PLAN_PLAN_HPP
#define ARCANI_PLAN_PLAN_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string_view>
#include <vector>

#include "recipe/recipe.hpp"

namespace arcani::plan {

// Values equal arc_stage_kind in arcani/arcani.h.
enum class StageKind : int {
  ThetaReference = 0,
  GammaPac = 1,
  StereoBus = 2,
  BinauralJoin = 3,
  MasterChain = 4
};

enum class ChannelUse {
  PerChannel,  // output channel c depends only on input channel c
  LinkedGain   // reads both channels only to derive one gain applied to each
};

struct StageDescriptor {
  StageKind kind;
  ChannelUse channel_use;
  std::array<int, 2> input_channel;  // output channel c reads input channel input_channel[c]
};

// The fixed stage list, in stage order.
std::span<const StageDescriptor> stage_descriptors() noexcept;

enum class Mode { Measure, Final };
enum class MuteEar { None, Left, Right };

// Largest recipe text compile accepts, in bytes (1 MiB).
inline constexpr std::size_t kMaxInputBytes = 1048576;

// Binaural oscillators of one ear pair: unmodulated sines, phase 0 at n = 0.
struct BinauralEars {
  std::array<std::uint64_t, 2> increment{0, 0};  // left, right
  std::array<double, 2> amplitude{0.0, 0.0};     // 1.0, or 0.0 when absent or muted
};

struct Plan {
  std::uint32_t sample_rate = 0;
  std::uint64_t frame_count = 0;  // seconds_to_samples(length_s, fs)
  BinauralEars binaural;
  std::array<StageKind, 5> stages{};
  std::vector<recipe::Error> warnings;  // non-blocking; empty in v0.1
};

struct CompileResult {
  std::optional<Plan> plan;  // empty on error
  recipe::Error error;
};

// Sample rates the engine renders natively (row sample-rates).
inline constexpr std::string_view kSampleRatesText = "44100 48000";

// Compiles recipe text. The caller has already checked the enum options.
// Throws only std::bad_alloc.
CompileResult compile(std::string_view utf8, Mode mode, std::uint32_t sample_rate, MuteEar mute);

}  // namespace arcani::plan

#endif  // ARCANI_PLAN_PLAN_HPP
