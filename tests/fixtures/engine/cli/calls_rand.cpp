// Must-fail fixture for the WAV writer symbol check, family randomness
// (Story 1.6).
//
// Never part of a normal build. It is compiled into arcani_cli_core (the WAV
// writer and report library, cli/wav.cpp and cli/report.cpp) only when the
// test-only cache variable ARCANI_CLI_TEST_EXTRA_SOURCE points at it
// (tests/cmake/test_engine_symbols.py), so the built library has an undefined
// reference to rand and tools/check_engine_symbols.py must fail.
//
// The call is in a function the caller can reach, so it is not removed.
#include <cstdlib>

extern "C" int arc_test_cli_calls_rand(void);

extern "C" int arc_test_cli_calls_rand(void) {
    return std::rand();
}
