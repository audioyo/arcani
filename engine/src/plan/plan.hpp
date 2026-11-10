// Plan compile and the fixed stage list (Story 1.2; docs/signal-spec.md,
// Stub chain).
//
// compile() turns recipe text into an immutable Plan, or one blocking error
// naming parameter, value, rule, and limit. The plan holds everything the
// renderer needs (session length, theta reference carrier and envelope
// increments, depth, and edge lengths, gamma PAC carrier and envelope
// increments and depth, binaural oscillator increments and amplitudes), so
// render does no lookup and has no test branch: a muted ear is increment 0
// and amplitude 0.0 in the plan.
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
#include <string>
#include <string_view>
#include <vector>

#include "core/envelope.hpp"
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

// The fixed stage list, in stage order. This table is the declared channel
// contract; it does not drive the renderer. The renderer's output is held to
// it by the muted-ear tests and the stub chain vector tests
// (tests/cpp/test_stages.cpp, tests/cpp/test_isolation.cpp).
std::span<const StageDescriptor> stage_descriptors() noexcept;

enum class Mode { Measure, Final };
enum class MuteEar { None, Left, Right };

// Largest recipe text compile accepts, in bytes (1 MiB).
inline constexpr std::size_t kMaxInputBytes = 1048576;

// Theta reference (docs/signal-spec.md, Theta reference): a carrier
// amplitude-modulated at the theta rate by one envelope shape, the same value
// in both channels. Carrier and envelope phases are each 0 at n = 0. Per
// sample: e = envelope(shape, phase_E, edge_units, half_on_units),
// a = 1.0 - depth * (1.0 - e), theta = a * sine(phase_T). Without a
// theta_reference field, present is false and theta is +0.0.
struct ThetaOscillator {
  bool present = false;
  std::uint64_t increment = 0;           // carrier: phase increment rule (carrier_hz, fs)
  std::uint64_t envelope_increment = 0;  // envelope: phase increment rule (rate_hz, fs)
  double depth = 0.0;                    // d = am_depth_percent / 100.0
  core::EnvelopeShape shape = core::EnvelopeShape::Sine;
  std::uint64_t edge_units = 0;     // W at rate_hz
  std::uint64_t half_on_units = 0;  // H
};

// Gamma PAC layer, uncoupled (docs/signal-spec.md, Gamma PAC layer): a sine
// carrier amplitude-modulated at the gamma rate by the sine envelope, with a
// depth constant for the render, the same value in both channels. Carrier
// and envelope phases are each 0 at n = 0. Per sample:
// e = sine_envelope(phase_M), a = 1.0 - depth * (1.0 - e),
// gamma = a * sine(phase_G). Without a gamma_pac field, present is false and
// gamma is +0.0.
struct GammaOscillator {
  bool present = false;
  std::uint64_t increment = 0;           // carrier: phase increment rule (carrier_hz, fs)
  std::uint64_t envelope_increment = 0;  // envelope: phase increment rule (rate_hz, fs)
  double depth = 0.0;                    // d = am_depth_percent / 100.0, constant (uncoupled)
};

// Binaural oscillators of one ear pair: unmodulated sines, phase 0 at n = 0.
struct BinauralEars {
  std::array<std::uint64_t, 2> increment{0, 0};  // left, right
  std::array<double, 2> amplitude{0.0, 0.0};     // 1.0, or 0.0 when absent or muted
};

struct Plan {
  std::uint32_t sample_rate = 0;
  std::uint64_t frame_count = 0;  // seconds_to_samples(length_s, fs)
  std::string recipe_hash;        // from parse, 64 lowercase hex digits
  std::uint64_t seed = 0;         // the recipe seed
  ThetaOscillator theta;
  GammaOscillator gamma;
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
