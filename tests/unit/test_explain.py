"""El informe que se mira cuando el motivo de una linea no basta."""

from __future__ import annotations

from actionprufe import diff as diffing
from actionprufe.errors import VerificationFailed
from actionprufe.types import (
    REDACTED,
    ActionSpec,
    Diff,
    Judgement,
    NodeKey,
    Result,
    Verdict,
    explain,
)
from builders import node, snapshot


def _caso() -> tuple[ActionSpec, Diff]:
    before = snapshot(node("button", "Anadir Camiseta M", "lista"))
    after = snapshot(
        node("button", "Anadir Camiseta M", "lista"),
        node("listitem", "Pantalon L", "carrito"),
    )
    spec = ActionSpec(
        kind="click",
        target=NodeKey("button", "Anadir Camiseta M", "lista"),
        target_states=frozenset(),
        intent="el carrito suma una camiseta",
    )
    return spec, diffing.compute(before, after)


def test_el_informe_junta_las_cuatro_cosas_que_hacen_falta() -> None:
    spec, cambios = _caso()
    juicio = Judgement(Verdict.MISMATCH, "el efecto corresponde a otro elemento")

    informe = explain(spec, juicio, cambios, attempts=2, undone=1)

    assert "click sobre button[Anadir Camiseta M] en lista" in informe
    assert "el carrito suma una camiseta" in informe
    assert "MISMATCH" in informe
    assert "1 deshecho/s" in informe
    assert "Pantalon L" in informe


def test_el_informe_no_destapa_un_valor_sensible() -> None:
    spec, cambios = _caso()
    spec = ActionSpec(
        kind="fill",
        target=spec.target,
        target_states=frozenset(),
        payload="hunter2-secreta",
        sensitive=True,
    )

    informe = explain(spec, Judgement(Verdict.MATCH, "ok"), cambios)

    assert "hunter2-secreta" not in informe
    assert REDACTED in informe


def test_el_informe_dice_cuando_lo_desempato_la_ia() -> None:
    spec, cambios = _caso()
    juicio = Judgement(Verdict.MATCH, "confirmado", escalated=True)

    assert "arbitro de IA" in explain(spec, juicio, cambios)


def test_el_result_y_el_error_dan_el_mismo_informe() -> None:
    spec, cambios = _caso()
    juicio = Judgement(Verdict.MISMATCH, "el efecto corresponde a otro elemento")

    resultado = Result(spec=spec, judgement=juicio, diff=cambios, attempts=1)
    error = VerificationFailed(juicio, cambios, 1, spec)

    assert resultado.explain() == error.explain()


def test_un_error_sin_contexto_sigue_explicando_lo_que_puede() -> None:
    """Nadie deberia construirlo asi, pero degradar no es lo mismo que reventar."""
    _, cambios = _caso()
    error = VerificationFailed(Judgement(Verdict.MISMATCH, "algo"), cambios, 1)

    assert "Pantalon L" in error.explain()
