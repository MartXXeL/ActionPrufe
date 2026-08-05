"""Tipos compartidos por todo ActionProof.

La pieza clave es `NodeKey`: la identidad de un elemento **no** incluye su posicion
en el DOM. En una pagina virtualizada (React reciclando nodos de una lista) el mismo
nodo fisico representa cosas distintas de un instante a otro, asi que identificar por
ruta o por handle produce falsos positivos. Aqui la identidad es semantica: rol,
nombre accesible y region.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Verdict(StrEnum):
    """Resultado de contrastar el efecto observado con el pretendido."""

    MATCH = "match"
    """El efecto observado es el pretendido."""

    MISMATCH = "mismatch"
    """Se observo un efecto que contradice lo pretendido (o no se observo ninguno)."""

    AMBIGUOUS = "ambiguous"
    """Hubo efecto, pero no se puede atribuir ni descartar sin mas informacion."""


@dataclass(frozen=True, slots=True)
class NodeKey:
    """Identidad semantica de un elemento, estable frente a reciclado de nodos."""

    role: str
    name: str
    region: str

    def __str__(self) -> str:
        """Forma legible que se usa tal cual en motivos, logs y prompts."""
        return f"{self.role}[{self.name}] en {self.region}"


@dataclass(frozen=True, slots=True)
class Node:
    """Un elemento observable: su identidad mas la carga util que puede mutar."""

    key: NodeKey
    value: str | None
    states: frozenset[str]

    @property
    def payload(self) -> tuple[str | None, frozenset[str]]:
        """Lo que puede cambiar sin que el elemento deje de ser el mismo."""
        return (self.value, self.states)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Estado semantico de la pagina en un instante."""

    url: str
    nodes: tuple[Node, ...]
    text_digest: str
    settled: bool
    """False si la pagina seguia mutando cuando se agoto el tiempo de espera."""


@dataclass(frozen=True, slots=True)
class Change:
    """Una diferencia concreta entre dos snapshots."""

    kind: str
    """`appeared`, `disappeared` o `changed`."""

    key: NodeKey
    before: tuple[str | None, frozenset[str]] | None = None
    after: tuple[str | None, frozenset[str]] | None = None

    def describe(self) -> str:
        """Descripcion en una linea, apta para logs y para el arbitro de IA."""
        if self.kind == "appeared":
            return f"aparecio {self.key}"
        if self.kind == "disappeared":
            return f"desaparecio {self.key}"
        before_value, before_states = self.before or (None, frozenset())
        after_value, after_states = self.after or (None, frozenset())
        parts: list[str] = []
        if before_value != after_value:
            parts.append(f"valor {before_value!r} -> {after_value!r}")
        gained = sorted(after_states - before_states)
        lost = sorted(before_states - after_states)
        if gained:
            parts.append(f"gano {', '.join(gained)}")
        if lost:
            parts.append(f"perdio {', '.join(lost)}")
        return f"cambio {self.key}: {'; '.join(parts) or 'sin detalle'}"


@dataclass(frozen=True, slots=True)
class Diff:
    """Conjunto de cambios entre el pre-estado y el post-estado de una accion."""

    changes: tuple[Change, ...]
    url_changed: bool
    text_changed: bool

    def __bool__(self) -> bool:
        """True si se observo algun efecto, por minimo que sea."""
        return bool(self.changes) or self.url_changed or self.text_changed

    def of_kind(self, kind: str) -> tuple[Change, ...]:
        """Los cambios de un tipo concreto."""
        return tuple(c for c in self.changes if c.kind == kind)

    def describe(self) -> str:
        """Todas las diferencias, una por linea."""
        lines = [c.describe() for c in self.changes]
        if self.url_changed:
            lines.append("cambio la URL")
        if self.text_changed and not lines:
            lines.append("cambio el texto de la pagina sin cambiar ningun elemento observable")
        return "\n".join(lines) or "no cambio nada"


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """Que se pidio hacer, para poder contrastarlo con lo que paso."""

    kind: str
    """`click`, `fill`, `check`, `uncheck` o `select`."""

    target: NodeKey | None
    """Identidad del elemento sobre el que se actuo, leida *antes* de actuar."""

    target_states: frozenset[str]
    """Estados del objetivo antes de la accion (para detectar el volteo esperado)."""

    target_value: str | None = None
    """Valor del objetivo antes de la accion."""

    payload: str | None = None
    """Texto a escribir u opcion a seleccionar, si aplica."""

    intent: str | None = None
    """Intencion declarada por quien llama, en lenguaje natural. Opcional."""


@dataclass(frozen=True, slots=True)
class Judgement:
    """Veredicto sobre una accion, con el motivo legible por humanos."""

    verdict: Verdict
    reason: str
    escalated: bool = False
    """True si el veredicto lo desempato el arbitro de IA."""


@dataclass(frozen=True, slots=True)
class Result:
    """Lo que devuelve cada accion verificada."""

    spec: ActionSpec
    judgement: Judgement
    diff: Diff
    attempts: int
    undone: int = 0
    """Cuantas veces hubo que deshacer antes de dar el resultado por bueno."""

    @property
    def ok(self) -> bool:
        """True si el efecto observado fue el pretendido."""
        return self.judgement.verdict is Verdict.MATCH
