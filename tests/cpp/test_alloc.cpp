// Real-time contract: render never allocates (Story 1.2). Its own test
// executable, arcani_alloc_tests, because it replaces the global operator new
// and operator delete with counting versions for the whole program. Public
// header only.
//
// The counter counts every replaceable operator new form (plain, array,
// nothrow, aligned) while a counting window is open. The window opens after
// compile and renderer creation and closes after the render calls, so only
// the render calls are measured. The window body does no Catch2 work: results
// are stored in preallocated arrays and checked after the window closes.
//
// Limit: a direct malloc call is not counted. The engine has no reason to
// call malloc; operator new is how C++ standard library containers allocate.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#include <atomic>
#include <cstddef>
#include <cstdlib>
#include <new>

#if defined(_WIN32)
#include <malloc.h>
#endif

namespace {

std::atomic<bool> g_counting{false};
std::atomic<std::size_t> g_allocations{0};
// Fail-next-allocation switch: the next operator new call of any form fails
// (the throwing forms throw std::bad_alloc, the nothrow forms return
// nullptr), then the switch clears itself.
std::atomic<bool> g_fail_next{false};

void* counted_alloc(std::size_t n) {
  if (g_counting.load(std::memory_order_relaxed)) {
    g_allocations.fetch_add(1, std::memory_order_relaxed);
  }
  if (g_fail_next.exchange(false)) {
    return nullptr;
  }
  return std::malloc(n == 0 ? 1 : n);
}

void* counted_aligned_alloc(std::size_t n, std::size_t align) {
  if (g_counting.load(std::memory_order_relaxed)) {
    g_allocations.fetch_add(1, std::memory_order_relaxed);
  }
  if (g_fail_next.exchange(false)) {
    return nullptr;
  }
  if (n == 0) {
    n = 1;
  }
#if defined(_WIN32)
  return _aligned_malloc(n, align);
#else
  void* p = nullptr;
  if (align < sizeof(void*)) {
    align = sizeof(void*);
  }
  return posix_memalign(&p, align, n) == 0 ? p : nullptr;
#endif
}

void aligned_free(void* p) {
#if defined(_WIN32)
  _aligned_free(p);
#else
  std::free(p);
#endif
}

// Opens a counting window for its lifetime.
class CountingWindow {
 public:
  CountingWindow() {
    g_allocations.store(0);
    g_counting.store(true);
  }
  ~CountingWindow() { g_counting.store(false); }
  CountingWindow(const CountingWindow&) = delete;
  CountingWindow& operator=(const CountingWindow&) = delete;
};

}  // namespace

void* operator new(std::size_t n) {
  void* p = counted_alloc(n);
  if (p == nullptr) throw std::bad_alloc();
  return p;
}
void* operator new[](std::size_t n) {
  void* p = counted_alloc(n);
  if (p == nullptr) throw std::bad_alloc();
  return p;
}
void* operator new(std::size_t n, const std::nothrow_t&) noexcept { return counted_alloc(n); }
void* operator new[](std::size_t n, const std::nothrow_t&) noexcept { return counted_alloc(n); }
void* operator new(std::size_t n, std::align_val_t a) {
  void* p = counted_aligned_alloc(n, static_cast<std::size_t>(a));
  if (p == nullptr) throw std::bad_alloc();
  return p;
}
void* operator new[](std::size_t n, std::align_val_t a) {
  void* p = counted_aligned_alloc(n, static_cast<std::size_t>(a));
  if (p == nullptr) throw std::bad_alloc();
  return p;
}
void* operator new(std::size_t n, std::align_val_t a, const std::nothrow_t&) noexcept {
  return counted_aligned_alloc(n, static_cast<std::size_t>(a));
}
void* operator new[](std::size_t n, std::align_val_t a, const std::nothrow_t&) noexcept {
  return counted_aligned_alloc(n, static_cast<std::size_t>(a));
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }
void operator delete(void* p, const std::nothrow_t&) noexcept { std::free(p); }
void operator delete[](void* p, const std::nothrow_t&) noexcept { std::free(p); }
void operator delete(void* p, std::align_val_t) noexcept { aligned_free(p); }
void operator delete[](void* p, std::align_val_t) noexcept { aligned_free(p); }
void operator delete(void* p, std::size_t, std::align_val_t) noexcept { aligned_free(p); }
void operator delete[](void* p, std::size_t, std::align_val_t) noexcept { aligned_free(p); }
void operator delete(void* p, std::align_val_t, const std::nothrow_t&) noexcept { aligned_free(p); }
void operator delete[](void* p, std::align_val_t, const std::nothrow_t&) noexcept { aligned_free(p); }

TEST_CASE("the counter counts an allocation inside the window", "[alloc]") {
  // Must-fail side of the check: one explicit operator new call (not a
  // new-expression, which the compiler may elide) is counted.
  static void* volatile sink = nullptr;
  std::size_t counted = 0;
  {
    CountingWindow window;
    sink = ::operator new(64);
    counted = g_allocations.load();
  }
  ::operator delete(sink);
  CHECK(counted == 1);
  {
    CountingWindow window;
    sink = ::operator new[](32, std::nothrow);
    counted = g_allocations.load();
  }
  ::operator delete[](sink);
  CHECK(counted == 1);
  {
    CountingWindow window;
    counted = g_allocations.load();
  }
  CHECK(counted == 0);
}

#ifdef ARC_ERROR_FIELD_BYTES

#include "api_helpers.hpp"

#include <array>
#include <vector>

namespace api = arcani::test::api;

TEST_CASE("render calls allocate nothing after compile and renderer creation", "[alloc]") {
  for (const std::uint32_t fs : {44100u, 48000u}) {
    for (const char* fixture : {api::kBeat0, api::kBeat6, api::kNoLayers}) {
      INFO(fixture << " at " << fs);
      auto plan = api::compile_ok(api::valid(fixture), api::options(ARC_MODE_MEASURE, fs));
      auto r = api::renderer(plan.get());
      const auto frames = static_cast<std::size_t>(arc_plan_frame_count(plan.get()));
      // Every buffer exists before the window opens.
      constexpr std::size_t kMaxChunk = 4096;
      std::vector<double> out(2 * kMaxChunk);
      api::TapBuffers taps(kMaxChunk);
      const arc_taps t = taps.taps();
      const std::array<std::size_t, 8> chunks = {1, 37, 63, 64, 65, 512, 4096, 1000};
      std::array<arc_status, 256> statuses{};
      // Seeks inside a block, on a block boundary, and past the end, each
      // followed by a render.
      const std::array<std::uint64_t, 3> seeks = {37, 64, frames + 10};
      std::array<arc_status, 6> seek_statuses{};
      arc_error e;
      std::size_t calls = 0;
      std::size_t rendered = 0;
      std::size_t counted = 0;
      {
        CountingWindow window;
        // Through the whole session and past its end, with and without taps,
        // plus an error return (null output buffer).
        while (rendered < frames + 5000 && calls + 1 < statuses.size()) {
          const std::size_t n = chunks[calls % chunks.size()];
          statuses[calls] = arc_render(r.get(), out.data(), n, calls % 2 ? &t : nullptr, &e);
          ++calls;
          rendered += n;
        }
        for (std::size_t k = 0; k < seeks.size(); ++k) {
          seek_statuses[2 * k] = arc_seek(r.get(), seeks[k], &e);
          seek_statuses[2 * k + 1] = arc_render(r.get(), out.data(), 100, &t, &e);
        }
        statuses[calls] = arc_render(r.get(), nullptr, 16, nullptr, &e);
        ++calls;
        counted = g_allocations.load();
      }
      CHECK(counted == 0);
      CHECK(rendered >= frames);
      for (std::size_t i = 0; i + 1 < calls; ++i) {
        CHECK(statuses[i] == ARC_OK);
      }
      CHECK(statuses[calls - 1] == ARC_ERR_INVALID_ARGUMENT);
      for (const arc_status s : seek_statuses) {
        CHECK(s == ARC_OK);
      }
    }
  }
}

TEST_CASE("the fail-next switch fails one allocation of each form", "[alloc]") {
  // Must-fail side of the out-of-memory cases below: the switch really fails
  // the next allocation, and only that one.
  g_fail_next.store(true);
  CHECK_THROWS_AS(::operator new(16), std::bad_alloc);
  void* p = ::operator new(16);
  CHECK(p != nullptr);
  ::operator delete(p);
  g_fail_next.store(true);
  CHECK(::operator new(16, std::nothrow) == nullptr);
  CHECK_FALSE(g_fail_next.load());
}

namespace {

void require_out_of_memory(arc_status s, const arc_error& e) {
  INFO(api::describe(e));
  CHECK(s == ARC_ERR_OUT_OF_MEMORY);
  REQUIRE(api::all_written(e));
  CHECK(std::string(e.rule) == "memory");
}

}  // namespace

TEST_CASE("an allocation failure in compile or renderer creation returns out of memory", "[alloc]") {
  const std::string text = api::valid(api::kBeat6);
  const arc_compile_options o = api::options(ARC_MODE_MEASURE, 48000);
  SECTION("arc_compile") {
    arc_error e;
    api::poison(e);
    arc_plan* plan = reinterpret_cast<arc_plan*>(&e);  // must be overwritten
    g_fail_next.store(true);
    const arc_status s = arc_compile(text.data(), text.size(), &o, &plan, &e);
    g_fail_next.store(false);
    CHECK(plan == nullptr);
    require_out_of_memory(s, e);
    arc_plan_release(plan);
  }
  SECTION("arc_renderer_create") {
    auto plan = api::compile_ok(text, o);
    arc_error e;
    api::poison(e);
    arc_renderer* r = reinterpret_cast<arc_renderer*>(&e);  // must be overwritten
    g_fail_next.store(true);
    const arc_status s = arc_renderer_create(plan.get(), &r, &e);
    g_fail_next.store(false);
    CHECK(r == nullptr);
    require_out_of_memory(s, e);
    arc_renderer_destroy(r);
    // The plan is still usable: a renderer on it now succeeds.
    auto ok = api::renderer(plan.get());
    CHECK(ok != nullptr);
  }
}

#else  // ARC_ERROR_FIELD_BYTES

TEST_CASE("render calls allocate nothing after compile and renderer creation", "[alloc]") {
  FAIL("arcani/arcani.h does not declare the Story 1.2 C API yet (no ARC_ERROR_FIELD_BYTES)");
}

#endif  // ARC_ERROR_FIELD_BYTES
