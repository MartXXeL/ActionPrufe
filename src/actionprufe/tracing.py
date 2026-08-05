"""Volcado a disco de cada accion verificada.

Sirve para lo que el informe de una excepcion no alcanza: reconstruir despues una
sesion entera, ver en que paso empezo a torcerse y comparar dos ejecuciones.

Dos reglas. La primera, que **una traza nunca puede tumbar la operacion**: si el disco
esta lleno o la ruta no existe, se pierde el registro, no la accion. La segunda, que lo
que se escribe pasa por la misma redaccion que todo lo demas — un fichero en disco es
tan publicable como un log.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .types import REDACTED, ActionSpec, Diff, Judgement

if TYPE_CHECKING:  # pragma: no cover - solo para tipado
    from pathlib import Path

_log = logging.getLogger(__name__)


def build_record(
    spec: ActionSpec,
    judgement: Judgement,
    diff: Diff,
    attempt: int,
) -> dict[str, Any]:
    """Construye el registro de una accion, ya redactado."""
    return {
        "momento": datetime.now(UTC).isoformat(timespec="seconds"),
        "accion": spec.kind,
        "objetivo": {
            "rol": spec.target.role if spec.target else None,
            "nombre": spec.target.name if spec.target else None,
            "region": spec.target.region if spec.target else None,
        },
        "valor": REDACTED if spec.sensitive else spec.payload,
        "intencion": spec.intent,
        "intento": attempt,
        "veredicto": judgement.verdict.value,
        "motivo": judgement.reason,
        "desempatado_por_ia": judgement.escalated,
        "url_cambio": diff.url_changed,
        "cambios": [
            {
                "tipo": cambio.kind,
                "rol": cambio.key.role,
                "nombre": cambio.key.name,
                "region": cambio.key.region,
                "antes": cambio.before[0] if cambio.before else None,
                "despues": cambio.after[0] if cambio.after else None,
            }
            for cambio in diff.changes
        ],
    }


def write(directory: Path, orden: int, record: dict[str, Any]) -> Path | None:
    """Escribe un registro. Devuelve la ruta, o None si no se pudo y hubo que seguir.

    Args:
        directory: carpeta donde volcar. Se crea si no existe.
        orden: numero de la accion dentro de la sesion, para que el listado ordene solo.
        record: el registro ya construido y redactado.

    Returns:
        La ruta escrita, o None si fallo.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        destino = directory / f"{orden:04d}-{record['accion']}-{record['veredicto']}.json"
        destino.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as error:
        # Se pierde el registro, no la accion: quien esta verificando una operacion real
        # no puede quedarse sin ella porque no quepa un fichero de diagnostico.
        _log.warning("no se pudo escribir la traza en %s: %s", directory, error)
        return None
    return destino
