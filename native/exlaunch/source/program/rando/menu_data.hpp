// Généré par ootrr/ingame_menu.py (menu_header) : ne pas modifier à la main.
#pragma once
#include <cstdint>

namespace ootrr::menu {

constexpr uint32_t kStructHash = 0x068ab00a;  // OoTRRMenu
constexpr uint32_t kMenuFlagHash = 0xa7ce2e71;  // OoTRR.IsRandomizerMenu
constexpr uint32_t kGenerateFlagHash = 0x81969956;  // OoTRR.GenerateSeed
constexpr uint32_t kSeedHash = 0xdb81d12e;  // OoTRR.Seed
// valeur lue -> valeur du réglage : bool = 0/1 ; énumération = index de la valeur du jeu
// member = hachage du nom du membre (ex. CameraRotateSpeed) : les accesseurs GameData d'une
// structure cherchent le membre par ce hachage dans la table de la poignée
struct MenuSetting { int32_t setting; uint32_t member; bool is_bool; int32_t count;
                     uint32_t game_values[8]; int32_t setting_values[8]; };
constexpr int kMenuSettingCount = 9;
inline constexpr MenuSetting kMenuSettings[kMenuSettingCount] = {
    {2, 0x0ae99f60, false, 3, {0x0c415b69, 0xfbe02251, 0x390b012d}, {0, 1, 2}},  // open_forest <- CameraRotateSpeed
    {3, 0xdd849f22, true, 0, {}, {}},  // open_door_of_time <- IsCameraUpDownReverse
    {9, 0x8c5522fc, true, 0, {}, {}},  // free_time_travel <- IsCameraRightLeftReverse
    {10, 0xa3f5862f, true, 0, {}, {}},  // skip_child_zelda <- IsUseGyro
    {0, 0x74b1edd9, false, 6, {0x69b014ce, 0x82591fa9, 0x2498c397, 0x7d30fc45, 0x515b9eeb, 0x33c26987}, {0, 1, 2, 3, 4, 5}},  // bridge <- VoiceLanguage
    {8, 0xc713c7da, false, 2, {0x60fc6939, 0x212dc0e7}, {0, 1}},  // shuffle_rewards <- LockOnType
    {6, 0xd9ec5222, false, 3, {0xb6eede09, 0x6bca39bd, 0x390b012d}, {0, 1, 2}},  // shuffle_hearts <- ControllerRumble
    {5, 0xaf497892, false, 3, {0x390b012d, 0xd4b93848, 0xbfae48cb}, {0, 1, 3}},  // maps_compasses <- DisplayMode
    {11, 0x3b0fc63f, true, 0, {}, {}},  // logic_lens_required <- IsChangeJumpButton
};

struct FixedSetting { int32_t setting; int32_t value; };
constexpr int kFixedSettingCount = 1;
inline constexpr FixedSetting kFixedSettings[kFixedSettingCount] = {
    {7, 1},  // skip_cutscenes = safe
};

constexpr int32_t kBridgeSetting = 0;
constexpr int32_t kBridgeCountSetting = 1;
struct BridgeCount { int32_t bridge; int32_t count; };
constexpr int kBridgeCountCount = 4;
inline constexpr BridgeCount kBridgeCounts[kBridgeCountCount] = {
    {2, 3},  // stones
    {3, 6},  // medallions
    {4, 9},  // dungeons
    {5, 10},  // hearts
};

// drapeaux posés au début de la partie : si réglage == valeur, drapeau = valeur du drapeau ;
// membre de structure (structure != 0) : écrit via la poignée de la structure
struct StartFlag { int32_t setting; int32_t value; uint32_t flag; uint32_t structure; uint32_t member;
                   bool flag_value; };
constexpr int kStartFlagCount = 25;
inline constexpr StartFlag kStartFlags[kStartFlagCount] = {
    {2, 1, 0xe5dc5674, 0x00000000, 0x00000000, false},  // open_forest=closed_deku : KokiriForest_Npc_Kokiri_007_Child_Blocker_00
    {2, 2, 0xe5dc5674, 0x00000000, 0x00000000, false},  // open_forest=open : KokiriForest_Npc_Kokiri_007_Child_Blocker_00
    {2, 2, 0x502f6cea, 0x00000000, 0x00000000, false},  // open_forest=open : KokiriForest_Npc_Kokiri_Mido_Child_Blocker
    {3, 1, 0x727c2cbd, 0x00000000, 0x00000000, true},  // open_door_of_time=True : Market_Child_TimeTempleDoor_Opened
    {3, 1, 0xb81f590c, 0x2b05cbb9, 0x82f1829f, true},  // open_door_of_time=True : HavePlayedEvent.Dm_TimeTemple_0010
    {5, 1, 0x89787395, 0x64e53a1f, 0x58aeb8fb, true},  // maps_compasses=start_with : DungeonInfo.InsideTheDekuTree.IsGetMap
    {5, 1, 0x06c51ff2, 0x64e53a1f, 0xc7692e3f, true},  // maps_compasses=start_with : DungeonInfo.InsideTheDekuTree.IsGetCompass
    {5, 1, 0xa52c3a19, 0x2bf2a024, 0x58aeb8fb, true},  // maps_compasses=start_with : DungeonInfo.DodongoCavern.IsGetMap
    {5, 1, 0x8b93edf9, 0x2bf2a024, 0xc7692e3f, true},  // maps_compasses=start_with : DungeonInfo.DodongoCavern.IsGetCompass
    {5, 1, 0xfcadd210, 0x88da0fed, 0x58aeb8fb, true},  // maps_compasses=start_with : DungeonInfo.InsideJabuJabuBelly.IsGetMap
    {5, 1, 0x9a2218db, 0x88da0fed, 0xc7692e3f, true},  // maps_compasses=start_with : DungeonInfo.InsideJabuJabuBelly.IsGetCompass
    {5, 1, 0xe704f9b4, 0x5b8d137d, 0x58aeb8fb, true},  // maps_compasses=start_with : DungeonInfo.ForestTemple.IsGetMap
    {5, 1, 0xf240eeb2, 0x5b8d137d, 0xc7692e3f, true},  // maps_compasses=start_with : DungeonInfo.ForestTemple.IsGetCompass
    {5, 1, 0x5b3ac0ba, 0x33ec10b0, 0x58aeb8fb, true},  // maps_compasses=start_with : DungeonInfo.FireTemple.IsGetMap
    {5, 1, 0x0aa068b6, 0x33ec10b0, 0xc7692e3f, true},  // maps_compasses=start_with : DungeonInfo.FireTemple.IsGetCompass
    {5, 1, 0x4a4402ab, 0x130436fc, 0x58aeb8fb, true},  // maps_compasses=start_with : DungeonInfo.WaterTemple.IsGetMap
    {5, 1, 0x2e82c8fe, 0x130436fc, 0xc7692e3f, true},  // maps_compasses=start_with : DungeonInfo.WaterTemple.IsGetCompass
    {5, 1, 0xf6177b93, 0xf4484a0a, 0x58aeb8fb, true},  // maps_compasses=start_with : DungeonInfo.ShadowTemple.IsGetMap
    {5, 1, 0x1e2feec5, 0xf4484a0a, 0xc7692e3f, true},  // maps_compasses=start_with : DungeonInfo.ShadowTemple.IsGetCompass
    {5, 1, 0xb85002ba, 0x9dc70937, 0x58aeb8fb, true},  // maps_compasses=start_with : DungeonInfo.SpiritTemple.IsGetMap
    {5, 1, 0x9bd1181c, 0x9dc70937, 0xc7692e3f, true},  // maps_compasses=start_with : DungeonInfo.SpiritTemple.IsGetCompass
    {5, 1, 0x77c47ec9, 0x8308d4be, 0x58aeb8fb, true},  // maps_compasses=start_with : DungeonInfo.BottomOfTheWell.IsGetMap
    {5, 1, 0x9d6efaac, 0x8308d4be, 0xc7692e3f, true},  // maps_compasses=start_with : DungeonInfo.BottomOfTheWell.IsGetCompass
    {5, 1, 0x322f2a94, 0x3876f97a, 0x58aeb8fb, true},  // maps_compasses=start_with : DungeonInfo.IceCavern.IsGetMap
    {5, 1, 0xea1846e6, 0x3876f97a, 0xc7692e3f, true},  // maps_compasses=start_with : DungeonInfo.IceCavern.IsGetCompass
};
// énumérations posées au début de la partie (valeur = hachage du nom de la valeur)
struct StartEnum { int32_t setting; int32_t value; uint32_t flag; uint32_t enum_value; };
constexpr int kStartEnumCount = 1;
inline constexpr StartEnum kStartEnums[kStartEnumCount] = {
    {3, 1, 0x378913ca, 0x21d6fa38},  // open_door_of_time=True: #931730378=Step06
};
// Porte du Temps ouverte : la quête ne doit pas reculer sous Step06
constexpr uint32_t kDoorChallengeHash = 0xe8dafe6c;  // DoorOfTime
constexpr uint32_t kDoorChallengePathHash = 0xa2beab0d;
constexpr uint32_t kDoorOpenSteps[] = {0x21d6fa38, 0x4c0a63f4};  // Step06, Complete
constexpr int32_t kOpenDoorSetting = 3;

}  // namespace ootrr::menu
