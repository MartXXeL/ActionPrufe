"""Diferencia semantica entre dos estados de la pagina.

Se compara por multiconjunto de identidades, no por posicion. Si una lista
virtualizada reordena o recicla sus nodos y el contenido percibido es el mismo, el
diff sale vacio — que es justo lo que queremos: no hubo efecto observable.
"""

from __future__ import annotations

from collections import Counter

from .types import Change, Diff, Snapshot


def compute(before: Snapshot, after: Snapshot) -> Diff:
    """Calcula que cambio entre dos snapshots.

    Args:
        before: estado previo a la accion.
        after: estado posterior a la accion.

    Returns:
        El `Diff` con las apariciones, desapariciones y mutaciones observadas.
    """
    before_keys = Counter(n.key for n in before.nodes)
    after_keys = Counter(n.key for n in after.nodes)

    changes: list[Change] = []

    for key, count in (after_keys - before_keys).items():
        payloads = [n.payload for n in after.nodes if n.key == key]
        for payload in payloads[:count]:
            changes.append(Change(kind="appeared", key=key, after=payload))

    for key, count in (before_keys - after_keys).items():
        payloads = [n.payload for n in before.nodes if n.key == key]
        for payload in payloads[:count]:
            changes.append(Change(kind="disappeared", key=key, before=payload))

    for key in before_keys.keys() & after_keys.keys():
        old = Counter(n.payload for n in before.nodes if n.key == key)
        new = Counter(n.payload for n in after.nodes if n.key == key)
        if old == new:
            continue
        gone = list((old - new).elements())
        arrived = list((new - old).elements())
        for index, payload in enumerate(arrived):
            previous = gone[index] if index < len(gone) else None
            changes.append(Change(kind="changed", key=key, before=previous, after=payload))

    return Diff(
        changes=tuple(changes),
        url_changed=before.url != after.url,
        text_changed=before.text_digest != after.text_digest,
    )
