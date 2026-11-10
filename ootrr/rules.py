"""Compilateur de règles de logique.

Les règles sont écrites dans les fichiers JSON sous forme d'expressions
au style Python, par exemple :

    "is_adult and can_use(Progressive_Hookshot) and (Bow or has_explosives)"

Elles sont analysées une seule fois avec le module `ast` (jamais exécutées
avec eval) puis transformées en fonctions `regle(state, age) -> bool`.

Vocabulaire disponible dans une règle :
  - True / False
  - is_child, is_adult                    -> l'âge en cours d'évaluation
  - <Objet> ou <Événement>                 -> possède au moins un exemplaire
  - <helper>                               -> règle nommée de helpers.json
  - <réglage booléen>                      -> valeur du réglage (ex. open_forest)
  - has(Objet, n)                          -> possède au moins n exemplaires
  - can_use(Objet)                         -> possède l'objet ET l'âge permet de
                                              l'utiliser ET ses prérequis (items.json)
  - can_play(Chant)                        -> possède l'ocarina et le chant
  - setting_is(reglage, 'valeur')          -> compare un réglage texte
  - count(A, B, C...)                      -> nombre d'objets possédés parmi la liste
  - setting_value(reglage)                 -> valeur numérique d'un réglage
  - hearts()                               -> cœurs de vie : 3 + réceptacles + quarts de cœur / 4
  - comparaisons : >=, >, <=, <, ==, != entre valeurs numériques
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Callable, Iterable, Mapping

if TYPE_CHECKING:
    from .search import State

Rule = Callable[["State", str], bool]
Num = Callable[["State", str], int]

AGES = ("child", "adult")


class RuleError(ValueError):
    """Erreur dans une règle écrite dans les données."""


def _const(value: bool) -> Rule:
    if value:
        rule = lambda state, age: True  # noqa: E731
    else:
        rule = lambda state, age: False  # noqa: E731
    rule.constant = value  # type: ignore[attr-defined]
    return rule


TRUE = _const(True)
FALSE = _const(False)


def _is_const(rule: Rule) -> bool | None:
    return getattr(rule, "constant", None)


class RuleCompiler:
    def __init__(
        self,
        item_names: Iterable[str],
        event_names: Iterable[str],
        helpers: Mapping[str, str],
        settings: Mapping[str, object],
        usable: Mapping[str, dict],
    ) -> None:
        self.item_names = set(item_names)
        self.event_names = set(event_names)
        self.helper_src = dict(helpers)
        self.settings = settings
        self.usable = usable
        self._helpers: dict[str, Rule] = {}
        self._compiling: list[str] = []

    # ------------------------------------------------------------------ API
    def compile(self, source: str | bool, where: str = "?") -> Rule:
        if isinstance(source, bool):
            return _const(source)
        text = str(source).strip()
        if not text:
            return TRUE
        try:
            tree = ast.parse(text, mode="eval")
        except SyntaxError as exc:
            raise RuleError(f"{where} : syntaxe invalide dans « {text} » ({exc.msg})") from None
        return self._bool(tree.body, where, text)

    def compile_all_helpers(self) -> None:
        """Compile tous les helpers pour détecter les erreurs même s'ils ne sont pas utilisés."""
        for name in self.helper_src:
            self._helper(name, f"helper {name}")

    # ------------------------------------------------------------ internes
    def _err(self, where: str, src: str, msg: str) -> RuleError:
        return RuleError(f"{where} : {msg} dans « {src} »")

    def _helper(self, name: str, where: str) -> Rule:
        if name in self._helpers:
            return self._helpers[name]
        if name in self._compiling:
            chain = " -> ".join(self._compiling + [name])
            raise RuleError(f"{where} : helper récursif ({chain})")
        self._compiling.append(name)
        try:
            rule = self.compile(self.helper_src[name], f"helper {name}")
        finally:
            self._compiling.pop()
        self._helpers[name] = rule
        return rule

    def _known_thing(self, name: str) -> bool:
        return name in self.item_names or name in self.event_names

    def _name(self, node: ast.Name, where: str, src: str) -> Rule:
        name = node.id
        if name in ("true", "True"):
            return TRUE
        if name in ("false", "False"):
            return FALSE
        if name == "is_child":
            return lambda state, age: age == "child"
        if name == "is_adult":
            return lambda state, age: age == "adult"
        if name in self.helper_src:
            return self._helper(name, where)
        if name in self.settings:
            value = self.settings[name]
            if not isinstance(value, bool):
                raise self._err(where, src, f"le réglage « {name} » n'est pas booléen, utilise setting_is()")
            return _const(value)
        if self._known_thing(name):
            return lambda state, age: state.has(name)
        raise self._err(where, src, f"nom inconnu « {name} »")

    def _thing_arg(self, node: ast.expr, where: str, src: str) -> str:
        if not isinstance(node, ast.Name) or not self._known_thing(node.id):
            raise self._err(where, src, "argument attendu : un nom d'objet ou d'événement")
        return node.id

    def _setting_arg(self, node: ast.expr, where: str, src: str) -> str:
        if not isinstance(node, ast.Name) or node.id not in self.settings:
            raise self._err(where, src, "argument attendu : un nom de réglage")
        return node.id

    def _can_use(self, item: str, where: str, src: str) -> Rule:
        info = self.usable.get(item, {})
        age_req = info.get("age")
        needs = [self._name(ast.Name(id=n), where, src) for n in info.get("needs", [])]

        def rule(state: "State", age: str) -> bool:
            if age_req and age != age_req:
                return False
            if not state.has(item):
                return False
            return all(n(state, age) for n in needs)

        return rule

    def _call(self, node: ast.Call, where: str, src: str) -> Rule:
        if not isinstance(node.func, ast.Name):
            raise self._err(where, src, "appel de fonction invalide")
        fname = node.func.id
        args = node.args
        if node.keywords:
            raise self._err(where, src, "arguments nommés non supportés")

        if fname == "has":
            if len(args) != 2 or not isinstance(args[1], ast.Constant) or not isinstance(args[1].value, int):
                raise self._err(where, src, "has(Objet, n) attend un objet et un entier")
            item, n = self._thing_arg(args[0], where, src), args[1].value
            return lambda state, age: state.has(item, n)

        if fname == "can_use":
            if len(args) != 1:
                raise self._err(where, src, "can_use(Objet) attend un argument")
            return self._can_use(self._thing_arg(args[0], where, src), where, src)

        if fname == "can_play":
            if len(args) != 1:
                raise self._err(where, src, "can_play(Chant) attend un argument")
            song = self._thing_arg(args[0], where, src)
            if "Ocarina" not in self.item_names:
                raise self._err(where, src, "objet « Ocarina » absent de items.json")
            return lambda state, age: state.has("Ocarina") and state.has(song)

        if fname == "setting_is":
            if len(args) != 2 or not isinstance(args[1], ast.Constant):
                raise self._err(where, src, "setting_is(reglage, 'valeur') attend deux arguments")
            name = self._setting_arg(args[0], where, src)
            return _const(self.settings[name] == args[1].value)

        raise self._err(where, src, f"fonction inconnue « {fname} »")

    def _num(self, node: ast.expr, where: str, src: str) -> Num:
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            value = node.value
            return lambda state, age: value
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "count":
                things = [self._thing_arg(a, where, src) for a in node.args]
                return lambda state, age: sum(1 for t in things if state.has(t))
            if node.func.id == "hearts" and not node.args:
                def hearts(state, age):
                    containers = sum(1 for n in range(1, 21) if state.has("Heart_Container", n))
                    pieces = sum(1 for n in range(1, 81) if state.has("Heart_Piece", n))
                    return 3 + containers + pieces // 4
                return hearts
            if node.func.id == "setting_value" and len(node.args) == 1:
                name = self._setting_arg(node.args[0], where, src)
                value = self.settings[name]
                if not isinstance(value, int) or isinstance(value, bool):
                    raise self._err(where, src, f"le réglage « {name} » n'est pas un entier")
                return lambda state, age: value
        raise self._err(where, src, "valeur numérique attendue (entier, count(...) ou setting_value(...))")

    def _compare(self, node: ast.Compare, where: str, src: str) -> Rule:
        if len(node.ops) != 1:
            raise self._err(where, src, "une seule comparaison à la fois")
        left = self._num(node.left, where, src)
        right = self._num(node.comparators[0], where, src)
        op = node.ops[0]
        ops = {
            ast.GtE: lambda a, b: a >= b,
            ast.Gt: lambda a, b: a > b,
            ast.LtE: lambda a, b: a <= b,
            ast.Lt: lambda a, b: a < b,
            ast.Eq: lambda a, b: a == b,
            ast.NotEq: lambda a, b: a != b,
        }
        fn = ops.get(type(op))
        if fn is None:
            raise self._err(where, src, "opérateur de comparaison non supporté")
        return lambda state, age: fn(left(state, age), right(state, age))

    def _bool(self, node: ast.expr, where: str, src: str) -> Rule:
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            return _const(node.value)
        if isinstance(node, ast.Name):
            return self._name(node, where, src)
        if isinstance(node, ast.Call):
            return self._call(node, where, src)
        if isinstance(node, ast.Compare):
            return self._compare(node, where, src)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            inner = self._bool(node.operand, where, src)
            c = _is_const(inner)
            if c is not None:
                return _const(not c)
            return lambda state, age: not inner(state, age)
        if isinstance(node, ast.BoolOp):
            parts = [self._bool(v, where, src) for v in node.values]
            if isinstance(node.op, ast.And):
                if any(_is_const(p) is False for p in parts):
                    return FALSE
                parts = [p for p in parts if _is_const(p) is not True]
                if not parts:
                    return TRUE
                if len(parts) == 1:
                    return parts[0]
                return lambda state, age: all(p(state, age) for p in parts)
            if any(_is_const(p) is True for p in parts):
                return TRUE
            parts = [p for p in parts if _is_const(p) is not False]
            if not parts:
                return FALSE
            if len(parts) == 1:
                return parts[0]
            return lambda state, age: any(p(state, age) for p in parts)
        raise self._err(where, src, f"élément non supporté ({type(node).__name__})")
