// Générateur natif compilé pour le PC (tests) : python -m ootrr.tools.native_check le compare au
// générateur Python. Usage : gen_main SEED [reglage=valeur ...]
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "../exlaunch/source/program/rando/generator.hpp"

using namespace ootrr;

static bool SetSetting(Settings& s, const char* arg) {
    const char* eq = strchr(arg, '=');
    if (!eq) return false;
    for (int i = 0; i < logic::kSettingCount; i++) {
        const logic::SettingInfo& info = logic::kSettings[i];
        if (strlen(info.name) != static_cast<size_t>(eq - arg) || strncmp(info.name, arg, eq - arg) != 0) continue;
        const char* v = eq + 1;
        if (info.kind == logic::S_BOOL) {
            s.values[i] = (strcmp(v, "true") == 0 || strcmp(v, "True") == 0 || strcmp(v, "1") == 0) ? 1 : 0;
        } else if (info.kind == logic::S_ENUM) {
            for (int k = 0; k < info.value_count; k++)
                if (strcmp(info.values[k], v) == 0) { s.values[i] = k; return true; }
            return false;
        } else {
            s.values[i] = atoi(v);
        }
        return true;
    }
    return false;
}

int main(int argc, char** argv) {
    if (argc < 2) return 2;
    Settings s = Settings::Defaults();
    for (int i = 2; i < argc; i++)
        if (!SetSetting(s, argv[i])) { fprintf(stderr, "réglage invalide : %s\n", argv[i]); return 2; }
    static SeedResult r;
    bool ok = Generate(s, strtoull(argv[1], nullptr, 10), r);
    if (!ok) { printf("ECHEC\n"); return 0; }
    printf("OK %d\n", r.attempts);
    for (int l = 0; l < logic::kLocationCount; l++)
        printf("%s=%s\n", logic::kLocations[l].name, r.placement[l] >= 0 ? logic::kItems[r.placement[l]].name : "-");
    return 0;
}
