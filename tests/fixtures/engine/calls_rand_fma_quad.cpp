// Must-fail fixture for the engine symbol check, families randomness, fused
// multiply-add, and quad precision (Story 1.6).
//
// Never part of a normal build. It is compiled into arcani_engine only when
// the test-only cache variable ARCANI_ENGINE_TEST_EXTRA_SOURCE points at it
// (tests/cmake/test_engine_symbols.py), so the built library has undefined
// references to rand, a std::random_device library function, and fma, and
// tools/check_engine_symbols.py must fail.
//
// Every argument comes from the caller, so no call can be folded. x86-64
// builds have no -mfma, so std::fma stays a call to the libm fma.
//
// The quad-precision part is compiled only where the compiler defines
// __SIZEOF_FLOAT128__. There, __float128 arithmetic becomes calls to the
// compiler-rt helpers (__multf3, __addtf3, __extenddftf2, __trunctfdf2), and
// the defined marker arc_test_float128_present tells the test to expect a
// quad precision line.
#include <cmath>
#include <cstdlib>
#include <random>

extern "C" int arc_test_calls_rand(void);
extern "C" unsigned int arc_test_calls_random_device(void);
extern "C" double arc_test_calls_std_fma(double a, double b, double c);

extern "C" int arc_test_calls_rand(void) {
    return std::rand();
}

extern "C" unsigned int arc_test_calls_random_device(void) {
    std::random_device device;
    return device();
}

extern "C" double arc_test_calls_std_fma(double a, double b, double c) {
    return std::fma(a, b, c);
}

#if defined(__SIZEOF_FLOAT128__)
extern "C" int arc_test_float128_present(void);
extern "C" double arc_test_float128_arith(double a, double b, double c);

extern "C" int arc_test_float128_present(void) {
    return 1;
}

extern "C" double arc_test_float128_arith(double a, double b, double c) {
    const __float128 qa = a;
    const __float128 qb = b;
    const __float128 qc = c;
    return static_cast<double>(qa * qb + qc);
}
#endif
