#include "ingame.hpp"

#include "generator.hpp"
#include "logic_data.hpp"
#include "keyboard.hpp"
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
using GetEnumFn = bool (*)(void* manager, uint32_t* value, Handle* handle, uint32_t member_hash);
using GetBoolFn = bool (*)(void* manager, bool* value, Handle* handle, uint32_t member_hash);
using GetIntFn = bool (*)(void* manager, int32_t* value, uint32_t hash);
using SetIntNodeFn = void (*)(void* node, uint32_t hash);
using SetBoolNodeFn = void (*)(void* node, uint32_t hash);
using SetEnumFn = void (*)(void* manager, uint32_t value, uint32_t hash);
// nom passé comme une chaîne du jeu : { char* texte ; s32 capacité }
struct GameString {
    const char* text;
    int32_t capacity;
    int32_t pad;
};
using PouchAddFn = uint64_t (*)(void* manager, GameString* name, int32_t variant, int32_t count, uint32_t reason,
                                int32_t a5, int32_t a6, bool is_get_event, uint8_t a8);
using PouchNotifyFn = void (*)(void* ui, GameString* name, bool added, uint32_t reason);
using SetStructBoolFn = void (*)(void* manager, bool value, Handle* handle, uint32_t member_hash);

void* Manager(std::uintptr_t main_base) { return **reinterpret_cast<void***>(main_base + kGameDataManagerPtr); }

SeedResult g_result;
Settings g_settings;
bool g_ready = false;
uint32_t g_seed = 0;

}  // namespace

/* Seed du générateur = seed affichée mélangée aux réglages (FNV-1a 64 bits) : une même seed donne
 * des placements différents selon les réglages, et reste reproductible (mêmes seed + réglages ->
 * même partie, y compris au chargement). Le générateur lui-même (identique à Python) ne change pas. */
uint64_t MixSettings(uint32_t seed, const Settings& settings) {
    uint64_t h = 0xcbf29ce484222325ull;
    auto mix = [&](uint32_t v) {
        for (int i = 0; i < 4; i++) {
            h ^= (v >> (8 * i)) & 0xff;
            h *= 0x100000001b3ull;
        }
    };
    mix(seed);
    for (int i = 0; i < logic::kSettingCount; i++) mix(static_cast<uint32_t>(settings.values[i]));
    return h & 0x7fffffffffffffffull;
}

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
    for (const menu::FixedSetting& f : menu::kFixedSettings) settings.values[f.setting] = f.value;
    for (const menu::BridgeCount& b : menu::kBridgeCounts)
        if (settings.values[menu::kBridgeSetting] == b.bridge) settings.values[menu::kBridgeCountSetting] = b.count;
    r.count = logic::kSettingCount < 16 ? logic::kSettingCount : 16;
    for (int i = 0; i < r.count; i++) r.values[i] = settings.values[i];
    g_seed = seed;
    g_settings = settings;
    g_ready = Generate(settings, MixSettings(seed, settings), g_result);
    return g_ready;
}

bool ReadManualSeed(std::uintptr_t main_base, uint32_t* seed) {
    void* manager = Manager(main_base);
    if (!manager) return false;
    Handle handle;
    if (!reinterpret_cast<GetHandleFn>(main_base + kGetStructHandle)(manager, &handle, menu::kStructHash)) return false;
    bool manual = false;
    if (!reinterpret_cast<GetBoolFn>(main_base + kGetStructBool)(manager, &manual, &handle, menu::kSeedManualMember) ||
        !manual)
        return false;
    uint32_t value = 0;
    if (!keyboard::AskSeed(&value)) return false;  // annulé : seed aléatoire
    *seed = value ? value : 1;  // 0 = « pas de seed » dans la sauvegarde
    return true;
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

namespace {
constexpr uint32_t kCurrentRupeeHash = 0xa77921d7;  // PlayerStatus.CurrentRupee

bool StartsWith(const char* text, const char* prefix) {
    while (*prefix && *text == *prefix) { text++; prefix++; }
    return !*prefix;
}
}  // namespace

int32_t RupeeValue(const char* item) {
    const char* rest = nullptr;
    if (StartsWith(item, "Obj_Rupee_")) rest = item + 10;
    else if (StartsWith(item, "TBox_Rupee_")) rest = item + 11;
    if (!rest) return 0;
    struct Kind { const char* name; int32_t value; };
    static const Kind kinds[] = {{"Green", 1}, {"Blue", 5}, {"Red", 20}, {"Purple", 50}, {"Gold", 200}};
    for (const Kind& k : kinds) {
        const char* a = rest;
        const char* b = k.name;
        while (*a && *a == *b) { a++; b++; }
        if (!*a && !*b) return k.value;
    }
    return 0;
}

int32_t AddRupees(std::uintptr_t main_base, int32_t amount) {
    void* manager = Manager(main_base);
    int32_t current = 0;
    if (!manager || !reinterpret_cast<GetIntFn>(main_base + kGetInt)(manager, &current, kCurrentRupeeHash)) return -1;
    alignas(16) uint8_t node[0x50] = {};
    static int32_t value;
    value = current + amount;
    *reinterpret_cast<int32_t**>(node + 0x40) = &value;
    reinterpret_cast<SetIntNodeFn>(main_base + kSetIntNode)(node, kCurrentRupeeHash);
    return value;
}

namespace {
constexpr uint32_t kHeartPieceStockHash = 0x51ec97b3;  // PouchData.Obj_Heart_Piece.StockNum
}  // namespace

int32_t HeartPieces(std::uintptr_t main_base) {
    void* manager = Manager(main_base);
    int32_t value = 0;
    if (!manager || !reinterpret_cast<GetIntFn>(main_base + kGetInt)(manager, &value, kHeartPieceStockHash)) return -1;
    return value;
}

void SetHeartPieces(std::uintptr_t main_base, int32_t count) {
    alignas(16) uint8_t node[0x50] = {};
    static int32_t value;
    value = count;
    *reinterpret_cast<int32_t**>(node + 0x40) = &value;
    reinterpret_cast<SetIntNodeFn>(main_base + kSetIntNode)(node, kHeartPieceStockHash);
}

int ApplyStartFlags(std::uintptr_t main_base) {
    auto set_bool = reinterpret_cast<SetBoolNodeFn>(main_base + kSetBoolNode);
    auto set_struct_bool = reinterpret_cast<SetStructBoolFn>(main_base + kSetStructBool);
    auto get_handle = reinterpret_cast<GetHandleFn>(main_base + kGetStructHandle);
    void* manager = Manager(main_base);
    int count = 0;
    for (const menu::StartFlag& f : menu::kStartFlags) {
        if (g_settings.values[f.setting] != f.value) continue;
        if (f.structure) {
            // membre de structure : l'écriture « non structure » ne le trouve pas
            Handle handle;
            if (manager && get_handle(manager, &handle, f.structure)) {
                set_struct_bool(manager, f.flag_value, &handle, f.member);
                count++;
            }
            continue;
        }
        // la fonction du nœud lit la valeur via un pointeur en nœud + 0x40
        alignas(16) uint8_t node[0x50] = {};
        static uint8_t value;
        value = f.flag_value ? 1 : 0;
        *reinterpret_cast<uint8_t**>(node + 0x40) = &value;
        set_bool(node, f.flag);
        count++;
    }
    auto set_enum = reinterpret_cast<SetEnumFn>(main_base + kSetEnum);
    for (const menu::StartEnum& e : menu::kStartEnums) {
        if (e.setting < 0 || g_settings.values[e.setting] != e.value || !manager) continue;
        set_enum(manager, e.enum_value, e.flag);
        count++;
    }
    return count;
}

int GiveStartItems(std::uintptr_t main_base) {
    void* manager = **reinterpret_cast<void***>(main_base + kPouchManagerPtr);
    if (!manager) return -1;
    void* ui = *reinterpret_cast<void**>(main_base + kPouchNotifyPtr);
    auto add = reinterpret_cast<PouchAddFn>(main_base + kPouchAdd);
    auto notify = reinterpret_cast<PouchNotifyFn>(main_base + kPouchNotify);
    // mêmes lieux que World._start_location_names (Porte du Temps ouverte ou Zelda enfant passée)
    const int32_t* list = nullptr;
    int count = 0;
    if (g_settings.values[logic::SET_open_door_of_time]) {
        list = logic::kOpenDoorStart;
        count = sizeof(logic::kOpenDoorStart) / sizeof(logic::kOpenDoorStart[0]);
    } else if (g_settings.values[logic::SET_skip_child_zelda]) {
        list = logic::kSkipChildZelda;
        count = sizeof(logic::kSkipChildZelda) / sizeof(logic::kSkipChildZelda[0]);
    }
    for (int i = 0; i < count; i++) {
        static char text[128];
        const char* name = ItemFor(list[i]);
        int n = 0;
        for (; name[n] && n < 127; n++) text[n] = name[n];
        text[n] = 0;
        GameString s{text, 128, 0};
        uint64_t added = add(manager, &s, 0, 1, kReasonEvent, 0, 0, false, 0);
        if (ui) notify(ui, &s, (added & 1) != 0, kReasonEvent);
    }
    return count;
}

bool Ready() { return g_ready; }
int32_t SettingValue(int setting) { return g_settings.values[setting]; }

int ReadStructBool(std::uintptr_t main_base, uint32_t structure, uint32_t member) {
    void* manager = Manager(main_base);
    Handle handle;
    bool value = false;
    if (!manager || !reinterpret_cast<GetHandleFn>(main_base + kGetStructHandle)(manager, &handle, structure)) return -1;
    if (!reinterpret_cast<GetBoolFn>(main_base + kGetStructBool)(manager, &value, &handle, member)) return -1;
    return value ? 1 : 0;
}
uint32_t CurrentSeed() { return g_seed; }
int LocationCount() { return logic::kLocationCount; }

const char* VanillaItem(int location) { return logic::kItems[logic::kLocations[location].vanilla].name; }

namespace {
bool SameText(const char* a, const char* b) {
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}
}  // namespace

const char* RewardFor(const char* name) {
    if (!g_ready || !name || g_settings.values[logic::SET_shuffle_rewards] != logic::kRewardsShuffled) return nullptr;
    // chaque récompense d'origine appartient à un seul lieu (boss, ou poche de Link pour le médaillon
    // de lumière) : le lieu est retrouvé par son objet d'origine
    for (int i = 0; i < logic::kLocationCount; i++) {
        if (logic::kLocations[i].kind != logic::kKindReward || !SameText(VanillaItem(i), name)) continue;
        const char* placed = ItemFor(i);
        return placed && !SameText(placed, name) ? placed : nullptr;
    }
    return nullptr;
}

const char* ItemFor(int location) {
    if (location < 0 || location >= logic::kLocationCount) return nullptr;
    if (g_ready && g_result.placement[location] >= 0) return logic::kItems[g_result.placement[location]].name;
    return VanillaItem(location);
}

bool IsDropEvent(int location) { return logic::kLocations[location].event == 2; }
bool IsConditional(int location) { return logic::kLocations[location].conditional; }

}  // namespace ootrr::ingame
