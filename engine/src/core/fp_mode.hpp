// Denormal guard (Story 1.2, AD-9).
//
// A host (an audio app) often runs with flush-to-zero set. Every
// floating-point C API call opens one FpModeGuard on entry: it saves the
// host's mode and clears the flush bits, so the engine computes in IEEE mode
// with denormals kept, and its destructor restores the saved mode exactly on
// every return, error returns included.
//
// x86-64: MXCSR through _mm_getcsr / _mm_setcsr; FTZ is bit 15 and DAZ is
// bit 6. AArch64: FPCR through the clang system-register builtins; FZ is bit
// 24. Intrinsics only: no fesetenv family and no FENV_ACCESS pragma
// (tools/engine_symbol_denylist.json family "fenv",
// tools/check_fp_pragmas.py). Other targets have no mode control and the guard
// does nothing.

#ifndef ARCANI_CORE_FP_MODE_HPP
#define ARCANI_CORE_FP_MODE_HPP

#include <cstdint>

#if defined(__x86_64__) || defined(_M_X64)
#include <immintrin.h>
#define ARCANI_FP_MODE_X86 1
#elif defined(__aarch64__) || defined(_M_ARM64)
#define ARCANI_FP_MODE_ARM64 1
#endif

namespace arcani::core {

class FpModeGuard {
 public:
  FpModeGuard() noexcept {
#if defined(ARCANI_FP_MODE_X86)
    saved_ = _mm_getcsr();
    _mm_setcsr(saved_ & ~kFlushBits);
#elif defined(ARCANI_FP_MODE_ARM64)
    saved_ = __builtin_arm_rsr64("fpcr");
    __builtin_arm_wsr64("fpcr", saved_ & ~kFlushBits);
#endif
  }

  ~FpModeGuard() {
#if defined(ARCANI_FP_MODE_X86)
    _mm_setcsr(saved_);
#elif defined(ARCANI_FP_MODE_ARM64)
    __builtin_arm_wsr64("fpcr", saved_);
#endif
  }

  FpModeGuard(const FpModeGuard&) = delete;
  FpModeGuard& operator=(const FpModeGuard&) = delete;

 private:
#if defined(ARCANI_FP_MODE_X86)
  static constexpr unsigned int kFlushBits = 0x8000u | 0x0040u;  // FTZ | DAZ
  unsigned int saved_ = 0;
#elif defined(ARCANI_FP_MODE_ARM64)
  static constexpr std::uint64_t kFlushBits = std::uint64_t{1} << 24;  // FZ
  std::uint64_t saved_ = 0;
#endif
};

}  // namespace arcani::core

#endif  // ARCANI_CORE_FP_MODE_HPP
