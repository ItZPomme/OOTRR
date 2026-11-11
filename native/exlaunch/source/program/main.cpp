#include "lib.hpp"
#include "rando/ingame.hpp"
#include "rando/menu_data.hpp"
#include "rando/logic_data.hpp"

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

    // seed aléatoire tirée à l'ouverture du menu (affichée dans la description de « Seed manuelle »,
    // utilisée au lancement si la seed manuelle est désactivée) ; 1-999999 pour pouvoir la ressaisir
    u32 g_menu_seed = 0;

    u32 RollSeed() {
        u64 tick;
        asm volatile("mrs %0, cntpct_el0" : "=r"(tick));
        return static_cast<u32>((tick ^ (tick >> 32) ^ (tick >> 17)) % ootrr::menu::kSeedMax) + 1;
    }

    void SetMenu(bool on) {
        if (g_menu != on) Log(on ? "OoTRR: menu du randomizer ouvert" : "OoTRR: menu du randomizer ferme");
        if (on && !g_menu) {
            g_trace = 4;
            g_menu_seed = RollSeed();
        }
        g_menu = on;
    }

    /* Texte trouvé (sortie de 0xa6afe0 : { const char* texte UTF-8 ; s32 longueur ; … }) : le repère
     * « ###### » est remplacé par la seed du menu, dans une copie (le texte du jeu reste intact). */
    struct MessageOut {
        const char* text;
        s32 length;
    };

    void SubstituteSeed(void* out) {
        auto* m = static_cast<MessageOut*>(out);
        if (!m->text || m->length <= 0 || !g_menu_seed) return;
        static char buffer[512];
        const char* src = m->text;
        size_t i = 0, n = 0;
        bool done = false;
        char digits[12];
        int count = 0;
        for (u32 v = g_menu_seed; v; v /= 10) digits[count++] = static_cast<char>('0' + v % 10);
        while (src[i] && n < sizeof(buffer) - 16) {
            if (!done && src[i] == '#' && src[i + 1] == '#' && src[i + 2] == '#' && src[i + 3] == '#' &&
                src[i + 4] == '#' && src[i + 5] == '#') {
                for (int k = count - 1; k >= 0; k--) buffer[n++] = digits[k];
                i += 6;
                done = true;
                continue;
            }
            buffer[n++] = src[i++];
        }
        if (!done) return;
        buffer[n] = 0;
        m->text = buffer;
        m->length += count - 6;  // chiffres ASCII : même écart en octets comme en caractères
    }

}

u64 ReadTick() {
    u64 value;
    asm volatile("mrs %0, cntpct_el0" : "=r"(value));
    return value;
}

bool g_trust_memory = false;
bool g_pending_start_items = false;  // objets de départ à donner une fois l'inventaire prêt  // seed de nouvelle partie pas encore visible dans GameData (écriture différée)

void LogMenuRead(const ootrr::ingame::MenuRead& r) {
    char buf[96] = "OoTRR: reglages lus ";
    size_t n = 20;
    buf[n++] = r.handle ? 'H' : '-';
    buf[n++] = static_cast<char>('0' + (r.read / 10) % 10);
    buf[n++] = static_cast<char>('0' + r.read % 10);
    buf[n++] = ' ';
    for (int i = 0; i < r.count && n < sizeof(buf) - 3; i++) {
        buf[n++] = static_cast<char>('0' + (r.values[i] % 10));
        buf[n++] = ',';
    }
    buf[n] = 0;
    Log(buf);
}

void GenerateSeed() {
    // seed aléatoire : celle affichée dans le menu (1-999999), qu'on peut ressaisir au clavier
    u32 seed = g_menu_seed ? g_menu_seed : RollSeed();
    bool manual = ootrr::ingame::ReadManualSeed(Main(), &seed);
    LogValue(manual ? "OoTRR: seed manuelle" : "OoTRR: seed aleatoire", seed);
    ootrr::ingame::MenuRead read;
    bool ok = ootrr::ingame::GenerateFromMenu(Main(), seed, &read);
    LogMenuRead(read);
    LogValue(ok ? "OoTRR: seed generee" : "OoTRR: echec de la generation, seed", seed);
    if (ok) {
        ootrr::ingame::WriteSavedSeed(Main(), static_cast<s32>(seed));
        g_trust_memory = true;
        LogValue("OoTRR: drapeaux de depart poses", static_cast<u64>(ootrr::ingame::ApplyStartFlags(Main())));
        g_pending_start_items = true;
    }
}

// partie chargée : régénère la seed enregistrée (et ses réglages) si ce n'est pas celle en mémoire
void EnsureSeedForCurrentGame() {
    s32 saved = ootrr::ingame::ReadSavedSeed(Main());
    if (g_trust_memory) {
        if (static_cast<u32>(saved) == ootrr::ingame::CurrentSeed()) g_trust_memory = false;
        return;
    }
    if (saved == 0) return;
    if (ootrr::ingame::Ready() && static_cast<u32>(saved) == ootrr::ingame::CurrentSeed()) return;
    ootrr::ingame::MenuRead read;
    bool ok = ootrr::ingame::GenerateFromMenu(Main(), static_cast<u32>(saved), &read);
    LogMenuRead(read);
    LogValue(ok ? "OoTRR: seed rechargee" : "OoTRR: echec de la regeneration, seed", static_cast<u32>(saved));
}

void OnSetBool(void* node, u32 hash) {
    bool value = (**reinterpret_cast<u8**>(static_cast<u8*>(node) + 0x40) & 1) != 0;
    if (hash == kMenuFlagHash) SetMenu(value);
    if (hash == ootrr::menu::kGenerateFlagHash && value) GenerateSeed();
}

HOOK_DEFINE_TRAMPOLINE(SetBoolNode) {
    static void Callback(void* node, u32 hash) {
        Orig(node, hash);
        OnSetBool(node, hash);
    }
};

HOOK_DEFINE_TRAMPOLINE(SetBoolNodeIndexed) {
    static void Callback(void* node, u32 hash, s32 index) {
        Orig(node, hash, index);
        OnSetBool(node, hash);
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

/* Jeton d'emplacement (OoTRR_Lnnnn) : l'objet donné par un cœur au sol porte le nom du jeton ; la
 * séquence « objet obtenu » cherche ses textes par ce nom (OoTRR_Lnnnn_GetCaption…). On les
 * redirige vers ceux de l'objet placé par la seed (<objet>_GetCaption…). Renvoie l'emplacement, -1 sinon. */
int TokenLocation(const char* text) {
    const char* prefix = "OoTRR_L";
    int k = 0;
    while (prefix[k] && text[k] == prefix[k]) k++;
    if (prefix[k]) return -1;
    int location = 0;
    for (int d = 0; d < 4; d++) {
        char c = text[k + d];
        if (c < '0' || c > '9') return -1;
        location = location * 10 + (c - '0');
    }
    return location;
}

int g_token_message_logs = 16;

/* Objet donné par un cœur au sol : les rubis « de coffre » (TBox_Rupee_*) n'ont ni texte « objet
 * obtenu » ni rôle au sol ; leur équivalent posé au sol (Obj_Rupee_*) en a (constaté : blocage). */
const char* GroundItem(const char* item) {
    const char* prefix = "TBox_Rupee_";
    int k = 0;
    while (prefix[k] && item[k] == prefix[k]) k++;
    if (prefix[k]) return item;
    static char buffer[64];
    size_t n = 0;
    for (const char* p = "Obj_Rupee_"; *p; p++) buffer[n++] = *p;
    for (const char* p = item + k; *p && n < sizeof(buffer) - 1; p++) buffer[n++] = *p;
    buffer[n] = 0;
    return buffer;
}

HOOK_DEFINE_TRAMPOLINE(FindMessage) {
    static u64 Callback(void* out, const char** file, const char** label, u64 extra) {
        if (label && *label) {
            int location = TokenLocation(*label);
            const char* item = location >= 0 ? ootrr::ingame::ItemFor(location) : nullptr;
            if (item) {
                static char name[160];
                const char* suffix = *label + 11;  // « _GetCaption »…
                auto build = [&](const char* base) {
                    size_t n = 0;
                    for (const char* p = base; *p && n < sizeof(name) - 1; p++) name[n++] = *p;
                    for (const char* p = suffix; *p && n < sizeof(name) - 1; p++) name[n++] = *p;
                    name[n] = 0;
                };
                build(GroundItem(item));
                const char* mine = name;
                u64 found = Orig(out, file, &mine, extra);
                if (!(found & 1)) {
                    // secours : texte du quart de cœur plutôt qu'un blocage
                    build("Obj_Heart_Piece");
                    mine = name;
                    found = Orig(out, file, &mine, extra);
                }
                if (g_token_message_logs > 0) {
                    g_token_message_logs--;
                    if (file && *file) Log(*file);
                    Log(*label);
                    Log(name);
                    LogValue("OoTRR: texte de jeton redirige, trouve", found);
                }
                return found;
            }
        }
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
            if (found & 1) {
                SubstituteSeed(out);
                return found;
            }
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

/* Placement pendant le jeu : le mod de fichiers remplace l'objet de chaque coffre mélangeable par un
 * jeton « OoTRR_Lnnnn » (nnnn = index de l'emplacement dans rando/logic_data.hpp) ; à l'initialisation
 * du composant « drop », on écrit l'objet placé par la seed (ou l'objet d'origine sans seed). */
namespace {
    constexpr const char* kTokenPrefix = "OoTRR_L";

    int TokenIndex(const char* name) {
        for (int i = 0; kTokenPrefix[i]; i++) if (name[i] != kTokenPrefix[i]) return -1;
        int n = 0;
        for (const char* p = name + 7; *p; p++) {
            if (*p < '0' || *p > '9') return -1;
            n = n * 10 + (*p - '0');
        }
        return n < ootrr::ingame::LocationCount() ? n : -1;
    }
}

/* Paramètres dynamiques d'un acteur placé (lus par l'initialisation du composant « drop ») :
 * *(*(infos + 0x40) + 0x270) -> objet, +0x10 -> table { u32 nombre de clés ; +0x08 const char** clés ;
 * +0x10 u32 nombre de valeurs ; +0x18 const char** valeurs }. Le tableau noir du coffre et son
 * porte-acteur (contenu créé à l'avance) lisent les mêmes valeurs : on remplace la valeur à la source. */
struct DynamicParams {
    u32 key_count;
    u32 pad0;
    const char** keys;
    u32 value_count;
    u32 pad1;
    const char** values;
};

DynamicParams* FindDynamicParams(u8* info) {
    if (!info) return nullptr;
    u8* placement = *reinterpret_cast<u8**>(info + 0x40);
    if (!placement) return nullptr;
    u8** holder = *reinterpret_cast<u8***>(placement + 0x270);
    if (!holder || !*holder) return nullptr;
    auto* params = *reinterpret_cast<DynamicParams**>(*holder + 0x10);
    if (reinterpret_cast<uintptr_t>(params) + 1 < 2) return nullptr; // nul ou -1 : pas de paramètres
    return params;
}

void ReplaceTokenAtSource(u8* info) {
    DynamicParams* params = FindDynamicParams(info);
    if (!params || !params->keys || !params->values) return;
    for (u32 i = 0; i < params->key_count && i < params->value_count; i++) {
        const char* key = params->keys[i];
        const char* value = params->values[i];
        if (!key || !value || !SameString(key, "Drop__DropActor")) continue;
        int index = TokenIndex(value);
        if (index < 0) return;
        EnsureSeedForCurrentGame();
        const char* real = ootrr::ingame::ItemFor(index);
        params->values[i] = real;
        // objet différent de l'original : retirer la scène de l'objet d'origine (event « drop ») et,
        // pour un coffre à contenu conditionnel, l'objet testé et son remplaçant (comme patch.chest_changes)
        if (!SameString(real, ootrr::ingame::VanillaItem(index))) {
            for (u32 k = 0; k < params->key_count && k < params->value_count; k++) {
                const char* other = params->keys[k];
                if (!other) continue;
                bool clear = (ootrr::ingame::IsDropEvent(index) && SameString(other, "GetEventName")) ||
                             (ootrr::ingame::IsConditional(index) &&
                              (SameString(other, "Drop__CheckActor") || SameString(other, "Drop__DropActor_Substitute")));
                // retirer le paramètre : renommer sa clé (une valeur vide empêche le coffre de s'ouvrir)
                if (clear) params->keys[k] = "OoTRR_Removed";
            }
        }
        char buf[96] = "OoTRR: emplacement ";
        size_t n = 19;
        for (const char* p = value; *p && n < 60; p++) buf[n++] = *p;
        buf[n++] = ' ';
        buf[n++] = '-';
        buf[n++] = ' ';
        for (const char* p = real; *p && n < sizeof(buf) - 1; p++) buf[n++] = *p;
        buf[n] = 0;
        Log(buf);
        return;
    }
}

/* Cartes et boussoles « au départ » : obtenir une carte = drapeau IsGetMap de la structure du donjon
 * + objet Item_Dungeon_Map dans l'inventaire (fonctions du nœud OneShotDungeonGetMap). L'objet du donjon
 * n'existe qu'une fois dedans : on les donne au chargement d'une salle de donjon, une fois par donjon. */
namespace {
    constexpr ptrdiff_t kDungeonOwnerPtr = 0x4c7e178;  // pointeur vers le pointeur du gestionnaire de scène
    constexpr ptrdiff_t kDungeonOwner = 0xb2af20;      // (gestionnaire) -> objet intermédiaire
    constexpr ptrdiff_t kCurrentDungeon = 0xb2afc0;    // (objet) -> donjon courant ou nul
    constexpr ptrdiff_t kDungeonGetMap = 0x3282fe0;    // (donjon, bool)
    constexpr ptrdiff_t kDungeonGetCompass = 0x3283060;

    void* g_dungeons_done[16];
    int g_dungeons_done_count = 0;

    void GiveDungeonItems() {
        if (!ootrr::ingame::Ready()) return;
        if (ootrr::ingame::SettingValue(ootrr::logic::SET_maps_compasses) != 1) return;  // start_with
        void* owner = **reinterpret_cast<void***>(Main() + kDungeonOwnerPtr);
        if (!owner) return;
        void* first = reinterpret_cast<void* (*)(void*)>(Main() + kDungeonOwner)(owner);
        if (!first) return;
        void* dungeon = reinterpret_cast<void* (*)(void*)>(Main() + kCurrentDungeon)(first);
        if (!dungeon) return;
        // donjon reconnu par sa structure GameData (poignée en +0x268, premier mot = structure) : l'objet
        // « donjon » est réutilisé d'une zone à l'autre (la forêt Kokiri en a un aussi)
        void* key = *reinterpret_cast<void**>(static_cast<u8*>(dungeon) + 0x268);
        if (!key) return;
        for (int i = 0; i < g_dungeons_done_count; i++)
            if (g_dungeons_done[i] == key) return;
        if (g_dungeons_done_count < 16) g_dungeons_done[g_dungeons_done_count++] = key;
        // diagnostic : IsGetMap de l'Arbre Mojo (posé à 1 au départ ; 0 = remis à zéro à l'entrée)
        LogValue("OoTRR: nouveau donjon, IsGetMap Arbre Mojo (+1)", static_cast<u64>(
            ootrr::ingame::ReadStructBool(Main(), 0x64e53a1f, 0x58aeb8fb) + 1));
        reinterpret_cast<void (*)(void*, bool)>(Main() + kDungeonGetMap)(dungeon, true);
        reinterpret_cast<void (*)(void*, bool)>(Main() + kDungeonGetCompass)(dungeon, true);
        Log("OoTRR: carte et boussole du donjon donnees");
    }
}

HOOK_DEFINE_TRAMPOLINE(InitDrop) {
    static void Callback(u8* component, u8* info) {
        ReplaceTokenAtSource(info);
        Orig(component, info);
        if (g_pending_start_items) {
            int given = ootrr::ingame::GiveStartItems(Main());
            if (given >= 0) {
                g_pending_start_items = false;
                LogValue("OoTRR: objets de depart donnes", static_cast<u64>(given));
            }
        }
        GiveDungeonItems();
    }
};

/* Porte du Temps ouverte : la quête DoorOfTime démarre à Step06 ; les scènes (ocarina des douves…)
 * la feraient reculer et la porte se refermerait. La fonction qui change l'étape d'une quête
 * (0x2cf54a0 : gestionnaire, hachage de la quête, hachage de l'étape, …) ignore alors toute étape
 * autre que Step06 / Complete. */
int g_challenge_logs = 20;

/* Ajout d'un objet à l'inventaire (0x110d570 : gestionnaire, nom, 0, nombre, raison, …). Les scènes
 * des boss (et le don de départ de la poche de Link) donnent la récompense d'origine par une action
 * d'événement (raison 7) : récompenses mélangées, on donne celle de la seed à la place. */
struct PouchName {
    const char* text;
    s32 capacity;
    s32 pad;
};
int g_pouch_logs = 12;

HOOK_DEFINE_TRAMPOLINE(PouchAdd) {
    static u64 Callback(void* manager, PouchName* name, s32 variant, s32 count, u32 reason, s32 a5, s32 a6,
                        bool is_get_event, u8 a8) {
        if (g_pouch_logs > 0 && name && name->text) {
            g_pouch_logs--;
            Log(name->text);
            LogValue("OoTRR: ajout a l'inventaire, raison", reason);
        }
        // jeton d'un cœur au sol (OoTRR_Lnnnn) ramassé : objet de la seed pour cet emplacement
        if (name && name->text) {
            const char* t = name->text;
            const char* prefix = "OoTRR_L";
            int k = 0;
            while (prefix[k] && t[k] == prefix[k]) k++;
            if (!prefix[k]) {
                int location = 0;
                bool ok = true;
                for (int d = 0; d < 4; d++) {
                    char c = t[k + d];
                    if (c < '0' || c > '9') ok = false;
                    else location = location * 10 + (c - '0');
                }
                const char* item = ok && !t[k + 4] ? ootrr::ingame::ItemFor(location) : nullptr;
                if (item) item = GroundItem(item);
                if (item) {
                    static char text[128];
                    size_t n = 0;
                    for (; item[n] && n < sizeof(text) - 1; n++) text[n] = item[n];
                    text[n] = 0;
                    static PouchName replaced;
                    replaced = {text, static_cast<s32>(sizeof(text)), 0};
                    Log(t);
                    Log(text);
                    Log("OoTRR: jeton de coeur remplace (jeton / objet)");
                    // les rubis ne passent pas par l'inventaire : valeur ajoutée à la bourse
                    if (s32 rupees = ootrr::ingame::RupeeValue(text)) {
                        LogValue("OoTRR: rubis ajoutes, nouveau total", static_cast<u64>(ootrr::ingame::AddRupees(Main(), rupees)));
                        return 1;
                    }
                    return Orig(manager, &replaced, variant, count, reason, a5, a6, is_get_event, a8);
                }
            }
        }
        if (name && name->text && reason == ootrr::ingame::kReasonEvent) {
            if (const char* reward = ootrr::ingame::RewardFor(name->text)) {
                static char text[128];
                size_t n = 0;
                for (; reward[n] && n < sizeof(text) - 1; n++) text[n] = reward[n];
                text[n] = 0;
                static PouchName replaced;
                replaced = {text, static_cast<s32>(sizeof(text)), 0};
                Log(name->text);
                Log(text);
                Log("OoTRR: recompense remplacee (avant / apres)");
                return Orig(manager, &replaced, variant, count, reason, a5, a6, is_get_event, a8);
            }
        }
        return Orig(manager, name, variant, count, reason, a5, a6, is_get_event, a8);
    }
};

HOOK_DEFINE_TRAMPOLINE(SetChallengeStep) {
    static u64 Callback(void* manager, u32 challenge, u32 step, u64 a3, u64 a4, u64 a5) {
        if (g_challenge_logs > 0) {
            g_challenge_logs--;
            LogValue("OoTRR: etape de quete (quete << 32 | etape)", (static_cast<u64>(challenge) << 32) | step);
        }
        bool door = challenge == ootrr::menu::kDoorChallengeHash || challenge == ootrr::menu::kDoorChallengePathHash;
        if (door && ootrr::ingame::Ready() && ootrr::ingame::SettingValue(ootrr::menu::kOpenDoorSetting)) {
            bool open = false;
            for (u32 s : ootrr::menu::kDoorOpenSteps) open = open || s == step;
            if (!open) {
                LogValue("OoTRR: recul de la Porte du Temps bloque, etape", step);
                return 0;
            }
        }
        return Orig(manager, challenge, step, a3, a4, a5);
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
    SetChallengeStep::InstallAtOffset(0x2cf54a0);
    PouchAdd::InstallAtOffset(ootrr::ingame::kPouchAdd);
    InitDrop::InstallAtOffset(kInitDrop);
    Log("OoTRR: module natif charge, crochets du menu installes");
}

extern "C" NORETURN void exl_exception_entry() {
    EXL_ABORT("Default exception handler called!");
}
