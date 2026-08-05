"""ActionPrufe: comprueba que cada accion de navegador hizo lo que pretendia.

Uso minimo:

    from playwright.async_api import async_playwright
    from actionprufe import ActionPrufe

    async with async_playwright() as pw:
        page = await (await pw.chromium.launch()).new_page()
        await page.goto("https://ejemplo.test/tienda")

        ap = ActionPrufe(page)
        await ap.click(page.get_by_role("button", name="Anadir Camiseta M"))

Si el clic acaba anadiendo otra cosa —porque la lista se reciclo, porque el nodo se
movio o porque la pagina hizo algo inesperado—, ActionPrufe lo detecta, lo deshace y
reintenta; y si no puede deshacerlo, aborta en vez de seguir.
"""

from .ai_judge import AIJudge, GeminiJudge, build_prompt, read_verdict
from .errors import ActionPrufeError, IrreversibleAction, UndoFailed, VerificationFailed
from .types import (
    ActionSpec,
    Change,
    Diff,
    Judgement,
    Node,
    NodeKey,
    Result,
    Snapshot,
    Verdict,
)
from .verifier import ActionPrufe

__all__ = [
    "AIJudge",
    "ActionPrufe",
    "ActionPrufeError",
    "ActionSpec",
    "Change",
    "Diff",
    "GeminiJudge",
    "IrreversibleAction",
    "Judgement",
    "Node",
    "NodeKey",
    "Result",
    "Snapshot",
    "UndoFailed",
    "Verdict",
    "VerificationFailed",
    "build_prompt",
    "read_verdict",
]

__version__ = "0.1.0"
