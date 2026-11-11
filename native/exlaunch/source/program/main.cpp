#include "lib.hpp"

/* OoTRR : menu du randomizer dans l'écran d'options du jeu (voir native/README.md).
 *
 * La séquence de l'écran titre (Sequence/NormalTitle, modifiée par ootrr/ingame_menu.py) ouvre
 * l'écran d'options après « Nouvelle partie » et écrit le drapeau OoTRR.IsRandomizerMenu (vrai avant
 * notre menu, faux avant l'écran Options normal et au début de la partie). Tant qu'il est vrai :
 *  - l'écran lit notre table de lignes (UI/OptionSetTable/OoTRRMenu…) au lieu de celle du jeu ;
 *  - les textes cherchent d'abord l'étiquette « OoTRR_<étiquette> » ;
 *  - la poignée GameData « OptionData » devient « OoTRRMenu » : nos lignes lisent et écrivent nos
 *    réglages, jamais les options du joueur.
 *
 * Adresses : relatives au module main, version 2.0.0 (build id E0F3CCFA…). Ghidra = adresse + 0x100000. */

namespace {

    constexpr u32 kMenuFlagHash = 0xa7ce2e71;   // MurmurHash3("OoTRR.IsRandomizerMenu")
    constexpr u32 kOptionDataHash = 0x834d9d9e; // MurmurHash3("OptionData")
    constexpr u32 kMenuStructHash = 0x068ab00a; // MurmurHash3("OoTRRMenu")

    constexpr ptrdiff_t kSetBoolNode = 0x682b00;         // nœud SeqOneShotSetNonStructGameDataBool (nœud, hachage)
    constexpr ptrdiff_t kSetBoolNodeIndexed = 0x32e6910; // variante avec index (nœud, hachage, index)
    constexpr ptrdiff_t kLoadOptionTable = 0x339bc40;    // charge OptionSetTable dans une table (table, tas)
    constexpr ptrdiff_t kOptionTablePath = 0x4bdf2f8;    // const char* : chemin de OptionSetTable
    constexpr ptrdiff_t kLoadResource = 0xa57350;        // charge une ressource (gestionnaire, const char** chemin), résultat via x8
    constexpr ptrdiff_t kTableCount = 0x339c5a0;         // nombre de lignes visibles (table)
    constexpr ptrdiff_t kTableRow = 0x339c630;           // ligne visible n° i (table, i)
    constexpr ptrdiff_t kTableRowByType = 0x339c790;     // ligne d'un type d'option (table, type)
    constexpr ptrdiff_t kFindMessage = 0xa6afe0;         // texte (sortie, const char** fichier, const char** étiquette)
    constexpr ptrdiff_t kGetStructHandle = 0x9b3eb0;     // poignée de structure GameData (gestionnaire, poignée, hachage)
    constexpr ptrdiff_t kInitDrop = 0xbd1c00;           // composant « drop » : lit Drop__DropActor (composant, infos de création)
    constexpr ptrdiff_t kLoadLayout = 0x43a0e0;          // construit une mise en page ; 5e argument = nom ("SystemOption_00")

    const char* const kMenuTablePath = "UI/OptionSetTable/OoTRRMenu.game__ui__OptionSetTable.bgyml";
    const char* const kOptionMessages = "LayoutMsg/SystemOption_00";
    const char* const kPrefix = "OoTRR_";
    const char* const kGameLayout = "SystemOption_00";
    const char* const kMenuLayout = "OoTRRMenu_00"; // copie sans les modèles amiibo / séparateur

    bool g_menu = false;
    bool g_loading_menu_table = false;
    bool g_menu_table_ready = false;
    const char* g_menu_table_path = kMenuTablePath;
    alignas(16) u8 g_menu_table[0x40] = {}; // même forme que la table du jeu : u32 nombre, lignes en +8

    uintptr_t Main() { return exl::util::modules::GetTargetStart(); }

    void Log(const char* text) {
        size_t n = 0;
        while (text[n]) n++;
        svcOutputDebugString(text, n);
    }

    bool SameString(const char* a, const char* b) {
        while (*a && *a == *b) { a++; b++; }
        return *a == *b;
    }

    void LogValue(const char* text, u64 value) {
        char buf[96];
        size_t n = 0;
        for (const char* p = text; *p && n < 70; p++) buf[n++] = *p;
        buf[n++] = ' ';
        buf[n++] = '0';
        buf[n++] = 'x';
        for (int shift = 60; shift >= 0; shift -= 4) buf[n++] = "0123456789abcdef"[(value >> shift) & 0xF];
        buf[n] = 0;
        Log(buf);
    }

    int g_trace = 0; // nombre de traces restantes depuis l'ouverture du menu

    void* PickTable(void* table) {
        bool mine = g_menu && g_menu_table_ready;
        if (g_menu && g_trace > 0) {
            g_trace--;
            LogValue(mine ? "OoTRR: table remplacee, table du jeu" : "OoTRR: table du jeu gardee", reinterpret_cast<u64>(table));
        }
        return mine ? static_cast<void*>(g_menu_table) : table;
    }

    void SetMenu(bool on) {
        if (g_menu != on) Log(on ? "OoTRR: menu du randomizer ouvert" : "OoTRR: menu du randomizer ferme");
        if (on && !g_menu) g_trace = 4;
        g_menu = on;
    }

}

HOOK_DEFINE_TRAMPOLINE(SetBoolNode) {
    static void Callback(void* node, u32 hash) {
        Orig(node, hash);
        if (hash == kMenuFlagHash) SetMenu((**reinterpret_cast<u8**>(static_cast<u8*>(node) + 0x40) & 1) != 0);
    }
};

HOOK_DEFINE_TRAMPOLINE(SetBoolNodeIndexed) {
    static void Callback(void* node, u32 hash, s32 index) {
        Orig(node, hash, index);
        if (hash == kMenuFlagHash) SetMenu((**reinterpret_cast<u8**>(static_cast<u8*>(node) + 0x40) & 1) != 0);
    }
};

/* Le résultat (poignée de ressource) est renvoyé par valeur via x8 : un type non trivial force
 * le compilateur à utiliser la même convention, et « return Orig(...) » transmet x8 tel quel. */
struct ResourceHandle {
    void* ptr;
    ~ResourceHandle() {}
};

HOOK_DEFINE_TRAMPOLINE(LoadResource) {
    static ResourceHandle Callback(void* manager, const char** path) {
        if (g_loading_menu_table && path == reinterpret_cast<const char**>(Main() + kOptionTablePath)) {
            path = &g_menu_table_path;
            Log("OoTRR: chargement de la table du menu");
        }
        return Orig(manager, path);
    }
};

HOOK_DEFINE_TRAMPOLINE(LoadOptionTable) {
    static bool Callback(void* table, void* heap) {
        bool ok = Orig(table, heap);
        if (!g_menu_table_ready) {
            g_loading_menu_table = true;
            bool mine = Orig(g_menu_table, heap);
            g_loading_menu_table = false;
            g_menu_table_ready = mine && *reinterpret_cast<u32*>(g_menu_table) > 0;
            Log(g_menu_table_ready ? "OoTRR: table du menu chargee" : "OoTRR: table du menu introuvable");
        }
        return ok;
    }
};

HOOK_DEFINE_TRAMPOLINE(TableCount) {
    static s32 Callback(void* table) {
        s32 n = Orig(PickTable(table));
        if (g_menu && g_trace > 0) LogValue("OoTRR: nombre de lignes", static_cast<u64>(n));
        return n;
    }
};

HOOK_DEFINE_TRAMPOLINE(TableRow) {
    static void* Callback(void* table, u32 i) { return Orig(PickTable(table), i); }
};

HOOK_DEFINE_TRAMPOLINE(TableRowByType) {
    static void* Callback(void* table, s32 type) { return Orig(PickTable(table), type); }
};

HOOK_DEFINE_TRAMPOLINE(FindMessage) {
    static u64 Callback(void* out, const char** file, const char** label, u64 extra) {
        if (g_menu && file && *file && label && *label && SameString(*file, kOptionMessages)) {
            char name[160];
            size_t n = 0;
            for (const char* p = kPrefix; *p && n < sizeof(name) - 1; p++) name[n++] = *p;
            for (const char* p = *label; *p && n < sizeof(name) - 1; p++) name[n++] = *p;
            name[n] = 0;
            const char* mine = name;
            u64 found = Orig(out, file, &mine, extra);
            if (g_trace > 0) {
                g_trace--;
                Log(name);
                LogValue("OoTRR: message trouve", found);
            }
            if (found & 1) return found;
        }
        return Orig(out, file, label, extra);
    }
};

HOOK_DEFINE_TRAMPOLINE(GetStructHandle) {
    static u64 Callback(void* manager, void* handle, u32 hash) {
        if (g_menu && hash == kOptionDataHash) hash = kMenuStructHash;
        return Orig(manager, handle, hash);
    }
};

/* 11 arguments : x0..x7 puis trois sur la pile ; le nom de la mise en page est le 5e (x4). */
HOOK_DEFINE_TRAMPOLINE(LoadLayout) {
    static u64 Callback(void* layout, u64 a1, u64 a2, u64 a3, const char* name, u64 a5, u64 a6, u64 a7,
                        u64 a8, u64 a9, u64 a10) {
        if (g_menu && name && SameString(name, kGameLayout)) {
            name = kMenuLayout;
            Log("OoTRR: mise en page du menu");
        }
        return Orig(layout, a1, a2, a3, name, a5, a6, a7, a8, a9, a10);
    }
};

/* Placement pendant le jeu : le mod de fichiers remplace l'objet de chaque emplacement mélangé par un
 * jeton « OoTRR_Lnnnn » ; à l'initialisation du composant « drop », on écrit l'objet prévu.
 * Table de test fixe (coffres de Mido) en attendant le générateur. */
namespace {
    constexpr const char* kTokenPrefix = "OoTRR_L";
    const char* g_placement[] = {"Item_Hookshot", "Item_HoverBoot", "Item_Range_Bow", "Item_Boomerang"};
    constexpr int kPlacementCount = sizeof(g_placement) / sizeof(g_placement[0]);
    constexpr const char* kFallbackItem = "TBox_Rupee_Green";

    int TokenIndex(const char* name) {
        for (int i = 0; kTokenPrefix[i]; i++) if (name[i] != kTokenPrefix[i]) return -1;
        int n = 0;
        for (const char* p = name + 7; *p; p++) {
            if (*p < '0' || *p > '9') return -1;
            n = n * 10 + (*p - '0');
        }
        return n;
    }
}

HOOK_DEFINE_TRAMPOLINE(InitDrop) {
    static void Callback(u8* component, u8* info) {
        Orig(component, info);
        char* item = *reinterpret_cast<char**>(component + 0x48);
        int capacity = *reinterpret_cast<int*>(component + 0x50);
        if (!item || capacity <= 1) return;
        int index = TokenIndex(item);
        if (index < 0) return;
        const char* real = index < kPlacementCount ? g_placement[index] : kFallbackItem;
        char buf[96] = "OoTRR: emplacement ";
        size_t n = 19;
        for (const char* p = item; *p && n < 60; p++) buf[n++] = *p;
        buf[n++] = ' ';
        buf[n++] = '-';
        buf[n++] = ' ';
        int i = 0;
        for (; real[i] && i < capacity - 1; i++) item[i] = real[i];
        item[i] = 0;
        for (const char* p = real; *p && n < sizeof(buf) - 1; p++) buf[n++] = *p;
        buf[n] = 0;
        Log(buf);
    }
};

extern "C" void exl_main(void* x0, void* x1) {
    exl::hook::Initialize();
    SetBoolNode::InstallAtOffset(kSetBoolNode);
    SetBoolNodeIndexed::InstallAtOffset(kSetBoolNodeIndexed);
    LoadResource::InstallAtOffset(kLoadResource);
    LoadOptionTable::InstallAtOffset(kLoadOptionTable);
    TableCount::InstallAtOffset(kTableCount);
    TableRow::InstallAtOffset(kTableRow);
    TableRowByType::InstallAtOffset(kTableRowByType);
    FindMessage::InstallAtOffset(kFindMessage);
    GetStructHandle::InstallAtOffset(kGetStructHandle);
    LoadLayout::InstallAtOffset(kLoadLayout);
    InitDrop::InstallAtOffset(kInitDrop);
    Log("OoTRR: module natif charge, crochets du menu installes");
}

extern "C" NORETURN void exl_exception_entry() {
    EXL_ABORT("Default exception handler called!");
}
