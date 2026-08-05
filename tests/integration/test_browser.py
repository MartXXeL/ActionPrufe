"""Pruebas contra paginas reales, incluidas las que se portan mal a proposito."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from playwright.async_api import Page

from actionproof import ActionProof, VerificationFailed
from actionproof.snapshot import REDACTED

pytestmark = pytest.mark.browser


async def test_tienda_honesta_no_produce_falsos_positivos(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """Lo primero que tiene que hacer bien: no inventarse fallos donde no los hay."""
    await page.goto(fixture_url("honest.html"))
    ap = ActionProof(page)

    result = await ap.click(page.get_by_role("button", name="Anadir Camiseta M"))

    assert result.ok
    assert result.attempts == 1
    assert result.undone == 0
    await page.get_by_role("listitem").filter(has_text="Camiseta M").first.wait_for()


async def test_fill_y_conmutacion_en_pagina_honesta(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    await page.goto(fixture_url("honest.html"))
    ap = ActionProof(page)

    assert (await ap.fill(page.get_by_label("Cupon"), "VERANO25")).ok
    assert (await ap.check(page.get_by_label("Acepto las condiciones"))).ok
    assert (await ap.select_option(page.get_by_label("Envio"), "Urgente")).ok

    assert await page.get_by_label("Cupon").input_value() == "VERANO25"
    assert await page.get_by_label("Quiero el boletin").is_checked() is False


async def test_una_contrasena_real_no_sale_de_la_pagina(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """Contra un navegador de verdad: el valor se verifica sin llegar a leerse."""
    await page.goto(fixture_url("honest.html"))
    ap = ActionProof(page)

    result = await ap.fill(page.get_by_label("Contrasena"), "hunter2-secreta")

    assert result.ok
    assert "hunter2-secreta" not in result.diff.describe()
    assert "hunter2-secreta" not in result.judgement.reason
    assert REDACTED in result.diff.describe()
    assert await page.get_by_label("Contrasena").input_value() == "hunter2-secreta"


async def test_el_efecto_tardio_no_se_toma_por_ausencia_de_efecto(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """El efecto llega 700 ms despues; sin estabilizacion seria un falso negativo."""
    await page.goto(fixture_url("late.html"))
    ap = ActionProof(page)

    result = await ap.click(page.get_by_role("button", name="Reservar Bilbao Madrid"))

    assert result.ok
    assert "Bilbao" in result.diff.describe()


async def test_lista_virtualizada_el_clic_acaba_en_el_vecino(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """El caso que justifica la libreria entera.

    Playwright clica sin error y el carrito acaba con otro producto. ActionProof
    lo detecta, lo deshace con el control de retirada de la propia pagina y, al
    ver que se repite, aborta en vez de dar la accion por buena.
    """
    await page.goto(fixture_url("virtualized.html"))
    ap = ActionProof(page, max_attempts=2)

    with pytest.raises(VerificationFailed) as error:
        await ap.click(page.get_by_role("button", name="Anadir Camiseta M"))

    assert "no al objetivo" in str(error.value)
    assert await page.locator("#carrito li").count() == 0, "el carrito debio quedar limpio"


async def test_sin_verificar_el_fallo_pasa_desapercibido(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """La contraprueba: con Playwright a secas, el mismo clic no da ningun error."""
    await page.goto(fixture_url("virtualized.html"))

    await page.get_by_role("button", name="Anadir Camiseta M").click()

    en_carrito = await page.locator("#carrito li").first.inner_text()
    assert "Camiseta M" not in en_carrito, "la pagina de prueba debe fallar de verdad"
