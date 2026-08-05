"""Errores de ActionProof.

La jerarquia distingue tres desenlaces que exigen reacciones distintas de quien llama:
la accion hizo algo distinto (`VerificationFailed`), no se pudo deshacer lo que hizo
(`UndoFailed`) o directamente no habia forma de deshacerlo (`IrreversibleAction`).
Los dos ultimos dejan la pagina en un estado sucio y no deben reintentarse a ciegas.
"""

from __future__ import annotations

from .types import Diff, Judgement


class ActionProofError(Exception):
    """Raiz de todos los errores de la libreria."""


class VerificationFailed(ActionProofError):
    """La accion produjo un efecto distinto del pretendido y no se pudo corregir."""

    def __init__(self, judgement: Judgement, diff: Diff, attempts: int) -> None:
        self.judgement = judgement
        self.diff = diff
        self.attempts = attempts
        super().__init__(f"{judgement.reason} (tras {attempts} intento/s)")


class IrreversibleAction(ActionProofError):
    """Se detecto un efecto equivocado y no existe forma conocida de deshacerlo.

    La pagina queda como esta a proposito: es preferible abortar y que un humano
    decida a seguir operando sobre un estado que ya no es el esperado.
    """


class UndoFailed(ActionProofError):
    """Se intento deshacer el efecto equivocado y la pagina no volvio a su estado."""

    def __init__(self, message: str, residue: Diff) -> None:
        self.residue = residue
        super().__init__(message)
