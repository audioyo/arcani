cmake_minimum_required(VERSION 4.4)

# Reads toolchain.json, fails on a CMake version mismatch, and arms the
# compiler pin check that runs before the compiler sanity try_compile.
include(cmake/Pins.cmake)

project(arcani VERSION 0.0.1 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(ARCANI_BUILD_TESTS "Build the C++ test binary" ON)

add_subdirectory(engine)
add_subdirectory(cli)

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
