# Spec vectors reach the C++ tests through a header generated at configure
# time (tests/cpp/SpecTables.cmake), never as literals; editing the vectors
# JSON re-runs the configure. Thresholds and ranges are read at run time from
# tests/tables/*.tsv through the assertion library (tests/assertions/), which
# records each row id in the ctest row usage file for the coverage check.
include("${CMAKE_CURRENT_SOURCE_DIR}/SpecTables.cmake")
set(_arcani_spec_vectors "${CMAKE_SOURCE_DIR}/tests/data/signal_spec_vectors.json")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${_arcani_spec_vectors}" "${CMAKE_CURRENT_SOURCE_DIR}/SpecTables.cmake")
arcani_generate_spec_tables(
  "${CMAKE_CURRENT_BINARY_DIR}/generated/spec_tables.hpp" "${_arcani_spec_vectors}")

add_executable(arcani_tests
  test_engine_version.cpp
  test_cli_stub.cpp
  test_phase.cpp
  test_sine.cpp
  test_tables.cpp)
# arcani::engine_internal exposes engine/src (core/phase.hpp, core/sine.hpp)
# to the tests; the public C API header stays the only shipped include path.
target_link_libraries(arcani_tests PRIVATE
  arcani::engine arcani::engine_internal arcani::test_tables Catch2::Catch2WithMain)
target_include_directories(arcani_tests PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
target_compile_definitions(arcani_tests PRIVATE
  ARCANI_RENDER_PATH="$<TARGET_FILE:arcani-render>"
  ARCANI_TABLE_FIXTURES_DIR="${CMAKE_SOURCE_DIR}/tests/fixtures/tables")
add_dependencies(arcani_tests arcani-render)

# One ctest entry runs every Catch2 test case. Per-case discovery is not used:
# Catch2 reads a test name starting with "--" as a command-line option.
add_test(NAME arcani_tests COMMAND arcani_tests)
# Row usage file for tools/check_row_coverage.py (Story 0.3).
set_tests_properties(arcani_tests PROPERTIES
  ENVIRONMENT "ARCANI_ROW_USAGE_FILE=${CMAKE_SOURCE_DIR}/build/row-usage/ctest.txt")
