from actionprufe import diff as diffing
from actionprufe.judge import judge
from actionprufe.types import ActionSpec, NodeKey, Verdict
from builders import node, snapshot


def spec(
    kind: str = "click",
    *,
    name: str = "Anadir Camiseta M",
    role: str = "button",
    region: str = "lista",
    states: frozenset[str] = frozenset(),
    value: str | None = None,
    payload: str | None = None,
    intent: str | None = None,
) -> ActionSpec:
    return ActionSpec(
        kind=kind,
        target=NodeKey(role=role, name=name, region=region),
        target_states=states,
        target_value=value,
        payload=payload,
        intent=intent,
    )


def test_sin_efecto_es_fallo() -> None:
    base = snapshot(node("button", "Anadir Camiseta M", "lista"))
    verdict = judge(spec(), diffing.compute(base, base), base, base)
    assert verdict.verdict is Verdict.MISMATCH
    assert "ningun efecto" in verdict.reason


def test_sin_efecto_pero_pagina_inestable_es_ambiguo() -> None:
    """No es lo mismo 'no hizo nada' que 'aun no ha terminado de hacerlo'."""
    base = snapshot(node("button", "Anadir Camiseta M", "lista"))
    unsettled = snapshot(node("button", "Anadir Camiseta M", "lista"), settled=False)
    verdict = judge(spec(), diffing.compute(base, unsettled), base, unsettled)
    assert verdict.verdict is Verdict.AMBIGUOUS


def test_clic_atribuido_al_objetivo_es_correcto() -> None:
    before = snapshot(node("button", "Anadir Camiseta M", "lista"))
    after = snapshot(
        node("button", "Anadir Camiseta M", "lista"),
        node("listitem", "Camiseta M", "carrito"),
    )
    verdict = judge(spec(), diffing.compute(before, after), before, after)
    assert verdict.verdict is Verdict.MATCH


def test_el_vecino_se_queda_el_clic_es_fallo() -> None:
    """El fallo caracteristico del DOM virtualizado: el efecto va al elemento de al lado."""
    before = snapshot(
        node("button", "Anadir Camiseta M", "lista"),
        node("button", "Anadir Pantalon L", "lista"),
    )
    after = snapshot(
        node("button", "Anadir Camiseta M", "lista"),
        node("button", "Anadir Pantalon L", "lista"),
        node("listitem", "Pantalon L", "carrito"),
    )
    verdict = judge(spec(), diffing.compute(before, after), before, after)
    assert verdict.verdict is Verdict.MISMATCH
    assert "Pantalon L" in verdict.reason


def test_efecto_sin_relacion_es_ambiguo() -> None:
    before = snapshot(node("button", "Anadir Camiseta M", "lista"))
    after = snapshot(
        node("button", "Anadir Camiseta M", "lista"),
        node("listitem", "Envio gratis", "avisos"),
    )
    verdict = judge(spec(), diffing.compute(before, after), before, after)
    assert verdict.verdict is Verdict.AMBIGUOUS


def test_la_intencion_declarada_resuelve_lo_ambiguo() -> None:
    before = snapshot(node("button", "Anadir Camiseta M", "lista"))
    after = snapshot(
        node("button", "Anadir Camiseta M", "lista"),
        node("listitem", "Envio gratis aplicado", "avisos"),
    )
    verdict = judge(
        spec(intent="se aplica el envio gratis"),
        diffing.compute(before, after),
        before,
        after,
    )
    assert verdict.verdict is Verdict.MATCH


def test_fill_en_el_campo_correcto() -> None:
    before = snapshot(node("textbox", "Cupon", "form", value=""))
    after = snapshot(node("textbox", "Cupon", "form", value="VERANO"))
    verdict = judge(
        spec("fill", name="Cupon", role="textbox", region="form", value="", payload="VERANO"),
        diffing.compute(before, after),
        before,
        after,
    )
    assert verdict.verdict is Verdict.MATCH


def test_fill_que_entra_en_otro_campo_es_fallo() -> None:
    before = snapshot(
        node("textbox", "Cupon", "form", value=""),
        node("textbox", "Email", "form", value=""),
    )
    after = snapshot(
        node("textbox", "Cupon", "form", value=""),
        node("textbox", "Email", "form", value="VERANO"),
    )
    verdict = judge(
        spec("fill", name="Cupon", role="textbox", region="form", value="", payload="VERANO"),
        diffing.compute(before, after),
        before,
        after,
    )
    assert verdict.verdict is Verdict.MISMATCH
    assert "Email" in verdict.reason


def test_conmutar_la_casilla_correcta() -> None:
    before = snapshot(node("checkbox", "Acepto", "form"))
    after = snapshot(node("checkbox", "Acepto", "form", states=["checked"]))
    verdict = judge(
        spec("check", name="Acepto", role="checkbox", region="form"),
        diffing.compute(before, after),
        before,
        after,
    )
    assert verdict.verdict is Verdict.MATCH


def test_conmutar_otra_casilla_es_fallo() -> None:
    before = snapshot(
        node("checkbox", "Acepto", "form"),
        node("checkbox", "Newsletter", "form"),
    )
    after = snapshot(
        node("checkbox", "Acepto", "form"),
        node("checkbox", "Newsletter", "form", states=["checked"]),
    )
    verdict = judge(
        spec("check", name="Acepto", role="checkbox", region="form"),
        diffing.compute(before, after),
        before,
        after,
    )
    assert verdict.verdict is Verdict.MISMATCH
    assert "Newsletter" in verdict.reason


def test_un_tercero_que_se_activa_es_fallo_aunque_sea_de_otro_rol() -> None:
    """Restringir la comprobacion al mismo rol dejaba pasar efectos colaterales reales."""
    before = snapshot(
        node("checkbox", "Acepto", "form"),
        node("switch", "Modo oscuro", "form"),
    )
    after = snapshot(
        node("checkbox", "Acepto", "form", states=["checked"]),
        node("switch", "Modo oscuro", "form", states=["pressed"]),
    )
    verdict = judge(
        spec("check", name="Acepto", role="checkbox", region="form"),
        diffing.compute(before, after),
        before,
        after,
    )
    assert verdict.verdict is Verdict.MISMATCH
    assert "Modo oscuro" in verdict.reason


def test_el_radio_que_se_apaga_al_elegir_otro_no_es_efecto_colateral() -> None:
    """En un grupo excluyente, que el hermano pierda el estado es lo normal, no un fallo."""
    before = snapshot(
        node("radio", "Envio estandar", "form", states=["checked"]),
        node("radio", "Envio urgente", "form"),
    )
    after = snapshot(
        node("radio", "Envio estandar", "form"),
        node("radio", "Envio urgente", "form", states=["checked"]),
    )
    verdict = judge(
        spec("check", name="Envio urgente", role="radio", region="form"),
        diffing.compute(before, after),
        before,
        after,
    )
    assert verdict.verdict is Verdict.MATCH


def test_conmutar_de_mas_tambien_es_fallo() -> None:
    """Marcar la correcta no basta si de paso se marca otra."""
    before = snapshot(
        node("checkbox", "Acepto", "form"),
        node("checkbox", "Newsletter", "form"),
    )
    after = snapshot(
        node("checkbox", "Acepto", "form", states=["checked"]),
        node("checkbox", "Newsletter", "form", states=["checked"]),
    )
    verdict = judge(
        spec("check", name="Acepto", role="checkbox", region="form"),
        diffing.compute(before, after),
        before,
        after,
    )
    assert verdict.verdict is Verdict.MISMATCH
