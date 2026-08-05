"""La API publica: acciones de Playwright que se verifican a si mismas.

El ciclo de cada accion es siempre el mismo:

    estabilizar -> leer objetivo -> actuar -> estabilizar -> diferenciar -> juzgar
                                                                              |
                            match <---------------------------------------- veredicto
                                                                              |
                                          deshacer y reintentar <--------- mismatch

Si no se puede deshacer, se aborta. Nunca se sigue operando sobre un estado que ya
no es el que se creia.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Literal

from . import diff as diffing
from . import undo
from .ai_judge import AIJudge
from .errors import ActionProofError, UndoFailed, VerificationFailed
from .judge import judge
from .settling import DEFAULT_QUIET_MS, DEFAULT_TIMEOUT_MS, wait_for_effect, wait_until_settled
from .snapshot import describe_element, fingerprint
from .types import ActionSpec, Diff, Judgement, Result, Snapshot, Verdict

if TYPE_CHECKING:  # pragma: no cover - solo para tipado
    from collections.abc import Awaitable, Callable

    from playwright.async_api import Locator, Page

AmbiguousPolicy = Literal["reject", "accept"]


class ActionProof:
    """Envuelve una pagina de Playwright y verifica el efecto de cada accion."""

    def __init__(
        self,
        page: Page,
        *,
        ai_judge: AIJudge | None = None,
        ambiguous: AmbiguousPolicy = "reject",
        max_attempts: int = 2,
        quiet_ms: int = DEFAULT_QUIET_MS,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        """Configura la verificacion.

        Args:
            page: pagina de Playwright sobre la que se va a operar.
            ai_judge: arbitro opcional para los casos ambiguos. Sin el, `ambiguous`
                decide.
            ambiguous: que hacer con un caso que no se puede resolver — `reject` lo
                trata como fallo (por defecto, y lo correcto si hay algo en juego),
                `accept` lo da por bueno.
            max_attempts: intentos totales por accion, deshaciendo entre uno y otro.
            quiet_ms: milisegundos de quietud para dar la pagina por estabilizada.
            timeout_ms: tope de espera de estabilizacion.
        """
        self._page = page
        self._ai = ai_judge
        self._ambiguous = ambiguous
        self._max_attempts = max(1, max_attempts)
        self._quiet_ms = quiet_ms
        self._timeout_ms = timeout_ms

    async def click(self, target: Locator, *, intent: str | None = None) -> Result:
        """Hace clic y comprueba que el efecto corresponde a ese elemento."""
        return await self._run("click", target, intent=intent, act=target.click)

    async def check(self, target: Locator, *, intent: str | None = None) -> Result:
        """Marca una casilla y comprueba que quedo marcada esa y solo esa."""
        return await self._run("check", target, intent=intent, act=target.check)

    async def uncheck(self, target: Locator, *, intent: str | None = None) -> Result:
        """Desmarca una casilla y comprueba que quedo desmarcada esa y solo esa."""
        return await self._run("uncheck", target, intent=intent, act=target.uncheck)

    async def fill(self, target: Locator, value: str, *, intent: str | None = None) -> Result:
        """Escribe un valor y comprueba que acabo en ese campo."""

        async def act() -> None:
            await target.fill(value)

        return await self._run("fill", target, intent=intent, act=act, payload=value)

    async def select_option(
        self, target: Locator, label: str, *, intent: str | None = None
    ) -> Result:
        """Selecciona una opcion por su etiqueta y comprueba que es la elegida."""

        async def act() -> None:
            await target.select_option(label=label)

        return await self._run("select", target, intent=intent, act=act, payload=label)

    async def settle(self) -> Snapshot:
        """Espera a que la pagina deje de moverse y devuelve su estado."""
        return await wait_until_settled(
            self._page, quiet_ms=self._quiet_ms, timeout_ms=self._timeout_ms
        )

    async def _describe_target(
        self, target: Locator, kind: str, payload: str | None, intent: str | None
    ) -> ActionSpec:
        """Lee la identidad del objetivo *antes* de tocarlo."""
        node = await describe_element(target)
        return ActionSpec(
            kind=kind,
            target=node.key,
            target_states=node.states,
            target_value=node.value,
            payload=payload,
            intent=intent,
        )

    async def _adjudicate(self, spec: ActionSpec, changes: Diff, judgement: Judgement) -> Judgement:
        """Resuelve un veredicto ambiguo: primero la IA, si no la politica configurada."""
        if judgement.verdict is not Verdict.AMBIGUOUS:
            return judgement
        if self._ai is not None:
            return await self._ai.adjudicate(spec, changes)
        if self._ambiguous == "accept":
            return Judgement(Verdict.MATCH, f"ambiguo aceptado por politica: {judgement.reason}")
        return Judgement(Verdict.MISMATCH, f"ambiguo rechazado por politica: {judgement.reason}")

    async def _revert(
        self, spec: ActionSpec, changes: Diff, target: Locator, before: Snapshot
    ) -> None:
        """Deshace el efecto y comprueba que de verdad se retiro."""
        await undo.revert(self._page, spec, changes, target)
        after_undo = await self.settle()
        left = undo.residue(changes, diffing.compute(before, after_undo))
        if left.changes or left.url_changed:
            raise UndoFailed(
                f"se intento deshacer pero quedan efectos sin retirar:\n{left.describe()}",
                left,
            )

    async def _run(
        self,
        kind: str,
        target: Locator,
        *,
        intent: str | None,
        act: Callable[[], Awaitable[None]],
        payload: str | None = None,
    ) -> Result:
        """Ejecuta el ciclo completo de una accion verificada."""
        before = await self.settle()
        spec = await self._describe_target(target, kind, payload, intent)
        undone = 0

        for attempt in range(1, self._max_attempts + 1):
            baseline = fingerprint(before)
            await act()
            after = await wait_for_effect(
                self._page, baseline, quiet_ms=self._quiet_ms, timeout_ms=self._timeout_ms
            )
            changes = diffing.compute(before, after)
            verdict = judge(spec, changes, before, after)
            verdict = await self._adjudicate(spec, changes, verdict)

            if verdict.verdict is Verdict.MATCH:
                return Result(
                    spec=spec, judgement=verdict, diff=changes, attempts=attempt, undone=undone
                )

            if attempt == self._max_attempts:
                # Se agotaron los intentos, pero el efecto equivocado sigue ahi: se
                # retira igualmente antes de rendirse, para no dejar la pagina sucia.
                failure = VerificationFailed(verdict, changes, attempt)
                try:
                    await self._revert(spec, changes, target, before)
                except ActionProofError as undo_error:
                    raise undo_error from failure
                raise failure

            await self._revert(spec, changes, target, before)
            undone += 1  # noqa: SIM113 - no es el indice del bucle: solo cuenta los deshechos
            before = await self.settle()
            # El objetivo puede haber mutado al deshacer: se relee antes de reintentar.
            node = await describe_element(target)
            spec = replace(
                spec, target=node.key, target_states=node.states, target_value=node.value
            )

        raise AssertionError("inalcanzable")  # pragma: no cover
