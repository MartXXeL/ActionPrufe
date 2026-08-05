"""Decide si el efecto observado es el efecto pretendido.

Todo lo que se puede decidir sin IA se decide sin IA. El veredicto `AMBIGUOUS` es la
unica puerta por la que se llama a un modelo, y ese modelo solo puede contestar si o
no (ver `ai_judge`).
"""

from __future__ import annotations

from .snapshot import REDACTED
from .text import overlap, relates
from .types import ActionSpec, Change, Diff, Judgement, Snapshot, Verdict

TOGGLE_STATES = frozenset({"checked", "selected", "pressed", "expanded"})

TOGGLE_ROLES = frozenset({"checkbox", "radio", "switch", "option", "menuitemcheckbox"})

STRONG_MATCH = 0.6
"""Solapamiento de tokens a partir del cual se considera atribuido un efecto."""


def _effects(diff: Diff) -> tuple[Change, ...]:
    """Cambios que representan un efecto positivo (algo que se añadio o mudo)."""
    return tuple(c for c in diff.changes if c.kind in {"appeared", "changed"})


def _toggled(change: Change) -> frozenset[str]:
    """Estados de conmutacion que este cambio gano o perdio."""
    before = change.before[1] if change.before else frozenset()
    after = change.after[1] if change.after else frozenset()
    return (before ^ after) & TOGGLE_STATES


def _describe_change_text(change: Change) -> str:
    """Texto asociado a un cambio, para medir solapamiento contra el objetivo."""
    value = (change.after or change.before or (None, frozenset()))[0] or ""
    return f"{change.key.name} {value}"


def _is_toggle_target(spec: ActionSpec) -> bool:
    """True si el objetivo es conmutable, este o no activado ahora mismo."""
    if spec.target_states & TOGGLE_STATES:
        return True
    return spec.target is not None and spec.target.role in TOGGLE_ROLES


def _judge_fill(spec: ActionSpec, diff: Diff) -> Judgement:
    """Un `fill` es correcto si el valor final del objetivo es el escrito."""
    expected = spec.payload or ""
    # Lo que se muestra en el motivo no siempre es lo que se compara: el motivo se
    # publica en logs y prompts, y el valor de un campo sensible no puede aparecer ahi.
    shown = REDACTED if spec.sensitive else repr(expected)
    for change in diff.changes:
        if change.kind != "changed" or change.key != spec.target:
            continue
        actual = (change.after or (None, frozenset()))[0] or ""
        if actual == REDACTED or spec.sensitive:
            # Campo sensible: su valor no se lee, asi que no hay nada que comparar. Lo
            # verificable es que cambio el campo correcto, y eso ya consta.
            return Judgement(Verdict.MATCH, f"el campo {spec.target} cambio (valor no leido)")
        if overlap(expected, actual) >= STRONG_MATCH or actual == expected:
            return Judgement(Verdict.MATCH, f"el campo {spec.target} contiene {actual!r}")
        return Judgement(
            Verdict.MISMATCH,
            f"se escribio en {spec.target} pero quedo {actual!r} en vez de {shown}",
        )

    for change in diff.changes:
        if change.kind == "changed" and change.key.role == "textbox":
            return Judgement(
                Verdict.MISMATCH,
                f"el texto entro en {change.key} en vez de en el objetivo {spec.target}",
            )

    return Judgement(
        Verdict.AMBIGUOUS,
        f"la pagina cambio pero el valor de {spec.target} no consta como modificado",
    )


def _gained_toggle(change: Change) -> frozenset[str]:
    """Estados de conmutacion que este cambio *gano* (no los que perdio)."""
    before = change.before[1] if change.before else frozenset()
    after = change.after[1] if change.after else frozenset()
    return (after - before) & TOGGLE_STATES


def _judge_toggle(spec: ActionSpec, diff: Diff) -> Judgement:
    """Una conmutacion es correcta si volteo el objetivo y solo el objetivo.

    Un tercero que *pierde* el estado no cuenta como efecto colateral: es lo que hace un
    grupo de radios o una lista de seleccion unica cuando se elige otra opcion. Lo que si
    cuenta es que un tercero lo *gane*, sea cual sea su rol — restringir la comprobacion a
    elementos del mismo rol que el objetivo dejaba pasar, por ejemplo, un interruptor que
    se activaba solo al marcar una casilla.
    """
    target_flip: Change | None = None
    foreign_flips: list[Change] = []
    foreign_gains: list[Change] = []

    for change in diff.changes:
        if not _toggled(change):
            continue
        if change.key == spec.target:
            target_flip = change
            continue
        foreign_flips.append(change)
        if _gained_toggle(change):
            foreign_gains.append(change)

    if target_flip and not foreign_gains:
        return Judgement(Verdict.MATCH, target_flip.describe())

    if foreign_flips and not target_flip:
        culprit = foreign_flips[0]
        return Judgement(
            Verdict.MISMATCH,
            f"se conmuto {culprit.key} en vez del objetivo {spec.target}",
        )

    if target_flip and foreign_gains:
        return Judgement(
            Verdict.MISMATCH,
            f"ademas del objetivo se conmuto {foreign_gains[0].key}",
        )

    return Judgement(
        Verdict.AMBIGUOUS,
        f"hubo cambios pero ninguno conmuta el estado de {spec.target}",
    )


def _judge_select(spec: ActionSpec, diff: Diff) -> Judgement:
    """Una seleccion es correcta si la opcion elegida es la pedida."""
    expected = spec.payload or ""
    for change in diff.changes:
        if change.kind != "changed":
            continue
        chosen = (change.after or (None, frozenset()))[0] or ""
        if change.key == spec.target:
            if overlap(expected, chosen) >= STRONG_MATCH or chosen == expected:
                return Judgement(Verdict.MATCH, f"{spec.target} quedo en {chosen!r}")
            return Judgement(
                Verdict.MISMATCH,
                f"{spec.target} quedo en {chosen!r} en vez de {expected!r}",
            )
    for change in diff.changes:
        if "selected" in _toggled(change) and overlap(expected, change.key.name) >= STRONG_MATCH:
            return Judgement(Verdict.MATCH, change.describe())
    return Judgement(Verdict.AMBIGUOUS, f"no consta que se seleccionara {expected!r}")


def _sibling_stole_the_click(spec: ActionSpec, change: Change, before: Snapshot) -> str | None:
    """Detecta que el efecto corresponde a *otro* elemento de la misma lista.

    Es el fallo caracteristico de las listas virtualizadas: el nodo se recicla entre
    que se localiza y que se clica, y el efecto acaba en el vecino. Sin esta
    comprobacion, el clic "no da error" y la operacion sigue con datos equivocados.
    """
    if spec.target is None:
        return None
    text = _describe_change_text(change)
    if relates(spec.target.name, text) >= STRONG_MATCH:
        return None
    for node in before.nodes:
        if node.key == spec.target:
            continue
        if node.key.role != spec.target.role or node.key.region != spec.target.region:
            continue
        if relates(node.key.name, text) >= STRONG_MATCH:
            return f"el efecto corresponde a {node.key}, no al objetivo {spec.target}"
    return None


def _judge_click(spec: ActionSpec, diff: Diff, before: Snapshot) -> Judgement:
    """Un clic generico es correcto si el efecto se puede atribuir al objetivo."""
    effects = _effects(diff)

    for change in effects:
        stolen = _sibling_stole_the_click(spec, change, before)
        if stolen:
            return Judgement(Verdict.MISMATCH, stolen)

    if spec.target is not None:
        for change in effects:
            if relates(spec.target.name, _describe_change_text(change)) >= STRONG_MATCH:
                return Judgement(Verdict.MATCH, f"atribuido al objetivo: {change.describe()}")

    if diff.url_changed:
        return Judgement(
            Verdict.AMBIGUOUS,
            "hubo navegacion, pero nada permite atribuirla al objetivo",
        )

    return Judgement(
        Verdict.AMBIGUOUS,
        f"la pagina cambio ({len(effects)} efectos) sin relacion clara con {spec.target}",
    )


def _refine_with_intent(spec: ActionSpec, diff: Diff, judgement: Judgement) -> Judgement:
    """Usa la intencion declarada para resolver un caso ambiguo, si alcanza."""
    if judgement.verdict is not Verdict.AMBIGUOUS or not spec.intent:
        return judgement
    described = diff.describe()
    if overlap(spec.intent, described) >= STRONG_MATCH:
        return Judgement(Verdict.MATCH, f"el efecto coincide con la intencion: {spec.intent!r}")
    return judgement


def judge(spec: ActionSpec, diff: Diff, before: Snapshot, after: Snapshot) -> Judgement:
    """Emite el veredicto sobre una accion ya ejecutada.

    Args:
        spec: que se pidio hacer.
        diff: diferencias observadas entre el pre-estado y el post-estado.
        before: estado previo, necesario para saber que otros elementos habia.
        after: estado posterior, del que interesa sobre todo si llego a estabilizarse.

    Returns:
        El `Judgement` con veredicto y motivo legible.
    """
    if not diff:
        if not after.settled:
            return Judgement(
                Verdict.AMBIGUOUS,
                "la pagina seguia mutando al agotarse la espera y no se observo efecto",
            )
        return Judgement(Verdict.MISMATCH, "la accion no produjo ningun efecto observable")

    if spec.kind == "fill":
        base = _judge_fill(spec, diff)
    elif spec.kind in {"check", "uncheck"}:
        base = _judge_toggle(spec, diff)
    elif spec.kind == "select":
        base = _judge_select(spec, diff)
    elif spec.kind == "click" and _is_toggle_target(spec):
        base = _judge_toggle(spec, diff)
    else:
        base = _judge_click(spec, diff, before)

    return _refine_with_intent(spec, diff, base)
