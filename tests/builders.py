"""Constructores de estados sinteticos para probar el nucleo sin navegador.

Viven aqui y no en un `conftest.py` porque hay dos suites con conftest propio y
pytest los importa a ambos como modulo `conftest`: el segundo tapa al primero.
"""

from __future__ import annotations

from collections.abc import Iterable

from actionproof.types import Node, NodeKey, Snapshot


def node(
    role: str,
    name: str,
    region: str = "document",
    *,
    value: str | None = None,
    states: Iterable[str] = (),
) -> Node:
    """Crea un nodo con la identidad y la carga util indicadas."""
    return Node(
        key=NodeKey(role=role, name=name, region=region), value=value, states=frozenset(states)
    )


def snapshot(
    *nodes: Node,
    url: str = "https://test.local/",
    text: str = "t",
    settled: bool = True,
) -> Snapshot:
    """Crea un snapshot a partir de una lista de nodos."""
    return Snapshot(url=url, nodes=tuple(nodes), text_digest=text, settled=settled)
