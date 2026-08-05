"""Comparacion de textos para atribuir un efecto a un elemento.

Deliberadamente simple y deterministica: solapamiento de tokens significativos. La IA
solo entra cuando esto no decide, no antes.
"""

from __future__ import annotations

import re
import unicodedata

_STOPWORDS = frozenset(
    {
        "a",
        "al",
        "de",
        "del",
        "la",
        "las",
        "el",
        "los",
        "un",
        "una",
        "unos",
        "unas",
        "y",
        "o",
        "en",
        "con",
        "por",
        "para",
        "que",
        "se",
        "su",
        "sus",
        "lo",
        "es",
        "the",
        "an",
        "of",
        "to",
        "in",
        "on",
        "for",
        "and",
        "or",
        "is",
        "it",
        "boton",
        "button",
        "link",
        "enlace",
    }
)

_TOKEN_RE = re.compile(r"[0-9a-z]+")


def normalize(text: str | None) -> str:
    """Minusculas, sin acentos y con los espacios colapsados."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.lower().split())


MIN_ANCHOR_LEN = 3
"""Longitud a partir de la cual un token basta por si solo para relacionar dos textos."""


def tokens(text: str | None) -> frozenset[str]:
    """Tokens significativos de un texto, sin palabras vacias.

    Se conservan los tokens de una sola letra o cifra: en la practica son tallas,
    cantidades y numeros de asiento, justo lo que distingue una opcion de su vecina.
    """
    return frozenset(t for t in _TOKEN_RE.findall(normalize(text)) if t not in _STOPWORDS)


def overlap(reference: str | None, candidate: str | None) -> float:
    """Fraccion de los tokens de `reference` presentes en `candidate`.

    Returns:
        Un valor entre 0.0 y 1.0. Si `reference` no tiene tokens significativos,
        devuelve 0.0 en vez de fingir certeza.
    """
    ref = tokens(reference)
    if not ref:
        return 0.0
    return len(ref & tokens(candidate)) / len(ref)


def relates(left: str | None, right: str | None) -> float:
    """Cuanto se relacionan dos textos, sin importar cual es mas largo.

    El solapamiento direccional castiga a las etiquetas con verbo: el boton se llama
    "Anadir Camiseta M" y lo que aparece en el carrito es "Camiseta M", asi que medir
    solo cuanto del boton esta en el efecto da 2/3 y se queda corto. Aqui se toma la
    mejor de las dos direcciones.

    Para evitar falsos positivos, se exige que la coincidencia se apoye en al menos un
    token de `MIN_ANCHOR_LEN` caracteres: compartir solo la talla "m" no relaciona nada.

    Returns:
        Un valor entre 0.0 y 1.0.
    """
    shared = tokens(left) & tokens(right)
    if not any(len(t) >= MIN_ANCHOR_LEN for t in shared):
        return 0.0
    return max(overlap(left, right), overlap(right, left))
