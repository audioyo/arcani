// SHA-256 (FIPS 180-4), engine-owned so the recipe hash needs no third-party
// library (AD-9 pure core). Story 1.1.

#ifndef ARCANI_CRYPTO_SHA256_HPP
#define ARCANI_CRYPTO_SHA256_HPP

#include <array>
#include <cstdint>
#include <string>
#include <string_view>

namespace arcani::crypto {

// Digest of the bytes. Pure: no allocation, no I/O.
std::array<std::uint8_t, 32> sha256(std::string_view bytes) noexcept;

// The digest as 64 lowercase hex digits.
std::string sha256_hex(std::string_view bytes);

}  // namespace arcani::crypto

#endif  // ARCANI_CRYPTO_SHA256_HPP
