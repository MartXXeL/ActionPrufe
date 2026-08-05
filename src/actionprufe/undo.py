"""Deshacer una accion cuyo efecto no fue el pretendido.

El orden de las estrategias no es arbitrario: primero las inversas exactas (reescribir
el valor previo, volver a conmutar), luego las del navegador (volver atras) y solo al
final la busqueda de un control de retirada en la propia pagina. Si ninguna aplica se
lanza `IrreversibleAction` en vez de continuar: dejar la pagina sucia y seguir es
peor que parar.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from .errors import IrreversibleAction
from .snapshot import REDACTED
from .types import ActionSpec, Change, Diff, NodeKey

if TYPE_CHECKING:  # pragma: no cover - solo para tipado
    from playwright.async_api import Locator, Page

_REMOVAL_RE = re.compile(
    r"\b(quitar|eliminar|borrar|retirar|deseleccionar|descartar|cancelar|cerrar|deshacer|"
    r"remove|delete|discard|dismiss|clear|close|undo)\b|^[x×✕✖✗]$",
    re.IGNORECASE,
)

_PLAYWRIGHT_ROLES = frozenset(
    {
        "alert",
        "button",
        "cell",
        "checkbox",
        "columnheader",
        "combobox",
        "dialog",
        "heading",
        "img",
        "link",
        "listitem",
        "menuitem",
        "option",
        "radio",
        "row",
        "switch",
        "tab",
        "textbox",
    }
)


def _locator_for(page: Page, key: NodeKey) -> Locator:
    """Construye un localizador a partir de la identidad semantica de un nodo."""
    if key.role in _PLAYWRIGHT_ROLES and key.name:
        return page.get_by_role(key.role, name=key.name, exact=True).first  # type: ignore[arg-type]
    return page.get_by_text(key.name, exact=True).first


def _removal_control(diff: Diff) -> Change | None:
    """Busca entre lo que aparecio un control que sirva para retirar el efecto.

    Es la estrategia mas especulativa de todas y la unica que se apoya en texto que
    escribe la pagina, asi que se exige que el control **haya aparecido junto al efecto
    que dice retirar**: en su misma region y acompanado de algo mas. Sin esa condicion,
    una pagina hostil solo tiene que mostrar un boton llamado "Cancelar y confirmar la
    transferencia" tras la accion fallida para que se le pulse solo.
    """
    appeared = diff.of_kind("appeared")
    vecinos = Counter(change.key.region for change in appeared)
    for change in appeared:
        if change.key.role not in {"button", "link"}:
            continue
        if not _REMOVAL_RE.search(change.key.name):
            continue
        if vecinos[change.key.region] < 2:
            continue
        return change
    return None


async def revert(page: Page, spec: ActionSpec, diff: Diff, locator: Locator) -> str:
    """Intenta devolver la pagina al estado previo a la accion.

    Args:
        page: pagina sobre la que se actuo.
        spec: descripcion de la accion a deshacer, con el estado previo del objetivo.
        diff: efectos observados que hay que retirar.
        locator: el localizador original del objetivo.

    Returns:
        Una descripcion de la estrategia empleada.

    Raises:
        IrreversibleAction: si no se conoce ninguna inversa aplicable.
    """
    if spec.kind == "fill":
        if spec.target_value == REDACTED:
            # El valor previo nunca se leyo, asi que no hay nada que restaurar.
            # Reescribir el marcador dejaria el campo con la cadena "[redactado]"
            # dentro, que es peor que no tocarlo: parece deshecho y no lo esta.
            raise IrreversibleAction(
                f"no se puede restaurar {spec.target} porque su valor previo es sensible "
                f"y nunca se leyo; el campo queda como esta"
            )
        await locator.fill(spec.target_value or "")
        return f"se reescribio el valor previo {spec.target_value!r}"

    if spec.kind == "select" and spec.target_value:
        await locator.select_option(label=spec.target_value)
        return f"se restauro la opcion previa {spec.target_value!r}"

    if spec.kind in {"check", "uncheck"} or (
        spec.target is not None and spec.target.role in {"checkbox", "radio", "switch", "option"}
    ):
        await locator.click()
        return "se volvio a conmutar el objetivo"

    if spec.kind == "hover":
        # Apartar el raton es la inversa exacta de pasarlo por encima: el menu que se
        # desplego al entrar se repliega al salir, sin tocar nada mas.
        await page.mouse.move(0, 0)
        return "se aparto el raton del objetivo"

    control = _removal_control(diff)
    if control is not None:
        candidato = _locator_for(page, control.key)
        # `.first` sobre varias coincidencias es una moneda al aire, y el clic puede ser
        # irreversible: si el control no es univoco, no se pulsa nada.
        if await candidato.count() == 1:
            await candidato.click()
            return f"se uso el control de retirada {control.key}"

    if diff.url_changed:
        await page.go_back()
        return "se volvio atras en el historial"

    if spec.target_states & {"checked", "selected", "pressed"}:
        await locator.click()
        return "se volvio a conmutar el objetivo"

    raise IrreversibleAction(
        f"no hay inversa conocida para {spec.kind} sobre {spec.target}; "
        f"efectos sin deshacer:\n{diff.describe()}"
    )


def residue(original: Diff, current: Diff) -> Diff:
    """Lo que separa la pagina de como estaba antes de la accion equivocada.

    Deshacer bien significa volver al punto de partida, asi que se mira **toda** la
    diferencia contra el estado previo y no solo si desaparecieron los efectos que se
    querian retirar. La distincion importa con las inversas que se re-resuelven sobre la
    pagina viva: si entre la accion y el deshacer la lista se reordena, arrastrar de
    vuelta puede mover otro elemento y dejar la pagina en un tercer estado —ni el
    original ni el erroneo— sin que ninguna clave del efecto original siguiera presente.

    Args:
        original: los efectos que produjo la accion equivocada. Se conserva para saber
            si el cambio de URL formaba parte de lo que habia que deshacer.
        current: la diferencia entre el estado previo y el estado tras deshacer.

    Returns:
        Un `Diff` con lo que sigue sin cuadrar. Vacio significa que se volvio al origen.
    """
    return Diff(
        changes=current.changes,
        url_changed=current.url_changed,
        text_changed=False,
    )
