"""Construction d'un mod LayeredFS : change le contenu de coffres identifiés par leur Hash.

Le mod contient uniquement les fichiers modifiés (cartes + table des tailles).
Les fichiers du jeu d'origine ne sont jamais modifiés.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from .formats.zs import ZsCodec, zstandard  # vérifie la présence de zstandard avec un message clair
from .formats.byml import byml_version, read_byml, write_byml
from .formats.restbl import Restbl

TITLE_ID = "0400486024DEC000"


class ModBuilder:
    def __init__(self, romfs: Path | str) -> None:
        self.romfs = Path(romfs)
        self.codec = ZsCodec(self.romfs)
        self.restbl_path = next((self.romfs / "System" / "Resource").glob("ResourceSizeTable*.rsizetable.zs"))
        self.restbl = Restbl(zstandard.ZstdDecompressor().decompress(
            self.restbl_path.read_bytes(), max_output_size=1 << 28))

    def find_files_with(self, hashes: set[int]) -> list[Path]:
        """Toutes les cartes qui contiennent au moins un des acteurs demandés (enfant ET adulte)."""
        found = []
        for path in sorted((self.romfs / "Banc").rglob("*.bcett.byml.zs")):
            root = read_byml(self.codec.decompress(path))
            if any(a.get("Hash") in hashes for a in root.get("Actors", []) or []):
                found.append(path)
        return found

    def _write_gamedata(self, flags: dict[str, object], out_romfs: Path,
                        bool_exps: dict[str, list] | None = None,
                        saved_ints: list[str] | None = None, saved_bools: list[str] | None = None) -> list[str]:
        """Change la valeur de départ (DefaultValue) de drapeaux de sauvegarde, et ajoute
        des expressions booléennes (bool_exps : {nom: programme postfixe}).

        saved_ints: new Int entries saved in progress.sav (default 0). An AI only sees another AI's writes through a
        saved entry (blue_fire_arrows, 2026-11-15: runtime Ints / Bools written by the arrow were never seen)."""
        from .formats.byml import U32, U64
        from .formats.gamedata import encode_bool_exp, enum_value, flag_hash, index

        path = next((self.romfs / "GameData").glob("GameDataList*.byml.zs"))
        raw = self.codec.decompress(path)
        root = read_byml(raw)
        idx = index(root)
        report = []
        for name, value in flags.items():
            entry = idx.get(flag_hash(name))
            if entry is None:
                raise KeyError(f"drapeau inconnu dans GameData : {name}")
            section, e = entry
            old = e["DefaultValue"]
            if section == "Bool":
                e["DefaultValue"] = bool(value)
            elif section == "Int":
                e["DefaultValue"] = int(value)
            elif section == "Enum":  # valeur donnée par son nom (ex. « Step06 »)
                e["DefaultValue"] = type(old)(enum_value(e, value))
            else:
                raise TypeError(f"{name} : type {section} non géré")
            report.append(f"GameData {name}: {old} -> {e['DefaultValue']}")
        for name, program in (bool_exps or {}).items():
            h = flag_hash(name)
            if h in idx:
                raise KeyError(f"expression déjà présente dans GameData : {name}")
            values = [[U64(x) for x in step] for step in encode_bool_exp(program)]
            root["Data"]["BoolExp"].append({"Hash": U32(h), "ResetTypeValue": 0, "SaveFileIndex": -1,
                                            "Values": values})
            report.append(f"GameData : nouvelle expression {name}")
        if saved_ints or saved_bools:
            import copy
            from .ingame_menu import PROGRESS_SAVE, add_saved_entries
            for section, names in (("Int", saved_ints or []), ("Bool", saved_bools or [])):
                template = next(e for e in root["Data"][section] if e.get("SaveFileIndex") == PROGRESS_SAVE)
                for name in names:
                    if flag_hash(name) in idx:
                        raise KeyError(f"entrée déjà présente dans GameData : {name}")
                    entry = copy.deepcopy(template)
                    entry.update({"Hash": U32(flag_hash(name)), "ResetTypeValue": 0,
                                  "DefaultValue": type(template["DefaultValue"])(0)})
                    root["Data"][section].append(entry)
            report += add_saved_entries(root, PROGRESS_SAVE, len(saved_ints or []) + len(saved_bools or []))
        new = write_byml(root, byml_version(raw))
        rel = path.relative_to(self.romfs).as_posix()
        self.restbl.resize_like(rel[:-3], len(raw), len(new))
        dest = out_romfs / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.codec.compress(path.name, new))
        return report

    def _write_events(self, event_changes: dict[str, dict[str, str]], out_romfs: Path,
                      event_skips: dict[str, list[str]] | None = None,
                      start_items: list[str] | None = None,
                      moat_gate: bool = False,
                      start_warp: tuple[str, str] | None = None,
                      scrub_sales: dict[str, int] | None = None,
                      scrub_progressive: dict[str, list[list[str]]] | None = None,
                      questions: list[str] | None = None,
                      timeline_skips: dict[str, list[str]] | None = None,
                      timeline_fade_in: list[str] | None = None,
                      event_entry_gates: dict[str, dict[str, dict[str, str]]] | None = None) -> list[str]:
        """Modifie des flux d'événements (Event/EventFlow/<flux>.bfevfl.zs).

        event_changes : {flux: {ancien nom: nouveau nom}} (ex. l'objet donné)
        event_skips   : {flux: [scènes]} étapes qui jouent ces scènes, à sauter
        start_items   : objets ajoutés à l'inventaire au début de l'introduction
        timeline_skips: {script: [scenes]} skippable timelines replaced with their "already seen" flag"""
        from .formats.evfl import (add_actions, find_action, insert_flow, replace_event_strings, replace_strings,
                                   set_event_bools, set_event_ints, skip_event_steps)

        report = []
        event_skips = event_skips or {}
        timeline_skips = timeline_skips or {}
        song_scenes = self._song_scene_flows()
        guards = [g for g in self.EVENT_GUARDS]
        if self.ocarina_guard:
            guards.append(None)  # garde de l'Ocarina des fées (OCARINA_GUARD)
        event_entry_gates = event_entry_gates or {}
        event_bools = self.event_bools or {}
        flows = (
            {self.OCARINA_GUARD[0] if g is None else g[0] for g in guards}
            | {self.ERA_FLOW, self.DAMPE_FLOW}
            | set(event_changes)
            | set(self.gift_edits)
            | set(self.gift_progressive)
            | set(self.event_ints)
            | set(event_bools)
            | ({self.START_FLOW} if self.spawn_branch else set())
            | ({self.SONG_FLOW} if self.song_gives else set())
            | set(song_scenes)
            | set(event_skips)
            | set(timeline_skips)
            | set(event_entry_gates)
            | ({self.COLLAPSE_FLOW} if self.skip_collapse else set())
            | ({self.START_FLOW} if start_items or start_warp or questions else set())
            | ({self.MOAT_FLOW} if moat_gate else set())
            | ({self.SCRUB_FLOW} if scrub_sales else set())
        )
        if self.given_flags:
            flows.add(self.WINDMILL_FLOW)
        if self.ground_chains:
            flows |= set(self.GROUND_FLOWS)
        for flow in sorted(flows):
            mapping = event_changes.get(flow, {})
            path = self.romfs / "Event" / "EventFlow" / f"{flow}.bfevfl.zs"
            if not path.exists():
                raise KeyError(f"flux d'événements introuvable : {flow}")
            raw = self.codec.decompress(path)
            new = raw
            if flow in event_skips:
                new, skip_report = skip_event_steps(new, event_skips[flow])
                if len(skip_report) < len(event_skips[flow]):
                    raise KeyError(f"{flow} : scène à sauter introuvable parmi {event_skips[flow]}")
                report += [f"{flow}: {r}" for r in skip_report]
            if flow in timeline_skips:
                new, tl_report = self._skip_timelines(new, timeline_skips[flow], set(timeline_fade_in or ()))
                report += [f"{flow}: {r}" for r in tl_report]
            count = 0
            if mapping:
                new, count = replace_strings(new, mapping)
                if count == 0:
                    raise KeyError(f"{flow} : aucune des chaînes {list(mapping)} n'est utilisée")
            if flow in self.gift_edits:
                # cadeaux (data/gifts.json) : paramètres texte d'événements précis -> jeton du lieu ou objet placé
                new, gift_report = replace_event_strings(new, self.gift_edits[flow])
                if gift_report:
                    raise KeyError(f"{flow} : cadeau différent du relevé ({'; '.join(gift_report)})")
                report.append(f"{flow}: {len(self.gift_edits[flow])} cadeaux")
            if flow in self.gift_progressive:
                new, gift_report = self._progressive_gift(new, self.gift_progressive[flow])
                report += [f"{flow}: {r}" for r in gift_report]
            if flow in self.event_ints:
                # minigame counts (cucco_count, big_poe_count): integer parameters of precise events
                new, int_report = set_event_ints(new, self.event_ints[flow])
                if int_report:
                    raise KeyError(f"{flow}: {'; '.join(int_report)}")
                report += [f"{flow}: event {e} {p} {a} -> {b}" for e, p, a, b in self.event_ints[flow]]
            if flow in event_bools:
                new, bool_report = set_event_bools(new, event_bools[flow])
                if bool_report:
                    raise KeyError(f"{flow}: {'; '.join(bool_report)}")
                report += [f"{flow}: event {e} {p} {a} -> {b}" for e, p, a, b in event_bools[flow]]
            if start_items and flow == self.START_FLOW:
                # action « ajouter à l'inventaire » copiée de la scène où Saria donne l'ocarina (sans animation)
                template = self.codec.decompress(self.romfs / "Event" / "EventFlow" / f"{self.POUCH_TEMPLATE}.bfevfl.zs")
                params = find_action(template, *self.POUCH_ACTION)
                if params is None:
                    raise KeyError(f"{self.POUCH_TEMPLATE} : action {self.POUCH_ACTION} introuvable")
                new, add_report = add_actions(new, self.START_ENTRY, *self.POUCH_ACTION, template, params,
                                              [{"Actor": item} for item in start_items])
                report += add_report
            if scrub_sales and flow == self.SCRUB_FLOW:
                new, scrub_report = self._scrub_sales(new, scrub_sales, scrub_progressive)
                report += scrub_report
            if self.ocarina_guard and flow == self.OCARINA_GUARD[0]:
                new, guard_report = self._guard_fairy_ocarina(new)
                report += guard_report
            if flow == self.ERA_FLOW:
                new, era_report = self._guard_era_sword(new)
                report += era_report
                new, era_report = self._give_master_sword(new)
                report += era_report
            if flow == self.ESCAPE_FLOW and "Dm_Kakariko_0025" in timeline_skips.get(flow, ()):
                new, escape_report = self._fire_warp(new)
                report += escape_report
            if self.given_flags and flow == self.DAMPE_FLOW:
                new, given_report = self._given_flag(new, flow, *self.DAMPE_GIVEN)
                report += given_report
            if self.given_flags and flow == self.WINDMILL_FLOW:
                new, given_report = self._given_flag(new, flow, *self.WINDMILL_GIVEN)
                report += given_report
            if self.ground_chains and flow in self.GROUND_FLOWS:
                new, ground_report = self._progressive_ground(new, self.GROUND_FLOWS[flow])
                report += [f"{flow}: {r}" for r in ground_report]
            if flow == self.DAMPE_FLOW:
                new, dampe_report = self._dampe_exit(new)
                report += dampe_report
            if self.skip_collapse and flow == self.COLLAPSE_FLOW:
                new, collapse_report = self._skip_tower_collapse(new)
                report += collapse_report
            # shuffled potion shop gift (a plain edit, or a progressive one: patch.progressive_gifts moves it)
            if flow == self.BOTTLE_TUTORIAL_FLOW and (flow in self.gift_edits or flow in self.gift_progressive):
                new, tutorial_report = self._skip_bottle_tutorial(new)
                report += tutorial_report
            for guard in self.EVENT_GUARDS:
                if guard[0] == flow:
                    new, guard_report = self._guard_event(new, guard)
                    report += guard_report
            if questions and flow == self.START_FLOW:
                new, qnodes = self._question_nodes(new, questions)
                new, q_report = insert_flow(new, self.START_ENTRY, qnodes)
                report += q_report
            if start_warp and flow == self.START_FLOW:
                # test : la nouvelle partie commence dans une autre zone (BANC, point de départ)
                template = self.codec.decompress(self.romfs / "Event" / "EventFlow" / f"{self.WARP_TEMPLATE}.bfevfl.zs")
                params = find_action(template, *self.WARP_ACTION)
                new, warp_report = add_actions(new, self.START_ENTRY, *self.WARP_ACTION, template, params,
                                               [{"NextBanc": start_warp[0], "NextStartPos": start_warp[1],
                                                 "BootEventName": ""}])
                report += warp_report
            if self.song_gives and flow == self.SONG_FLOW:
                new, song_report = self._song_gives(new)
                report += song_report
            if flow in song_scenes:
                new, scene_report = self._song_scene_get(new, *song_scenes[flow])
                report += [f"{flow}: {r}" for r in scene_report]
            if self.spawn_branch and flow == self.START_FLOW:
                new, spawn_nodes = self._spawn_nodes(new)
                new, spawn_report = insert_flow(new, self.START_ENTRY, spawn_nodes)
                report += spawn_report + [f"{flow}: {len(self.spawn_branch)} points d'apparition selon {self.spawn_branch_entry}"]
            if moat_gate and flow == self.MOAT_FLOW:
                new, moat_report = insert_flow(new, self.MOAT_ENTRY, self._moat_gate(new))
                report += moat_report
            for entry, gate in event_entry_gates.get(flow, {}).items():
                from .formats.evfl import ensure_actor_member, find_query

                query_flow = new
                query = find_query(query_flow, "GameDataActor", "EventQueryIsGameDataBoolExp")
                if query is None:
                    query_flow = self.codec.decompress(
                        self.romfs / "Event" / "EventFlow" / "DoorOfTime.bfevfl.zs")
                    query = find_query(query_flow, "GameDataActor", "EventQueryIsGameDataBoolExp")
                    if query is None:
                        raise KeyError("DoorOfTime: no GameDataActor.EventQueryIsGameDataBoolExp template")
                    new = ensure_actor_member(new, "GameDataActor", "query", "EventQueryIsGameDataBoolExp")
                nodes = [
                    {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
                     "template": (query_flow, query), "set": {"GameDataName": gate["condition"]},
                     "cases": {0: 1, 1: "old"}},
                    {"flow": gate.get("flow", ""), "entry": gate["entry"], "next": "old"},
                ]
                before = int(gate["before"]) if "before" in gate else None
                new, gate_report = insert_flow(new, entry, nodes, before=before)
                report += gate_report
            rel = path.relative_to(self.romfs).as_posix()
            self.restbl.resize_like(rel[:-3], len(raw), len(new))
            dest = out_romfs / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.codec.compress(path.name, new))
            if mapping:
                report.append(f"{flow}: {mapping} ({count} références)")
        return report

    def _write_ainb_edits(self, ainb_edits: dict[str, dict], out_romfs: Path,
                          pack_changes: dict[str, dict[str, dict]] | None = None) -> list[str]:
        """Adds nodes to AI modules inside actor packs (ootrr.ainb_graph).

        ainb_edits : {"fast_walk": {"actors": [...], "file": inner path, "bool_exp": ..., "head_flag": ...,
        "head_actor": ..., "factor": ...}}. The edited file is the same in every listed pack; its own RESTBL entry
        is raised too (see ainb_graph)."""
        from . import ainb_graph
        from .formats.sarc import Sarc

        report = []
        templates = ainb_graph.Templates(self.romfs, self.codec)
        for kind, edit in sorted(ainb_edits.items()):
            if kind == "blue_fire_arrows":
                report += self._write_blue_fire_arrows(edit, out_romfs, templates, pack_changes)
                continue
            if kind == "still_floors":
                report += self._write_still_floors(edit, out_romfs, pack_changes)
                continue
            if kind == "ganon_boss_key":
                report += self._write_flag_module(edit, out_romfs)
                continue
            if kind == "navi_return":
                report += self._write_navi_module(edit, out_romfs, templates)
                continue
            if kind != "fast_walk":
                raise KeyError(f"unknown AINB edit: {kind}")
            clash = set(edit["actors"]) & set(pack_changes or {})
            if clash:
                raise ValueError(f"packs edited twice: {sorted(clash)}")
            inner, new_inner = edit["file"], None
            for actor in edit["actors"]:
                path = self.romfs / "Pack" / "Actor" / f"{actor}.pack.zs"
                raw = self.codec.decompress(path)
                sarc = Sarc(raw)
                if new_inner is None:
                    new_inner = ainb_graph.fast_walk(sarc.files[inner], templates, edit["bool_exp"],
                                                     edit["head_flag"], edit["head_actor"], edit["factor"])
                    ainb_graph.inner_size_entry(self.restbl, inner, len(new_inner))
                    report.append(f"{inner}: x{edit['factor']} forward speed while {edit['head_actor']} is worn "
                                  f"({len(sarc.files[inner])} -> {len(new_inner)} bytes)")
                sarc.files[inner] = new_inner
                new = sarc.to_bytes()
                rel = path.relative_to(self.romfs).as_posix()
                self.restbl.resize_like(rel[:-3], len(raw), len(new) + ainb_graph.INNER_MARGIN)
                dest = out_romfs / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(self.codec.compress(path.name, new))
                report.append(f"  pack {actor}")
        return report

    def _write_navi_module(self, edit: dict, out_romfs: Path, templates) -> list[str]:
        """Link's "call Navi" module (ainb_graph.navi_return), in every pack of Link; the packs may already hold
        another edit of this mod (fast_walk)."""
        from . import ainb_graph
        from .formats.sarc import Sarc

        inner, new_inner, report = edit["file"], None, []
        for actor in edit["actors"]:
            path = self.romfs / "Pack" / "Actor" / f"{actor}.pack.zs"
            rel = path.relative_to(self.romfs).as_posix()
            dest = out_romfs / rel
            raw = self.codec.decompress(dest if dest.exists() else path)
            sarc = Sarc(raw)
            if new_inner is None:
                new_inner = ainb_graph.navi_return(sarc.files[inner], templates)
                ainb_graph.inner_size_entry(self.restbl, inner, len(new_inner))
                report.append(f"{inner}: calling Navi asks for the map's event ({len(sarc.files[inner])} -> "
                              f"{len(new_inner)} bytes)")
            sarc.files[inner] = new_inner
            new = sarc.to_bytes()
            self.restbl.resize_like(rel[:-3], len(raw), len(new) + ainb_graph.INNER_MARGIN)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.codec.compress(path.name, new))
            report.append(f"  pack {actor}")
        return report

    # Way back: one event per map, named after the map (asked for by Link's AI), all in one script, a renamed copy of
    # WarpEvent (it has the actors needed and 14 entry points: 12 dungeons, child outside, adult outside).
    RETURN_FLOW, RETURN_BASE = "OoTRR_Return", "WarpEvent"
    RETURN_ROW = "NaviTips_Gauntlet_00"  # plain FlowchartEvent asked for by Link's AI
    RETURN_FILE = "EventFlowMsg/Enemy_Event"
    RETURN_LABELS = {"entrance": 9111, "start": 9112, "cancel": 9113}
    RETURN_TEXTS = {
        "en": {"dungeon": "Are you stuck?\nWhere do you want to go back to?",
               "outside": "Are you stuck?\nDo you want to go back to the start?",
               "entrance": "Dungeon entrance", "start": "Starting point", "cancel": "Cancel"},
        "fr": {"dungeon": "Tu es bloqué ?\nOù veux-tu retourner ?",
               "outside": "Tu es bloqué ?\nVeux-tu retourner au départ ?",
               "entrance": "Entrée du donjon", "start": "Point de départ", "cancel": "Annuler"}}

    def _return_messages(self, language: str) -> dict[str, bytes]:
        texts = self.RETURN_TEXTS["fr" if language.endswith("fr") else "en"]
        out = {f"{n:04d}": texts[k].encode() for k, n in self.RETURN_LABELS.items()}
        out.update({f"OoTRR_Return_{k}": texts[k].encode() for k in ("dungeon", "outside")})
        return out

    def _write_navi_return(self, edit: dict, out_romfs: Path) -> tuple[list[str], dict[str, dict[str, dict]]]:
        """The script and the RSDB rows ({table: rows}) of the way back."""
        from .formats.evfl import (_dic_names, _flowchart_full, ensure_actor_member, event_params, find_action,
                                   insert_flow, rename_flow)
        from .tools.events import event_line

        folder = self.romfs / "Event" / "EventFlow"
        raw = self.codec.decompress(folder / f"{self.RETURN_BASE}.bfevfl.zs")
        fc = _flowchart_full(raw)
        entries = [e for e in _dic_names(raw, fc["entry_dic"]) if e]
        flow = rename_flow(raw, self.RETURN_BASE, self.RETURN_FLOW)
        for actor, kind, member in (("SystemTextNPC", "action", "EventTalk"),
                                    ("GameSystemActor", "query", "EventQueryTalkChoice2"),
                                    ("GameSystemActor", "query", "EventQueryTalkChoice3"),
                                    ("GameSystemActor", "action", "EventReserveBancChange"),
                                    ("Player_Event", "query", "EventQueryPlayerIsChild"),
                                    ("Player_Event", "action", "EventTriggerParticipateEvent")):
            flow = ensure_actor_member(flow, actor, kind, member)
        talk_src = self.codec.decompress(folder / "GetPouchContent.bfevfl.zs")
        talk = (talk_src, find_action(talk_src, "SystemTextNPC", "EventTalk"))
        # map change of Dampé's exit (a plain one, used the same way there), validated in game
        warp_src = self.codec.decompress(folder / f"{self.DAMPE_FLOW}.bfevfl.zs")
        if "Graveyard_Adult" not in event_line(warp_src, self.DAMPE_WARP)[0]:
            raise KeyError(f"{self.DAMPE_FLOW}: unexpected map change")
        warp = (warp_src, event_params(warp_src, self.DAMPE_WARP))

        def go(point) -> dict:
            return {"actor": "GameSystemActor", "action": "EventReserveBancChange", "template": warp,
                    "set": {"NextBanc": point[0], "NextStartPos": point[1]}, "next": None}

        def ask(text: str, *labels: str) -> dict:
            values = {"MessageId": f"{self.RETURN_FILE}:OoTRR_Return_{text}", "ChoiceNumber": len(labels),
                      "ChoiceDefaultNo": len(labels) - 1, "ChoiceCancelNo": len(labels) - 1}
            values.update({f"ChoiceLabel{i}": self.RETURN_LABELS[k] for i, k in enumerate(labels, 1)})
            return {"actor": "SystemTextNPC", "action": "EventTalk", "template": talk, "set": values, "next": 2}

        join = {"actor": "Player_Event", "action": "EventTriggerParticipateEvent", "template": (flow, 0), "next": 1}
        graphs: list[tuple[list[str], list[dict]]] = []
        for game, pos in edit["dungeons"].items():
            graphs.append(([game], [
                dict(join), ask("dungeon", "entrance", "start", "cancel"),
                {"actor": "GameSystemActor", "query": "EventQueryTalkChoice3", "template": (flow, 0),
                 "cases": {0: 3, 1: 4, 2: None}},
                go((game, pos)),
                {"actor": "Player_Event", "query": "EventQueryPlayerIsChild", "template": (flow, 0),
                 "cases": {0: 5, 1: 6}},
                go(edit["points"]["child"]), go(edit["points"]["adult"])]))
        for age, maps in edit["outside"].items():
            graphs.append((maps, [
                dict(join), ask("outside", "start", "cancel"),
                {"actor": "GameSystemActor", "query": "EventQueryTalkChoice2", "template": (flow, 0),
                 "cases": {0: 3, 1: None}},
                go(edit["points"][age])]))
        if len(graphs) > len(entries):
            raise ValueError(f"{self.RETURN_BASE}: {len(entries)} entry points for {len(graphs)} questions")
        setting, analyzed = {}, {}
        for entry, (maps, nodes) in zip(entries, graphs):
            flow, _ = insert_flow(flow, entry, nodes)
            for name in maps:
                setting[name] = {"__new": True, "__copy_from": self.RETURN_ROW, "EntryPointName": entry,
                                 "FlowchartFileName": f"Work/Event/EventFlow/{self.RETURN_FLOW}.evfc"}
                analyzed[name] = {"__new": True, "__copy_from": self.RETURN_ROW}
        rel = f"Event/EventFlow/{self.RETURN_FLOW}.bfevfl"
        base = self.restbl.get(f"Event/EventFlow/{self.RETURN_BASE}.bfevfl")
        self.restbl.set(rel, base + max(0, len(flow) - len(raw)))
        dest = out_romfs / (rel + ".zs")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.codec.compress(dest.name, flow))
        return ([f"{rel}: way back asked by Navi, {len(graphs)} questions, {len(setting)} maps"],
                {"EventSetting": setting, "GameAnalyzedEventInfo": analyzed})

    def _write_still_floors(self, edit: dict[str, list], out_romfs: Path,
                            pack_changes: dict[str, dict[str, dict]] | None = None) -> list[str]:
        """Falling floors that stay up (world.STILL_FLOORS, ainb_graph.still_floor)."""
        from . import ainb_graph
        from .formats.sarc import Sarc

        report = []
        for inner, (selector, support, message, actors) in sorted(edit.items()):
            clash = set(actors) & set(pack_changes or {})
            if clash:
                raise ValueError(f"packs edited twice: {sorted(clash)}")
            new_inner = None
            for actor in actors:
                path = self.romfs / "Pack" / "Actor" / f"{actor}.pack.zs"
                raw = self.codec.decompress(path)
                sarc = Sarc(raw)
                if new_inner is None:
                    new_inner = ainb_graph.still_floor(sarc.files[inner], selector, support, message)
                    ainb_graph.inner_size_entry(self.restbl, inner, len(new_inner))
                sarc.files[inner] = new_inner
                new = sarc.to_bytes()
                rel = path.relative_to(self.romfs).as_posix()
                self.restbl.resize_like(rel[:-3], len(raw), len(new) + ainb_graph.INNER_MARGIN)
                dest = out_romfs / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(self.codec.compress(path.name, new))
            report.append(f"{inner}: the floor no longer falls ({', '.join(actors)})")
        return report

    def _write_flag_module(self, edit: dict, out_romfs: Path) -> list[str]:
        """Logic module that sets a Bool while Link is in its room and an expression is true (ganon_boss_key:
        world.GANON_KEY_MODULE, ainb_graph.set_flag_in_room)."""
        from . import ainb_graph

        rel = f"Logic/{edit['module']}.logic.module.ainb"
        raw = (self.romfs / rel).read_bytes()
        new = ainb_graph.set_flag_in_room(raw, self.romfs, edit["bool_exp"], edit["flag"])
        self.restbl.resize_like(rel, len(raw), len(new) + ainb_graph.INNER_MARGIN)
        dest = out_romfs / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(new)
        return [f"{rel}: {edit['flag']} set by {edit['bool_exp']} ({len(raw)} -> {len(new)} bytes)"]

    def _write_blue_fire_arrows(self, edit: dict, out_romfs: Path, templates,
                                pack_changes: dict[str, dict[str, dict]] | None = None) -> list[str]:
        """Ice Arrows act as Blue Fire (world.BLUE_FIRE_ARROW, ainb_graph.ice_arrow_ai / red_ice_melt).

        NormalArrow gets an AI (new AIInfo + root file, PostSensorAIRef); each red ice pack gets the melt condition,
        aimed at the centre of its own Tgt shape, with a radius of twice its half size (King Zora's ice is 7.5 m
        tall; with the bow drawn the camera ray passed 4 to 8 m from its centre)."""
        from . import ainb_graph
        from .formats.sarc import Sarc, read_sarc

        arrow = edit["arrow"]
        clash = ({arrow["actor"]} | set(edit["red_ice"])) & set(pack_changes or {})
        if clash:
            raise ValueError(f"packs edited twice: {sorted(clash)}")

        def put(sarc, name: str, data: bytes) -> None:
            try:
                known = self.restbl.get(name)
            except KeyError:
                known = 0
            self.restbl.set(name, max(known, len(data) + ainb_graph.INNER_MARGIN))
            if name not in sarc.files:
                sarc.align[name] = 8
            sarc.files[name] = data

        def write(actor: str, sarc, raw: bytes) -> None:
            path = self.romfs / "Pack" / "Actor" / f"{actor}.pack.zs"
            new = sarc.to_bytes()
            rel = path.relative_to(self.romfs).as_posix()
            self.restbl.resize_like(rel[:-3], len(raw), len(new) + ainb_graph.INNER_MARGIN)
            dest = out_romfs / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.codec.compress(path.name, new))

        report = []
        base_actor, base_file = arrow["base"]
        base = read_sarc(self.codec.decompress(self.romfs / "Pack" / "Actor" / f"{base_actor}.pack.zs"))
        ai = ainb_graph.ice_arrow_ai(base[base_file], templates, arrow["ai"], edit["timer"], arrow["value"],
                                     arrow["ice_type"])
        raw = self.codec.decompress(self.romfs / "Pack" / "Actor" / f"{arrow['actor']}.pack.zs")
        sarc = Sarc(raw)
        param = f"Actor/{arrow['actor']}.engine__actor__ActorParam.bgyml"
        version = byml_version(sarc.files[param])
        info = f"AI/AIInfo/{arrow['ai'].split('.')[0]}.engine__actor__AIInfo.bgyml"
        put(sarc, f"AI/{arrow['ai']}.ainb", ai)
        put(sarc, info, write_byml({"PostSensorAIRef": f"Work/AI/Root/{arrow['ai']}.ain"}, version))
        tree = read_byml(sarc.files[param])
        tree["Components"]["AIInfoRef"] = "?" + info
        put(sarc, param, write_byml(tree, version))
        write(arrow["actor"], sarc, raw)
        report.append(f"{arrow['actor']}: AI {arrow['ai']} ({len(ai)} bytes), Ice Arrow shot -> {edit['timer']}")
        for actor in edit["red_ice"]:
            raw = self.codec.decompress(self.romfs / "Pack" / "Actor" / f"{actor}.pack.zs")
            sarc = Sarc(raw)
            shapes = sorted(k for k in sarc.files if k.startswith("Phive/ShapeParam/") and "__Tgt" in k)
            shape = ([k for k in shapes if f"/{actor}__" in k] or shapes)[0]
            box = read_byml(sarc.files[shape])["AutoCalc"]
            centre = tuple(float(box["Center"][k]) for k in "XYZ")
            radius = 2 * max((float(box["Max"][k]) - float(box["Min"][k])) / 2 for k in "XYZ")
            new_ai = ainb_graph.red_ice_melt(sarc.files[edit["file"]], templates, edit["timer"], centre, radius)
            put(sarc, edit["file"], new_ai)
            write(actor, sarc, raw)
            report.append(f"  {actor}: melts on an Ice Arrow shot (centre {tuple(round(v, 2) for v in centre)}, "
                          f"radius {radius:.1f} m)")
        return report

    def _write_packs(self, pack_changes: dict[str, dict[str, dict]], out_romfs: Path) -> list[str]:
        """Modifie des paramètres BYML à l'intérieur d'archives d'acteurs (Pack/Actor/<acteur>.pack.zs).

        pack_changes : {acteur: {fichier interne: {clé: valeur ou None pour supprimer}}}"""
        from .formats.sarc import Sarc

        report = []
        for actor, inner in sorted(pack_changes.items()):
            path = self.romfs / "Pack" / "Actor" / f"{actor}.pack.zs"
            raw = self.codec.decompress(path)
            sarc = Sarc(raw)
            for fname, fields in inner.items():
                fields = dict(fields)
                source = fields.pop("__copy_from", None)  # nouveau fichier : copie d'un fichier de l'archive
                if source is not None and fname not in sarc.files:
                    sarc.files[fname] = sarc.files[source]
                    sarc.align[fname] = sarc.align.get(source, 8)
                if fname not in sarc.files:
                    raise KeyError(f"{actor} : fichier interne introuvable {fname}")
                data = sarc.files[fname]
                tree = read_byml(data)
                for key, value in fields.items():
                    old = tree.get(key)
                    if value is None:
                        tree.pop(key, None)
                    else:
                        tree[key] = value
                    report.append(f"{actor} :: {fname.rsplit('/', 1)[-1]} {key}: {old} -> {value}")
                sarc.files[fname] = write_byml(tree, byml_version(data))
            new = sarc.to_bytes()
            rel = path.relative_to(self.romfs).as_posix()
            self.restbl.resize_like(rel[:-3], len(raw), len(new))
            dest = out_romfs / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.codec.compress(path.name, new))
        return report

    def _write_rsdb(self, rsdb_changes: dict[str, dict[str, dict]], out_romfs: Path) -> list[str]:
        """Modifie des lignes des tables précompilées RSDB/<table>.Product.*.rstbl.byml.zs.

        rsdb_changes : {table: {__RowId: {champ: valeur ou None}}}
        Le champ spécial « __copy_from » remplace d'abord la ligne par une copie d'une autre ligne."""
        report = []
        for table, rows_changes in sorted(rsdb_changes.items()):
            path = next((self.romfs / "RSDB").glob(f"{table}.Product.*.rstbl.byml.zs"))
            raw = self.codec.decompress(path)
            root = read_byml(raw)
            rows = root if isinstance(root, list) else next(iter(root.values()))
            by_id = {r.get("__RowId"): r for r in rows}
            for row_id, fields in rows_changes.items():
                fields = dict(fields)
                is_new = fields.pop("__new", False)
                row = by_id.get(row_id)
                if row is None and is_new:
                    row = {"__RowId": row_id}
                    rows.append(row)
                    by_id[row_id] = row
                    report.append(f"RSDB {table} : nouvelle ligne {row_id}")
                if row is None:
                    raise KeyError(f"{table} : ligne introuvable {row_id}")
                src = fields.pop("__copy_from", None)
                if src is not None:
                    if src not in by_id:
                        raise KeyError(f"{table} : ligne source introuvable {src}")
                    row.clear()
                    row.update({k: v for k, v in by_id[src].items()})
                    row["__RowId"] = row_id
                    report.append(f"RSDB {table} {row_id} : copie de {src}")
                for key, value in fields.items():
                    old = row.get(key)
                    if value is None:
                        row.pop(key, None)
                    else:
                        row[key] = value
                    report.append(f"RSDB {table} {row_id} {key}: {old} -> {value}")
            rows.sort(key=lambda r: r.get("__RowId", ""))  # le jeu cherche les lignes par ordre alphabétique
            new = write_byml(root, byml_version(raw))
            rel = path.relative_to(self.romfs).as_posix()
            self.restbl.resize_like(rel[:-3], len(raw), len(new))
            dest = out_romfs / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.codec.compress(path.name, new))
        return report

    START_FLOW, START_ENTRY = "OpeningEvent", "Opening_Introduction"
    WARP_TEMPLATE, WARP_ACTION = "DoorOfTime", ("GameSystemActor", "EventReserveBancChange")
    MOAT_FLOW, MOAT_ENTRY = "DoorOfTime", "DoorOfTime_GetOcarinaOfTime"
    STONES = ("Item_Stone_Forest", "Item_Stone_Fire", "Item_Stone_Water")
    MOAT_ITEMS = ("Item_Ocarina_Time", "Item_Melody_TimeSong")
    # le jeu remplace l'ocarina possédée par celle qu'on reçoit : Saria ne donne plus
    # l'Ocarina des fées si Link a déjà l'Ocarina du Temps
    OCARINA_GUARD = ("Dm_Kokiri_0155", "Item_Ocarina_Fairy", "IsGet.Item_Ocarina_Time")
    # désactivée quand l'objet de Saria peut changer (shuffle_ocarinas, menu natif) : il serait perdu
    ocarina_guard = True
    # cadeaux : {flux: [(événement, paramètre, texte d'origine, nouveau texte)]} (World.gift_event_changes ou jetons)
    gift_edits: dict = {}
    # progressive gifts (PC-built mod, patch.progressive_gifts): {flow: [[event, parameter, vanilla text,
    # [[item, pouch name], ...]]]}
    gift_progressive: dict = {}

    def _progressive_gift(self, flow: bytes, entries: list) -> tuple[bytes, list[str]]:
        """Before each gift step, questions from the last step down: "does Link own step k?" -> a copy of the gift
        step that gives step k+1 (the last step once owned); none -> step 1. The copies go on where the gift
        step went. Pouch question: PouchSystemActor.EventQueryIsExistInPouch (0 = yes), as at Dampe's exit."""
        from .formats.evfl import ensure_actor_member, event_param_slot, find_query, insert_flow

        template = self.codec.decompress(self.romfs / "Event" / "EventFlow" / f"{self.DAMPE_FLOW}.bfevfl.zs")
        ask = (template, find_query(template, "PouchSystemActor", "EventQueryIsExistInPouch"))
        if ask[1] is None:
            raise KeyError(f"{self.DAMPE_FLOW}: no EventQueryIsExistInPouch to copy")
        flow = ensure_actor_member(flow, "PouchSystemActor", "query", "EventQueryIsExistInPouch")
        report = []
        for event, param, old, steps in entries:
            found = event_param_slot(flow, event, param)
            if found is None or found[1] != old:
                raise KeyError(f"gift event {event}: {param} = {found[1] if found else None!r}, expected {old!r}")
            n = len(steps)
            nodes: list[dict] = []
            first = steps[0][1]
            # a weapon first (bow, slingshot): no weapon, whatever bag Link has -> the weapon
            base = 2 if first.startswith("Weapon_") and first != steps[0][0] else 0
            if base:
                nodes = [{"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch", "template": ask,
                          "set": {"Actor": first}, "cases": {0: 2, 1: 1}},
                         {"copy_event": event, "set": {param: steps[0][0]}, "next": "after"}]
            # node 2k: question "owns step n-1-k?"; node 2k+1: copy giving the step after it
            for k in range(n):
                owned = n - 1 - k
                nodes.append({"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch", "template": ask,
                              "set": {"Actor": steps[owned][1]},
                              "cases": {0: base + 2 * k + 1, 1: base + 2 * k + 2}})
                nodes.append({"copy_event": event, "set": {param: steps[min(owned + 1, n - 1)][0]},
                              "next": "after"})
            nodes.append({"copy_event": event, "set": {param: steps[0][0]}, "next": "after"})
            flow, _ = insert_flow(flow, f"ProgressiveGift{event}", nodes, before=event)  # entry: names only
            report.append(f"progressive gift, event {event}: {' / '.join(s[0] for s in steps)}")
        return flow, report
    event_ints: dict = {}  # {flow: [(event, parameter, vanilla value, new value)]}
    event_bools: dict[str, list[tuple[int, str, bool, bool]]] = {}
    moat_items = MOAT_ITEMS  # dons directs aux douves (l'objet du lieu de l'Ocarina du Temps peut changer)
    # scènes propres à l'objet d'origine d'un coffre, sautées si l'objet n'a pas été obtenu :
    # (flux, acteur, action, paramètre, valeur, drapeau). Coffre de l'épée Kokiri : son événement
    # (Get_StoneOfForest:GetSword) joue Dm_Kokiri_0063 qui met une épée dans la main de Link, même si le
    # coffre contenait autre chose (le menu natif ne peut pas retirer GetEventName à temps ; l'épée
    # disparaît au rechargement)
    EVENT_GUARDS = [("Get_StoneOfForest", "EventSystemActor", "EventTransition", "EventName", "Dm_Kokiri_0063",
                     "IsGet.Weapon_Sword_Kokiri")]

    # questions posées au début de la nouvelle partie : {réglage: (question, [(drapeau, valeur) si « oui »])}
    QUESTIONS = {
        "open_forest": ("Randomizer setting:\nOpen the Kokiri Forest?",
                        [("KokiriForest_Npc_Kokiri_007_Child_Blocker_00", False),
                         ("KokiriForest_Npc_Kokiri_Mido_Child_Blocker", False)]),
    }
    QUESTION_FILE = "EventFlowMsg/Enemy_Event"
    ANSWER_LABELS = (9101, 9102)  # réponses « Yes » / « No » (étiquettes 9101 et 9102 du même fichier)

    def _question_nodes(self, flow: bytes, questions: list[str]) -> tuple[bytes, list[dict]]:
        from .formats.evfl import ensure_actor_member, find_action

        flow = ensure_actor_member(flow, "SystemTextNPC", "action", "EventTalk")
        flow = ensure_actor_member(flow, "GameSystemActor", "query", "EventQueryTalkChoice2")
        flow = ensure_actor_member(flow, "GameDataActor", "action", "EventTriggerSetGameDataBool")
        ev = self.romfs / "Event" / "EventFlow"
        talk_src = self.codec.decompress(ev / "GetPouchContent.bfevfl.zs")
        talk = (talk_src, find_action(talk_src, "SystemTextNPC", "EventTalk"))
        set_src = self.codec.decompress(ev / "DoorOfTime.bfevfl.zs")
        setb = (set_src, find_action(set_src, "GameDataActor", "EventTriggerSetGameDataBool"))
        nodes: list[dict] = []
        for qi, name in enumerate(questions):
            text, flags = self.QUESTIONS[name]
            first = len(nodes)
            after = "old" if qi + 1 == len(questions) else None  # corrigé plus bas
            nodes.append({"actor": "SystemTextNPC", "action": "EventTalk", "template": talk, "next": first + 1,
                          "set": {"MessageId": f"{self.QUESTION_FILE}:OoTRR_Question_{name}", "ChoiceNumber": 2,
                                  "ChoiceLabel1": self.ANSWER_LABELS[0], "ChoiceLabel2": self.ANSWER_LABELS[1],
                                  "ChoiceDefaultNo": 0, "ChoiceCancelNo": 1}})
            end = first + 2 + len(flags)  # nœud qui suit cette question
            nodes.append({"actor": "GameSystemActor", "query": "EventQueryTalkChoice2", "template": (flow, 0),
                          "cases": {0: first + 2, 1: end}})
            for k, (flag, value) in enumerate(flags):
                nodes.append({"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool", "template": setb,
                              "set": {"GameDataName": flag, "Value": int(bool(value))}, "next": first + 3 + k})
        # le dernier saut de chaque question mène à la suivante ; après la dernière : l'intro d'origine
        total = len(nodes)
        for n in nodes:
            if n.get("next") == total:
                n["next"] = "old"
            if "cases" in n:
                n["cases"] = {k: ("old" if v == total else v) for k, v in n["cases"].items()}
        return flow, nodes

    TIMELINE_TRANSITION = ("EventSystemActor", "EventTransition", "EventName")
    # templates: "GameDataActor.EventTriggerSetGameDataBool" and "UISystemActor.EventEventFadeIn" (DoorOfTime)
    TIMELINE_TEMPLATE = "DoorOfTime"

    def _skip_timelines(self, flow: bytes, scenes: list[str], fade_in: set[str]) -> tuple[bytes, list[str]]:
        """Replaces each step that plays one of these skippable timelines (EventTransition) with
        HavePlayedEvent.<scene> = true, then a fade-in for the scenes of `fade_in` (transitions that let the
        timeline fade the screen back in). The rest of the script is unchanged."""
        from .formats.evfl import ensure_actor_member, find_action, find_action_events, insert_flow

        src = self.codec.decompress(self.romfs / "Event" / "EventFlow" / f"{self.TIMELINE_TEMPLATE}.bfevfl.zs")
        setb = (src, find_action(src, "GameDataActor", "EventTriggerSetGameDataBool"))
        fade = (src, find_action(src, "UISystemActor", "EventEventFadeIn"))
        if setb[1] is None or fade[1] is None:
            raise KeyError(f"{self.TIMELINE_TEMPLATE}: template actions not found")
        flow = ensure_actor_member(flow, "GameDataActor", "action", "EventTriggerSetGameDataBool")
        if fade_in & set(scenes):
            flow = ensure_actor_member(flow, "UISystemActor", "action", "EventEventFadeIn")
        report = []
        for scene in scenes:
            steps = find_action_events(flow, *self.TIMELINE_TRANSITION, scene)
            if not steps:
                raise KeyError(f"timeline step not found: {scene}")
            for step in steps:
                nodes = [{"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool", "template": setb,
                          "set": {"GameDataName": f"HavePlayedEvent.{scene}", "Value": 1}, "next": "after"}]
                if scene in fade_in:
                    nodes[0]["next"] = 1
                    nodes.append({"actor": "UISystemActor", "action": "EventEventFadeIn", "template": fade,
                                  "next": "after"})
                flow, _ = insert_flow(flow, None, nodes, before=step)
                report.append(f"{scene}: step {step} replaced with its flag{' + fade-in' if scene in fade_in else ''}")
        return flow, report

    SCRUB_FLOW = "Enemy_Scrub_Business_Common"
    SCRUB_MSG_PREFIX = "OoTRR_Scrub_"
    # texte des Peste Mojo : la phrase du jeu pour le quart de cœur, dans la langue du fichier,
    # dont le nom en couleur est remplacé par le nom de l'objet (dans la même langue)
    SCRUB_TEMPLATE = "Enemy_Scrub_Business_Heart_01"
    SCRUB_TEXT = ("I've got ", " for you! It's ", " rupees", ". Wanna buy it?")  # secours si le modèle manque

    def _write_messages(self, scrub_items: list[str], out_romfs: Path, questions: list[str] = (),
                        pouch_texts: dict[str, bytes] | None = None, way_back: bool = False,
                        navi_texts: dict[str, bytes] | None = None) -> list[str]:
        """Messages des Peste Mojo : un message par objet vendu, dans chaque langue, avec le nom
        de l'objet tel que le jeu l'écrit (ActorMsg/PouchContent.msbt) et le prix (SimpleShop_Price).
        pouch_texts: item texts added to ActorMsg/PouchContent.msbt in every language ({label: text}; the
        multiworld chest actors, `_mw_texts`); navi_texts: same for EventFlowMsg/NaviChat.msbt (`_navi_texts`)."""
        from .formats.msbt import add_messages, read_labels, read_texts, tag
        from .formats.sarc import Sarc

        price = tag(2, 12, bytes.fromhex("100053696d706c6553686f705f5072696365ffff"))
        on, off = tag(0, 3, b"\x00\x00"), tag(0, 3, b"\xff\xff")
        report = []
        words = self.SCRUB_TEXT
        for path in sorted((self.romfs / "Mals").glob("*.sarc.zs")):
            raw = self.codec.decompress(path)
            sarc = Sarc(raw)
            names = sarc.files["ActorMsg/PouchContent.msbt"]
            labels, texts = read_labels(names), read_texts(names)
            event = sarc.files["EventFlowMsg/Enemy_Event.msbt"]
            ev_labels, ev_texts = read_labels(event), read_texts(event)
            template = ev_texts[ev_labels[self.SCRUB_TEMPLATE]] if self.SCRUB_TEMPLATE in ev_labels else None
            new = {}
            for item in scrub_items:
                # nom écrit par le jeu depuis Shop_SelectItemName (posé avant la vente) : un jeton du menu
                # natif y prend le nom de l'objet placé (texte <jeton>_Name redirigé)
                name = self.SHOP_ITEM_NAME_TAG
                start = template.find(on) if template else -1
                end = template.find(off, start + len(on)) if start >= 0 else -1
                if start >= 0 and end > start:
                    # le premier passage en couleur est le nom de l'objet vendu
                    new[f"{self.SCRUB_MSG_PREFIX}{item}"] = template[:start + len(on)] + name + template[end:]
                    continue
                new[f"{self.SCRUB_MSG_PREFIX}{item}"] = (
                    tag(3, 0, b"\x0f\x00\x00") + words[0].encode() + on + name + off + words[1].encode()
                    + on + price + words[2].encode() + off + b"." + tag(5, 0) + words[3].lstrip(".").encode())
            for name in questions:  # questions de réglage (en anglais pour l'instant)
                new[f"OoTRR_Question_{name}"] = self.QUESTIONS[name][0].encode()
            if questions:
                new[f"{self.ANSWER_LABELS[0]:04d}"] = b"Yes"
                new[f"{self.ANSWER_LABELS[1]:04d}"] = b"No"
            if way_back:
                new.update(self._return_messages(path.name.split(".")[0]))
            key = "EventFlowMsg/Enemy_Event.msbt"
            sarc.files[key] = add_messages(sarc.files[key], new)
            if pouch_texts:
                sarc.files["ActorMsg/PouchContent.msbt"] = add_messages(names, pouch_texts)
            if navi_texts:
                sarc.files["EventFlowMsg/NaviChat.msbt"] = add_messages(sarc.files["EventFlowMsg/NaviChat.msbt"],
                                                                        navi_texts)
            data = sarc.to_bytes()
            rel = path.relative_to(self.romfs).as_posix()
            self.restbl.resize_like(rel[:-3], len(raw), len(data))
            dest = out_romfs / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.codec.compress(path.name, data))
            report.append(f"{rel}: {len(new)} scrub messages, {len(pouch_texts or {})} item texts")
        return report
    # balise des boutiques : nom de l'objet contenu dans la donnée GameData Shop_SelectItemName
    SHOP_ITEM_NAME_TAG = bytes.fromhex("0e020003001700130053686f705f53656c6563744974656d4e616d65ffff")
    SCRUB_TALK = "Enemy_Scrub_Business_DekuStickPouch_01"  # script « sac de bâtons » commun aux Peste Mojo mélangées
    # Peste Mojo du quart de cœur de la plaine : son script (entrée « Secret ») vend le quart de cœur
    # directement, sans comparer l'article ; (objet, prix) vendu à la place, ou None
    scrub_secret: tuple[str, int] | None = None
    # messages de vente supplémentaires (objets que le module natif peut substituer à un jeton)
    scrub_message_items: list[str] = []
    # article reconnu -> objet vendu (menu natif : l'article de la Peste Mojo doit être un vrai objet,
    # EventScrubBusinessWriteGameDataBancItemName ignore un nom inconnu ; il sert de marque)
    scrub_sold: dict[str, str] = {}

    def _scrub_sales(self, flow: bytes, sales: dict[str, int],
                     progressive: dict[str, list[list[str]]] | None = None) -> tuple[bytes, list[str]]:
        """Peste Mojo : avant les comparaisons d'origine, une question par objet vendu
        (« l'objet à vendre est-il X ? » ; 0 = oui) qui mène à la vente unique de X à son prix."""
        from .formats.evfl import _flowchart_full, _q, _string_at, _header, EVENT_SIZE, find_query, insert_flow
        if progressive and any(item in progressive for item in sales):
            from .formats.evfl import ensure_actor_member
            flow = ensure_actor_member(flow, "PouchSystemActor", "query", "EventQueryIsExistInPouch")
        import struct as _st
        if self.scrub_price_entries:  # question « entier GameData » (prix choisi en jeu)
            from .formats.evfl import ensure_actor_member
            flow = ensure_actor_member(flow, "GameDataActor", "query", "EventQueryGameDataIntBranch")

        reloc, _ = _header(flow)
        fc = _flowchart_full(flow)
        compare = sale = None
        for i in range(fc["n_events"]):
            o = fc["events"] + i * EVENT_SIZE
            p = _q(flow, o + 0x10)
            if not p:
                continue
            text = flow[p:p + 0x400]
            if flow[o + 8] == 1 and compare is None and b"" in text:
                pass
        # repères : la question « TempItemName == Obj_Heart_Piece » et l'appel de vente du sac de bâtons
        from .formats.evfl import string_refs
        refs = string_refs(flow)
        def owner(slot):
            best = None
            for i in range(fc["n_events"]):
                p = _q(flow, fc["events"] + i * EVENT_SIZE + 0x10)
                if p and p <= slot and (best is None or p > best[1]):
                    best = (i, p)
            return best[0] if best else None
        for slot in refs.get("Obj_Heart_Piece", []):
            i = owner(slot)
            if i is not None and flow[fc["events"] + i * EVENT_SIZE + 8] == 1:
                compare = i
                break
        for slot in refs.get("Item_StickBag_Medium", []):
            i = owner(slot)
            if i is not None and flow[fc["events"] + i * EVENT_SIZE + 8] == 4:
                sale = i
                break
        ask = (flow, _q(flow, fc["events"] + compare * EVENT_SIZE + 0x10)) if compare is not None else None
        if compare is None or sale is None:
            raise KeyError("repères introuvables dans le script des Peste Mojo")
        from .tools.events import trace
        # étape « Shop_SelectItemName = objet » (nom écrit dans le message de vente)
        set_name = [int(line.split(":", 1)[0]) for line in trace(flow, "SimpleShopRoot_Enemy_Scrub_Business_Pouch")
                    if "EventTriggerSetGameDataString64" in line and "'Shop_SelectItemName'" in line]
        if not set_name:
            raise KeyError("pose de Shop_SelectItemName introuvable dans le script des Peste Mojo")
        set_name = set_name[0]
        report: list[str] = []
        if self.scrub_secret:
            # vente directe du quart de cœur dans l'entrée « Secret » : remplacée par celle de l'objet
            item, price = self.scrub_secret
            direct = [int(line.split(":", 1)[0]) for line in trace(flow, "Secret")
                      if "SimpleShopSub_Scrub_Business_OneTime" in line and "'Obj_Heart_Piece'" in line]
            if len(direct) != 1:
                raise KeyError(f"vente du quart de cœur (entrée Secret) : {len(direct)} candidates")
            secret_nodes = [{"copy_event": set_name, "next": 1, "set": {"Value": item}}]
            secret_nodes += self._scrub_sale_nodes(flow, direct[0], item, int(price), base=1)
            flow, secret_report = insert_flow(flow, None, secret_nodes, before=direct[0])
            report += secret_report
            fc = _flowchart_full(flow)
            ask = (flow, _q(flow, fc["events"] + compare * EVENT_SIZE + 0x10))
        items = sorted(sales)
        blocks = []
        for item in items:
            sold = self.scrub_sold.get(item, item)
            chain = progressive.get(item) if progressive and item not in self.scrub_sold else None
            if chain:
                block = self._progressive_scrub_block(flow, ask, sale, set_name, item, int(sales[item]), chain)
            else:
                block = [{"actor": "GameDataActor", "query": "EventQueryIsGameDataString64", "template": ask,
                          "set": {"Value": item}, "cases": {}},
                         {"copy_event": set_name, "next": 2, "set": {"Value": sold}}]
                block += self._scrub_sale_nodes(flow, sale, sold, int(sales[item]), base=2)
            blocks.append(block)
        nodes = []
        for k, block in enumerate(blocks):
            start = len(nodes)
            nxt = start + len(block) if k + 1 < len(blocks) else None
            for node in block:
                node = dict(node)
                if "cases" in node and not node["cases"]:  # question « objet = X ? »
                    node["cases"] = {0: start + 1, 1: nxt if nxt is not None else "old"}
                elif "cases" in node:
                    node["cases"] = {v: start + t for v, t in node["cases"].items()}
                elif node.get("next") is not None:
                    node["next"] = start + node["next"]
                nodes.append(node)
        flow, sale_report = insert_flow(flow, None, nodes, before=compare)
        return flow, report + sale_report

    def _progressive_scrub_block(self, flow: bytes, item_query: tuple[bytes, int], sale: int, set_name: int,
                                 item: str, price: int, steps: list[list[str]]) -> list[dict]:
        from .formats.evfl import find_query

        actor, query = "PouchSystemActor", "EventQueryIsExistInPouch"
        template = self.codec.decompress(self.romfs / "Event" / "EventFlow" / f"{self.DAMPE_FLOW}.bfevfl.zs")
        pouch_query = find_query(template, actor, query)
        if pouch_query is None:
            raise KeyError(f"{self.DAMPE_FLOW}: no {query} to copy")
        block = [{"actor": "GameDataActor", "query": "EventQueryIsGameDataString64", "template": item_query,
                  "set": {"Value": item}, "cases": {}}]
        has_weapon = steps[0][1].startswith("Weapon_") and steps[0][1] != steps[0][0]
        weapon_query = None
        if has_weapon:
            weapon_query = len(block)
            block.append({"actor": actor, "query": query, "template": (template, pouch_query),
                          "set": {"Actor": steps[0][1]}, "cases": {}})

        checks = []
        for owned in range(len(steps) - 1, -1, -1):
            checks.append(len(block))
            block.append({"actor": actor, "query": query, "template": (template, pouch_query),
                          "set": {"Actor": steps[owned][1]}, "cases": {}})

        outcomes = {}
        for step, (name, _pouch) in enumerate(steps):
            outcomes[step] = len(block)
            block.append({"copy_event": set_name, "next": len(block) + 1, "set": {"Value": name}})
            sale_start = len(block)
            block += self._scrub_sale_nodes(flow, sale, name, price, base=sale_start)

        for position, owned in enumerate(range(len(steps) - 1, -1, -1)):
            next_check = checks[position + 1] if position + 1 < len(checks) else outcomes[0]
            block[checks[position]]["cases"] = {
                0: outcomes[min(owned + 1, len(steps) - 1)],
                1: next_check,
            }
        if weapon_query is not None:
            block[weapon_query]["cases"] = {0: checks[0], 1: outcomes[0]}
        return block

    # prix des Peste Mojo choisi en jeu : {jeton: entier GameData (prix / 5)} (menu natif) ; sans lui,
    # prix fixe
    scrub_price_entries: dict[str, tuple[str, str]] | None = None  # {jeton: (dizaines, unités) de prix / 5}
    PRICE_LEVELS = 20  # 0 à 95 rubis par pas de 5
    INT_BRANCH_TEMPLATE = "Minigame_CatchCucco"  # EventQueryGameDataIntBranch avec un nom fixe

    def _scrub_sale_nodes(self, flow: bytes, sale: int, sold: str, price: int, base: int) -> list[dict]:
        """Vente unique de `sold` (étapes relatives : la première a l'indice `base`). Prix choisi en jeu :
        valeur = prix / 5 (0 à 19), lue en deux questions (dizaines, unités : une question ne gère que 16
        cas), puis une vente par prix (5 x valeur)."""
        message = f"EventFlowMsg/Enemy_Event:{self.SCRUB_MSG_PREFIX}{sold}"
        entry = (self.scrub_price_entries or {}).get(sold)
        if not entry:
            return [{"copy_event": sale, "next": None, "set": {"ActorName": sold, "Price": price, "SellerMessageId": message}}]
        from .formats.evfl import find_query
        template = self.codec.decompress(self.romfs / "Event" / "EventFlow" / f"{self.INT_BRANCH_TEMPLATE}.bfevfl.zs")
        branch = (template, find_query(template, "GameDataActor", "EventQueryGameDataIntBranch"))
        tens_entry, units_entry = entry
        groups = (self.PRICE_LEVELS - 1) // self.BRANCH_BASE + 1
        first_sale = base + 1 + groups
        nodes = [{"actor": "GameDataActor", "query": "EventQueryGameDataIntBranch", "template": branch,
                  "set": {"GameDataName": tens_entry}, "cases": {t: base + 1 + t for t in range(groups)}}]
        for t in range(groups):
            cases = {u: first_sale + t * self.BRANCH_BASE + u for u in range(self.BRANCH_BASE)
                     if t * self.BRANCH_BASE + u < self.PRICE_LEVELS}
            nodes.append({"actor": "GameDataActor", "query": "EventQueryGameDataIntBranch", "template": branch,
                          "set": {"GameDataName": units_entry}, "cases": cases})
        for v in range(self.PRICE_LEVELS):
            nodes.append({"copy_event": sale, "next": None,
                          "set": {"ActorName": sold, "Price": 5 * v, "SellerMessageId": message}})
        return nodes

    def _guard_fairy_ocarina(self, flow: bytes) -> tuple[bytes, list[str]]:
        from .formats.evfl import ensure_actor_member, find_action_event, find_query, insert_flow

        _, item, flag = self.OCARINA_GUARD
        idx = find_action_event(flow, *self.POUCH_ACTION, "Actor", item)
        gd, query = "GameDataActor", "EventQueryIsGameDataBool"
        flow = ensure_actor_member(flow, gd, "query", query)
        template = self.codec.decompress(self.romfs / "Event" / "EventFlow" / "DoorOfTime.bfevfl.zs")
        ask = (template, find_query(template, gd, query))
        if idx is None or ask[1] is None:
            raise KeyError("don de l'Ocarina des fées introuvable")
        # la question doit exister dans ce fichier : sinon, pas de garde (rapport)
        try:
            return insert_flow(flow, None, [{"actor": gd, "query": query, "template": ask, "set": {"GameDataName": flag},
                                             "cases": {0: "after", 1: "old"}}], before=idx)  # 0 = oui (déjà l'Ocarina du Temps) : pas de don
        except KeyError as exc:
            return flow, [f"garde de l'ocarina impossible : {exc}"]

    # chants : Dm_SY_Ocarina donne chaque chant par sa propre action (choisie selon la mélodie de la scène).
    # song_gives = {chant d'origine: objet ou jeton donné à la place}. Seule l'action de don change : le nom
    # de la Berceuse sert aussi à tester si Link la connaît (EventQueryCheckIsGet).
    SONG_FLOW = "Dm_SY_Ocarina"
    song_gives: dict[str, str] | None = None
    # each song scene also calls GetPouchContent:GetPouchContentByActorName with its own song, which really adds
    # it (Malon gave Epona's Song on top of the seed's song). The PC mod turns that call into
    # DisplayGetByActorName (same get window, no gift) naming the seed's item. The native menu blocks that
    # add in the module instead, so it leaves the scenes alone (song_scene_display = False).
    SONG_SCENES = {
        "Item_Melody_ZeldaLullaby": "Dm_MelodyGet_Zelda", "Item_Melody_EponaSong": "Dm_MelodyGet_Epona",
        "Item_Melody_SariaSong": "Dm_MelodyGet_Saria", "Item_Melody_SunSong": "Dm_MelodyGet_Sun_03",
        "Item_Melody_TimeSong": "Dm_MelodyGet_Time", "Item_Melody_StormSong": "Dm_MelodyGet_Storm",
        "Item_Melody_ForestMinuet": "Dm_MelodyGet_Forest", "Item_Melody_FireBolero": "Dm_MelodyGet_Fire",
        "Item_Melody_WaterSerenade": "Dm_MelodyGet_Water", "Item_Melody_SpiritRequiem": "Dm_MelodyGet_Spilit",
        "Item_Melody_ShadowNocturne": "Dm_MelodyGet_Shadow", "Item_Melody_LightPrelude": "Dm_MelodyGet_Shine",
    }
    SCENE_GET = ("GetPouchContent", "GetPouchContentByActorName", "DisplayGetByActorName")
    song_scene_display = True

    def _song_scene_flows(self) -> dict[str, tuple[str, str]]:
        """{scene flow: (vanilla song, item given instead)} for the scenes whose song changes."""
        if not self.song_gives or not self.song_scene_display:
            return {}
        return {self.SONG_SCENES[song]: (song, item) for song, item in self.song_gives.items()
                if song in self.SONG_SCENES}

    def _song_scene_get(self, flow: bytes, song: str, item: str) -> tuple[bytes, list[str]]:
        from .formats.evfl import find_subflow_events, retarget_subflows

        src, entry, display = self.SCENE_GET
        found = find_subflow_events(flow, src, entry, "ActorName", song)
        if not found:
            raise KeyError(f"{src}:{entry} of {song} not found")
        flow = retarget_subflows(flow, [(i, display, {"ActorName": item}) for i in found])
        return flow, [f"{song}: {len(found)} scene gift(s) -> {display} {item}"]

    def _song_gives(self, flow: bytes) -> tuple[bytes, list[str]]:
        from .formats.evfl import find_action_event, insert_flow

        report = []
        found = {}
        for song in self.song_gives:
            idx = find_action_event(flow, *self.POUCH_ACTION, "Actor", song)
            if idx is None:
                raise KeyError(f"{self.SONG_FLOW} : don de {song} introuvable")
            found[song] = idx
        for song, idx in found.items():  # copie de l'action avec l'autre objet, l'originale est sautée
            flow, r = insert_flow(flow, None, [{"copy_event": idx, "set": {"Actor": self.song_gives[song]},
                                                "next": "after"}], before=idx)
            report += r
        return flow, report

    # menu natif : point d'apparition choisi en jeu ; l'introduction lit deux entiers GameData
    # `spawn_branch_entry` = (dizaines, unités) de k (0 = rien, k = téléportation vers spawn_branch[k - 1]).
    # Une question EventQueryGameDataIntBranch ne gère que 16 cas : avec 34, la valeur 22 a mené au cas 15
    # (constaté en jeu) ; deux questions de 10 cas au plus.
    spawn_branch: list[tuple[str, str]] | None = None
    spawn_branch_entry = ("OoTRR.SpawnTens", "OoTRR.SpawnUnits")
    BRANCH_BASE = 10

    def _spawn_nodes(self, flow: bytes) -> tuple[bytes, list[dict]]:
        from .formats.evfl import ensure_actor_member, find_action, find_query

        flow = ensure_actor_member(flow, "GameDataActor", "query", "EventQueryGameDataIntBranch")
        flow = ensure_actor_member(flow, *self.WARP_ACTION[:1], "action", self.WARP_ACTION[1])
        branch_src = self.codec.decompress(self.romfs / "Event" / "EventFlow" / f"{self.INT_BRANCH_TEMPLATE}.bfevfl.zs")
        warp_src = self.codec.decompress(self.romfs / "Event" / "EventFlow" / f"{self.WARP_TEMPLATE}.bfevfl.zs")
        branch = (branch_src, find_query(branch_src, "GameDataActor", "EventQueryGameDataIntBranch"))
        warp = (warp_src, find_action(warp_src, *self.WARP_ACTION))
        if branch[1] is None or warp[1] is None:
            raise KeyError("modèles introuvables pour le point d'apparition")
        tens_entry, units_entry = self.spawn_branch_entry
        base = self.BRANCH_BASE
        n = len(self.spawn_branch)
        groups = n // base + 1  # dizaines 0 .. n // base
        if groups > 16:
            raise ValueError("trop de points d'apparition pour deux questions")
        # nœud 0 : dizaines -> nœud 1 + t ; nœuds 1..groups : unités -> téléportations
        nodes = [{"actor": "GameDataActor", "query": "EventQueryGameDataIntBranch", "template": branch,
                  "set": {"GameDataName": tens_entry}, "cases": {t: 1 + t for t in range(groups)}}]
        warp_index = {}
        first_warp = 1 + groups
        for k in range(1, n + 1):
            warp_index[k] = first_warp + k - 1
        for t in range(groups):
            cases = {}
            for u in range(base):
                k = t * base + u
                if k == 0:
                    cases[u] = "old"
                elif k <= n:
                    cases[u] = warp_index[k]
            nodes.append({"actor": "GameDataActor", "query": "EventQueryGameDataIntBranch", "template": branch,
                          "set": {"GameDataName": units_entry}, "cases": cases})
        for banc, pos in self.spawn_branch:
            nodes.append({"actor": self.WARP_ACTION[0], "action": self.WARP_ACTION[1], "template": warp,
                          "set": {"NextBanc": banc, "NextStartPos": pos, "BootEventName": ""}, "next": "old"})
        return flow, nodes

    # changement d'époque : la sous-séquence équipe l'épée Kokiri même si Link ne l'a pas (épée mélangée,
    # pas encore trouvée) ; sans l'épée en poche, l'arme de l'autre époque reste vide
    ERA_FLOW = "ReplaceEquipmentForEraChange"

    def _guard_era_sword(self, flow: bytes) -> tuple[bytes, list[str]]:
        from .formats.evfl import find_action_event, find_query, insert_flow

        idx = find_action_event(flow, "GameDataActor", "EventTriggerSetGameDataString64", "Value", "Weapon_Sword_Kokiri")
        ask = (flow, find_query(flow, "PouchSystemActor", "EventQueryIsExistInPouch"))
        if idx is None or ask[1] is None:
            raise KeyError(f"{self.ERA_FLOW} : étape de l'épée Kokiri introuvable")
        new, report = insert_flow(flow, None, [{"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
                                                # « set » n'écrit que des textes : Num (entier, 1) reste celui du
                                                # modèle ; 0 = oui (épée en poche) -> l'étape qui l'équipe
                                                "template": ask, "set": {"Actor": "Weapon_Sword_Kokiri"},
                                                "cases": {0: "old", 1: "after"}}], before=idx)
        return new, report + [f"{self.ERA_FLOW}: épée Kokiri équipée seulement si possédée"]

    # First change to adulthood: the Door of Time script (its step that adds the Master Sword) may be skipped; the sword
    # was equipped but not in the pouch, and lost as soon as Link changed swords (save read 2026-11-24:
    # IsGet.Weapon_Sword_Master false as adult). Given here when Link, child, has none. The adult's map flag
    # (world.ADULT_MAP_FLAG) and the one that lets night come (world.NIGHT_FLAG, at every change of age) are set here
    # too, for the saves made before they were start flags. world.ADULT_TIME_FREEZE_FLAG is cleared at every change of
    # age, for the saves where Sheik's scene already set it.
    def _give_master_sword(self, flow: bytes) -> tuple[bytes, list[str]]:
        from .formats.evfl import ensure_actor_member, find_action, find_query, insert_flow

        template = self.codec.decompress(self.romfs / "Event" / "EventFlow" / f"{self.POUCH_TEMPLATE}.bfevfl.zs")
        flow = ensure_actor_member(flow, *self.POUCH_ACTION[:1], "action", self.POUCH_ACTION[1])
        ask = (flow, find_query(flow, "PouchSystemActor", "EventQueryIsExistInPouch"))
        src = self.codec.decompress(self.romfs / "Event" / "EventFlow" / f"{self.TIMELINE_TEMPLATE}.bfevfl.zs")
        flow = ensure_actor_member(flow, "GameDataActor", "action", "EventTriggerSetGameDataBool")
        from .world import ADULT_MAP_FLAG, ADULT_TIME_FREEZE_FLAG, NIGHT_FLAG
        set_bool = (src, find_action(src, "GameDataActor", "EventTriggerSetGameDataBool"))
        nodes = [{"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool", "template": set_bool,
                  "set": {"GameDataName": NIGHT_FLAG, "Value": 1}, "next": 5},
                 {"actor": "Player_Event", "query": "EventQueryPlayerIsChild", "template": (flow, 0),
                  "cases": {0: 2, 1: "old"}},
                 {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool", "template": set_bool,
                  "set": {"GameDataName": ADULT_MAP_FLAG, "Value": 1}, "next": 3},
                 {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch", "template": ask,
                  "set": {"Actor": "Weapon_Sword_Master"}, "cases": {0: "old", 1: 4}},
                 {"actor": self.POUCH_ACTION[0], "action": self.POUCH_ACTION[1],
                  "template": (template, find_action(template, *self.POUCH_ACTION)),
                  "set": {"Actor": "Weapon_Sword_Master"}, "next": "old"},
                 {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool", "template": set_bool,
                  "set": {"GameDataName": ADULT_TIME_FREEZE_FLAG, "Value": 0}, "next": 1}]
        new, report = insert_flow(flow, self.ERA_FLOW, nodes)
        return new, report + [f"{self.ERA_FLOW}: Master Sword given on the way to adulthood"]

    # Blue warp after Volvagia: the script goes to Kakariko (scene Dm_Kakariko_0025), then to the Chamber of Sages. With
    # the scene skipped, Link stayed stuck in Kakariko without the reward (2026-11-24). As for the other temples, the
    # warp goes straight to the Chamber of Sages (copy of the script's own map change, step 73).
    ESCAPE_FLOW = "Dm_SY_BancChange_EscapeDungeon"
    FIRE_KAKARIKO, FIRE_SAGES = 69, 73

    def _fire_warp(self, flow: bytes) -> tuple[bytes, list[str]]:
        from .formats.evfl import find_action, insert_flow
        from .tools.events import event_line

        if "FireTemple_SageOfFire_Kakariko" not in event_line(flow, self.FIRE_KAKARIKO)[0] or \
                "FireTemple_SageOfFire_SageRoom" not in event_line(flow, self.FIRE_SAGES)[0]:
            raise KeyError(f"{self.ESCAPE_FLOW}: unexpected Fire Temple warp steps")
        src = self.codec.decompress(self.romfs / "Event" / "EventFlow" / f"{self.TIMELINE_TEMPLATE}.bfevfl.zs")
        setb = (src, find_action(src, "GameDataActor", "EventTriggerSetGameDataBool"))
        new, report = insert_flow(flow, None, [
            {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool", "template": setb,
             "set": {"GameDataName": "HavePlayedEvent.Dm_Kakariko_0025", "Value": 1}, "next": 1},
            {"copy_event": self.FIRE_SAGES, "next": None}], before=self.FIRE_KAKARIKO)
        return new, report + [f"{self.ESCAPE_FLOW}: Volvagia's warp goes straight to the Chamber of Sages"]

    # "Already given?" checks that test "does Link have the vanilla item?" (world.GIVEN_MODULES, PC-built mod): the
    # questions read a saved flag of our own, set when the check is given. (flag, step that gives, questions).
    # Dampé: the flag is set with the chest state OpenedHookShot; windmill: before the song's scene (Dm_MelodyGet_Storm).
    given_flags = False
    WINDMILL_FLOW = "Npc_Hylia_009_Adult"
    DAMPE_GIVEN = ("OoTRR.DampeHookshot", (125, "OpenedHookShot"),
                   {39: "Item_Hookshot", 74: "Item_Hookshot", 75: "Item_Longshot", 165: "Item_Hookshot",
                    167: "Item_Longshot", 422: "Item_Hookshot", 423: "Item_Hookshot", 424: "Item_Hookshot"})
    WINDMILL_GIVEN = ("OoTRR.Given.Windmill.Storms", (55, "Dm_MelodyGet_Storm"),
                      {4: "IsGet.Item_Melody_StormSong", 17: "IsGet.Item_Melody_StormSong",
                       51: "IsGet.Item_Melody_StormSong", 54: "IsGet.Item_Melody_StormSong"})

    def _given_flag(self, flow: bytes, name: str, flag: str, gives: tuple[int, str],
                    questions: dict[int, str]) -> tuple[bytes, list[str]]:
        from .formats.evfl import ensure_actor_member, find_action, find_query, insert_flow
        from .tools.events import event_line

        gd, query, action = "GameDataActor", "EventQueryIsGameDataBool", "EventTriggerSetGameDataBool"
        folder = self.romfs / "Event" / "EventFlow"
        door = self.codec.decompress(folder / "DoorOfTime.bfevfl.zs")
        src = self.codec.decompress(folder / f"{self.TIMELINE_TEMPLATE}.bfevfl.zs")
        ask, setb = (door, find_query(door, gd, query)), (src, find_action(src, gd, action))
        flow = ensure_actor_member(ensure_actor_member(flow, gd, "query", query), gd, "action", action)
        for event, item in sorted(questions.items()):
            line = event_line(flow, event)[0]
            found = re.search(r"cas=\[(.*)\]$", line)
            if item not in line or not found:
                raise KeyError(f"{name}: event {event} is not a question about {item}")
            cases = {int(v): {"event": int(t)} for v, t in re.findall(r"\((\d+), (\d+)\)", found.group(1))}
            flow, _ = insert_flow(flow, None, [{"actor": gd, "query": query, "template": ask,
                                                "set": {"GameDataName": flag}, "cases": cases}], before=event)
        if gives[1] not in event_line(flow, gives[0])[0]:
            raise KeyError(f"{name}: event {gives[0]} does not name {gives[1]}")
        flow, _ = insert_flow(flow, None, [{"actor": gd, "action": action, "template": setb,
                                            "set": {"GameDataName": flag, "Value": 1}, "next": "old"}], before=gives[0])
        return flow, [f"{name}: {len(questions)} questions read {flag} (set before event {gives[0]})"]

    # Ground items of the progressive chains (patch.ground_chains): they give the chain's last step, and right after
    # the pouch add the pickup script checks each chain: last step owned without the step before -> the last step is
    # removed and the missing step added. The check is on the pouch, not on the item just taken: if one pickup path
    # is not covered, the next item taken anywhere puts it right. (flow: step after "add to the pouch")
    ground_chains: list = []
    GROUND_FLOWS = {"Dm_SY_Get": (7, 183)}
    REMOVE_TEMPLATE = ("Goto_HyruleCastle", "Item_WeirdEgg")  # AddOrRemovePouchContent, Num -1

    def _progressive_ground(self, flow: bytes, steps: tuple[int, int]) -> tuple[bytes, list[str]]:
        from .formats.evfl import (ensure_actor_member, event_params, find_action, find_action_event, find_query,
                                   insert_flow)
        from .tools.events import event_line

        add_own, before = steps
        if "EventTriggerAddOwnToPouch" not in event_line(flow, add_own)[0] or \
                event_line(flow, add_own)[1] != [before]:
            raise KeyError("pickup script: unexpected steps")
        folder = self.romfs / "Event" / "EventFlow"
        load = lambda n: self.codec.decompress(folder / f"{n}.bfevfl.zs")
        dampe, door, timeline, pouch, egg = (load(n) for n in (self.DAMPE_FLOW, "DoorOfTime", self.TIMELINE_TEMPLATE,
                                                              self.POUCH_TEMPLATE, self.REMOVE_TEMPLATE[0]))
        pq, gq = ("PouchSystemActor", "EventQueryIsExistInPouch"), ("GameDataActor", "EventQueryIsGameDataBool")
        ga = ("GameDataActor", "EventTriggerSetGameDataBool")
        for actor, kind, member in ((pq[0], "query", pq[1]), (gq[0], "query", gq[1]), (ga[0], "action", ga[1]),
                                    (self.POUCH_ACTION[0], "action", self.POUCH_ACTION[1])):
            flow = ensure_actor_member(flow, actor, kind, member)
        remove_at = find_action_event(egg, *self.POUCH_ACTION, "Actor", self.REMOVE_TEMPLATE[1])
        templates = {"has": (dampe, find_query(dampe, *pq)), "flag": (door, find_query(door, *gq)),
                     "set": (timeline, find_action(timeline, *ga)), "add": (pouch, find_action(pouch, *self.POUCH_ACTION)),
                     "remove": (egg, event_params(egg, remove_at))}
        nodes: list[dict] = []

        def owned(step: list[str], yes, no) -> dict:
            # a weapon (bow, slingshot) stays in the pouch after its upgrades; the others are replaced by them
            if step[1].startswith("Weapon_"):
                return {"actor": pq[0], "query": pq[1], "template": templates["has"], "set": {"Actor": step[1]},
                        "cases": {0: yes, 1: no}}
            return {"actor": gq[0], "query": gq[1], "template": templates["flag"],
                    "set": {"GameDataName": f"IsGet.{step[0]}"}, "cases": {0: yes, 1: no}}

        for number, chain in enumerate(self.ground_chains):
            start, n, last = len(nodes), len(chain), chain[-1]
            # layout: question "last step?", n-1 questions, n-1 fixes of 3 actions
            fixes = start + n
            after = "old" if number == len(self.ground_chains) - 1 else fixes + 3 * (n - 1)
            nodes.append({"actor": pq[0], "query": pq[1], "template": templates["has"], "set": {"Actor": last[1]},
                          "cases": {0: start + 1, 1: after}})
            for i, step in enumerate(chain[:-1]):
                yes = start + 2 + i if i + 1 < n - 1 else after
                nodes.append(owned(step, yes, fixes + 3 * i))
            for i, step in enumerate(chain[:-1]):
                at = fixes + 3 * i
                nodes += [{"actor": self.POUCH_ACTION[0], "action": self.POUCH_ACTION[1],
                           "template": templates["remove"], "set": {"Actor": last[0]}, "next": at + 1},
                          {"actor": ga[0], "action": ga[1], "template": templates["set"],
                           "set": {"GameDataName": f"IsGet.{last[0]}", "Value": 0}, "next": at + 2},
                          {"actor": self.POUCH_ACTION[0], "action": self.POUCH_ACTION[1],
                           "template": templates["add"], "set": {"Actor": step[0]}, "next": after}]
        new, _ = insert_flow(flow, None, nodes, before=before)
        return new, ["progressive ground items: " + ", ".join("/".join(s[0] for s in c) for c in self.ground_chains)]

    # course de Dampé : la sortie de la salle d'arrivée demande le Grappin, qui est dans le coffre de la course
    # (mélangé : on peut l'ouvrir sans recevoir le Grappin). Après ce coffre (état OpenedHookShot), parler à
    # Dampé ne fait que conseiller le Grappin (SuggestExit, étape 260) ; sans Grappin ni Super Grappin, il
    # ramène Link dehors : copie du changement de zone de la chute (étape 70 : Graveyard_Adult, point 4)
    DAMPE_FLOW = "MiniGame_DampeRace"
    DAMPE_SUGGEST_EXIT, DAMPE_WARP = 260, 70

    def _dampe_exit(self, flow: bytes) -> tuple[bytes, list[str]]:
        from .formats.evfl import find_query, insert_flow
        from .tools.events import event_line

        if "MiniGame_DampeRace_End" not in event_line(flow, 68)[0] or                 "Graveyard_Adult" not in event_line(flow, 70)[0] or "SuggestExit" not in event_line(flow, 260)[0]:
            raise KeyError(f"{self.DAMPE_FLOW} : étapes de la sortie inattendues")
        ask = (flow, find_query(flow, "PouchSystemActor", "EventQueryIsExistInPouch"))
        nodes = [{"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch", "template": ask,
                  "set": {"Actor": "Item_Longshot"}, "cases": {0: "old", 1: 1}},
                 {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch", "template": ask,
                  "set": {"Actor": "Item_Hookshot"}, "cases": {0: "old", 1: 2}},
                 # copie autonome du changement de zone de la chute (Graveyard_Adult, point 4), puis fin du script.
                 # Un saut direct à l'étape 71 (soin -> changement de zone -> fin de course, dans une branche
                 # parallèle d'un autre point d'entrée) faisait planter le moteur de scripts (constaté en jeu)
                 {"copy_event": self.DAMPE_WARP, "next": None}]
        new, report = insert_flow(flow, None, nodes, before=self.DAMPE_SUGGEST_EXIT)
        return new, report + [f"{self.DAMPE_FLOW}: sortie sans Grappin après le coffre de la course"]

    # Market potion shop (child): after giving the bottle, the keeper starts the bug-catch tutorial (challenge
    # Market_Item_Bottle_TutorialEvent, step "Playing", a minigame with a no-escape area) and the door's AI
    # (Obj_Door_ShopMedicine_9089 module) only opens from inside once Market_Item_Bottle_TutorialEvent_Cleared is
    # set, which only catching the bug in a bottle does. With the gift shuffled, Link may have no bottle: softlock.
    # Fix: at the step that starts the challenge, set the Cleared flag instead (copy of the step that sets
    # ..._Started) and end there, so the minigame never starts and the door opens.
    BOTTLE_TUTORIAL_FLOW = "Npc_Hylia_020_Shop_Child"
    BOTTLE_TUTORIAL_FLAG = "Market_Item_Bottle_TutorialEvent_"

    def _skip_bottle_tutorial(self, flow: bytes) -> tuple[bytes, list[str]]:
        from .formats.evfl import find_action_event, insert_flow

        flag = self.BOTTLE_TUTORIAL_FLAG
        started = find_action_event(flow, "GameDataActor", "EventTriggerSetGameDataBool", "GameDataName", flag + "Started")
        playing = find_action_event(flow, "ChallengeSystemActor", "EventExecuteProgressChallengeStep", "StepName", "Playing")
        if started is None or playing is None:
            raise KeyError(f"{self.BOTTLE_TUTORIAL_FLOW}: bottle tutorial steps not found")
        new, report = insert_flow(flow, None, [{"copy_event": started, "set": {"GameDataName": flag + "Cleared"},
                                                "next": "after"}], before=playing)
        return new, report + [f"{self.BOTTLE_TUTORIAL_FLOW}: bug-catch tutorial skipped (door opens without a bottle)"]

    # Tower collapse: after Ganondorf (InsideGanonCastle_Dungeon_BossDie_1) the script reserves the change to the map
    # CrumblingGanonCastle; the escape (its own quest, EscapeFromCrumblingGanonCastle) ends at a door to Ganon's arena
    # whose values are the ones below. The flag is the one its way out sets (Dm_SY_BancChangeGo, look of the arena
    # before the fight). Nothing in the arena reads the escape quest or the other flags of the tower.
    COLLAPSE_FLOW = "Defeat_Ganon"
    COLLAPSE_BANC = "CrumblingGanonCastle"
    COLLAPSE_WARP = {"NextBanc": "FinalBattleField", "NextStartPos": "FinalBattleField_Entrance",
                     "BootEventName": "InsideGanonCaslte_Dungeon_Escape",
                     "EventStarterName": "FinalBattleField_Entrance"}
    COLLAPSE_FLAG = "FinalBattleField_ChangeENVForBeforeBattle"
    skip_collapse = False  # setting skip_tower_collapse

    def _skip_tower_collapse(self, flow: bytes) -> tuple[bytes, list[str]]:
        """After Ganondorf, straight to Ganon's arena (the step that changes the map, replaced with a copy)."""
        from .formats.evfl import find_action_event, insert_flow

        warp = find_action_event(flow, *self.WARP_ACTION, "NextBanc", self.COLLAPSE_BANC)
        # any step that sets a Bool to true, copied for the flag
        set_true = find_action_event(flow, "GameDataActor", "EventTriggerSetGameDataBool", "GameDataName",
                                     "InsideGanonCastele_Dungeon_Ganondorf_Die")
        if warp is None or set_true is None:
            raise KeyError(f"{self.COLLAPSE_FLOW}: steps after Ganondorf not found")
        new, report = insert_flow(flow, None, [
            {"copy_event": set_true, "set": {"GameDataName": self.COLLAPSE_FLAG}, "next": 1},
            {"copy_event": warp, "set": dict(self.COLLAPSE_WARP), "next": "after"}], before=warp)
        return new, report + [f"{self.COLLAPSE_FLOW}: tower collapse skipped (straight to Ganon's arena)"]

    def _guard_event(self, flow: bytes, guard: tuple) -> tuple[bytes, list[str]]:
        """Saute un événement (EVENT_GUARDS) tant que le drapeau est faux (0 = oui : l'événement se joue)."""
        from .formats.evfl import ensure_actor_member, find_action_event, find_query, insert_flow

        name, actor, action, param, value, flag = guard
        idx = find_action_event(flow, actor, action, param, value)
        gd, query = "GameDataActor", "EventQueryIsGameDataBool"
        flow = ensure_actor_member(flow, gd, "query", query)
        template = self.codec.decompress(self.romfs / "Event" / "EventFlow" / "DoorOfTime.bfevfl.zs")
        ask = (template, find_query(template, gd, query))
        if idx is None or ask[1] is None:
            raise KeyError(f"{name} : événement {action} {param}={value} introuvable")
        new, report = insert_flow(flow, None, [{"actor": gd, "query": query, "template": ask, "set": {"GameDataName": flag},
                                               "cases": {0: "old", 1: "after"}}], before=idx)
        return new, report + [f"{name}: {value} seulement si {flag}"]

    def _moat_gate(self, flow: bytes) -> list[dict]:
        """Douves : avec les 3 pierres, l'Ocarina du Temps et le Chant du Temps sont donnés
        directement (sans dépendre de la scène de Zelda), puis la scène habituelle se joue."""
        from .formats.evfl import find_action, find_query

        gd, query = "GameDataActor", "EventQueryIsGameDataBool"
        ask = (flow, find_query(flow, gd, query))
        template = self.codec.decompress(self.romfs / "Event" / "EventFlow" / f"{self.POUCH_TEMPLATE}.bfevfl.zs")
        give = (template, find_action(template, *self.POUCH_ACTION))
        if ask[1] is None or give[1] is None:
            raise KeyError("modèles introuvables pour l'Ocarina du Temps (DoorOfTime)")
        # l'ocarina n'est visible qu'avec les 3 pierres (condition de présence) : pas de question ici
        items = list(self.moat_items)
        return [{"actor": self.POUCH_ACTION[0], "action": self.POUCH_ACTION[1], "template": give,
                 "set": {"Actor": item}, "next": i + 1 if i + 1 < len(items) else "old"}
                for i, item in enumerate(items)]

    def _write_logic(self, patches: dict[str, dict[str, str]], out_romfs: Path) -> list[str]:
        """Remplace des chaînes de même longueur dans des modules de logique AINB (Logic/*.ainb)."""
        report = []
        for module, mapping in sorted(patches.items()):
            rel = f"Logic/{module}.logic.module.ainb"
            data = bytearray((self.romfs / rel).read_bytes())
            pool = int.from_bytes(data[0x24:0x28], "little")
            for old, new in mapping.items():
                if len(old) != len(new):
                    raise ValueError(f"{module} : {old!r} et {new!r} doivent avoir la même longueur")
                needle = b"\0" + old.encode() + b"\0"
                at = data.find(needle, pool - 1)
                if at < 0:
                    raise KeyError(f"{module} : chaîne {old!r} introuvable")
                data[at + 1:at + 1 + len(old)] = new.encode()
                report.append(f"{rel}: {old} -> {new}")
            dest = out_romfs / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(bytes(data))
        return report

    def _write_logic_graph_edits(self, edits: dict[str, dict], out_romfs: Path) -> list[str]:
        """Replace an AINB logic node while preserving its index and graph connections."""
        import copy
        import ainb

        report = []
        for module, edit in sorted(edits.items()):
            rel = f"Logic/{module}.logic.module.ainb"
            script = ainb.AINB.from_binary((self.romfs / rel).read_bytes())
            index = edit["node"]
            if not 0 <= index < len(script.nodes):
                raise IndexError(f"{module}: node {index} is outside the module")
            target = script.nodes[index]
            if target.name != edit["expected"]:
                raise KeyError(f"{module}: node {index} is {target.name}, expected {edit['expected']}")
            target_inputs = {p.name: p.default_value for p in (target.params.string_inputs or [])}
            if any(target_inputs.get(name) != value for name, value in edit["expected_inputs"].items()):
                raise ValueError(f"{module}: node {index} inputs changed: {target_inputs}")

            template_rel = f"Logic/{edit['template_module']}.logic.module.ainb"
            template_script = ainb.AINB.from_binary((self.romfs / template_rel).read_bytes())
            template_index = edit["template_node"]
            if not 0 <= template_index < len(template_script.nodes):
                raise IndexError(f"{edit['template_module']}: node {template_index} is outside the module")
            template = template_script.nodes[template_index]
            if template.name != edit["template_node_name"]:
                raise KeyError(f"{edit['template_module']}: node {template_index} is {template.name}, "
                               f"expected {edit['template_node_name']}")
            output_index = next((i for i, p in enumerate(template.params.bool_outputs or [])
                                 if p.name == edit["output"]), None)
            if output_index is None:
                raise KeyError(f"{edit['template_module']}: {template.name} has no {edit['output']} output")
            for consumer in edit["consumers"]:
                consumer_index = consumer["node"]
                if not 0 <= consumer_index < len(script.nodes):
                    raise IndexError(f"{module}: consumer node {consumer_index} is outside the module")
                consumer_node = script.nodes[consumer_index]
                if consumer_node.name != consumer["expected"]:
                    raise KeyError(f"{module}: consumer node {consumer_index} is {consumer_node.name}, "
                                   f"expected {consumer['expected']}")
                input_plug = next((p for p in (consumer_node.params.bool_inputs or [])
                                   if p.name == consumer["input"]), None)
                if input_plug is None:
                    raise KeyError(f"{module}: node {consumer_index} has no {consumer['input']} input")
                sources = input_plug.source if isinstance(input_plug.source, list) else [input_plug.source]
                matches = [source for source in sources if source.src_node_index == index]
                if len(matches) != 1 or matches[0].src_output_index != consumer["source_output"]:
                    raise ValueError(f"{module}: node {consumer_index} {consumer['input']} does not use "
                                     f"node {index} output {consumer['source_output']}")
                matches[0].src_output_index = output_index
            replacement = copy.deepcopy(template)
            replacement.index = target.index
            replacement.guid = target.guid
            condition = next((p for p in (replacement.params.string_inputs or [])
                              if p.name == "GameDataNameBoolExp"), None)
            if condition is None:
                raise KeyError(f"{edit['template_module']}: {template.name} has no GameDataNameBoolExp input")
            condition.default_value = edit["expression"]
            script.nodes[index] = replacement
            dest = out_romfs / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(script.to_binary())
            report.append(f"{rel}: node {index} {target.name} -> {template.name} ({edit['expression']})")
        return report

    def _write_logic_ints(self, patches: dict[str, list], out_romfs: Path) -> list[str]:
        """Changes integer inputs (default values) of logic module nodes: {module: [(node, input, old, new)]}.

        The ainb library re-serialises a module with a few bytes in another order, so it only locates the value:
        the 4 bytes that change in its output are patched in the original file, which keeps everything else."""
        import ainb

        report = []
        for module, edits in sorted(patches.items()):
            rel = f"Logic/{module}.logic.module.ainb"
            raw = (self.romfs / rel).read_bytes()
            data = bytearray(raw)
            for node, name, old, new in edits:
                script = ainb.AINB.from_binary(raw)
                plug = next((p for p in script.nodes[node].params.int_inputs or [] if p.name == name), None)
                if plug is None or plug.default_value != old:
                    raise KeyError(f"{module}: node {node} {name} = {getattr(plug, 'default_value', None)}, "
                                   f"expected {old}")
                before = script.to_binary()
                plug.default_value = new
                after = script.to_binary()
                changed = [i for i in range(len(before)) if before[i] != after[i]] if len(before) == len(after) else []
                if not changed or changed[-1] - changed[0] > 3:
                    raise ValueError(f"{module}: node {node} {name}: value not located")
                at = changed[0] - changed[0] % 4
                if int.from_bytes(raw[at:at + 4], "little", signed=True) != old:
                    raise ValueError(f"{module}: node {node} {name}: value {old} not at 0x{at:x} in the original")
                data[at:at + 4] = new.to_bytes(4, "little", signed=True)
                report.append(f"{rel}: node {node} {name} {old} -> {new}")
            dest = out_romfs / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(bytes(data))
        return report
    POUCH_TEMPLATE = "Dm_Kokiri_0155"
    POUCH_ACTION = ("PouchSystemActor", "EventTriggerAddOrRemovePouchContent")
    PICKUP_BASE = "Obj_Heart_Container"
    SHOP_ONCE = "?Component/ActorGameDataSetting/NoRespawn.game__component__ActorGameDataSetting.bgyml"
    pickup_models = True  # l'objet ramassable prend le modèle 3D de l'objet donné
    pickup_pouch = True  # ... et ses paramètres d'inventaire (traitement spécial de l'ocarina, etc.)
    # jetons « SELF » : fichiers ajoutés à chaque archive de jeton (modèles des objets possibles, sous
    # leur chemin d'origine) ; le module natif redirige le modèle du jeton vers celui de l'objet placé
    token_model_files: dict[str, bytes] | None = None

    def _use_item_model(self, sarc, param_path: str, name: str, item: str, pouch_params: bool = True,
                        rupee: bool = False) -> bool:
        """Remplace le modèle et l'animation du réceptacle par ceux de l'objet donné.

        Les fichiers de l'objet sont copiés sous le nom du nouvel acteur (un même
        chemin doit avoir le même contenu dans toutes les archives du jeu).
        Rien n'est changé si l'objet n'a pas son propre modèle (chants : rubis)."""
        from .formats.sarc import read_sarc

        item_pack = self.romfs / "Pack" / "Actor" / f"{item}.pack.zs"
        if not item_pack.exists():
            return False
        files = read_sarc(self.codec.decompress(item_pack))

        def component(key: str) -> str | None:
            # suit la chaîne $parent dans l'archive de l'objet
            path = f"Actor/{item}.engine__actor__ActorParam.bgyml"
            while path in files:
                param = read_byml(files[path])
                ref = param.get("Components", {}).get(key)
                if ref:
                    return ref.lstrip("?")
                parent = param.get("$parent", "")
                path = "Actor/" + parent.split("/")[-1].replace(".gyml", ".bgyml") if parent else ""
            return None

        param = read_byml(sarc.files[param_path])
        pouch = component("PouchContentRef")
        if self.pickup_pouch and pouch_params and pouch and pouch in files:
            # paramètres d'inventaire de l'objet (et non ceux du réceptacle) : son traitement
            # spécial (SpecialDeal, ex. l'ocarina) et sa catégorie. Fichiers copiés sous leur
            # chemin d'origine, avec leurs parents présents dans l'archive de l'objet.
            p = pouch
            while p and p in files:
                sarc.files[p] = files[p]
                sarc.align[p] = 8
                parent = read_byml(files[p]).get("$parent", "")
                p = "Component/PouchContentParam/" + parent.split("/")[-1].replace(".gyml", ".bgyml") if parent else ""
            param["Components"]["PouchContentRef"] = "?" + pouch
            sarc.files[param_path] = write_byml(param, byml_version(sarc.files[param_path]))
        model, anim = component("ModelInfoRef"), component("AnimationRef")
        if not model or model not in files:
            return False
        if read_byml(files[model]).get("ModelProjectName") == "Obj_Rupee" and not rupee:
            return False  # a rupee model only for a real rupee (rupee: multiworld chests), not for songs
        for key, src, folder, kind in (("ModelInfoRef", model, "ModelInfo", "engine__component__ModelInfo"),
                                       ("AnimationRef", anim, "AnimationParam", "engine__component__AnimationParam")):
            if not src or src not in files:
                # pas d'animation propre (ex. Ocarina du Temps) : pas celle du réceptacle non plus
                param["Components"][key] = ""
                continue
            dest = f"Component/{folder}/{name}.{kind}.bgyml"
            sarc.files[dest] = files[src]
            sarc.align[dest] = 8
            param["Components"][key] = "?" + dest
        # sans les étincelles rouges du réceptacle (effet ELink « Obj_Heart_Container »)
        param["Components"]["ELinkRef"] = ""
        sarc.files[param_path] = write_byml(param, byml_version(sarc.files[param_path]))
        return True

    def _write_key_flows(self, key_events: dict[str, tuple[str, str]], out_romfs: Path,
                         mw_events: dict[str, str] | None = None) -> list[str]:
        """Scripts of the chest events that give a key outside its dungeon (keys.py): copies of the boss key
        chest script (ForestTemple_Gimmick) where Navi's line after the opening sequence becomes
        "DungeonInfo.<game>.SmallKeyNum + 1" or "DungeonInfo.<game>.IsGetBossKey = true". The RSDB rows
        (EventSetting, GameAnalyzedEventInfo) come with the patch's rsdb_changes.
        mw_events: multiworld chests holding another player's item ({event: saved Int}): same copy, the line
        becomes "<Int> + 1" (multiworld.slot_patch); the script is named after the event."""
        from . import keys as keys_mod
        from .formats.evfl import ensure_actor_member, event_params, insert_flow, rename_flow

        specs = [(keys_mod.flow_name(kind, game), kind, keys_mod.COUNTER[kind].format(game=game),
                  f"chest event {event}") for event, (kind, game) in sorted(key_events.items())]
        specs += [(event, keys_mod.SMALL, counter, f"multiworld chest event, {counter} + 1")
                  for event, counter in sorted((mw_events or {}).items())]

        folder = self.romfs / "Event" / "EventFlow"
        src = folder / f"{keys_mod.TEMPLATE_FLOW}.bfevfl.zs"
        raw = self.codec.decompress(src)
        actions = self.codec.decompress(folder / f"{keys_mod.ACTION_TEMPLATE_FLOW}.bfevfl.zs")
        src_rel = src.relative_to(self.romfs).as_posix()[:-3]
        report = []
        for flow_name, kind, counter, what in specs:
            action = keys_mod.ACTION[kind]
            # its own name first (rename_flow reads the untouched header layout)
            flow = ensure_actor_member(rename_flow(raw, keys_mod.TEMPLATE_FLOW, flow_name), "GameDataActor", "action", action)
            node = {"actor": "GameDataActor", "action": action,
                    "template": (actions, event_params(actions, keys_mod.ACTION_TEMPLATE_STEP[kind])),
                    "set": {"GameDataName": counter}, "next": None}
            new, steps = insert_flow(flow, None, [node], before=keys_mod.TEMPLATE_STEP)
            # the copy names itself (file and flowchart names, the only two references): with the template's name
            # the chest never opened (Longshot, 2026-11-17: template event fine, copy refused)
            name = f"{flow_name}.bfevfl"
            rel = f"Event/EventFlow/{name}"
            self.restbl.set(rel, self.restbl.get(src_rel) + max(0, len(new) - len(raw)))
            dest = out_romfs / (rel + ".zs")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.codec.compress(dest.name, new))
            report.append(f"{name}: {what} ({'; '.join(steps)})")
        return report

    MW_TEXT_FORBIDDEN = re.compile("[\x00-\x1f\x7f]")  # control characters (0x0e starts a text tag)

    def _mw_texts(self, mw_actors: dict[str, dict[str, str]]) -> dict[str, bytes]:
        """Get texts of the multiworld chest actors: "You found Pomme's Hookshot!" and the caption under it,
        English in every language for now; the item's name as the game writes it in English (mw_log)."""
        from .mw_log import labeller
        label = labeller(self.romfs)
        out: dict[str, bytes] = {}
        for actor, spec in sorted(mw_actors.items()):
            owner = self.MW_TEXT_FORBIDDEN.sub("", spec["owner"]).strip() or "another player"
            item = self.MW_TEXT_FORBIDDEN.sub("", label(spec["item"]))
            out[f"{actor}_Name"] = f"{owner}'s {item}".encode()
            out[f"{actor}_GetMessage"] = f"You found {owner}'s {item}!".encode()
            out[f"{actor}_GetCaption"] = f"It is on its way to {owner}'s game.".encode()
        return out

    NAVI_PACK = "Pack/NaviBallonMess.pack"
    NAVI_PARAM = "Game/NaviBalloonMessageParam/{}.game__navi__NaviBalloonMessageParam"
    NAVI_BASE = "Return000"  # "You OK?" after a fall: asked for, ignores the interval between two balloons
    NAVI_LONG = 1835921017  # flag_hash("Long"), value of DisplayTime / DestructionTime

    @staticmethod
    def _navi_label(number: str) -> str:
        return f"OoTRR_Navi_{int(number):03d}"

    def _navi_texts(self, balloons: dict[str, list[str]]) -> dict[str, bytes]:
        """{NaviChat label: text} of the multiworld balloons, English in every language (as `_mw_texts`)."""
        from .formats.msbt import tag
        from .mw_log import labeller
        from .mw_navi import text
        label, on, off = labeller(self.romfs), tag(0, 3, b"\x00\x00"), tag(0, 3, b"\xff\xff")
        return {self._navi_label(n): text(sender, label(item) if item else "", on, off)
                for n, (sender, item) in balloons.items()}

    def _write_navi_balloons(self, balloons: dict[str, list[str]], out_romfs: Path) -> list[str]:
        """Navi's multiworld balloons (mw_navi): parameters copied from NAVI_BASE and their line in the balloon table."""
        from .formats.byml import U32
        from .formats.gamedata import flag_hash
        from .formats.sarc import Sarc
        from .mw_navi import raw_value

        path = self.romfs / f"{self.NAVI_PACK}.zs"
        raw = self.codec.decompress(path)
        sarc = Sarc(raw)
        base = self.NAVI_PARAM.format(self.NAVI_BASE) + ".bgyml"
        template = sarc.files[base]
        table_path, = (self.romfs / "GameParameter" / "NaviMgrGlobalParam").glob("*.bgyml")
        table_raw = table_path.read_bytes()
        table = read_byml(table_raw)
        for n in balloons:
            param = read_byml(template)
            param.update(Name=f"OoTRR {n}", LabelList=[{"Label": self._navi_label(n), "Proportion": 1}],
                         DisplayTime=U32(self.NAVI_LONG), DestructionTime=U32(self.NAVI_LONG),
                         IsNotRequestInCombat=False, IsDisplayDuringAttention=True, IsSetReadFlagIfNoRequest=False)
            data = write_byml(param, byml_version(template))
            name = self.NAVI_PARAM.format(f"OoTRR{int(n):03d}")
            sarc.files[f"{name}.bgyml"], sarc.align[f"{name}.bgyml"] = data, sarc.align[base]
            self.restbl.set(f"{name}.bgyml", self.restbl.get(base) + max(0, len(data) - len(template)) + 0x200)
            key = flag_hash(raw_value(int(n)))
            if table["BalloonMessageParamList"].get(key) != "":
                raise KeyError(f"Navi balloon {n} is not free")
            table["BalloonMessageParamList"][key] = f"Work/{name}.gyml"
        for rel, old, new in ((f"{self.NAVI_PACK}.zs", raw, sarc.to_bytes()),
                              (table_path.relative_to(self.romfs).as_posix(), table_raw,
                               write_byml(table, byml_version(table_raw)))):
            self.restbl.resize_like(rel.removesuffix(".zs"), len(old), len(new))
            dest = out_romfs / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.codec.compress(dest.name, new) if rel.endswith(".zs") else new)
        return [f"{self.NAVI_PACK}: {len(balloons)} multiworld balloons"]

    def _write_mw_actors(self, mw_actors: dict[str, dict[str, str]], out_romfs: Path) -> dict[str, dict[str, dict]]:
        """Actors dropped by the multiworld chests: copies of the placeholder key (multiworld.REMOTE_PLACEHOLDER,
        "NotPushToPouch": nothing goes to the pouch), one per chest so that each one has its own texts (the get
        window reads `<actor>_GetMessage` / `_GetCaption`; GAME_KNOWLEDGE: a missing text blocks the game).
        Each copy also takes the model and animation of the owner's item (`_use_item_model`, as the ground items;
        unchanged when the item has no model of its own, e.g. rupees). Writes the archives, returns the RSDB rows."""
        from .formats.sarc import Sarc
        from .multiworld import REMOTE_PLACEHOLDER as base
        from .mw_log import _ALIASES, _RELATED

        raw = self.codec.decompress(self.romfs / "Pack" / "Actor" / f"{base}.pack.zs")
        margin = self.restbl.get(f"Pack/Actor/{base}.pack") - len(raw)
        rsdb: dict[str, dict[str, dict]] = {"ActorInfo": {}, "GameActorInfo": {}, "PouchActorInfo": {}}
        models: dict[str, str] = {}
        for name in sorted(mw_actors):
            sarc = Sarc(raw)
            old_param = f"Actor/{base}.engine__actor__ActorParam.bgyml"
            new_param = f"Actor/{name}.engine__actor__ActorParam.bgyml"
            sarc.files[new_param] = sarc.files.pop(old_param)
            sarc.align[new_param] = sarc.align.pop(old_param)
            item = _ALIASES.get(mw_actors[name]["item"], mw_actors[name]["item"])
            for actor in [item] + [item.replace(a, b, 1) for a, b in _RELATED if item.startswith(a)]:
                if self._use_item_model(sarc, new_param, name, actor, pouch_params=False, rupee=True):
                    models[name] = actor
                    break
            data = sarc.to_bytes()
            rel = f"Pack/Actor/{name}.pack"
            self.restbl.set(rel, len(data) + margin)
            dest = out_romfs / (rel + ".zs")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.codec.compress(dest.name, data))
            rsdb["ActorInfo"][name] = {"__new": True, "__copy_from": base, "ActorName": name}
            rsdb["GameActorInfo"][name] = {"__new": True, "__copy_from": base}
            rsdb["PouchActorInfo"][name] = {"__new": True, "__copy_from": base}
        self.mw_models = models
        return rsdb

    def _write_pickups(self, pickups: dict[str, str], out_romfs: Path) -> dict[str, dict[str, dict]]:
        """Crée des objets ramassables sur mesure : copie du réceptacle de cœur qui donne un autre objet.

        pickups : {nouveau nom d'acteur: objet donné (ex. Item_Hookshot)}
        L'objet peut s'écrire « OBJET@ACTEUR » pour copier un autre acteur que le
        réceptacle (ex. un article de boutique Shop_Weapon_Shield_Deku). OBJET = « SELF » : l'objet
        donné porte le nom de l'acteur lui-même (jeton remplacé au ramassage par le module natif),
        paramètres d'inventaire copiés de ACTEUR.
        Écrit les archives et retourne les lignes RSDB à ajouter (fusionnées avec rsdb_changes)."""
        from .formats.sarc import Sarc

        bases: dict[str, tuple[bytes, int]] = {}
        rsdb: dict[str, dict[str, dict]] = {"ActorInfo": {}, "GameActorInfo": {}, "PouchActorInfo": {}}
        for name, spec in sorted(pickups.items()):
            item, _, base = spec.partition("@")
            base = base or self.PICKUP_BASE
            pouch_from = item
            if item == "SELF":
                item, pouch_from = name, base
            if base not in bases:
                raw = self.codec.decompress(self.romfs / "Pack" / "Actor" / f"{base}.pack.zs")
                bases[base] = (raw, self.restbl.get(f"Pack/Actor/{base}.pack") - len(raw))
            base_raw, margin = bases[base]
            sarc = Sarc(base_raw)
            old_param = f"Actor/{base}.engine__actor__ActorParam.bgyml"
            new_param = f"Actor/{name}.engine__actor__ActorParam.bgyml"
            sarc.files[new_param] = sarc.files.pop(old_param)
            sarc.align[new_param] = sarc.align.pop(old_param)
            if pouch_from != item:  # jeton SELF : modèle propre (copie de celui du cœur), redirigé en jeu
                self._use_item_model(sarc, new_param, name, base, pouch_params=False)
                for path, data in (self.token_model_files or {}).items():
                    sarc.files[path] = data
                    sarc.align[path] = 8
            elif self.pickup_models:
                self._use_item_model(sarc, new_param, name, item, pouch_params=not base.startswith("Shop_"))
            if base.startswith("Shop_"):
                # article de boutique : vendu une seule fois (le bouclier Mojo d'origine réapparaît toujours)
                param = read_byml(sarc.files[new_param])
                param["Components"]["ActorGameDataSetting"] = self.SHOP_ONCE
                sarc.files[new_param] = write_byml(param, byml_version(sarc.files[new_param]))
            data = sarc.to_bytes()
            rel = f"Pack/Actor/{name}.pack"
            self.restbl.set(rel, len(data) + margin)
            dest = out_romfs / (rel + ".zs")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.codec.compress(dest.name, data))
            rsdb["ActorInfo"][name] = {"__new": True, "__copy_from": base, "ActorName": item}
            rsdb["GameActorInfo"][name] = {"__new": True, "__copy_from": base}
            rsdb["PouchActorInfo"][name] = {"__new": True, "__copy_from": pouch_from}
        return rsdb

    def build(self, changes: dict[int, dict], out_romfs: Path | str,
              start_flags: dict[str, object] | None = None,
              event_changes: dict[str, dict[str, str]] | None = None,
              pack_changes: dict[str, dict[str, dict]] | None = None,
              rsdb_changes: dict[str, dict[str, dict]] | None = None,
              pickups: dict[str, str] | None = None,
              event_skips: dict[str, list[str]] | None = None,
              start_items: list[str] | None = None,
              moat_gate: bool = False,
              logic_patches: dict[str, dict[str, str]] | None = None,
              logic_ints: dict[str, list] | None = None,
              bool_exps: dict[str, list] | None = None,
              start_warp: tuple[str, str] | None = None,
              scrub_sales: dict[str, int] | None = None,
              scrub_progressive: dict[str, list[list[str]]] | None = None,
              questions: list[str] | None = None,
              timeline_skips: dict[str, list[str]] | None = None,
              timeline_fade_in: list[str] | None = None,
              ainb_edits: dict[str, dict] | None = None,
              key_events: dict[str, tuple[str, str]] | None = None,
              mw_events: dict[str, str] | None = None,
              mw_actors: dict[str, dict[str, str]] | None = None,
              mw_navi: dict | None = None,
              logic_graph_edits: dict[str, dict] | None = None,
              event_entry_gates: dict[str, dict[str, dict[str, str]]] | None = None) -> list[str]:
        """changes : {hash: {"Drop__DropActor": "...", "GetEventName": ... ou None pour supprimer}}
        start_flags : {nom de drapeau: valeur au début d'une nouvelle partie}
        event_changes : {flux d'événements: {ancien objet: nouvel objet}}"""
        out_romfs = Path(out_romfs)
        report = []
        applied: set[int] = set()
        for path in self.find_files_with(set(changes)):
            raw = self.codec.decompress(path)
            root = read_byml(raw)
            # acteurs retirés de la carte (ex. PNJ qui bloque un passage)
            removed = [a for a in root["Actors"] if changes.get(a.get("Hash"), {}).get("__delete")]
            if removed:
                gone = {a["Hash"] for a in removed}
                root["Actors"] = [a for a in root["Actors"] if a["Hash"] not in gone]
                # plus aucune référence vers eux : liens, logique de groupe (AiGroups), listes de groupes
                for a in root["Actors"]:
                    if "Links" in a:
                        a["Links"] = [l for l in a["Links"] if l.get("Dst") not in gone]
                if "AiGroups" in root:
                    dropped = [g for g in root["AiGroups"]
                               if any(r.get("Reference") in gone for r in g.get("References", []))]
                    root["AiGroups"] = [g for g in root["AiGroups"] if g not in dropped]
                    report += [f"{path.name}: logique de groupe retirée {g.get('Logic')}" for g in dropped]
                for key in ("FarDeleteGroups", "SimultaneousGroups"):
                    if key in root:
                        root[key] = [[h for h in grp if h not in gone] for grp in root[key]]
                        root[key] = [grp for grp in root[key] if grp]
                for a in removed:
                    applied.add(a["Hash"])
                    report.append(f"{path.parent.name}/{path.name}: {a['Hash']} {a.get('Gyaml')} retiré")
            added = []
            for actor in root["Actors"]:
                change = changes.get(actor.get("Hash"))
                if not change:
                    continue
                for clone in change.get("__clone", []):
                    # nouvel acteur : copie de celui-ci (après modification), décalée et renommée
                    added.append((actor, clone))
                dyn = actor.setdefault("Dynamic", {})
                for key, value in change.items():
                    if key == "__clone":
                        continue
                    if key == "__add_links":  # liens ajoutés (ex. marchand -> copie d'un article)
                        actor.setdefault("Links", []).extend(dict(l) for l in value)
                        report.append(f"{path.parent.name}/{path.name}: {actor['Hash']} {len(value)} liens ajoutés")
                        continue
                    if key == "Presence" and value is None:  # condition d'apparition retirée
                        actor.pop("Presence", None)
                        report.append(f"{path.parent.name}/{path.name}: {actor['Hash']} Presence retirée")
                        continue
                    if key in ("Presence", "Rotate", "Translate"):  # champs de l'acteur lui-même
                        actor[key] = type(actor.get(key, value))(value) if key != "Presence" else dict(value)
                        report.append(f"{path.parent.name}/{path.name}: {actor['Hash']} {key}: {value}")
                        continue
                    if key == "__progressive_chest":  # progressive item: conditional chest (patch.progressive_chest)
                        old = actor.get("Gyaml", "")
                        actor["Gyaml"] = "Obj_TBox_A_06_NoBake" if old.endswith("NoBake") else "Obj_TBox_A_06"
                        if old != actor["Gyaml"]:
                            report.append(f"{path.parent.name}/{path.name}: {actor['Hash']} Gyaml: {old} -> "
                                          f"{actor['Gyaml']} (progressive item)")
                        continue
                    if key == "Gyaml":  # type d'acteur (ex. remplacer un cœur par un coffre)
                        old = actor.get("Gyaml")
                        actor["Gyaml"] = value
                        report.append(f"{path.parent.name}/{path.name}: {actor['Hash']} Gyaml: {old} -> {value}")
                        continue
                    old = dyn.get(key)
                    if value is None:
                        dyn.pop(key, None)
                    else:
                        dyn[key] = value
                    report.append(f"{path.parent.name}/{path.name}: {actor['Hash']} {key}: {old} -> {value}")
                applied.add(actor["Hash"])
            for source, clone in added:
                import copy
                from .formats.byml import U32, U64
                new_actor = copy.deepcopy(source)
                new_actor["Hash"] = U64(clone["Hash"])
                new_actor["SRTHash"] = U32(clone["Hash"] & 0xFFFFFFFF)
                if "Phive" in new_actor:
                    new_actor["Phive"] = {"Placement": {"ID": U64(clone["Hash"])}}
                new_actor["Gyaml"] = clone.get("Gyaml", source["Gyaml"])
                new_actor.pop("Links", None)
                if "Links" in clone:  # liens propres à la copie (ex. marchand -> articles de la variante)
                    new_actor["Links"] = [dict(l) for l in clone["Links"]]
                if "Translate" in clone:
                    new_actor["Translate"] = [float(v) for v in clone["Translate"]]
                else:
                    off = clone.get("Offset", [0.0, 0.0, 0.0])
                    new_actor["Translate"] = [type(v)(v + o) for v, o in zip(source["Translate"], off)]
                for key in ("Rotate", "Presence", "Dynamic"):
                    if key in clone:
                        new_actor[key] = list(clone[key]) if key == "Rotate" else dict(clone[key])
                if any(a.get("Hash") == new_actor["Hash"] for a in root["Actors"]):
                    raise KeyError(f"hash déjà utilisé dans {path.name} : {clone['Hash']}")
                root["Actors"].append(new_actor)
                report.append(f"{path.parent.name}/{path.name}: nouvel acteur {new_actor['Hash']} {new_actor['Gyaml']}")
            new = write_byml(root, byml_version(raw))
            rel = path.relative_to(self.romfs).as_posix()
            self.restbl.resize_like(rel[:-3], len(raw), len(new))
            dest = out_romfs / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.codec.compress(path.name, new))

        missing = set(changes) - applied
        if missing:
            raise KeyError(f"acteurs introuvables : {sorted(missing)}")
        saved_ints = [e["timer"] for e in (ainb_edits or {}).values() if "timer" in e]
        if mw_events:  # multiworld: one saved Int per remote chest, and the received items counter
            from .multiworld import RECEIVED_COUNTER
            saved_ints += sorted(mw_events.values()) + [RECEIVED_COUNTER]
        if mw_navi:
            saved_ints.append(mw_navi["mark"])
        saved_bools = []
        if self.given_flags:
            from .world import DAMPE_FLAG, GIVEN_MODULES, WINDMILL_FLAG
            saved_bools = [DAMPE_FLAG, WINDMILL_FLAG]
            logic_patches = {**(logic_patches or {}), **GIVEN_MODULES}
        if start_flags or bool_exps or saved_ints or saved_bools:
            report += self._write_gamedata(start_flags or {}, out_romfs, bool_exps, saved_ints, saved_bools)
        if True:  # ERA_FLOW (épée Kokiri au changement d'époque) est toujours modifié
            report += self._write_events(event_changes or {}, out_romfs, event_skips, start_items, moat_gate,
                                         start_warp, scrub_sales, scrub_progressive, questions, timeline_skips,
                                         timeline_fade_in, event_entry_gates)
        if logic_patches:
            report += self._write_logic(logic_patches, out_romfs)
        if logic_graph_edits:
            edited_modules = set(logic_patches or {}) | set(logic_ints or {})
            duplicates = set(logic_graph_edits) & edited_modules
            if duplicates:
                raise ValueError(f"modules edited twice: {sorted(duplicates)}")
            report += self._write_logic_graph_edits(logic_graph_edits, out_romfs)
        if logic_ints:
            if set(logic_ints) & set(logic_patches or {}):
                raise ValueError(f"modules edited twice: {sorted(set(logic_ints) & set(logic_patches))}")
            report += self._write_logic_ints(logic_ints, out_romfs)
        navi = (ainb_edits or {}).get("navi_return")
        navi_texts = self._navi_texts(mw_navi["balloons"]) if mw_navi else None
        if scrub_sales or questions or mw_actors or navi or navi_texts:
            progressive_items = {step[0] for chain in (scrub_progressive or {}).values() for step in chain}
            items = sorted(set(scrub_sales or {}) | progressive_items | set(self.scrub_message_items)) \
                if scrub_sales or questions else []
            report += self._write_messages(items, out_romfs, questions or [],
                                           self._mw_texts(mw_actors) if mw_actors else None, bool(navi),
                                           navi_texts)
        if mw_navi:
            report += self._write_navi_balloons(mw_navi["balloons"], out_romfs)
        if key_events or mw_events:
            report += self._write_key_flows(key_events or {}, out_romfs, mw_events)
        if pack_changes:
            report += self._write_packs(pack_changes, out_romfs)
        if ainb_edits:
            report += self._write_ainb_edits(ainb_edits, out_romfs, pack_changes)
        rsdb_all: dict[str, dict[str, dict]] = {t: dict(rows) for t, rows in (rsdb_changes or {}).items()}
        if navi:
            navi_report, rows_by_table = self._write_navi_return(navi, out_romfs)
            report += navi_report
            for table, rows in rows_by_table.items():
                rsdb_all.setdefault(table, {}).update(rows)
        if pickups:
            for table, rows in self._write_pickups(pickups, out_romfs).items():
                rsdb_all.setdefault(table, {}).update(rows)
            report.append(f"{len(pickups)} objets ramassables créés : {pickups}")
        if mw_actors:
            for table, rows in self._write_mw_actors(mw_actors, out_romfs).items():
                rsdb_all.setdefault(table, {}).update(rows)
            report.append(f"{len(mw_actors)} multiworld chest items created, {len(self.mw_models)} with their item's "
                          f"model")
        if rsdb_all:
            report += self._write_rsdb(rsdb_all, out_romfs)

        rel = self.restbl_path.relative_to(self.romfs)
        dest = out_romfs / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zstandard.ZstdCompressor(level=16).compress(self.restbl.to_bytes()))
        return report


def emulator_root() -> Path:
    r"""Dossier de données de l'émulateur : $OOTRR_EMU_DIR, sinon %APPDATA%\fritchii (Fritchii récent)
    s'il existe, sinon %APPDATA%\eden (Eden et anciennes versions de Fritchii)."""
    if os.environ.get("OOTRR_EMU_DIR"):
        return Path(os.environ["OOTRR_EMU_DIR"])
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    for name in ("fritchii", "eden"):
        if (appdata / name / "load").is_dir():
            return appdata / name
    return appdata / "eden"


def install(mod_dir: Path, eden_root: Path, name: str) -> Path:
    """Copie le mod dans le dossier de mods de l'émulateur (load/<TitleID>/<nom>)."""
    target = eden_root / "load" / TITLE_ID / name
    try:
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(mod_dir, target)
    except PermissionError:
        raise SystemExit(f"Error: files of the {name} mod are locked. Close the emulator (or the game) and run the command again.")
    return target
