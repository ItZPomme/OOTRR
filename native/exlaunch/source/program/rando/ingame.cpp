#include "ingame.hpp"

#include "generator.hpp"
#include "logic_data.hpp"
#include "menu_data.hpp"

namespace ootrr::ingame {
namespace {

struct Handle {
    uint64_t a = 0;
    uint32_t b = 0;
    uint8_t c = 0;
    uint8_t pad[3] = {};
};

using GetHandleFn = bool (*)(void* manager, Handle* handle, uint32_t hash);
using GetEnumFn = bool (*)(void* manager, uint32_t* value, Handle* handle, int32_t member);
using GetBoolFn = bool (*)(void* manager, bool* value, Handle* handle, int32_t member);
using GetIntFn = bool (*)(void* manager, int32_t* value, uint32_t hash);
using SetIntNodeFn = void (*)(void* node, uint32_t hash);

void* Manager(std::uintptr_t main_base) { return **reinterpret_cast<void***>(main_base + kGameDataManagerPtr); }

SeedResult g_result;
bool g_ready = false;
uint32_t g_seed = 0;

}  // namespace

bool GenerateFromMenu(std::uintptr_t main_base, uint32_t seed, MenuRead* read) {
    void* manager = Manager(main_base);
    auto get_handle = reinterpret_cast<GetHandleFn>(main_base + kGetStructHandle);
    auto get_enum = reinterpret_cast<GetEnumFn>(main_base + kGetStructEnum);
    auto get_bool = reinterpret_cast<GetBoolFn>(main_base + kGetStructBool);

    Settings settings = Settings::Defaults();
    Handle handle;
    MenuRead local{};
    MenuRead& r = read ? *read : local;
    r = MenuRead{};
    r.handle = manager && get_handle(manager, &handle, menu::kStructHash);
    if (r.handle) {
        for (const menu::MenuSetting& m : menu::kMenuSettings) {
            if (m.is_bool) {
                bool value = false;
                if (get_bool(manager, &value, &handle, m.member)) {
                    settings.values[m.setting] = value ? 1 : 0;
                    r.read++;
                }
                continue;
            }
            uint32_t value = 0;
            if (!get_enum(manager, &value, &handle, m.member)) continue;
            for (int i = 0; i < m.count; i++)
                if (m.game_values[i] == value) {
                    settings.values[m.setting] = m.setting_values[i];
                    r.read++;
                }
        }
    }
    r.count = logic::kSettingCount < 16 ? logic::kSettingCount : 16;
    for (int i = 0; i < r.count; i++) r.values[i] = settings.values[i];
    g_seed = seed;
    g_ready = Generate(settings, seed, g_result);
    return g_ready;
}

int32_t ReadSavedSeed(std::uintptr_t main_base) {
    void* manager = Manager(main_base);
    int32_t value = 0;
    if (!manager || !reinterpret_cast<GetIntFn>(main_base + kGetInt)(manager, &value, menu::kSeedHash)) return 0;
    return value;
}

void WriteSavedSeed(std::uintptr_t main_base, int32_t seed) {
    // la fonction du nœud lit la valeur via un pointeur en nœud + 0x40 (2 bits de poids faible = étiquette)
    alignas(16) uint8_t node[0x50] = {};
    static int32_t value;
    value = seed;
    *reinterpret_cast<int32_t**>(node + 0x40) = &value;
    reinterpret_cast<SetIntNodeFn>(main_base + kSetIntNode)(node, menu::kSeedHash);
}

bool Ready() { return g_ready; }
uint32_t CurrentSeed() { return g_seed; }
int LocationCount() { return logic::kLocationCount; }

const char* VanillaItem(int location) { return logic::kItems[logic::kLocations[location].vanilla].name; }

const char* ItemFor(int location) {
    if (location < 0 || location >= logic::kLocationCount) return nullptr;
    if (g_ready && g_result.placement[location] >= 0) return logic::kItems[g_result.placement[location]].name;
    return VanillaItem(location);
}

bool IsDropEvent(int location) { return logic::kLocations[location].event == 2; }
bool IsConditional(int location) { return logic::kLocations[location].conditional; }

}  // namespace ootrr::ingame
