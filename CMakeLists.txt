cmake_minimum_required(VERSION 4.4)

# Reads toolchain.json, fails on a CMake version mismatch, and arms the
# compiler pin check that runs before the compiler sanity try_compile.
include(cmake/Pins.cmake)

project(arcani VERSION 0.0.1 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(ARCANI_BUILD_TESTS "Build the C++ test binary" ON)

# compile_commands.json lets tools/check_compile_flags.py check the commands
# Ninja really runs, including anything added through CMAKE_CXX_FLAGS.
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
# No C++20 modules are used. Module scanning would add an @<file>.modmap
# response file to every compile command, which hides flags from the check.
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)

# AD-9 bit-exactness: no fused multiply-add contraction and no fast-math, for
# the whole project. add_compile_options lands after CMAKE_CXX_FLAGS and the
# build-type flags on each command line, so it restores contraction off after
# any earlier fp option. Other fast-math effects of an earlier flag are not
# undone; tools/check_compile_flags.py catches them.
# Warnings as errors apply to arcani_engine, arcani-render, and the test-only
# arcani-hashprobe.
if(CMAKE_CXX_COMPILER_FRONTEND_VARIANT STREQUAL "MSVC")
  set(ARCANI_TOOLCHAIN_NAME "clang-cl")
  set(ARCANI_FP_FLAGS "/clang:-ffp-contract=off")
  set(ARCANI_WARNING_FLAGS /W4 /WX)
else()
  if(CMAKE_CXX_COMPILER_ID STREQUAL "AppleClang")
    set(ARCANI_TOOLCHAIN_NAME "AppleClang")
  else()
    set(ARCANI_TOOLCHAIN_NAME "clang")
  endif()
  set(ARCANI_FP_FLAGS "-ffp-contract=off")
  set(ARCANI_WARNING_FLAGS -Wall -Wextra -Werror)
endif()
add_compile_options(${ARCANI_FP_FLAGS})

add_subdirectory(engine)
add_subdirectory(cli)
# Cross-platform hash probe (test only). Always built, so the Android NDK
# build, which has no C++ tests, has it too.
add_subdirectory(tests/hashprobe)

if(ARCANI_BUILD_TESTS)
  include(FetchContent)
  set(CATCH_INSTALL_DOCS OFF CACHE BOOL "" FORCE)
  set(CATCH_INSTALL_EXTRAS OFF CACHE BOOL "" FORCE)
  FetchContent_Declare(Catch2
    URL "${ARCANI_PIN_CATCH2_URL}"
    URL_HASH "SHA256=${ARCANI_PIN_CATCH2_SHA256}"
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
  FetchContent_MakeAvailable(Catch2)

  enable_testing()
  add_subdirectory(tests/cpp)
endif()
