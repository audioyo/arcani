// Floating-point mode guard (Story 1.2, AD-9).
//
// A host (an audio app) may run with flush-to-zero, another rounding mode,
// or unmasked exceptions. Every floating-point C API call opens one
// FpModeGuard on entry: it saves the host's mode and sets one fixed IEEE mode
// (round to nearest, no flush, exceptions masked), so engine math is the
// same under every host. Its destructor restores the saved mode exactly on
// every return, error returns included.
//
// x86-64: MXCSR = 0x1F80 through _mm_getcsr / _mm_setcsr (round to nearest,
// all six exceptions masked, FTZ and DAZ off). AArch64: FPCR through the
// clang system-register builtins, with FIZ (bit 0), AH (1), the trap enables
// (bits 8 to 12 and 15), FZ16 (19), RMode (22 and 23), FZ (24), and DN (25)
// cleared. Intrinsics only: no fesetenv family and no FENV_ACCESS pragma
// (tools/engine_symbol_denylist.json family "fenv",
// tools/check_fp_pragmas.py). Any other target fails to compile.

#ifndef ARCANI_CORE_FP_MODE_HPP
#define ARCANI_CORE_FP_MODE_HPP

#include <cstdint>

#if defined(__x86_64__) || defined(_M_X64)
#include <immintrin.h>
#define ARCANI_FP_MODE_X86 1
#elif defined(__aarch64__) || defined(_M_ARM64)
#define ARCANI_FP_MODE_ARM64 1
#else
#error "FpModeGuard: no floating-point mode control for this target (x86-64 and AArch64 only)"
#endif

namespace arcani::core {

class FpModeGuard {
 public:
  FpModeGuard() noexcept {
#if defined(ARCANI_FP_MODE_X86)
    saved_ = _mm_getcsr();
    _mm_setcsr(kEngineMxcsr);
#else
    saved_ = __builtin_arm_rsr64("fpcr");
    __builtin_arm_wsr64("fpcr", saved_ & ~kClearedFpcrBits);
#endif
  }

  ~FpModeGuard() {
#if defined(ARCANI_FP_MODE_X86)
    _mm_setcsr(saved_);
#else
    __builtin_arm_wsr64("fpcr", saved_);
#endif
  }

  FpModeGuard(const FpModeGuard&) = delete;
  FpModeGuard& operator=(const FpModeGuard&) = delete;

 private:
#if defined(ARCANI_FP_MODE_X86)
  // Round to nearest (RC = 0), all exceptions masked (bits 7 to 12), FTZ (15)
  // and DAZ (6) off, status flags clear.
  static constexpr unsigned int kEngineMxcsr = 0x1F80u;
  unsigned int saved_ = 0;
#else
  static constexpr std::uint64_t kClearedFpcrBits =
      (std::uint64_t{1} << 0) |                               // FIZ
      (std::uint64_t{1} << 1) |                               // AH
      (std::uint64_t{0x1F} << 8) | (std::uint64_t{1} << 15) |  // trap enables
      (std::uint64_t{1} << 19) |                              // FZ16
      (std::uint64_t{3} << 22) |                              // RMode
      (std::uint64_t{1} << 24) |                              // FZ
      (std::uint64_t{1} << 25);                               // DN
  std::uint64_t saved_ = 0;
#endif
};

}  // namespace arcani::core

#endif  // ARCANI_CORE_FP_MODE_HPP
