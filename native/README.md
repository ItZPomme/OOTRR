# Code natif (menu en jeu, expérimental)

Module injecté dans le jeu avec [exlaunch](https://github.com/shadowninja108/exlaunch)
(GPL-2, copié depuis le commit `f9f4b0d`, voir `exlaunch/LICENSE`), chargé comme `subsdk9`.

## État

- **Étape 0 — validée en jeu (2026-11-10)** : Eden charge le module (`Module subsdk9 loaded`)
  et l'exécute (`OutputDebugString: OoTRR: module natif charge`, puis `svcBreak` de
  notification avec info1 = `0x4F6F545252`). Le jeu continue normalement.
- Suite : trouver dans `main` les fonctions à accrocher (écran « Nouvelle partie », affichage
  de texte) pour construire le menu de réglages. Gros travail de rétro-ingénierie.

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
