"""Espera a que la pagina deje de moverse.

Sin esto no se puede distinguir "la accion no hizo nada" de "la accion aun no ha
hecho nada". Es la diferencia entre abortar una operacion buena y aceptar una mala.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .snapshot import capture, fingerprint
from .types import Snapshot

if TYPE_CHECKING:  # pragma: no cover - solo para tipado
    from playwright.async_api import Page

DEFAULT_QUIET_MS = 250
DEFAULT_TIMEOUT_MS = 5_000


async def wait_until_settled(
    page: Page,
    *,
    quiet_ms: int = DEFAULT_QUIET_MS,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Snapshot:
    """Captura el estado cuando la pagina lleva `quiet_ms` sin cambiar.

    Args:
        page: pagina de Playwright a observar.
        quiet_ms: milisegundos de quietud exigidos para dar el estado por bueno.
        timeout_ms: tope total de espera.

    Returns:
        El `Snapshot` final. Su campo `settled` es False si se agoto el tiempo con
        la pagina todavia mutando; en ese caso el veredicto posterior no debe tratar
        un diff vacio como "no paso nada".
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_ms / 1000
    interval = max(quiet_ms / 1000, 0.02)

    previous = await capture(page, settled=False)
    previous_print = fingerprint(previous)

    while loop.time() < deadline:
        await asyncio.sleep(interval)
        current = await capture(page, settled=False)
        current_print = fingerprint(current)
        if current_print == previous_print:
            return Snapshot(
                url=current.url,
                nodes=current.nodes,
                text_digest=current.text_digest,
                settled=True,
            )
        previous, previous_print = current, current_print

    return previous
