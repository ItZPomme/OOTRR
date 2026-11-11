#pragma once
// Génération de la seed dans le jeu : lecture des réglages du menu (GameData OoTRRMenu),
// génération, et objet à donner pour chaque jeton d'emplacement.
#include <cstdint>

namespace ootrr::ingame {

// adresses relatives au module main (version 2.0.0)
constexpr std::intptr_t kGameDataManagerPtr = 0x4c7e180;  // pointeur vers le pointeur du gestionnaire GameData
constexpr std::intptr_t kGetStructHandle = 0x9b3eb0;      // (gestionnaire, poignée*, hachage) -> bool
constexpr std::intptr_t kGetStructEnum = 0x404760;        // (gestionnaire, u32* valeur, poignée*, membre) -> bool
constexpr std::intptr_t kGetStructBool = 0x179f70;        // (gestionnaire, bool* valeur, poignée*, membre) -> bool

// lit les réglages du menu et génère une seed ; renvoie false si la génération échoue
bool GenerateFromMenu(std::uintptr_t main_base, uint32_t seed);

bool Ready();
uint32_t CurrentSeed();

// objet à donner pour l'emplacement `location` (index de logic::kLocations) ; si aucune seed
// n'est prête, l'objet d'origine
const char* ItemFor(int location);
const char* VanillaItem(int location);
bool IsDropEvent(int location);
bool IsConditional(int location);
int LocationCount();

}  // namespace ootrr::ingame
