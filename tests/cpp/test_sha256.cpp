// Engine-owned SHA-256 against the FIPS 180-4 / NIST example vectors in
// tests/data/sha256_vectors.json (Story 1.1). The vectors file is read with a
// small pattern match here, not the engine JSON parser, so this test does not
// depend on the parser it would otherwise share a fault with.
//
// Expected interface (engine/src/crypto/sha256.hpp, namespace arcani::crypto):
//
//   std::array<std::uint8_t, 32> sha256(std::string_view bytes) noexcept;
//   std::string sha256_hex(std::string_view bytes);  // 64 lowercase hex digits
//
// Pure: no allocation in sha256, no I/O, C++20 standard library only.

#include <catch2/catch_test_macros.hpp>

#ifndef ARCANI_TEST_DATA_DIR
#error "ARCANI_TEST_DATA_DIR must name tests/data"
#endif

#if __has_include("crypto/sha256.hpp")

#include "crypto/sha256.hpp"

#include <cstddef>
#include <cstdint>
#include <fstream>
#include <regex>
#include <sstream>
#include <string>
#include <vector>

namespace {

struct Vector {
  std::string name, input;
  std::size_t repeat;
  std::string sha256;
};

std::vector<Vector> load_vectors() {
  std::ifstream in(std::string(ARCANI_TEST_DATA_DIR) + "/sha256_vectors.json", std::ios::binary);
  REQUIRE(in.good());
  std::stringstream ss;
  ss << in.rdbuf();
  const std::string text = ss.str();
  // Each vector object is written on its own lines in a fixed key order:
  // name, input_ascii, repeat, sha256 (tools-free, ASCII only).
  const std::regex entry(
      "\"name\":\\s*\"([^\"]*)\",\\s*\"input_ascii\":\\s*\"([^\"]*)\",\\s*"
      "\"repeat\":\\s*([0-9]+),\\s*\"sha256\":\\s*\"([0-9a-f]{64})\"");
  std::vector<Vector> out;
  for (auto it = std::sregex_iterator(text.begin(), text.end(), entry); it != std::sregex_iterator();
       ++it) {
    out.push_back({(*it)[1].str(), (*it)[2].str(), std::stoul((*it)[3].str()), (*it)[4].str()});
  }
  return out;
}

std::string repeat(const std::string& s, std::size_t n) {
  std::string out;
  out.reserve(s.size() * n);
  for (std::size_t i = 0; i < n; ++i) {
    out += s;
  }
  return out;
}

}  // namespace

TEST_CASE("sha256 matches the FIPS 180-4 example vectors", "[sha256]") {
  const auto vectors = load_vectors();
  REQUIRE(vectors.size() >= 5);
  for (const auto& v : vectors) {
    INFO(v.name);
    CHECK(arcani::crypto::sha256_hex(repeat(v.input, v.repeat)) == v.sha256);
  }
}

TEST_CASE("sha256 raw digest and hex form agree", "[sha256]") {
  const auto digest = arcani::crypto::sha256("abc");
  static const char kHex[] = "0123456789abcdef";
  std::string hex;
  for (const std::uint8_t b : digest) {
    hex += kHex[b >> 4];
    hex += kHex[b & 0x0f];
  }
  CHECK(hex == arcani::crypto::sha256_hex("abc"));
}

TEST_CASE("sha256 hashes embedded NUL bytes", "[sha256]") {
  const std::string with_nul("a\0b", 3);
  CHECK(arcani::crypto::sha256_hex(with_nul) != arcani::crypto::sha256_hex("ab"));
  CHECK(arcani::crypto::sha256_hex(with_nul).size() == 64);
}

#else

TEST_CASE("sha256 is implemented", "[sha256]") {
  FAIL("not implemented: crypto/sha256.hpp");
}

#endif
