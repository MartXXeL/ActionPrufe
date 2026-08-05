"""El secreto se tapa alli donde asome, no solo en el campo donde se escribio.

La redaccion del navegador se apoya en marcas que pone la pagina. Cuando el secreto lo
declara quien llama, esas marcas no existen y la pagina puede repetir el valor donde
quiera: una vista previa, un medidor de fuerza, un parrafo de confirmacion. Cada uno de
esos sitios es un nodo distinto del objetivo, y antes se publicaban en claro.
"""

from __future__ import annotations

import json

from actionprufe import diff as diffing
from actionprufe import tracing
from actionprufe.ai_judge import build_prompt
from actionprufe.types import REDACTED, ActionSpec, Diff, Judgement, NodeKey, Verdict
from builders import node, snapshot

IBAN = "ES9121000418450200051332"
OBJETIVO = NodeKey("textbox", "Numero de cuenta", "form")


def _spec() -> ActionSpec:
    return ActionSpec(
        kind="fill",
        target=OBJETIVO,
        target_states=frozenset(),
        target_value="",
        payload=IBAN,
        sensitive=True,
    )


def _reflejado() -> Diff:
    """La pagina repite el valor en un parrafo que no es el campo objetivo."""
    before = snapshot(node("textbox", "Numero de cuenta", "form", value=""))
    after = snapshot(
        node("textbox", "Numero de cuenta", "form", value=IBAN),
        node("paragraph", f"Vas a transferir a {IBAN}", "resumen"),
    )
    return diffing.compute(before, after)


def test_el_eco_de_la_pagina_en_otro_nodo_tambien_se_tapa() -> None:
    limpio = diffing.redact(_reflejado(), OBJETIVO, IBAN)

    assert IBAN not in limpio.describe()
    assert limpio.describe().count(REDACTED) >= 2, "el campo y el eco"


def test_el_eco_no_llega_al_prompt_del_arbitro() -> None:
    limpio = diffing.redact(_reflejado(), OBJETIVO, IBAN)

    assert IBAN not in build_prompt(_spec(), limpio)


def test_el_eco_no_llega_al_disco() -> None:
    limpio = diffing.redact(_reflejado(), OBJETIVO, IBAN)
    registro = tracing.build_record(_spec(), Judgement(Verdict.MATCH, "ok"), limpio, 1)

    assert IBAN not in json.dumps(registro, ensure_ascii=False)


def test_un_secreto_metido_en_el_nombre_accesible_tambien_se_tapa() -> None:
    """Hay controles que reflejan lo tecleado en su propio `aria-label`."""
    before = snapshot(node("textbox", "Numero de cuenta", "form", value=""))
    after = snapshot(node("textbox", f"Cuenta {IBAN}", "form", value=""))

    limpio = diffing.redact(diffing.compute(before, after), OBJETIVO, IBAN)

    assert IBAN not in limpio.describe()


def test_sin_secreto_declarado_no_se_toca_nada_que_no_sea_el_objetivo() -> None:
    """La redaccion no puede comerse la pagina: dejaria la verificacion sin comparar."""
    limpio = diffing.redact(_reflejado(), OBJETIVO, None)

    assert IBAN in limpio.describe(), "el eco sigue, porque nadie declaro que fuera secreto"
