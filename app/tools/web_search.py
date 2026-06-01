from langchain_tavily import TavilyExtract, TavilySearch

from app.config import settings
from app.tools import NarrationMeta

web_search = TavilySearch(
    max_results=5,
    search_depth="advanced",
    topic="general",
    include_answer=True,
    tavily_api_key=settings.tavily_api_key,
)
object.__setattr__(web_search, "narration", NarrationMeta(
    icon="🔍",
    announce_template="Pesquisando: {query}",
    done_label="Pesquisa concluída",
    error_label="Pesquisa falhou",
    level=1,
))

web_extract = TavilyExtract(
    extract_depth="basic",
    tavily_api_key=settings.tavily_api_key,
)
object.__setattr__(web_extract, "narration", NarrationMeta(
    icon="📄",
    announce_template="Extraindo conteúdo de {urls}",
    done_label="Conteúdo extraído",
    error_label="Extração falhou",
    level=1,
))
