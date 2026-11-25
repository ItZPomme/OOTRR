"""Adding nodes to actor AI modules (AINB) with the `ainb` library (fast Bunny Hood, Ice Arrows as Blue Fire), and
to logic modules (Logic/*.ainb: `set_flag_in_room`).

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


# logic module nodes copied by set_flag_in_room: {key: (module, node)}
LOGIC_SOURCES = {
    "bool_exp": ("DeathMountainTrail_Adult_Prefab_a3cd", 1, "HoldGameDataGetBoolExpSimple"),
    # sets DungeonInfo.WaterTemple.IsGetCompass: the same GameData struct as the boss keys
    "set_true": ("WaterTemple_Level_Room_03_Prefab_d37d", 14, "TriggerGameDataSetBoolTrue"),
}


def set_flag_in_room(raw: bytes, romfs: Path, bool_exp: str, flag: str) -> bytes:
    """Logic module of a dungeon room: the Bool `flag` becomes true when Link is in the room AND `bool_exp` is true.

    The module must hold a HoldDungeonRoomQueryIsInCurrentRoom node and an OperateAND that reads it (copied). New
    nodes: expression, AND(in room, expression), TriggerGameDataSetBoolTrue driven by the AND (its output True), so
    the trigger sees the AND become true when Link enters the room, as the module's own room clear does. A node
    with several sources has one plug, to the first of its queries (every OperateAND of the game's modules)."""
    import ainb

    script = ainb.AINB.from_binary(raw)
    room = next(n for n in script.nodes if n.name == "HoldDungeonRoomQueryIsInCurrentRoom")
    gate = next(n for n in script.nodes if n.name == "OperateAND" and room.index in n.queries and len(n.queries) == 2)

    def add(source):
        n = copy.deepcopy(source)
        n.index = len(script.nodes)
        n.guid = str(uuid.UUID(int=(0x4F6F5452 << 96) | (0x4000 << 48) | (0x8000 << 32) | (0x2000 + n.index)))
        script.nodes.append(n)
        return n

    def template(key):
        module, index, name = LOGIC_SOURCES[key]
        data = (Path(romfs) / "Logic" / f"{module}.logic.module.ainb").read_bytes()
        n = ainb.AINB.from_binary(data).nodes[index]
        if n.name != name:
            raise ValueError(f"{module}: node {index} is {n.name}, expected {name}")
        return n

    def text(node, name, value):
        next(p for p in node.params.string_inputs if p.name == name).default_value = value

    exp = add(template("bool_exp"))
    text(exp, "GameDataNameBoolExp", bool_exp)
    both = add(gate)
    sources = next(p for p in both.params.bool_inputs if p.name == "BoolMulti").source
    (in_room, other) = sorted(sources, key=lambda s: s.src_node_index != room.index)
    if in_room.src_node_index != room.index:
        raise ValueError("room module: the AND does not read the room")
    other.src_node_index, other.src_output_index = exp.index, 0
    both.queries = [room.index, exp.index]
    plug, = both.generic_plugs
    plug.node_index = room.index
    trigger = add(template("set_true"))
    text(trigger, "GameDataNameBool", flag)
    drive = next(p for p in trigger.params.bool_inputs if p.name == "IsDrive")
    true_output = [p.name for p in both.params.bool_outputs].index("True")
    drive.source.src_node_index, drive.source.src_output_index = both.index, true_output
    trigger.queries = [both.index]
    plug, = trigger.generic_plugs
    plug.node_index = both.index
    return script.to_binary()


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
        # blue_fire_arrows
        "simultaneous": ("Obj_RedIce_A_02", "AI/Obj_RedIce_A_01.root.ainb", 14),
        "or": ("Obj_RedIce_A_02", "AI/Obj_RedIce_A_01.root.ainb", "QueryLogicalDisjunction"),
        "get_int": ("Dm_Poe_Amy", None, "QueryGetNonStructGameDataInt"),
        "add_int": ("Land_Gerudo_HorsebackArcheryTarget_A_01", None, "OneShotAddNonStructGameDataInt"),
        "blackboard_s32": ("DungeonRoomArea", None, "QueryBlackboardGetS32NoError"),
        "equal_s32": ("Animal_Cow", None, "QueryMathEqualS32"),
        "less_s32": ("Animal_Cucco", None, "QueryMathLessS32"),
        "less_f32": ("Animal_Cow", None, "QueryMathLessF32"),
        "select_s32": ("Animal_Cucco", None, "QuerySelectS32ByBool"),
        "shootable_state": ("Octorok_Bullet", None, "QueryShootableGetState"),
        "camera": ("Dm_Npc_Base", None, "QueryCameraGetGameCameraWorldPosition"),
        "actor_position": ("Obj_BlueFire_A_03", None, "QueryActorGetPosition"),
        "add_vec": ("Animal_Cow", None, "QueryMathAddVector3f"),
        "sub_vec": ("Obj_BlueFire_A_03", None, "QueryMathSubVector3f"),
        "normalize": ("Obj_BlueFire_A_03", None, "QueryMathNormalizeVector"),
        "dot": ("Animal_Horse", None, "QueryMathDotVector"),
        "distance": ("Animal_Cucco", None, "QueryMathCalcVectorDistance"),
        # navi_return: Link's AI asks for an event by name (as the game does for the NaviTips_Gauntlet events)
        "request_event": ("Player_Adult", "AI/Player.action.grabpushpull.module.ainb",
                          "OneShotEventPerformerRequestEventByEventName"),
        "map_path": ("GameSystemActor", "AI/GameSystemActor.event.root.ainb", "QueryGetCurrentNormalizedBancName"),
        "file_name": ("GameSystemActor", "AI/GameSystemActor.event.root.ainb", "QueryGetFileName"),
        "add_f32": ("Obj_RedIce_A_02", "AI/Obj_RedIce_A_01.root.ainb", "QueryMathAddF32"),
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


def still_floor(raw: bytes, selector: int, support: int, message: int) -> bytes:
    """Falling floor AI that never starts to fall: the selector that waits for Link on the floor
    (QueryPhysicsIsSpreadSupportActive, node `support`) reads the "fall" message query (node `message`) instead.
    The messages are only sent by floors that start to fall, so it stays false: the floor stays as if untouched."""
    import ainb

    script = ainb.AINB.from_binary(raw)
    node = script.nodes[selector]
    names = (script.nodes[support].name, script.nodes[message].name)
    if (node.type != ainb.NodeType.Element_BoolSelector or node.queries != [support] or names !=
            ("QueryPhysicsIsSpreadSupportActive", "QueryInsideTheDekuFallingFloorReceiveFallMessage")):
        raise ValueError(f"{script.filename}: unexpected falling floor nodes ({names}, queries {node.queries})")
    source = node.params.bool_inputs[0].source
    plug, = node.generic_plugs
    if source.src_node_index != support or plug.node_index != support:
        raise ValueError(f"{script.filename}: unexpected input of node {selector}")
    source.src_node_index = plug.node_index = message
    node.queries = [message]
    return script.to_binary()


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


class Logic(Graph):
    """Helpers for AIs that keep running (blue_fire_arrows). Validated in game (Longshot, 2026-11-15): a selector
    added beside the original tree of such an AI is only evaluated on its first frame, so conditions are turned
    into numbers (QuerySelectS32ByBool) feeding ExecuteEveryFrame actions, or ORed into the AI's own selectors."""

    @staticmethod
    def _from(param, node, out: int = 0) -> None:
        param.source.src_node_index, param.source.src_output_index = node.index, out
        param.source.flags = type(param.source.flags)(0)

    @staticmethod
    def _const(param, value) -> None:
        param.default_value = value
        param.source.src_node_index, param.source.src_output_index = -1, 0
        param.source.flags = type(param.source.flags)(IMMEDIATE)

    @staticmethod
    def _param(node, kind: str, name: str):
        return next(p for p in getattr(node.params, f"{kind}_inputs") if p.name == name)

    def query(self, key: str, *sources):
        """New node; its OutputOnlyOnEnter property is cleared; `sources` are listed as its queries."""
        n = self.add(key)
        for p in n.properties.bool_properties:
            if p.name == "OutputOnlyOnEnter":
                p.default_value = False
        n.queries = [s.index for s in sources]
        return n

    def feed(self, node, kind: str, name: str, value, out: int = 0) -> None:
        """Input `name` from a node (its output `out`) or a constant."""
        param = self._param(node, kind, name)
        if hasattr(value, "params"):
            self._from(param, value, out)
            if value.index not in node.queries:
                node.queries.append(value.index)
        else:
            self._const(param, value)

    def group(self, *children):
        box = self.add("simultaneous")
        box.flags = type(box.flags)(0)
        box.child_plugs.clear()
        box.child_plugs.extend(self.child(c) for c in children)
        return box

    def int_data(self, key: str, name: str):
        """GameData Int node (get / add), every frame."""
        n = self.query(key)
        self._const(self._param(n, "string", "GameDataFullName"), name)
        for p in n.properties.bool_properties:
            if p.name == "ExecuteEveryFrame":
                p.default_value = True
        return n

    def add_by(self, name: str, query, if_true: int, out: int = 0):
        """Int `name` += if_true on every frame where `query` is true."""
        value = self.query("select_s32")
        self.feed(value, "bool", "Bool", query, out)
        self.feed(value, "int", "TrueValue", int(if_true))
        self.feed(value, "int", "FalseValue", 0)
        add = self.int_data("add_int", name)
        self.feed(add, "int", "Value", value)
        return add

    def compare(self, key: str, kind: str, a, b, a_out: int = 0, b_out: int = 0):
        """QueryMathLess* = (a < b): inputs (S32 / F32, S32Base / F32Base); also EqualS32."""
        n = self.query(key)
        first, base = ("S32", "S32Base") if kind == "int" else ("F32", "F32Base")
        self.feed(n, kind, first, a, a_out)
        self.feed(n, kind, base, b, b_out)
        return n

    def both(self, key: str, a, b, a_out: int = 0, b_out: int = 0):
        """QueryLogicalConjunction ("and") / QueryLogicalDisjunction ("or")."""
        n = self.query(key)
        x, y = n.params.bool_inputs
        self._from(x, a, a_out)
        self._from(y, b, b_out)
        n.queries = [a.index, b.index]
        return n

    def vec(self, key: str, a, b, a_out: int = 0, b_out: int = 0):
        """Two-vector node (add / sub / dot / distance): first two vec3f inputs, in order."""
        n = self.query(key)
        x, y = n.params.vec3f_inputs[:2]
        for param, value, out in ((x, a, a_out), (y, b, b_out)):
            if hasattr(value, "params"):
                self._from(param, value, out)
                n.queries.append(value.index)
            else:
                self._const(param, tuple(float(v) for v in value))
        return n

    def wrap_root(self, extra) -> None:
        """New root = Simultaneous[old root, extra]."""
        cmd = self.s.commands[0]
        old = self.nodes[cmd.root_node_index]
        root = self.group(old, extra)
        root.flags = type(old.flags)(int(old.flags))
        old.flags = type(old.flags)(0)
        cmd.root_node_index = root.index


def ice_arrow_ai(base: bytes, templates: Templates, filename: str, timer: str, value: int, ice_type: int) -> bytes:
    """AI for NormalArrow (it has none), built in the root file of another actor (`base`, whose own tree never runs).

    Validated in game (Longshot, 2026-11-15): the AI runs while the arrow is nocked and 2 frames after the shot
    (QueryShootableGetState > 1); the blackboard S32 ShootableArrow_ArrowType is 2 for an Ice Arrow. During those 2
    frames an Ice Arrow adds `value` to the saved Int `timer`; on the other frames the arrow takes 1 from it while it
    is > 0 (not validated in game: the tested version only added)."""
    g = Logic(base, templates)
    g.s.filename = filename
    old = g.nodes[g.s.commands[0].root_node_index]
    kind = g.query("blackboard_s32")
    for p in kind.properties.string_properties:
        if p.name == "BlackboardKey":
            p.default_value = "ShootableArrow_ArrowType"
    for p in kind.properties.int_properties:
        if p.name == "BlackboardType":
            p.default_value = 1
    never = g.compare("equal_s32", "int", 99, kind)
    state = g.query("shootable_state")
    shot = g.compare("less_s32", "int", 1, state)               # 1 < state: released
    ice_shot = g.both("and", g.compare("equal_s32", "int", ice_type, kind), shot)
    # every other frame of a nocked arrow counts the timer down, so a shot far from any red ice (which also counts
    # it down) is forgotten once the bow is drawn again
    left = g.compare("less_s32", "int", 0, g.int_data("get_int", timer))
    step = g.query("select_s32")
    g.feed(step, "bool", "Bool", ice_shot)
    g.feed(step, "int", "TrueValue", int(value))
    drain = g.query("select_s32")
    g.feed(drain, "bool", "Bool", left)
    g.feed(drain, "int", "TrueValue", -1)
    g.feed(drain, "int", "FalseValue", 0)
    g.feed(step, "int", "FalseValue", drain)
    add = g.int_data("add_int", timer)
    g.feed(add, "int", "Value", step)
    root = g.group(g.selector(never, old, g.add("dummy")), add)
    root.flags = type(old.flags)(int(old.flags))
    old.flags = type(old.flags)(0)
    g.s.commands[0].root_node_index = root.index
    return g.to_binary()


def red_ice_melt(raw: bytes, templates: Templates, timer: str, centre: tuple, radius: float,
                 dot_min: float = 0.85, max_dist: float = 15.0) -> bytes:
    """AI/Obj_RedIce_A_01.root.ainb: melts on the Blue Fire message OR (0 < `timer` AND the camera aims at the ice).

    Aim: the actor position + `centre` (its Tgt shape centre) is within 15 m of the camera and either at most
    ~30 degrees from its forward axis (DIrZ) or within `radius` of its ray. The ice decrements `timer` every frame
    while it is > 0. Validated in game (Longshot, 2026-11-15): Ice Cavern red ice and King Zora's ice (Zora Tunic)."""
    g = Logic(raw, templates)
    n = g.nodes
    if n[51].name != "QueryMessageBlueFireReceiveMessage" or n[48].name != "QueryLogicalDisjunction":
        raise ValueError("red ice AI: unexpected nodes")
    active = g.compare("less_s32", "int", 0, g.int_data("get_int", timer))
    cam = g.query("camera")
    outs = [p.name for p in cam.params.vec3f_outputs]
    at, ahead = outs.index("Position"), outs.index("DIrZ")
    middle = g.vec("add_vec", g.query("actor_position"), centre)
    # cone around the centre
    norm = g.query("normalize")
    to = g.vec("sub_vec", middle, cam, b_out=at)
    g._from(norm.params.vec3f_inputs[0], to)
    norm.queries = [to.index]
    in_cone = g.compare("less_f32", "float", float(dot_min), g.vec("dot", norm, cam, b_out=ahead))
    near = g.compare("less_f32", "float", g.vec("distance", middle, cam, b_out=at), float(max_dist))
    # ray: with v = centre - camera and t = v . DIrZ: |v|^2 < t^2 + radius^2 and t > 0
    along = g.vec("dot", g.vec("sub_vec", middle, cam, b_out=at), cam, b_out=ahead)
    square = g.query("mul_f32")
    for p in square.params.float_inputs:
        g._from(p, along)
    square.queries = [along.index]
    limit = g.query("add_f32")
    g.feed(limit, "float", "InputA", square)
    g.feed(limit, "float", "InputB", float(radius) ** 2)
    d2 = g.vec("distance", middle, cam, b_out=at)
    for p in d2.properties.bool_properties:
        if p.name == "IsCalcSquareDistance":
            p.default_value = True
    on_ray = g.both("and", g.compare("less_f32", "float", d2, limit), g.compare("less_f32", "float", 0.0, along))
    aimed = g.both("and", g.both("or", in_cone, on_ray), near)
    melt = g.both("and", active, aimed)
    for sel_index, (src, out) in ((28, (51, 1)), (45, (48, 0))):   # the selectors waiting for the Blue Fire message
        sel = n[sel_index]
        inp = sel.params.bool_inputs[0]
        if (inp.source.src_node_index, inp.source.src_output_index) != (src, out):
            raise ValueError("red ice AI: unexpected selector input")
        either = g.both("or", n[src], melt, a_out=out)
        g._from(inp, either)
        sel.queries = [either.index]
    g.wrap_root(g.group(g.add_by(timer, active, -1)))
    return g.to_binary()


def navi_return(raw: bytes, templates: Templates) -> bytes:
    """Link's AI, command "call Navi" (Player.sp.action `Summon`, D-pad right): whether Navi can be called or the module
    shows "cannot call Navi", it asks for the event named after the current map (`FireTemple`...: rows written by
    ModBuilder._write_navi_return; nothing happens on a map without a row). Validated in game (2026-11-25)."""
    g = Graph(raw, templates)
    blocked = next(n for n in g.nodes if n.name == "ExecuteNaviOpenUICannotCallNavi")
    area = next(n for n in g.nodes if n.name == "QueryIsNaviAreaHint")
    both = next(n for n in g.nodes if [p.node_index for p in n.child_plugs][:1] == [blocked.index]
                and n.type == g.ainb.NodeType.Element_Simultaneous)
    choice = next(n for n in g.nodes if n.type == g.ainb.NodeType.Element_BoolSelector and n.queries == [area.index])
    path, name, ask = g.add("map_path"), g.add("file_name"), g.add("request_event")
    g._link(next(p for p in name.params.string_inputs if p.name == "FilePath"), path)
    g._link(next(p for p in ask.params.string_inputs if p.name == "EventName"), name)
    name.queries, ask.queries = [path.index], [name.index]
    for p in ask.properties.bool_properties:
        if p.name == "ExecuteEveryFrame":
            p.default_value = False
    both.child_plugs[0].node_index = ask.index
    for plug in choice.child_plugs:
        plug.node_index = both.index
    # Navi can be called (QueryNaviIsNaviFlag): the module does nothing itself, the call is handled elsewhere
    flag = next(n for n in g.nodes if n.name == "QueryNaviIsNaviFlag")
    call = next(n for n in g.nodes if n.type == g.ainb.NodeType.Element_BoolSelector and n.queries == [flag.index])
    plug = next(p for p in call.child_plugs if p.name == "True")
    calling = g.add("simultaneous")
    calling.child_plugs[:] = [g.child(g.nodes[plug.node_index]), g.child(ask)]
    plug.node_index = calling.index
    return g.to_binary()


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
