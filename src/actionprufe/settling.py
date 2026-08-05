"""Espera a que la pagina deje de moverse.

Sin esto no se puede distinguir "la accion no hizo nada" de "la accion aun no ha
hecho nada". Es la diferencia entre abortar una operacion buena y aceptar una mala.

Los dos bucles preguntan lo mismo —¿se ha movido algo?— y para eso les basta la huella
barata, que se calcula dentro de la pagina y solo devuelve una cadena. El `Snapshot`
completo se construye una sola vez, al final.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .snapshot import capture, probe
from .types import Snapshot

if TYPE_CHECKING:  # pragma: no cover - solo para tipado
    from playwright.async_api import Page

DEFAULT_QUIET_MS = 250
DEFAULT_TIMEOUT_MS = 5_000
POLL_MS = 50


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

    anterior = await probe(page)

    while loop.time() < deadline:
        await asyncio.sleep(interval)
        actual = await probe(page)
        if actual == anterior:
            estado = await capture(page, settled=True)
            # La captura es una lectura mas, y la pagina ha tenido su hueco para moverse
            # mientras se hacia. Sin volver a sondear despues, se devolveria como
            # asentado un estado que ya no lo esta, que es justo lo que evita este modulo.
            despues = await probe(page)
            if despues == actual:
                return estado
            anterior = despues
            continue
        anterior = actual

    return await capture(page, settled=False)


async def wait_for_effect(
    page: Page,
    baseline: str,
    *,
    quiet_ms: int = DEFAULT_QUIET_MS,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Snapshot:
    """Espera a que la accion surta efecto, y solo entonces a que la pagina se asiente.

    Esperar unicamente un periodo de quietud no vale despues de actuar: una pagina que
    todavia no ha empezado a reaccionar esta quieta, y se declararia "sin efecto" a los
    250 ms una respuesta de red que iba a llegar a los 700. Aqui la conclusion de que no
    paso nada exige haber agotado el tiempo entero.

    Args:
        page: pagina de Playwright a observar.
        baseline: huella del estado justo antes de actuar.
        quiet_ms: quietud exigida una vez detectado el primer movimiento.
        timeout_ms: tope total de espera.

    Returns:
        El `Snapshot` posterior a la accion.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_ms / 1000

    while loop.time() < deadline:
        if await probe(page) != baseline:
            restante_ms = max(int((deadline - loop.time()) * 1000), quiet_ms)
            return await wait_until_settled(page, quiet_ms=quiet_ms, timeout_ms=restante_ms)
        await asyncio.sleep(POLL_MS / 1000)

    # Se agoto el plazo sin que nada se moviera: aqui "no paso nada" ya es una
    # conclusion, no una lectura prematura.
    return await capture(page, settled=True)
