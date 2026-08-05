"""Captura del estado semantico de la pagina.

No se guarda el DOM: se guarda lo que un humano percibiria — que elementos hay, como
se llaman, en que region viven y en que estado estan. Eso es lo unico estable cuando
el framework recicla nodos por debajo.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from playwright.async_api import Error as PlaywrightError

from .types import REDACTED, Node, NodeKey, Snapshot

__all__ = ["EVAL_TIMEOUT_S", "REDACTED", "capture", "describe_element", "probe"]

EVAL_TIMEOUT_S = 10.0
"""Tope de cada evaluacion en la pagina.

El script se ejecuta en el contexto de la pagina, que es de un tercero y puede haber
sustituido las funciones nativas de las que dependen los ayudantes. Sin tope, una de
esas funciones colgada bloquea la accion entera y el `timeout_ms` configurado no llega
a aplicarse nunca, porque su reloj solo avanza entre evaluaciones.
"""

if TYPE_CHECKING:  # pragma: no cover - solo para tipado
    from playwright.async_api import Frame, Locator, Page

_HELPERS_JS = (
    r"""
  const REDACTED = '"""
    + REDACTED
    + r"""';
  const NAME_MAX = 140;
  const SENSITIVE_AUTOCOMPLETE =
    /(^|\s)(current-password|new-password|one-time-code|cc-number|cc-csc|cc-exp|cc-name)(\s|$)/i;

  function sensitive(el) {
    if (el.hasAttribute('data-ap-sensitive')) return true;
    if (el.tagName === 'INPUT' && (el.getAttribute('type') || '').toLowerCase() === 'password') {
      return true;
    }
    return SENSITIVE_AUTOCOMPLETE.test(el.getAttribute('autocomplete') || '');
  }
"""
)

_HELPERS_JS += r"""
  const LANDMARKS = new Set(['nav', 'main', 'header', 'footer', 'aside', 'form',
                             'section', 'dialog', 'table']);
  const LANDMARK_ROLES = new Set(['navigation', 'main', 'banner', 'contentinfo',
                                  'complementary', 'form', 'region', 'dialog',
                                  'table', 'list']);
  const INPUT_ROLES = { checkbox: 'checkbox', radio: 'radio', submit: 'button',
                        button: 'button', reset: 'button' };

  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().slice(0, NAME_MAX);

  function visible(el) {
    if (!el.getClientRects().length) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0';
  }

  function roleOf(el) {
    // norm() tambien aqui: el rol lo escribe la pagina y un atributo de varios MB en
    // miles de nodos se convierte en clave de diccionario y se rehashea en cada sondeo.
    const explicit = norm(el.getAttribute('role'));
    if (explicit) return explicit.toLowerCase();
    const tag = el.tagName.toLowerCase();
    switch (tag) {
      case 'a': return el.hasAttribute('href') ? 'link' : null;
      case 'button': return 'button';
      case 'select': return 'combobox';
      case 'option': return 'option';
      case 'textarea': return 'textbox';
      case 'li': return 'listitem';
      // El texto corrido tambien es estado observable. Un dialogo suele llevar
      // aria-label ("Confirmacion") y toda la informacion util —que se va a borrar,
      // cuanto se va a cobrar— vive en su parrafo. Sin esto se descarta justo lo que
      // permite atribuir el efecto a la accion.
      case 'p': return 'paragraph';
      case 'td': return 'cell';
      case 'th': return 'columnheader';
      case 'summary': return 'button';
      case 'img': return 'img';
      case 'input': {
        const t = (el.getAttribute('type') || 'text').toLowerCase();
        if (t === 'hidden') return null;
        return INPUT_ROLES[t] || 'textbox';
      }
      default:
        if (/^h[1-6]$/.test(tag)) return 'heading';
        if (el.hasAttribute('data-ap-watch')) return 'watched';
        return null;
    }
  }

  function nameOf(el) {
    const aria = el.getAttribute('aria-label');
    if (aria) return norm(aria);
    const by = el.getAttribute('aria-labelledby');
    if (by) {
      const t = by.split(/\s+/)
        .map((id) => { const n = document.getElementById(id); return n ? n.textContent : ''; })
        .join(' ');
      if (norm(t)) return norm(t);
    }
    if (el.labels && el.labels.length) {
      const t = norm(Array.from(el.labels).map((l) => l.textContent).join(' '));
      if (t) return t;
    }
    if (el.tagName === 'IMG') return norm(el.getAttribute('alt'));
    const own = norm(el.innerText || el.textContent);
    if (own) return own;
    const fallback = norm(el.getAttribute('title') || el.getAttribute('placeholder'));
    if (fallback) return fallback;
    // Ultimo recurso: el propio valor. Solo si el campo no es sensible, porque este
    // texto viaja a los logs y al arbitro de IA.
    if (sensitive(el)) return '';
    return norm(el.value);
  }

  // Todo lo que compone una region y sale de la pagina se limpia de los separadores
  // que la propia gramatica usa. Sin esto, un `id` llamado "pendientes/lista:hechas"
  // fabrica una region que no le corresponde y se hace pasar por otra.
  function limpiar(s) {
    return norm(s).replace(/[\/:]/g, '-');
  }

  // El padre de la raiz de un shadow tree no es un elemento: es el host, y hay que
  // saltar a el o la region de todo lo que vive dentro de un componente se pierde.
  function parentOf(el) {
    if (el.parentElement) return el.parentElement;
    const root = el.getRootNode();
    return root && root.host ? root.host : null;
  }

  // PREFIJO lo calcula Python a partir del marco real que da Playwright, no la pagina.
  // Antes se deducia aqui de `window.name`, que lo escribe quien pone el <iframe>: dos
  // marcos podian declararse el mismo y sus nodos se confundian entre si.
  function regionOf(el) {
    // La lista mas cercana se anota como sufijo en vez de cortar la busqueda. Asi
    // mover un elemento de una lista a otra dentro del mismo area se ve como lo que
    // es —un cambio— sin que la lista se coma la region que declaro el autor.
    let lista = '';
    let p = parentOf(el);
    while (p && p !== document.documentElement) {
      const tag = p.tagName.toLowerCase();
      if (!lista && (tag === 'ul' || tag === 'ol')) {
        const suya = limpiar(p.getAttribute('aria-label') || p.getAttribute('id') || '');
        if (suya) lista = '/lista:' + suya;
      }
      const marked = p.getAttribute('data-ap-region');
      if (marked) return PREFIJO + limpiar(marked) + lista;
      const role = limpiar(p.getAttribute('role') || '').toLowerCase();
      if (LANDMARKS.has(tag) || LANDMARK_ROLES.has(role)) {
        const label = limpiar(p.getAttribute('aria-label') || '');
        const base = role || tag;
        return PREFIJO + (label ? base + ':' + label : base) + lista;
      }
      p = parentOf(p);
    }
    return PREFIJO + 'document' + lista;
  }

  function statesOf(el) {
    const st = [];
    if (el.checked === true) st.push('checked');
    if (el.selected === true) st.push('selected');
    if (el.disabled === true) st.push('disabled');
    if (el.hasAttribute('aria-checked') && el.getAttribute('aria-checked') !== 'false') {
      st.push('checked');
    }
    if (el.getAttribute('aria-selected') === 'true') st.push('selected');
    if (el.getAttribute('aria-pressed') === 'true') st.push('pressed');
    if (el.getAttribute('aria-expanded') === 'true') st.push('expanded');
    if (el.getAttribute('aria-disabled') === 'true') st.push('disabled');
    if (el.hasAttribute('data-ap-state')) {
      st.push.apply(st, norm(el.getAttribute('data-ap-state')).split(/\s+/).slice(0, 16));
    }
    return Array.from(new Set(st.filter(Boolean))).sort();
  }

  function valueOf(el) {
    if (el.tagName === 'SELECT') {
      const opt = el.selectedOptions && el.selectedOptions[0];
      return opt ? norm(opt.textContent) : '';
    }
    if ('value' in el && typeof el.value === 'string') {
      if (!sensitive(el)) return norm(el.value);
      // Se conserva la distincion entre vacio y con contenido: basta para saber que el
      // campo cambio, y es todo lo que se necesita saber.
      return el.value ? REDACTED : '';
    }
    return null;
  }

  function describe(el) {
    return {
      role: roleOf(el) || 'generic',
      name: nameOf(el),
      region: regionOf(el),
      value: valueOf(el),
      states: statesOf(el),
      sensitive: sensitive(el),
    };
  }
"""

_COLLECT_JS = (
    "(PREFIJO) => {\n"
    + _HELPERS_JS
    + r"""
  const LIMIT = 4000;
  const nodes = [];

  // querySelectorAll no atraviesa los shadow roots, y detras de ellos vive buena parte
  // de la web moderna: sin esto, un componente entero es invisible y cualquier accion
  // sobre el se declara "sin efecto".
  function* recorrer(raiz) {
    for (const el of raiz.querySelectorAll('*')) {
      yield el;
      if (el.shadowRoot) yield* recorrer(el.shadowRoot);
    }
  }

  const all = document.body ? recorrer(document.body) : [];
  for (const el of all) {
    if (nodes.length >= LIMIT) break;
    const role = roleOf(el);
    if (!role) continue;
    if (role !== 'option' && !visible(el)) continue;
    const name = nameOf(el);
    const value = valueOf(el);
    if (!name && value === null) continue;
    nodes.push({
      role, name, region: regionOf(el), value,
      states: statesOf(el), sensitive: sensitive(el),
    });
  }

  const text = (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').trim();
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = ((h * 33) ^ text.charCodeAt(i)) >>> 0;

  return { url: location.href, nodes, textDigest: String(h) + ':' + text.length };
}
"""
)

_DESCRIBE_JS = "(el, PREFIJO) => {\n" + _HELPERS_JS + "\n  return describe(el);\n}"

# Solo la huella, sin construir ni enviar la lista de nodos. Los bucles de espera
# preguntan «¿se ha movido algo?» cada 50 ms, y responder a eso serializando cuatro mil
# nodos por sondeo es lo que convierte una pagina grande en una espera insoportable.
_FINGERPRINT_JS = (
    "(PREFIJO) => {\n"
    + _HELPERS_JS
    + r"""
  const LIMIT = 4000;
  function* recorrer(raiz) {
    for (const el of raiz.querySelectorAll('*')) {
      yield el;
      if (el.shadowRoot) yield* recorrer(el.shadowRoot);
    }
  }

  let h = 5381;
  let vistos = 0;
  function mezclar(s) {
    for (let i = 0; i < s.length; i++) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0;
  }

  if (document.body) {
    for (const el of recorrer(document.body)) {
      if (vistos >= LIMIT) break;
      const role = roleOf(el);
      if (!role) continue;
      if (role !== 'option' && !visible(el)) continue;
      const name = nameOf(el);
      const value = valueOf(el);
      if (!name && value === null) continue;
      vistos++;
      mezclar(role); mezclar('\x1f'); mezclar(name); mezclar('\x1f');
      mezclar(regionOf(el)); mezclar('\x1f'); mezclar(String(value)); mezclar('\x1f');
      mezclar(statesOf(el).join(','));
    }
  }

  const text = (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').trim();
  mezclar(String(text.length));
  mezclar(text);
  return String(h) + ':' + vistos;
}
"""
)


_log = logging.getLogger(__name__)

MAX_FRAMES = 40
"""Tope de marcos que se recorren.

Una pagina puede abrir cientos de `iframe` y cada uno cuesta una evaluacion en cada
sondeo. El tope convierte un abuso en una observacion incompleta —que se nota— en vez
de en una espera que no termina.
"""


def _frame_prefix(page: Page, frame: Frame) -> str:
    """Prefijo de region de un marco, atado a algo que la pagina no elige.

    El nombre del marco lo escribe quien pone la etiqueta `<iframe>`, asi que dos marcos
    pueden declararse el mismo y sus nodos acabarian confundiendose. La posicion que les
    da Playwright, en cambio, es unica por marco: se antepone al nombre para que la
    region siga siendo legible sin ser falsificable.
    """
    if frame is page.main_frame:
        return ""
    try:
        posicion = page.frames.index(frame)
    except ValueError:  # pragma: no cover - el marco se fue entre medias
        posicion = -1
    etiqueta = _clean(frame.name) or "iframe"
    return f"marco{posicion}:{etiqueta}/"


def _clean(text: str | None) -> str:
    """Quita los separadores que la gramatica de region usa para estructurar."""
    if not text:
        return ""
    return " ".join(text.replace("/", "-").replace(":", "-").split())[:140]


def _node_from(raw: dict[str, Any]) -> Node:
    """Convierte un elemento crudo del navegador en un `Node`."""
    return Node(
        key=NodeKey(role=raw["role"], name=raw["name"], region=raw["region"]),
        value=raw["value"],
        states=frozenset(raw["states"]),
        sensitive=bool(raw.get("sensitive")),
    )


async def capture(
    page: Page, *, settled: bool = True, timeout_s: float = EVAL_TIMEOUT_S
) -> Snapshot:
    """Captura el estado semantico actual de la pagina, marcos incluidos.

    Un `iframe` es una pagina aparte y su contenido no aparece al evaluar en el marco
    principal. Sin recorrerlos, cualquier accion dentro de un pasarela de pago, de un
    reproductor o de un formulario incrustado se declara sin efecto.

    Args:
        page: pagina de Playwright de la que leer el estado.
        settled: si la pagina se considera estabilizada en el momento de capturar.
        timeout_s: tope de la evaluacion en cada marco.

    Returns:
        El `Snapshot` correspondiente.

    Raises:
        TimeoutError: si algun marco no devuelve el estado a tiempo.
    """
    nodes: list[Node] = []
    digests: list[str] = []

    for frame in page.frames[:MAX_FRAMES]:
        try:
            raw: dict[str, Any] = await asyncio.wait_for(
                frame.evaluate(_COLLECT_JS, _frame_prefix(page, frame)), timeout=timeout_s
            )
        except PlaywrightError as error:
            # Los marcos se destruyen y se recrean solos mientras se navega, y los de
            # otro origen pueden negarse a ejecutar. Ninguna de las dos cosas es motivo
            # para tirar la observacion del resto de la pagina. Cualquier otro error
            # —una respuesta con forma inesperada, por ejemplo— si sube: taparlo seria
            # confundir una pagina manipulada con un marco que se fue.
            # Se registra igualmente: si esto pasa siempre, todo se juzga «sin efecto» y
            # sin rastro seria indistinguible de que la accion no hiciera nada.
            _log.debug("marco omitido al capturar (%s): %s", frame.url, error)
            continue
        nodes.extend(_node_from(n) for n in raw["nodes"])
        digests.append(raw["textDigest"])

    return Snapshot(
        url=page.url,
        nodes=tuple(nodes),
        text_digest="|".join(digests),
        settled=settled,
    )


async def describe_element(locator: Locator, *, timeout_s: float = EVAL_TIMEOUT_S) -> Node:
    """Lee la identidad y el estado de un elemento concreto, antes de actuar sobre el.

    Args:
        locator: localizador de Playwright que debe resolver a un unico elemento.
        timeout_s: tope de la evaluacion en la pagina.

    Returns:
        El `Node` que representa a ese elemento en el momento de la lectura.

    Raises:
        TimeoutError: si la pagina no devuelve el estado a tiempo.
    """
    # El prefijo tiene que salir del mismo sitio que en el barrido, o el objetivo de una
    # accion dentro de un iframe no coincidiria jamas con lo observado y todo saldria
    # ambiguo. El marco se le pregunta al propio elemento, no se adivina.
    prefijo = ""
    handle = await locator.element_handle()
    if handle is not None:
        frame = await handle.owner_frame()
        if frame is not None:
            prefijo = _frame_prefix(locator.page, frame)

    raw: dict[str, Any] = await asyncio.wait_for(
        locator.evaluate(_DESCRIBE_JS, prefijo), timeout=timeout_s
    )
    return _node_from(raw)


async def probe(page: Page, *, timeout_s: float = EVAL_TIMEOUT_S) -> str:
    """Huella barata del estado, para saber si *algo* se movio.

    No sirve para diferenciar —para eso hace falta el `Snapshot` entero—, sino para
    responder a la unica pregunta de los bucles de espera. El calculo se hace dentro de
    la pagina y solo cruza una cadena, en vez de la lista completa de nodos.

    Args:
        page: pagina a sondear.
        timeout_s: tope de la evaluacion en cada marco.

    Returns:
        Una cadena que cambia si cambia cualquier cosa observable.
    """
    huellas: list[str] = []
    for frame in page.frames[:MAX_FRAMES]:
        try:
            huellas.append(
                await asyncio.wait_for(
                    frame.evaluate(_FINGERPRINT_JS, _frame_prefix(page, frame)), timeout_s
                )
            )
        except PlaywrightError as error:  # un marco que se va no invalida el sondeo
            _log.debug("marco omitido al sondear (%s): %s", frame.url, error)
            continue
    return "|".join(huellas)
