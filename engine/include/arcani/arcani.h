/* Arcani engine public C API (Story 1.2).

   Plain C, no C++ construct, so a C host can include it. The engine compiles
   a JSON recipe into an immutable, reference-counted plan, and a renderer
   plays a plan as interleaved stereo binary64 frames.

   Errors: every call that can fail returns an arc_status and, when `error`
   is not NULL, writes all five arc_error fields (each NUL-terminated; a
   longer text is cut to at most its size less 1 byte, ending in "...",
   never inside a UTF-8 sequence). The detail is empty for every rule but
   the spacing rule (Story 3.2).
   A successful call makes no promise about `error`.

   Real-time contract: arc_render and arc_seek never allocate, lock, block,
   do I/O, throw, or log. Every floating-point call (compile, renderer
   creation, render, seek) sets one fixed IEEE mode (round to nearest, no
   flush, exceptions masked) on entry and puts the host's floating-point mode
   back on every return.

   Threads and buffers: a plan may be shared by renderers on any threads, and
   arc_plan_retain and arc_plan_release are thread-safe. One renderer must be
   used by one thread at a time. In arc_render, `out` and the tap buffers
   must not overlap each other. */
#ifndef ARCANI_ARCANI_H
#define ARCANI_ARCANI_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Size in bytes of each arc_error field, terminator included. */
#define ARC_ERROR_FIELD_BYTES 256
/* Size in bytes of arc_error::detail, terminator included (Story 3.2). */
#define ARC_ERROR_DETAIL_BYTES 512

typedef enum arc_status {
  ARC_OK = 0,
  ARC_ERR_INVALID_ARGUMENT = 1, /* a null pointer, bad enum, or index */
  ARC_ERR_REJECTED = 2,         /* the recipe or an option is refused */
  ARC_ERR_OUT_OF_MEMORY = 3,
  ARC_ERR_INTERNAL = 4
} arc_status;

typedef enum arc_mode {
  ARC_MODE_MEASURE = 0, /* the stored loudness gain may be absent */
  ARC_MODE_FINAL = 1    /* loudness_gain_db and loudness_hash are required */
} arc_mode;

/* Offline measurement control for the binaural isolation test (FR-4): the
   muted ear's binaural oscillator has increment 0 and amplitude 0.0 in the
   plan. Not a recipe field. */
typedef enum arc_mute_ear {
  ARC_MUTE_NONE = 0,
  ARC_MUTE_LEFT = 1,
  ARC_MUTE_RIGHT = 2
} arc_mute_ear;

/* The fixed stage list, in order (docs/signal-spec.md, Stub chain). */
typedef enum arc_stage_kind {
  ARC_STAGE_THETA_REFERENCE = 0,
  ARC_STAGE_GAMMA_PAC = 1,
  ARC_STAGE_STEREO_BUS = 2,
  ARC_STAGE_BINAURAL_JOIN = 3,
  ARC_STAGE_MASTER_CHAIN = 4
} arc_stage_kind;

typedef struct arc_error {
  char parameter[ARC_ERROR_FIELD_BYTES]; /* JSON Pointer, argument name, or "" */
  char value[ARC_ERROR_FIELD_BYTES];     /* the offending value as text */
  char rule[ARC_ERROR_FIELD_BYTES];      /* the rule that refused it, never empty */
  char limit[ARC_ERROR_FIELD_BYTES];     /* what the rule allows */
  char detail[ARC_ERROR_DETAIL_BYTES];   /* the spacing rule's pair and where (Story 3.2); else "" */
} arc_error;

typedef struct arc_compile_options {
  arc_mode mode;
  uint32_t sample_rate; /* 44100 or 48000; any other rate is rejected */
  arc_mute_ear mute_binaural_ear;
} arc_compile_options;

/* Optional per-stage taps. Each is NULL (not wanted) or a buffer of
   2 * frames doubles, interleaved left, right, over the same frames as the
   render output. */
typedef struct arc_taps {
  double* theta_reference;
  double* gamma_pac;
  double* stereo_bus;
  double* binaural_join; /* the engine output point */
  double* master;        /* equals the render output */
} arc_taps;

typedef struct arc_plan arc_plan;         /* opaque, immutable, reference-counted */
typedef struct arc_renderer arc_renderer; /* opaque */

/* Engine version as a static, null-terminated string, for example "0.0.1".
   The pointer stays valid for the life of the program. */
const char* arc_engine_version(void);

/* Compiles `length` bytes of UTF-8 recipe JSON (at most 1048576) into a plan
   with one reference. On failure *out_plan is set to NULL. */
arc_status arc_compile(const char* utf8, size_t length, const arc_compile_options* options,
                       arc_plan** out_plan, arc_error* error);

void arc_plan_retain(arc_plan* plan);  /* NULL is a no-op */
void arc_plan_release(arc_plan* plan); /* NULL is a no-op; frees at zero */

/* Session length in frames; 0 for NULL. */
uint64_t arc_plan_frame_count(const arc_plan* plan);
/* Recipe hash, 64 lowercase hex digits, valid while the plan lives; "" for
   NULL. */
const char* arc_plan_recipe_hash(const arc_plan* plan);
/* Recipe seed; 0 for NULL. */
uint64_t arc_plan_seed(const arc_plan* plan);
/* Stage count; 0 for NULL. */
size_t arc_plan_stage_count(const arc_plan* plan);
arc_status arc_plan_stage(const arc_plan* plan, size_t index, arc_stage_kind* out_kind,
                          arc_error* error);
/* Loop frames of a looping recipe (docs/signal-spec.md, Loop; Story 2.7).
   The opening covers frames [0, opening_end_frame); seam k, for k = 1 to
   seam_count, is opening_end_frame + k * body_frames; the session ends at
   end_frame (arc_plan_frame_count). Without a loop field, looping is 0 and
   every other field is 0. */
typedef struct arc_loop_frames {
  int looping; /* 1 for a looping recipe, else 0 */
  uint64_t opening_end_frame;
  uint64_t body_frames;
  uint64_t seam_count;
  uint64_t end_frame;
} arc_loop_frames;

/* Fills *out_loop. ARC_ERR_INVALID_ARGUMENT for a NULL plan or out_loop. */
arc_status arc_plan_loop(const arc_plan* plan, arc_loop_frames* out_loop, arc_error* error);

/* Spectral component table (docs/signal-spec.md, Components; Story 3.1).
   Per ear (the left ear's rows first) and per layer (theta reference, gamma
   PAC layer, binaural), by ascending center_hz: every spectral line whose
   level is at least the threshold of row spectral-component-level re its
   layer's carrier line. The line's frequency at any moment is the layer's
   carrier plus gamma_mult times the gamma rate, theta_mult times the theta
   rate, and beat_mult times the beat rate, each following its rate cycle;
   [low_hz, high_hz] is the range it covers over a whole cycle (both equal
   center_hz without one). A line whose frequency lies below 0 Hz sounds at
   its absolute value and is listed mirrored (center_hz, low_hz, high_hz
   become -center_hz, -high_hz, -low_hz; an interval that crosses 0 is listed
   as |center_hz|, 0, and the larger end), while the multipliers keep
   describing the unmirrored frequency. The table is the same at every sample rate, and a
   muted ear has no binaural row. The renderer never reads it. */
typedef enum arc_component_layer {
  ARC_COMPONENT_THETA_REFERENCE = 0,
  ARC_COMPONENT_GAMMA_PAC = 1,
  ARC_COMPONENT_BINAURAL = 2
} arc_component_layer;

typedef enum arc_ear {
  ARC_EAR_LEFT = 0,
  ARC_EAR_RIGHT = 1
} arc_ear;

typedef struct arc_component {
  arc_component_layer layer;
  arc_ear ear;
  double center_hz;
  double low_hz;
  double high_hz;
  double level; /* line amplitude over the layer's carrier line, in (0, 1] */
  int32_t gamma_mult;
  int32_t theta_mult;
  int32_t beat_mult;
} arc_component;

/* Component count; 0 for NULL. */
size_t arc_plan_component_count(const arc_plan* plan);
/* Fills *out_component with row `index` of the table.
   ARC_ERR_INVALID_ARGUMENT for a NULL plan or out_component, or an index at
   or past the count. */
arc_status arc_plan_component(const arc_plan* plan, size_t index, arc_component* out_component,
                              arc_error* error);

/* Spacing rule margins (docs/signal-spec.md, Spacing, Margins; Story 3.2).
   Per ear, the pair of component rows of different layers with the
   smallest minimum distance over the whole session (ties to the smaller
   index of row 1, then of row 2). The result is the same at every sample
   rate and honors mute_binaural_ear. component_1 and component_2 are
   positions in the whole table (arc_plan_component), so they shift when
   mute_binaural_ear removes a binaural row: a muted left ear moves every
   right-ear index down by one. */
typedef struct arc_spacing {
  int32_t has_pair;       /* 0: fewer than two layers in this ear; every other field 0 */
  double min_distance_hz; /* the smallest minimum distance of any pair in this ear */
  double margin_hz;       /* min_distance_hz less the value of row spacing-rule */
  size_t component_1;     /* arc_plan_component index of the pair's row 1 (the smaller index) */
  size_t component_2;     /* and of row 2 */
} arc_spacing;

/* Fills *out_spacing with the worst pair of one ear. ARC_ERR_INVALID_ARGUMENT
   for a NULL plan or out_spacing, or an ear other than ARC_EAR_LEFT and
   ARC_EAR_RIGHT. */
arc_status arc_plan_spacing(const arc_plan* plan, arc_ear ear, arc_spacing* out_spacing, arc_error* error);

/* Non-blocking warning count; 0 for NULL. A warning is an arc_error. */
size_t arc_plan_warning_count(const arc_plan* plan);
arc_status arc_plan_warning(const arc_plan* plan, size_t index, arc_error* out_warning,
                            arc_error* error);

/* Creates a renderer at frame 0. It holds its own plan reference. Every
   allocation happens here. On failure *out_renderer is set to NULL. */
arc_status arc_renderer_create(arc_plan* plan, arc_renderer** out_renderer, arc_error* error);

/* Renders `frames` frames into `out` (2 * frames doubles, interleaved left,
   right) and into each non-NULL tap; `taps` may be NULL. Past the session end
   every sample is +0.0. */
arc_status arc_render(arc_renderer* renderer, double* out, size_t frames, const arc_taps* taps,
                      arc_error* error);

/* Sets the next rendered frame to `frame`; any frame is allowed. Pure. */
arc_status arc_seek(arc_renderer* renderer, uint64_t frame, arc_error* error);

void arc_renderer_destroy(arc_renderer* renderer); /* NULL is a no-op */

#ifdef __cplusplus
}
#endif

#endif /* ARCANI_ARCANI_H */
