from langchain_tavily import TavilyExtract, TavilySearch

from app.config import settings

web_search = TavilySearch(
    max_results=5,
    search_depth="advanced",
    topic="general",
    include_answer=True,
    tavily_api_key=settings.tavily_api_key,
)

web_extract = TavilyExtract(
    extract_depth="basic",
    tavily_api_key=settings.tavily_api_key,
)
