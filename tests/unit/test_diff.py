from conftest import node, snapshot

from actionproof import diff as diffing


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
    assert len(diffing.compute(before, after).of_kind("appeared")) == 1


def test_cambio_de_url_se_registra() -> None:
    before = snapshot(url="https://test.local/a")
    after = snapshot(url="https://test.local/b")
    assert diffing.compute(before, after).url_changed
