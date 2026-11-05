// Host floating-point mode for the denormal-guard tests (Story 1.2). Test
// code only. A host (an audio app) often runs with flush-to-zero set; the
// engine must clear it on entry to every floating-point C API call and put the
// host's mode back on every return.
//
// x86-64: MXCSR through _mm_getcsr / _mm_setcsr; FTZ is bit 15 (0x8000), DAZ
// is bit 6 (0x0040). AArch64: FPCR through the clang system-register
// builtins; FZ is bit 24 (flushes inputs and outputs). Other targets have no
// support and the calling tests skip.

#pragma once

#include <cstdint>

#if defined(__x86_64__) || defined(_M_X64)
#include <immintrin.h>
#define ARCANI_TEST_FP_X86 1
#elif defined(__aarch64__) || defined(_M_ARM64)
#define ARCANI_TEST_FP_ARM64 1
#endif

namespace arcani::test::fp {

inline bool supported() {
#if defined(ARCANI_TEST_FP_X86) || defined(ARCANI_TEST_FP_ARM64)
  return true;
#else
  return false;
#endif
}

inline std::uint64_t get() {
#if defined(ARCANI_TEST_FP_X86)
  return _mm_getcsr();
#elif defined(ARCANI_TEST_FP_ARM64)
  return __builtin_arm_rsr64("fpcr");
#else
  return 0;
#endif
}

inline void set(std::uint64_t mode) {
#if defined(ARCANI_TEST_FP_X86)
  _mm_setcsr(static_cast<unsigned int>(mode));
#elif defined(ARCANI_TEST_FP_ARM64)
  __builtin_arm_wsr64("fpcr", mode);
#else
  (void)mode;
#endif
}

// The flush bits: FTZ and DAZ on x86-64, FZ on AArch64.
inline std::uint64_t flush_bits() {
#if defined(ARCANI_TEST_FP_X86)
  return 0x8000u | 0x0040u;
#elif defined(ARCANI_TEST_FP_ARM64)
  return std::uint64_t{1} << 24;
#else
  return 0;
#endif
}

// The control bits of the mode. On x86-64 the low six MXCSR bits are sticky
// exception status flags that any arithmetic may set (an underflow sets UE),
// so mode comparisons leave them out. AArch64 keeps its status flags in FPSR,
// not FPCR, so every FPCR bit is compared.
inline std::uint64_t control_mask() {
#if defined(ARCANI_TEST_FP_X86)
  return ~std::uint64_t{0x3F};
#else
  return ~std::uint64_t{0};
#endif
}

// The host's current control bits.
inline std::uint64_t controls() { return get() & control_mask(); }

// Smallest normal binary64 times one half: 0x1p-1023, a denormal, unless the
// mode flushes it to zero. volatile keeps the compiler from folding it.
inline double half_of_smallest_normal() {
  volatile double tiny = 0x1p-1022;
  volatile double half = 0.5;
  volatile double r = tiny * half;
  return r;
}

// Sets the host mode for a scope and restores the mode found on entry.
class HostMode {
 public:
  explicit HostMode(std::uint64_t mode) : saved_(get()) { set(mode); }
  ~HostMode() { set(saved_); }
  HostMode(const HostMode&) = delete;
  HostMode& operator=(const HostMode&) = delete;

 private:
  std::uint64_t saved_;
};

}  // namespace arcani::test::fp
