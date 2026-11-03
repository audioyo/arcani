// arcani-tables-dump [TABLES_DIR]: prints every row the C++ table loader
// read, one line per row in the cross-check format (tables.hpp, dump_line),
// for tests/python/test_tables_crosscheck.py. Test only, never shipped.
// Exit 0; on a loader error, the message on stderr and exit 1.

#include "tables.hpp"

#include <cstdio>
#include <exception>
#include <string>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

int main(int argc, char** argv) {
#ifdef _WIN32
  // LF line ends on Windows too: no text-mode translation of stdout.
  _setmode(_fileno(stdout), _O_BINARY);
#endif
  const std::string dir = argc > 1 ? argv[1] : ARCANI_TABLES_DIR;
  try {
    for (const auto& r : arcani::test::tables::load_tables(dir)) {
      const std::string line = arcani::test::tables::dump_line(r) + "\n";
      std::fwrite(line.data(), 1, line.size(), stdout);
    }
  } catch (const std::exception& e) {
    std::fprintf(stderr, "%s\n", e.what());
    return 1;
  }
  return 0;
}
