// Must-fail fixture for the engine symbol check (Story 0.1 part 2).
//
// Never part of a normal build. It is compiled into arcani_engine only when
// the test-only cache variable ARCANI_ENGINE_TEST_EXTRA_SOURCE points at it
// (tests/cmake/test_engine_symbols.py), so the built library has an undefined
// reference to the libm sin and tools/check_engine_symbols.py must fail.
//
// The argument is not a compile-time constant, so the call cannot be folded.
#include <cmath>

extern "C" double arc_test_calls_std_sin(double x);

extern "C" double arc_test_calls_std_sin(double x) {
    return std::sin(x);
}
