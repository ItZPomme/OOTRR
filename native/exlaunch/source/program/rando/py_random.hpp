#pragma once
// Générateur pseudo-aléatoire identique à random.Random de Python (CPython 3.12) :
// Mersenne Twister MT19937, graine entière via init_by_array, _randbelow par getrandbits,
// shuffle et choice. Le générateur natif reproduit ainsi exactement les seeds du générateur Python.
#include <cstdint>

namespace ootrr {

class PyRandom {
public:
    explicit PyRandom(uint64_t seed) { Seed(seed); }

    void Seed(uint64_t seed) {
        // random.seed(int) : valeur absolue découpée en mots de 32 bits (poids faible d'abord)
        uint32_t key[2];
        int n = 0;
        key[n++] = static_cast<uint32_t>(seed);
        if (seed >> 32) key[n++] = static_cast<uint32_t>(seed >> 32);
        InitByArray(key, n);
    }

    uint32_t Next32() {
        if (index_ >= kN) Twist();
        uint32_t y = mt_[index_++];
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c5680u;
        y ^= (y << 15) & 0xefc60000u;
        y ^= y >> 18;
        return y;
    }

    // getrandbits(k), 1 <= k <= 32
    uint32_t GetRandBits(int k) { return Next32() >> (32 - k); }

    // _randbelow(n), n >= 1
    uint32_t RandBelow(uint32_t n) {
        int k = 0;
        while ((n >> k) != 0) k++;  // n.bit_length()
        uint32_t r = GetRandBits(k);
        while (r >= n) r = GetRandBits(k);
        return r;
    }

    template <typename T>
    void Shuffle(T* data, int count) {
        for (int i = count - 1; i >= 1; i--) {
            int j = static_cast<int>(RandBelow(static_cast<uint32_t>(i + 1)));
            T tmp = data[i];
            data[i] = data[j];
            data[j] = tmp;
        }
    }

    // index choisi par choice(seq) pour une séquence de taille count (>= 1)
    int ChoiceIndex(int count) { return static_cast<int>(RandBelow(static_cast<uint32_t>(count))); }

private:
    static constexpr int kN = 624;
    static constexpr int kM = 397;
    uint32_t mt_[kN];
    int index_ = kN + 1;

    void InitGenrand(uint32_t s) {
        mt_[0] = s;
        for (int i = 1; i < kN; i++) mt_[i] = 1812433253u * (mt_[i - 1] ^ (mt_[i - 1] >> 30)) + static_cast<uint32_t>(i);
        index_ = kN;
    }

    void InitByArray(const uint32_t* key, int length) {
        InitGenrand(19650218u);
        int i = 1, j = 0;
        for (int k = (kN > length ? kN : length); k; k--) {
            mt_[i] = (mt_[i] ^ ((mt_[i - 1] ^ (mt_[i - 1] >> 30)) * 1664525u)) + key[j] + static_cast<uint32_t>(j);
            i++;
            j++;
            if (i >= kN) { mt_[0] = mt_[kN - 1]; i = 1; }
            if (j >= length) j = 0;
        }
        for (int k = kN - 1; k; k--) {
            mt_[i] = (mt_[i] ^ ((mt_[i - 1] ^ (mt_[i - 1] >> 30)) * 1566083941u)) - static_cast<uint32_t>(i);
            i++;
            if (i >= kN) { mt_[0] = mt_[kN - 1]; i = 1; }
        }
        mt_[0] = 0x80000000u;
    }

    void Twist() {
        for (int k = 0; k < kN; k++) {
            uint32_t y = (mt_[k] & 0x80000000u) | (mt_[(k + 1) % kN] & 0x7fffffffu);
            mt_[k] = mt_[(k + kM) % kN] ^ (y >> 1) ^ ((y & 1u) ? 0x9908b0dfu : 0u);
        }
        index_ = 0;
    }
};

}  // namespace ootrr
