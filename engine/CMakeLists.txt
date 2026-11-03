# Pure engine core: C++ standard library only.
#
# ARCANI_ENGINE_TEST_EXTRA_SOURCE is a test-only cache variable
# (tests/cmake/test_engine_symbols.py). When set to a source file path, that
# file is compiled into arcani_engine so the symbol check's must-fail case can
# be exercised. Never set it in presets or CI.
set(ARCANI_ENGINE_TEST_EXTRA_SOURCE "" CACHE FILEPATH
  "Test only: one extra source compiled into arcani_engine. Never set in presets or CI.")

set(_arcani_engine_sources src/version.cpp)
if(ARCANI_ENGINE_TEST_EXTRA_SOURCE)
  list(APPEND _arcani_engine_sources "${ARCANI_ENGINE_TEST_EXTRA_SOURCE}")
endif()

add_library(arcani_engine STATIC ${_arcani_engine_sources})
add_library(arcani::engine ALIAS arcani_engine)

# The public header directory is the only include path consumers see.
target_include_directories(arcani_engine PUBLIC
  "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_definitions(arcani_engine PRIVATE
  ARC_ENGINE_VERSION_STRING="${PROJECT_VERSION}")
target_compile_options(arcani_engine PRIVATE ${ARCANI_WARNING_FLAGS})

# llvm-nm for tools/check_engine_symbols.py: only the one shipped next to the
# pinned compiler, never one from PATH. The compiler path may be a symlink
# (for example /usr/bin/clang++), so its resolved directory is searched first.
get_filename_component(_arcani_compiler_dir "${CMAKE_CXX_COMPILER}" DIRECTORY)
file(REAL_PATH "${CMAKE_CXX_COMPILER}" _arcani_compiler_real)
get_filename_component(_arcani_compiler_real_dir "${_arcani_compiler_real}" DIRECTORY)
find_program(ARCANI_LLVM_NM NAMES llvm-nm
  HINTS "${_arcani_compiler_real_dir}" "${_arcani_compiler_dir}"
  NO_DEFAULT_PATH NO_CACHE)
if(NOT ARCANI_LLVM_NM)
  message(FATAL_ERROR
    "llvm-nm not found next to the pinned compiler: expected it in "
    "${_arcani_compiler_dir} (compiler ${CMAKE_CXX_COMPILER})")
endif()

# Facts the build checks need, written at generate time:
# tools/check_compile_flags.py and tools/check_engine_symbols.py read it.
function(_arcani_json_string out_var value)
  string(REPLACE "\\" "\\\\" value "${value}")
  string(REPLACE "\"" "\\\"" value "${value}")
  set(${out_var} "\"${value}\"" PARENT_SCOPE)
endfunction()
_arcani_json_string(_j_name "${ARCANI_TOOLCHAIN_NAME}")
_arcani_json_string(_j_version "${CMAKE_CXX_COMPILER_VERSION}")
_arcani_json_string(_j_source "${CMAKE_SOURCE_DIR}")
_arcani_json_string(_j_commands "${CMAKE_BINARY_DIR}/compile_commands.json")
_arcani_json_string(_j_nm "${ARCANI_LLVM_NM}")
file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/arcani_engine_check.json" CONTENT
"{
  \"toolchain_name\": ${_j_name},
  \"toolchain_version\": ${_j_version},
  \"source_dir\": ${_j_source},
  \"compile_commands\": ${_j_commands},
  \"engine_library\": \"$<TARGET_FILE:arcani_engine>\",
  \"llvm_nm\": ${_j_nm}
}
")
