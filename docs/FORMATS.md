# File formats

All readers/writers are in `ootrr/formats/` and rewrite the original files **byte for byte** when nothing changes
(verified for BYML, RESTBL, BFEVFL RELT, MSBT).

| Format | Files | Module | Notes |
|---|---|---|---|
| Zstandard + dictionaries | `*.zs` | `zs.py` | dictionaries in `Pack/ZsDic.pack.zs` (zs, bcett.byml, pack, bkprb) |
| SARC | `Pack/**/*.pack.zs`, `Mals/*.sarc.zs` | `sarc.py` | the writer keeps each file's alignment |
| BYML v7 | maps `Banc/**`, `GameData`, `RSDB`, parameters `*.bgyml` | `byml.py` | U32/I64/U64/F64 types preserved; identical subtrees deduplicated |
| RESTBL | `System/Resource/ResourceSizeTable*.rsizetable.zs` | `restbl.py` | size reserved per file; map = decompressed size + 292 |
| GameData | `GameData/GameDataList*.byml.zs` | `gamedata.py` | 32-bit MurmurHash3 of the name; `#hash` for an unknown name; expressions |
| BFEVFL | `Event/EventFlow/*.bfevfl.zs` | `evfl.py` | see below |
| MSBT | in `Mals/<language>.*.sarc.zs` | `msbt.py` | UTF-8; LBL1 (hash ×0x492) + TXT2 |
| AINB | `Logic/*.logic.module.ainb` | `modbuild._write_logic` | uncompressed; only same-length string replacement is supported |

## BFEVFL (event scripts)

- Header: `0x18` offset of the RELT table, `0x1C` size; absolute 64-bit pointers.
- RELT: list of every pointer location (one section covering the file). Any change that adds data rebuilds RELT
  (`evfl.build_relt`).
- Flowchart ("EVFL"): `+0x10` counts (actors, actions, queries, events, entry points), `+0x28` actors, `+0x30`
  events, `+0x38` entry point dictionary, `+0x40` entry points.
- Actor 0x38: name, secondary name, argument, actions (array of string pointers), queries, parameters; `+0x30`
  action count, `+0x32` query count.
- Event 0x30: name, `+8` type (0 action, 1 query, 2 fork, 3 join, 4 sub-flow), `+0x0A` next (or case count),
  `+0x0C` actor, `+0x0E` action/query, `+0x10` parameters, `+0x18` cases (query) or sub-flow script, `+0x20`
  sub-flow entry point.
- A query case: 8 bytes (`u32` value, `u16` event). 0 = yes.
- Entry point 0x20: `+0x1C` first event.
- Parameters: container (type 1) + "DIC" dictionary + values; strings often stored right after their value.
- To add steps without shifting the file, the actor and event arrays are **copied to the end of the file** with the
  new elements (existing indices do not change).

Tool: `python -m ootrr.tools.events --romfs ROMFS <script> [--entry E | --find TEXT]`.

## Maps (Banc)

`Banc/<Area>/<Area>_{Child,Adult}_{Dynamic,Static}.bcett.byml.zs`: `Actors` (Gyaml, Hash, SRTHash, Translate,
Rotate, Dynamic, Presence, Links, Phive), `AiGroups` (logic modules and their actors), `FarDeleteGroups`,
`SimultaneousGroups`, `Rails`. A given chest has the same hash in the child and adult maps.
