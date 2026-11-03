add_executable(arcani-render main.cpp)
# Reaches the engine only through its public header target.
target_link_libraries(arcani-render PRIVATE arcani::engine)
target_compile_options(arcani-render PRIVATE ${ARCANI_WARNING_FLAGS})
