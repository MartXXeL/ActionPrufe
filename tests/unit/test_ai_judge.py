import pytest
from conftest import node, snapshot

from actionproof import diff as diffing
from actionproof.ai_judge import build_prompt, read_verdict
from actionproof.types import ActionSpec, NodeKey


@pytest.mark.parametrize("answer", ["SI", " si ", "Sí", "yes", "SI."])
def test_respuestas_afirmativas(answer: str) -> None:
    assert read_verdict(answer) is True


@pytest.mark.parametrize(
    "answer",
    ["NO", "", None, "quiza", "probablemente si", "SI, pero con matices", "1", "true"],
)
def test_todo_lo_que_no_es_un_si_limpio_se_lee_como_no(answer: str | None) -> None:
    """Ante la duda no se aprueba: un 'podria' es un no."""
    assert read_verdict(answer) is False


def test_el_prompt_incluye_intencion_y_efectos() -> None:
    before = snapshot(node("button", "Anadir", "lista"))
    after = snapshot(node("button", "Anadir", "lista"), node("listitem", "Camiseta", "carrito"))
    spec = ActionSpec(
        kind="click",
        target=NodeKey("button", "Anadir", "lista"),
        target_states=frozenset(),
        intent="el carrito suma una camiseta",
    )
    prompt = build_prompt(spec, diffing.compute(before, after))
    assert "el carrito suma una camiseta" in prompt
    assert "Camiseta" in prompt
    assert "SI o NO" in prompt
