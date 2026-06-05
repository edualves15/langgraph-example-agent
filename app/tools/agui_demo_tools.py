"""Ferramentas de demonstração das capacidades do protocolo AG-UI.

- Estado compartilhado (`proverbs`): ferramentas que mutam o estado do grafo
  retornando `Command(update=...)`. A integração oficial emite os eventos
  `STATE_SNAPSHOT` / `STATE_DELTA` automaticamente a partir dessas mudanças.
- Human-in-the-loop: `send_email` usa `interrupt()` do LangGraph para pausar
  a execução e aguardar a decisão do usuário, retomada pelo cliente via resume.
"""

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command, interrupt


@tool
def add_proverb(
    proverb: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Append a proverb to the shared `proverbs` state list.

    Use this tool when the user asks to create, add, or invent a proverb.

    Input:
    - proverb: a short, original saying to append.

    Returns a confirmation message; the updated list is emitted to the UI as shared
    state.
    """
    proverbs = list(state.get("proverbs", []))
    proverbs.append(proverb)
    return Command(
        update={
            "proverbs": proverbs,
            "messages": [
                ToolMessage(
                    content=f'Provérbio adicionado. Agora há {len(proverbs)} provérbio(s).',
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


@tool
def set_proverbs(
    proverbs: list[str],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Replace the entire shared `proverbs` state list with the provided list.

    Use this tool when the user asks to reset, replace, or clear the proverbs (pass an
    empty list to clear).

    Input:
    - proverbs: the new list of proverbs (may be empty).

    Returns a confirmation message; the updated list is emitted to the UI as shared
    state.
    """
    return Command(
        update={
            "proverbs": proverbs,
            "messages": [
                ToolMessage(
                    content=f"Lista de provérbios definida com {len(proverbs)} item(ns).",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email. Requires human approval before sending (human-in-the-loop).

    Use this tool when the user asks to send an email. Draft the full email yourself
    (recipient, subject, body) from the request — do not stop to ask for details you
    can reasonably infer. Execution pauses automatically for the user to approve or
    reject; consider the email sent only after approval.

    Input:
    - to: recipient email address.
    - subject: the subject line.
    - body: the full email body.

    Returns a confirmation that the email was sent, or that the user cancelled it.
    """
    decision = interrupt(
        {
            "action": "send_email",
            "to": to,
            "subject": subject,
            "body": body,
            "question": f"Enviar este e-mail para {to}?",
        }
    )

    # O cliente pode retomar com um booleano ou com {"approved": bool}.
    if isinstance(decision, dict):
        approved = bool(decision.get("approved", False))
    else:
        approved = bool(decision)

    if approved:
        return f"E-mail enviado para {to} com o assunto '{subject}'."
    return f"Envio cancelado pelo usuário. O e-mail para {to} NÃO foi enviado."
