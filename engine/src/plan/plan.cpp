// Plan compile and the fixed stage list.

#include "plan/plan.hpp"

#include <optional>
#include <string>
#include <utility>

#include "core/envelope.hpp"
#include "core/phase.hpp"
#include "validate/validate.hpp"

namespace arcani::plan {

namespace {

constexpr StageDescriptor kStages[] = {
    {StageKind::ThetaReference, ChannelUse::PerChannel, {0, 1}},
    {StageKind::GammaPac, ChannelUse::PerChannel, {0, 1}},
    {StageKind::StereoBus, ChannelUse::PerChannel, {0, 1}},
    {StageKind::BinauralJoin, ChannelUse::PerChannel, {0, 1}},
    {StageKind::MasterChain, ChannelUse::LinkedGain, {0, 1}},
};

CompileResult fail(std::string parameter, std::string value, std::string rule, std::string limit) {
  CompileResult r;
  r.error = {std::move(parameter), std::move(value), std::move(rule), std::move(limit)};
  return r;
}

core::EnvelopeShape envelope_shape(recipe::ThetaShape s) noexcept {
  switch (s) {
    case recipe::ThetaShape::SmoothedOnOff:
      return core::EnvelopeShape::SmoothedOnOff;
    case recipe::ThetaShape::Sawtooth:
      return core::EnvelopeShape::Sawtooth;
    case recipe::ThetaShape::ReverseSaw:
      return core::EnvelopeShape::ReverseSaw;
    case recipe::ThetaShape::Sine:
    case recipe::ThetaShape::Custom:  // rejected before the plan is built
      break;
  }
  return core::EnvelopeShape::Sine;
}

}  // namespace

std::span<const StageDescriptor> stage_descriptors() noexcept { return kStages; }

CompileResult compile(std::string_view utf8, Mode mode, std::uint32_t sample_rate, MuteEar mute) {
  if (utf8.size() > kMaxInputBytes) {
    return fail("", std::to_string(utf8.size()), "input.max_bytes", std::to_string(kMaxInputBytes));
  }
  if (sample_rate != 44100 && sample_rate != 48000) {
    return fail("sample_rate", std::to_string(sample_rate), "sample_rate", std::string(kSampleRatesText));
  }

  recipe::ParseResult parsed = recipe::parse(utf8);
  if (!parsed.recipe) {
    CompileResult r;
    r.error = std::move(parsed.error);
    return r;
  }
  const recipe::Recipe& rec = *parsed.recipe;

  // Locked ranges (Story 1.3), in both modes, before final.required.
  if (std::optional<recipe::Error> e = validate::check_ranges(rec)) {
    CompileResult r;
    r.error = std::move(*e);
    return r;
  }

  // Carrier rules, theta shape rule (Story 2.1), and gamma carrier wave rule
  // (Story 2.2), after every range check.
  if (std::optional<recipe::Error> e = validate::check_rules(rec)) {
    CompileResult r;
    r.error = std::move(*e);
    return r;
  }

  if (mode == Mode::Final) {
    if (!rec.loudness_gain_db) {
      return fail("/loudness_gain_db", "absent", "final.required", "present in final mode");
    }
    if (!rec.loudness_hash) {
      return fail("/loudness_hash", "absent", "final.required", "present in final mode");
    }
  }

  Plan p;
  p.sample_rate = sample_rate;
  p.frame_count = core::seconds_to_samples(rec.length_s, sample_rate);
  p.recipe_hash = rec.hash;
  p.seed = rec.seed;
  for (std::size_t i = 0; i < p.stages.size(); ++i) {
    p.stages[i] = kStages[i].kind;
  }

  // Theta reference: the carrier at theta_reference.carrier_hz,
  // amplitude-modulated at rate_hz by the shape's envelope, both phases 0 at
  // n = 0, the same value in both channels. check_rules() has rejected a
  // custom shape. The mute option never touches it.
  if (rec.theta_reference) {
    const recipe::ThetaReference& t = *rec.theta_reference;
    p.theta.present = true;
    p.theta.increment = core::phase_increment(t.carrier_hz, sample_rate);
    p.theta.envelope_increment = core::phase_increment(t.rate_hz, sample_rate);
    p.theta.depth = t.am_depth_percent / 100.0;
    p.theta.shape = envelope_shape(t.shape);
    p.theta.edge_units = core::theta_edge_units(t.rate_hz);
    p.theta.half_on_units = core::theta_half_on_units();
  }

  // Gamma PAC layer: the carrier at gamma_pac.carrier_hz, amplitude-modulated
  // at rate_hz by the sine envelope, both phases 0 at n = 0, the same value in
  // both channels; uncoupled with a constant depth, smooth_swell with the depth
  // scaled by the swell of the theta envelope phase about C. check_rules() has
  // rejected a non-sine carrier, coupled gamma with depth but no theta
  // reference depth, and a missing or stray coupling phase. The mute option
  // never touches it.
  if (rec.gamma_pac) {
    const recipe::GammaPac& g = *rec.gamma_pac;
    p.gamma.present = true;
    p.gamma.increment = core::phase_increment(g.carrier_hz, sample_rate);
    p.gamma.envelope_increment = core::phase_increment(g.rate_hz, sample_rate);
    p.gamma.depth = g.am_depth_percent / 100.0;
    if (g.coupling == recipe::GammaCoupling::SmoothSwell) {
      p.gamma.coupled = true;
      p.gamma.coupling_phase_units = core::coupling_phase_units(*g.coupling_phase_deg);  // checked: present
    }
  }

  // Binaural layer: a pure sine per ear, the left ear at carrier_left_hz and
  // the right ear at f_C = carrier_left_hz + beat_rate_hz (range row
  // binaural-carrier-right), unit amplitude, phase 0; with a beat rate cycle
  // the right phase adds the closed-form offset U (Rate curve, Engine).
  // check_rules() has rejected a non-sine waveform.
  if (rec.binaural) {
    const recipe::Binaural& b = *rec.binaural;
    const double f_left = b.carrier_left_hz;
    const double f_center = b.carrier_left_hz + b.beat_rate_hz;
    p.binaural.increment = {core::phase_increment(f_left, sample_rate),
                            core::phase_increment(f_center, sample_rate)};
    p.binaural.amplitude = {1.0, 1.0};
    if (b.beat_rate_cycle) {
      const recipe::BeatRateCycle& cycle = *b.beat_rate_cycle;
      p.binaural.cycle = true;
      p.binaural.cycle_start = core::coupling_phase_units(cycle.start_phase_deg);
      p.binaural.cycle_increment = core::phase_increment(1.0 / cycle.period_s, sample_rate);
      p.binaural.cycle_k = (cycle.swing_hz * cycle.period_s) * core::kInvTwoPi;
      p.binaural.cycle_c0 = core::cycle_cosine(p.binaural.cycle_start);  // the per-sample function
    }
  }
  if (mute != MuteEar::None) {
    const std::size_t c = mute == MuteEar::Left ? 0 : 1;
    p.binaural.increment[c] = 0;
    p.binaural.amplitude[c] = 0.0;
    if (c == 1) {
      // A muted right ear has no cycle, so it outputs 0.0 * sine(0) = +0.0.
      p.binaural.cycle = false;
      p.binaural.cycle_start = 0;
      p.binaural.cycle_increment = 0;
      p.binaural.cycle_k = 0.0;
      p.binaural.cycle_c0 = 0.0;
    }
  }

  CompileResult r;
  r.plan = std::move(p);
  return r;
}

}  // namespace arcani::plan
