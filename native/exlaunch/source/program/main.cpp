#include "lib.hpp"
#include "rando/ingame.hpp"
#include "rando/menu_data.hpp"
#include "rando/logic_data.hpp"
#include "rando/ground_models.hpp"

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

    const char* const kOptionMessages = "LayoutMsg/SystemOption_00";
    const char* const kGameLayout = "SystemOption_00";
    const char* const kMenuLayout = "OoTRRMenu_00"; // copie sans les modèles amiibo / séparateur

    bool g_menu = false;
    bool g_loading_menu_table = false;
    bool g_menu_tables_ready = false;
    const char* g_menu_table_path = ootrr::menu::kPageTables[0];
    // une table par page, même forme que la table du jeu : u32 nombre, lignes en +8
    alignas(16) u8 g_menu_tables[ootrr::menu::kPageCount][0x40] = {};
    bool g_page_ready[ootrr::menu::kPageCount] = {};
    // page affichée : l'écran d'options s'ouvre une fois par page (mise en page chargée à chaque fois)
    int g_page = 0;
    // condition du pont lue à l'ouverture de la page (index du réglage bridge ; -1 = inconnue) : textes « <préfixe>B<n>_ »
    int g_bridge_mode = -1;
    int g_layouts = 0;

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
        bool mine = g_menu && g_page_ready[g_page];
        if (g_menu && g_trace > 0) {
            g_trace--;
            LogValue(mine ? "OoTRR: table remplacee, table du jeu" : "OoTRR: table du jeu gardee", reinterpret_cast<u64>(table));
        }
        return mine ? static_cast<void*>(g_menu_tables[g_page]) : table;
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
            g_page = 0;
            g_layouts = 0;
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

void WriteAllTokenPrices();  // prix des articles jetons (plus bas)

u64 ReadTick() {
    u64 value;
    asm volatile("mrs %0, cntpct_el0" : "=r"(value));
    return value;
}

bool g_trust_memory = false;
bool g_giving_start = false;  // objets de départ en cours (leurs chants passent)
int g_song_blocks = 0;
// chants placés dans un coffre (donnés sous leur vrai nom, pas par un jeton) : autorisés une fois chacun
const char* g_chest_songs[16] = {};

bool IsSongName(const char* t) {
    const char* prefix = "Item_Melody_";
    int k = 0;
    while (prefix[k] && t[k] == prefix[k]) k++;
    return !prefix[k];
}

void AllowChestSong(const char* song) {
    for (const char*& s : g_chest_songs)
        if (s && SameString(s, song)) return;
    for (const char*& s : g_chest_songs)
        if (!s) { s = song; return; }
}

bool TakeChestSong(const char* song) {
    for (const char*& s : g_chest_songs)
        if (s && SameString(s, song)) { s = nullptr; return true; }
    return false;
}
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
    // nouvelle partie : aucun article vendu (l'entier n'est pas remis à zéro par « Nouvelle partie »)
    if (ok) ootrr::ingame::WriteGameDataInt(Main(), ootrr::menu::kShopSoldHash, 0);
    if (ok) WriteAllTokenPrices();
    if (ok) {
        // point d'apparition lu par l'introduction (OpeningEvent : questions sur les dizaines puis les unités ;
        // une question ne gère que 16 cas)
        ootrr::ingame::WriteGameDataInt(Main(), ootrr::menu::kSpawnTensHash, ootrr::ingame::SpawnPoint() / 10);
        ootrr::ingame::WriteGameDataInt(Main(), ootrr::menu::kSpawnUnitsHash, ootrr::ingame::SpawnPoint() % 10);
        LogValue("OoTRR: point d'apparition", static_cast<u64>(ootrr::ingame::SpawnPoint()));
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
    if (ok) WriteAllTokenPrices();
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

int TokenLocation(const char* text);
void WriteTokenPrice(int location);
const char* GroundItem(const char* item);
int g_model_logs = 24;

/* Article jeton de boutique déjà acheté (OoTRR.ShopSold) : il reste affiché avec l'objet de la seed mais coûte
 * 999 rubis (ingame::SoldShopPrice) une fois la zone rechargée ; un rachat entre-temps est remboursé (PouchAdd).
 * Sans cela l'objet de la seed se rachetait à l'infini (constaté en jeu). « Coming Soon » / « Sold out » dans la
 * liste du marchand : plantage du chargement (pointeur nul en 0x612850, constaté 4 fois), voir ROADMAP. */
const char* ShopSoldItem(int location, const char* item) {
    (void)location;
    return item;
}

const char* PlacedItem(int location) {
    return ShopSoldItem(location, location >= 0 ? ootrr::ingame::ItemFor(location) : nullptr);
}

/* Modèle d'un jeton de cœur au sol : Component/ModelInfo/OoTRR_Lnnnn… (et AnimationParam) redirigé
 * vers le fichier de l'objet placé par la seed (copié dans l'archive du jeton sous son chemin). */
const char* TokenModelPath(const char* path) {
    const char* kinds[2] = {"Component/ModelInfo/", "Component/AnimationParam/"};
    for (int kind = 0; kind < 2; kind++) {
        const char* p = path;
        const char* q = kinds[kind];
        while (*q && *p == *q) { p++; q++; }
        if (*q) continue;
        int location = TokenLocation(p);
        const char* item = location >= 0 ? ootrr::ingame::ItemFor(location) : nullptr;
        if (!item) return nullptr;
        item = ShopSoldItem(location, item);
        // nom de l'objet tel quel d'abord : la table connaît « Obj_Token_Gold », que GroundItem change en
        // « Item_Token_Gold » (nom pour les textes) ; sans cela le jeton d'or gardait le modèle de sa base
        // (bouclier Mojo pour un article de boutique, constaté en jeu)
        for (const char* name : {item, GroundItem(item)})
            for (const auto& m : ootrr::ground::kGroundModels)
                if (SameString(m.item, name)) return kind == 0 ? m.model : m.anim;
        return nullptr;  // pas de modèle connu : celui du cœur
    }
    return nullptr;
}

/* Recherche d'un fichier dans une archive SARC (0x32ade0 : archive, chaîne* chemin -> numéro ; la
 * chaîne commence par son pointeur de texte). Les composants d'un acteur (ModelInfo…) sont lus ainsi
 * dans son archive : le modèle d'un jeton est remplacé ici par celui de l'objet placé. */
struct PathString {
    const char* text;
};

HOOK_DEFINE_TRAMPOLINE(ArchiveEntry) {
    static s64 Callback(void* archive, PathString* path) {
        // liste d'un marchand : variante selon le nombre d'articles mélangés (X_C<n>, ootrr.shops)
        if (path && path->text && path->text[0] == 'C' && ootrr::ingame::Ready()) {
            const char* prefix = "Component/ShopParam/";
            int k = 0;
            while (prefix[k] && path->text[k] == prefix[k]) k++;
            int count = ootrr::ingame::SettingValue(ootrr::logic::SET_shuffle_shops);
            if (!prefix[k] && count > 0) {
                static char variant[160];
                int n = 0, dot = -1;
                for (const char* p = path->text; *p && n < 150; p++) {
                    if (*p == '.' && dot < 0) {
                        dot = n;
                        variant[n++] = '_';
                        variant[n++] = 'C';
                        variant[n++] = static_cast<char>('0' + count);
                    }
                    variant[n++] = *p;
                }
                variant[n] = 0;
                PathString replaced{variant};
                s64 found = Orig(archive, &replaced);
                if (g_model_logs > 0) {
                    g_model_logs--;
                    Log(variant);
                    LogValue("OoTRR: liste du marchand, variante", static_cast<u64>(found));
                }
                if (found >= 0) return found;
            }
        }
        if (path && path->text && path->text[0] == 'C') {
            if (const char* other = TokenModelPath(path->text)) {
                if (g_model_logs > 0) {
                    g_model_logs--;
                    Log(path->text);
                    Log(other);
                    Log("OoTRR: modele de jeton redirige (avant / apres)");
                }
                PathString replaced{other};
                return Orig(archive, &replaced);
            }
        }
        return Orig(archive, path);
    }
};

HOOK_DEFINE_TRAMPOLINE(LoadResource) {
    static ResourceHandle Callback(void* manager, const char** path) {
        if (g_loading_menu_table && path == reinterpret_cast<const char**>(Main() + kOptionTablePath)) {
            path = &g_menu_table_path;
            Log("OoTRR: chargement de la table du menu");
        }
        if (path && *path) {
            const char* p = *path;
            bool token = false;
            for (const char* s = p; *s; s++)
                if (s[0] == 'O' && s[1] == 'o' && s[2] == 'T' && s[3] == 'R' && s[4] == 'R' && s[5] == '_' && s[6] == 'L') token = true;
            if (token) {
                static const char* redirected;
                const char* other = TokenModelPath(p);
                if (g_model_logs > 0) {
                    g_model_logs--;
                    Log(p);
                    if (other) Log(other);
                    Log(other ? "OoTRR: ressource de jeton redirigee (avant / apres)" : "OoTRR: ressource de jeton chargee");
                }
                if (other) {
                    redirected = other;
                    path = &redirected;
                }
            }
        }
        return Orig(manager, path);
    }
};

HOOK_DEFINE_TRAMPOLINE(LoadOptionTable) {
    static bool Callback(void* table, void* heap) {
        bool ok = Orig(table, heap);
        if (!g_menu_tables_ready) {
            g_menu_tables_ready = true;
            for (int p = 0; p < ootrr::menu::kPageCount; p++) {
                g_menu_table_path = ootrr::menu::kPageTables[p];
                g_loading_menu_table = true;
                bool mine = Orig(g_menu_tables[p], heap);
                g_loading_menu_table = false;
                g_page_ready[p] = mine && *reinterpret_cast<u32*>(g_menu_tables[p]) > 0;
                LogValue(g_page_ready[p] ? "OoTRR: table du menu chargee, page" : "OoTRR: table du menu introuvable, page",
                         static_cast<u64>(p + 1));
            }
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

int g_row_type_logs = 6;

HOOK_DEFINE_TRAMPOLINE(TableRowByType) {
    static void* Callback(void* table, s32 type) {
        void* picked = PickTable(table);
        // menu : plusieurs lignes du même type (nombre requis pour le pont) ; le jeu prend la première, même
        // cachée. On rend la première ligne visible du type : sans condition (+0x24 = 0) ou dont la condition
        // est le drapeau d'affichage de la condition du pont lue à l'ouverture de la page.
        if (g_menu && picked) {
            u32 count = *reinterpret_cast<u32*>(picked);
            u8* rows = *reinterpret_cast<u8**>(reinterpret_cast<u8*>(picked) + 8);
            for (u32 i = 0; rows && i < count && i < 64; i++) {
                u8* row = rows + i * 0x28;
                if (*reinterpret_cast<s32*>(row) != type) continue;
                u32 cond = *reinterpret_cast<u32*>(row + 0x24);
                bool visible = cond == 0;
                for (const ootrr::menu::BridgeRow& b : ootrr::menu::kBridgeRows)
                    if (cond == b.show_flag && b.bridge == g_bridge_mode) visible = true;
                if (g_row_type_logs > 0 && cond != 0) {
                    g_row_type_logs--;
                    LogValue("OoTRR: ligne par type, condition (type << 32 | condition)",
                             (static_cast<u64>(static_cast<u32>(type)) << 32) | cond);
                }
                if (visible) return row;
            }
        }
        return Orig(picked, type);
    }
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
    if (SameString(item, "Obj_Token_Gold")) return "Item_Token_Gold";  // ActorInfo.ActorName du jeton d'or
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

/* Recherche intérieure d'un message (0xa6b060 : gestionnaire, sortie, const char** fichier,
 * const char** étiquette ; 0 = trouvé). Les balises de nom (ex. Shop_SelectItemName dans un message de
 * vente) l'appellent sans passer par 0xa6afe0 : texte <jeton>_Name… redirigé vers celui de l'objet. */
int g_inner_logs = 12;
int g_button_logs = 12;

HOOK_DEFINE_TRAMPOLINE(FindMessageInner) {
    static u64 Callback(void* manager, void* out, const char** file, const char** label) {
        if (label && *label) {
            int location = TokenLocation(*label);
            const char* item = location >= 0 ? PlacedItem(location) : nullptr;
            if (item) {
                static char name[160];
                size_t n = 0;
                for (const char* p = GroundItem(item); *p && n < sizeof(name) - 1; p++) name[n++] = *p;
                for (const char* p = *label + 11; *p && n < sizeof(name) - 1; p++) name[n++] = *p;
                name[n] = 0;
                const char* mine = name;
                u64 result = Orig(manager, out, file, &mine);
                if (g_inner_logs > 0) {
                    g_inner_logs--;
                    Log(*label);
                    Log(name);
                    LogValue("OoTRR: nom de jeton redirige (recherche interieure), resultat", result);
                }
                if (result == 0) return result;
            }
        }
        // menu : textes des volets (ex. titre du bouton « Pa_AmiiboBtn_00-T_BtnTitle_00 ») cherchés ici sans
        // passer par 0xa6afe0 : même redirection par page « <préfixe><étiquette> »
        if (g_menu && label && *label && file && *file) {
            bool button = false;
            for (const char* p = *label; *p; p++)
                if (p[0] == 'B' && p[1] == 't' && p[2] == 'n' && p[3] == 'T') button = true;
            static char name[160];
            size_t n = 0;
            for (const char* p = ootrr::menu::kPagePrefixes[g_page]; *p && n < sizeof(name) - 1; p++) name[n++] = *p;
            for (const char* p = *label; *p && n < sizeof(name) - 1; p++) name[n++] = *p;
            name[n] = 0;
            const char* mine = name;
            u64 result = Orig(manager, out, file, &mine);
            if (button && g_button_logs > 0) {
                g_button_logs--;
                Log(*file);
                Log(name);
                LogValue("OoTRR: titre de bouton du menu (recherche interieure), resultat", result);
            }
            if (result == 0) return result;
        }
        return Orig(manager, out, file, label);
    }
};

/* Recherche d'une étiquette dans un fichier de messages déjà chargé (0xa6b250 : x0 = fichier, x1 = étiquette,
 * résultat de 0x18 octets via x8 : { texte, longueur, index… } ; texte nul = absent). Le rappel de texte des
 * mises en page (0x3780cd0) l'appelle directement avec « <volet>-<zone de texte> » : c'est ainsi que le
 * bouton de fin de page reçoit « Zelda Notes » (Pa_AmiiboBtn_00-T_BtnTitle_00 dans SystemOption_00), sans
 * passer par 0xa6afe0 / 0xa6b060. Pendant le menu, on essaie d'abord « <préfixe de page><étiquette> ». */
struct MessageSlice {
    const char* text;
    s32 length;
    u32 index;
    u64 extra;
    ~MessageSlice() {}
};
int g_pane_logs = 12;

HOOK_DEFINE_TRAMPOLINE(MessageInFile) {
    static MessageSlice Callback(void* file, const char* label) {
        if (g_menu && label && label[0] == 'P' && label[1] == 'a' && label[2] == '_') {
            char name[160];
            size_t n = 0;
            for (const char* p = ootrr::menu::kPagePrefixes[g_page]; *p && n < sizeof(name) - 1; p++) name[n++] = *p;
            for (const char* p = label; *p && n < sizeof(name) - 1; p++) name[n++] = *p;
            name[n] = 0;
            MessageSlice mine = Orig(file, name);
            if (g_pane_logs > 0) {
                g_pane_logs--;
                Log(name);
                LogValue("OoTRR: texte de volet du menu (0xa6b250), trouve", mine.text ? 1 : 0);
            }
            if (mine.text) return mine;
        }
        return Orig(file, label);
    }
};

HOOK_DEFINE_TRAMPOLINE(FindMessage) {
    static u64 Callback(void* out, const char** file, const char** label, u64 extra) {
        // message de vente d'une Peste Mojo (OoTRR_Scrub_<jeton>) -> celui de l'objet placé
        if (label && *label) {
            const char* scrub = "OoTRR_Scrub_";
            int k = 0;
            while (scrub[k] && (*label)[k] == scrub[k]) k++;
            int location = scrub[k] ? -1 : TokenLocation(*label + k);
            const char* item = location >= 0 ? ootrr::ingame::ItemFor(location) : nullptr;
            if (item) {
                static char name[160];
                size_t n = 0;
                for (const char* p = scrub; *p && n < sizeof(name) - 1; p++) name[n++] = *p;
                for (const char* p = GroundItem(item); *p && n < sizeof(name) - 1; p++) name[n++] = *p;
                name[n] = 0;
                const char* mine = name;
                u64 found = Orig(out, file, &mine, extra);
                if (g_token_message_logs > 0) {
                    g_token_message_logs--;
                    Log(*label);
                    Log(name);
                    LogValue("OoTRR: vente de Peste Mojo redirigee, trouve", found);
                }
                if (found & 1) return found;
            }
        }
        if (label && *label) {
            int location = TokenLocation(*label);
            const char* item = location >= 0 ? PlacedItem(location) : nullptr;
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
        if (g_menu && label && *label && g_button_logs > 0) {
            for (const char* p = *label; *p; p++)
                if (p[0] == 'B' && p[1] == 't' && p[2] == 'n' && p[3] == 'T') {
                    g_button_logs--;
                    if (file && *file) Log(*file);
                    Log(*label);
                    Log("OoTRR: titre de bouton du menu demande (0xa6afe0)");
                    break;
                }
        }
        if (g_menu && file && *file && label && *label && SameString(*file, kOptionMessages)) {
            // lignes du nombre requis pour le pont : affichées selon le mode (le jeu relit-il la condition ?)
            static u32 last_mode = 0;
            u32 mode = ootrr::ingame::UpdateBridgeRows(Main());
            if (mode != last_mode) {
                last_mode = mode;
                LogValue("OoTRR: mode du pont lu dans le menu (hachage)", mode);
            }
            if (g_bridge_mode >= 0 && g_bridge_mode < 10) {  // textes propres à la condition du pont
                char name[160];
                size_t n = 0;
                for (const char* p = ootrr::menu::kPagePrefixes[g_page]; *p && n < sizeof(name) - 4; p++) name[n++] = *p;
                name[n++] = 'B';
                name[n++] = static_cast<char>('0' + g_bridge_mode);
                name[n++] = '_';
                for (const char* p = *label; *p && n < sizeof(name) - 1; p++) name[n++] = *p;
                name[n] = 0;
                const char* mine = name;
                u64 found = Orig(out, file, &mine, extra);
                if (found & 1) return found;
            }
            char name[160];
            size_t n = 0;
            for (const char* p = ootrr::menu::kPagePrefixes[g_page]; *p && n < sizeof(name) - 1; p++) name[n++] = *p;
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
        if (g_menu && hash == kOptionDataHash) hash = ootrr::menu::kPageStructs[g_page];
        return Orig(manager, handle, hash);
    }
};

/* 11 arguments : x0..x7 puis trois sur la pile ; le nom de la mise en page est le 5e (x4). */
HOOK_DEFINE_TRAMPOLINE(LoadLayout) {
    static u64 Callback(void* layout, u64 a1, u64 a2, u64 a3, const char* name, u64 a5, u64 a6, u64 a7,
                        u64 a8, u64 a9, u64 a10) {
        if (g_menu && name && SameString(name, kGameLayout)) {
            name = kMenuLayout;
            // une ouverture de l'écran d'options par page
            g_page = g_layouts < ootrr::menu::kPageCount ? g_layouts : ootrr::menu::kPageCount - 1;
            g_layouts++;
            g_trace = 4;
            LogValue("OoTRR: mise en page du menu, page", static_cast<u64>(g_page + 1));
            u32 mode = ootrr::ingame::UpdateBridgeRows(Main());
            g_bridge_mode = -1;
            for (const ootrr::menu::BridgeRow& b : ootrr::menu::kBridgeRows)
                if (b.mode_value == mode) g_bridge_mode = b.bridge;
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
        if (ootrr::ingame::KeepsToken(index)) return;  // Skulltula : le jeton reste, objet donné au ramassage
        EnsureSeedForCurrentGame();
        const char* real = ootrr::ingame::ItemFor(index);
        // bombes sans sac : le coffre donnerait le sac de bombes (par un autre chemin que l'ajout à
        // l'inventaire, constaté en jeu) -> rubis bleu (5) ; ocarinas progressifs
        {
            s32 bomb_rupees = 0;
            const char* adjusted = ootrr::ingame::AdjustItem(Main(), real, &bomb_rupees);
            if (bomb_rupees) real = "TBox_Rupee_Blue";
            else if (adjusted) real = adjusted;
        }
        params->values[i] = real;
        if (IsSongName(real)) AllowChestSong(real);  // chant dans un coffre : son ajout ne sera pas bloqué
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
            g_giving_start = true;
            int given = ootrr::ingame::GiveStartItems(Main());
            g_giving_start = false;
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
        // chants mélangés : la leçon d'une scène (Dm_MelodyGet_*) ajoute aussi le chant d'origine (constaté : les
        // deux apparaissent dans la liste de l'ocarina). Les dons de la seed passent par des jetons (OoTRR_L) ou
        // les objets de départ ; tout autre ajout direct d'un chant est ignoré quand les chants sont mélangés.
        if (name && name->text && !g_giving_start && ootrr::ingame::Ready()
            && ootrr::ingame::SettingValue(ootrr::logic::SET_shuffle_songs) != 0) {
            const char* t = name->text;
            if (IsSongName(t) && TakeChestSong(t)) {
                Log(t);
                LogValue("OoTRR: chant d'un coffre accepte, raison", reason);
            } else if (IsSongName(t)) {
                Log(t);
                LogValue("OoTRR: chant d'origine ignore, raison", reason);
                LogValue("OoTRR: chant d'origine ignore (chants melanges), total", static_cast<u64>(++g_song_blocks));
                return 1;
            }
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
                const char* item = ok && !t[k + 4] ? PlacedItem(location) : nullptr;
                if (item) item = GroundItem(item);
                // article jeton de boutique : premier achat = objet de la seed, puis l'article coûte 999 rubis
                // (SoldShopPrice), plus que la plus grande bourse : il ne peut plus être racheté. La boutique garde le
                // prix lu à son chargement (constaté : rachat au prix d'origine) : un rachat avant rechargement de la
                // zone ne donne rien et le prix payé est rendu
                if (item && ootrr::ingame::IsShop(location) && ootrr::ingame::IsShopSold(Main(), location)) {
                    Log(t);
                    LogValue("OoTRR: article deja vendu, rien donne, rubis rendus, total",
                             static_cast<u64>(ootrr::ingame::AddRupees(Main(), ootrr::ingame::ShopPrice(location))));
                    return 1;
                }
                if (item && ootrr::ingame::IsShop(location) && !ootrr::ingame::IsShopSold(Main(), location)) {
                    LogValue("OoTRR: article de boutique vendu, masque", static_cast<u64>(ootrr::ingame::MarkShopSold(Main(), location)));
                    WriteTokenPrice(location);
                }
                if (item && ootrr::ingame::RecentOcarinaToken(location)) {
                    Log(t);
                    Log("OoTRR: jeton d'ocarina deja donne (douves : don direct puis scene), ignore");
                    return 1;
                }
                if (item) {
                    s32 bomb_rupees = 0;
                    if (const char* adjusted = ootrr::ingame::AdjustItem(Main(), item, &bomb_rupees)) item = adjusted;
                    if (bomb_rupees) {
                        LogValue("OoTRR: bombes sans sac -> rubis, nouveau total",
                                 static_cast<u64>(ootrr::ingame::AddRupees(Main(), bomb_rupees)));
                        return 1;
                    }
                }
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
                    bool heart = SameString(text, "Obj_Heart_Piece");
                    s32 before = heart ? ootrr::ingame::HeartPieces(Main()) : 0;
                    u64 result = Orig(manager, &replaced, variant, count, reason, a5, a6, is_get_event, a8);
                    LogValue("OoTRR: ajout du jeton, resultat", result);
                    if (SameString(text, "Obj_Heart_Container") && (result & 1))
                        LogValue("OoTRR: vie maximale (quarts)", static_cast<u64>(ootrr::ingame::AddMaxLife(Main(), 4)));
                    if (heart) {
                        s32 after = ootrr::ingame::HeartPieces(Main());
                        LogValue("OoTRR: quarts de coeur avant", static_cast<u64>(before));
                        LogValue("OoTRR: quarts de coeur apres", static_cast<u64>(after));
                        if (before >= 0 && after == before) {
                            // l'ajout n'a rien compté (vente d'un jeton) : on compte le quart nous-mêmes
                            ootrr::ingame::SetHeartPieces(Main(), before + 1);
                            LogValue("OoTRR: quart de coeur compte a la main, total", static_cast<u64>(before + 1));
                        }
                    }
                    return result;
                }
            }
        }
        // récompense d'origine donnée par une scène -> celle de la seed. Pas pendant les objets de départ : ils sont
        // déjà ceux de la seed (poche de Link : Item_Medal_Shadow, pris pour la récompense d'origine de Bongo Bongo,
        // devenait le médaillon placé chez Bongo Bongo, constaté en jeu : Forêt en plus de l'Ombre)
        if (name && name->text && reason == ootrr::ingame::kReasonEvent && !g_giving_start) {
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
        // objet donné sous son vrai nom (coffre, scène) : ocarinas progressifs, bombes sans sac
        if (name && name->text) {
            s32 bomb_rupees = 0;
            const char* adjusted = ootrr::ingame::AdjustItem(Main(), name->text, &bomb_rupees);
            if (bomb_rupees) {
                Log(name->text);
                LogValue("OoTRR: bombes sans sac -> rubis, nouveau total",
                         static_cast<u64>(ootrr::ingame::AddRupees(Main(), bomb_rupees)));
                return 1;
            }
            if (adjusted) {
                static char text[128];
                size_t n = 0;
                for (; adjusted[n] && n < sizeof(text) - 1; n++) text[n] = adjusted[n];
                text[n] = 0;
                static PouchName replaced;
                replaced = {text, static_cast<s32>(sizeof(text)), 0};
                Log(name->text);
                Log(text);
                Log("OoTRR: ocarina progressif (avant / apres)");
                return Orig(manager, &replaced, variant, count, reason, a5, a6, is_get_event, a8);
            }
        }
        return Orig(manager, name, variant, count, reason, a5, a6, is_get_event, a8);
    }
};

/* Prix des articles jetons : la boutique lit le prix d'achat dans la ligne PouchActorInfo de l'acteur
 * (RSDB, copie de celle du bouclier Mojo pour un jeton), pas dans PriceParam. 0x5a7c60 remplit une
 * ligne (ligne, nœud BYML) : +0 = nom (__RowId), +200 = BuyingPrice (s32). On note l'adresse de la
 * ligne de chaque jeton et on y écrit le prix des réglages (à la lecture, et quand la boutique charge). */
constexpr int kRowPriceOffset = 200;
// une ligne peut être lue plusieurs fois (copies) : jusqu'à 4 adresses par jeton
constexpr int kRowCopies = 4;
s32* g_token_price[1024][kRowCopies] = {};
int g_row_logs = 8;
int g_shop_row_logs = 24;

void WriteTokenPrice(int location) {
    if (location < 0 || location >= 1024) return;
    if (!ootrr::ingame::Ready() || !ootrr::ingame::IsShop(location)) return;
    for (s32* price : g_token_price[location])
        if (price) *price = ootrr::ingame::IsShopSold(Main(), location) ? ootrr::ingame::SoldShopPrice(location)
                                                                       : ootrr::ingame::ShopPrice(location);
}

// prix de tous les articles jetons : dès que la seed est prête, avant qu'une boutique ne charge
void WriteAllTokenPrices() {
    for (int location = 0; location < 1024 && location < ootrr::ingame::LocationCount(); location++)
        WriteTokenPrice(location);
    ootrr::ingame::WriteScrubPrices(Main());
}

HOOK_DEFINE_TRAMPOLINE(ParsePouchRow) {
    static void Callback(void* row, void* node) {
        Orig(row, node);
        const char* name = *reinterpret_cast<const char**>(row);
        int location = name ? TokenLocation(name) : -1;
        if (location >= 0 && location < 1024) {
            s32* price = reinterpret_cast<s32*>(static_cast<u8*>(row) + kRowPriceOffset);
            int slot = 0;
            while (slot < kRowCopies && g_token_price[location][slot] && g_token_price[location][slot] != price) slot++;
            if (slot < kRowCopies) g_token_price[location][slot] = price;
            if (ootrr::ingame::IsShop(location) && g_shop_row_logs > 0) {
                g_shop_row_logs--;
                Log(name);
                LogValue("OoTRR: ligne PouchActorInfo d'un article jeton, copie", static_cast<u64>(slot));
            }
            WriteTokenPrice(location);
        }
    }
};

/* Onglet Key Items (ImportantMenu, onglet 6 du menu : pierres et médaillons). Le jeu ne l'ouvre qu'une fois une
 * pierre spirituelle obtenue (constaté : ouvert avec la Pierre Kokiri, fermé « ??? » avec un médaillon seul) ; dans
 * le jeu d'origine, la première récompense est toujours une pierre. 0xa6ab50 (onglet, numéro, ouvert) écrit le
 * titre de l'onglet (« ??? » si fermé) : ouvert aussi dès qu'un médaillon est obtenu. */
constexpr u32 kRewardIsGet[] = {
    0x110b83ec, 0x8908d6ad, 0xeec383f5,                          // IsGet.Item_Stone_Forest / Fire / Water
    0x9026c187, 0xfcd8d653, 0x103a0dc7, 0xcf64e780, 0x12d63ac6, 0xe269df38,  // IsGet.Item_Medal_*
};
int g_tab_logs = 6;

HOOK_DEFINE_TRAMPOLINE(MenuTabTitle) {
    static void Callback(void* tab, u64 index, u64 open) {
        if ((index & 0xffffffff) == 6 && !(open & 1)) {
            bool any = false;
            for (u32 h : kRewardIsGet) any = any || ootrr::ingame::ReadFlag(Main(), h) == 1;
            if (any) {
                open = 1;
                if (g_tab_logs > 0) {
                    g_tab_logs--;
                    Log("OoTRR: onglet Key Items ouvert (recompense obtenue)");
                }
            }
        }
        Orig(tab, index, open);
    }
};

/* Contenu de l'onglet Key Items : l'écran (0x33dd6b0) fait la même boucle que l'onglet (0xa69220) sur la liste 4
 * (pierres) et n'affiche rien (« Unavailable right now ») si aucune n'est obtenue (constaté avec un médaillon seul).
 * 0x181160 (« objet obtenu ? ») répond oui pour ces deux appels-là (retours 0xa694dc et 0x33dd82c) dès qu'une
 * pierre ou un médaillon est obtenu. */
int g_keyitem_logs = 4;

HOOK_DEFINE_TRAMPOLINE(ItemObtained) {
    static u64 Callback(void* name) {
        u64 result = Orig(name);
        if (result & 1) return result;
        uintptr_t back = (reinterpret_cast<uintptr_t>(__builtin_return_address(0)) & 0xFFFFFFFFFFFFull) - Main();
        if (back != 0xa694dc && back != 0x33dd82c) return result;
        for (u32 h : kRewardIsGet)
            if (ootrr::ingame::ReadFlag(Main(), h) == 1) {
                if (g_keyitem_logs > 0) {
                    g_keyitem_logs--;
                    LogValue("OoTRR: Key Items ouvert (recompense obtenue), appel", back);
                }
                return 1;
            }
        return result;
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
    FindMessageInner::InstallAtOffset(0xa6b060);
    MessageInFile::InstallAtOffset(0xa6b250);
    GetStructHandle::InstallAtOffset(kGetStructHandle);
    LoadLayout::InstallAtOffset(kLoadLayout);
    SetChallengeStep::InstallAtOffset(0x2cf54a0);
    PouchAdd::InstallAtOffset(ootrr::ingame::kPouchAdd);
    ArchiveEntry::InstallAtOffset(0x32ade0);
    MenuTabTitle::InstallAtOffset(0xa6ab50);
    ItemObtained::InstallAtOffset(0x181160);
    InitDrop::InstallAtOffset(kInitDrop);
    ParsePouchRow::InstallAtOffset(0x5a7c60);
    Log("OoTRR: module natif charge, crochets du menu installes");
}

extern "C" NORETURN void exl_exception_entry() {
    EXL_ABORT("Default exception handler called!");
}
