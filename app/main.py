import logging
from pathlib import Path

from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.agent.graph import build_graph

# Uvicorn configura apenas seus próprios loggers (uvicorn.*) e não toca no root.
# Sem isso, logger.info() de código da aplicação é silenciado (root em WARNING).
logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s: %(name)s: %(message)s")

logger = logging.getLogger(__name__)

app = FastAPI(title="LangGraph Private Agent — AG-UI", version="0.2.0")

# ---------------------------------------------------------------------------
# Endpoint oficial AG-UI sobre LangGraph
# ---------------------------------------------------------------------------
# `add_langgraph_fastapi_endpoint` registra POST /agent (stream SSE de eventos
# AG-UI) e GET /agent/health. O LangGraphAgent mapeia os eventos do LangGraph
# para os eventos canônicos do protocolo (RUN_*, TEXT_MESSAGE_*, TOOL_CALL_*,
# STATE_SNAPSHOT/DELTA, etc.) automaticamente.
graph = build_graph()
agent = LangGraphAgent(name="private-agent", graph=graph)
add_langgraph_fastapi_endpoint(app, agent, "/agent")

logger.info("Agente AG-UI inicializado com %d ferramenta(s).", len(graph.nodes))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Página de demonstração (servida pelo próprio FastAPI)
# ---------------------------------------------------------------------------
# Montado por último para que /agent e /health tenham precedência.
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
