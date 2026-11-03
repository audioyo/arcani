# Spec vectors, thresholds, and ranges reach the C++ tests through a header
# generated at configure time (tests/cpp/SpecTables.cmake), never as literals.
# Editing any of the three JSON files re-runs the configure.
include("${CMAKE_CURRENT_SOURCE_DIR}/SpecTables.cmake")
set(_arcani_spec_vectors "${CMAKE_SOURCE_DIR}/tests/data/signal_spec_vectors.json")
set(_arcani_spec_thresholds "${CMAKE_SOURCE_DIR}/tests/tables/thresholds.json")
set(_arcani_spec_ranges "${CMAKE_SOURCE_DIR}/tests/tables/ranges.json")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${_arcani_spec_vectors}" "${_arcani_spec_thresholds}" "${_arcani_spec_ranges}"
  "${CMAKE_CURRENT_SOURCE_DIR}/SpecTables.cmake")
arcani_generate_spec_tables(
  "${CMAKE_CURRENT_BINARY_DIR}/generated/spec_tables.hpp"
  "${_arcani_spec_vectors}" "${_arcani_spec_thresholds}" "${_arcani_spec_ranges}")

add_executable(arcani_tests
  test_engine_version.cpp
  test_cli_stub.cpp
  test_phase.cpp
  test_sine.cpp)
# arcani::engine_internal exposes engine/src (core/phase.hpp, core/sine.hpp)
# to the tests; the public C API header stays the only shipped include path.
target_link_libraries(arcani_tests PRIVATE
  arcani::engine arcani::engine_internal Catch2::Catch2WithMain)
target_include_directories(arcani_tests PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
target_compile_definitions(arcani_tests PRIVATE
  ARCANI_RENDER_PATH="$<TARGET_FILE:arcani-render>")
add_dependencies(arcani_tests arcani-render)

# One ctest entry runs every Catch2 test case. Per-case discovery is not used:
# Catch2 reads a test name starting with "--" as a command-line option.
add_test(NAME arcani_tests COMMAND arcani_tests)
