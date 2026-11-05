/* The public header compiles as C (Story 1.2). Not linked: ctest runs the
   pinned compiler in C mode, syntax only, warnings as errors
   (tests/cpp/CMakeLists.txt, test arcani_api_c_header). Every declared call
   and type is used with its exact C signature, so a C++-only construct or a
   drifted declaration in arcani/arcani.h fails this test. The must-fail twin
   is tests/fixtures/c_api/cpp_reference.c. */
#include <arcani/arcani.h>

#include <stddef.h>
#include <stdint.h>

typedef const char* (*version_fn)(void);
typedef arc_status (*compile_fn)(const char*, size_t, const arc_compile_options*, arc_plan**, arc_error*);
typedef void (*plan_fn)(arc_plan*);
typedef uint64_t (*frame_count_fn)(const arc_plan*);
typedef size_t (*count_fn)(const arc_plan*);
typedef arc_status (*stage_fn)(const arc_plan*, size_t, arc_stage_kind*, arc_error*);
typedef arc_status (*warning_fn)(const arc_plan*, size_t, arc_error*, arc_error*);
typedef arc_status (*create_fn)(arc_plan*, arc_renderer**, arc_error*);
typedef arc_status (*render_fn)(arc_renderer*, double*, size_t, const arc_taps*, arc_error*);
typedef arc_status (*seek_fn)(arc_renderer*, uint64_t, arc_error*);
typedef void (*destroy_fn)(arc_renderer*);

int arc_test_c_header(void);

int arc_test_c_header(void) {
  version_fn version = arc_engine_version;
  compile_fn compile = arc_compile;
  plan_fn retain = arc_plan_retain;
  plan_fn release = arc_plan_release;
  frame_count_fn frame_count = arc_plan_frame_count;
  count_fn stage_count = arc_plan_stage_count;
  stage_fn stage = arc_plan_stage;
  count_fn warning_count = arc_plan_warning_count;
  warning_fn warning = arc_plan_warning;
  create_fn create = arc_renderer_create;
  render_fn render = arc_render;
  seek_fn seek = arc_seek;
  destroy_fn destroy = arc_renderer_destroy;

  arc_error error;
  arc_compile_options options;
  arc_taps taps;
  arc_status status = ARC_OK;
  arc_mode mode = ARC_MODE_MEASURE;
  arc_mute_ear mute = ARC_MUTE_NONE;
  arc_stage_kind kind = ARC_STAGE_THETA_REFERENCE;
  int sum = 0;

  error.parameter[0] = '\0';
  error.value[ARC_ERROR_FIELD_BYTES - 1] = '\0';
  error.rule[0] = '\0';
  error.limit[0] = '\0';
  options.mode = ARC_MODE_FINAL;
  options.sample_rate = 48000u;
  options.mute_binaural_ear = ARC_MUTE_LEFT;
  taps.theta_reference = NULL;
  taps.gamma_pac = NULL;
  taps.stereo_bus = NULL;
  taps.binaural_join = NULL;
  taps.master = NULL;

  sum += (int)status + (int)mode + (int)mute + (int)kind;
  sum += ARC_ERR_INVALID_ARGUMENT + ARC_ERR_REJECTED + ARC_ERR_OUT_OF_MEMORY + ARC_ERR_INTERNAL;
  sum += ARC_MUTE_RIGHT + ARC_STAGE_GAMMA_PAC + ARC_STAGE_STEREO_BUS + ARC_STAGE_BINAURAL_JOIN +
         ARC_STAGE_MASTER_CHAIN;
  sum += (version != NULL) + (compile != NULL) + (retain != NULL) + (release != NULL) +
         (frame_count != NULL) + (stage_count != NULL) + (stage != NULL) + (warning_count != NULL) +
         (warning != NULL) + (create != NULL) + (render != NULL) + (seek != NULL) + (destroy != NULL);
  sum += (int)sizeof error + error.parameter[0] + (int)options.sample_rate + (taps.master == NULL);
  return sum;
}
