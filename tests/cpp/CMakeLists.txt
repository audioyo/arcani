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
  test_cli.cpp
  test_phase.cpp
  test_sine.cpp
  test_tables.cpp
  test_json.cpp
  test_recipe.cpp
  test_sha256.cpp
  test_api.cpp
  test_stages.cpp
  test_seek.cpp
  test_isolation.cpp
  test_fp_mode.cpp
  test_validate.cpp
  test_wav.cpp
  test_report.cpp
  test_determinism.cpp
  test_theta.cpp
  test_gamma.cpp
  test_coupling.cpp)
# arcani::engine_internal exposes engine/src (core/phase.hpp, core/sine.hpp)
# to the tests; the public C API header stays the only shipped include path.
target_link_libraries(arcani_tests PRIVATE
  arcani::engine arcani::engine_internal arcani::test_tables Catch2::Catch2WithMain)
# Story 1.4: test_wav.cpp and test_report.cpp test the CLI core (cli/wav.hpp,
# cli/report.hpp) through the static library arcani_cli_core, whose PUBLIC
# include directory is cli/. Linked, and ARCANI_HAVE_CLI_CORE defined, only
# once that target exists, so the suite builds before it does and the
# missing pieces show as failing test cases.
target_link_libraries(arcani_tests PRIVATE $<$<TARGET_EXISTS:arcani_cli_core>:arcani_cli_core>)
target_include_directories(arcani_tests PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
target_compile_definitions(arcani_tests PRIVATE
  ARCANI_RENDER_PATH="$<TARGET_FILE:arcani-render>"
  ARCANI_TABLE_FIXTURES_DIR="${CMAKE_SOURCE_DIR}/tests/fixtures/tables"
  ARCANI_RECIPES_DIR="${CMAKE_SOURCE_DIR}/recipes"
  ARCANI_TEST_DATA_DIR="${CMAKE_SOURCE_DIR}/tests/data"
  ARCANI_TEST_OUT_DIR="${CMAKE_CURRENT_BINARY_DIR}/cli_out"
  $<$<TARGET_EXISTS:arcani_cli_core>:ARCANI_HAVE_CLI_CORE=1>)
add_dependencies(arcani_tests arcani-render)

# One ctest entry runs every Catch2 test case. Per-case discovery is not used:
# Catch2 reads a test name starting with "--" as a command-line option.
add_test(NAME arcani_tests COMMAND arcani_tests)
# Row usage file for tools/check_row_coverage.py (Story 0.3).
set_tests_properties(arcani_tests PROPERTIES
  ENVIRONMENT "ARCANI_ROW_USAGE_FILE=${CMAKE_SOURCE_DIR}/build/row-usage/ctest.txt")

# Story 1.2: render never allocates. Its own executable, because
# test_alloc.cpp replaces the global operator new and operator delete for the
# whole program. Public header only (plus the test fixtures path).
add_executable(arcani_alloc_tests test_alloc.cpp)
target_link_libraries(arcani_alloc_tests PRIVATE arcani::engine Catch2::Catch2WithMain)
target_compile_definitions(arcani_alloc_tests PRIVATE
  ARCANI_RECIPES_DIR="${CMAKE_SOURCE_DIR}/recipes")
add_test(NAME arcani_alloc_tests COMMAND arcani_alloc_tests)

# Story 1.2: the public header compiles as C. The project enables only C++,
# so ctest runs the pinned compiler in C mode, syntax only, warnings as
# errors. The must-fail twin (a C++ reference parameter) must not compile,
# and must fail with the C diagnostic at that parameter (line 7), so a
# missing compiler or a bad flag does not count as the expected failure.
if(CMAKE_CXX_COMPILER_FRONTEND_VARIANT STREQUAL "MSVC")
  set(_arcani_c_check /nologo /TC /Zs /W4 /WX /clang:-std=c11
    "/I${CMAKE_SOURCE_DIR}/engine/include")
else()
  set(_arcani_c_check -x c -std=c11 -fsyntax-only -Wall -Wextra -Werror -pedantic
    "-I${CMAKE_SOURCE_DIR}/engine/include")
endif()
add_test(NAME arcani_api_c_header
  COMMAND "${CMAKE_CXX_COMPILER}" ${_arcani_c_check}
    "${CMAKE_CURRENT_SOURCE_DIR}/test_api_c.c")
add_test(NAME arcani_api_c_header_mustfail
  COMMAND "${CMAKE_CXX_COMPILER}" ${_arcani_c_check}
    "${CMAKE_SOURCE_DIR}/tests/fixtures/c_api/cpp_reference.c")
set_tests_properties(arcani_api_c_header_mustfail PROPERTIES
  PASS_REGULAR_EXPRESSION [=[cpp_reference[.]c[(:]7[,:][0-9]+[):]+ error: expected ']=])
