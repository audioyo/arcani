// Must-fail fixture for the engine symbol check, fenv family (Story 1.2).
//
// Never part of a normal build. It is compiled into arcani_engine only when
// the test-only cache variable ARCANI_ENGINE_TEST_EXTRA_SOURCE points at it
// (tests/cmake/test_engine_symbols.py), so the built library has an undefined
// reference to fesetenv and tools/check_engine_symbols.py must fail. The
// engine sets its floating-point mode with MXCSR / FPCR intrinsics only (AD-9).
//
// The environment comes from the caller, so the call cannot be folded.
#include <cfenv>

extern "C" int arc_test_calls_fesetenv(const std::fenv_t* env);

extern "C" int arc_test_calls_fesetenv(const std::fenv_t* env) {
    return std::fesetenv(env);
}
