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

static_assert(sizeof(arc_mode) == sizeof(int) && sizeof(arc_mute_ear) == sizeof(int),
              "the options enums are read as int");
static_assert(static_cast<int>(arcani::plan::StageKind::ThetaReference) == ARC_STAGE_THETA_REFERENCE &&
              static_cast<int>(arcani::plan::StageKind::GammaPac) == ARC_STAGE_GAMMA_PAC &&
              static_cast<int>(arcani::plan::StageKind::StereoBus) == ARC_STAGE_STEREO_BUS &&
              static_cast<int>(arcani::plan::StageKind::BinauralJoin) == ARC_STAGE_BINAURAL_JOIN &&
              static_cast<int>(arcani::plan::StageKind::MasterChain) == ARC_STAGE_MASTER_CHAIN,
              "StageKind values equal arc_stage_kind");

// Copies text into one error field, NUL-terminated. A longer text is cut to at most
// ARC_ERROR_FIELD_BYTES - 1 bytes ending in "...", never inside a UTF-8 sequence.
void write_field(char (&dest)[ARC_ERROR_FIELD_BYTES], std::string_view text) noexcept {
  constexpr std::size_t kMax = ARC_ERROR_FIELD_BYTES - 1;
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
          std::string_view limit) noexcept {
  if (e == nullptr) {
    return;
  }
  write_field(e->parameter, parameter);
  write_field(e->value, value);
  write_field(e->rule, rule);
  write_field(e->limit, limit);
}

void fill(arc_error* e, const arcani::recipe::Error& from) noexcept {
  fill(e, from.parameter, from.value, from.rule, from.limit);
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
