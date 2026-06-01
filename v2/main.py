import asyncio
import json
import os
import sys
import unicodedata
from typing import Annotated, TypedDict
import operator

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from langgraph.types import StreamWriter

load_dotenv()

from v2.tools import (
    ALL_TOOLS,
    TOOLS_BY_NAME,
    format_narration_label,
    get_tool_narration,
)
from v2.narration import NarrationAdapter, render_event


# =========================================================
# Encoding — tenta UTF-8 no terminal; fallback ASCII com
# transliteracao de acentos (ex: "c" -> "c", "a" -> "a").
# =========================================================

def _setup_encoding() -> None:
    """Reconfigura stdout para UTF-8 se possivel (Windows cp1252 -> 65001)."""
    if sys.platform != "win32":
        return
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            return
        except Exception:
            pass
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass


_setup_encoding()


def _asciify(text: str) -> str:
    """Remove acentos preservando legibilidade: "informacao" -> "informacao"."""
    if not text:
        return text
    try:
        text.encode(sys.stdout.encoding)
        return text
    except (UnicodeEncodeError, LookupError):
        pass
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _safe_print(*args, **kwargs) -> None:
    """print() resiliente a qualquer encoding de terminal."""
    cleaned = [_asciify(a) if isinstance(a, str) else a for a in args]
    try:
        print(*cleaned, **kwargs)
    except UnicodeEncodeError:
        ascii_args = [
            a.encode("ascii", errors="replace").decode("ascii") if isinstance(a, str) else a
            for a in cleaned
        ]
        print(*ascii_args, **kwargs)


# =========================================================
# Estado
# =========================================================

class State(TypedDict):
    messages: Annotated[list, operator.add]


# =========================================================
# LLM
# =========================================================

llm = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0,
)

llm_with_tools = llm.bind_tools(ALL_TOOLS)


# =========================================================
# Helpers
# =========================================================

def _serialize_tool_result(result) -> str:
    """Converte resultado de tool para string (para ToolMessage.content)."""
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False, default=str)
    return str(result)


# =========================================================
# Nos do grafo
# =========================================================

async def agent_node(state: State, writer: StreamWriter) -> dict:
    """Chama o LLM e gera narracao semantica em duas fases.

    Fase 1 — Reasoning: emitida DURANTE a chamada LLM (futuro front-end
             usa para spinner/indicador de "pensando...").
    Fase 2 — Tool calls: anunciadas APOS a resposta, com labels descritivos
             baseados no que o LLM decidiu fazer.
    """

    # --- Fase 1: Reasoning (durante a chamada LLM) ---
    has_tool_results = any(isinstance(m, ToolMessage) for m in state["messages"])
    reasoning_text = (
        "Analisando resultados..." if has_tool_results
        else "Analisando sua pergunta..."
    )
    writer({
        "type": "narration",
        "event": "reasoning_started",
        "text": reasoning_text,
        "icon": "💭",
        "level": 1,
    })

    response = await llm_with_tools.ainvoke(state["messages"])

    tool_calls = getattr(response, "tool_calls", [])

    # --- Fase 2: Reasoning concluido ---
    writer({"type": "narration", "event": "reasoning_end", "level": 1})

    # --- Fase 3: Anuncia cada tool call ---

    for tc in tool_calls:
        meta = get_tool_narration(TOOLS_BY_NAME.get(tc["name"]))
        writer({
            "type": "narration",
            "event": "tool_call",
            "tool_name": tc["name"],
            "tool_call_id": tc["id"],
            "text": format_narration_label(meta, tc),
            "icon": meta.icon,
            "args": tc.get("args", {}),
            "level": meta.level,
        })

    return {"messages": [response]}


async def tool_node(state: State, writer: StreamWriter) -> dict:
    """Executa as tool calls e emite eventos de conclusao ou erro."""
    last_message = state["messages"][-1]
    outputs = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_call_id = tool_call["id"]
        tool = TOOLS_BY_NAME[tool_name]
        meta = get_tool_narration(tool)

        try:
            result = await tool.ainvoke(tool_call["args"])
            writer({
                "type": "narration",
                "event": "tool_result",
                "tool": tool_name,
                "tool_call_id": tool_call_id,
                "text": meta.done_label or f"{tool_name} concluido",
                "icon": meta.icon,
            })
        except Exception as exc:
            result = f"Erro: {exc}"
            writer({
                "type": "narration",
                "event": "tool_error",
                "tool": tool_name,
                "tool_call_id": tool_call_id,
                "text": meta.error_label or f"{tool_name} falhou",
                "icon": meta.icon,
                "error": str(exc),
            })

        outputs.append(
            ToolMessage(
                content=_serialize_tool_result(result),
                name=tool_name,
                tool_call_id=tool_call_id,
            )
        )

    return {"messages": outputs}


def should_continue(state: State) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


# =========================================================
# Grafo
# =========================================================

builder = StateGraph(State)
builder.add_node("agent", agent_node)
builder.add_node("tools", tool_node)
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
builder.add_edge("tools", "agent")

graph = builder.compile()


# =========================================================
# Execucao
# =========================================================

async def run(message: str) -> None:
    """Executa o grafo com narracao rica de status para o terminal."""
    initial_state = {"messages": [HumanMessage(content=message)]}

    async for item in NarrationAdapter(
        graph.astream(initial_state, stream_mode=["custom", "messages"])
    ):
        if isinstance(item, str):
            # Streaming de tokens da resposta final
            _safe_print(item, end="", flush=True)
        else:
            # Evento canonico de narracao
            render_event(item)


# =========================================================
# Entrada
# =========================================================

if __name__ == "__main__":
    asyncio.run(
        run(
            "Preciso planejar um projeto que comeca hoje e termina em 15 de dezembro de 2026. "
            "Me ajude com o seguinte:\n\n"
            "1. Quantos dias uteis temos entre hoje e o prazo final? "
            "Desconte os feriados bancarios brasileiros que caem nesse periodo. "
            "Considere que trabalhamos de segunda a sexta.\n\n"
            "2. Se dividirmos o projeto em 4 fases iguais em dias uteis, "
            "qual a data final de cada fase? "
            "Calcule uma a uma a partir de hoje.\n\n"
            "3. A data final (15/12/2026) cai em qual dia da semana? "
            "Se for final de semana ou feriado, qual o dia util imediatamente anterior?\n\n"
            "4. Quantas segundas-feiras teremos nesse periodo? "
            "Isso importa porque nossas reunioes de alinhamento sao sempre as segundas.\n\n"
            "5. Considerando que a equipe tem 5 pessoas e cada uma entrega "
            "exatamente 3 pontos de historia por dia util, "
            "quantos pontos no total a equipe consegue entregar nesse periodo? "
            "Calcule os pontos totais usando a ferramenta de matematica.\n\n"
            "6. Qual foi o dia da semana em que eu nasci, em 15 de agosto de 1990?"
        )
    )
