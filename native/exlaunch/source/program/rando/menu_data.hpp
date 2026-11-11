// Généré par ootrr/ingame_menu.py (menu_header) : ne pas modifier à la main.
#pragma once
#include <cstdint>

namespace ootrr::menu {

constexpr uint32_t kStructHash = 0x068ab00a;  // OoTRRMenu
constexpr uint32_t kMenuFlagHash = 0xa7ce2e71;  // OoTRR.IsRandomizerMenu
constexpr uint32_t kGenerateFlagHash = 0x81969956;  // OoTRR.GenerateSeed
// valeur lue -> valeur du réglage : bool = 0/1 ; énumération = index de la valeur du jeu
struct MenuSetting { int32_t setting; int32_t member; bool is_bool; int32_t count;
                     uint32_t game_values[8]; int32_t setting_values[8]; };
constexpr int kMenuSettingCount = 10;
inline constexpr MenuSetting kMenuSettings[kMenuSettingCount] = {
    {2, 1, false, 3, {0x0c415b69, 0xfbe02251, 0x390b012d}, {0, 1, 2}},  // open_forest <- CameraRotateSpeed
    {3, 5, true, 0, {}, {}},  // open_door_of_time <- IsCameraUpDownReverse
    {9, 6, true, 0, {}, {}},  // free_time_travel <- IsCameraRightLeftReverse
    {10, 2, true, 0, {}, {}},  // skip_child_zelda <- IsUseGyro
    {0, 7, false, 6, {0x69b014ce, 0x82591fa9, 0x2498c397, 0x7d30fc45, 0x515b9eeb, 0x33c26987}, {0, 1, 2, 3, 4, 5}},  // bridge <- VoiceLanguage
    {8, 10, false, 2, {0x60fc6939, 0x212dc0e7}, {0, 1}},  // shuffle_rewards <- LockOnType
    {6, 17, false, 3, {0xb6eede09, 0x6bca39bd, 0x390b012d}, {0, 1, 2}},  // shuffle_hearts <- ControllerRumble
    {5, 3, false, 3, {0x390b012d, 0xd4b93848, 0xbfae48cb}, {0, 1, 3}},  // maps_compasses <- DisplayMode
    {7, 12, false, 2, {0xa3db7114, 0xdb209aaf}, {0, 1}},  // skip_cutscenes <- OcarinaKeyAssign
    {11, 8, true, 0, {}, {}},  // logic_lens_required <- IsChangeJumpButton
};

}  // namespace ootrr::menu
