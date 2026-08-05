"""Las trazas sirven para reconstruir despues, y no pueden tumbar nada."""

from __future__ import annotations

import json
from pathlib import Path

from actionprufe import diff as diffing
from actionprufe import tracing
from actionprufe.types import REDACTED, ActionSpec, Diff, Judgement, NodeKey, Verdict
from builders import node, snapshot

SECRETO = "hunter2-secreta"


def _caso(sensitive: bool = False) -> tuple[ActionSpec, Diff]:
    before = snapshot(node("textbox", "Contrasena", "form", value=""))
    after = snapshot(
        node("textbox", "Contrasena", "form", value=REDACTED if sensitive else SECRETO)
    )
    spec = ActionSpec(
        kind="fill",
        target=NodeKey("textbox", "Contrasena", "form"),
        target_states=frozenset(),
        payload=SECRETO,
        intent="se rellena la contrasena",
        sensitive=sensitive,
    )
    return spec, diffing.compute(before, after)


def test_el_registro_recoge_lo_que_hace_falta_para_reconstruir() -> None:
    spec, cambios = _caso()
    registro = tracing.build_record(spec, Judgement(Verdict.MATCH, "ok"), cambios, attempt=1)

    assert registro["accion"] == "fill"
    assert registro["objetivo"]["nombre"] == "Contrasena"
    assert registro["intencion"] == "se rellena la contrasena"
    assert registro["veredicto"] == "match"
    assert registro["intento"] == 1
    assert len(registro["cambios"]) == 1


def test_un_valor_sensible_tampoco_llega_al_disco() -> None:
    spec, cambios = _caso(sensitive=True)
    registro = tracing.build_record(spec, Judgement(Verdict.MATCH, "ok"), cambios, attempt=1)

    assert SECRETO not in json.dumps(registro, ensure_ascii=False)
    assert registro["valor"] == REDACTED


def test_se_escribe_un_fichero_por_accion_y_ordenan_solos(tmp_path: Path) -> None:
    spec, cambios = _caso()
    for orden in (1, 2, 10):
        registro = tracing.build_record(spec, Judgement(Verdict.MATCH, "ok"), cambios, 1)
        assert tracing.write(tmp_path, orden, registro) is not None

    nombres = sorted(p.name for p in tmp_path.iterdir())
    assert nombres == ["0001-fill-match.json", "0002-fill-match.json", "0010-fill-match.json"]
    assert json.loads((tmp_path / nombres[0]).read_text(encoding="utf-8"))["accion"] == "fill"


def test_una_traza_que_no_se_puede_escribir_no_tumba_la_operacion(tmp_path: Path) -> None:
    """Quien verifica una operacion real no puede perderla porque no quepa un diagnostico."""
    estorbo = tmp_path / "estorbo"
    estorbo.write_text("no soy una carpeta", encoding="utf-8")
    spec, cambios = _caso()

    resultado = tracing.write(
        estorbo, 1, tracing.build_record(spec, Judgement(Verdict.MATCH, "ok"), cambios, 1)
    )

    assert resultado is None
