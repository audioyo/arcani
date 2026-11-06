# Engine tap dump for the Python reference match (Story 1.5). Test only,
# never shipped. tests/python/test_reference_match.py builds it in the
# platform preset's own build directory
# (cmake --build --preset <preset> --target arcani-tapdump) and compares its
# files with reference/stub_chain.py. Public C API header only.
add_executable(arcani-tapdump main.cpp)
target_link_libraries(arcani-tapdump PRIVATE arcani::engine)
target_compile_options(arcani-tapdump PRIVATE ${ARCANI_WARNING_FLAGS})
if(WIN32)
  # fopen is the portable call here; the dump is not engine code.
  target_compile_definitions(arcani-tapdump PRIVATE _CRT_SECURE_NO_WARNINGS)
endif()
