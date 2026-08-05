"""Pruebas contra paginas reales, incluidas las que se portan mal a proposito."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

from actionprufe import ActionPrufe, IrreversibleAction, VerificationFailed
from actionprufe.snapshot import REDACTED

pytestmark = pytest.mark.browser


async def test_tienda_honesta_no_produce_falsos_positivos(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """Lo primero que tiene que hacer bien: no inventarse fallos donde no los hay."""
    await page.goto(fixture_url("honest.html"))
    ap = ActionPrufe(page)

    result = await ap.click(page.get_by_role("button", name="Anadir Camiseta M"))

    assert result.ok
    assert result.attempts == 1
    assert result.undone == 0
    await page.get_by_role("listitem").filter(has_text="Camiseta M").first.wait_for()


async def test_fill_y_conmutacion_en_pagina_honesta(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    await page.goto(fixture_url("honest.html"))
    ap = ActionPrufe(page)

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
    ap = ActionPrufe(page)

    result = await ap.fill(page.get_by_label("Contrasena"), "hunter2-secreta")

    assert result.ok
    assert "hunter2-secreta" not in result.diff.describe()
    assert "hunter2-secreta" not in result.judgement.reason
    assert REDACTED in result.diff.describe()
    assert await page.get_by_label("Contrasena").input_value() == "hunter2-secreta"


async def test_un_campo_sin_marcar_se_protege_si_quien_llama_lo_declara(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """El caso que la deteccion automatica no puede cubrir.

    El campo es un `type=text` corriente: la pagina no dice en ninguna parte que ahi va
    un secreto, y no hay forma de adivinarlo. La palabra de quien llama basta.
    """
    await page.goto(fixture_url("honest.html"))
    ap = ActionPrufe(page)
    iban = "ES9121000418450200051332"

    result = await ap.fill(page.get_by_label("Numero de cuenta"), iban, sensitive=True)

    assert result.ok
    assert iban not in result.diff.describe()
    assert iban not in result.judgement.reason
    assert await page.get_by_label("Numero de cuenta").input_value() == iban


async def test_adjuntar_un_fichero_se_verifica(
    page: Page, fixture_url: Callable[[str], str], tmp_path: Path
) -> None:
    await page.goto(fixture_url("honest.html"))
    ap = ActionPrufe(page)
    justificante = tmp_path / "justificante-agosto.pdf"
    justificante.write_bytes(b"%PDF-1.4\n")

    result = await ap.upload(page.get_by_label("Justificante"), justificante)

    assert result.ok
    assert "justificante-agosto" in result.diff.describe()


async def test_arrastrar_una_tarea_se_verifica(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """Lo que se comprueba es que se movio *esa* tarea, no otra de la misma lista."""
    await page.goto(fixture_url("honest.html"))
    ap = ActionPrufe(page)

    result = await ap.drag_to(
        page.get_by_text("Revisar el pedido de Martxel"),
        page.locator("#hechas"),
        intent="la tarea pasa a la lista de hechas",
    )

    assert result.ok
    assert await page.locator("#hechas li").count() == 1


async def test_el_hover_que_despliega_un_menu_se_verifica(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """Un menu que no se despliega es un fallo silencioso: el hover nunca da error."""
    await page.goto(fixture_url("honest.html"))
    ap = ActionPrufe(page)

    result = await ap.hover(
        page.get_by_role("button", name="Mas opciones"),
        intent="se despliega el menu con el historial y las facturas",
    )

    assert result.ok
    assert "historial" in result.diff.describe().lower()


async def test_el_efecto_tardio_no_se_toma_por_ausencia_de_efecto(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """El efecto llega 700 ms despues; sin estabilizacion seria un falso negativo."""
    await page.goto(fixture_url("late.html"))
    ap = ActionPrufe(page)

    result = await ap.click(page.get_by_role("button", name="Reservar Bilbao Madrid"))

    assert result.ok
    assert "Bilbao" in result.diff.describe()


async def test_lista_virtualizada_el_clic_acaba_en_el_vecino(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """El caso que justifica la libreria entera.

    Playwright clica sin error y el carrito acaba con otro producto. ActionPrufe
    lo detecta, lo deshace con el control de retirada de la propia pagina y, al
    ver que se repite, aborta en vez de dar la accion por buena.
    """
    await page.goto(fixture_url("virtualized.html"))
    ap = ActionPrufe(page, max_attempts=2)

    with pytest.raises(VerificationFailed) as error:
        await ap.click(page.get_by_role("button", name="Anadir Camiseta M"))

    assert "no al objetivo" in str(error.value)
    assert await page.locator("#carrito li").count() == 0, "el carrito debio quedar limpio"


async def test_el_reproductor_que_tapa_el_boton_falla_de_forma_limpia(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """La frontera con Playwright: lo que ya cubre el, se propaga tal cual.

    Un elemento tapado lo detecta la comprobacion de accionabilidad de Playwright, que
    reintenta y acaba lanzando. Lo que se fija aqui es que ese error sale a la superficie
    y no se convierte en un veredicto inventado ni deja la pagina tocada.
    """
    await page.goto(fixture_url("overlay.html"))
    page.set_default_timeout(1_500)
    ap = ActionPrufe(page)

    with pytest.raises(PlaywrightTimeout):
        await ap.click(page.get_by_role("button", name="Reservar Bilbao Madrid"))

    assert await page.locator("#reservas li").count() == 0


async def test_confirmacion_intermedia_en_dos_pasos(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """Una operacion destructiva no ocurre al primer clic, y eso no es un fallo."""
    await page.goto(fixture_url("confirm.html"))
    ap = ActionPrufe(page)

    abrir = await ap.click(page.get_by_role("button", name="Eliminar la cuenta de Martxel"))

    assert abrir.ok, "abrir el dialogo es el efecto correcto de ese clic"
    assert await page.get_by_role("dialog").is_visible()

    # "Confirmar borrado" no se parece a "Cuenta eliminada" y ningun vecino explica el
    # efecto, asi que sin declarar la intencion esto se queda en ambiguo.
    confirmar = await ap.click(
        page.get_by_role("button", name="Confirmar borrado"),
        intent="la cuenta queda eliminada",
    )

    assert confirmar.ok
    assert await page.get_by_text("Cuenta eliminada").is_visible()


async def test_sin_intencion_el_borrado_confirmado_aborta_y_lo_dice(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """Lo peor que puede pasar, dicho en voz alta.

    Sin intencion declarada el efecto no se puede atribuir, y la politica por defecto es
    no aprobarlo. Pero es que ademas un borrado confirmado no tiene inversa: no hay valor
    previo que reescribir, ni control de retirada, ni historial al que volver. Se lanza
    `IrreversibleAction` encadenada al fallo de verificacion, que es exactamente lo que
    quien llama necesita saber: la pagina cambio, no se pudo comprobar y no se puede
    deshacer.
    """
    await page.goto(fixture_url("confirm.html"))
    ap = ActionPrufe(page, max_attempts=1)

    await ap.click(page.get_by_role("button", name="Eliminar la cuenta de Martxel"))

    with pytest.raises(IrreversibleAction) as error:
        await ap.click(page.get_by_role("button", name="Confirmar borrado"))

    causa = error.value.__cause__
    assert isinstance(causa, VerificationFailed)
    assert "ambiguo rechazado por politica" in str(causa)


async def test_sin_verificar_el_fallo_pasa_desapercibido(
    page: Page, fixture_url: Callable[[str], str]
) -> None:
    """La contraprueba: con Playwright a secas, el mismo clic no da ningun error."""
    await page.goto(fixture_url("virtualized.html"))

    await page.get_by_role("button", name="Anadir Camiseta M").click()

    en_carrito = await page.locator("#carrito li").first.inner_text()
    assert "Camiseta M" not in en_carrito, "la pagina de prueba debe fallar de verdad"
