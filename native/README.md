# Code natif (menu en jeu, expérimental)

Module injecté dans le jeu avec [exlaunch](https://github.com/shadowninja108/exlaunch)
(GPL-2, copié depuis le commit `f9f4b0d`, voir `exlaunch/LICENSE`), chargé comme `subsdk9`.

## État

- **Étape 0 — validée en jeu (2026-11-10)** : Eden charge le module (`Module subsdk9 loaded`)
  et l'exécute (`OutputDebugString: OoTRR: module natif charge`, puis `svcBreak` de
  notification avec info1 = `0x4F6F545252`). Le jeu continue normalement.
- Suite : trouver dans `main` les fonctions à accrocher (écran « Nouvelle partie », affichage
  de texte) pour construire le menu de réglages. Gros travail de rétro-ingénierie.

## Rétro-ingénierie : point de départ

- `main` est compressé en « ZBIC » (format Switch 2, pas du LZ4) : `ootrr.tools.nso` ne le lit
  pas. On récupère le code décompressé avec l'option d'Eden `dump_nso` (section Debugging de
  `qt-config.ini`, mettre aussi `dump_nso\default=false`, Eden fermé) : une partie lancée écrit
  `%APPDATA%\eden\dump\0400486024DEC000\nso\main-<build id>.nso` (en-tête 0x100 + image
  mémoire, relocations déjà appliquées avec base 0). Ôter l'en-tête -> `output/native/main.bin`.
- Segments (build id E0F3CCFA…) : `.text` 0 – 0x3c461d0, `.rodata` 0x3c47000 – 0x484c080,
  `.data` 0x484d000 – 0x4d46b80.
- Désassembler : `aarch64-none-elf-objdump -D -b binary -m aarch64 --start-address=0x... main.bin`.
  Références à une chaîne ou adresse : `python -m ootrr.tools.xref output/native/main.bin NOM --data`.
- L'écran titre est piloté par des modules AINB de la RomFS (`Sequence/`) : `NormalTitle`
  (boutons `Pa_Button_00/01/02` = nouvelle partie / charger / options), `ConfirmationNewGame`
  (fenêtre système `TitleSystemWindow_00`, préréglage `NewGame`), `Option` (écran
  `SystemOption_00`, boutons `PaOptionBtn_00` / `PaOptionBtnLevel_00`). Les nœuds (`SeqQuery…`,
  `SeqOneShot…`, `SeqExecute…`) sont des classes C++ : chaque classe a une méthode qui renvoie
  son nom (ex. `SeqQueryGetSelectedOptionType` : nom en 0x32f9880, vtable vers 0x4bc9c68 ;
  `SeqOneShotOpenSystemWindow` : 0x32d9360, vtable vers 0x4bb4c80).
- Mises en page : `UI/Layout2Archive/*.blarc.zs` (SARC de fichiers `.buil`, format Layout2 non
  documenté). Écran options : `Common…blarc` / `SystemOption_00.buil`.

### Écrans et nœuds de séquence (vérifié dans le code)

- ~5 700 classes de nœuds AINB. Dans chaque vtable, seules quelques entrées sont propres à la
  classe (référencées une seule fois) : lecture des paramètres et exécution.
- Les nœuds trouvent un écran par **MurmurHash3 du nom de mise en page** (même hachage que
  GameData) : `FUN_033eb1d0(gestionnaire, hash)` ou `FUN_029f9fb0(...)` (adresses Ghidra, base 0x100000).
  `SystemOption_00` = 0x87ebe934, `TitleSystemWindow_00` = 0xe1932d84, `SystemWindow_00` = 0x6d47deab.
- `SeqQueryGetSelectedOptionType` : lit `écran(SystemOption_00) + 0x370` (option sélectionnée).
- `SeqOneShotOpenSystemWindow` (paramètres `Preset`, `IsTitle`) : choisit l'écran titre ou normal,
  convertit le préréglage en numéro (`NewGame` 0, `ResetOption` 1, `BackToTitle` 2,
  `BackToTitleFromGameOver` 3, `NewGameMQ` 4, `ReleaseMQ` 5) puis appelle
  `FUN_03505a00(écran, numéro, IsTitle)` (Ghidra).
- Écran d'options = classe `UISystemOptionScreen` (code vers 0x33ce000 – 0x3404000, relatif).
  Liste fixe de 17 options (table de noms en 0x3f13800) : IsCameraUpDownReverse,
  IsCameraRightLeftReverse, CameraRotateSpeed, IsUseGyro, IsChangeJumpButton, DisplayMode,
  IsDisplayTextRuby, MessageWindowTransparency, VoiceLanguage, LockOnType,
  OcarinaSongEstimateMode, OcarinaKeyAssign, VoiceSubtitle, VoiceSubtitleSpeakerName,
  ZeldaNoteState, ControllerRumble (+ amiibo). Textes : messages `LayoutMsg/SystemOption_00`,
  étiquettes `%s_Title`, `%s_Caption`, `%s_00`…
- **Les lignes de l'écran viennent d'un fichier** : `UI/OptionSetTable/OptionSetTable.game__ui__OptionSetTable.bgyml`
  (dans `Pack/Bootup.Nin_Ounce_NVN2.pack.zs`). `OptionSetArray` = 20 lignes `{OptionType,
  ButtonType, ChoiceType[], CheckGameData, IsCheckDisplayGameData}` ; les énumérations sont des
  hachages (ButtonType 1160613079 = séparateur, 3569415379 = choix, 3166595148 = bascule…).
  En mémoire : gestionnaire d'options (global `+0x500`), entrées de 0x28 octets (+0 type d'option,
  +4 genre de ligne : 0 bascule, 1 choix, 2 amiibo, 3 séparateur ; +0x24 condition GameData).
  Accès : `FUN_0349c5a0` (nombre de lignes visibles), `FUN_0349c630` (ligne i), `FUN_0349c790`
  (ligne par type). Le comportement de chaque type d'option reste dans le code.
- Objet écran `UISystemOptionScreen` : boutons par genre en `+0x2b8/+0x2c0`, `+0x2c8/+0x2d0`,
  `+0x2d8/+0x2e0` (type d'option du bouton en +0x54 / +0x58), lignes affichées `+0x338/+0x340`
  (paires genre, index), option sélectionnée `+0x370`. Construction : `FUN_035011c0` (Ghidra,
  0x34011c0 relatif) clone les modèles `Pa_ToggleBtn_00`, `Pa_SelectBtn_00`, `Pa_AmiiboBtn_00`,
  `Pa_Separator_00`.

## Ghidra

Installé hors du dépôt (`C:\Users\<toi>\Tools` : Ghidra 12.2 + JDK 25, le projet d'analyse contient
du code du jeu). Points à savoir :
- Paramètres et cache déplacés (`launch.properties` : `-Dapplication.settingsdir`, `-Dapplication.cachedir`) :
  le cache OSGi dans `%APPDATA%` échouait (« The data file must be inside the data dir »).
- Ne pas passer `-analysisTimeoutPerFile 0` (= arrêt immédiat).
- Import : `-import main.elf -processor AARCH64:LE:64:v8A -preScript SetupAnalysis.java`
  (désactive la détection des fonctions sans retour, fausse ici ; ~22 min). L'ELF est chargé à
  0x100000 : les scripts `native/ghidra/*.java` prennent et affichent des adresses relatives au module.
- Décompiler : `-process main.elf -noanalysis -readOnly -postScript Decompile.java sortie.c 0xADRESSE...`.
- `ootrr.tools.nso` contient `make_elf` (image -> ELF avec segments .text / .rodata / .data).

## Modifications d'exlaunch

- `config.mk` : `PROGRAM_ID := 0400486024DEC000`, `LOAD_KIND := Module`, `PYTHON := py`,
  `CXX_FLAGS := -Wno-non-c-typedef-for-linkage` (GCC 15 de devkitA64 refuse sinon `hook_impl.cpp`).
- `source/program/main.cpp` : notre point d'entrée `exl_main`.

## Compiler (Windows)

Installer devkitPro (devkitA64 + libnx), puis depuis le shell MSYS2 de devkitPro
(`C:\devkitPro\msys2\usr\bin\bash.exe -l`) :

```bash
export DEVKITPRO=/opt/devkitpro DEVKITA64=/opt/devkitpro/devkitA64
export PATH=$DEVKITPRO/devkitA64/bin:$DEVKITPRO/tools/bin:$PATH
cd native/exlaunch && make
```

Le make de devkitPro lancé depuis Git Bash ne voit pas `DEVKITPRO` : utiliser le shell MSYS2.

## Installer (Eden fermé)

Copier seulement `deploy/subsdk9` dans
`%APPDATA%\eden\load\0400486024DEC000\OoTRR-native\exefs\subsdk9`. **Ne pas** copier
`deploy/main.npdm` : celui du jeu doit rester. Ce mod ne touche que l'exefs et peut rester
actif avec un mod OoTRR (romfs).

Note : Eden journalise un « Userspace PANIC » (0x1A80A) à la fermeture du jeu, avec ou sans
ce module ; ce n'est pas un plantage du module.
