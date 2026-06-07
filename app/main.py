import logging
from contextlib import asynccontextmanager
from pathlib import Path

from ag_ui_langgraph import LangGraphAgent
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.agent.graph import build_graph
from app.config import settings
from app.domain.restaurant import DOMAIN
from app.errors import describe_error, error_hint
from app.middleware import configure_middlewares
from app.routers import agent as agent_router
from app.routers import health as health_router
from app.services.mcp_service import general_mcp_servers, get_mcp_tools, merge_servers

# Uvicorn configura apenas seus próprios loggers (uvicorn.*) e não toca no root.
# Sem isso, logger.info() de código da aplicação é silenciado (root em WARNING).
logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s: %(name)s: %(message)s")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — inicialização assíncrona dos recursos (padrão oficial FastAPI).
# Composition root: monta o engine genérico com o `DOMAIN` escolhido (único lugar que
# conhece engine + domínio + AG-UI). As tools MCP (`get_mcp_tools`) exigem setup async;
# os servidores gerais (mcp.json da raiz) são unidos aos do domínio (`DOMAIN.mcp_servers`)
# e carregados com isolamento de falha por servidor. O agente fica em `app.state.agent`;
# as dicas de UI do domínio em `app.state.ui_hints` (entregues ao front via CUSTOM).
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp_servers = merge_servers(general_mcp_servers(), DOMAIN.mcp_servers)
    mcp_tools = await get_mcp_tools(mcp_servers)
    graph = build_graph(DOMAIN, extra_tools=mcp_tools)
    app.state.agent = LangGraphAgent(name="private-agent", graph=graph)
    app.state.ui_hints = DOMAIN.ui_hints
    logger.info("Agente AG-UI inicializado. Domínio=%s, MCP servers=%d, tools=%d",
                DOMAIN.name, len(mcp_servers), len(mcp_tools))
    logger.info("AG_UI_STREAM_RAW_EVENTS=%s", settings.ag_ui_stream_raw_events)
    yield


app = FastAPI(title="LangGraph Private Agent — AG-UI", version="0.2.0", lifespan=lifespan)

# Middleware (CORS) — isolado em app/middleware.py.
configure_middlewares(app)

# Rotas — APIRouters dedicados.
#   POST /agent (SSE + wrap de RUN_ERROR), GET /agent/health  →  app/routers/agent.py
#   GET  /health                                              →  app/routers/health.py
app.include_router(agent_router.router)
app.include_router(health_router.router)


# ---------------------------------------------------------------------------
# Handlers globais — capturam qualquer erro fora do stream, sem traceback.
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning("Requisição inválida em %s: corpo não corresponde ao schema esperado.",
                   request.url.path)
    return JSONResponse(
        status_code=422,
        content={"detail": "Requisição inválida: o corpo não corresponde ao formato esperado."},
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    # Detalhe só no log; resposta ao cliente é genérica/segura.
    logger.error("Erro não tratado em %s: %s", request.url.path, error_hint(exc))
    return JSONResponse(status_code=500, content={"detail": describe_error(exc)})


# ---------------------------------------------------------------------------
# Página de demonstração (servida pelo próprio FastAPI)
# ---------------------------------------------------------------------------
# Montado por último para que /agent e /health tenham precedência.
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
