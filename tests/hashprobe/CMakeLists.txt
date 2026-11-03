# Cross-platform hash probe (test only, never shipped). Built by every preset,
# the Android NDK one included, so each platform job can run it.
#
# ARCANI_HASHPROBE_EXTRA_FLAGS is a test-only cache variable: compile options
# appended to this target only, after the project fp flags, so they win. Only
# the contract-mustfail CI job sets it (-ffp-contract=fast) to prove that a
# contracted build gives a different hash. Never set it in presets.
set(ARCANI_HASHPROBE_EXTRA_FLAGS "" CACHE STRING
  "Test only: extra compile options for arcani-hashprobe. Never set in presets.")

add_executable(arcani-hashprobe main.cpp)
target_compile_options(arcani-hashprobe PRIVATE ${ARCANI_WARNING_FLAGS})
if(ARCANI_HASHPROBE_EXTRA_FLAGS)
  target_compile_options(arcani-hashprobe PRIVATE ${ARCANI_HASHPROBE_EXTRA_FLAGS})
endif()
if(WIN32)
  # fopen is the portable call here; the probe is not engine code.
  target_compile_definitions(arcani-hashprobe PRIVATE _CRT_SECURE_NO_WARNINGS)
endif()
if(ANDROID)
  # Static bionic binary: runs on the hosted arm64 Linux runner without the
  # Android OS (design log 2026-11-02 (aa)).
  target_link_options(arcani-hashprobe PRIVATE -static)
endif()
