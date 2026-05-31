from typing import TypedDict, Annotated
import operator
import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END

load_dotenv()

# Importa a tool externa
from tools.math_tools import calculate_math_expression


# =========================================================
# 1. Definir estado
# =========================================================

# Define o formato do estado global compartilhado
# entre todos os nós do grafo
class State(TypedDict):

    # Lista de mensagens do agente
    #
    # operator.add diz ao LangGraph para concatenar
    # novas mensagens ao invés de sobrescrever
    messages: Annotated[list, operator.add]


# =========================================================
# 2. Configurar LLM com tools
# =========================================================

# Cria instância do modelo
llm = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0,
)

# Entrega as tools ao modelo
# para permitir tool calling automático
llm_with_tools = llm.bind_tools([
    calculate_math_expression
])

# Mapa para localizar tools pelo nome
# retornado pelo LLM
tools_by_name = {
    "calculate_math_expression": calculate_math_expression
}


# =========================================================
# Nó principal do agente
# =========================================================

def agent_node(state: State):

    # Envia histórico completo ao LLM
    response = llm_with_tools.invoke(
        state["messages"]
    )

    # Retorna nova mensagem para atualizar estado
    return {
        "messages": [response]
    }


# =========================================================
# Nó executor de ferramentas
# =========================================================

def tool_node(state: State):

    # Pega última mensagem do estado
    last_message = state["messages"][-1]

    outputs = []

    # Itera sobre tool calls solicitadas pelo LLM
    for tool_call in last_message.tool_calls:

        # Obtém nome da tool
        tool_name = tool_call["name"]

        # Localiza tool correta
        tool = tools_by_name[tool_name]

        # Executa tool com argumentos enviados pelo LLM
        result = tool.invoke(
            tool_call["args"]
        )

        # Cria mensagem de resposta da tool
        outputs.append(
            ToolMessage(
                content=result,
                tool_call_id=tool_call["id"],
            )
        )

    # Retorna outputs para atualizar estado
    return {
        "messages": outputs
    }


# =========================================================
# Função de roteamento do grafo
# =========================================================

def should_continue(state: State):

    # Obtém última mensagem
    last_message = state["messages"][-1]

    # Se o modelo solicitou tools
    # então vai para o nó tools
    if getattr(last_message, "tool_calls", None):
        return "tools"

    # Caso contrário encerra o grafo
    return END


# =========================================================
# 3. Criar grafo
# =========================================================

# Cria blueprint do grafo usando schema State
builder = StateGraph(State)


# =========================================================
# 4. Adicionar nós
# =========================================================

# Registra nó do agente
builder.add_node(
    "agent",
    agent_node
)

# Registra nó de tools
builder.add_node(
    "tools",
    tool_node
)


# =========================================================
# 5. Definir arestas / transições
# =========================================================

# Fluxo inicial:
# START -> agent
builder.add_edge(
    START,
    "agent"
)

# Define roteamento condicional
builder.add_conditional_edges(
    "agent",
    should_continue,
    {
        # Se houver tool calls
        "tools": "tools",

        # Caso contrário encerra
        END: END,
    },
)

# Cria loop:
# tools -> agent
builder.add_edge(
    "tools",
    "agent"
)


# =========================================================
# 6. Compilar
# =========================================================

# Valida e transforma o blueprint
# em runtime executável
graph = builder.compile()


# =========================================================
# 7. Executar
# =========================================================

# Estado inicial da execução
input_data = {
    "messages": [
        HumanMessage(
            content="Quanto é ((42 - 7) / 5) ** 2?"
        )
    ]
}


# =========================================================
# invoke()
# Executa tudo e retorna resultado final
# =========================================================

# result = graph.invoke(input_data)
#
# print("\nRESULTADO FINAL:")
# print(result["messages"][-1].content)


# =========================================================
# stream()
# Executa emitindo eventos incrementais
# =========================================================


# ---------------------------------------------------------
# stream_mode="values"
#
# Emite estado completo atualizado
# ---------------------------------------------------------

# for event in graph.stream(
#     input_data,
#     stream_mode="values",
# ):
#     print("\nEVENT:")
#     print(event["messages"][-1])


# ---------------------------------------------------------
# stream_mode="updates"
#
# Emite apenas alterações por nó
# ---------------------------------------------------------

# for event in graph.stream(
#     input_data,
#     stream_mode="updates",
# ):
#     print("\nUPDATE:")
#     print(event)


# ---------------------------------------------------------
# stream_mode="messages"
#
# Stream de tokens/mensagens do LLM
# ---------------------------------------------------------

# for token, metadata in graph.stream(
#     input_data,
#     stream_mode="messages",
# ):
#     print("\nMESSAGE:")
#     print(token.content, end="")


# ---------------------------------------------------------
# stream_mode="debug"
#
# Eventos internos detalhados do runtime
# ---------------------------------------------------------

for event in graph.stream(
    input_data,
    stream_mode="debug",
):
    print("\nDEBUG EVENT:")
    print(event)
