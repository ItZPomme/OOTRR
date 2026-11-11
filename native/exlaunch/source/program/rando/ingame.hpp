#pragma once
// Génération de la seed dans le jeu : lecture des réglages du menu (GameData OoTRRMenu),
// génération, et objet à donner pour chaque jeton d'emplacement.
#include <cstdint>

namespace ootrr::ingame {

// adresses relatives au module main (version 2.0.0)
constexpr std::intptr_t kGameDataManagerPtr = 0x4c7e180;  // pointeur vers le pointeur du gestionnaire GameData
constexpr std::intptr_t kGetStructHandle = 0x9b3eb0;      // (gestionnaire, poignée*, hachage) -> bool
constexpr std::intptr_t kGetStructEnum = 0x404760;        // (gestionnaire, u32* valeur, poignée*, hachage du membre) -> bool
constexpr std::intptr_t kGetStructBool = 0x179f70;        // (gestionnaire, bool* valeur, poignée*, hachage du membre) -> bool
constexpr std::intptr_t kGetInt = 0x163d20;               // (gestionnaire, s32* valeur, hachage) -> bool
constexpr std::intptr_t kSetIntNode = 0xc25ce0;           // nœud SeqOneShotSetNonStructGameDataInt (nœud, hachage)
constexpr std::intptr_t kSetBoolNode = 0x682b00;          // nœud SeqOneShotSetNonStructGameDataBool (nœud, hachage)
// ajout d'un objet (fonctions du nœud OneShotAddOrRemovePouchContent) :
constexpr std::intptr_t kPouchAdd = 0x110d570;            // (gestionnaire, nom*, 0, nombre, raison, 0, 0, scène, 0) -> bool
constexpr std::intptr_t kPouchManagerPtr = 0x4c7e0d0;     // pointeur vers le pointeur du gestionnaire
constexpr std::intptr_t kPouchNotify = 0x110d0b0;         // (interface, nom*, ajouté, raison) : objet « nouveau »
constexpr std::intptr_t kPouchNotifyPtr = 0x4e6b718;      // pointeur vers l'interface d'inventaire
constexpr uint32_t kReasonEvent = 7;                      // PickUp 0, Use 1, … Event 7
constexpr std::intptr_t kSetEnum = 0x3e0980;               // (gestionnaire, valeur, hachage)
constexpr std::intptr_t kSetStructBool = 0x608a10;        // (gestionnaire, valeur, poignée*, hachage du membre)

// résultat de la lecture des réglages du menu (pour le journal)
struct MenuRead {
    bool handle;   // poignée de la structure OoTRRMenu obtenue
    int read;      // réglages lus
    int32_t values[16];
    int count;
};

// lit les réglages du menu et génère une seed ; renvoie false si la génération échoue
bool GenerateFromMenu(std::uintptr_t main_base, uint32_t seed, MenuRead* read = nullptr);

// seed enregistrée dans la partie (GameData OoTRR.Seed) ; 0 = aucune
int32_t ReadSavedSeed(std::uintptr_t main_base);

// seed manuelle du menu (ligne « Seed manuelle ») : clavier virtuel ; vrai et *seed rempli si saisie
bool ReadManualSeed(std::uintptr_t main_base, uint32_t* seed);
void WriteSavedSeed(std::uintptr_t main_base, int32_t seed);
// entier GameData (non structuré) : écrit via le nœud SeqOneShotSetNonStructGameDataInt
void WriteGameDataInt(std::uintptr_t main_base, uint32_t hash, int32_t value);
// Peste Mojo : prix / 5 dans leur entier GameData (le script de vente choisit la vente à ce prix)
void WriteScrubPrices(std::uintptr_t main_base);

// rubis (Obj_Rupee_* / TBox_Rupee_*) : valeur en rubis, 0 si ce n'est pas un rubis
int32_t RupeeValue(const char* item);
// ajoute des rubis à la bourse (GameData PlayerStatus.CurrentRupee) ; renvoie le nouveau total, -1 si illisible
int32_t AddRupees(std::uintptr_t main_base, int32_t amount);
// nombre de quarts de cœur (GameData PouchData.Obj_Heart_Piece.StockNum) ; -1 si illisible
int32_t HeartPieces(std::uintptr_t main_base);
void SetHeartPieces(std::uintptr_t main_base, int32_t value);

// drapeaux de départ selon les réglages de la dernière génération (nouvelle partie) ; renvoie leur nombre
int ApplyStartFlags(std::uintptr_t main_base);

// objets donnés au départ selon les réglages (Zelda enfant / Porte du Temps : lettre et berceuse) ;
// renvoie leur nombre, -1 si l'inventaire n'est pas prêt
int GiveStartItems(std::uintptr_t main_base);

bool Ready();
uint32_t CurrentSeed();
// valeur d'un réglage de la dernière génération (logic::SettingId)
int32_t SettingValue(int setting);
// diagnostic : booléen d'un membre de structure GameData (-1 = illisible)
int ReadStructBool(std::uintptr_t main_base, uint32_t structure, uint32_t member);

// objet à donner pour l'emplacement `location` (index de logic::kLocations) ; si aucune seed
// n'est prête, l'objet d'origine
const char* ItemFor(int location);
const char* VanillaItem(int location);
// récompenses mélangées : objet à donner à la place de la récompense d'origine `name` (donnée par
// la scène d'un boss, ou au départ pour la poche de Link) ; nullptr si rien ne change
const char* RewardFor(const char* name);
bool IsDropEvent(int location);
bool IsConditional(int location);
// emplacement dont le jeton est un objet ramassable gardé tel quel (Skulltula d'or) : pas de
// remplacement à la source, l'objet est donné au ramassage
bool KeepsToken(int location);
int LocationCount();
// article de boutique (rang > 0)
bool IsShop(int location);
// prix d'un article de boutique mélangé (réglage shop_prices ; même calcul que world.shop_price)
int32_t ShopPrice(int location);

}  // namespace ootrr::ingame
