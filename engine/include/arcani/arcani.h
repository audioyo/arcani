/* Arcani engine public C API (Story 1.2).

   Plain C, no C++ construct, so a C host can include it. The engine compiles
   a JSON recipe into an immutable, reference-counted plan, and a renderer
   plays a plan as interleaved stereo binary64 frames.

   Errors: every call that can fail returns an arc_status and, when `error`
   is not NULL, writes all four arc_error fields (each NUL-terminated; a
   longer text is cut to ARC_ERROR_FIELD_BYTES - 1 bytes ending in "...").
   A successful call makes no promise about `error`.

   Real-time contract: arc_render and arc_seek never allocate, lock, block,
   do I/O, throw, or log. Every floating-point call (compile, renderer
   creation, render, seek) clears the denormal flush modes on entry and puts
   the host's floating-point mode back on every return. */
#ifndef ARCANI_ARCANI_H
#define ARCANI_ARCANI_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Size in bytes of each arc_error field, terminator included. */
#define ARC_ERROR_FIELD_BYTES 256

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
/* Stage count; 0 for NULL. */
size_t arc_plan_stage_count(const arc_plan* plan);
arc_status arc_plan_stage(const arc_plan* plan, size_t index, arc_stage_kind* out_kind,
                          arc_error* error);
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
