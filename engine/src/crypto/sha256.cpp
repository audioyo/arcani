// SHA-256 (FIPS 180-4 section 6.2).

#include "crypto/sha256.hpp"

#include <cstddef>

namespace arcani::crypto {

namespace {

constexpr std::uint32_t kRound[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u, 0x923f82a4u,
    0xab1c5ed5u, 0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u, 0x72be5d74u, 0x80deb1feu,
    0x9bdc06a7u, 0xc19bf174u, 0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu,
    0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau, 0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u,
    0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu,
    0x53380d13u, 0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u, 0xa2bfe8a1u, 0xa81a664bu,
    0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u, 0x19a4c116u,
    0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
    0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u, 0x90befffau, 0xa4506cebu, 0xbef9a3f7u,
    0xc67178f2u};

constexpr std::uint32_t rotr(std::uint32_t x, int n) noexcept {
  return (x >> n) | (x << (32 - n));
}

void compress(std::uint32_t (&h)[8], const std::uint8_t* block) noexcept {
  std::uint32_t w[64];
  for (int t = 0; t < 16; ++t) {
    w[t] = (std::uint32_t{block[4 * t]} << 24) | (std::uint32_t{block[4 * t + 1]} << 16) |
           (std::uint32_t{block[4 * t + 2]} << 8) | std::uint32_t{block[4 * t + 3]};
  }
  for (int t = 16; t < 64; ++t) {
    const std::uint32_t s0 = rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^ (w[t - 15] >> 3);
    const std::uint32_t s1 = rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^ (w[t - 2] >> 10);
    w[t] = w[t - 16] + s0 + w[t - 7] + s1;
  }
  std::uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], k = h[7];
  for (int t = 0; t < 64; ++t) {
    const std::uint32_t big1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
    const std::uint32_t ch = (e & f) ^ (~e & g);
    const std::uint32_t t1 = k + big1 + ch + kRound[t] + w[t];
    const std::uint32_t big0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
    const std::uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
    const std::uint32_t t2 = big0 + maj;
    k = g;
    g = f;
    f = e;
    e = d + t1;
    d = c;
    c = b;
    b = a;
    a = t1 + t2;
  }
  h[0] += a;
  h[1] += b;
  h[2] += c;
  h[3] += d;
  h[4] += e;
  h[5] += f;
  h[6] += g;
  h[7] += k;
}

}  // namespace

std::array<std::uint8_t, 32> sha256(std::string_view bytes) noexcept {
  std::uint32_t h[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                        0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
  const auto* data = reinterpret_cast<const std::uint8_t*>(bytes.data());
  const std::size_t size = bytes.size();
  std::size_t full = size - size % 64;
  for (std::size_t at = 0; at < full; at += 64) {
    compress(h, data + at);
  }
  // Padding: 0x80, zeros, then the message length in bits, big-endian.
  std::uint8_t tail[128] = {};
  const std::size_t rest = size - full;
  for (std::size_t i = 0; i < rest; ++i) {
    tail[i] = data[full + i];
  }
  tail[rest] = 0x80;
  const std::size_t tail_size = rest + 1 + 8 <= 64 ? 64 : 128;
  const std::uint64_t bits = static_cast<std::uint64_t>(size) * 8u;
  for (int i = 0; i < 8; ++i) {
    tail[tail_size - 1 - static_cast<std::size_t>(i)] = static_cast<std::uint8_t>(bits >> (8 * i));
  }
  compress(h, tail);
  if (tail_size == 128) {
    compress(h, tail + 64);
  }
  std::array<std::uint8_t, 32> out{};
  for (int i = 0; i < 8; ++i) {
    out[static_cast<std::size_t>(4 * i)] = static_cast<std::uint8_t>(h[i] >> 24);
    out[static_cast<std::size_t>(4 * i + 1)] = static_cast<std::uint8_t>(h[i] >> 16);
    out[static_cast<std::size_t>(4 * i + 2)] = static_cast<std::uint8_t>(h[i] >> 8);
    out[static_cast<std::size_t>(4 * i + 3)] = static_cast<std::uint8_t>(h[i]);
  }
  return out;
}

std::string sha256_hex(std::string_view bytes) {
  static constexpr char kHex[] = "0123456789abcdef";
  const auto digest = sha256(bytes);
  std::string out;
  out.reserve(64);
  for (const std::uint8_t b : digest) {
    out += kHex[b >> 4];
    out += kHex[b & 0x0f];
  }
  return out;
}

}  // namespace arcani::crypto
