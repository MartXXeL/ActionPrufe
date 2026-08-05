"""Diferencia semantica entre dos estados de la pagina.

Se compara por multiconjunto de identidades, no por posicion. Si una lista
virtualizada reordena o recicla sus nodos y el contenido percibido es el mismo, el
diff sale vacio — que es justo lo que queremos: no hubo efecto observable.
"""

from __future__ import annotations

from collections import Counter

from .types import Change, Diff, NodeKey, Snapshot

Payload = tuple[str | None, frozenset[str]]


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
