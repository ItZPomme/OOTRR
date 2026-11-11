/* Clavier virtuel : bibliothèque nn::swkbd du module sdk du jeu (le jeu lui-même ne s'en sert pas).
 * Les fonctions sont importées par leur nom (rtld les résout dans sdk au chargement).
 *
 * Disposition relevée dans sdk (version de la mise à jour 131072) :
 * - KeyboardConfig : 0x518 octets. +0x000 mode (u32 : 1 = pavé numérique, 2 = clavier complet),
 *   +0x3ac longueur maximale (s32), +0x3b0 longueur minimale (s32). MakePreset remplit le reste.
 * - ShowKeyboardArg : KeyboardConfig puis +0x518 tampon de travail, +0x520 sa taille (0x1000 octets
 *   sans dictionnaire, aligné sur 0x1000), +0x528… autres tampons facultatifs (laissés à zéro).
 * - String : { char16_t* texte ; size_t taille } ; taille = exactement GetRequiredStringBufferSize (0x7d4) :
 *   ReadCloseResultAndString lit ce nombre d'octets dans la réponse ; plus grand, la lecture échoue et
 *   le SDK arrête le jeu (erreur 2128-0503, constaté en jeu).
 * - ShowKeyboard renvoie 0 si le texte est validé, 0x29f si le joueur annule. */
#include "keyboard.hpp"

#include <cstddef>

namespace nn::swkbd {
struct KeyboardConfig;
struct ShowKeyboardArg;
struct String {
    char16_t* text;
    std::size_t size;
};
enum Preset : int { Preset_Default = 0 };

void MakePreset(KeyboardConfig* config, Preset preset);
std::size_t GetRequiredWorkBufferSize(bool use_dictionary);
std::size_t GetRequiredStringBufferSize();
void SetHeaderTextUtf8(KeyboardConfig* config, const char* text);
void SetGuideTextUtf8(KeyboardConfig* config, const char* text);
uint32_t ShowKeyboard(String* out, const ShowKeyboardArg& arg);
}  // namespace nn::swkbd

namespace ootrr::keyboard {
namespace {

constexpr std::size_t kConfigSize = 0x518;
constexpr std::size_t kArgSize = 0x600;  // au-delà des champs lus par ShowKeyboard (0x548)
constexpr std::size_t kWorkSize = 0x1000;
constexpr std::size_t kStringSize = 0x800;
constexpr uint32_t kModeNumeric = 1;
constexpr int32_t kMaxDigits = 9;  // la seed tient dans 32 bits

alignas(0x1000) uint8_t g_work[kWorkSize];
alignas(16) uint8_t g_arg[kArgSize];
alignas(16) char16_t g_text[kStringSize / sizeof(char16_t)];

template <typename T>
T& At(std::size_t offset) {
    return *reinterpret_cast<T*>(g_arg + offset);
}

}  // namespace

bool AskSeed(uint32_t* seed) {
    if (nn::swkbd::GetRequiredWorkBufferSize(false) > kWorkSize ||
        nn::swkbd::GetRequiredStringBufferSize() > kStringSize)
        return false;
    for (auto& b : g_arg) b = 0;
    for (auto& c : g_text) c = 0;
    auto* config = reinterpret_cast<nn::swkbd::KeyboardConfig*>(g_arg);
    nn::swkbd::MakePreset(config, nn::swkbd::Preset_Default);
    At<uint32_t>(0x000) = kModeNumeric;
    At<int32_t>(0x3ac) = kMaxDigits;
    At<int32_t>(0x3b0) = 1;
    nn::swkbd::SetHeaderTextUtf8(config, "Seed");
    nn::swkbd::SetGuideTextUtf8(config, "Seed du randomizer / Randomizer seed");
    At<void*>(kConfigSize) = g_work;
    At<std::size_t>(kConfigSize + 8) = kWorkSize;

    // taille exacte : la réponse est lue d'un bloc de cette taille (au-delà, le SDK arrête le jeu)
    nn::swkbd::String out{g_text, nn::swkbd::GetRequiredStringBufferSize()};
    if (nn::swkbd::ShowKeyboard(&out, *reinterpret_cast<nn::swkbd::ShowKeyboardArg*>(g_arg)) != 0) return false;

    uint64_t value = 0;
    int digits = 0;
    for (std::size_t i = 0; i < sizeof(g_text) / sizeof(g_text[0]) && g_text[i]; i++) {
        char16_t c = g_text[i];
        if (c < u'0' || c > u'9') continue;
        value = value * 10 + static_cast<uint64_t>(c - u'0');
        if (++digits >= kMaxDigits) break;
    }
    if (digits == 0) return false;
    *seed = static_cast<uint32_t>(value);
    return true;
}

}  // namespace ootrr::keyboard
