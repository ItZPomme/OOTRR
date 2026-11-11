#pragma once
// Générateur de seed natif : portage exact de ootrr/search.py et ootrr/fill.py.
// Données : logic_data.hpp (python -m ootrr.native_logic). Aucune allocation dynamique.
#include <cstdint>

#include "logic_data.hpp"

namespace ootrr {

struct Settings {
    int32_t values[logic::kSettingCount];

    static Settings Defaults() {
        Settings s{};
        for (int i = 0; i < logic::kSettingCount; i++) s.values[i] = logic::kSettings[i].def;
        return s;
    }
    int32_t operator[](int id) const { return values[id]; }
};

struct SeedResult {
    bool ok = false;
    int attempts = 0;
    // objet (index de kItems) placé à chaque lieu (index de kLocations), -1 si aucun
    int16_t placement[logic::kLocationCount];
};

// Génère une seed ; même résultat que fill.generate(World(settings), seed) en Python.
bool Generate(const Settings& settings, uint64_t seed, SeedResult& out, int max_attempts = 20);

}  // namespace ootrr
