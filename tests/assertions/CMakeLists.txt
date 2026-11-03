# Assertion library: the C++ threshold and range table loader and the
# assertion call (tables.hpp), plus the test-only arcani-tables-dump used by
# the C++/Python cross-check. Both are EXCLUDE_FROM_ALL: they build only when
# arcani_tests links the library or a test asks for the dump target, so
# platform jobs that build everything (the Android NDK one included) do not
# change. The tables are read at run time, so editing them needs no configure.
add_library(arcani_test_tables STATIC EXCLUDE_FROM_ALL tables.cpp)
add_library(arcani::test_tables ALIAS arcani_test_tables)
target_include_directories(arcani_test_tables PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_compile_definitions(arcani_test_tables PUBLIC
  ARCANI_TABLES_DIR="${CMAKE_SOURCE_DIR}/tests/tables")
target_compile_options(arcani_test_tables PRIVATE ${ARCANI_WARNING_FLAGS})
if(WIN32)
  # getenv and fopen-family calls are the portable ones here; test code only.
  target_compile_definitions(arcani_test_tables PRIVATE _CRT_SECURE_NO_WARNINGS)
endif()

add_executable(arcani-tables-dump EXCLUDE_FROM_ALL dump_main.cpp)
target_link_libraries(arcani-tables-dump PRIVATE arcani::test_tables)
target_compile_options(arcani-tables-dump PRIVATE ${ARCANI_WARNING_FLAGS})
