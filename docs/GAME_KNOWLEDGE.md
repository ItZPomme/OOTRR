# What we know about the game

Knowledge gathered while developing the randomizer (game version: update 131072, files `*.Product.110/111`).
Legend: **[game]** validated in game, **[files]** observed in the files but not tested yet, **[hypothesis]** to be
confirmed.

## General

- *Tears of the Kingdom* engine: BYML maps, BFEVFL scripts, AINB logic modules, RSDB tables, GameData save (flags
  identified by the MurmurHash3 of their name).
- Title: `0400486024DEC000`. Mods: `<emulator>\load\0400486024DEC000\<mod>\romfs\...` (`%APPDATA%\fritchii` for
  recent Fritchii, `%APPDATA%\eden` for Eden).
- Answers of **script queries** are **0 = yes, 1 = no** (e.g. the Deku Scrub script: "has the medium bag?" -> 0 =
  sells the big bag). A case that ends the script is **omitted** from the case table (never a jump to 0xFFFF)
  **[game]**.
- GameData flags (`DefaultValue`) only apply to a **new game** **[game]**.

## Items

- Any item in any chest works (`Dynamic.Drop__DropActor`) **[game]**.
- Upgrades never downgrade (Hookshot after Longshot) **[game]**, **except the ocarina**: receiving the Fairy Ocarina
  replaces the Ocarina of Time **[game]** (guard added in Saria's script).
- Bombs require the bag **and** the Goron Bracelet **[game]** (`has_explosives`).
- A chest's "GetEventName" may belong to the item (Kokiri Sword: the sword appears on the back) -> `event: drop` when
  the item changes; or to the location (Dampé, Ruto) -> `keep`.
- `Obj_TBox_A_06` chests: conditional content (`Drop__CheckActor` / `Drop__DropActor_Substitute`).
- **Custom ground items**: copy of `Obj_Heart_Container` (renamed archive) + RSDB rows (`ActorInfo.ActorName` = item
  given, `PouchActorInfo` copied from the item). Works for simple items, songs, Pieces of Heart **[game]**. Model and
  animation copied from the item, inventory parameters (`PouchContentRef`) too.
- **An ocarina given by a ground item is not playable**, even with its inventory parameters **[game]**. Only script
  "gifts" (`PouchSystemActor.EventTriggerAddOrRemovePouchContent`) and chests make it playable. Equipment (bow, boots)
  is not added from the ground either (before copying the inventory parameters; not retested).
- Silent gift at the start: action `EventTriggerAddOrRemovePouchContent` (template: `Dm_Kokiri_0155`,
  `IsGetEvent = 0`) inserted in `OpeningEvent:Opening_Introduction` **[game]**.
- `IsGet.<item>` flags are set when the item is obtained; setting them to true does **not** remove the first-obtain
  animation of consumables **[game]** (decided by the engine).
- **Freestanding hearts, native menu [game]** (2026-11-11): the actor becomes a token `OoTRR_Lnnnn` (copy of the
  original heart, `ActorInfo.ActorName` = the token itself, `PouchActorInfo` copied from the heart). On pickup, the
  "item obtained" sequence looks up `<item>_GetMessage` / `_GetCaption` in `ActorMsg/PouchContent`: **a missing text
  blocks the game** (the heart spins forever); the token's texts are redirected to those of the seed item, then the
  add (`0x110d570`) too.
- **Model of a ground item chosen in game [game]** (2026-11-11): an actor's components (`ModelInfoRef`,
  `AnimationRef`…) are looked up by their path in its SARC archive (`0x32ade0`, path -> file number), not by the
  resource loader `0xa57350`. The token references `Component/ModelInfo/<token>…`; the lookup is redirected to the
  item's `ModelInfo` / `AnimationParam`, copied into the token's archive under their original path. Songs: rupee
  model without animation, they keep the heart's.
- Chest rupees `TBox_Rupee_*` do not have these texts (`Obj_Rupee_*` do). Rupees do not go through the inventory:
  adding them has no effect, money is the integer `PlayerStatus.CurrentRupee` **[game]**.
- Inventory: binary block of the save, no per-item flags (except `PouchData.<item>.StockNum`).
- Useful values: `PlayerStatus.MaxLife` (quarter hearts, 12 = 3 hearts), `PlayerStatus.Life`,
  `PouchData.Item_Token_Gold.StockNum` (Gold Skulltula tokens).

- Inventory add (`0x110d570`): chests give with reason 7 (event), like scenes (seen in the log): name + reason are
  not enough to know where an item comes from.
- Bombs (`Item_BombBundle_*`) obtained without a bag: the game gives the bomb bag (reported in game). Replacing the
  name in the inventory add (`0x110d570`) is not enough: the bag still arrives (observed, sword chest). Native menu:
  the chest receives a blue rupee at the source if there is no `IsGet.Item_BombBag_*` **[files]** (to test).
- Kokiri Sword chest: `GetEventName = Get_StoneOfForest_GetSword` -> `Dm_Kokiri_0063` puts a sword in Link's hand
  (`EventTriggerPlayerRequestCreateDynamicEquipmentNoRelationPouch`) even if the chest contained something else; the
  sword disappears on reload (reported in game, native menu: removing `GetEventName` at the source is not enough).
  Guard added: the scene only plays if `IsGet.Weapon_Sword_Kokiri` **[files]** (to test).
- **Ice Arrows lost as child [game]** (2026-11-13): Ice Arrows from a chest (Graveyard shield grave, no bow) as
  child, with nothing else to put on the item buttons: the game equips the bow with Ice Arrows by itself, then the
  arrows are missing from the Items tab, child and adult, although `IsGet.Item_Arrow_Ice` is set in the save. Same
  chest with Deku Sticks and Nuts from the start (`start_with_consumables`): the arrows are in the inventory. Fire
  Arrows obtained as adult were fine. Not yet known: whether Fire / Light Arrows or the Bow are lost the same way as
  child, and why Mido's chests (test 13) did not lose them. Tools: `testmod --test 13|14`.
- Reading a GameData boolean (non-struct): `0x3744460` (manager, bool*, hash, index >= 0), function of the
  `SeqQueryGetNonStructGameDataBool` node **[files]**.

## Ocarinas

- Saria (`Dm_Kokiri_0155`, called by `Goto_HyruleCastle:KokiriForest_ArriveLostWood`) and the moat
  (`Dm_MelodyGet_Time`, after `DoorOfTime:DoorOfTime_GetOcarinaOfTime`) name the ocarina 4 times: inventory action,
  `GetPouchContent:DisplayGetByActorName`, ZeldaNotes and an actor of the scene.
- Saria's scene is no longer skipped (the Fairy Ocarina is no longer given at the start). `shuffle_ocarinas`: native
  menu = the scenes give the location's token (copy of the ocarina), the module gives the seed item; progressive
  ocarinas (the second one obtained is the Ocarina of Time); double gift at the moat (direct gift + scene) ignored
  **[files]** (to test in game).

## Songs

- The 12 songs are given by the common script `Dm_SY_Ocarina` (called by the `Dm_MelodyGet_*` scenes): a query
  `EventQueryMelodyTypeForNormal` (melody of the scene) leads to one inventory action per song. The Lullaby's name is
  also used there for `EventQueryCheckIsGet` (free ocarina play): only the gift action is copied with the other item
  (`ModBuilder.song_gives`), the original one is skipped **[files]**.
- `shuffle_songs`: vanilla, shuffle (permutation between song locations, like boss rewards), random (song locations
  in the pool). Native menu: each gift becomes its location's token; the Song of Time is also given directly at the
  moat (duplicate ignored). Only the seed's song is given **[game]** (2026-11-12); the scene's lesson still plays the
  original song.

## Gifts (minigames, Great Fairies…) **[files]**

- These items do **not** go through `EventTriggerAddOrRemovePouchContent`: the scripts name them in a text parameter
  of a sub-flow. Two mechanisms: `NpcCommon:NpcCommon_HandOver_NpcToPlayer_NoDisplay` (parameter `ReveiveItem`;
  shooting galleries `MiniGame_HitTarget`, bowling, fishing, Anju `Minigame_CatchCucco`) and
  `Dm_SY_GetInEvent:GetInEvent_*` (parameter `ActorName`; Great Fairies `Dm_FairyFountain_*`, Darunia
  `Dm_Goron_0030`, Gerudo card `Dm_Gerudo_0025`, `Dm_LostWood_0040`, horseback archery, diving, Light Arrows
  `Dm_TimeTemple_0130`, man on the roof `Npc_Hylia_001_Adult`, Dampé's tour `Npc_Hylia_Dampe_001`). The bag / quiver
  given depends on what Link owns (condition `EventQueryIsExistInPouch` on the medium level): one variant per item,
  listed in `data/gifts.json` (flow, event number, parameter, original text).
- `evfl.replace_event_strings` only changes these precise events: the string "Item_BulletBag_Medium" is **shared**
  with the `IsExistInPouch` condition (single pointer), `replace_strings` would break it.
- With the native menu, each location gives the token `OoTRR_Lnnnn` (copy of the original item) and the `PouchAdd`
  hook gives the seed item, as for ocarinas; setting `shuffle_gifts`, "Gifts" row (page 3). Without the menu, the
  placed item's name directly replaces the text. **Not fully validated in game yet.**
- Adult Anju (`Npc_Hylia_049_Adult`, event 223, `ReveiveItem` = `Item_PocketEgg`): location "Kak Anju as Adult". After
  the gift the script moves the quest `SubEvent_GetSwordBigGoron` to `StartSubEvent` whatever item was given; the
  rest of the Biggoron trade quest (Cojiro at event 194, etc.) stays vanilla.
- Biggoron (`Npc_Goron_Biggoron_Adult`, entry `SubEvent_GetSwordBigGoron_Step11`, event 95 = sub-sequence
  `Dm_SY_GetInEvent:GetInEventItemSwordBiggoron`, `ActorName` = `Item_Sword_Biggoron`): location "DMT Biggoron".
  Every path after the Claim Check is shown (Talk_301 / Talk_312, removal of `Weapon_Sword_Giant` or
  `Weapon_Sword_BrokenGiant` if Link has one) reaches this event; then the quest step `Complete`. Saved flag
  `IsGet.Weapon_Sword_Biggoron`; PouchActorInfo: `PouchTabCategory` Equipment (so not a ground item).
  `adult_trade_sequence`: the logic follows the vanilla quest through events `Trade_*` (Kakariko: Cojiro once Talon
  is woken with the hatched egg, Granny's Odd Potion; Lost Woods: Grog, Fado; Gerudo Fortress side: carpenter boss;
  summit: Prescription; Zora's Domain: Eyeball Frog, King Zora thawed with Blue Fire; Lake Hylia lab: Eyedrops).
  Timers (Odd Potion, Eyedrops) are not modelled. Off: the location has `no_progression` (`trade: true`) and
  `Item_PocketEgg` gives no logic item. **Verified in the files, not validated in game** (an item other than the
  sword given by `GetInEventItemSwordBiggoron`, and a Pocket Egg found elsewhere than at Anju's).
- Not done: Zelda's letter (`Dm_HrlCastle_0050`, interferes with `skip_child_zelda`), the Ghost Shop's 1000-point
  "golden reward", bowling 2nd prize, horseback archery 1000 points and other Pieces of Heart: mechanism not found
  yet.

### Bottles **[files]** (2026-11-14, not validated in game)

The five bottles that exist in the game files (scan of every `Event/EventFlow` script for `Bottle` / `Letter` /
`Poe`) are all locations shuffled with `shuffle_gifts`:

| Location | Giver | Mechanism |
|---|---|---|
| `Kak Anju as Child` | Anju, cuccos (`Minigame_CatchCucco` 124) | `HandOver_NpcToPlayer_NoDisplay`, `ReveiveItem` = `Item_Bottle` |
| `LLR Talons Chickens` | Talon, child (`Minigame_FindOutCucco` 262) | same, `Item_Bottle_Milk`. First win only (`IsClear_Minigame_FindOutCucco` false); later wins refill an empty bottle (event 190, `NpcCommon_HandOver_NpcToPlayer_EmptyBottle`), left alone |
| `Market Potion Shop Bottle` | child potion shop keeper (`Npc_Hylia_020_Shop_Child` 162), remake addition: "bottle tutorial" on first talk (`Market_Item_Bottle_TutorialEvent`, then catch a bug) | `GetInEvent_NotTurn_FixedCamera_WarpLink`, `ActorName` = `Item_Bottle` |
| `Market 5 Big Poes` | Ghost Shop (`Npc_Hylia_048_BottleShop` 319, adult market) | `GetInEvent_Poeshop`, `ActorName` = `Item_Bottle`. 100 points (`GhostShop_CouponNum`) per Big Poe, the bottle comes with the sale that reaches 500 (10 `Enemy_Poe_Big` in `HyruleField_Adult_Static`). Rule copied from OoT (Epona, bow, bottle), not checked in game |
| `LH Underwater Item` | Ruto's letter on the lake floor: ground actor `Obj_Bottle_Letter` (hash 474136620438465634, `HyruleField_Child_Static`) | `pickup: "item"` like the Fire Arrows (the actor's type is changed) |

- Ruto's letter quest step: `Dm_SY_Get` (generic "get item" flow) calls `Get_StoneOfWater:StoneOfWater_GetRutoletter`
  (sets `Get_StoneOfWater_GetRutoLetter`, Step05_01) when the obtained actor has the tag `LetterBottle`, which both
  `Obj_Bottle_Letter` and `Item_Bottle_Letter` carry (RSDB `Tag`). So the letter given from elsewhere should still
  advance the quest, *if* that gift goes through `Dm_SY_Get` (unknown for chests and NPC gifts).
- Not locations: the Business Scrubs give a free `Item_Bottle` (`GetInEvent_NotTurn_2DShop`, price 0) when Link has
  no bottle and buys bottled content (`Enemy_Scrub_Business_Common` 444, `_Dream` 291): anti-softlock, left alone.
- The pickup location can only hold "ground" items (`items.json`), so the letter itself goes to chests and gifts.

- **Minigame counts** **[files]** (settings `cucco_count`, `big_poe_count`; PC-built mod only, not validated in
  game). `EventQueryIsGameDataInt` answers 0 = less, 1 = equal, 2 = greater (value compared with `Value`).
  - Anju: the logic module `MiniGame_CatchCucco_c69b` counts the 7 cuccos in the pen (`OperateBoolCount`, node 9,
    into `MiniGame_CatchCucco_InFenceCount`) and compares 7 with it (`OperateCompareInt` node 17, `Int_A` = 7):
    Equal sets `Npc_Hylia_049_Child_Cucco06_IsInTheCage` (in fact "all in the pen"), A_Bigger clears it, only when
    the count changes. The script `Minigame_CatchCucco` checks that flag before `Ready_Npc_Hylia_049_Complete_Talk`
    and computes the remaining count from the same 7 (events 30 and 17). The generator changes these three 7s;
    the in-place patch of the module changes 4 bytes (the `ainb` library re-serialises with other flag bytes).
  - Poe buyer (`Npc_Hylia_048_BottleShop`): 100 points per Big Poe in `GhostShop_CouponNum`; before a sale the
    points are compared with 400 (events 242, 243, 244 for the sale paths, 246, 248, 250, 252 for texts): equal ->
    the sale that reaches 500 gives the bottle (event 319). **The remake's bottle needs 5 Big Poes**, not 10; at
    1000 points (compare with 900) he gives a Gold Rupee and completes `SubEvent_GhostShop`. The generator moves
    the 400s to (count - 1) x 100. Texts that say "7 cuccos" / "500 points" are not changed.
- **Fire Arrows**: ground item `Obj_Arrow_Fire` (base `Obj_Item_Base`, like Pieces of Heart) in
  `HyruleField_Adult_Static`, created by `HyruleField_LakeHylia_Adult_Prefab_5313` (quest `SubEvent_GetFireArrow`
  at Ready, time window, arrow shot into the sun -> scene `Dm_LakeHrl_0030`, Step03). Location `pickup: "item"`
  (with `actor`), shuffled with `shuffle_gifts`; token like freestanding hearts **[files]**.
- Zora's River (child): rocks `Obj_BrokenRock_A_01` at the entrance, to blow up with a bomb (no adult version)
  **[game, original behaviour]**.
- Dampé's grave (adult race): the exit of the arrival room needs the Hookshot, which is in the race chest; without
  it, talking to Dampé warps out (standalone copy of event 70 of the flow) **[game]**.

## Shops, Deku Scrubs, Skulltulas

- **A merchant's list: never add `Release` to an item that has none**: reading `GoodsList` calls a null pointer
  (`0x612b24`, `Release` field read by `0x3051480`) -> endless loading (Goron City, shops with 4 items, seen in the
  Eden log). Goron, Zora and Bombchu have no original `Release`; `shops.py` only lifts the condition where it exists
  **[files]**. Adding new keys or conditions on new GameData to make a "Sold out" sign also crashed at 0x612850
  **[game]** (see ROADMAP).

- **Shuffled shops (native menu) [game]** (2026-11-11): see native/README.md ("Shops"). A merchant's item list:
  `Component/ShopParam/…` in its archive, `GoodsList` in `ShopItemIndex` order; `Release` = appearance condition
  ("Coming Soon": Kokiri shop before the Deku Tree; "sold out": bazaar bombs before the fire stone). The Bombchu
  merchant only appears after the fire stone (presence removed). An item must be in the list AND linked to the
  merchant (`ForSale`, `Reference` links) to be chosen. The price comes from the RSDB row
  `PouchActorInfo.BuyingPrice`. Single sale: saved integer `OoTRR.ShopSold` (one bit per item), price 999 after
  purchase, refund of a repurchase **[game]** (2026-11-12).

- Shop item = actor `Shop_*`; `ActorInfo.ActorName` = item sold; price in the archive's `PriceParam`. Copy of an item
  = another item sold **[game]**; `ActorGameDataSetting` = `NoRespawn` for a single sale **[game]**.
- Deku Scrub salesmen (`Enemy_Scrub_Business`): `Dynamic.ScrubBusiness_ShopItemActorName0..2`, `TalkEventName`. The
  script `Enemy_Scrub_Business_Common` compares the name with a fixed list. Method **[game]**: "stick bag" script for
  all of them, inserted queries ("item = X?") that lead to the single sale `SimpleShopSub_Scrub_Business_OneTime`
  (integer price, message).
- **Shuffled Deku Scrubs (native menu) [game]** (2026-11-11): 5 sellers of a unique item (field, crater, sticks
  forest/Lost Woods, nuts). The item must stay a **real item** (`EventScrubBusinessWriteGameDataBancItemName` ignores
  an unknown name): it is used as a marker, an inserted query sells the token. The field one sells directly (`Secret`
  entry). Name in the message: shop tag `[2:3 Shop_SelectItemName]` (set before the sale), resolved by the inner
  lookup `0xa6b060` (not `0xa6afe0`) where the token's text is redirected.
- A Piece of Heart added under another name (token) is **not counted**: the module increments
  `PouchData.Obj_Heart_Piece.StockNum` (going to 4 pieces -> container: not verified).
- Gold Skulltula: `Dynamic.Drop__DropActor` replaces the token **[game]**; it needs a collectable item (copy of
  `Obj_Token_Gold` or of the container). As long as the item is not picked up, the Skulltula reappears.
- Shuffled Gold Skulltulas: the Skulltula drops its token `OoTRR_Lnnnn` (copy of `Obj_Token_Gold`), model, texts and
  add redirected to the seed item — **validated in game** (Deku Tree). The token is not replaced at the source
  (`KeepsToken`). Gold token placed in a chest: **validated in game**.
- Useful `Enemy_Skulltula_Gold` (Dynamic) parameters to identify each Skulltula:
  `Enemy_Skulltula_Gold_IsMagicBeanSoil` (soft soil, presence = flag `Gimmick_MagicBeanSoil_<area>`, set when bugs
  are released), `Enemy_Skulltula_Gold_Nocturnal` (night), `AppearPopOut` + `AppearWarpRotOffset` (tree), an
  `Obj_BrokenBox_A_*` crate at the same position, `DefaultDungeonRoomIndex`. Rules in `skulltulas.json` (9 uncertain
  ones keep `no_progression`): **verified in the files**, not yet validated in game one by one.

## Masks, Blue Fire, player movement **[files]** (2026-11-14)

- **Happy Mask Shop quest**: GameData Enum without a known name, hash `3925934864` (found in
  `SubEvent_MaskSalesman_IsCompleted_Exp`): NotReady, Ready, UntilRentMaskOfKeaton, Step01_Hint, Step01, Step02,
  UntilRentMaskOfSkull, Step03_Hint, Step03, Step04, UntilRentMaskOfSpooky, Step05_Hint, Step05, Step06,
  UntilRentMaskOfBunny, Step07_Hint, Step07, Step08, Complete. Buyers in `SubEvent_MaskSalesman` (Kakariko guard
  `Npc_Hylia_Soldier_003` Step01/02, Skull Kid Step03/04, Running Man Step07/08; the Spooky Mask buyer is not in
  this flow), payments in `Npc_Hylia_023_Shop_Child` (`Pay_ki-tan`, `Pay_dokuro`, `Pay_kowaso`, `Pay_usagi`; at
  Complete the talk goes to `TalkWithoutMask_Complete`). The shop's `ShopParam` (`Npc_Hylia_023_Shop_Child`) shows
  each mask while the BoolExp `HappyMaskShop_HasMask_<mask>` is true: quest after Step01 (Skull), Step03 (Spooky),
  Step05 (Bunny), Step07 (Zora, Goron, Gerudo, Truth; Truth also needs `IsPlayingFirstTruthMaskGetDemo` false),
  `PouchData.Armor_Child_Mask_<mask>.StockNum` = 0 and the lent-mask integer (hash 3472691999, -1 at the start)
  not equal to the mask's rank in the list (Spooky 0, Keaton 1, Bunny 2, Skull 3, Zora 4, Goron 5, Gerudo 6,
  Truth 7). Keaton needs `Npc_Hylia_Soldier_003_GateOpen` (Kakariko gate) instead of a step. Setting
  `complete_mask_quest`: the Enum starts at Complete (start flag, PC-built mod only). The Lost Woods Skull Kid
  only disappears with `NPC_SkullKid_Delete` (set when he buys the mask), not with the quest step. **To test in
  game.**
- **Red ice and Blue Fire**: `Obj_RedIce_A_*` has no Chemical or Life component: its AI (`Obj_RedIce_A_01.root`)
  only melts on a message `QueryMessageBlueFireReceiveMessage` (MessageType 890699779), then relays it to its
  linked actors. The poured Blue Fire (`Obj_BlueFire_A_03`, ActorHolder of `Weapon_Bottle_BlueFire`) finds the
  target with `QueryBlueFireFindTarget` (attention client `Obj_RedIce_A_01_BlueFireTarget`, range 4 m), flies to
  it (`ExecuteBlueFireMove`) and sends that message (`OneShotMessageBlueFireSendMessage`). King Zora has his own
  Blue Fire handling in `Npc_Zora_KingZora_adult.event.root`.
- **Ice Arrows**: every arrow is the actor `NormalArrow` (`AssginableItemParam.ShootableActor`), without AI; the
  arrow type picks an entry of `GameBalance/AttackParam/NormalArrow` by `AttackType` (Ice Arrow = 3740198074 =
  `AssignableItem` of `Item_Arrow_Ice`, `DamageElements` [2817341698], multiplier 2). The element only reaches
  actors with a damage receiver (Life / DamageCalculator, e.g. `QueryGetLastDamageIsOnDamageElementFromExternal...`),
  which red ice does not have, and no hit of any kind reaches red ice (see "Red ice graft" below).
- **Ice Arrows melt red ice (`blue_fire_arrows`) [game]** (Longshot, 2026-11-15; prototype mods
  `OoTRR-essai-fleche11`, `roizora4..6`, script `output/essai/exp_ice3.py`; setting built by the generator,
  `ainb_graph.ice_arrow_ai` / `red_ice_melt`, validated with the generator-built mod `OoTRR-essai-bluefire1` on
  King Zora). Two AIs linked by a saved GameData Int (`OoTRR.IceArrowShot`):
  - `NormalArrow` gets an AI (`AIInfoRef` -> `PostSensorAIRef`; the actor had none). It runs while the arrow is
    nocked (`QueryShootableGetState` 1) and **only 2 more frames after the shot** (state 2, then 0; selector-free
    count, `roizora6`); not in flight nor stuck. There the blackboard S32
    `ShootableArrow_ArrowType` (`QueryBlackboardGetS32NoError`, `BlackboardType` 1) is 0 for a normal arrow, 2 for an
    Ice Arrow. While it is 2, the arrow writes 60 to `OoTRR.IceAim`, a **saved** Int (SaveFileIndex 0). A runtime
    Int or Bool (SaveFileIndex -1) written by the arrow was never seen by red ice; a Bool also cleared by normal
    arrows stayed false.
  - Red ice (`AI/Obj_RedIce_A_01.root.ainb`, 7 packs) decrements it while > 0 and melts on the Blue Fire message OR
    (`0 < OoTRR.IceAim` AND camera aim): `QueryCameraGetGameCameraWorldPosition` (vec3f outputs `DIrZ`, `Position`,
    used in that order), direction camera -> actor position + (0, 1.5, 0) normalised, `dot(direction, DIrZ) > 0.9`
    (DIrZ points forward) and `QueryMathCalcVectorDistance` < 15 m (the `Magnitude` output of
    `QueryMathNormalizeVector` is not usable). The melt condition is ORed into the two original selectors that
    wait for the Blue Fire message (nodes 28 and 45).
  - `fleche11`: the timer was written while nocked, so the ice melted while aiming. **Melting on the shot [game]**
    (`roizora6`, King Zora): the arrow writes the timer only when it is an Ice Arrow AND `1 < state` (the 2 frames
    after the release), with `QuerySelectS32ByBool` (60, else the current value) into an `ExecuteEveryFrame`
    `OneShotSetNonStructGameDataInt`; the camera still points at the ice then. Aiming without shooting no longer
    melts it. Possible flaw, not checked: nocked arrows write back the current value every frame, which may keep
    the timer alive after an Ice Arrow shot while the bow stays drawn.
  - **King Zora [game]** (mod `OoTRR-essai-roizora4`): his ice is `Obj_RedIce_A_02` (same position as
    `Npc_Zora_KingZora_adult`, which links to it; `NpcZora.interruptseq.ControlFrozen` keeps him frozen while that
    ice actor exists). Melting it this way thaws him with the vanilla scene and the Zora Tunic. A cone around
    actor position + 1.5 m missed this 7.5 m ice: each pack now aims at the centre of its own Tgt shape
    (`AutoCalc.Center`) and also melts when the camera ray passes within a radius of it (|v|^2 < t^2 + r^2, t > 0,
    with `QueryMathCalcVectorDistance` `IsCalcSquareDistance`). With the bow drawn the ray passed 4 to 8 m from
    King Zora's ice centre (r = 4.1 m: 52 aimed frames out of 1163), so r is now twice the Tgt half size
    (`roizora5`; `roizora6` with it melted King Zora's ice on the shot). `Obj_RedIce_A_03` (Zora's Domain adult,
    no AI) is a decoration.
  - Not tested: the other red ice packs one by one, Blue Fire from a bottle with the mod.
- **Fast Bunny Hood (`fast_bunny_hood`) [game]** (Longshot, 2026-11-14, PC-built mod): nodes added to Link's
  `Player.action.walk.module` (`ootrr/ainb_graph.py`). `ExecutePlayerMove` has no parameter and masks have no
  movement data, but `QueryPhysicsCctGetForwardSpeedMps` x factor -> `ExecutePhysicsCctSetForwardSpeedMps` after it
  scales Link's speed and follows the stick (a constant forward speed or `ExecutePhysicsCctSetForwardAndSide...Rate`
  do not: the side rate pushed Link sideways). Condition: BoolExp `OoTRR_HoodWorn_Exp` = the unnamed saved
  `PlayerStatus` Bool (member key 3947362076, flag hash 3262939387: 0 without the hood, 1 with it, read in
  progress.sav) AND `PlayerStatus.EquipHeadArmor` == `Armor_Child_Mask_Bunny` (that String64 keeps the last mask
  after it is taken off). Tested in game with x1.6; the setting uses x1.5.

- **Adding nodes to actor AI modules [game]** (Longshot, 2026-11-14; experiment scripts in `output/essai/`):
  - **Each file inside a pack has its own RESTBL entry**, only ~0x190 bytes over its size. A bigger `.ainb`
    without a bigger entry overwrites memory: black screen when Link is created, Bunny Hood that no longer equips.
    Raising the pack's entry or RSDB `InstanceHeapSize` does not help. With the inner entry raised, nodes copied
    from other packs work (`ainb_graph.inner_size_entry`).
  - A file shared by several packs (the walk module: `Player_Child`, `Player_Adult`, `Player_Base`) is edited in
    each of them.
  - `Element_BoolSelector` with `CalculateTiming` 1 re-evaluates its input every frame (0 keeps its choice while
    the child runs). `QueryGetNonStructGameDataBool` reads flags correctly (control test).
  - **A selector added beside the original tree of an AI that keeps running is only evaluated on its first
    frame** (red ice, 2026-11-15), even with `CalculateTiming` 1 and branches that never finish: every condition
    logged that way was its first-frame value (counters equal to 0 or to the frame count). The walk module and the
    arrow AI are re-entered, so selectors work there. What works in a running AI: an `ExecuteEveryFrame` action
    whose input comes from a query (re-read every frame), e.g. `QuerySelectS32ByBool` -> `OneShotAdd...Int` to
    count frames, and conditions ORed into the original tree's own selectors. **The red ice logs of
    `glace2`..`glace14` and `fleche5`..`fleche9` were therefore first-frame values only.**
  - `QueryMathLessF32` / `QueryMathLessS32` = (`F32` < `F32Base`).
  - The AI of `Armor_Child_Mask_Bunny` only runs for a moment when the actor is created (a saved frame counter
    written by it stopped at 96): it cannot report "worn" every frame. Wrapping its root in a `SplitTiming` broke
    the hood (before the RESTBL fix).
  - **Logging**: an AI can write saved GameData Ints (`OneShotSetNonStructGameDataInt`, new entries saved with
    `ingame_menu.add_saved_entries`); the values are read back from `user/save/*/slot_*/progress.sav` (pairs hash,
    value after a 0x20 header; String64 values are offsets in the file). Longshot saves in rotating slots.
  - Red ice + `LifeRef` / `SensorHitRef` components copied from `Obj_LakeHrl_SwitchHit_A_01`: **crash** when
    Zora's Domain (adult) creates `Obj_RedIce_A_02` (heap corruption in the engine's allocator), also with the
    original AI and with `InstanceHeapSize` + 256 KB; tried before the RESTBL fix above.
  - **Red ice graft, with the inner RESTBL entries raised [game]** (Longshot, 2026-11-14/15, mods
    `OoTRR-essai-glace2`..`glace14`, scripts `output/essai/exp_ice.py`, `ice_*.py`): no crash, the added AI runs
    (frame counter), but no hit was logged on the red ice (first-frame values only, see above), with normal or Ice Arrows (TgHit, TgIgnore,
    DamageTypeAny, IsDamaged, Life external damage, damage elements 0..10: all 0). Tried, cumulatively: Chemical
    (`Obj_BrokenIcePillar_A_01`), Life (pillar's, made invincible), SensorHit (pillar's, then `Obj_Ice_A_01`'s with
    `IsIgnoreOcclusionCheckTgHit`), Tg sensor layer `EnemyReceipt` / `Default` + `MotionType` like
    `Ptm_DgnObjStatic_00_Tgt`, and the actor class `ActorLogicSimpleActor` instead of `ActorLogicRedIce`. Same Tgt
    / Physical shape sizes as `Obj_Ice_A_01` (which fire arrows melt via TgHit AND `QueryChemicalIsContactFire`).
    Control: the same log beside the AI of `Obj_BlueFirePedestalLid_A_01` (Ice Cavern, root
    `Obj_BrokenIcePillar_A_01.root`, `PreActorSetting` ActorOnly) never ran at all, even when shot (frame counter
    0): likely a pre-actor that only becomes a full actor on an effective hit. The ice never melted either, so
    hits really do not reach it; the aim method above replaces this graft. Test mods with the bow need `Item_Quiver_Small`, `Item_Arrow_Normal` and
    `PouchData.Item_Arrow_Normal.StockNum`; a start in a banc without an `_Adult` variant (IceCavern) makes Link a
    child even with `starting_age=adult` (use `ZoraFountain_Adult=ZoraFountain_FromIceCavern`).

## Dungeon keys **[files]** (2026-11-15, not validated in game)

- Per dungeon, saved GameData members (SaveFileIndex 0) `DungeonInfo.<game>.SmallKeyNum` (Int) and
  `DungeonInfo.<game>.IsGetBossKey` (Bool), beside `IsGetMap` / `IsGetCompass`; they exist for the 8 dungeons with
  keys (`ForestTemple`, `FireTemple`, `WaterTemple`, `ShadowTemple`, `SpiritTemple`, `BottomOfTheWell`,
  `GerudoTrainingGround`, `InsideGanonCastle`) and `GerudoFortress`. The struct has 4 more members, names unknown.
- Key chests (`tools.inventory`): `Drop__DropActor` = `Item_Dungeon_SmallKey` (37 chests) or `Item_Dungeon_BossKey`
  (6 chests, Ganon's Castle included). Ground keys `Obj_Dungeon_SmallKey`: one in Bottom of the Well (room 3), one in
  the Shadow Temple (room 13). Gerudo Fortress carpenters drop `Obj_Dungeon_SmallKey_GerudoFortress_0N` (untouched).
  Hashes and rooms (`DefaultDungeonRoomIndex`) are in `data/keys.json`.
- A chest gives a key through `Dm_SY_Treasurebox` (`Success_AddContent`): `EventQueryTreasureBoxIsDungeonCommonItemInside`
  (0 map, 1 compass, 2 boss key, 3 small key, 4 other) -> `GameSystemActor.EventGetDungeonSmallKey` /
  `EventGetDungeonBossKey`, **without a dungeon parameter**: the key goes to the dungeon of the current map. Hence a
  key of dungeon A found elsewhere needs another way:
  - the chest drops `Obj_MiniGame_SmallKey` (the Treasure Chest Shop's key: "You got a door key!", PouchSpecialDeal
    `NotPushToPouch`, so it is not counted anywhere by itself);
  - its `GetEventName` names a new RSDB `EventSetting` row (+ `GameAnalyzedEventInfo` row), copy of
    `ForesetTemple_GetBossKey` (the event of every vanilla boss key chest, flow `ForestTemple_Gimmick`, entry
    `TreasureBoxDM_NaviChat_ForestTemple_BossKey`: `EventTransition Dm_SY_Treasurebox`, then Navi's line, step 101).
    A chest event replaces the default opening and plays `Dm_SY_Treasurebox` itself; the vanilla row is used in
    Fire / Water / Shadow / Spirit, whose maps have none of the flow's other actors (Stalfos...), so missing actors
    of unused steps are fine;
  - the row's `FlowchartFileName` points to a copy of `ForestTemple_Gimmick` (`OoTRR_SmallKey_<game>.bfevfl`, new
    RESTBL entry) where step 101 becomes `GameDataActor.EventTriggerAddOrSubGameDataInt`
    (`DungeonInfo.<game>.SmallKeyNum`, Value 1; template step 33 of `MiniGame_SequentialChoiceTreasure`, which counts
    the shop's keys the same way in `MiniGame_SmallKeyNum`) or `EventTriggerSetGameDataBool` (`IsGetBossKey`, True;
    template step 195). To check in game: the new script file is found, the counter goes up, the HUD count follows.
- `removed`: the counters start at the dungeon's total of keys (chests + ground) and `IsGetBossKey` at true
  (DefaultValue). Not known yet whether the boss door only reads `IsGetBossKey`.
- Locked doors: `Obj_DoorChainLock_A_01` (one per side, e.g. 10 in the Forest Temple = 5 doors, `_A_02` = boss
  door, Fire Temple `_A_04`, Spirit Temple `Obj_SpiritTemple_DoorChainLock_A_01`), driven by logic modules
  `DungeonDoorSingleWithChainLockSet_*` (`ActorLogicDoorChainLock` input `OpenKey`, output `IsKeyOpen`). No room
  connection table was found (RSDB `DungeonParam` only lists rooms), so the logic does not know the door layout.

## Messages (Mals)

- `Mals/<language>.Product.110.sarc.zs`: 16 languages, MSBT in **UTF-8** (byte 0x0C = 0).
- Tags: `0x0E` + group, type, size, data. E.g. color `[0:3:0000]`…`[0:3:ffff]`, price `[2:12:…SimpleShop_Price…]`
  (GameData value inserted), pause `[5:0:]`.
- A dialogue's answers (`ChoiceLabel1 = N`) are the message named `000N` **of the same file**.
- Item names: `ActorMsg/PouchContent.msbt`, labels `<item>_Name`.
- Messages can be added (`msbt.add_messages`, identical rewrite verified).

## Kokiri Forest

- Door of Link's house (`Obj_Kokiri_Door_A_01`, the only actor of this type): it plays `Dm_Kokiri_0045` (discovery of
  the forest) when opening, ignoring the "already seen" flag. Flag `KokiriForest_LinkHouseDoor_Open` true at the
  start: door open, no scene **[game]**. (Removing the door leaves an invisible wall; emptying `OpenEventName` keeps it
  from opening.)
- First-discovery map of a location: `IsVisitLocation.<location>` true = already discovered **[game]**.

- Blockers: `Npc_Kokiri_007_Child` (exit towards the bridge), `Npc_Kokiri_Mido_Child` (Deku Tree), invisible walls
  `FldObj_AirWall_Player_GenerateNavMesh` present depending on `KokiriForest_Npc_Kokiri_007_Child_Blocker_00` /
  `KokiriForest_Npc_Kokiri_Mido_Child_Blocker` (true at the start) **[game]**.
- Interruptions: Kokiri on the roof = event request `KokiriForest_Kokiri_011_StopInFrontOfShop_00` (made absent)
  **[game]**; shield tutorial = sub-flow called by the shopkeeper after the purchase (`Npc_Kokiri_001_Shop_Child` ->
  `Npc_Kokiri_010_Child:DekuShield_TutorialTalk`) **[game]**.
- Saria at the bridge (`Dm_Kokiri_0155`) gives the Fairy Ocarina through an inventory action.

## Door of Time, sword, time travel

- Quest `DoorOfTime` = GameData Enum without a known name, hash `931730378` (NotReady, Ready, Step01… Step06,
  Complete). The door (module `Market_Common_f252`) is open if the step is **≥ Step06**.
  `Market_Child_TimeTempleDoor_Opened` only skips the animation **[game]**.
- The remake counts **the Goron Ruby and the Zora Sapphire** for the door (`DoorOfTime_CheckStoneNum`).
- The moat ocarina (`Obj_Ocarina_Time_A_01`, module `HyruleField_Child_Prefab_91f9`) only exists at step **=
  Step04**; picking it up runs `DoorOfTime:DoorOfTime_GetOcarinaOfTime` (scene `Dm_MelodyGet_Time`). Open door:
  module changed for Step06 + "3 stones" presence + direct gifts in the script **[game]**.
- Native menu: the door opens by setting the Enum to Step06 at the start of the game (function `0x3e0980`); a hook on
  the quest step change (`0x2cf54a0`) prevents any going back. The moat module creates the ocarina "after Step03"
  instead of "= Step04", to work with the door closed or open. Door open (On) and door closed + empty moat (Off)
  validated **[game]** (2026-11-10); moat ocarina with the 3 stones not tested yet with the native menu.
- Rauru: the first sword pull checks `HavePlayedEvent.Dm_TimeTemple_0040`; marked as seen -> direct travel, the
  reward in Link's pocket is given at the start **[game]**.
- Returning to child: `Market_Adult_Prefab_89da` requires `SageOfForest_IsCompleted_Exp` (Forest Temple done).
  Replaced by an always-true expression if `free_time_travel` **[game]**. Native menu: the module reads
  `OoTRR_FreeTimeTravel_Exp` (saved flag `OoTRR.FreeTimeTravel`, set by the menu, OR
  `SageOfForest_IsCompleted_Exp`) **[game]** (2026-11-10).
- `ReplaceEquipmentForEraChange` equips the Kokiri Sword when going back to child even without owning it: guarded
  by a pouch query (`_guard_era_sword`) **[game]** (2026-11-12).

## Child Zelda and day / night cycle

- Meeting Zelda (`Goto_HyruleCastle:Goto_HyruleCastle_MeetZelda`) moves the quest `Goto_HyruleCastle` to `Complete`
  (enum hash 3683238313, found in `Goto_HyruleCastle_IsCompleted_Exp`) and `DoorOfTime` to `Step01`.
  `skip_child_zelda` (and the open door) set these states at the start, so that time flows as after Zelda
  **[files]**; this was not enough: see `HyruleField_ArriveEntrance` below.
- **Frozen light in the child field [files]**: `WorldParam/HyruleField_Child` has a `ConditionEnvTimePalette`
  (`GameDataCondition: HyruleField_ChangeENV`) towards `MainField_Bluesky_First` (`Pack/EnvPalette.pack`), copy of
  `MainField_Bluesky` with `IsForceMainLight: true` (fixed sun, elevation 18°): while the flag is true, the lighting
  no longer follows the time. Set true when leaving the forest (`Goto_HyruleCastle:KokiriForest_ArriveLostWood`,
  step 182), reset to false by the owl at the field entrance (`Goto_HyruleCastle_Kaepora_00`, step 181, then
  `Event_RebuildConditionEnvTimePalette`). The owl is only requested (module `HyruleField_Child_Prefab_de5f`: player
  in the area, `Dm_HrlField_0010` not seen, quest `Goto_HyruleCastle` at Step01) in a normal game: step 182 is
  skipped (`world.FIELD_FIRST_PALETTE_STEP`).
- `IsWorldTimeStop` / `IsDisableTimeProgress` are event settings (EventSetting), not a global state.
- **Time only flows after `HyruleField_ArriveEntrance` [game, native trace]**: 0x345c020 freezes the time unless
  `Meet_DekuTree` is at Ready, or `HyruleField_ArriveEntrance` is true and `HrlField_HasEnteredFirstTime_Adult` false
  (set by `Dm_TimeTemple_0055`, cleared on arrival in an area by `Dm_SY_BancChangeArrive`). Frozen time = time
  requests ignored (Sun's Song: visual night only). The flag comes from the owl (`Goto_HyruleCastle_Kaepora_00`): set
  at the start, **validated in game** (2026-11-12). Observed speed: about 2 game minutes per second.

## Age and starting point

- Changing era (`Market_Child_Field_ChildToAdult` / `Market_Adult_Field_AdultToChild`) = sub-flow
  `ReplaceEquipmentForEraChange`, flag `Sequence_IsChildhood` (true = childhood), then `EventReserveBancChange`
  towards the other era's map (`Market_Adult` / `Market_Child`) **[files]**.
- Adult start: `Sequence_IsChildhood` false at the start, teleport to the Temple of Time (`Market_Adult` /
  `LightPrelude`), `Weapon_Sword_Master` given; Door of Time open and free time travel forced (otherwise the child
  is only reachable after the Forest Temple, itself unreachable without Saria's Song learned as child) **[files]**
  (to test in game).
- Spawn points: `StartPos` actors (`Name` field) of the maps; selected list in `data/spawns.json` (33, outside
  dungeons). Native menu: the intro reads the integer `OoTRR.Spawn` (written by the module at generation) and
  reserves the matching map change **[files]**. The `random_spawn` setting was removed (the logic
  assumed a fixed start); the list still serves the adult start.
- **`EventQueryGameDataIntBranch`: 16 cases at most (strong hypothesis).** With 34 cases, value 22 led to case 15
  (seen in game: arrival in front of Jabu-Jabu instead of the Temple of Time). The spawn point now goes through two
  queries (tens `OoTRR.SpawnTens`, units `OoTRR.SpawnUnits`). Deku Scrub prices (20 values) too:
  `OoTRR.Price.<token>` (tens) and `OoTRR.PriceUnits.<token>` (units) of price / 5 **[files]**.
- Starting consumables **[game]** (2026-11-11): the maximum quantity comes from a bag (`ExpansionMaxNumActor`:
  `Item_StickBag_Small` 10, `Item_NutBag_Small` 20; maximum 0 without a bag). Adding the item does not count its
  quantity: small bag, then the item, then the stock written to `PouchData.<item>.StockNum`.
- The logic assumes that Root (back to the starting point) stays reachable, as for Link's house (not verified: the
  remake may resume the game where it was saved).

## Boss rewards

- Given by scenes that name the item: `Dm_Kokiri_0130` (emerald), `Dm_DeathMtTrail_0025` (ruby),
  `Dm_ZoraFountain_0030` + `Dm_InsideJabu_Jabu_0030` (sapphire), `Dm_Awake_<X>_Get` (medallions, also in `.110`
  version). Replacing the name in these scenes changes the reward (validated for the emerald) **[game]**.
- Native menu: hook on the inventory add `0x110d570`; an event gift (reason 7) of an original reward is replaced by
  the seed's one. Validated for Link's pocket at the start (Light Medallion -> Zora Sapphire) **[game]** (2026-11-10);
  boss scenes: same mechanism, not tested. Disabled while giving starting items (otherwise a starting medallion was
  replaced as well) **[game]** (2026-11-12). Reasons seen: 7 = event, 8 = starting equipment (wallet, tunics).
- The Key Items tab and screen only open when an item of list 4 (spiritual stones) is obtained; the native module
  also opens them for a medallion (hooks 0xa6ab50 and 0x181160) **[game]**.

## Rainbow bridge

- Module `GanonCastle_Level_Field_00_Prefab_14ba`: the scene `GanonCastle_Adult_Field_Rainbow` (script
  `Defeat_Ganon`, moves the quest to Step01) triggers if `Defeat_Ganon_IsAfter_Ready_Exp` AND NOT
  `Defeat_Ganon_IsAfter_Step01_Exp`; the bridge (`Obj_GanonCastle_Bridge_A_01`) only exists once the scene is seen
  (`HavePlayedEvent`). **Only replace "Ready"** with the randomizer's condition: replacing both prevents the scene,
  hence the bridge **[game]** (native menu, "open" condition, 2026-11-10). Native menu: saved flags
  `OoTRR.Bridge.<condition>` set at the start.
- The game's BoolExp expressions: 26 elements at most; long conditions are split into sub-expressions (precaution,
  limit not verified).

## Boolean expressions (GameData `BoolExp`)

Postfix notation: `0` Bool flag, `10` another expression, `1`/`12` Enum (equal / from) followed by `2` value, `15`
integer + `16` constant (equality), `3` AND, `4` OR, `5` NOT. New ones can be added (not saved, the save size does
not change) **[game]**.

## Cutscenes

- `HavePlayedEvent.<scene>` true at the start -> the scene is considered seen **[game]**.
- Some scenes are played without a check (intro: `OpeningEvent` -> `Dm_Kokiri_0000/0030`): the step that plays them
  is skipped (`skip_event_steps`) **[game]**.
- Generated list: `ootrr/data/cutscenes.json` (`python -m ootrr.tools.cutscenes`).
- **Which cutscenes the player can skip (+ / X)** is decided per event in RSDB `EventSetting` (one row per event,
  `__RowId` = event name): its `EventSettingComponentList` (`Event/EventSetting/EventSettingComponentList/*.bgyml`,
  `$parent` lists inherited) must have the category `TimelineEvent`, and must not contain the component
  `SkipSetting/DisableSkip` (`IsDisableSkip: true`). Flowchart events (`FlowchartEvent`, `NPCTalk`...) are never
  skippable. Result: 100 skippable timelines; 8 timelines with `DisableSkip` (`Dm_Kokiri_0000` tapestry narration,
  `Dm_StaffCredit_0005`, `Dm_Title_*`) **[files]**. Lists in `cutscenes.json` (`game_skippable`, `game_no_skip`).
- A timeline is played by an `EventSystemActor.EventTransition` step of a parent script (`EventName` = the scene,
  `FadeInTypeEventEnd` 2 = the parent fades back in itself, 0/1 = the timeline does). Timeline files (`Dm_*.bfevfl`
  without flowchart, plus `_Env` / `_Effect`) only hold presentation (camera, animations, voices, fades, environment
  `EventWorldManagerController`), except: `EventTrigger_SetTime` (`Dm_HrlField_0005/0060`, `Dm_Kakariko_0030/0040`,
  `Dm_ZoraFountain_0020`), boss music (`*_BossIn`), heart refill and Navi (`Dm_InsideGanonCastle_BossIn`), credits
  **[files]**. After a transition, parents often ask `EventQueryIsEventSkipedMostRecent` (camera reset only).
- `HavePlayedEvent.<timeline>` is read by maps (presence), logic modules (`HoldGameDataHavePlayedEvent` by
  `EventName`), AI schedules and scripts: e.g. `Dm_Kokiri_0050` (Kokiri Forest), `Dm_LakeHrl_0020` (lake water),
  `Dm_DodongoCave_BossOut` (Gorons), `Dm_Kakariko_0025` (Death Mountain) **[files]**. So a skipped timeline must still
  set its flag.
- `skip_cutscenes=safe` (and the in-game menu): in each parent script, the transition step of a skippable timeline is
  replaced with `HavePlayedEvent.<scene> = true` (+ a fade-in when `FadeInTypeEventEnd` != 2), see
  `ModBuilder._skip_timelines`: 73 scenes in 19 scripts (boss defeats, sages' awakenings, Ganon's castle, Epona,
  Sun's Song, Door of Time...) **[files; to validate in game]**. Still played (`timeline_kept`): ending and credits,
  the last two Ganondorf / Ganon fights, `Dm_InsideGanonCastle_0110` (AI schedule), and the five scenes that set the
  time. Scenes already marked as seen at the start (`skippable`, Rauru, Kaepora...) are not touched.

## In-game menu (title sequence)

- Option rows of type 13 (OcarinaKeyAssign) are used as buttons ("Next Page" / "Start the Game"). A button row does
  not go through TrigA: the native module records type 13 (`SeqQueryGetSelectedOptionType`, 0x32f97a0) and injects B
  for 30 frames in `SeqQueryControllerTrigMaskChecker` (0x7550b0) **[game]**. The player's B sets
  `OoTRR.MenuBack`, read by a selector after each page in `Sequence/NormalTitle` **[game]**.
- `UI_IsFinishChallengeMenuOpenEvent` unlocks the Threads of Time tab **[game]**.

## Pitfalls met

- Changing an actor's type through `Gyaml` (heart -> chest): nothing appears. A chest copied into a static map
  (`Obj_TBox_A_01_NoBake`) could not be opened.
- A copy of the Heart Container that gives HP (custom Piece of Heart) blocks the game.
- `insert_flow`: `set` only writes **strings**. An integer parameter (e.g. `Num` of `EventQueryIsExistInPouch`)
  receives the string's address (`Num = 12304`): keep the template's value. Query answers: 0 = yes. Always re-read
  the produced script with `tools.events` **[files]**.
- Jumping from a copied step to an event of another entry point (parallel branch) crashes the script engine: copy
  the needed event instead (`copy_event`) **[game]**.
- Texts of a layout's panes (e.g. `Pa_AmiiboBtn_00-T_BtnTitle_00`): read by 0xa6b250 (message file already loaded),
  not by 0xa6afe0 / 0xa6b060 **[files, Ghidra]**.
- An actor in a logic group (AiGroups) may ignore its presence condition depending on the module; test it.
- PowerShell 5 adds a UTF-8 BOM with `Set-Content -Encoding utf8`: breaks JSON files.
- Windows paths too long: build in a temporary folder then copy.

## Leads not followed through

- **In-game** settings menu: done with native code (exlaunch), see `native/README.md`.
- **Maps and compasses "at the start": validated in game (2026-11-10, native menu).** The map stayed "???" (even the
  one from a real chest) because the arrival scenes, marked as seen, are the ones that **discover** a location
  (`EventTriggerOpenLocationUI`) when RSDB `Location` `IsShowLocationUIFirstTimeInDemo` is true (33 locations out of
  36): field set to false with `skip_cutscenes=safe` (`World.rsdb_changes`), the location is discovered on first
  entry. The native menu also gives the map and compass on entering the dungeon (functions of the
  `OneShotDungeonGetMap` node, `0x3282fe0` / `0x3283060`).
