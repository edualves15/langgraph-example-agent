from typing import TypedDict, Annotated
import operator
import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END

load_dotenv()

# Importa tools
from tools.math_tools import calculate_math_expression
from tools.calendar_tools import (
    get_today_info,
    get_date_details,
    calculate_date_difference,
    shift_date,
    count_business_days,
    add_business_days,
    find_next_weekday,
    list_dates_in_range,
)


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
    calculate_math_expression,
    get_today_info,
    get_date_details,
    calculate_date_difference,
    shift_date,
    count_business_days,
    add_business_days,
    find_next_weekday,
    list_dates_in_range,
])

# Mapa para localizar tools pelo nome
# retornado pelo LLM
tools_by_name = {
    "calculate_math_expression": calculate_math_expression,
    "get_today_info": get_today_info,
    "get_date_details": get_date_details,
    "calculate_date_difference": calculate_date_difference,
    "shift_date": shift_date,
    "count_business_days": count_business_days,
    "add_business_days": add_business_days,
    "find_next_weekday": find_next_weekday,
    "list_dates_in_range": list_dates_in_range,
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

        # Emite mensagem de progresso dinâmica usando os args reais
        # Tenta formatar o template com os args; cai no label estático se falhar
        if tool.metadata:
            template = tool.metadata.get("step_label_template")
            if template:
                try:
                    step_label = template.format(**tool_call["args"])
                except KeyError:
                    step_label = tool.metadata.get("step_label", tool_name)
            else:
                step_label = tool.metadata.get("step_label", tool_name)
            icon = tool.metadata.get("step_icon", "")
        else:
            step_label = tool_name
            icon = ""
        print(f"{icon} {step_label}" if icon else step_label)

        # Executa tool com argumentos enviados pelo LLM
        result = tool.invoke(
            tool_call["args"],
        )

        # Cria mensagem de resposta da tool
        outputs.append(
            ToolMessage(
                content=result,
                name=tool_name,
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
initial_state = {
    "messages": [
        HumanMessage(
            # Exemplos de prompts para testar ferramentas individuais:
            # content="Quanto é ((42 - 7) / 5) ** 2?"         → calculate_math_expression
            # content="Que dia foi ontem?"                     → shift_date
            # content="Que dia da semana é 25/12/2026?"        → get_date_details
            # content="Quantos dias úteis até 31/12/2026?"     → count_business_days
            # content="Qual é a próxima segunda-feira?"        → find_next_weekday
            # content="Quais são todas as sextas de junho/2026?" → list_dates_in_range
            #
            # Prompt multi-tool: força múltiplas tools no mesmo loop
            content=(
                "Daqui a exatamente 100 dias úteis, que data será? "
                "E qual é o dia da semana dessa data? "
                "Além disso, quantos dias corridos existem entre hoje e essa data?"
                "Qual é a próxima sexta-feira? "
                "E quantas sextas-feiras ainda existem em 2026 a partir de hoje? "
                "Além disso, quanto é (52 * 5) + 3?"
                "Que dia da semana foi o Natal do ano retrasado?"
                "Quais os feriados bancários desse ano?"
            )
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

# for event in graph.stream(
#     input_data,
#     stream_mode="debug",
# ):
#     print("\nDEBUG EVENT:")
#     print(event)


# ---------------------------------------------------------
# stream_mode=["updates", "messages"]
#
# Combinação ideal para frontend:
# - "updates" para progresso de ferramentas
# - "messages" para streaming de tokens da resposta final
# ---------------------------------------------------------

for mode, data in graph.stream(
    initial_state,
    stream_mode=["updates", "messages"],
):
    if mode == "messages":
        token, metadata = data
        if metadata.get("langgraph_node") != "agent":
            continue
        # content pode ser string ou lista de content blocks (padrão LangChain)
        content = token.content
        text = (
            "".join(c.get("text", "") for c in content if isinstance(c, dict))
            if isinstance(content, list)
            else content or ""
        )
        if text:
            print(text, end="", flush=True)

print()
