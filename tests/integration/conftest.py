"""Navegador real para las pruebas de integracion."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from playwright.async_api import Browser, Page, async_playwright

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def browser() -> AsyncIterator[Browser]:
    """Un unico Chromium para toda la sesion.

    `loop_scope` tiene que acompanar a `scope`: si el fixture vive toda la sesion
    pero el bucle de eventos se recrea por prueba, la segunda prueba se queda
    esperando sobre una conexion que pertenece a un bucle ya cerrado.
    """
    async with async_playwright() as pw:
        instance = await pw.chromium.launch()
        yield instance
        await instance.close()


@pytest_asyncio.fixture(loop_scope="session")
async def page(browser: Browser) -> AsyncIterator[Page]:
    """Una pestana limpia por prueba."""
    context = await browser.new_context()
    yield await context.new_page()
    await context.close()


@pytest.fixture
def fixture_url() -> Callable[[str], str]:
    """Devuelve la URL `file://` de una pagina de prueba."""

    def build(name: str) -> str:
        return (FIXTURES / name).as_uri()

    return build
