add_executable(arcani_tests
  test_engine_version.cpp
  test_cli_stub.cpp)
target_link_libraries(arcani_tests PRIVATE arcani::engine Catch2::Catch2WithMain)
target_compile_definitions(arcani_tests PRIVATE
  ARCANI_RENDER_PATH="$<TARGET_FILE:arcani-render>")
add_dependencies(arcani_tests arcani-render)

# One ctest entry runs every Catch2 test case. Per-case discovery is not used:
# Catch2 reads a test name starting with "--" as a command-line option.
add_test(NAME arcani_tests COMMAND arcani_tests)
