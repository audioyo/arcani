# arcani_cli_core: 24-bit rounding, the WAV header, and the JSON report
# (wav.cpp, report.cpp), shared by arcani-render and the C++ tests. The CLI
# reaches the engine only through its public header target, and reads the
# threshold tables through the assertion library (tests/assertions, AD-17).
add_library(arcani_cli_core STATIC wav.cpp report.cpp)
target_include_directories(arcani_cli_core PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(arcani_cli_core PUBLIC arcani::engine arcani::test_tables)
target_compile_options(arcani_cli_core PRIVATE ${ARCANI_WARNING_FLAGS})

add_executable(arcani-render main.cpp)
target_link_libraries(arcani-render PRIVATE arcani_cli_core arcani::engine arcani::test_tables)
target_compile_options(arcani-render PRIVATE ${ARCANI_WARNING_FLAGS})
if(WIN32)
  # getenv and fopen are the portable calls here.
  target_compile_definitions(arcani_cli_core PRIVATE _CRT_SECURE_NO_WARNINGS)
  target_compile_definitions(arcani-render PRIVATE _CRT_SECURE_NO_WARNINGS)
endif()
