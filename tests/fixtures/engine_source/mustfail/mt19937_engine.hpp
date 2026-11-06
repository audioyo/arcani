// Must-fail fixture: a <random> library engine, even without the include line.
unsigned int draw(unsigned int seed) {
  std::mt19937 engine(seed);
  return static_cast<unsigned int>(engine());
}
