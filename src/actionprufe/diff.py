"""Diferencia semantica entre dos estados de la pagina.

Se compara por multiconjunto de identidades, no por posicion. Si una lista
virtualizada reordena o recicla sus nodos y el contenido percibido es el mismo, el
diff sale vacio — que es justo lo que queremos: no hubo efecto observable.
"""

from __future__ import annotations

from collections import Counter

from .snapshot import REDACTED
from .types import Change, Diff, NodeKey, Snapshot

Payload = tuple[str | None, frozenset[str]]


def redact(diff: Diff, target: NodeKey | None, secret: str | None = None) -> Diff:
    """Tapa el secreto de quien llama alli donde asome.

    La redaccion normal ocurre dentro del navegador, pero se apoya en marcas que escribe
    la propia pagina (`type=password`, `autocomplete`, `data-ap-sensitive`). Cuando es
    quien llama el que sabe que ese campo lleva un secreto, el valor ya ha cruzado a
    Python sin tapar y hay que taparlo aqui, antes de que llegue a un motivo, a un log,
    a un fichero de traza o al prompt del arbitro.

    Se tapa el objetivo **y cualquier otro nodo cuyo valor contenga el secreto**. Tapar
    solo el objetivo dejaba escapar el caso mas normal de todos: la pagina que refleja lo
    que escribes en otro sitio —una vista previa, un medidor de fuerza, un campo de
    confirmacion que no es `type=password`— y que el navegador no reconoce como sensible.
    El resto de la pagina se deja intacto: no es un secreto de quien llama, y vaciarlo
    entero dejaria la verificacion sin nada que comparar.
    """
    if target is None and not secret:
        return diff

    def tapar(
        payload: tuple[str | None, frozenset[str]] | None,
    ) -> tuple[str | None, frozenset[str]] | None:
        if payload is None:
            return None
        value, states = payload
        return (REDACTED if value else value, states)

    def delata(payload: tuple[str | None, frozenset[str]] | None) -> bool:
        return bool(secret and payload and payload[0] and secret in payload[0])

    def clave(key: NodeKey) -> NodeKey:
        # El nombre accesible tambien puede llevar el secreto dentro: hay controles que
        # reflejan lo tecleado en su propio `aria-label`, y ese texto no pasa por la
        # redaccion del navegador porque se resuelve antes de mirar si el campo es
        # sensible. Se tapa aqui aunque cambie la identidad del nodo: perder un poco de
        # precision al atribuir es mejor que publicar un secreto.
        if secret and secret in key.name:
            return NodeKey(role=key.role, name=REDACTED, region=key.region)
        return key

    changes = tuple(
        Change(kind=c.kind, key=clave(c.key), before=tapar(c.before), after=tapar(c.after))
        if c.key == target
        or delata(c.before)
        or delata(c.after)
        or (secret and secret in c.key.name)
        else c
        for c in diff.changes
    )
    return Diff(changes=changes, url_changed=diff.url_changed, text_changed=diff.text_changed)


def _group(snapshot: Snapshot) -> dict[NodeKey, Counter[Payload]]:
    """Agrupa los nodos por identidad, contando cuantos comparten cada carga util."""
    grouped: dict[NodeKey, Counter[Payload]] = {}
    for node in snapshot.nodes:
        grouped.setdefault(node.key, Counter())[node.payload] += 1
    return grouped


def _changes_for(key: NodeKey, before: Counter[Payload], after: Counter[Payload]) -> list[Change]:
    """Diferencias de una sola identidad, respetando cuantos ejemplares hay de cada una.

    El emparejamiento importa. Si de tres filas iguales quedan dos, hay una desaparicion,
    no tres cambios; y si una de las que quedan ademas muta, hay una desaparicion y un
    cambio, no dos de cada. Contar por separado las apariciones y las mutaciones, como se
    hacia antes, duplicaba unas y perdia otras.
    """
    # Lo que sobrevive intacto no es ningun cambio.
    only_before = list((before - after).elements())
    only_after = list((after - before).elements())

    changes: list[Change] = []
    paired = min(len(only_before), len(only_after))
    for index in range(paired):
        changes.append(
            Change(kind="changed", key=key, before=only_before[index], after=only_after[index])
        )
    for payload in only_before[paired:]:
        changes.append(Change(kind="disappeared", key=key, before=payload))
    for payload in only_after[paired:]:
        changes.append(Change(kind="appeared", key=key, after=payload))
    return changes


def compute(before: Snapshot, after: Snapshot) -> Diff:
    """Calcula que cambio entre dos snapshots.

    Args:
        before: estado previo a la accion.
        after: estado posterior a la accion.

    Returns:
        El `Diff` con las apariciones, desapariciones y mutaciones observadas.
    """
    by_key_before = _group(before)
    by_key_after = _group(after)

    changes: list[Change] = []
    for key in by_key_before.keys() | by_key_after.keys():
        changes.extend(
            _changes_for(key, by_key_before.get(key, Counter()), by_key_after.get(key, Counter()))
        )

    return Diff(
        changes=tuple(changes),
        url_changed=before.url != after.url,
        text_changed=before.text_digest != after.text_digest,
    )
