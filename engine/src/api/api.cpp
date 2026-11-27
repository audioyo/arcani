// The C API boundary (Story 1.2): argument checks, error struct filling,
// exception catch, plan reference counts, and the denormal guard on every
// floating-point call. No exception crosses this boundary. Error filling
// never allocates, so render and seek error returns keep the real-time
// contract.

#include <arcani/arcani.h>

#include <atomic>
#include <charconv>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <new>
#include <string_view>
#include <utility>

#include "core/fp_mode.hpp"
#include "plan/plan.hpp"
#include "recipe/recipe.hpp"
#include "render/renderer.hpp"

struct arc_plan {
  explicit arc_plan(arcani::plan::Plan p) : plan(std::move(p)) {}
  arcani::plan::Plan plan;
  std::atomic<std::size_t> references{1};
};

struct arc_renderer {
  explicit arc_renderer(arc_plan* p) noexcept : plan(p), renderer(p->plan) {}
  arc_plan* plan;  // one reference, released by arc_renderer_destroy
  arcani::render::Renderer renderer;
};

namespace {

using arcani::core::FpModeGuard;

static_assert(sizeof(arc_mode) == sizeof(int) && sizeof(arc_mute_ear) == sizeof(int) && sizeof(arc_ear) == sizeof(int),
              "the options enums are read as int");
static_assert(static_cast<int>(arcani::plan::StageKind::ThetaReference) == ARC_STAGE_THETA_REFERENCE &&
              static_cast<int>(arcani::plan::StageKind::GammaPac) == ARC_STAGE_GAMMA_PAC &&
              static_cast<int>(arcani::plan::StageKind::StereoBus) == ARC_STAGE_STEREO_BUS &&
              static_cast<int>(arcani::plan::StageKind::BinauralJoin) == ARC_STAGE_BINAURAL_JOIN &&
              static_cast<int>(arcani::plan::StageKind::MasterChain) == ARC_STAGE_MASTER_CHAIN,
              "StageKind values equal arc_stage_kind");

// Copies text into one error field, NUL-terminated. A longer text is cut to at most
// the field size less 1 byte, ending in "...", never inside a UTF-8 sequence.
template <std::size_t N>
void write_field(char (&dest)[N], std::string_view text) noexcept {
  constexpr std::size_t kMax = N - 1;
  if (text.size() <= kMax) {
    std::memcpy(dest, text.data(), text.size());
    dest[text.size()] = '\0';
    return;
  }
  constexpr std::string_view kEllipsis = "...";
  // Never split a UTF-8 sequence: back up off continuation bytes.
  std::size_t keep = kMax - kEllipsis.size();
  while (keep > 0 && (static_cast<unsigned char>(text[keep]) & 0xC0u) == 0x80u) {
    --keep;
  }
  std::memcpy(dest, text.data(), keep);
  std::memcpy(dest + keep, kEllipsis.data(), kEllipsis.size());
  dest[keep + kEllipsis.size()] = '\0';
}

void fill(arc_error* e, std::string_view parameter, std::string_view value, std::string_view rule,
          std::string_view limit, std::string_view detail = {}) noexcept {
  if (e == nullptr) {
    return;
  }
  write_field(e->parameter, parameter);
  write_field(e->value, value);
  write_field(e->rule, rule);
  write_field(e->limit, limit);
  write_field(e->detail, detail);
}

void fill(arc_error* e, const arcani::recipe::Error& from) noexcept {
  fill(e, from.parameter, from.value, from.rule, from.limit, from.detail);
}

// Decimal text of an unsigned integer, without allocation.
struct Decimal {
  explicit Decimal(std::uint64_t v) noexcept {
    const auto r = std::to_chars(buffer, buffer + sizeof buffer, v);
    length = static_cast<std::size_t>(r.ptr - buffer);
  }
  explicit Decimal(int v) noexcept {
    const auto r = std::to_chars(buffer, buffer + sizeof buffer, v);
    length = static_cast<std::size_t>(r.ptr - buffer);
  }
  std::string_view view() const noexcept { return {buffer, length}; }
  char buffer[24] = {};
  std::size_t length = 0;
};

arc_status null_argument(arc_error* e, std::string_view name) noexcept {
  fill(e, name, "null", "argument.null", "non-null");
  return ARC_ERR_INVALID_ARGUMENT;
}

arc_status bad_index(arc_error* e, std::size_t index, std::size_t count) noexcept {
  fill(e, "index", Decimal(static_cast<std::uint64_t>(index)).view(), "argument.index",
       Decimal(static_cast<std::uint64_t>(count)).view());
  return ARC_ERR_INVALID_ARGUMENT;
}

arc_status bad_enum(arc_error* e, std::string_view name, int value, std::string_view allowed) noexcept {
  fill(e, name, Decimal(value).view(), "argument.enum", allowed);
  return ARC_ERR_INVALID_ARGUMENT;
}

arc_status out_of_memory(arc_error* e) noexcept {
  fill(e, "", "", "memory", "allocation succeeds");
  return ARC_ERR_OUT_OF_MEMORY;
}

arc_status internal(arc_error* e) noexcept {
  fill(e, "", "", "internal", "no internal fault");
  return ARC_ERR_INTERNAL;
}

}  // namespace

extern "C" {

arc_status arc_compile(const char* utf8, size_t length, const arc_compile_options* options,
                       arc_plan** out_plan, arc_error* error) {
  const FpModeGuard guard;
  if (out_plan != nullptr) {
    *out_plan = nullptr;
  }
  if (utf8 == nullptr) {
    return null_argument(error, "utf8");
  }
  if (options == nullptr) {
    return null_argument(error, "options");
  }
  if (out_plan == nullptr) {
    return null_argument(error, "out_plan");
  }
  int mode_value = 0;
  int mute_value = 0;
  std::memcpy(&mode_value, &options->mode, sizeof mode_value);
  std::memcpy(&mute_value, &options->mute_binaural_ear, sizeof mute_value);
  if (mode_value != ARC_MODE_MEASURE && mode_value != ARC_MODE_FINAL) {
    return bad_enum(error, "mode", mode_value, "0 (measure) 1 (final)");
  }
  if (mute_value != ARC_MUTE_NONE && mute_value != ARC_MUTE_LEFT && mute_value != ARC_MUTE_RIGHT) {
    return bad_enum(error, "mute_binaural_ear", mute_value, "0 (none) 1 (left) 2 (right)");
  }
  const auto mode = mode_value == ARC_MODE_FINAL ? arcani::plan::Mode::Final : arcani::plan::Mode::Measure;
  const auto mute = mute_value == ARC_MUTE_LEFT    ? arcani::plan::MuteEar::Left
                    : mute_value == ARC_MUTE_RIGHT ? arcani::plan::MuteEar::Right
                                                   : arcani::plan::MuteEar::None;
  try {
    arcani::plan::CompileResult r =
        arcani::plan::compile(std::string_view(utf8, length), mode, options->sample_rate, mute);
    if (!r.plan) {
      fill(error, r.error);
      return ARC_ERR_REJECTED;
    }
    *out_plan = new arc_plan(std::move(*r.plan));
    return ARC_OK;
  } catch (const std::bad_alloc&) {
    return out_of_memory(error);
  } catch (...) {
    return internal(error);
  }
}

void arc_plan_retain(arc_plan* plan) {
  if (plan != nullptr) {
    plan->references.fetch_add(1, std::memory_order_relaxed);
  }
}

void arc_plan_release(arc_plan* plan) {
  if (plan != nullptr && plan->references.fetch_sub(1, std::memory_order_acq_rel) == 1) {
    delete plan;
  }
}

uint64_t arc_plan_frame_count(const arc_plan* plan) {
  return plan == nullptr ? 0 : plan->plan.frame_count;
}

const char* arc_plan_recipe_hash(const arc_plan* plan) {
  return plan == nullptr ? "" : plan->plan.recipe_hash.c_str();
}

uint64_t arc_plan_seed(const arc_plan* plan) {
  return plan == nullptr ? 0 : plan->plan.seed;
}

size_t arc_plan_stage_count(const arc_plan* plan) {
  return plan == nullptr ? 0 : plan->plan.stages.size();
}

arc_status arc_plan_stage(const arc_plan* plan, size_t index, arc_stage_kind* out_kind, arc_error* error) {
  if (plan == nullptr) {
    return null_argument(error, "plan");
  }
  if (out_kind == nullptr) {
    return null_argument(error, "out_kind");
  }
  const auto& stages = plan->plan.stages;
  if (index >= stages.size()) {
    return bad_index(error, index, stages.size());
  }
  *out_kind = static_cast<arc_stage_kind>(static_cast<int>(stages[index]));
  return ARC_OK;
}

arc_status arc_plan_loop(const arc_plan* plan, arc_loop_frames* out_loop, arc_error* error) {
  if (plan == nullptr) {
    return null_argument(error, "plan");
  }
  if (out_loop == nullptr) {
    return null_argument(error, "out_loop");
  }
  const arcani::plan::LoopFrames& loop = plan->plan.loop;
  std::memset(out_loop, 0, sizeof *out_loop);
  if (loop.present) {
    out_loop->looping = 1;
    out_loop->opening_end_frame = loop.opening_end_frame;
    out_loop->body_frames = loop.body_frames;
    out_loop->seam_count = loop.seam_count;
    out_loop->end_frame = plan->plan.frame_count;
  }
  return ARC_OK;
}

size_t arc_plan_gain_ramp_count(const arc_plan* plan) {
  if (plan == nullptr) {
    return 0;
  }
  const arcani::plan::Plan& p = plan->plan;
  return p.theta_gain.count + p.gamma_gain.count + p.binaural_gain.count + p.master_ramp.count;
}

arc_status arc_plan_gain_ramp(const arc_plan* plan, size_t index, arc_gain_ramp* out_ramp, arc_error* error) {
  if (plan == nullptr) {
    return null_argument(error, "plan");
  }
  if (out_ramp == nullptr) {
    return null_argument(error, "out_ramp");
  }
  const arcani::plan::Plan& p = plan->plan;
  const arcani::plan::GainSchedule* schedules[] = {&p.theta_gain, &p.gamma_gain, &p.binaural_gain, &p.master_ramp};
  const std::size_t count = arc_plan_gain_ramp_count(plan);
  if (index >= count) {
    return bad_index(error, index, count);
  }
  std::size_t at = index;
  for (int s = 0; s < 4; ++s) {
    if (at < schedules[s]->count) {
      const arcani::plan::GainRamp& r = schedules[s]->ramps[at];
      std::memset(out_ramp, 0, sizeof *out_ramp);
      out_ramp->target = static_cast<arc_gain_target>(s);
      out_ramp->start_frame = r.start_frame;
      out_ramp->end_frame = r.end_frame;
      out_ramp->from = r.from;
      out_ramp->to = r.to;
      return ARC_OK;
    }
    at -= schedules[s]->count;
  }
  return bad_index(error, index, count);  // not reached
}

arc_status arc_plan_loudness_hash(const arc_plan* plan, char out_hash[65], arc_error* error) {
  if (plan == nullptr) {
    return null_argument(error, "plan");
  }
  if (out_hash == nullptr) {
    return null_argument(error, "out_hash");
  }
  const std::string& h = plan->plan.loudness_hash;  // 64 lowercase hex digits
  std::memcpy(out_hash, h.data(), 64);
  out_hash[64] = '\0';
  return ARC_OK;
}

size_t arc_plan_component_count(const arc_plan* plan) {
  return plan == nullptr ? 0 : plan->plan.components.size();
}

arc_status arc_plan_component(const arc_plan* plan, size_t index, arc_component* out_component,
                              arc_error* error) {
  if (plan == nullptr) {
    return null_argument(error, "plan");
  }
  if (out_component == nullptr) {
    return null_argument(error, "out_component");
  }
  const auto& rows = plan->plan.components;
  if (index >= rows.size()) {
    return bad_index(error, index, rows.size());
  }
  const arcani::validate::Component& c = rows[index];
  std::memset(out_component, 0, sizeof *out_component);
  out_component->layer = static_cast<arc_component_layer>(static_cast<int>(c.layer));
  out_component->ear = static_cast<arc_ear>(static_cast<int>(c.ear));
  out_component->center_hz = c.center_hz;
  out_component->low_hz = c.low_hz;
  out_component->high_hz = c.high_hz;
  out_component->level = c.level;
  out_component->gamma_mult = c.gamma_mult;
  out_component->theta_mult = c.theta_mult;
  out_component->beat_mult = c.beat_mult;
  return ARC_OK;
}

arc_status arc_plan_spacing(const arc_plan* plan, arc_ear ear, arc_spacing* out_spacing, arc_error* error) {
  if (plan == nullptr) {
    return null_argument(error, "plan");
  }
  if (out_spacing == nullptr) {
    return null_argument(error, "out_spacing");
  }
  int ear_value = 0;
  std::memcpy(&ear_value, &ear, sizeof ear_value);
  if (ear_value != ARC_EAR_LEFT && ear_value != ARC_EAR_RIGHT) {
    return bad_enum(error, "ear", ear_value, "0 (left) 1 (right)");
  }
  std::memset(out_spacing, 0, sizeof *out_spacing);
  const auto& worst = plan->plan.spacing[static_cast<std::size_t>(ear_value)];
  if (worst) {
    out_spacing->has_pair = 1;
    out_spacing->min_distance_hz = worst->min_distance_hz;
    out_spacing->margin_hz = worst->margin_hz;
    out_spacing->component_1 = worst->component_1;
    out_spacing->component_2 = worst->component_2;
  }
  return ARC_OK;
}

size_t arc_plan_warning_count(const arc_plan* plan) {
  return plan == nullptr ? 0 : plan->plan.warnings.size();
}

arc_status arc_plan_warning(const arc_plan* plan, size_t index, arc_error* out_warning, arc_error* error) {
  if (plan == nullptr) {
    return null_argument(error, "plan");
  }
  if (out_warning == nullptr) {
    return null_argument(error, "out_warning");
  }
  const auto& warnings = plan->plan.warnings;
  if (index >= warnings.size()) {
    return bad_index(error, index, warnings.size());
  }
  fill(out_warning, warnings[index]);
  return ARC_OK;
}

arc_status arc_renderer_create(arc_plan* plan, arc_renderer** out_renderer, arc_error* error) {
  const FpModeGuard guard;
  if (out_renderer != nullptr) {
    *out_renderer = nullptr;
  }
  if (plan == nullptr) {
    return null_argument(error, "plan");
  }
  if (out_renderer == nullptr) {
    return null_argument(error, "out_renderer");
  }
  arc_renderer* r = new (std::nothrow) arc_renderer(plan);
  if (r == nullptr) {
    return out_of_memory(error);
  }
  arc_plan_retain(plan);
  *out_renderer = r;
  return ARC_OK;
}

arc_status arc_render(arc_renderer* renderer, double* out, size_t frames, const arc_taps* taps,
                      arc_error* error) {
  const FpModeGuard guard;
  if (renderer == nullptr) {
    return null_argument(error, "renderer");
  }
  if (out == nullptr) {
    return null_argument(error, "out");
  }
  arcani::render::Taps t;
  if (taps != nullptr) {
    t.theta_reference = taps->theta_reference;
    t.gamma_pac = taps->gamma_pac;
    t.stereo_bus = taps->stereo_bus;
    t.binaural_join = taps->binaural_join;
    t.master = taps->master;
    t.theta_reference_gained = taps->theta_reference_gained;
    t.gamma_pac_gained = taps->gamma_pac_gained;
    t.binaural = taps->binaural;
    t.binaural_gained = taps->binaural_gained;
  }
  renderer->renderer.render(out, frames, t);
  return ARC_OK;
}

arc_status arc_seek(arc_renderer* renderer, uint64_t frame, arc_error* error) {
  const FpModeGuard guard;
  if (renderer == nullptr) {
    return null_argument(error, "renderer");
  }
  renderer->renderer.seek(frame);
  return ARC_OK;
}

void arc_renderer_destroy(arc_renderer* renderer) {
  if (renderer != nullptr) {
    arc_plan* plan = renderer->plan;
    delete renderer;
    arc_plan_release(plan);
  }
}

}  // extern "C"
