# Native code (in-game menu)

Module injected into the game with [exlaunch](https://github.com/shadowninja108/exlaunch) (GPL-2, copied from commit
`f9f4b0d`, see `exlaunch/LICENSE`), loaded as `subsdk9`.

## Status

- **Step 0 — validated in game (2026-11-10)**: Eden loads the module (`Module subsdk9 loaded`) and runs it
  (`OutputDebugString: OoTRR: module natif charge`, then a notification `svcBreak` with info1 = `0x4F6F545252`). The
  game continues normally.
- Since then: settings menu, seed generator, shuffled locations and many settings in the game (sections below).

## Reverse engineering: starting point

- `main` is compressed as "ZBIC" (Switch 2 format, not LZ4): `ootrr.tools.nso` cannot read it. The decompressed code
  is obtained with Eden's `dump_nso` option (Debugging section of `qt-config.ini`, also set `dump_nso\default=false`,
  Eden closed): a started game writes `%APPDATA%\eden\dump\0400486024DEC000\nso\main-<build id>.nso` (0x100 header +
  memory image, relocations already applied with base 0). Strip the header -> `output/native/main.bin`.
- Segments (build id E0F3CCFA…): `.text` 0 – 0x3c461d0, `.rodata` 0x3c47000 – 0x484c080, `.data` 0x484d000 –
  0x4d46b80.
- Disassemble: `aarch64-none-elf-objdump -D -b binary -m aarch64 --start-address=0x... main.bin`. References to a
  string or address: `python -m ootrr.tools.xref output/native/main.bin NAME --data`.
- The title screen is driven by AINB modules of the RomFS (`Sequence/`): `NormalTitle` (buttons
  `Pa_Button_00/01/02` = new game / load / options), `ConfirmationNewGame` (system window `TitleSystemWindow_00`,
  preset `NewGame`), `Option` (screen `SystemOption_00`, buttons `PaOptionBtn_00` / `PaOptionBtnLevel_00`). The nodes
  (`SeqQuery…`, `SeqOneShot…`, `SeqExecute…`) are C++ classes: each class has a method that returns its name (e.g.
  `SeqQueryGetSelectedOptionType`: name at 0x32f9880, vtable near 0x4bc9c68; `SeqOneShotOpenSystemWindow`:
  0x32d9360, vtable near 0x4bb4c80).
- Layouts: `UI/Layout2Archive/*.blarc.zs` (SARC of `.buil` files, undocumented Layout2 format). Options screen:
  `Common…blarc` / `SystemOption_00.buil`.

### Screens and sequence nodes (verified in the code)

- ~5,700 AINB node classes. In each vtable, only a few entries are specific to the class (referenced only once):
  parameter reading and execution.
- Nodes find a screen by the **MurmurHash3 of the layout name** (same hash as GameData): `FUN_033eb1d0(manager,
  hash)` or `FUN_029f9fb0(...)` (Ghidra addresses, base 0x100000). `SystemOption_00` = 0x87ebe934,
  `TitleSystemWindow_00` = 0xe1932d84, `SystemWindow_00` = 0x6d47deab.
- `SeqQueryGetSelectedOptionType`: reads `screen(SystemOption_00) + 0x370` (selected option).
- `SeqOneShotOpenSystemWindow` (parameters `Preset`, `IsTitle`): chooses the title or normal screen, converts the
  preset to a number (`NewGame` 0, `ResetOption` 1, `BackToTitle` 2, `BackToTitleFromGameOver` 3, `NewGameMQ` 4,
  `ReleaseMQ` 5) then calls `FUN_03505a00(screen, number, IsTitle)` (Ghidra).
- Options screen = class `UISystemOptionScreen` (code around 0x33ce000 – 0x3404000, relative). Fixed list of 17
  options (name table at 0x3f13800): IsCameraUpDownReverse, IsCameraRightLeftReverse, CameraRotateSpeed, IsUseGyro,
  IsChangeJumpButton, DisplayMode, IsDisplayTextRuby, MessageWindowTransparency, VoiceLanguage, LockOnType,
  OcarinaSongEstimateMode, OcarinaKeyAssign, VoiceSubtitle, VoiceSubtitleSpeakerName, ZeldaNoteState,
  ControllerRumble (+ amiibo). Texts: messages `LayoutMsg/SystemOption_00`, labels `%s_Title`, `%s_Caption`,
  `%s_00`…
- **The screen's rows come from a file**: `UI/OptionSetTable/OptionSetTable.game__ui__OptionSetTable.bgyml` (in
  `Pack/Bootup.Nin_Ounce_NVN2.pack.zs`). `OptionSetArray` = 20 rows `{OptionType, ButtonType, ChoiceType[],
  CheckGameData, IsCheckDisplayGameData}`; enums are hashes (ButtonType 1160613079 = separator, 3569415379 = choice,
  3166595148 = toggle…). In memory: option manager (global `+0x500`), 0x28-byte entries (+0 option type, +4 row
  kind: 0 toggle, 1 choice, 2 amiibo, 3 separator; +0x24 GameData condition). Access: `FUN_0349c5a0` (number of
  visible rows), `FUN_0349c630` (row i), `FUN_0349c790` (row by type). The behaviour of each option type stays in
  the code. **Validated in game (2026-11-10, experiment removed since)**: a reordered table / removed row in the
  Bootup pack and replaced `LayoutMsg/SystemOption_00` texts are accepted by the game.
- `UISystemOptionScreen` screen object: buttons per kind at `+0x2b8/+0x2c0`, `+0x2c8/+0x2d0`, `+0x2d8/+0x2e0`
  (button's option type at +0x54 / +0x58), displayed rows `+0x338/+0x340` (kind, index pairs), selected option
  `+0x370`. Construction: `FUN_035011c0` (Ghidra, 0x34011c0 relative) clones the templates `Pa_ToggleBtn_00`,
  `Pa_SelectBtn_00`, `Pa_AmiiboBtn_00`, `Pa_Separator_00`.

### Opening the menu after "New Game" (validated in game, 2026-11-10)

`Sequence/NormalTitle.module.ainb` (title screen graph, read and rewritten with the `ainb` library 0.2.17, GPL-2,
`pip install ainb`; change the object, not the dict/JSON, which breaks the string table at 0x408):
- node 1 (`Element_StringSelector`): `Pa_Button_00` -> 50 -> 49 -> 48 -> 2 `ConfirmationNewGame.module` ("Yes" -> 13
  game start, "No" -> 53 back to title); `Pa_Button_02` -> 52 -> 43 -> 9 `Option.module` (`IsTitleMenu` = true,
  "End" -> 53). 48 and 43 do the same preparation (hide the title screen).
- Change (`ootrr.ingame_menu.title_sequence`): copy of node 9 as node 74, 48 -> 74, "End" of 74 -> 2;
  `Option.module.ainb` goes to 2 instances. Result in game: New Game -> options screen -> B -> confirmation -> Yes =
  game, No = title.
- Useful failures: replacing `ConfirmationNewGame.module.ainb` with the options module just makes the menu disappear
  (input parameters missing); inserting the screen after "Yes" leaves the confirmation window displayed on top.

### Randomizer menu (validated in game, 2026-11-10)

`python -m ootrr.tools.menutest --romfs ROMFS --install` (mod `OoTRR-menu`, RomFS + exefs; data in
`ootrr/ingame_menu.py`, hooks in `exlaunch/source/program/main.cpp`).
- Flag `OoTRR.IsRandomizerMenu` (unsaved GameData entry) written by three nodes added to `NormalTitle`: true with the
  New Game preparation (48), false with the Options one (43) and at the start of the game (13). The hook of
  `0x682b00` / `0x32e6910` (execution of `SeqOneShotSetNonStructGameDataBool`, arguments node + hash; value at
  `**(node + 0x40)`) follows it.
- Table: `LoadOptionTable` (`0x339bc40`) loads a second table of ours; during this load, the hook of the resource
  loader `0xa57350` replaces the path. **This loader takes (manager, const char** path) and returns its result
  through x8**: the hook returns a non-trivial type to keep x8. The accessors `0x339c5a0` / `0x339c630` /
  `0x339c790` receive our table during the menu.
- Texts: `0xa6afe0` (output, `const char**` file, `const char**` label; 1 = found): `OoTRR_<label>` is tried first.
- Values: `0x9b3eb0` (manager, handle, hash): `OptionData` -> `OoTRRMenu` (copied GameData structure, unsaved
  entries, default values = `settings.py`). The player's options are not touched (verified in game).
- Layout: `0x43a0e0` (layout name in x4, 11 arguments): `SystemOption_00` -> `OoTRRMenu_00`, a copy where the amiibo
  template is invisible (bit 0 of the flags of a .buil element = visible, verified in game; the records number names
  from the start of the string pool, which begins with the page name, before `RootPane`). A template without a
  matching row stays displayed in place: the amiibo is hidden, and the table contains two separators (the template
  is used).
- Choices stored in the game (validated: re-read in progress.sav): the "setting" members of `OoTRRMenu` have
  SaveFileIndex 0 and ResetTypeValue 0; MetaData shifted by 8 bytes per entry (`ingame_menu.add_saved_entries`). The
  menu restarts from the default values after going back to the title.
- **Screen limits** (seen in game, 2026-11-11): option types come from a fixed table in the code (17 names,
  `0x3f13780`: `IsUseAmiibo` … `ControllerRumble`); a type absent from `OptionData` (`MessageWindowTransparency`)
  stores nothing, and a list only stores the values of its type in the game (added choices shown but lost). Values
  per type: VoiceLanguage 9, CameraRotateSpeed 5, DisplayMode / OcarinaSongEstimateMode / ControllerRumble 3,
  LockOnType / OcarinaKeyAssign 2.
- **Pages (validated in game, 2026-11-11)**: `NormalTitle` chains a copy of the options node per page; each page has
  its structure (`OoTRRMenu`, `OoTRRMenu2`…), its table and its text prefix (`OoTRR_`, `OoTRR2_`…). The module counts
  loads of the `SystemOption_00` layout during the menu to know which page is displayed (`menu_data.hpp`: `kPage*`).
  Each page must have at least one list, one toggle and one separator: a row template without a row of its kind
  stays displayed alone (seen).

### "Next Page" / "Start the Game" button (validated in game, 2026-11-12)

- In `Sequence/Option.module`, A on a button row (amiibo / Zelda Notes kind, `ButtonType` 320412644) leads to an
  `Element_S32Selector` switch on `SeqQueryGetSelectedOptionType`: 1 = amiibo (`Amiibo.module`), 16 = Zelda Notes,
  otherwise nothing. Option types (code table): 0 None, 1 IsUseAmiibo, 2 IsCameraUpDownReverse,
  3 IsCameraRightLeftReverse, 4 CameraRotateSpeed, 5 IsUseGyro, 6 IsChangeJumpButton, 7 DisplayMode,
  8 IsDisplayTextRuby, 9 MessageWindowTransparency, 10 VoiceLanguage, 11 LockOnType, 12 OcarinaSongEstimateMode,
  13 OcarinaKeyAssign, 14 VoiceSubtitle, 15 VoiceSubtitleSpeakerName, 16 ZeldaNoteState, 17 ControllerRumble.
- `ingame_menu.option_module` adds case 13 (OcarinaKeyAssign, unused by our pages): each page has a button row of
  this type at the bottom, titled "Next Page" (last page: "Start the Game"). The normal Options screen has no button
  of this type. Changing the graph alone was not enough: the native module records type 13 (hook on 0x32f97a0) and
  injects B for 30 frames in `SeqQueryControllerTrigMaskChecker` (0x7550b0: TrigA node + 0x28, TrigB + 0x30).
- Button title: hook on `MessageInFile` (0xa6b250, texts of the `Pa_…` panes); right-hand state "Press A"
  (`<prefix>ZeldaNote_00/01`).
- B from the player = previous page (main menu from page 1): flag `OoTRR.MenuBack` set by the module, read by a
  selector added after each page in `NormalTitle`; the displayed page follows (-1 / +1).

### Shops (validated in game, 2026-11-11: Kokiri shop, 0 / 2 / 4 items)

- Each shuffleable item stays in the map (present if `OoTRR.Shop<rank>` is false) with a token copy at the same place
  (present if it is true); the module sets these flags at the start. The merchant designates its items through
  `ForSale` and `Reference` links, and a link to an absent actor blocks the cursor (seen): one copy of the merchant
  per number n of shuffled items, present if `OoTRR.ShopCount<n>`, linked to the right items; the original merchant
  is used for 0.
- Merchant's list (`Component/ShopParam/…`, looked up by `0x32ade0`): variant `X_C<n>` chosen by the module
  depending on the number of shuffled items.
- Prices: the shop reads `BuyingPrice` in the actor's RSDB row `PouchActorInfo`, not in `PriceParam`. `0x5a7c60`
  fills a row (row, BYML node) at game start: +0 name (`__RowId`), +200 price (s32). The module records the address
  of each token's row and writes the settings' price there as soon as the seed is generated or reloaded (writing it
  when the shop loads is too late for some items, seen).
- Single sale (validated in game, 2026-11-12): saved integer `OoTRR.ShopSold` (one bit per item); after the purchase
  the price becomes 999 and a repurchase before the area reloads gives nothing and is refunded. "Sold out" signs
  crashed the shop loading (see ROADMAP).
- Deku Scrubs: the sale (`SimpleShopSub_Scrub_Business_OneTime`) displays and charges `SimpleShop_Price` but checks
  the wallet with the script's constant. The inserted script branches (`EventQueryGameDataIntBranch`, template
  `Minigame_CatchCucco`) on the integer `OoTRR.Price.<token>` (price / 5, unsaved, written by the module) towards 20
  copies of the sale (0 to 95 rupees).
- Pitfalls: base price 0 in the RSDB row, or `PriceOffset` / `ConditionalPriceOffsetList` offsets added to the
  merchant's list -> blocked while loading the forest.

### Placement during the game (validated in game, 2026-11-10: Mido's chests)

- The file mod puts a **token** `OoTRR_Lnnnn` in each shuffled location (Drop__DropActor). A token must be a **real
  actor** (copy of `TBox_Rupee_Green`, RSDB records copied): otherwise the chest does not offer to be opened.
- The chest creates its content in advance (actor holder, name read from its blackboard, itself filled from the map
  parameters). Replacing the copy of the "drop" component is not enough (the chest spawns the token -> blocked). The
  hook of `0xbd1c00` replaces **the value at the source**, in the dynamic parameters in memory, before the original
  call: `*(*(*(info+0x40)+0x270))+0x10` -> { u32 key count, const char** keys (+8), u32 value count (+0x10),
  const char** values (+0x18) }.
- Tokens are placed in the 134 shuffleable chests (`native_logic.chest_tokens`, index = rank in `logic_data.hpp`).
  "Drop" chest whose item changes: `GetEventName` emptied at the source; conditional chest: `Drop__CheckActor` and
  `Drop__DropActor_Substitute` emptied.

### In-game seed generator (validated in game, 2026-11-10)

- `python -m ootrr.native_logic` exports the logic as C++ tables (`rando/logic_data.hpp`): rules as prefix code,
  symbolic settings (read from the menu). `rando/generator.cpp` is an exact port of `search.py` / `fill.py`, and
  `rando/py_random.hpp` of `random.Random` (MT19937, init_by_array, _randbelow, shuffle, choice).
- `python -m ootrr.tools.native_check` compiles the generator for the PC (w64devkit) and compares it with Python:
  1000 identical seeds on 5 presets. In game: seeds 0x5d0e118b (default) and 0x20eed1eb (menu settings) identical to
  Python on the Kokiri Forest chests.
- At the start of the game, the added node `OoTRR.GenerateSeed` triggers the generation: settings read from the
  `OoTRRMenu` structure (accessors `0x404760` enum / `0x179f70` boolean, **by hash of the member name**), seed drawn
  from the system counter, written to `OoTRR.Seed` (saved integer, through the function of the
  `SeqOneShotSetNonStructGameDataInt` node `0xc25ce0` with a fake node; read `0x163d20`).
- Loaded game: at the first token, if the stored seed differs from the one in memory, regeneration with the game's
  seed and settings (validated: same placement after reloading).

### Manual seed with the virtual keyboard (validated in game, 2026-11-10)

"Manual Seed" row of the menu (member `VoiceSubtitle` of `OoTRRMenu`, unsaved). When enabled, the module opens the
console keyboard when the game starts (`rando/keyboard.cpp`): `nn::swkbd` library of the **sdk** module (the game
does not use it, but sdk exports it; rtld resolves our imports by name). Numeric pad, 9 digits; cancelled or empty ->
random seed (1-999999). Layout found in sdk: `KeyboardConfig` 0x518 bytes (mode +0x0, max length +0x3ac, min
+0x3b0), `ShowKeyboardArg` = config + work buffer (+0x518, 0x1000 aligned bytes) + size (+0x520), `String` =
{ char16_t*, size }. **The size of `String` must be exactly `GetRequiredStringBufferSize()`**: larger, reading the
answer fails and the SDK stops the game (2128-0503).

Random seed drawn when the menu opens (1-999999) and shown in the row's description (validated in game): the text
read by `0xa6afe0` (output { const char* UTF-8; s32 length }) is copied with the `######` marker replaced by the
seed. This seed is used when the manual seed is disabled.

The generator receives the displayed seed **mixed with the settings** (`MixSettings`, FNV-1a; validated in game): the
same seed gives another game if the settings change, and the same game with the same settings (including on load).
The generator (identical to Python) is not modified; a menu seed therefore does not match the same seed passed to
`python -m ootrr --seed`.

### Required number for the bridge (menu validated in game, 2026-11-12)

- Rows at the top of page 2 (`ingame_menu.BRIDGE_ROWS`): stones 1–3, medallions 1–6, rewards 1–9, hearts = base
  (3 / 12) + extra (+0 to +8). Each one is only shown for its condition.
- **Display condition (validated in game, 2026-11-11)**: `CheckGameData` must be a **Bool** flag
  (`OoTRR.Menu.Show.<condition>`, unsaved); an expression never shows the row. The game reads the condition when the
  page opens, not when the mode changes on the same page: the native module sets the flags from the "bridge" row of
  page 1 (`UpdateBridgeRows`, called when the layout loads). A hidden row leaves no gap.
- `0x339c790` (row by type) takes the **first row of the type, even hidden** (Ghidra; seen in game: the "Rewards" row
  capped at 6 = choices of the medallions row). The `TableRowByType` hook returns the first visible row of the type
  (+0x24 = hash of `CheckGameData`, 0 without condition). Rows of the same type = same GameData member: texts
  specific to the condition (`<prefix>B<n>_…`, tried first), value brought back into the visible row's choices
  (`kSetEnum` on the full name, not verified); a value beyond counts as the maximum (native, expressions,
  `ingame_spoiler`).
- Enum comparison in an expression: `[12, flag]` then `[2, value]` (`encode_bool_exp`, `EnumEq`).
- Bridge in game: `bridge_menu_exps`, one expression per combination of choices ("rows equal … AND at least N").

## Ghidra

Installed outside the repository (`C:\Users\<you>\Tools`: Ghidra 12.2 + JDK 25, the analysis project contains game
code). Things to know:
- Settings and cache moved (`launch.properties`: `-Dapplication.settingsdir`, `-Dapplication.cachedir`): the OSGi
  cache in `%APPDATA%` failed ("The data file must be inside the data dir").
- Do not pass `-analysisTimeoutPerFile 0` (= immediate stop).
- Import: `-import main.elf -processor AARCH64:LE:64:v8A -preScript SetupAnalysis.java` (disables non-returning
  function detection, wrong here; ~22 min). The ELF is loaded at 0x100000: the `native/ghidra/*.java` scripts take
  and print addresses relative to the module.
- Decompile: `-process main.elf -noanalysis -readOnly -postScript Decompile.java output.c 0xADDRESS...`.
- `ootrr.tools.nso` contains `make_elf` (image -> ELF with .text / .rodata / .data segments).

## exlaunch changes

- `config.mk`: `PROGRAM_ID := 0400486024DEC000`, `LOAD_KIND := Module`, `PYTHON := py`,
  `CXX_FLAGS := -Wno-non-c-typedef-for-linkage` (devkitA64's GCC 15 otherwise rejects `hook_impl.cpp`).
- `source/program/main.cpp`: our entry point `exl_main`.

## Building (Windows)

Install devkitPro (devkitA64 + libnx), then from devkitPro's MSYS2 shell (`C:\devkitPro\msys2\usr\bin\bash.exe -l`):

```bash
export DEVKITPRO=/opt/devkitpro DEVKITA64=/opt/devkitpro/devkitA64
export PATH=$DEVKITPRO/devkitA64/bin:$DEVKITPRO/tools/bin:$PATH
cd native/exlaunch && make
```

devkitPro's make started from Git Bash does not see `DEVKITPRO`: use the MSYS2 shell. Normally
`python -m ootrr.tools.menutest` builds and installs everything.

## Installing alone (Eden closed)

Copy only `deploy/subsdk9` to `<emulator>\load\0400486024DEC000\OoTRR-native\exefs\subsdk9` (`%APPDATA%\fritchii`
or `%APPDATA%\eden`). Do **not** copy `deploy/main.npdm`: the game's one must stay. This mod only touches the exefs.
For the full menu, use `menutest` (mod `OoTRR-menu`).

Note: Eden logs a "Userspace PANIC" (0x1A80A) when the game closes, with or without this module; it is not a crash of
the module.
