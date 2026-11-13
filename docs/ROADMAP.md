# Remaining work

By priority. Each item: current state -> next step.

## In-game test feedback (fix as we go)
Bugs and improvements found during test sessions. Tick when fixed **and** validated in game.

### Bugs
- [x] Shadow Medallion "not obtained" when starting with it: it was given but invisible (Key Items tab locked, see
  Menu), and a second medallion was added: PouchAdd took the item from Link's pocket for Bongo Bongo's original
  reward and replaced it (Forest on top of Shadow). Replacement disabled while giving starting items; **validated in
  game** (2026-11-12: only the Shadow Medallion).
- [x] The logic assumed a start in Zora's Domain: random spawn disabled (`RANDOM_SPAWN_ENABLED = False`, Python and
  native); the "Random Spawn" row is removed from the menu. **Validated in game** (2026-11-12: start in the forest,
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
  12 gifts of `Dm_SY_Ocarina` (steps 26-31, 32-38) are all replaced; the other mentions of `Item_Melody_*` (scenes
  `Dm_MelodyGet_*`, NPCs, `Dm_SY_Ocarina_SariaSong`) are not inventory actions; in the code, `Item_Melody_%s` is only
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
- [x] Exit of Dampé's grave: the Hookshot is required to leave the arrival room and it is in the race chest.
  `ModBuilder._dampe_exit`: after the chest (state `OpenedHookShot`), without Longshot or Hookshot, talking to Dampé
  runs a standalone copy of the fall's area change (step 70: `Graveyard_Adult`, point `4`) then ends the script. A
  direct jump to step 71 (other entry point, parallel branch) crashed the script engine. **Validated in game**
  (2026-11-12).

### Shuffle to extend
- [ ] Minigames: shuffled rewards (Slingshot, Bow, etc.).
- [ ] Man on the roof (Kakariko) and gravedigging tour (child Dampé): added to the gifts (`gifts.json`:
  `Npc_Hylia_001_Adult` step 14, `Npc_Hylia_Dampe_001` and `.110` step 602; the Piece of Heart that comes out of the
  ground stays visible), **to validate in game**.
- [ ] Shuffled checks giving bottles: Anju, market potion shop, 5 Poes, Talon, Ruto's letter (which must also be
  shuffled).
- [ ] Shuffled Light Arrow cutscene.
- [ ] Shuffled Great Fairy checks (fountains).
- [ ] Shuffled Goron Bracelet.
- [ ] Shuffled checks giving scales, adult fishing and diving (minigames).
- [ ] Zelda's Lullaby in the pool (starting song with skipped child Zelda and random songs): already the case in the
  generator (`Song from Impa` is a shuffled song location and the start gives the item found there; verified on 8
  Python seeds); **to validate in game with the menu**.

### Menu / settings
- [x] Key Items tab: the game only opens it (tab 0xa69220 and screen 0x33dd6b0) if an item of list 4 (spiritual
  stones) is obtained: closed "???" / "Unavailable right now" with only a medallion at the start. Native hooks: tab
  title (0xa6ab50) and "item obtained" test (0x181160, only for these two calls) open as soon as a stone or a
  medallion is obtained; **validated in game** (2026-11-12). Threads of Time tab: `UI_IsFinishChallengeMenuOpenEvent`
  set at the start (validated in game). The "MsgNotFound" in Threads of Time (skipped quest steps) remain to look at.
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
- First-obtain animation of consumables: not removed (decided by the engine).
- Progressive upgrades in chests (mechanism of the A_06 chests with conditional content).
- Shuffled NPCs and songs (replacing the item name in their scenes — validated for one NPC).
- Small keys / boss keys: currently in their original location.
- Settings window on PC (simple alternative to the in-game menu).
- Native in-game menu (injected code, exlaunch): injection validated in game, see `native/README.md`.
