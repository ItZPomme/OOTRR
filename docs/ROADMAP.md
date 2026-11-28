# Remaining work

By priority. Each item: current state -> next step.

## In-game test feedback (fix as we go)
Bugs and improvements found during test sessions. Tick when fixed **and** validated in game.

### Bugs
- [x] Shadow Medallion "not obtained" when starting with it: it was given but invisible (Key Items tab locked, see
  Menu), and a second medallion was added: PouchAdd took the item from Link's pocket for Bongo Bongo's original
  reward and replaced it (Forest on top of Shadow). Replacement disabled while giving starting items; **validated in
  game** (2026-11-12: only the Shadow Medallion).
- [x] The logic assumed a start in Zora's Domain: random spawn disabled, then the `random_spawn` setting removed
  (Python, native, app; 2026-11-14); the "Random Spawn" row is removed from the menu. **Validated in game** (2026-11-12: start in the forest,
  row absent from the menu).
- [x] Infinite shop: **fixed and validated in game** (2026-11-12, Kokiri shop). Saved integer `OoTRR.ShopSold` (one
  bit per token item, reset to 0 at generation); first purchase = seed item; afterwards the item costs 999 rupees
  (the shop only re-reads the price when the area reloads) and a repurchase in between gives nothing and refunds.
  **No "Coming Soon" / "Sold out"**: 4 attempts crashed the shop loading (null pointer at 0x612850, generic BYML
  reader): `Release` added to an item that had none (Goron), "sold out" keys added (Kokiri), then even with only
  the original keys (`IsCheckReleaseGameData` true, `ReleaseGameData` = new expression) and 32 `OoTRR.Sold.<token>`
  flags added to GameData. Undecided leads: the 32 saved flags, or a condition referring to GameData added by the
  mod. To try separately.
- [x] Day/night cycle: **fixed and validated in game** (2026-11-12, new game: time flows, the Sun's Song changes the
  time; native time trace). 0x345c020 ("time frozen?", read by the time advance 0x3cdf70) answers "free" only if the
  `Meet_DekuTree` quest is Ready, or if `HyruleField_ArriveEntrance` is true and `HrlField_HasEnteredFirstTime_Adult`
  false; otherwise time stops and time requests (Sun's Song) are cleared without being applied (observed: 6:00 for
  the whole game, 0:00 and 20:00 requests ignored). `HyruleField_ArriveEntrance` is only set by the owl scene at the
  field entrance (`Goto_HyruleCastle_Kaepora_00`, step 132), never played with skipped scenes or skipped Zelda. Fix:
  flag set at the start, all settings (`world.TIME_FLOW_FLAG`). Also: step 182 (`HyruleField_ChangeENV`, "First"
  palette with forced sun) stays skipped. "Time" object: `*(*0x4c7e898)+0x510` (+0x28 seconds of the day, +0x48
  requested time, bit 1 of +0x08 = request); 0xeee640 requests a time; normal advance also depends on
  `HavePlayedEvent.Dm_HrlField_0020` (otherwise pulled back towards 15:00). The diagnostic trace (hooks on 0xeee640
  and 0x3cdf70) was removed; redo it from these addresses if needed.
- [ ] Heart Containers obtained from a token only count at the next age change: the native module now increases
  `PlayerStatus.MaxLife` (+4 quarters) and restores health (`AddMaxLife`, compiled, **to validate in game**; bosses
  and original containers untouched).
- [x] Kokiri Sword given back when returning to child: `ReplaceEquipmentForEraChange` equipped the Kokiri Sword even
  without having it; guard added (`_guard_era_sword`: query "Kokiri Sword in pouch?", otherwise empty weapon). The
  first version was wrong (re-read with `tools.events`): `Num` overwritten by `set` (integer written as text: 12304)
  and answers inverted; fixed (template `Num` = 1, 0 = yes -> equip). **Validated in game** (2026-11-12: without the
  sword, returning to child does not give it).
- [x] Shuffled songs: the original song also appeared in the ocarina list (observed). **Verified in the files**: the
  12 gifts of `Dm_SY_Ocarina` (steps 26-31, 32-38) are all replaced; the other mentions of `Item_Melody_*` (NPCs,
  `Dm_SY_Ocarina_SariaSong`) are not inventory actions — **except** the scenes' `GetPouchContentByActorName`, which
  does add the song (PC mod: Malon gave Serenade + Epona's Song; now retargeted to `DisplayGetByActorName` with the
  seed's item, verified in the files, to test in game); in the code, `Item_Melody_%s` is only
  used for the sound (0x323f420) and the icon (0x33bff00). Native countermeasure: any direct `Item_Melody_*` add is
  ignored when `shuffle_songs` != vanilla, except starting items and **a song placed in a chest**; log lines
  "chant d'origine ignore, raison" / "chant d'un coffre accepte". **Validated in game** (2026-11-12: only the seed's
  song is given).
- [ ] Talon in front of the castle: presence tied to `DoorOfTime_IsAfter_Step01_Exp` (like Impa), so absent with
  skipped Zelda or open door (`TALON_CASTLE`, built, **to validate in game**).
- [x] Invisible wall at the start of Zora's River: **original game behaviour** (clarified by the tester): the rocks at
  the entrance (`Obj_BrokenRock_A_01`, `ZoraRiver_Child` map only; already broken as adult) block the way until
  they are blown up. The logic already requires it (`ZR Front` -> `Zora River`: `is_adult or has_explosives`).
  Nothing to fix.
- [ ] Skulltula token in a shop: Deku Shield model. **Cause found in the code**: `TokenModelPath` passed the item
  through `GroundItem` (`Obj_Token_Gold` -> `Item_Token_Gold`, name used for texts) before looking it up in
  `kGroundModels`, which only knows `Obj_Token_Gold`: no model, so the base one (shield). Fixed (name as is first),
  compiled, **to validate in game** (also applies to a gold token on a freestanding heart).
- [ ] Fire Arrow check (`LH Sun`, Lake Hylia): missing from the spoiler because the location had no gift mechanism
  (neither chest nor token), so it was never shuffled. **Added in the files**: the arrow is an item lying on the
  water (`Obj_Arrow_Fire`, hash 4598657944866228526, map `HyruleField_Adult_Static`), created by the module
  `HyruleField_LakeHylia_Adult_Prefab_5313` (quest `SubEvent_GetFireArrow`, shot into the sun, time window). New kind
  of location `pickup: "item"` (+ `actor`): shuffled with `shuffle_gifts`, the actor becomes a token (copy of
  `Obj_Arrow_Fire`) like freestanding hearts, "ground" items only. Always in the spoiler. Native generator identical
  to Python; **to validate in game** (also depends on the day/night cycle).
- [ ] Shadow Temple giant pot: with shuffled small keys and `key_locations=ground`, the vanilla key pickup is now a
  ground check and appears in the spoiler (verified in the generated patch and RomFS build, **to validate in game**).
  Room 13's combat shutter is linked to the four Keese; a report says it blocks entry on a fresh save, not reproduced
  in game and not changed.
- [x] Exit of Dampé's grave: the Hookshot is required to leave the arrival room and it is in the race chest.
  `ModBuilder._dampe_exit`: after the chest (state `OpenedHookShot`), without Longshot or Hookshot, talking to Dampé
  runs a standalone copy of the fall's area change (step 70: `Graveyard_Adult`, point `4`) then ends the script. A
  direct jump to step 71 (other entry point, parallel branch) crashed the script engine. **Validated in game**
  (2026-11-12).

- [ ] Cutscenes the game lets the player skip (+ / X) are never played (`skip_cutscenes=safe`, always on in the
  menu): extracted from RSDB `EventSetting` (category `TimelineEvent` without `SkipSetting/DisableSkip`), 73
  timelines replaced with their `HavePlayedEvent` flag in 19 scripts (see GAME_KNOWLEDGE "Cutscenes"). Built and
  re-read in the files; **to validate in game**: Gohma defeat (`Get_StoneOfForest`), Saria outside Link's house
  (`Dm_Kokiri_0045`, fade-in), Darunia (`Get_StoneOfFire`, fade-in), a sage awakening after a temple
  (`Dm_SY_BancChange_EscapeDungeon`, medallion), Epona, Sun's Song at the royal tomb, Door of Time / Master Sword,
  Ganon's castle barriers. Still played: ending, credits, last Ganondorf / Ganon fights, 5 scenes that set the time
  (`EventTrigger_SetTime`: to reproduce in the parent script before skipping them).

- [ ] "Logic" setting (page 3 of the menu, `logic`): Glitchless (the current logic) or No Logic (random placement,
  placement constraints kept, no beatable check; spoiler marked "not beatable"). Python and native generators
  identical (`native_check`, 2 no-logic presets); **to validate in game** (menu row, seed generated).

#### Reported 2026-11-27 (in-game test)
- [x] Goron / Zora Tunic in a chest: the chest could not be opened. Cause: the rolling Goron and King Zora gifts had
  the logic-only aliases `Goron_Tunic` / `Zora_Tunic` as vanilla item (no such actor), so with shuffled gifts a chest
  got `Drop__DropActor = Goron_Tunic` (the menu mod build even crashed on `Pack/Actor/Goron_Tunic.pack.zs`). Vanilla
  items are now `Armor_Adult_Goron` / `Armor_Adult_Zora` (`overworld.json`). **Validated in game** (2026-11-27,
  Fritchii: both tunics from Mido's chests).
- [x] Lake Hylia owl (flight to the field) is gone. First fix (actor presence `Dm_TimeTemple_0086`) was not enough
  (still absent in game, 2026-11-27). **Real gate [files]**: logic module `HyruleField_LakeHylia_Child_Prefab_32f1`
  creates it only while `Goto_HyruleCastle_IsCompleted_Exp` (child Zelda met) AND (lake visited OR ...) AND NOT
  `Dm_TimeTemple_0086`. The quest test is replaced with an always-true expression (`world.LAKE_OWL_MODULE`). **Validated in game**
  (2026-11-27, Fritchii, child Link at the lake without meeting Zelda).
- [x] Beds do not let Link choose day or night. **Cause found in the files**: `LinkSleepInBed:EntryPoint0` (Link's
  bed, event 13) and `CommonBed` (other beds, events 85 and 131; the Lon Lon Ranch bed still had no choice with only
  event 13 changed) offer the choice only after child Zelda (`HavePlayedEvent.HyruleCastle_Goto_HyruleCastle_MeetZelda`), otherwise
  `SleepBeforeMeetZelda` without a choice. The test now reads `UI_IsFinishChallengeMenuOpenEvent` (true from the start;
  `world.BED_STRINGS`). **Validated in game** (2026-11-27, Fritchii, Lon Lon Ranch bed).
- [x] No Hyrule Field music when leaving the forest. **Cause found in the files**: the forest exit
  (`Goto_HyruleCastle:KokiriForest_ArriveLostWood`, step 89) stops the in-game BGM (`CommandLife 0`); only the owl at
  the field entrance (`Goto_HyruleCastle_Kaepora_00`, step 96) starts `BGM_HyruleField` again. Skipping step 89
  alone was not enough (still silent in game, 2026-11-27; the fade near the bridge is vanilla: scenery
  `Area_KokiriForest_Bridge` has no `BgmName`). The owl event was never requested because `Dm_HrlField_0005/0010` were
  marked seen at the start (`EXTRA_SKIPPED`); they are now replaced with their flags inside the owl script
  (`world.FIELD_OWL_SCENES`), so the event runs at once without cutscenes (BGM, quest Step02, Navi balloon, the "Threads of Time"
  tutorial frame). **Validated in game** (2026-11-27, Fritchii, open forest). Still open: settings where the castle quest does not start at Step01 (skipped Zelda / open
  door with a closed forest) never request the owl.
- [ ] Key Items tab still unavailable without a child stone (any one): re-reported, see "Menu / settings" below.

#### Reported 2026-11-28 (Longshot, multiworld)
- [ ] Bow without a quiver: a progressive Medium Quiver from the Kakariko roof man (Willx, mw 0AEF6F9822) gave the bow
  at 0/0 (the Ice Arrows he also had were real: DC Map Chest; the bow's in-game name is "Fairy Bow"). **Cause [game,
  Longshot memory reads]**: a script adding `Item_Range_Bow` (`EventTriggerAddOrRemovePouchContent`: progressive gifts,
  ground item fixes, starting items) gives `Weapon_Range_Bow` only, no `Item_Quiver_Small`, 0 arrows; a chest gives the
  bow correctly. Fix (`modbuild.SMALL_CONTAINERS`): those scripts add the small quiver / seed bag right after the weapon;
  starting items verified in Longshot (quiver + 30 arrows), progressive gift verified in the files (roof man: bow, then
  quiver). **To validate in game** on a real gift. Not covered: a bow or slingshot given as placed by a non-progressive
  gift (only when a chain copy sits where nothing progressive is possible).

### Shuffle to extend
- [ ] Minigames: shuffled rewards (Slingshot, Bow, etc.).
- [ ] Man on the roof (Kakariko) and gravedigging tour (child Dampé): added to the gifts (`gifts.json`:
  `Npc_Hylia_001_Adult` step 14, `Npc_Hylia_Dampe_001` and `.110` step 602; the Piece of Heart that comes out of the
  ground stays visible), **to validate in game**.
- [ ] Biggoron (Claim Check) gives a seed item (location "DMT Biggoron", Biggoron Sword in the pool) and
  `adult_trade_sequence` puts the vanilla trade quest in the logic: **to validate in game** (another item given by
  `GetInEventItemSwordBiggoron`; the quest with a Pocket Egg found in a chest). Later: shuffle the trade items.
- [ ] Shuffled checks giving bottles: Anju, market potion shop, 5 Big Poes, Talon and Ruto's letter (on the lake
  floor) are locations shuffled with `shuffle_gifts` (see GAME_KNOWLEDGE, "Bottles"), **to validate in game**
  (especially the letter given from elsewhere and the King Zora quest).
- [x] Market potion shop: the bug-catch tutorial locked Link inside without a bottle (seen in game); the PC-built and
  menu mods now skip it after the gift (GAME_KNOWLEDGE, "Potion shop bug tutorial softlock"). **Validated in game**
  (Longshot, 2026-11-21, PC-built mod, gift = Piece of Heart, no bottle): the door opens after the gift
- [ ] Shuffled Light Arrow cutscene.
- [ ] Shuffled Great Fairy checks (fountains).
- [ ] Shuffled Goron Bracelet.
- [ ] Shuffled checks giving scales, adult fishing and diving (minigames).
- [ ] House of Skulltula rewards (Kakariko): absent from the data, since Gold Skulltula tokens have no logic item
  yet (a location must always be reachable, so `False` is refused). **[files]** Script `GatheringTokenGold`, entry
  `TokenCheck_Reward`: 10 `Item_Wallet_Medium`, 20 `Item_AgonyStone`, 30 `Item_Wallet_Large`, 40
  `Item_BombchuBundle_Large`, 50 `Obj_Heart_Piece` (map icon `KakarikoVillage_IsAfterSave_Npc_Hylia_025`), 100
  `Obj_Rupee_Gold`.
- [ ] Heart pieces given by scripts and minigames, fixed today (no hash, not shuffled), found in the files through the
  `HeartPieceAnchor` map icons (`HeartPieceAnchor_GameDataPath` = the flag set when it is obtained): Skull Kid,
  Skull Kid memory game, treasure chest game (chest `Obj_HrlCity_Shop_TBox_A_02`, hash 16881481538337649070),
  bombchu bowling, lost dog, child fishing, lab dive (`Npc_Hylia_045_Child`, a **child** diving challenge: the rule
  is probably wrong), frogs (two), horseback archery, Goron City pot. Gerudo Valley waterfall: own actor
  `Obj_GerudoValley_Heart_Piece` (hash 16129198288828948135), not linked to its location yet. No heart piece
  actor exists for the old HF Tektite grotto, Lon Lon Ranch and Ice Cavern locations (removed on 2026-11-16).
- [ ] Zelda's Lullaby in the pool (starting song with skipped child Zelda and random songs): already the case in the
  generator (`Song from Impa` is a shuffled song location and the start gives the item found there; verified on 8
  Python seeds); **to validate in game with the menu**.

### Menu / settings
- [ ] Key Items tab: the game previously hid it until a stone or medallion was obtained (the gated behavior was
  **validated in game**, 2026-11-12). The native tab-title hook (0xa6ab50) now keeps tab 6 visible from the start;
  the separate content hook (0x181160) is unchanged, so the screen may still say "Unavailable right now" before a
  reward. With the native module, a medallion alone opens the tab: **validated in game** (2026-11-27, Fritchii, child
  Link with only the starting Light Medallion; log "Key Items ouvert (recompense obtenue), appel 0xa694dc"). The
  2026-11-27 report "unavailable without a child stone" comes from Longshot (below).
- [ ] Key Items tab on Longshot (no native module): still "Unavailable right now" until a child stone is owned
  (reported 2026-11-26 and 2026-11-27). The test is in the game's code, not in data **[files]**: tab 0xa69220 and
  screen 0x33dd6b0 walk list 4 (0xa6f690 -> 0x3397ac0, item names hard-coded in `main`: `Item_Stone_*`,
  `Item_Medal_*`) and call 0x181160 ("obtained?") at 0xa694d8 / 0x33dd828; `Sequence/ImportantMenu.module.ainb` only
  sets the pouch display type 4, stones and medallions have identical `PouchActorInfo` rows. A code patch (both calls
  -> `mov w0, #1`) would fix it, but Longshot only loads RomFS mods (no `exefs`, IPS or `subsdk` in `longshot.exe`,
  v3.2.0). Needs code-patch support in Longshot; writing an `IsGet` flag of a stone would break the logic.
  **Tested in Longshot 2026-11-27** (control pipe, OoTRR-essai, new game): `IsGet.Item_Medal_Light` true, no stone ->
  tab "???" and "Unavailable right now", as child and as adult (`age age=adult`). So the walked list holds the three
  stones only, for both ages. 0x181160 reads `IsGet.<name>` (murmur3 of the name, member of GameData struct
  0xade0ef78); no `GameActorInfo` / `PouchActorInfo` field redirects it [files].
- [x] Threads of Time tab: `UI_IsFinishChallengeMenuOpenEvent` is set at the start (validated in game). The
  "MsgNotFound" in Threads of Time (skipped quest steps) remain to look at.
- [x] Menu: end-of-page button and navigation, **validated in game** (2026-11-12). "Next Page" / "Start the Game"
  title: `MessageInFile` hook (0xa6b250, texts of `Pa_…` panes); right-hand state "Press A"
  (`<prefix>ZeldaNote_00/01`). Press: a button row does not go through TrigA; the screen detects it and the script
  goes to the button switch, which reads the type (13 = OcarinaKeyAssign); changing the graph was not enough: the
  native module records type 13 (`SeqQueryGetSelectedOptionType`, 0x32f97a0) and injects B for 30 frames
  (`SeqQueryControllerTrigMaskChecker`, 0x7550b0: TrigA node + 0x28, TrigB + 0x30). Player's B = previous page (main
  menu from page 1): `OoTRR.MenuBack` flag set by the module, read by a selector added after each page in
  `Sequence/NormalTitle` (`title_sequence`); the displayed page follows (-1 / +1).
- [ ] Bridge condition: required number chosen at the top of page 2 (see "Rainbow bridge"); menu **validated in
  game**, bridge opening at the chosen number to check.

## Multiworld, then coop
See [`MULTIWORLD.md`](MULTIWORLD.md). Done: shared fill over several worlds (`ootrr/multiworld.py`), protocol and relay
server (`ootrr/tools/mw_server.py`), per-player mod (`tools/mw_mod.py`) and the Longshot bridge
(`tools/mw_longshot.py`): **validated in game** in Longshot v3.0.0 (2026-11-20: a found chest reaches the server,
received items given and kept after save + reload). The file-verified pouch-action dispatcher now routes received
Gauntlets and ocarinas through the game's add-to-pouch action; **to do**: validate that test in game, including Silver
Gauntlet lifting and ocarina D-pad assignment after reload. Also test Heart Containers / Pieces received in Longshot
(max life is rewritten every frame), validate the Bow + small-quiver fix when an upgraded quiver arrives first,
check other item kinds (bottles, seeds, songs, swords, magic), GOAL detection,
a player on another network (room code + UPnP: validated on one PC only, 2026-11-21), the Eden client in the native
module (`nn::socket` from sdk), then coop. The desktop app's Multiworld window (host with a room code, join, install
and play) is validated in game on one PC.

## Deku Scrub salesmen (scrubsanity)
- Mechanism validated in game (a Deku Scrub sells any item, message in the game's language).
- **To do**: inventory of the ~35 Deku Scrubs (`Enemy_Scrub_Business` in the child and adult maps, with their
  hashes), region and rule of each in `ootrr/data/world/`, `shuffle_scrubs` setting, prices (the game's or fixed).
  Current test option: `--test-scrub HASH=ITEM:PRICE`.

## Gold Skulltulas
- Replaceable drop validated in game.
- **To do**: the 100 locations in the logic (area, age, tools), `tokensanity` setting, then the `tokens` bridge (the
  value `PouchData.Item_Token_Gold.StockNum` is known).

## Shops (shopsanity)
- Native menu: 4 items per shop (8 shops), setting 0 to 4, prices Vanilla / Affordable / Random; validated in game
  in the Kokiri shop.
- **To do**: check the other shops, the single sale after saving, the item model that goes through the shelf, the
  Python version (mod without menu), and wallets in the logic for prices above 99.

## Rainbow bridge
- Conditions implemented (open, vanilla, stones, medallions, dungeons, hearts): **to test in game**.
- Native menu: required number chosen on page 2 (stones 1–3, medallions 1–6, rewards 1–9, hearts 3–20), rows shown
  depending on the condition: **validated in game** (2026-11-12). Still to check in game that the bridge opens at
  the chosen number for each condition.

## In-game questions ("menu" at launch)
- Prototype: `open_forest=ask` (yes/no question at the start of the new game) — **to test**.
- Extend to settings that can be decided during the game: cutscenes, Door of Time, bridge condition (expressions
  that read an answer flag), starting items. Translate the questions.

## Miscellaneous
- `blue_fire_arrows` (Ice Arrows act as Blue Fire): done, PC-built mod only, validated in game (generator-built
  mod, King Zora). To do: the native menu (its mod is built once: the arrow and red ice AIs would have to be in it
  and read the setting), the Ice Cavern red ice one by one with the generator-built mod, and the arrow-side
  countdown of the timer (not validated in game).
- Deku Tree falling floor of the Slingshot room (stays up, PC-built mod): validated in game
  (2026-11-24). To do: the native menu's mod.
- `ganon_boss_key` (Ganon's Castle boss key on its own: vanilla, removed, random or a condition): PC-built mod only, verified in the files, **to
  validate in game** (key given in the main room, door of Ganondorf's room, nothing given below the count, hearts).
- `skip_trials` (Ganon's Castle trials done from the start): PC-built mod only, validated in game (2026-11-23).
  To do: the native menu.
- `skip_tower_collapse` (Ganondorf -> Ganon's arena): PC-built mod only, validated in game (2026-11-24, with a test mod
  started at Ganondorf's door, up to the credits). To do: the native menu (a question before the map change of `Defeat_Ganon`); the retry after dying to Ganon, not reported yet.
- `complete_mask_quest` and `fast_bunny_hood` in the native menu (PC-built mod only for now).
- First-obtain animation of consumables: not removed (decided by the engine).
- Progressive items: done in the native menu (`ingame::AdjustItem`), **to validate in game** (each chain, and the
  bow / slingshot "owned" flags). PC-built mod: chests as `Obj_TBox_A_06` conditional chests (Hookshot chain and
  slingshot `CheckActor` validated in game; to validate: a converted big chest, a whole seed). Gifts: questions
  before the gift (validated in game, 2026-11-16). Not done in the PC-built mod: scrubs, ground items and
  Skulltulas (fixed items).
- Shuffled NPCs and songs (replacing the item name in their scenes — validated for one NPC).
- Small keys / boss keys (`small_keys`, `boss_keys`): done in the generator and the PC-built mod, verified in the
  files (tools `verify`, `events`), **to validate in game**: a key in its own dungeon's chest (counter), a key of
  another dungeon (door key + chest event `OoTRR_GetSmallKey_<dungeon>`, new script files), `removed` (counters and
  `IsGetBossKey` at the start: do the locked doors and the boss doors open?), the ground keys removed from the maps.
  Next: map the door layout of each dungeon (locked doors per room) to replace the prudent logic, a proper text for
  a boss key found elsewhere, the native menu.
- Settings window on PC (simple alternative to the in-game menu).
- Native in-game menu (injected code, exlaunch): injection validated in game, see `native/README.md`.

## Play session of 2026-11-24 (multiworld, two players): still open

- [ ] Way back asked by Navi (softlocks: Gerudo Training Ground Lizalfos room, adult Spirit Temple room with the Beamos
  and 3 Anubis): question **validated in game** (GAME_KNOWLEDGE, "Way back"); to try in those two locked rooms.
- [x] Day / night only changed with the Sun's Song (`world.NIGHT_FLAG`): **validated in game** (2026-11-25, new game). To
  try: an older save (flag set by the next change of age, read in the script).
- [x] Maps as adult (`world.ADULT_MAP_FLAG`): **validated in game** (2026-11-25).
- [ ] Rolling Goron after the Fire Temple's quest steps (GAME_KNOWLEDGE).
- [ ] To validate in game: everything GAME_KNOWLEDGE dates 2026-11-25 or [files] for this session.
