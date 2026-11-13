"""Sorts the cutscenes (Event/EventFlow/Dm_*) and writes ootrr/data/cutscenes.json.

    python -m ootrr.tools.cutscenes --romfs "D:\\...\\romfs"

Two lists, both used by the skip_cutscenes=safe setting:

1. "skippable": scenes marked as already seen at the start (HavePlayedEvent.<name> = true). A scene is
   listed if it has a HavePlayedEvent.<name> flag AND neither it nor its sub-flows:
     - change a save flag (EventTriggerSetGameData*, AddOrSubGameDataInt);
     - give or take an item (GetPouchContent*, AddOrRemovePouchContent, or an item name);
     - change the time, save, or change scene (title, credits...).

2. "timeline_skips": the scenes the game itself lets the player skip (+ / X). The game decides it in RSDB
   EventSetting: an event whose EventSettingComponentList has the category "TimelineEvent" can be skipped,
   unless the list (or one of its $parent lists) contains the component SkipSetting/DisableSkip
   (IsDisableSkip = true). Those timelines are played by an "EventSystemActor.EventTransition" step of a
   parent script (EventName = the scene). The builder replaces that step with
   "HavePlayedEvent.<scene> = true" (the flag the game would set by playing it; maps and logic modules read
   it), plus a fade-in when the transition does not leave the fade to the parent (FadeInTypeEventEnd != 2).
   Everything else in the parent script (items, quest steps, flags, scene changes) is kept.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

from ..formats.byml import read_byml
from ..formats.evfl import find_action_events, string_refs
from ..formats.gamedata import index, murmur3_32
from ..formats.zs import ZsCodec

STATE_ACTIONS = {
    "EventTriggerSetGameDataBool", "EventTriggerSetGameDataInt", "EventTriggerAddOrSubGameDataInt",
    "EventTriggerSetGameDataFloat", "EventTriggerSetGameDataString", "EventTriggerSetGameDataEnum",
    "GetPouchContent", "GetPouchContentByActorName", "EventTriggerAddOrRemovePouchContent", "PouchSystemActor",
    "EventTrigger_SetTime", "EventTriggerRequestAutoSave",
}
SCENE_RE = re.compile(r"Banc|ChangeScene|SceneChange|LoadScene|Stage(Change|Load)|GameOver|Ending|Credit|Title", re.I)
ITEM_PREFIX = ("Item_", "Obj_Heart", "Weapon_Sword", "Weapon_Shield", "Armor_")
ACTOR_PREFIX = ("Npc_", "Enemy_", "Obj_", "Item_", "Animal_", "Player", "Weapon_", "Armor_", "Land_", "Navi")
OUT = Path(__file__).resolve().parents[1] / "data" / "cutscenes.json"
# scenes that the start event plays without a condition (checked: no item, no flag); "#N" = step number N
# (OpeningEvent #28: camera placed for the wake-up scene, which would stay far from Link)
EVENT_SKIPS = {"OpeningEvent": ["Dm_Kokiri_0000", "Dm_Kokiri_0030", "#28"]}

# Skippable timelines that are still played, with the reason (the player can still skip them in game).
TIMELINE_KEPT = {
    "Dm_Ending_0000": "ending (after the win)",
    "Dm_StaffCredit_0000": "credits (EventViewStaffRoll)",
    "Dm_StaffCredit_0010": "credits (EventCloseStaffRollEnd)",
    "Dm_FinalBattle_BossIn": "final Ganon fight: the timeline warps actors (EventWarpToHomeMatrix), boss music",
    "Dm_InsideGanonCastle_BossIn": "Ganondorf fight: refills the hearts, makes Navi appear, boss music",
    "Dm_InsideGanonCastle_0110": "the timeline selects an AI schedule (EventTriggerAIScheduleSelectSchedule)",
    "Dm_HrlField_0005": "the timeline sets the time of day (EventTrigger_SetTime)",
    "Dm_HrlField_0060": "the timeline sets the time of day (EventTrigger_SetTime)",
    "Dm_Kakariko_0030": "the timeline sets the time of day (EventTrigger_SetTime)",
    "Dm_Kakariko_0040": "the timeline sets the time of day (EventTrigger_SetTime)",
    "Dm_ZoraFountain_0020": "the timeline sets the time of day (EventTrigger_SetTime)",
}
TRANSITION = ("EventSystemActor", "EventTransition", "EventName")
COMPONENT_LISTS = Path("Event") / "EventSetting" / "EventSettingComponentList"


def classify(romfs: Path) -> tuple[list[str], dict[str, list[str]]]:
    codec = ZsCodec(romfs)
    idx = index(read_byml(codec.decompress(next((romfs / "GameData").glob("GameDataList*.byml.zs")))))
    flows = {p.name.replace(".bfevfl.zs", ""): p for p in (romfs / "Event" / "EventFlow").glob("*.bfevfl.zs")}
    cache: dict[str, set[str]] = {}
    memo: dict[str, list[str]] = {}

    def refs_of(f: str) -> set[str]:
        if f not in cache:
            cache[f] = set(string_refs(codec.decompress(flows[f])))
        return cache[f]

    def reasons(f: str, stack: tuple = ()) -> list[str]:
        if f in memo:
            return memo[f]
        if f in stack:
            return []
        r = refs_of(f)
        why = sorted(r & STATE_ACTIONS)
        why += [f"scene:{s}" for s in sorted(r) if SCENE_RE.search(s)]
        why += [f"item:{s}" for s in sorted(r) if s.startswith(ITEM_PREFIX)]
        for s in sorted(r):
            if s in flows and s != f and not s.startswith(ACTOR_PREFIX) and reasons(s, stack + (f,)):
                why.append(f"sub-flow:{s}")
        memo[f] = why
        return why

    safe, kept = [], {}
    for flow in sorted(f for f in flows if f.startswith("Dm_")):
        if murmur3_32(f"HavePlayedEvent.{flow}") not in idx:
            continue
        why = reasons(flow)
        if why:
            kept[flow] = why
        else:
            safe.append(flow)
    return safe, kept


def _component_list(romfs: Path, name: str) -> tuple[str | None, dict]:
    """(category, components) of an EventSettingComponentList, $parent lists included."""
    d = read_byml((romfs / COMPONENT_LISTS / f"{name}.engine__event__EventSettingComponentList.bgyml").read_bytes())
    category, components = None, {}
    if d.get("$parent"):
        category, components = _component_list(romfs, Path(d["$parent"]).name.split(".")[0])
        components = dict(components)
    components.update(d.get("Components") or {})
    return d.get("Category", category), components


def game_skippable(romfs: Path) -> tuple[list[str], list[str]]:
    """(events the player can skip in game, timeline events with DisableSkip), from RSDB EventSetting."""
    codec = ZsCodec(romfs)
    rows = read_byml(codec.decompress(next((romfs / "RSDB").glob("EventSetting.Product.*.rstbl.byml.zs"))))
    lists: dict[str, tuple] = {}
    skip, no_skip = set(), set()
    for row in rows:
        name = Path(row["EventSettingComponentList"]).name.split(".")[0]
        if name not in lists:
            lists[name] = _component_list(romfs, name)
        category, components = lists[name]
        if category != "TimelineEvent":
            continue
        (no_skip if "SkipSetting" in components else skip).add(row["__RowId"])
    return sorted(skip), sorted(no_skip)


def timeline_parents(romfs: Path, scenes: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """({parent script: [scenes it plays with EventTransition]}, scenes whose transitions need a fade-in)."""
    from .events import params
    from ..formats.evfl import EVENT_SIZE, _flowchart_full, _header, _q
    codec = ZsCodec(romfs)
    wanted = set(scenes)
    parents: dict[str, list[str]] = {}
    fade_in: set[str] = set()
    for p in sorted((romfs / "Event" / "EventFlow").glob("*.bfevfl.zs")):
        flow = p.name.replace(".bfevfl.zs", "")
        d = codec.decompress(p)
        found = wanted & set(string_refs(d))
        if not found:
            continue
        reloc, _ = _header(d)
        try:
            fc = _flowchart_full(d)
        except struct.error:
            continue  # timeline file (the scene itself or a sub-timeline), no flowchart
        for scene in sorted(found):
            events = find_action_events(d, *TRANSITION, scene)
            if not events:
                continue
            parents.setdefault(flow, []).append(scene)
            for i in events:
                ev = params(d, _q(d, fc["events"] + i * EVENT_SIZE + 0x10), reloc)
                if ev.get("FadeInTypeEventEnd", "2") != "2":
                    fade_in.add(scene)
    return parents, sorted(fade_in)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--romfs", required=True)
    args = p.parse_args(argv)
    romfs = Path(args.romfs)
    safe, kept = classify(romfs)
    skippable_in_game, no_skip = game_skippable(romfs)
    codec = ZsCodec(romfs)
    idx = index(read_byml(codec.decompress(next((romfs / "GameData").glob("GameDataList*.byml.zs")))))
    candidates = [s for s in skippable_in_game if s not in safe and s not in TIMELINE_KEPT
                  and murmur3_32(f"HavePlayedEvent.{s}") in idx]
    parents, fade_in = timeline_parents(romfs, candidates)
    played = {s for scenes in parents.values() for s in scenes}
    OUT.write_text(json.dumps({
        "_doc": "Cutscenes with no effect on the game (no item, no flag, no scene change): the skip_cutscenes=safe "
                "setting marks them as already seen from the new game. Generated by python -m ootrr.tools.cutscenes.",
        "skippable": safe,
        "_event_skips": "Scenes played without checking the 'already seen' flag: the step that plays them is "
                        "skipped in the given event (e.g. tapestry narration and Navi's wake-up at the start). "
                        "'#N' = step number N (OpeningEvent #28: camera placed for the wake-up scene, which would "
                        "stay far from Link).",
        "event_skips": EVENT_SKIPS,
        "_game_skippable": "Events the game lets the player skip with + / X (RSDB EventSetting: category "
                           "TimelineEvent without SkipSetting/DisableSkip), and the timelines that cannot be skipped.",
        "game_skippable": skippable_in_game,
        "game_no_skip": no_skip,
        "_timeline_skips": "skip_cutscenes=safe: in each parent script, the EventTransition step that plays one of "
                           "these skippable timelines is replaced with HavePlayedEvent.<scene> = true (and a fade-in "
                           "for the scenes of timeline_fade_in). Scenes of 'skippable' are not repeated here.",
        "timeline_skips": parents,
        "timeline_fade_in": [s for s in fade_in],
        "timeline_kept": TIMELINE_KEPT,
        "timeline_unplayed": sorted(set(candidates) - played),
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(safe)} cutscenes marked as seen, {len(kept)} kept; {len(skippable_in_game)} skippable in game, "
          f"{len(played)} replaced in {len(parents)} scripts, {len(TIMELINE_KEPT)} still played -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
