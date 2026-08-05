"""Demostracion en 30 segundos: el mismo clic, con y sin verificacion.

    python examples/demo.py

Abre la pagina de prueba que recicla los nodos de su lista —el fallo real que se ve en
cualquier web hecha con React cuando la lista se redibuja entre que localizas un boton y
lo pulsas— y hace exactamente el mismo clic dos veces:

1. Con Playwright a secas. No hay error. El carrito acaba con otro producto.
2. Con ActionPrufe. Se detecta, se deshace y se aborta explicando por que.

No hace falta clave de ninguna API: el veredicto de este caso sale del diff, sin IA.
"""

from __future__ import annotations

import asyncio
import pathlib

from playwright.async_api import Page, async_playwright

from actionprufe import ActionPrufe, ActionPrufeError, VerificationFailed

PAGINA = (
    pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "virtualized.html"
).as_uri()
BOTON = "Anadir Camiseta M"


def titulo(texto: str) -> None:
    """Escribe un separador legible."""
    print(f"\n{'-' * 70}\n{texto}\n{'-' * 70}")


async def carrito(page: Page) -> list[str]:
    """Lo que hay ahora mismo en el carrito, en texto."""
    return [t.strip() for t in await page.locator("#carrito li").all_inner_texts()]


async def main() -> None:
    """Ejecuta las dos versiones del mismo clic."""
    async with async_playwright() as pw:
        navegador = await pw.chromium.launch()

        titulo("1. Playwright a secas")
        page = await (await navegador.new_context()).new_page()
        await page.goto(PAGINA)
        print(f"Pido:      pulsar «{BOTON}»")
        await page.get_by_role("button", name=BOTON).click()
        print("Resultado: el clic no da ningun error")
        print(f"Carrito:   {await carrito(page)}")
        print("           <- nadie se entera de que esto esta mal")

        titulo("2. Con ActionPrufe")
        page = await (await navegador.new_context()).new_page()
        await page.goto(PAGINA)
        ap = ActionPrufe(page, max_attempts=2)
        print(f"Pido:      pulsar «{BOTON}»")
        try:
            await ap.click(page.get_by_role("button", name=BOTON))
        except ActionPrufeError as error:
            print(f"Resultado: {type(error).__name__}")
            informe = error.explain() if isinstance(error, VerificationFailed) else str(error)
            print("\n".join(f"           {linea}" for linea in informe.splitlines()))
        else:  # pragma: no cover - solo si la pagina de prueba dejara de fallar
            print("Resultado: correcto (la pagina de prueba ya no falla)")
        print(f"Carrito:   {await carrito(page)}")
        print("           <- se deshizo lo que se metio mal, y se paro a tiempo")

        await navegador.close()
        print()


if __name__ == "__main__":
    asyncio.run(main())
