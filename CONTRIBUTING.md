# Contributing

## Setup

1. Python 3.10 or newer, then `python -m pip install -r requirements.txt`.
2. Extract **your own copy** of the game (update included): you need the `romfs` folder of the update
   (`.../updates/<version>/romfs`). Never add it to the repository.
3. Emulator: Eden (or another Yuzu fork). Mods go into `<emulator>\load\0400486024DEC000\<mod name>`
   (`%APPDATA%\fritchii` or `%APPDATA%\eden`, see `modbuild.emulator_root`).
4. Check: `python -m ootrr --check`, then `python -m unittest discover -s tests`.

## How to work

- An in-game feature always follows the same cycle: search the files (`tools.events`, `tools.lookup`),
  prototype with a `--test-*` option, install as `--mod-name OoTRR-essai`, **test in game** (new game if start
  flags change), then integrate into the generator + tests + docs.
- Record every finding in `docs/GAME_KNOWLEDGE.md` with its level of certainty
  (**[game]**, **[files]**, **[hypothesis]**) and update `docs/ROADMAP.md`.
- Back up your saves before a test: `python -m ootrr.tools.saves backup <name>` (emulator closed).
- Language of docs, new code comments and commit messages: **English**.

## Before a commit

- `python -m unittest discover -s tests` green.
- `python -m ootrr --check` OK.
- No game files, no saves, no personal paths.
