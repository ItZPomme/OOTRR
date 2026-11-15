"""Adding nodes to actor AI modules (AINB) with the `ainb` library.

Validated in game (Longshot, 2026-11-14) for `Player.action.walk.module` (fast Bunny Hood). What matters:
- every edited file INSIDE a pack has its own RESTBL entry (the game's margin is only ~0x190 bytes over the file
  size): a bigger .ainb without a bigger entry overwrites memory (black screen, hood no longer equipped). See
  `inner_size_entry`.
- a file shared by several packs (the walk module is in Player_Child, Player_Adult and Player_Base) is edited in
  each of them.
- node templates are deep copies of nodes of other game files (any pack), changed in place; the GUID is new.
- an `Element_BoolSelector` with `CalculateTiming` 1 re-evaluates its input every frame.
- the AI of an armor actor (Armor_Child_Mask_Bunny) only runs for a moment when it is created: it cannot report a
  state every frame. The worn state is read on Link's side instead (GameData).
"""

from __future__ import annotations

import copy
import uuid
from pathlib import Path

from .formats.sarc import read_sarc

IMMEDIATE = 0x800000  # parameter flag: constant value (no source node)
INNER_MARGIN = 0x2000  # RESTBL margin over the size of an edited file inside a pack


def inner_size_entry(restbl, inner: str, new_size: int) -> None:
    restbl.set(inner, max(restbl.get(inner), new_size + INNER_MARGIN))


class Templates:
    """Nodes copied from the game's own AI files (looked up once)."""

    SOURCES = {
        "bool_selector": ("Obj_RedIce_A_02", "AI/Obj_RedIce_A_01.root.ainb", 28),
        "dummy": ("Obj_RedIce_A_02", "AI/Obj_RedIce_A_01.root.ainb", 38),
        "and": ("Obj_RedIce_A_02", "AI/Obj_RedIce_A_01.root.ainb", 21),
        "string_equal": ("Obj_RedIce_A_02", "AI/Obj_RedIce_A_01.root.ainb", "QueryStringIsEqual"),
        "get_bool_exp": ("Land_Goron_EmissionProp_Base", None, "QueryGetNonStructGameDataBoolExp"),
        "get_string64": ("Animal_Epona_Adult", None, "QueryGetNonStructGameDataString64"),
        "get_forward_speed": ("Enemy_BabyDodongo", None, "QueryPhysicsCctGetForwardSpeedMps"),
        "mul_f32": ("Obj_BlueFire_A_03", None, "QueryMathMulF32"),
        "set_forward_speed": ("Player_Child", None, "ExecutePhysicsCctSetForwardSpeedMps"),
    }

    def __init__(self, romfs: Path, codec) -> None:
        self.romfs = Path(romfs)
        self.codec = codec
        self._cache: dict[str, object] = {}

    def __getitem__(self, key: str):
        if key not in self._cache:
            import ainb

            actor, inner, which = self.SOURCES[key]
            files = read_sarc(self.codec.decompress(self.romfs / "Pack" / "Actor" / f"{actor}.pack.zs"))
            found = None
            for fn, data in files.items():
                if not fn.endswith(".ainb") or (inner and fn != inner):
                    continue
                if isinstance(which, str) and which.encode() not in data:
                    continue
                nodes = ainb.AINB.from_binary(data).nodes
                if isinstance(which, int):
                    found = nodes[which]
                else:
                    found = next((n for n in nodes if n.name == which), None)  # first one, as tested in game
                if found is not None:
                    break
            if found is None:
                raise KeyError(f"AINB template {key} not found in {actor}")
            if key == "bool_selector":
                for p in found.properties.int_properties:
                    if p.name == "CalculateTiming":
                        p.default_value = 1
            self._cache[key] = found
        return self._cache[key]


class Graph:
    def __init__(self, raw: bytes, templates: Templates) -> None:
        import ainb

        self.ainb = ainb
        self.s = ainb.AINB.from_binary(raw)
        self.nodes = self.s.nodes
        self.t = templates

    def to_binary(self) -> bytes:
        return self.s.to_binary()

    def root(self):
        return self.nodes[self.s.commands[0].root_node_index]

    def add(self, key: str):
        n = copy.deepcopy(self.t[key])
        n.index = len(self.nodes)
        n.guid = str(uuid.UUID(int=(0x4F6F5452 << 96) | (0x4000 << 48) | (0x8000 << 32) | (0x1000 + n.index)))
        n.queries = []
        self.nodes.append(n)
        return n

    @staticmethod
    def _link(param, node=None, value=None) -> None:
        """Feeds a parameter from a node output (index 0), or makes it a constant."""
        if node is not None:
            param.source.src_node_index, param.source.src_output_index = node.index, 0
            param.source.flags = type(param.source.flags)(0)
        else:
            param.default_value = value
            param.source.src_node_index, param.source.src_output_index = -1, 0
            param.source.flags = type(param.source.flags)(IMMEDIATE)

    def child(self, node):
        from ainb.node import ChildPlug

        plug = ChildPlug()
        plug.node_index = node.index
        plug.name = ""
        return plug

    def gamedata(self, key: str, name: str):
        q = self.add(key)
        for p in q.params.string_inputs:
            if p.name == "GameDataFullName":
                self._link(p, value=name)
        return q

    def string_equal(self, node, constant: str):
        eq = self.add("string_equal")
        a, b = sorted(eq.params.string_inputs, key=lambda p: p.name)
        self._link(a, node)
        self._link(b, value=constant)
        eq.queries = [node.index]
        return eq

    def logical_and(self, a, b):
        n = self.add("and")
        x, y = n.params.bool_inputs
        self._link(x, a)
        self._link(y, b)
        n.queries = [a.index, b.index]
        return n

    def selector(self, query, on_true, on_false):
        sel = self.add("bool_selector")
        sel.flags = type(sel.flags)(0)
        sel.queries = [query.index]
        self._link(sel.params.bool_inputs[0], query)
        for plug in sel.child_plugs:
            plug.node_index = on_true.index if plug.name == "True" else on_false.index
        return sel

    def scale_forward_speed(self, factor: float):
        """Forward speed = current forward speed x factor (follows the stick)."""
        get = self.add("get_forward_speed")
        mul = self.add("mul_f32")
        a, b = sorted(mul.params.float_inputs, key=lambda p: p.name)
        self._link(a, get)
        self._link(b, value=float(factor))
        b.source.flags = type(b.source.flags)(0)
        mul.queries = [get.index]
        out = self.add("set_forward_speed")
        self._link(out.params.float_inputs[0], mul)
        out.queries = [mul.index]
        return out


def fast_walk(raw: bytes, templates: Templates, bool_exp: str, head_flag: str, head_actor: str,
              factor: float) -> bytes:
    """Player.action.walk.module: while `bool_exp` is true AND the String64 `head_flag` equals `head_actor`, the
    forward speed is multiplied by `factor` (new child of the root Element_Simultaneous)."""
    g = Graph(raw, templates)
    root = g.root()
    if root.type != g.ainb.NodeType.Element_Simultaneous:
        raise ValueError("walk module: unexpected root node")
    worn = g.gamedata("get_bool_exp", bool_exp)
    head = g.string_equal(g.gamedata("get_string64", head_flag), head_actor)
    cond = g.logical_and(worn, head)
    root.child_plugs.append(g.child(g.selector(cond, g.scale_forward_speed(factor), g.add("dummy"))))
    return g.to_binary()
