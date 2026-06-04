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
def request_approval(action: str) -> str:
    """Solicita aprovação humana antes de executar uma ação sensível.

    Use SEMPRE que o usuário pedir para realizar uma ação que exija confirmação
    explícita (ex.: enviar um e-mail, apagar dados, confirmar uma compra). A
    execução do agente é pausada (human-in-the-loop) até o usuário aprovar ou
    rejeitar; só prossiga com a ação após a aprovação.
    """
    decision = interrupt(
        {
            "action": action,
            "question": f"Você aprova a seguinte ação? {action}",
        }
    )

    # O cliente pode retomar com um booleano ou com {"approved": bool}.
    if isinstance(decision, dict):
        approved = bool(decision.get("approved", False))
    else:
        approved = bool(decision)

    if approved:
        return f"Ação APROVADA pelo usuário: {action}. Pode prosseguir."
    return f"Ação REJEITADA pelo usuário: {action}. Não execute."
