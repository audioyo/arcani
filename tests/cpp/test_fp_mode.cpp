// Engine denormal guard (Story 1.2, AD-9). One of the two internal-header
// tests this story allows (the other is the stage descriptor table). The host
// floating-point mode tests through the public C API are in test_api.cpp.
//
// Expected interface, engine/src/core/fp_mode.hpp, namespace arcani::core:
//
//   class FpModeGuard {
//    public:
//     FpModeGuard() noexcept;   // saves the host mode, then clears FTZ and DAZ
//                               // (MXCSR, x86-64) or FZ (FPCR, AArch64)
//     ~FpModeGuard();           // restores the saved mode exactly
//     FpModeGuard(const FpModeGuard&) = delete;
//     FpModeGuard& operator=(const FpModeGuard&) = delete;
//   };
//
// Intrinsics only (_mm_getcsr / _mm_setcsr, clang FPCR builtins): no
// fesetenv family, no FENV_ACCESS pragma (tools/engine_symbol_denylist.json
// family "fenv", tools/check_fp_pragmas.py).

#include <catch2/catch_test_macros.hpp>

#include "host_fp_mode.hpp"

namespace fp = arcani::test::fp;

#if __has_include("core/fp_mode.hpp")

#include "core/fp_mode.hpp"

#include <type_traits>

TEST_CASE("denormal guard: a denormal survives inside the guard while the host flushes", "[fp_mode][internal]") {
  STATIC_REQUIRE_FALSE(std::is_copy_constructible_v<arcani::core::FpModeGuard>);
  STATIC_REQUIRE_FALSE(std::is_copy_assignable_v<arcani::core::FpModeGuard>);
  if (!fp::supported()) {
    SKIP("no floating-point mode control on this target");
  }
  const std::uint64_t flushed = fp::controls() | fp::flush_bits();
  fp::HostMode host(flushed);
  REQUIRE(fp::controls() == flushed);
  // Premise (must-fail side): with the host's flush mode the denormal is lost.
  CHECK(fp::half_of_smallest_normal() == 0.0);
  {
    arcani::core::FpModeGuard guard;
    CHECK((fp::get() & fp::flush_bits()) == 0);
    CHECK(fp::half_of_smallest_normal() == 0x1p-1023);
  }
  CHECK(fp::controls() == flushed);
  CHECK(fp::half_of_smallest_normal() == 0.0);
}

TEST_CASE("denormal guard: restores an IEEE host mode and nests", "[fp_mode][internal]") {
  if (!fp::supported()) {
    SKIP("no floating-point mode control on this target");
  }
  const std::uint64_t ieee = fp::controls() & ~fp::flush_bits();
  fp::HostMode host(ieee);
  {
    arcani::core::FpModeGuard outer;
    {
      arcani::core::FpModeGuard inner;
      CHECK(fp::half_of_smallest_normal() == 0x1p-1023);
    }
    CHECK((fp::get() & fp::flush_bits()) == 0);
  }
  CHECK(fp::controls() == ieee);
}

#else  // core/fp_mode.hpp

TEST_CASE("denormal guard: a denormal survives inside the guard while the host flushes", "[fp_mode][internal]") {
  FAIL("engine/src/core/fp_mode.hpp is missing (Story 1.2 denormal guard)");
}

#endif  // core/fp_mode.hpp
