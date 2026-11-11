#pragma once
#include <cstdint>

namespace ootrr::keyboard {

// Ouvre le clavier virtuel de la console (pavé numérique) pour saisir une seed.
// Vrai et *seed rempli si un nombre a été saisi ; faux si le joueur annule ou si le texte est vide.
bool AskSeed(uint32_t* seed);

}  // namespace ootrr::keyboard
