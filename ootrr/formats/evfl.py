"""Fichiers d'événements BFEVFL : remplacement de chaînes (ex. l'objet donné).

Structure utile :
  0x18 u32  offset de la table de relocation RELT     0x1C u32  taille du fichier
  Chaînes : u16 longueur + texte + \\0 ; les paramètres pointent dessus avec un
  offset 64 bits (vers le champ longueur).
  RELT : liste de tous les emplacements de pointeurs du fichier (bitmaps de 32
  pointeurs consécutifs), et une section qui couvre tout le fichier jusqu'à RELT.

Pour remplacer une chaîne sans décaler le reste du fichier, on ajoute la
nouvelle chaîne juste avant RELT, on redirige les pointeurs vers elle, puis on
recopie RELT plus loin en corrigeant l'entête.
"""

from __future__ import annotations

import struct


def _header(d: bytes) -> tuple[int, int]:
    if d[:6] != b"BFEVFL":
        raise ValueError("pas un fichier BFEVFL")
    return struct.unpack_from("<II", d, 0x18)


def pointer_slots(d: bytes) -> list[int]:
    """Emplacements de tous les pointeurs du fichier, d'après RELT."""
    reloc, _ = _header(d)
    magic, _self, nsec = struct.unpack_from("<4sII", d, reloc)
    if magic != b"RELT":
        raise ValueError("table RELT introuvable")
    sections = [struct.unpack_from("<QIIII", d, reloc + 16 + 24 * i) for i in range(nsec)]
    entries_at = reloc + 16 + 24 * nsec
    slots = []
    for _ptr, base, _size, idx, cnt in sections:
        for e in range(idx, idx + cnt):
            off, bits = struct.unpack_from("<II", d, entries_at + 8 * e)
            for i in range(32):
                if bits >> i & 1:
                    slots.append(base + off + 8 * i)
    return slots


def _string_at(d: bytes, t: int, limit: int) -> str | None:
    if t + 2 > limit:
        return None
    n = struct.unpack_from("<H", d, t)[0]
    end = t + 2 + n
    if end >= limit or d[end] != 0:
        return None
    try:
        return d[t + 2:end].decode("utf-8")
    except UnicodeDecodeError:
        return None


def string_refs(d: bytes) -> dict[str, list[int]]:
    """{chaîne: [emplacements de pointeurs qui la désignent]}"""
    reloc, _ = _header(d)
    refs: dict[str, list[int]] = {}
    for slot in pointer_slots(d):
        t = struct.unpack_from("<Q", d, slot)[0]
        if 0 < t < reloc:
            s = _string_at(d, t, reloc)
            if s is not None:
                refs.setdefault(s, []).append(slot)
    return refs


EVENT_SIZE = 0x30
ENTRY_SIZE = 0x20
EV_ACTION, EV_SWITCH, EV_FORK, EV_JOIN, EV_SUBFLOW = 0, 1, 2, 3, 4
NO_EVENT = 0xFFFF


def _flowchart(d: bytes) -> dict:
    """Champs utiles du flowchart (bloc EVFL pointé par l'entête)."""
    off = d.find(b"EVFL", 0x20)
    if off < 0:
        raise ValueError("bloc EVFL introuvable")
    n_actors, n_actions, n_queries, n_events, n_entries = struct.unpack_from("<5H", d, off + 0x10)
    events, entry_dic, entries = struct.unpack_from("<QQQ", d, off + 0x30)
    return {"events": events, "n_events": n_events, "entries": entries, "n_entries": n_entries}


def skip_event_steps(d: bytes, scene_names: list[str]) -> tuple[bytes, list[str]]:
    """Fait sauter les étapes « action » dont les paramètres citent une de ces scènes
    (« #N » : l'étape numéro N, ex. un mouvement de caméra sans nom).

    Tout ce qui menait à l'étape (point d'entrée, étape précédente, cas d'une
    condition, branche d'un fork) mène désormais à l'étape suivante. La structure
    du fichier ne change pas : seuls des indices de 2 octets sont modifiés."""
    reloc, _ = _header(d)
    fc = _flowchart(d)
    out = bytearray(d)
    ev = [fc["events"] + i * EVENT_SIZE for i in range(fc["n_events"])]
    params = sorted((struct.unpack_from("<Q", d, o + 0x10)[0], i) for i, o in enumerate(ev)
                    if d[o + 8] == EV_ACTION and struct.unpack_from("<Q", d, o + 0x10)[0])
    report = []
    for scene in scene_names:
        targets = set()
        if scene.startswith("#"):
            targets.add(int(scene[1:]))
        for slot in pointer_slots(d) if not scene.startswith("#") else []:
            t = struct.unpack_from("<Q", d, slot)[0]
            if 0 < t < reloc and _string_at(d, t, reloc) == scene:
                owner = None
                for start, i in params:
                    if start <= slot:
                        owner = i
                if owner is not None:
                    targets.add(owner)
        # appel d'une sous-séquence portant ce nom (ex. le tutoriel d'un autre PNJ)
        for i, o in enumerate(ev):
            if d[o + 8] == EV_SUBFLOW and _string_at(d, struct.unpack_from("<Q", d, o + 0x20)[0], reloc) == scene:
                targets.add(i)
        for idx in sorted(targets):
            nxt = struct.unpack_from("<H", out, ev[idx] + 0x0A)[0]
            redirected = 0
            # points d'entrée
            for e in range(fc["n_entries"]):
                at = fc["entries"] + e * ENTRY_SIZE + 0x1C
                if struct.unpack_from("<H", out, at)[0] == idx:
                    struct.pack_into("<H", out, at, nxt)
                    redirected += 1
            for j, o in enumerate(ev):
                t = out[o + 8]
                if t in (EV_ACTION, EV_JOIN, EV_SUBFLOW) and struct.unpack_from("<H", out, o + 0x0A)[0] == idx:
                    struct.pack_into("<H", out, o + 0x0A, nxt)
                    redirected += 1
                elif t == EV_SWITCH:
                    n = struct.unpack_from("<H", out, o + 0x0A)[0]
                    cases = struct.unpack_from("<Q", out, o + 0x18)[0]
                    for c in range(n):
                        at = cases + 8 * c + 4
                        if struct.unpack_from("<H", out, at)[0] == idx:
                            struct.pack_into("<H", out, at, nxt)
                            redirected += 1
                elif t == EV_FORK:
                    n = struct.unpack_from("<H", out, o + 0x0A)[0]
                    forks = struct.unpack_from("<Q", out, o + 0x10)[0]
                    for c in range(n):
                        if struct.unpack_from("<H", out, forks + 2 * c)[0] == idx:
                            struct.pack_into("<H", out, forks + 2 * c, nxt)
                            redirected += 1
            report.append(f"{scene} : étape {idx} sautée -> {nxt if nxt != NO_EVENT else 'fin'} ({redirected} renvois)")
    return bytes(out), report


ACTOR_SIZE = 0x38


def _q(d, o: int) -> int:
    return struct.unpack_from("<Q", d, o)[0]


def _dic_names(d: bytes, p: int) -> list[str]:
    """Noms d'un dictionnaire « DIC » (dans l'ordre des éléments, sans la racine)."""
    n = struct.unpack_from("<I", d, p + 4)[0]
    reloc, _ = _header(d)
    return [_string_at(d, _q(d, p + 8 + 16 * i + 8), reloc) for i in range(1, n + 1)]


def build_relt(body: bytes, slots) -> bytes:
    """Fichier complet = body + nouvelle table RELT décrivant ces emplacements de pointeurs."""
    slots = sorted(set(slots))
    entries = []
    i = 0
    while i < len(slots):
        base, bits = slots[i], 0
        while i < len(slots) and slots[i] < base + 256 and (slots[i] - base) % 8 == 0:
            bits |= 1 << ((slots[i] - base) // 8)
            i += 1
        entries.append((base, bits))
    out = bytearray(body)
    while len(out) % 8:
        out.append(0)
    reloc = len(out)
    out += struct.pack("<4sIII", b"RELT", reloc, 1, 0)
    out += struct.pack("<QIIII", 0, 0, reloc, 0, len(entries))
    for base, bits in entries:
        out += struct.pack("<II", base, bits)
    struct.pack_into("<II", out, 0x18, reloc, len(out))
    return bytes(out)


def _flowchart_full(d: bytes) -> dict:
    fc = _q(d, _q(d, 0x28))
    na, nact, nq, ne, nep = struct.unpack_from("<5H", d, fc + 0x10)
    return {"fc": fc, "n_actors": na, "n_actions": nact, "n_events": ne, "n_entries": nep,
            "actors": _q(d, fc + 0x28), "events": _q(d, fc + 0x30),
            "entry_dic": _q(d, fc + 0x38), "entries": _q(d, fc + 0x40)}


def find_action(d: bytes, actor: str, action: str) -> int | None:
    """Adresse du conteneur de paramètres du premier événement « acteur.action »."""
    reloc, _ = _header(d)
    fc = _flowchart_full(d)
    for i in range(fc["n_events"]):
        o = fc["events"] + i * EVENT_SIZE
        if d[o + 8] != EV_ACTION:
            continue
        ai, aai = struct.unpack_from("<HH", d, o + 0x0C)
        a = fc["actors"] + ai * ACTOR_SIZE
        if _string_at(d, _q(d, a), reloc) == actor and \
                _string_at(d, _q(d, _q(d, a + 0x18) + 8 * aai), reloc) == action:
            return _q(d, o + 0x10)
    return None


def find_query(d: bytes, actor: str, query: str) -> int | None:
    """Adresse du conteneur de paramètres de la première condition « acteur.question »."""
    reloc, _ = _header(d)
    fc = _flowchart_full(d)
    for i in range(fc["n_events"]):
        o = fc["events"] + i * EVENT_SIZE
        if d[o + 8] != EV_SWITCH:
            continue
        ai, qi = struct.unpack_from("<HH", d, o + 0x0C)
        a = fc["actors"] + ai * ACTOR_SIZE
        if _string_at(d, _q(d, a), reloc) == actor and \
                _string_at(d, _q(d, _q(d, a + 0x20) + 8 * qi), reloc) == query:
            return _q(d, o + 0x10)
    return None


def _actor_slot(d: bytes, fc: dict, actor: str, name: str, kind: str) -> tuple[int, int]:
    """(indice de l'acteur, indice de l'action ou de la question) parmi les acteurs du fichier."""
    reloc, _ = _header(d)
    lst, cnt = (0x18, 0) if kind == "action" else (0x20, 1)
    for ai in range(fc["n_actors"]):
        a = fc["actors"] + ai * ACTOR_SIZE
        if _string_at(d, _q(d, a), reloc) != actor:
            continue
        n = struct.unpack_from("<HH", d, a + 0x30)[cnt]
        for k in range(n):
            if _string_at(d, _q(d, _q(d, a + lst) + 8 * k), reloc) == name:
                return ai, k
    raise KeyError(f"{actor}.{name} ({kind}) absent du fichier")


def ensure_actor_member(d: bytes, actor: str, kind: str, name: str) -> bytes:
    """Garantit que l'acteur « actor » (sans nom secondaire) possède l'action ou la question
    « name » (kind = "action" ou "query") ; ajoute l'acteur s'il manque.

    Le tableau des acteurs est recopié en fin de fichier ; les indices existants ne changent pas."""
    reloc, _ = _header(d)
    fc = _flowchart_full(d)
    lst, cnt_off, hdr_off = (0x18, 0x30, 0x12) if kind == "action" else (0x20, 0x32, 0x14)
    found = None
    for ai in range(fc["n_actors"]):
        a = fc["actors"] + ai * ACTOR_SIZE
        if _string_at(d, _q(d, a), reloc) == actor and not _string_at(d, _q(d, a + 8), reloc):
            n = struct.unpack_from("<H", d, a + cnt_off)[0]
            if name in [_string_at(d, _q(d, _q(d, a + lst) + 8 * k), reloc) for k in range(n)]:
                return d
            found = ai
            break
    old_slots = pointer_slots(d)
    body = bytearray(d[:reloc])
    slots = list(old_slots)
    existing = {s: _q(d, refs[0]) for s, refs in string_refs(d).items()}
    pending: list[tuple[int, str]] = []

    def align(n=8):
        while len(body) % n:
            body.append(0)

    align()
    actors = len(body)
    body.extend(d[fc["actors"]:fc["actors"] + fc["n_actors"] * ACTOR_SIZE])
    for s in old_slots:
        if fc["actors"] <= s < fc["actors"] + fc["n_actors"] * ACTOR_SIZE:
            slots.append(s - fc["actors"] + actors)
    n_actors = fc["n_actors"]
    if found is None:
        found = n_actors
        a_new = len(body)
        body.extend(b"\0" * ACTOR_SIZE)
        ref = fc["actors"]
        pending.append((a_new, actor))
        for k in (0x08, 0x10, 0x28):  # nom secondaire et argument vides, paramètres d'acteur génériques
            struct.pack_into("<Q", body, a_new + k, _q(d, ref + k))
            slots.append(a_new + k)
        struct.pack_into("<HHHBB", body, a_new + 0x30, 0, 0, NO_EVENT, 1, 0)
        n_actors += 1
        old_arr, n = 0, 0
    else:
        a_old = fc["actors"] + found * ACTOR_SIZE
        old_arr, n = _q(d, a_old + lst), struct.unpack_from("<H", d, a_old + cnt_off)[0]
    a = actors + found * ACTOR_SIZE
    align()
    arr = len(body)
    body.extend((d[old_arr:old_arr + 8 * n] if n else b"") + b"\0" * 8)
    for k in range(n):
        slots.append(arr + 8 * k)
    pending.append((arr + 8 * n, name))
    struct.pack_into("<Q", body, a + lst, arr)
    slots.append(a + lst)
    struct.pack_into("<H", body, a + cnt_off, n + 1)
    for at, text in pending:
        if text not in existing:
            align(2)
            existing[text] = len(body)
            raw = text.encode("utf-8")
            body.extend(struct.pack("<H", len(raw)) + raw + b"\0")
        struct.pack_into("<Q", body, at, existing[text])
        slots.append(at)
    f = fc["fc"]
    struct.pack_into("<H", body, f + 0x10, n_actors)
    total = struct.unpack_from("<H", d, f + hdr_off)[0]
    struct.pack_into("<H", body, f + hdr_off, total + 1)
    struct.pack_into("<Q", body, f + 0x28, actors)
    return build_relt(body, slots)


def find_action_event(d: bytes, actor: str, action: str, param: str, value: str) -> int | None:
    """Indice du premier événement « acteur.action » dont le paramètre texte vaut value."""
    reloc, _ = _header(d)
    fc = _flowchart_full(d)
    for i in range(fc["n_events"]):
        o = fc["events"] + i * EVENT_SIZE
        if d[o + 8] != EV_ACTION:
            continue
        ai, aai = struct.unpack_from("<HH", d, o + 0x0C)
        a = fc["actors"] + ai * ACTOR_SIZE
        if _string_at(d, _q(d, a), reloc) != actor or \
                _string_at(d, _q(d, _q(d, a + 0x18) + 8 * aai), reloc) != action:
            continue
        p = _q(d, o + 0x10)
        names = _dic_names(d, _q(d, p + 8))
        if param in names:
            child = _q(d, p + 0x10 + 8 * names.index(param))
            if d[child] == 5 and _string_at(d, _q(d, child + 0x10), reloc) == value:
                return i
    return None


def insert_flow(d: bytes, entry: str | None, nodes: list[dict], before: int | None = None) -> tuple[bytes, list[str]]:
    """Ajoute au début du point d'entrée « entry » un petit graphe d'étapes.

    Réponses des questions du jeu : 0 = oui, 1 = non (ex. Enemy_Scrub_Business_Common :
    « possède le sac de bâtons moyen ? » -> 0 = vend le grand sac).
    nodes[i] : {"actor", "action" ou "query", "template": (fichier, adresse des paramètres),
                "set": {paramètre: chaîne}, "next": cible (action) ou "cases": {valeur: cible}}
    Une cible est l'indice d'un autre nœud, « old » (l'ancien début du point d'entrée)
    ou None (fin). Les acteurs, actions et questions doivent déjà exister dans le fichier.

    Avec before=indice d'un événement, le graphe est inséré juste avant cet événement
    (tout ce qui y menait mène au graphe) : « old » = cet événement, « after » = l'étape
    qui le suit (pour le sauter)."""
    reloc, _ = _header(d)
    fc = _flowchart_full(d)
    first = fc["n_events"]
    if before is None:
        names = _dic_names(d, fc["entry_dic"])
        if entry not in names:
            raise KeyError(f"point d'entrée introuvable : {entry} (connus : {names})")
        entry_at = fc["entries"] + names.index(entry) * ENTRY_SIZE
        old_main = struct.unpack_from("<H", d, entry_at + 0x1C)[0]
        after = NO_EVENT
    else:
        entry_at = None
        old_main = before
        after = struct.unpack_from("<H", d, fc["events"] + before * EVENT_SIZE + 0x0A)[0]

    def target(t) -> int:
        if t == "old":
            return old_main
        if t == "after":
            return after
        return NO_EVENT if t is None else first + t

    old_slots = pointer_slots(d)
    body = bytearray(d[:reloc])
    slots = list(old_slots)
    pending: list[tuple[int, str]] = []
    existing = {s: _q(d, refs[0]) for s, refs in string_refs(d).items()}

    def align(n=8):
        while len(body) % n:
            body.append(0)

    def copy_params(template: bytes, tp: int, overrides: dict[str, str]) -> int:
        t_reloc, _ = _header(template)
        t_end = _container_end(template, tp)
        t_names = _dic_names(template, _q(template, tp + 8))
        align()
        base = len(body)
        body.extend(template[tp:t_end])
        mine: dict[int, str] = {}
        for s in pointer_slots(template):
            if not tp <= s < t_end:
                continue
            v, at = _q(template, s), s - tp + base
            if tp <= v < t_end:
                struct.pack_into("<Q", body, at, v - tp + base)
                slots.append(at)
            else:
                mine[at] = _string_at(template, v, t_reloc)
        for key, value in overrides.items():
            child = _q(template, tp + 0x10 + 8 * t_names.index(key))
            if isinstance(value, int) and not isinstance(value, bool):
                struct.pack_into("<i", body, child + 0x10 - tp + base, value)  # paramètre entier
            else:
                mine[child + 0x10 - tp + base] = value
        pending.extend(mine.items())
        return base

    # paramètres et tableaux de cas
    built = []
    for i, node in enumerate(nodes):
        if "copy_event" in node:
            src = fc["events"] + node["copy_event"] * EVENT_SIZE
            node["template"] = (d, _q(d, src + 0x10))
        params = copy_params(*node["template"], node.get("set", {})) if node["template"][1] else 0
        cases_at = None
        if "query" in node:
            # comme dans les scripts du jeu : un cas qui termine le script est omis
            # (jamais de saut vers 0xFFFF dans un tableau de cas)
            node["_cases"] = [(v, target(t)) for v, t in sorted(node["cases"].items()) if target(t) != NO_EVENT]
            align()
            cases_at = len(body)
            for value, t in node["_cases"]:
                body.extend(struct.pack("<IHH", value, t, 0))
        built.append((params, cases_at))

    events = len(body)
    body.extend(d[fc["events"]:fc["events"] + fc["n_events"] * EVENT_SIZE])
    for s in old_slots:
        if fc["events"] <= s < fc["events"] + fc["n_events"] * EVENT_SIZE:
            slots.append(s - fc["events"] + events)
    report = []
    for i, (node, (params, cases_at)) in enumerate(zip(nodes, built)):
        o = len(body)
        body.extend(b"\0" * EVENT_SIZE)
        pending.append((o, f"OoTRR_{entry}_{i}"))
        if "copy_event" in node:
            src = fc["events"] + node["copy_event"] * EVENT_SIZE
            body[o:o + EVENT_SIZE] = d[src:src + EVENT_SIZE]
            for s in old_slots:  # pointeurs propres à l'événement (nom, sous-séquence…), sauf ses paramètres
                if src <= s < src + EVENT_SIZE and s != src + 0x10:
                    slots.append(s - src + o)
            pending = [(a, t) for a, t in pending if a != o]
            pending.append((o, f"OoTRR_{entry}_{i}"))
            struct.pack_into("<H", body, o + 0x0A, target(node.get("next")))
            struct.pack_into("<Q", body, o + 0x10, params)
            slots.append(o + 0x10)
            report.append(f"{entry or before} : copie de l'étape {node['copy_event']} {node.get('set', {})}")
        elif "query" in node:
            ai, qi = _actor_slot(d, fc, node["actor"], node["query"], "query")
            struct.pack_into("<BBHHH", body, o + 8, EV_SWITCH, 0, len(node["_cases"]), ai, qi)
            struct.pack_into("<QQ", body, o + 0x10, params, cases_at)
            slots += ([o + 0x10] if params else []) + [o + 0x18]
            report.append(f"{entry} : si {node['actor']}.{node['query']} {node.get('set', {})}")
        else:
            ai, k = _actor_slot(d, fc, node["actor"], node["action"], "action")
            struct.pack_into("<BBHHH", body, o + 8, EV_ACTION, 0, target(node.get("next")), ai, k)
            struct.pack_into("<Q", body, o + 0x10, params)
            slots.append(o + 0x10)
            report.append(f"{entry} : {node['actor']}.{node['action']} {node.get('set', {})}")

    for at, text in pending:
        if text not in existing:
            align(2)
            existing[text] = len(body)
            raw = text.encode("utf-8")
            body.extend(struct.pack("<H", len(raw)) + raw + b"\0")
        struct.pack_into("<Q", body, at, existing[text])
        slots.append(at)

    f = fc["fc"]
    struct.pack_into("<H", body, f + 0x16, fc["n_events"] + len(nodes))
    struct.pack_into("<Q", body, f + 0x30, events)
    if entry_at is not None:
        struct.pack_into("<H", body, entry_at + 0x1C, first)
    else:
        # tout ce qui menait à l'événement « before » mène maintenant au premier nœud
        for e in range(fc["n_entries"]):
            at = fc["entries"] + e * ENTRY_SIZE + 0x1C
            if struct.unpack_from("<H", body, at)[0] == before:
                struct.pack_into("<H", body, at, first)
        for j in range(fc["n_events"]):
            o = events + j * EVENT_SIZE
            t = body[o + 8]
            if t in (EV_ACTION, EV_JOIN, EV_SUBFLOW) and struct.unpack_from("<H", body, o + 0x0A)[0] == before:
                struct.pack_into("<H", body, o + 0x0A, first)
            elif t == EV_SWITCH:
                n = struct.unpack_from("<H", body, o + 0x0A)[0]
                cases = _q(body, o + 0x18)
                for c in range(n):
                    if struct.unpack_from("<H", body, cases + 8 * c + 4)[0] == before:
                        struct.pack_into("<H", body, cases + 8 * c + 4, first)
            elif t == EV_FORK:
                n = struct.unpack_from("<H", body, o + 0x0A)[0]
                forks = _q(body, o + 0x10)
                for c in range(n):
                    if struct.unpack_from("<H", body, forks + 2 * c)[0] == before:
                        struct.pack_into("<H", body, forks + 2 * c, first)
    return build_relt(body, slots), report


def _container_end(d: bytes, p: int) -> int:
    """Fin d'un conteneur de paramètres simple (dictionnaire de valeurs scalaires)."""
    n = struct.unpack_from("<H", d, p + 2)[0]
    end = _q(d, p + 8) + 8 + 16 * (n + 1)
    for i in range(n):
        child = _q(d, p + 0x10 + 8 * i)
        kind, count = d[child], struct.unpack_from("<H", d, child + 2)[0]
        if kind in (2, 3, 4, 5):
            size = 0x18
        elif kind in (10, 11, 12):  # tableaux de textes, identifiant d'acteur : pointeurs
            size = 0x10 + 8 * count
        elif kind in (7, 8, 9):  # tableaux d'entiers, de booléens, de flottants
            size = (0x10 + 4 * count + 7) // 8 * 8
        else:
            raise ValueError(f"conteneur modèle non pris en charge (type {kind})")
        end = max(end, child + size)
    return end


def add_actions(d: bytes, entry: str, actor: str, action: str, template: bytes, template_params: int,
                values: list[dict[str, str]]) -> tuple[bytes, list[str]]:
    """Ajoute au début du point d'entrée « entry » une suite d'actions « acteur.action ».

    Les paramètres de chaque action sont une copie de ceux de template_params (dans
    le fichier template), dont on remplace les chaînes indiquées par values[i]
    (ex. {"Actor": "Item_ZeldaLetter"}). Les tableaux d'acteurs et d'événements sont
    recopiés en fin de fichier avec les éléments ajoutés ; le reste ne bouge pas."""
    reloc, _ = _header(d)
    fc = _flowchart_full(d)
    names = _dic_names(d, fc["entry_dic"])
    if entry not in names:
        raise KeyError(f"point d'entrée introuvable : {entry} (connus : {names})")
    entry_at = fc["entries"] + names.index(entry) * ENTRY_SIZE

    old_slots = pointer_slots(d)
    body = bytearray(d[:reloc])
    slots = list(old_slots)
    pending: list[tuple[int, str]] = []  # (emplacement, chaîne à créer)
    existing = {s: _q(d, refs[0]) for s, refs in string_refs(d).items()}

    def align(n=8):
        while len(body) % n:
            body.append(0)

    def copy_array(start: int, count: int, size: int) -> int:
        align()
        new = len(body)
        body.extend(d[start:start + count * size])
        for s in old_slots:
            if start <= s < start + count * size:
                slots.append(s - start + new)
        return new

    # 1. acteurs : copie, puis l'acteur existant reçoit l'action, ou un nouvel acteur est ajouté
    existing_actor = None
    for ai in range(fc["n_actors"]):
        a = fc["actors"] + ai * ACTOR_SIZE
        if _string_at(d, _q(d, a), reloc) == actor and not _string_at(d, _q(d, a + 8), reloc):
            existing_actor = ai
            break
    new_actors = 0 if existing_actor is not None else 1
    actors = copy_array(fc["actors"], fc["n_actors"], ACTOR_SIZE)
    if existing_actor is not None:
        actor_idx = existing_actor
        a_old = fc["actors"] + actor_idx * ACTOR_SIZE
        a_new = actors + actor_idx * ACTOR_SIZE
        n_act = struct.unpack_from("<H", d, a_old + 0x30)[0]
        names_old = [_string_at(d, _q(d, _q(d, a_old + 0x18) + 8 * k), reloc) for k in range(n_act)]
        if action in names_old:
            action_idx, added_actions = names_old.index(action), 0
        else:
            align()
            arr = len(body)
            body.extend(d[_q(d, a_old + 0x18):_q(d, a_old + 0x18) + 8 * n_act] + b"\0" * 8)
            for k in range(n_act):
                slots.append(arr + 8 * k)
            pending.append((arr + 8 * n_act, action))
            struct.pack_into("<Q", body, a_new + 0x18, arr)
            struct.pack_into("<H", body, a_new + 0x30, n_act + 1)
            action_idx, added_actions = n_act, 1
    else:
        actor_idx, action_idx, added_actions = fc["n_actors"], 0, 1
        ref = fc["actors"]  # acteur modèle : réutilise ses chaînes vides et ses paramètres d'acteur
        new_actor = len(body)
        body.extend(b"\0" * ACTOR_SIZE)
        pending.append((new_actor, actor))
        for k in (0x08, 0x10, 0x28):  # nom secondaire, argument (vides), paramètres d'acteur
            struct.pack_into("<Q", body, new_actor + k, _q(d, ref + k))
            slots.append(new_actor + k)
        struct.pack_into("<HHHBB", body, new_actor + 0x30, 1, 0, NO_EVENT, 1, 0)
        actions_arr = len(body)
        body.extend(b"\0" * 8)
        pending.append((actions_arr, action))
        struct.pack_into("<Q", body, new_actor + 0x18, actions_arr)
        slots.append(new_actor + 0x18)

    # 2. paramètres de chaque nouvelle action : copie du conteneur modèle
    t_reloc, _ = _header(template)
    t_end = _container_end(template, template_params)
    t_slots = [s for s in pointer_slots(template) if template_params <= s < t_end]
    t_names = _dic_names(template, _q(template, template_params + 8))
    params_at = []
    for value in values:
        align()
        base = len(body)
        body.extend(template[template_params:t_end])
        for s in t_slots:
            v = _q(template, s)
            at = s - template_params + base
            if template_params <= v < t_end:
                struct.pack_into("<Q", body, at, v - template_params + base)
                slots.append(at)
            else:
                pending.append((at, _string_at(template, v, t_reloc)))
        for key, text in value.items():
            child = _q(template, template_params + 0x10 + 8 * t_names.index(key))
            at = child + 0x10 - template_params + base
            pending = [(a, s) for a, s in pending if a != at] + [(at, text)]
        params_at.append(base)

    # 3. événements : copie + nouvelles actions enchaînées avant l'ancien début
    first = fc["n_events"]
    old_main = struct.unpack_from("<H", d, entry_at + 0x1C)[0]
    events = copy_array(fc["events"], fc["n_events"], EVENT_SIZE)
    report = []
    for i, base in enumerate(params_at):
        o = len(body)
        body.extend(b"\0" * EVENT_SIZE)
        pending.append((o, f"OoTRR_{action}_{i}"))
        nxt = first + i + 1 if i + 1 < len(params_at) else old_main
        struct.pack_into("<BBHHH", body, o + 8, EV_ACTION, 0, nxt, actor_idx, action_idx)
        struct.pack_into("<Q", body, o + 0x10, base)
        slots.append(o + 0x10)
        report.append(f"{entry} : {actor}.{action} {values[i]}")

    # 4. chaînes : réutilise celles du fichier, sinon les ajoute
    for at, text in pending:
        if text not in existing:
            align(2)
            existing[text] = len(body)
            raw = text.encode("utf-8")
            body.extend(struct.pack("<H", len(raw)) + raw + b"\0")
        struct.pack_into("<Q", body, at, existing[text])
        slots.append(at)

    # 5. entête du flowchart et point d'entrée
    f = fc["fc"]
    struct.pack_into("<H", body, f + 0x10, fc["n_actors"] + new_actors)
    struct.pack_into("<H", body, f + 0x12, fc["n_actions"] + added_actions)
    struct.pack_into("<H", body, f + 0x16, fc["n_events"] + len(params_at))
    struct.pack_into("<QQ", body, f + 0x28, actors, events)
    struct.pack_into("<H", body, entry_at + 0x1C, first)
    return build_relt(body, slots), report


def replace_strings(d: bytes, mapping: dict[str, str]) -> tuple[bytes, int]:
    """Remplace chaque chaîne de mapping partout où un pointeur la désigne.

    Retourne (nouveau fichier, nombre de pointeurs redirigés)."""
    refs = string_refs(d)
    return _redirect_slots(d, [(mapping[old], slots) for old, slots in refs.items() if old in mapping])


def event_param_slot(d: bytes, event: int, param: str) -> tuple[int, str | None] | None:
    """(emplacement du pointeur, texte actuel) du paramètre texte `param` de l'événement n° `event`
    (action, condition ou sous-séquence) ; None s'il n'existe pas ou n'est pas un texte."""
    reloc, _ = _header(d)
    fc = _flowchart_full(d)
    if not 0 <= event < fc["n_events"]:
        return None
    o = fc["events"] + event * EVENT_SIZE
    if d[o + 8] not in (EV_ACTION, EV_SWITCH, EV_SUBFLOW):
        return None
    p = _q(d, o + 0x10)
    if not p:
        return None
    n = struct.unpack_from("<H", d, p + 2)[0]
    names = _dic_names(d, _q(d, p + 8))
    for i in range(n):
        if names[i] != param:
            continue
        pv = _q(d, p + 0x10 + 8 * i)
        if d[pv] != 5:  # 5 = texte
            return None
        slot = pv + 0x10
        return slot, _string_at(d, _q(d, slot), reloc)
    return None


def replace_event_strings(d: bytes, edits: list[tuple[int, str, str, str]]) -> tuple[bytes, list[str]]:
    """Modifie des paramètres texte d'événements précis : [(événement, paramètre, texte attendu, nouveau texte)].

    Contrairement à replace_strings, une chaîne partagée par d'autres événements (comme l'objet testé par une
    condition) reste intacte. Un événement dont le texte actuel diffère de celui attendu est ignoré et
    signalé dans le rapport (autre version du jeu)."""
    groups: list[tuple[str, list[int]]] = []
    report = []
    for event, param, old, new in edits:
        found = event_param_slot(d, event, param)
        if found is None or found[1] != old:
            report.append(f"événement {event} : {param} = {found[1] if found else None!r}, attendu {old!r}")
            continue
        groups.append((new, [found[0]]))
    out, _ = _redirect_slots(d, groups)
    return out, report


def _redirect_slots(d: bytes, groups: list[tuple[str, list[int]]]) -> tuple[bytes, int]:
    """Écrit chaque nouvelle chaîne en fin de données et redirige les pointeurs `slots` vers elle."""
    reloc, size = _header(d)
    if not groups:
        return d, 0
    body = bytearray(d[:reloc])
    relt = bytearray(d[reloc:size])
    count = 0
    offsets: dict[str, int] = {}
    for new, slots in groups:
        if new not in offsets:
            if len(body) % 2:
                body.append(0)
            offsets[new] = len(body)
            raw = new.encode("utf-8")
            body += struct.pack("<H", len(raw)) + raw + b"\0"
    while len(body) % 8:
        body.append(0)
    for new, slots in groups:
        for slot in slots:
            struct.pack_into("<Q", body, slot, offsets[new])
            count += 1

    new_reloc = len(body)
    struct.pack_into("<I", relt, 4, new_reloc)  # auto-référence de RELT
    nsec = struct.unpack_from("<I", relt, 8)[0]
    old_cover = reloc  # la section couvrait [0, reloc - 4] dans l'original
    for i in range(nsec):
        base, sec_size = struct.unpack_from("<II", relt, 16 + 24 * i + 8)
        if base + sec_size >= old_cover - 8:
            struct.pack_into("<I", relt, 16 + 24 * i + 12, sec_size + (new_reloc - reloc))
    out = body + relt
    struct.pack_into("<II", out, 0x18, new_reloc, len(out))
    return bytes(out), count
