"""Construction d'un mod LayeredFS : change le contenu de coffres identifiés par leur Hash.

Le mod contient uniquement les fichiers modifiés (cartes + table des tailles).
Les fichiers du jeu d'origine ne sont jamais modifiés.
"""

from __future__ import annotations

import os
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
                        bool_exps: dict[str, list] | None = None) -> list[str]:
        """Change la valeur de départ (DefaultValue) de drapeaux de sauvegarde, et ajoute
        des expressions booléennes (bool_exps : {nom: programme postfixe})."""
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
                      questions: list[str] | None = None) -> list[str]:
        """Modifie des flux d'événements (Event/EventFlow/<flux>.bfevfl.zs).

        event_changes : {flux: {ancien nom: nouveau nom}} (ex. l'objet donné)
        event_skips   : {flux: [scènes]} étapes qui jouent ces scènes, à sauter
        start_items   : objets ajoutés à l'inventaire au début de l'introduction"""
        from .formats.evfl import add_actions, find_action, insert_flow, replace_strings, skip_event_steps

        report = []
        event_skips = event_skips or {}
        flows = {self.OCARINA_GUARD[0]} | set(event_changes) | set(event_skips) | ({self.START_FLOW} if start_items or start_warp or questions else set())             | ({self.MOAT_FLOW} if moat_gate else set()) | ({self.SCRUB_FLOW} if scrub_sales else set())
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
            count = 0
            if mapping:
                new, count = replace_strings(new, mapping)
                if count == 0:
                    raise KeyError(f"{flow} : aucune des chaînes {list(mapping)} n'est utilisée")
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
                new, scrub_report = self._scrub_sales(new, scrub_sales)
                report += scrub_report
            if flow == self.OCARINA_GUARD[0]:
                new, guard_report = self._guard_fairy_ocarina(new)
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
            if moat_gate and flow == self.MOAT_FLOW:
                new, moat_report = insert_flow(new, self.MOAT_ENTRY, self._moat_gate(new))
                report += moat_report
            rel = path.relative_to(self.romfs).as_posix()
            self.restbl.resize_like(rel[:-3], len(raw), len(new))
            dest = out_romfs / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.codec.compress(path.name, new))
            if mapping:
                report.append(f"{flow}: {mapping} ({count} références)")
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

    SCRUB_FLOW = "Enemy_Scrub_Business_Common"
    SCRUB_MSG_PREFIX = "OoTRR_Scrub_"
    # texte des Peste Mojo : la phrase du jeu pour le quart de cœur, dans la langue du fichier,
    # dont le nom en couleur est remplacé par le nom de l'objet (dans la même langue)
    SCRUB_TEMPLATE = "Enemy_Scrub_Business_Heart_01"
    SCRUB_TEXT = ("I've got ", " for you! It's ", " rupees", ". Wanna buy it?")  # secours si le modèle manque

    def _write_messages(self, scrub_items: list[str], out_romfs: Path, questions: list[str] = ()) -> list[str]:
        """Messages des Peste Mojo : un message par objet vendu, dans chaque langue, avec le nom
        de l'objet tel que le jeu l'écrit (ActorMsg/PouchContent.msbt) et le prix (SimpleShop_Price)."""
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
                name = texts[labels[f"{item}_Name"]] if f"{item}_Name" in labels else item.encode()
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
            key = "EventFlowMsg/Enemy_Event.msbt"
            sarc.files[key] = add_messages(sarc.files[key], new)
            data = sarc.to_bytes()
            rel = path.relative_to(self.romfs).as_posix()
            self.restbl.resize_like(rel[:-3], len(raw), len(data))
            dest = out_romfs / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.codec.compress(path.name, data))
            report.append(f"{rel}: {len(new)} messages de Peste Mojo")
        return report
    SCRUB_TALK = "Enemy_Scrub_Business_DekuStickPouch_01"  # script « sac de bâtons » commun aux Peste Mojo mélangées

    def _scrub_sales(self, flow: bytes, sales: dict[str, int]) -> tuple[bytes, list[str]]:
        """Peste Mojo : avant les comparaisons d'origine, une question par objet vendu
        (« l'objet à vendre est-il X ? » ; 0 = oui) qui mène à la vente unique de X à son prix."""
        from .formats.evfl import _flowchart_full, _q, _string_at, _header, EVENT_SIZE, find_query, insert_flow
        import struct as _st

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
        nodes = []
        items = sorted(sales)
        for k, item in enumerate(items):
            nodes.append({"actor": "GameDataActor", "query": "EventQueryIsGameDataString64", "template": ask,
                          "set": {"Value": item}, "cases": {0: 2 * k + 1, 1: 2 * k + 2 if k + 1 < len(items) else "old"}})
            nodes.append({"copy_event": sale, "next": None,
                          "set": {"ActorName": item, "Price": int(sales[item]),
                                  "SellerMessageId": f"EventFlowMsg/Enemy_Event:{self.SCRUB_MSG_PREFIX}{item}"}})
        return insert_flow(flow, None, nodes, before=compare)

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
        items = list(self.MOAT_ITEMS)
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
    POUCH_TEMPLATE = "Dm_Kokiri_0155"
    POUCH_ACTION = ("PouchSystemActor", "EventTriggerAddOrRemovePouchContent")
    PICKUP_BASE = "Obj_Heart_Container"
    SHOP_ONCE = "?Component/ActorGameDataSetting/NoRespawn.game__component__ActorGameDataSetting.bgyml"
    pickup_models = True  # l'objet ramassable prend le modèle 3D de l'objet donné
    pickup_pouch = True  # ... et ses paramètres d'inventaire (traitement spécial de l'ocarina, etc.)

    def _use_item_model(self, sarc, param_path: str, name: str, item: str, pouch_params: bool = True) -> bool:
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
        if read_byml(files[model]).get("ModelProjectName") == "Obj_Rupee":
            return False
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
            if self.pickup_models:
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
              bool_exps: dict[str, list] | None = None,
              start_warp: tuple[str, str] | None = None,
              scrub_sales: dict[str, int] | None = None,
              questions: list[str] | None = None) -> list[str]:
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
                    if key in ("Presence", "Rotate", "Translate"):  # champs de l'acteur lui-même
                        actor[key] = type(actor.get(key, value))(value) if key != "Presence" else dict(value)
                        report.append(f"{path.parent.name}/{path.name}: {actor['Hash']} {key}: {value}")
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
        if start_flags or bool_exps:
            report += self._write_gamedata(start_flags or {}, out_romfs, bool_exps)
        if event_changes or event_skips or start_items or moat_gate or start_warp or scrub_sales or questions:
            report += self._write_events(event_changes or {}, out_romfs, event_skips, start_items, moat_gate,
                                         start_warp, scrub_sales, questions)
        if logic_patches:
            report += self._write_logic(logic_patches, out_romfs)
        if scrub_sales or questions:
            report += self._write_messages(sorted(scrub_sales or {}), out_romfs, questions or [])
        if pack_changes:
            report += self._write_packs(pack_changes, out_romfs)
        rsdb_all: dict[str, dict[str, dict]] = {t: dict(rows) for t, rows in (rsdb_changes or {}).items()}
        if pickups:
            for table, rows in self._write_pickups(pickups, out_romfs).items():
                rsdb_all.setdefault(table, {}).update(rows)
            report.append(f"{len(pickups)} objets ramassables créés : {pickups}")
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
        raise SystemExit(f"Erreur : fichiers du mod {name} verrouillés. Ferme Eden (ou le jeu) puis relance la commande.")
    return target
