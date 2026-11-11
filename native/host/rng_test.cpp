// Test hôte : tirages de PyRandom à comparer avec random.Random de Python.
#include <cstdio>
#include <cstdlib>
#include "../exlaunch/source/program/rando/py_random.hpp"
int main(int argc, char** argv) {
    unsigned long long seed = strtoull(argv[1], nullptr, 10);
    ootrr::PyRandom r(seed);
    for (int i = 0; i < 1000; i++) printf("%u\n", r.GetRandBits(32));
    for (int i = 1; i <= 1000; i++) printf("%u\n", r.RandBelow(i));
    int a[50]; for (int i = 0; i < 50; i++) a[i] = i;
    r.Shuffle(a, 50);
    for (int i = 0; i < 50; i++) printf("%d\n", a[i]);
}
