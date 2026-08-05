from actionproof import diff as diffing
from builders import node, snapshot


def test_estado_identico_no_produce_diferencias() -> None:
    before = snapshot(node("button", "Anadir"), node("listitem", "Camiseta M"))
    assert not diffing.compute(before, before)


def test_reordenar_no_cuenta_como_cambio() -> None:
    """Una lista virtualizada reordena nodos sin que cambie nada percibible."""
    a, b = node("listitem", "Camiseta M"), node("listitem", "Camiseta L")
    assert not diffing.compute(snapshot(a, b), snapshot(b, a))


def test_detecta_aparicion_y_desaparicion() -> None:
    before = snapshot(node("listitem", "Camiseta M"))
    after = snapshot(node("listitem", "Camiseta L"))
    result = diffing.compute(before, after)
    assert [c.kind for c in result.of_kind("appeared")] == ["appeared"]
    assert result.of_kind("appeared")[0].key.name == "Camiseta L"
    assert result.of_kind("disappeared")[0].key.name == "Camiseta M"


def test_detecta_cambio_de_valor_conservando_identidad() -> None:
    before = snapshot(node("textbox", "Cupon", value=""))
    after = snapshot(node("textbox", "Cupon", value="VERANO"))
    (change,) = diffing.compute(before, after).changes
    assert change.kind == "changed"
    assert change.after == ("VERANO", frozenset())


def test_duplicados_se_cuentan_por_multiplicidad() -> None:
    """Anadir un segundo ejemplar identico es un efecto, no un empate."""
    before = snapshot(node("listitem", "Camiseta M"))
    after = snapshot(node("listitem", "Camiseta M"), node("listitem", "Camiseta M"))
    result = diffing.compute(before, after)
    assert len(result.of_kind("appeared")) == 1
    assert result.of_kind("changed") == (), "el ejemplar nuevo no es ademas una mutacion"


def test_un_ejemplar_de_mas_no_genera_cambio_fantasma() -> None:
    """Un mismo nodo no puede contarse dos veces, como aparicion y como mutacion."""
    before = snapshot(node("checkbox", "Seleccionar", "tabla"))
    after = snapshot(
        node("checkbox", "Seleccionar", "tabla"), node("checkbox", "Seleccionar", "tabla")
    )
    assert len(diffing.compute(before, after).changes) == 1


def test_al_menguar_no_se_pierde_ninguna_desaparicion() -> None:
    """De dos filas distintas queda una nueva: un cambio y una desaparicion, sin perder nada."""
    before = snapshot(
        node("listitem", "Fila", "tabla", value="uno"),
        node("listitem", "Fila", "tabla", value="dos"),
    )
    after = snapshot(node("listitem", "Fila", "tabla", value="tres"))
    result = diffing.compute(before, after)

    assert len(result.of_kind("changed")) == 1
    assert len(result.of_kind("disappeared")) == 1
    reportados = {c.before[0] for c in result.changes if c.before}
    assert reportados == {"uno", "dos"}, "ninguna de las dos filas puede quedar sin reportar"


def test_cambio_de_url_se_registra() -> None:
    before = snapshot(url="https://test.local/a")
    after = snapshot(url="https://test.local/b")
    assert diffing.compute(before, after).url_changed
