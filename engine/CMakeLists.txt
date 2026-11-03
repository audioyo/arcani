# Pure engine core: C++ standard library only.
add_library(arcani_engine STATIC src/version.cpp)
add_library(arcani::engine ALIAS arcani_engine)

# The public header directory is the only include path consumers see.
target_include_directories(arcani_engine PUBLIC
  "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_definitions(arcani_engine PRIVATE
  ARC_ENGINE_VERSION_STRING="${PROJECT_VERSION}")
