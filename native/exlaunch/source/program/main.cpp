#include "lib.hpp"

/* Test d'injection OoTRR : prouve que notre module (subsdk9) est chargé ET exécuté.
 * - svcOutputDebugString : visible dans le journal d'Eden si le filtre inclut Debug_Emulated:Debug ;
 * - svcBreak en mode « notification seulement » (bit 31) : Eden l'écrit au niveau Critical
 *   (« Emulated program broke execution! ») sans arrêter le jeu. info1 = 0x4F6F545252 (« OoTRR »). */

extern "C" void exl_main(void* x0, void* x1) {
    static const char message[] = "OoTRR: module natif charge";
    svcOutputDebugString(message, sizeof(message) - 1);
    svcBreak(0x80000000u | 0x4F, 0x4F6F545252ull, 0);
}

extern "C" NORETURN void exl_exception_entry() {
    EXL_ABORT("Default exception handler called!");
}
