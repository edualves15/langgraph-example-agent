from langchain_tavily import TavilyExtract, TavilySearch

from app.config import settings

# `description=` sobrescreve a descrição nativa para seguir o mesmo padrão das
# demais tools (a docstring/description é a superfície de prompt vista pelo modelo).
web_search = TavilySearch(
    max_results=5,
    search_depth="advanced",
    topic="general",
    include_answer=True,
    tavily_api_key=settings.tavily_api_key,
    description=(
        "Search the web for current information. "
        "Use this tool when the user asks about news, events, prices, real-time data, "
        "or anything that may have changed recently or is outside your knowledge. "
        "Input: a search query string. "
        "Returns ranked results with titles, URLs, and snippets; cite the source URLs."
    ),
)

web_extract = TavilyExtract(
    extract_depth="basic",
    tavily_api_key=settings.tavily_api_key,
    description=(
        "Extract the full content of specific web pages. "
        "Use this tool to read a known URL in depth — for example, a page already found "
        "via web search. "
        "Input: one or more URLs. "
        "Returns the extracted page text."
    ),
)
