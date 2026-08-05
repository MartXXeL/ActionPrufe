"""ActionProof: comprueba que cada accion de navegador hizo lo que pretendia.

Uso minimo:

    from playwright.async_api import async_playwright
    from actionproof import ActionProof

    async with async_playwright() as pw:
        page = await (await pw.chromium.launch()).new_page()
        await page.goto("https://ejemplo.test/tienda")

        ap = ActionProof(page)
        await ap.click(page.get_by_role("button", name="Anadir Camiseta M"))

Si el clic acaba anadiendo otra cosa —porque la lista se reciclo, porque el nodo se
movio o porque la pagina hizo algo inesperado—, ActionProof lo detecta, lo deshace y
reintenta; y si no puede deshacerlo, aborta en vez de seguir.
"""

from .ai_judge import AIJudge, GeminiJudge, build_prompt, read_verdict
from .errors import ActionProofError, IrreversibleAction, UndoFailed, VerificationFailed
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
from .verifier import ActionProof

__all__ = [
    "AIJudge",
    "ActionProof",
    "ActionProofError",
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
