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
  **Validé en jeu (2026-11-10, expérience retirée depuis)** : table réordonnée / ligne retirée
  dans le pack Bootup et textes de `LayoutMsg/SystemOption_00` remplacés sont acceptés par le jeu.
- Objet écran `UISystemOptionScreen` : boutons par genre en `+0x2b8/+0x2c0`, `+0x2c8/+0x2d0`,
  `+0x2d8/+0x2e0` (type d'option du bouton en +0x54 / +0x58), lignes affichées `+0x338/+0x340`
  (paires genre, index), option sélectionnée `+0x370`. Construction : `FUN_035011c0` (Ghidra,
  0x34011c0 relatif) clone les modèles `Pa_ToggleBtn_00`, `Pa_SelectBtn_00`, `Pa_AmiiboBtn_00`,
  `Pa_Separator_00`.

### Ouvrir le menu après « Nouvelle partie » (validé en jeu, 2026-11-10)

`Sequence/NormalTitle.module.ainb` (graphe de l'écran titre, lu et réécrit avec la bibliothèque
`ainb` 0.2.17, GPL-2, `pip install ainb` ; modifier l'objet, pas le dict/JSON qui casse la table des
chaînes en 0x408) :
- nœud 1 (`Element_StringSelector`) : `Pa_Button_00` -> 50 -> 49 -> 48 -> 2 `ConfirmationNewGame.module`
  (« Yes » -> 13 début de partie, « No » -> 53 retour au titre) ; `Pa_Button_02` -> 52 -> 43 -> 9
  `Option.module` (`IsTitleMenu` = vrai, « End » -> 53). 48 et 43 font la même préparation (cachent l'écran titre).
- Modification (`ootrr.ingame_menu.title_sequence`) : copie du nœud 9 en nœud 74,
  48 -> 74, « End » de 74 -> 2 ; `Option.module.ainb` passe à 2 instances. Résultat en jeu :
  Nouvelle partie -> écran d'options -> B -> confirmation -> Oui = partie, Non = titre.
- Échecs utiles : remplacer `ConfirmationNewGame.module.ainb` par le module d'options fait juste
  disparaître le menu (paramètres d'entrée absents) ; insérer l'écran après « Oui » laisse la
  fenêtre de confirmation affichée par-dessus.
- Reste : nos propres lignes seulement dans ce menu (l'écran Options normal doit garder les siennes)
  et nos propres valeurs (aujourd'hui une ligne renommée change toujours l'option du jeu).

### Menu du randomizer (validé en jeu, 2026-11-10)

`python -m ootrr.tools.menutest --romfs ROMFS --install` (mod `OoTRR-menu`, RomFS + exefs ; données
dans `ootrr/ingame_menu.py`, crochets dans `exlaunch/source/program/main.cpp`).
- Drapeau `OoTRR.IsRandomizerMenu` (entrée GameData non sauvegardée) écrit par trois nœuds ajoutés à
  `NormalTitle` : vrai avec la préparation de Nouvelle partie (48), faux avec celle d'Options (43) et au
  début de la partie (13). Le crochet de `0x682b00` / `0x32e6910` (exécution de
  `SeqOneShotSetNonStructGameDataBool`, arguments nœud + hachage ; valeur en `**(nœud + 0x40)`) le suit.
- Table : `LoadOptionTable` (`0x339bc40`) charge une deuxième table à nous ; pendant ce chargement, le
  crochet du chargeur de ressources `0xa57350` remplace le chemin. **Ce chargeur prend (gestionnaire,
  const char** chemin) et renvoie son résultat par x8** : le crochet renvoie un type non trivial pour
  garder x8. Les accès `0x339c5a0` / `0x339c630` / `0x339c790` reçoivent notre table pendant le menu.
- Textes : `0xa6afe0` (sortie, `const char**` fichier, `const char**` étiquette ; 1 = trouvé) : on
  essaie d'abord `OoTRR_<étiquette>`.
- Valeurs : `0x9b3eb0` (gestionnaire, poignée, hachage) : `OptionData` -> `OoTRRMenu` (structure
  GameData copiée, entrées non sauvegardées, valeurs par défaut = `settings.py`). Les options du joueur
  ne sont pas touchées (vérifié en jeu).
- Mise en page : `0x43a0e0` (nom de la mise en page en x4, 11 arguments) : `SystemOption_00` ->
  `OoTRRMenu_00`, copie où le modèle amiibo est invisible (bit 0 des drapeaux d'un élément .buil =
  visible, vérifié en jeu ; les fiches numérotent les noms depuis le début de la réserve de chaînes,
  qui commence par le nom de la page, avant `RootPane`). Un modèle sans ligne correspondante reste
  affiché à sa place : on cache l'amiibo, et la table contient deux séparateurs (le modèle sert).
- Choix enregistrés dans la partie (validé : relu dans progress.sav) : les membres « réglage » de
  `OoTRRMenu` ont SaveFileIndex 0 et ResetTypeValue 0 ; MetaData décalé de 8 octets par entrée
  (`ingame_menu.add_saved_entries`). Le menu repart des valeurs par défaut après un retour au titre.

### Placement pendant le jeu (validé en jeu, 2026-11-10 : coffres de Mido)

- Le mod de fichiers met dans chaque emplacement mélangé un **jeton** `OoTRR_Lnnnn` (Drop__DropActor).
  Un jeton doit être un **vrai acteur** (copie de `TBox_Rupee_Green`, fiches RSDB copiées) : sinon le
  coffre ne propose pas de l'ouvrir.
- Le coffre crée son contenu à l'avance (porte-acteur, nom lu dans son tableau noir, lui-même rempli
  depuis les paramètres de la carte). Remplacer la copie du composant « drop » ne suffit pas (le coffre
  fait apparaître le jeton -> blocage). Le crochet de `0xbd1c00` remplace **la valeur à la source**,
  dans les paramètres dynamiques en mémoire, avant l'appel d'origine :
  `*(*(*(infos+0x40)+0x270))+0x10` -> { u32 nb clés, const char** clés (+8), u32 nb valeurs (+0x10),
  const char** valeurs (+0x18) }.
- Les jetons sont posés dans les 134 coffres mélangeables (`native_logic.chest_tokens`, index = rang dans
  `logic_data.hpp`). Coffre « drop » dont l'objet change : `GetEventName` vidé à la source ; coffre
  conditionnel : `Drop__CheckActor` et `Drop__DropActor_Substitute` vidés.

### Générateur de seed dans le jeu (validé en jeu, 2026-11-10)

- `python -m ootrr.native_logic` exporte la logique en tables C++ (`rando/logic_data.hpp`) : règles en
  code préfixé, réglages symboliques (lus dans le menu). `rando/generator.cpp` est un portage exact de
  `search.py` / `fill.py`, et `rando/py_random.hpp` de `random.Random` (MT19937, init_by_array,
  _randbelow, shuffle, choice).
- `python -m ootrr.tools.native_check` compile le générateur pour le PC (w64devkit) et le compare à
  Python : 1000 seeds identiques sur 5 préréglages. En jeu : seeds 0x5d0e118b (défaut) et 0x20eed1eb
  (réglages du menu) identiques à Python sur les coffres de la forêt Kokiri.
- Au début de la partie, le nœud ajouté `OoTRR.GenerateSeed` déclenche la génération : réglages lus dans
  la structure `OoTRRMenu` (accesseurs `0x404760` énumération / `0x179f70` booléen, **par hachage du nom
  du membre**), seed tirée du compteur système, écrite dans `OoTRR.Seed` (entier sauvegardé, via la
  fonction du nœud `SeqOneShotSetNonStructGameDataInt` `0xc25ce0` avec un faux nœud ; lecture `0x163d20`).
- Partie chargée : au premier jeton, si la seed enregistrée diffère de celle en mémoire, régénération
  avec la seed et les réglages de la partie (validé : même placement après rechargement).
- Reste : appliquer en jeu les autres effets des réglages (forêt, porte, récompenses, cœurs au sol,
  cartes, objets de départ…) et les emplacements qui ne sont pas des coffres.


### Seed manuelle au clavier virtuel (validé en jeu, 2026-11-10)

Ligne « Seed manuelle » du menu (membre `VoiceSubtitle` de `OoTRRMenu`, non sauvegardé). Activée, le
module ouvre au lancement de la partie le clavier de la console (`rando/keyboard.cpp`) : bibliothèque
`nn::swkbd` du module **sdk** (le jeu ne s'en sert pas, mais sdk l'exporte ; rtld résout nos imports
par leur nom). Pavé numérique, 9 chiffres ; annulé ou vide -> seed aléatoire (1-999999).
Disposition relevée dans sdk : `KeyboardConfig` 0x518 octets (mode +0x0, longueur max +0x3ac, min
+0x3b0), `ShowKeyboardArg` = config + tampon de travail (+0x518, 0x1000 octets alignés) + taille
(+0x520), `String` = { char16_t*, taille }. **La taille de `String` doit être exactement
`GetRequiredStringBufferSize()`** : plus grande, la lecture de la réponse échoue et le SDK arrête le
jeu (2128-0503).

Seed aléatoire tirée à l'ouverture du menu (1-999999) et affichée dans la description de la ligne
(validé en jeu) : le texte lu par `0xa6afe0` (sortie { const char* UTF-8 ; s32 longueur }) est copié
avec le repère `######` remplacé par la seed. C'est cette seed qui sert si la seed manuelle est désactivée.

Le générateur reçoit la seed affichée **mélangée aux réglages** (`MixSettings`, FNV-1a) : une même
seed donne une autre partie si les réglages changent, et la même partie avec les mêmes réglages (y
compris au chargement). Le générateur (identique à Python) n'est pas modifié ; une seed du menu ne
correspond donc pas à la même seed passée à `python -m ootrr --seed`.

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
`<émulateur>\load\0400486024DEC000\OoTRR-native\exefs\subsdk9` (`%APPDATA%\fritchii` ou `%APPDATA%\eden`). **Ne pas** copier
`deploy/main.npdm` : celui du jeu doit rester. Ce mod ne touche que l'exefs et peut rester
actif avec un mod OoTRR (romfs).

Note : Eden journalise un « Userspace PANIC » (0x1A80A) à la fermeture du jeu, avec ou sans
ce module ; ce n'est pas un plantage du module.
