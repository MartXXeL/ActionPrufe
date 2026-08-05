"""Arbitro de IA para los casos que el juicio deterministico deja ambiguos.

Dos reglas que no se negocian:

1. **Solo se llama en `AMBIGUOUS`.** Si el diff ya demuestra el fallo o el acierto, no
   se gasta una llamada ni se le da al modelo la oportunidad de contradecir la evidencia.
2. **La respuesta es binaria.** El modelo contesta SI o NO. Cualquier otra cosa —un
   "podria", una respuesta vacia, un error de red— se lee como NO. Ante la duda, la
   accion no se da por buena.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .types import ActionSpec, Diff, Judgement, Verdict

if TYPE_CHECKING:  # pragma: no cover - solo para tipado
    from collections.abc import Callable

_PROMPT = """Eres un verificador de automatizacion web. No razonas en voz alta.

Se ejecuto esta accion sobre una pagina:
  accion: {kind}
  elemento objetivo: {target}
  {payload_line}intencion declarada: {intent}

Estos son TODOS los cambios observados en la pagina tras la accion:
{diff}

Pregunta unica: ¿los cambios observados son exactamente el efecto que se pretendia,
sin efectos adicionales que contradigan la intencion?

Responde con una sola palabra, SI o NO. Si la informacion no basta para afirmarlo,
responde NO."""


@runtime_checkable
class AIJudge(Protocol):
    """Contrato de cualquier arbitro externo."""

    async def adjudicate(self, spec: ActionSpec, diff: Diff) -> Judgement:
        """Resuelve un caso ambiguo con veredicto binario."""
        ...


def build_prompt(spec: ActionSpec, diff: Diff) -> str:
    """Construye el prompt del arbitro. Publico para poder probarlo sin red."""
    payload_line = f"valor o opcion: {spec.payload!r}\n  " if spec.payload else ""
    return _PROMPT.format(
        kind=spec.kind,
        target=spec.target or "desconocido",
        payload_line=payload_line,
        intent=spec.intent or "(no declarada)",
        diff=diff.describe(),
    )


def read_verdict(answer: str | None) -> bool:
    """Interpreta la respuesta del modelo. Todo lo que no sea un SI limpio es NO."""
    if not answer:
        return False
    cleaned = answer.strip().strip(".,;:!¡¿?\"'").upper()
    return cleaned in {"SI", "SÍ", "YES"}


class GeminiJudge:
    """Arbitro apoyado en Gemini. Requiere el extra `ai` (`google-genai`)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-2.5-flash",
        serializer: Callable[[ActionSpec, Diff], str] = build_prompt,
    ) -> None:
        from google import genai  # importacion diferida: la libreria es opcional

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._serialize = serializer

    async def adjudicate(self, spec: ActionSpec, diff: Diff) -> Judgement:
        """Pregunta al modelo y devuelve un veredicto que nunca es ambiguo."""
        prompt = self._serialize(spec, diff)
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model, contents=prompt
            )
            approved = read_verdict(getattr(response, "text", None))
        except Exception as exc:  # noqa: BLE001 - cualquier fallo se lee como "no"
            return Judgement(
                Verdict.MISMATCH,
                f"el arbitro de IA no pudo responder ({exc.__class__.__name__}), se asume fallo",
                escalated=True,
            )

        if approved:
            return Judgement(Verdict.MATCH, "el arbitro de IA confirmo el efecto", escalated=True)
        return Judgement(Verdict.MISMATCH, "el arbitro de IA no confirmo el efecto", escalated=True)
