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

SeedResult g_result;
bool g_ready = false;
uint32_t g_seed = 0;

}  // namespace

bool GenerateFromMenu(std::uintptr_t main_base, uint32_t seed) {
    void* manager = **reinterpret_cast<void***>(main_base + kGameDataManagerPtr);
    auto get_handle = reinterpret_cast<GetHandleFn>(main_base + kGetStructHandle);
    auto get_enum = reinterpret_cast<GetEnumFn>(main_base + kGetStructEnum);
    auto get_bool = reinterpret_cast<GetBoolFn>(main_base + kGetStructBool);

    Settings settings = Settings::Defaults();
    Handle handle;
    if (manager && get_handle(manager, &handle, menu::kStructHash)) {
        for (const menu::MenuSetting& m : menu::kMenuSettings) {
            if (m.is_bool) {
                bool value = false;
                if (get_bool(manager, &value, &handle, m.member)) settings.values[m.setting] = value ? 1 : 0;
                continue;
            }
            uint32_t value = 0;
            if (!get_enum(manager, &value, &handle, m.member)) continue;
            for (int i = 0; i < m.count; i++)
                if (m.game_values[i] == value) settings.values[m.setting] = m.setting_values[i];
        }
    }
    g_seed = seed;
    g_ready = Generate(settings, seed, g_result);
    return g_ready;
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
