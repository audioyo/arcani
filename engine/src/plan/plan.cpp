// Plan compile and the fixed stage list.

#include "plan/plan.hpp"

#include <string>
#include <utility>

#include "core/phase.hpp"

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
  for (std::size_t i = 0; i < p.stages.size(); ++i) {
    p.stages[i] = kStages[i].kind;
  }

  // Binaural join stub: an unmodulated sine per ear, the left ear at
  // carrier_left_hz and the right ear at carrier_left_hz + beat_rate_hz
  // (range row binaural-carrier-right), unit amplitude, phase 0.
  if (rec.binaural) {
    const double f_left = rec.binaural->carrier_left_hz;
    const double f_right = rec.binaural->carrier_left_hz + rec.binaural->beat_rate_hz;
    p.binaural.increment = {core::phase_increment(f_left, sample_rate),
                            core::phase_increment(f_right, sample_rate)};
    p.binaural.amplitude = {1.0, 1.0};
  }
  if (mute != MuteEar::None) {
    const std::size_t c = mute == MuteEar::Left ? 0 : 1;
    p.binaural.increment[c] = 0;
    p.binaural.amplitude[c] = 0.0;
  }

  CompileResult r;
  r.plan = std::move(p);
  return r;
}

}  // namespace arcani::plan
