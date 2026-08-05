"""El contenido sensible no puede salir de la pagina.

Importa porque ese texto acaba en los mensajes de error, en los logs de quien usa la
libreria y, cuando el veredicto es ambiguo, en el prompt que se envia a un tercero.
"""

from __future__ import annotations

from actionprufe import diff as diffing
from actionprufe.ai_judge import build_prompt
from actionprufe.judge import judge
from actionprufe.snapshot import REDACTED
from actionprufe.types import ActionSpec, NodeKey, Verdict
from builders import node, snapshot

CONTRASENA = "hunter2-secreta"


def _spec() -> ActionSpec:
    return ActionSpec(
        kind="fill",
        target=NodeKey("textbox", "Contrasena", "form"),
        target_states=frozenset(),
        target_value="",
        payload=CONTRASENA,
        sensitive=True,
    )


def test_el_valor_sensible_nunca_llega_al_prompt_de_la_ia() -> None:
    before = snapshot(node("textbox", "Contrasena", "form", value=""))
    after = snapshot(node("textbox", "Contrasena", "form", value=REDACTED))

    prompt = build_prompt(_spec(), diffing.compute(before, after))

    assert CONTRASENA not in prompt
    assert REDACTED in prompt


def test_un_campo_redactado_se_verifica_igualmente() -> None:
    """No se puede comparar el valor, pero si comprobar que cambio el campo correcto."""
    before = snapshot(node("textbox", "Contrasena", "form", value=""))
    after = snapshot(node("textbox", "Contrasena", "form", value=REDACTED))

    verdict = judge(_spec(), diffing.compute(before, after), before, after)

    assert verdict.verdict is Verdict.MATCH
    assert CONTRASENA not in verdict.reason
