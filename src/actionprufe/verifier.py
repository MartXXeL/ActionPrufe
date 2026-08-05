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
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from . import diff as diffing
from . import tracing, undo
from .ai_judge import AIJudge
from .errors import ActionPrufeError, UndoFailed, VerificationFailed
from .judge import judge
from .settling import DEFAULT_QUIET_MS, DEFAULT_TIMEOUT_MS, wait_for_effect, wait_until_settled
from .snapshot import describe_element, probe
from .types import ActionSpec, Diff, Judgement, Result, Snapshot, Verdict

if TYPE_CHECKING:  # pragma: no cover - solo para tipado
    from collections.abc import Awaitable, Callable

    from playwright.async_api import Locator, Page

AmbiguousPolicy = Literal["reject", "accept"]


class ActionPrufe:
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
        trace_dir: str | Path | None = None,
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
            trace_dir: carpeta donde volcar un JSON por accion. Sirve para reconstruir
                despues una sesion entera y ver en que paso empezo a torcerse. Lo que se
                escribe pasa por la misma redaccion que todo lo demas.
        """
        self._page = page
        self._ai = ai_judge
        self._ambiguous = ambiguous
        self._max_attempts = max(1, max_attempts)
        self._quiet_ms = quiet_ms
        self._timeout_ms = timeout_ms
        self._trace_dir = Path(trace_dir) if trace_dir is not None else None
        self._traced = 0

    async def click(self, target: Locator, *, intent: str | None = None) -> Result:
        """Hace clic y comprueba que el efecto corresponde a ese elemento."""
        return await self._run("click", target, intent=intent, act=target.click)

    async def check(self, target: Locator, *, intent: str | None = None) -> Result:
        """Marca una casilla y comprueba que quedo marcada esa y solo esa."""
        return await self._run("check", target, intent=intent, act=target.check)

    async def uncheck(self, target: Locator, *, intent: str | None = None) -> Result:
        """Desmarca una casilla y comprueba que quedo desmarcada esa y solo esa."""
        return await self._run("uncheck", target, intent=intent, act=target.uncheck)

    async def fill(
        self, target: Locator, value: str, *, intent: str | None = None, sensitive: bool = False
    ) -> Result:
        """Escribe un valor y comprueba que acabo en ese campo.

        Args:
            target: campo sobre el que escribir.
            value: texto a escribir.
            intent: intencion declarada, opcional.
            sensitive: fuerza el trato de secreto aunque la pagina no lo declare. La
                deteccion automatica se apoya en `type=password`, en `autocomplete` y en
                `data-ap-sensitive`, que los escribe la propia pagina; un campo de tarjeta
                sin marcar o una cuenta bancaria en un `type=text` no se detectan solos.
                Si lo que escribes es un secreto, dilo aqui y no confies en la pagina.
        """

        async def act() -> None:
            await target.fill(value)

        return await self._run(
            "fill", target, intent=intent, act=act, payload=value, sensitive=sensitive
        )

    async def select_option(
        self, target: Locator, label: str, *, intent: str | None = None, sensitive: bool = False
    ) -> Result:
        """Selecciona una opcion por su etiqueta y comprueba que es la elegida."""

        async def act() -> None:
            await target.select_option(label=label)

        return await self._run(
            "select", target, intent=intent, act=act, payload=label, sensitive=sensitive
        )

    async def press(self, target: Locator, key: str, *, intent: str | None = None) -> Result:
        """Pulsa una tecla sobre un elemento y comprueba el efecto.

        Es la accion de los formularios que se envian con Enter, donde el efecto casi
        nunca lleva el nombre del campo: suele hacer falta declarar la intencion.
        """

        async def act() -> None:
            await target.press(key)

        return await self._run("press", target, intent=intent, act=act, payload=key)

    async def hover(self, target: Locator, *, intent: str | None = None) -> Result:
        """Pasa el raton por encima y comprueba que aparecio lo que tenia que aparecer.

        Un menu que no se despliega es un fallo silencioso de manual: el `hover` no da
        error nunca, y el clic siguiente falla en otro sitio y por otro motivo.
        """

        async def act() -> None:
            await target.hover()

        return await self._run("hover", target, intent=intent, act=act)

    async def upload(
        self, target: Locator, path: str | Path, *, intent: str | None = None
    ) -> Result:
        """Adjunta un fichero y comprueba que quedo en ese campo."""
        fichero = Path(path)

        async def act() -> None:
            await target.set_input_files(fichero)

        async def inverse() -> None:
            await target.set_input_files([])

        return await self._run(
            "upload", target, intent=intent, act=act, payload=fichero.name, inverse=inverse
        )

    async def drag_to(
        self, source: Locator, destination: Locator, *, intent: str | None = None
    ) -> Result:
        """Arrastra un elemento a otro sitio y comprueba que acabo donde debia.

        La inversa es arrastrarlo de vuelta, que es exacta y no depende de que la pagina
        ofrezca ningun control. El objetivo que se verifica es el elemento arrastrado:
        lo que importa es que sea *ese* el que se movio, no otro de la misma lista.
        """

        async def act() -> None:
            await source.drag_to(destination)

        async def inverse() -> None:
            await destination.drag_to(source)

        return await self._run("drag", source, intent=intent, act=act, inverse=inverse)

    async def settle(self) -> Snapshot:
        """Espera a que la pagina deje de moverse y devuelve su estado."""
        return await wait_until_settled(
            self._page, quiet_ms=self._quiet_ms, timeout_ms=self._timeout_ms
        )

    def _trace(self, spec: ActionSpec, verdict: Judgement, changes: Diff, attempt: int) -> None:
        """Vuelca la accion a disco, si se configuro una carpeta de trazas."""
        if self._trace_dir is None:
            return
        self._traced += 1
        tracing.write(
            self._trace_dir, self._traced, tracing.build_record(spec, verdict, changes, attempt)
        )

    async def _describe_target(
        self,
        target: Locator,
        kind: str,
        payload: str | None,
        intent: str | None,
        sensitive: bool = False,
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
            # Se suman las dos fuentes y nunca se restan: lo que diga la pagina puede
            # anadir sensibilidad, jamas quitarla. La pagina es de un tercero y no puede
            # tener la ultima palabra sobre si un secreto de quien llama se publica.
            sensitive=sensitive or node.sensitive,
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
        self,
        spec: ActionSpec,
        changes: Diff,
        target: Locator,
        before: Snapshot,
        inverse: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Deshace el efecto y comprueba que de verdad se retiro.

        Una inversa declarada por la propia accion siempre gana a las heuristicas de
        `undo`: arrastrar de vuelta o vaciar el adjunto es exacto, y no depende de que
        la pagina ofrezca ningun control ni de adivinar nada por el texto.
        """
        if inverse is not None:
            await inverse()
        else:
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
        sensitive: bool = False,
        inverse: Callable[[], Awaitable[None]] | None = None,
    ) -> Result:
        """Ejecuta el ciclo completo de una accion verificada."""
        before = await self.settle()
        spec = await self._describe_target(target, kind, payload, intent, sensitive)
        undone = 0

        for attempt in range(1, self._max_attempts + 1):
            baseline = await probe(self._page)
            await act()
            after = await wait_for_effect(
                self._page, baseline, quiet_ms=self._quiet_ms, timeout_ms=self._timeout_ms
            )
            changes = diffing.compute(before, after)
            if spec.sensitive:
                # Se tapa antes de juzgar, no despues: asi ni el veredicto, ni el motivo,
                # ni el prompt, ni el Result que se devuelve llegan a ver el valor.
                changes = diffing.redact(changes, spec.target)
            verdict = judge(spec, changes, before, after)
            verdict = await self._adjudicate(spec, changes, verdict)
            self._trace(spec, verdict, changes, attempt)

            if verdict.verdict is Verdict.MATCH:
                return Result(
                    spec=spec, judgement=verdict, diff=changes, attempts=attempt, undone=undone
                )

            if attempt == self._max_attempts:
                # Se agotaron los intentos, pero el efecto equivocado sigue ahi: se
                # retira igualmente antes de rendirse, para no dejar la pagina sucia.
                failure = VerificationFailed(verdict, changes, attempt, spec)
                try:
                    await self._revert(spec, changes, target, before, inverse)
                except ActionPrufeError as undo_error:
                    raise undo_error from failure
                raise failure

            await self._revert(spec, changes, target, before, inverse)
            undone += 1  # noqa: SIM113 - no es el indice del bucle: solo cuenta los deshechos
            before = await self.settle()
            # El objetivo puede haber mutado al deshacer: se relee antes de reintentar.
            node = await describe_element(target)
            spec = replace(
                spec,
                target=node.key,
                target_states=node.states,
                target_value=node.value,
                sensitive=spec.sensitive or node.sensitive,
            )

        raise AssertionError("inalcanzable")  # pragma: no cover
