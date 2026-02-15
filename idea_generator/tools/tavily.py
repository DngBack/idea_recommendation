"""
Tavily search tool for web and literature discovery.
Uses Tavily API (https://tavily.com) – no Semantic Scholar key required.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from .base import BaseTool

logger = logging.getLogger(__name__)


class TavilySearchTool(BaseTool):
    """Search for papers and web content via the Tavily API."""

    def __init__(self, max_results: int = 10):
        parameters = [
            {
                "name": "query",
                "type": "str",
                "description": "The search query to find relevant papers or web sources.",
            }
        ]
        super().__init__(
            name="SearchTavily",
            description=(
                "Search for relevant literature and web content using Tavily. "
                "Use for academic topics, recent research, and general references. "
                "Provide a search query to find relevant sources."
            ),
            parameters=parameters,
        )
        self.max_results = min(max_results, 20)
        self._api_key = os.getenv("TAVILY_API_KEY")

    def use_tool(self, query: str) -> Optional[str]:
        if not self._api_key:
            return (
                "Error: TAVILY_API_KEY is not set. "
                "Add it to .env or export TAVILY_API_KEY=your_key to use SearchTavily."
            )
        results = self._search(query)
        if results:
            return self._format(results)
        return "No results found from Tavily."

    def _search(self, query: str) -> Optional[List[Dict[str, Any]]]:
        if not query:
            return None
        try:
            from tavily import TavilyClient
        except ImportError:
            logger.error("tavily-python not installed. Run: pip install tavily-python")
            return None

        try:
            client = TavilyClient(api_key=self._api_key)
            response = client.search(
                query=query,
                max_results=self.max_results,
                search_depth="basic",
                topic="general",
            )
        except Exception as e:
            logger.exception("Tavily search failed: %s", e)
            return None

        raw_results = response.get("results") or []
        if not raw_results:
            return None

        # Normalize to common shape: title, url, content, optional author/year
        out = []
        for r in raw_results:
            out.append({
                "title": r.get("title") or "Untitled",
                "url": r.get("url") or "",
                "content": r.get("content") or "",
                "score": r.get("score"),
            })
        return out

    @staticmethod
    def _format(results: List[Dict[str, Any]]) -> str:
        parts = []
        for i, r in enumerate(results):
            title = r.get("title", "Unknown Title")
            url = r.get("url", "N/A")
            content = (r.get("content") or "No description available.").strip()
            # CITE line for References: no author/year from Tavily, use title + url
            cite = f"CITE: ({title}). {url}."
            parts.append(
                f"{i + 1}: {title}\n"
                f"URL: {url}\n"
                f"Content: {content}\n"
                f"{cite}"
            )
        return "\n\n".join(parts)
