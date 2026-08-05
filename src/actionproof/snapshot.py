"""Captura del estado semantico de la pagina.

No se guarda el DOM: se guarda lo que un humano percibiria — que elementos hay, como
se llaman, en que region viven y en que estado estan. Eso es lo unico estable cuando
el framework recicla nodos por debajo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .types import Node, NodeKey, Snapshot

if TYPE_CHECKING:  # pragma: no cover - solo para tipado
    from playwright.async_api import Locator, Page

_HELPERS_JS = r"""
  const NAME_MAX = 140;
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
    const explicit = el.getAttribute('role');
    if (explicit) return explicit.trim().toLowerCase();
    const tag = el.tagName.toLowerCase();
    switch (tag) {
      case 'a': return el.hasAttribute('href') ? 'link' : null;
      case 'button': return 'button';
      case 'select': return 'combobox';
      case 'option': return 'option';
      case 'textarea': return 'textbox';
      case 'li': return 'listitem';
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
    return norm(el.getAttribute('title') || el.getAttribute('placeholder') || el.value);
  }

  function regionOf(el) {
    let p = el.parentElement;
    while (p && p !== document.documentElement) {
      const marked = p.getAttribute('data-ap-region');
      if (marked) return norm(marked);
      const tag = p.tagName.toLowerCase();
      const role = (p.getAttribute('role') || '').toLowerCase();
      if (LANDMARKS.has(tag) || LANDMARK_ROLES.has(role)) {
        const label = norm(p.getAttribute('aria-label') || '');
        const base = role || tag;
        return label ? base + ':' + label : base;
      }
      p = p.parentElement;
    }
    return 'document';
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
      st.push.apply(st, el.getAttribute('data-ap-state').split(/\s+/));
    }
    return Array.from(new Set(st.filter(Boolean))).sort();
  }

  function valueOf(el) {
    if (el.tagName === 'SELECT') {
      const opt = el.selectedOptions && el.selectedOptions[0];
      return opt ? norm(opt.textContent) : '';
    }
    if ('value' in el && typeof el.value === 'string') return norm(el.value);
    return null;
  }

  function describe(el) {
    return {
      role: roleOf(el) || 'generic',
      name: nameOf(el),
      region: regionOf(el),
      value: valueOf(el),
      states: statesOf(el),
    };
  }
"""

_COLLECT_JS = (
    "() => {\n"
    + _HELPERS_JS
    + r"""
  const LIMIT = 4000;
  const nodes = [];
  const all = document.body ? document.body.querySelectorAll('*') : [];
  for (const el of all) {
    if (nodes.length >= LIMIT) break;
    const role = roleOf(el);
    if (!role) continue;
    if (role !== 'option' && !visible(el)) continue;
    const name = nameOf(el);
    const value = valueOf(el);
    if (!name && value === null) continue;
    nodes.push({ role, name, region: regionOf(el), value, states: statesOf(el) });
  }

  const text = (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').trim();
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = ((h * 33) ^ text.charCodeAt(i)) >>> 0;

  return { url: location.href, nodes, textDigest: String(h) + ':' + text.length };
}
"""
)

_DESCRIBE_JS = "(el) => {\n" + _HELPERS_JS + "\n  return describe(el);\n}"


def _node_from(raw: dict[str, Any]) -> Node:
    """Convierte un elemento crudo del navegador en un `Node`."""
    return Node(
        key=NodeKey(role=raw["role"], name=raw["name"], region=raw["region"]),
        value=raw["value"],
        states=frozenset(raw["states"]),
    )


async def capture(page: Page, *, settled: bool = True) -> Snapshot:
    """Captura el estado semantico actual de la pagina.

    Args:
        page: pagina de Playwright de la que leer el estado.
        settled: si la pagina se considera estabilizada en el momento de capturar.

    Returns:
        El `Snapshot` correspondiente.
    """
    raw: dict[str, Any] = await page.evaluate(_COLLECT_JS)
    return Snapshot(
        url=raw["url"],
        nodes=tuple(_node_from(n) for n in raw["nodes"]),
        text_digest=raw["textDigest"],
        settled=settled,
    )


async def describe_element(locator: Locator) -> Node:
    """Lee la identidad y el estado de un elemento concreto, antes de actuar sobre el.

    Args:
        locator: localizador de Playwright que debe resolver a un unico elemento.

    Returns:
        El `Node` que representa a ese elemento en el momento de la lectura.
    """
    raw: dict[str, Any] = await locator.evaluate(_DESCRIBE_JS)
    return _node_from(raw)


def fingerprint(snapshot: Snapshot) -> tuple[str, str, int]:
    """Huella barata para detectar si la pagina sigue mutando.

    No sirve para diferenciar: sirve para saber si *algo* se movio entre dos lecturas.
    """
    joined = "|".join(
        f"{n.key.role}\x1f{n.key.name}\x1f{n.key.region}\x1f{n.value}\x1f{','.join(sorted(n.states))}"
        for n in snapshot.nodes
    )
    digest = 5381
    for ch in joined:
        digest = ((digest * 33) ^ ord(ch)) & 0xFFFFFFFF
    return (snapshot.text_digest, str(digest), len(snapshot.nodes))
