/* Arcani engine public C API. */
#ifndef ARCANI_ARCANI_H
#define ARCANI_ARCANI_H

#ifdef __cplusplus
extern "C" {
#endif

/* Engine version as a static, null-terminated string, for example "0.0.1".
   The pointer stays valid for the life of the program. */
const char* arc_engine_version(void);

#ifdef __cplusplus
}
#endif

#endif /* ARCANI_ARCANI_H */
