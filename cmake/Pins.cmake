# Toolchain pins, read from toolchain.json (the single source of tool versions).
#
# Included twice:
#  1. From the top-level CMakeLists.txt before project(): reads the pins,
#     checks the CMake version, and registers this file as
#     CMAKE_USER_MAKE_RULES_OVERRIDE.
#  2. By CMake itself as the user rules override, right after the C++ compiler
#     is identified and before the compiler sanity try_compile: checks the
#     compiler against the llvm pin.
#
# ARCANI_PIN_OVERRIDE_LLVM and ARCANI_PIN_OVERRIDE_CMAKE are test-only cache
# variables (tests/cmake/test_pin_check.py). They replace the expected version
# so the must-fail case can be exercised. Never set them in presets or CI.

set(_arcani_toolchain_file "${CMAKE_CURRENT_LIST_DIR}/../toolchain.json")
file(READ "${_arcani_toolchain_file}" _arcani_toolchain_json)

function(arcani_pin out_var tool)
  string(JSON _value ERROR_VARIABLE _err GET "${_arcani_toolchain_json}" ${tool} ${ARGN})
  if(_err)
    message(FATAL_ERROR "toolchain.json: cannot read ${tool} ${ARGN}: ${_err}")
  endif()
  set(${out_var} "${_value}" PARENT_SCOPE)
endfunction()

arcani_pin(ARCANI_PIN_CMAKE cmake version)
arcani_pin(ARCANI_PIN_LLVM llvm version)
arcani_pin(ARCANI_PIN_CATCH2 catch2 version)
arcani_pin(ARCANI_PIN_CATCH2_URL catch2 url)
arcani_pin(ARCANI_PIN_CATCH2_SHA256 catch2 sha256)

if(ARCANI_PIN_OVERRIDE_CMAKE)
  set(ARCANI_PIN_CMAKE "${ARCANI_PIN_OVERRIDE_CMAKE}")
endif()
if(ARCANI_PIN_OVERRIDE_LLVM)
  set(ARCANI_PIN_LLVM "${ARCANI_PIN_OVERRIDE_LLVM}")
endif()

if(NOT CMAKE_CXX_COMPILER_ID)
  # Pass 1: before project().
  if(NOT CMAKE_VERSION VERSION_EQUAL ARCANI_PIN_CMAKE)
    message(FATAL_ERROR
      "CMake version does not match toolchain.json: "
      "expected CMake ${ARCANI_PIN_CMAKE}, found CMake ${CMAKE_VERSION}")
  endif()
  set(CMAKE_USER_MAKE_RULES_OVERRIDE "${CMAKE_CURRENT_LIST_FILE}")
  # Re-run configure when the pins change.
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_arcani_toolchain_file}")
else()
  # Pass 2: compiler identified, sanity try_compile not yet run.
  if(WIN32)
    set(_arcani_expected_frontend "MSVC")
    set(_arcani_expected_name "clang-cl")
  else()
    set(_arcani_expected_frontend "GNU")
    set(_arcani_expected_name "clang")
  endif()
  set(_arcani_found_frontend "${CMAKE_CXX_COMPILER_FRONTEND_VARIANT}")
  if(NOT _arcani_found_frontend)
    set(_arcani_found_frontend "${CMAKE_CXX_SIMULATE_ID}")
  endif()
  if(NOT CMAKE_CXX_COMPILER_ID STREQUAL "Clang"
     OR NOT CMAKE_CXX_COMPILER_VERSION VERSION_EQUAL ARCANI_PIN_LLVM
     OR NOT _arcani_found_frontend STREQUAL _arcani_expected_frontend)
    message(FATAL_ERROR
      "C++ compiler does not match toolchain.json: "
      "expected ${_arcani_expected_name} ${ARCANI_PIN_LLVM}, "
      "found ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION} "
      "(frontend ${_arcani_found_frontend}) at ${CMAKE_CXX_COMPILER}")
  endif()
endif()
