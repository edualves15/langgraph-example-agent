from langchain_tavily import TavilyExtract, TavilySearch

from app.config import settings

web_search = TavilySearch(
    max_results=5,
    search_depth="advanced",
    topic="general",
    include_answer=True,
    tavily_api_key=settings.tavily_api_key,
)
web_search.metadata = {
    "step_label": "Pesquisando: {query}",
    "step_done_label": "Pesquisa concluída",
    "step_icon": "search",
    "step_category": "web",
}

web_extract = TavilyExtract(
    extract_depth="basic",
    tavily_api_key=settings.tavily_api_key,
)
web_extract.metadata = {
    "step_label": "Extraindo conteúdo de {urls}",
    "step_done_label": "Conteúdo extraído",
    "step_icon": "document",
    "step_category": "web",
}
