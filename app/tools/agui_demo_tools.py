"""Ferramentas de demonstração das capacidades do protocolo AG-UI.

- Estado compartilhado (`proverbs`): ferramentas que mutam o estado do grafo
  retornando `Command(update=...)`. A integração oficial emite os eventos
  `STATE_SNAPSHOT` / `STATE_DELTA` automaticamente a partir dessas mudanças.
- Human-in-the-loop: `request_approval` usa `interrupt()` do LangGraph para pausar
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
    """Adiciona um provérbio à lista de provérbios do estado compartilhado.

    Use quando o usuário pedir para criar, adicionar ou inventar um provérbio.
    O provérbio deve ser uma frase curta e original.
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
    """Substitui toda a lista de provérbios do estado compartilhado pela lista fornecida.

    Use quando o usuário pedir para redefinir, substituir ou limpar os provérbios
    (passe uma lista vazia para limpar).
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
    """Envia um e-mail. EXIGE aprovação humana antes do envio (human-in-the-loop).

    Use quando o usuário pedir para enviar um e-mail. Monte você mesmo um rascunho
    completo (destinatário, assunto e corpo) com base no pedido — não interrompa
    para perguntar detalhes que você consegue inferir. A execução do agente é
    pausada automaticamente para o usuário aprovar ou rejeitar o envio; só
    considere o e-mail enviado após a aprovação.
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
