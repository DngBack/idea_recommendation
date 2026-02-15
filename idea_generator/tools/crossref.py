"""
CrossRef search tool for literature discovery.
Uses the public CrossRef REST API (no API key required).
"""

import logging
from typing import Any, Dict, List, Optional

import backoff
import requests

from .base import BaseTool

logger = logging.getLogger(__name__)

CROSSREF_API_URL = "https://api.crossref.org/works"


def _on_backoff(details: Dict[str, Any]) -> None:
    logger.warning(
        "Backing off %.1f seconds after %d tries calling %s",
        details["wait"],
        details["tries"],
        details["target"].__name__,
    )


class CrossRefSearchTool(BaseTool):
    """Search for works (papers, books) via the CrossRef API (DOI metadata)."""

    def __init__(self, max_results: int = 10):
        parameters = [
            {
                "name": "query",
                "type": "str",
                "description": "The search query to find relevant works (title, author, keyword).",
            }
        ]
        super().__init__(
            name="SearchCrossRef",
            description=(
                "Search for literature using CrossRef (DOI metadata). "
                "Provide a search query to find works by title, author, or keyword. No API key required."
            ),
            parameters=parameters,
        )
        self.max_results = max_results

    def use_tool(self, query: str) -> Optional[str]:
        items = self._search(query)
        if items:
            return self._format(items)
        return "No works found on CrossRef."

    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.HTTPError, requests.exceptions.ConnectionError),
        on_backoff=_on_backoff,
        max_tries=5,
    )
    def _search(self, query: str) -> Optional[List[Dict[str, Any]]]:
        if not query:
            return None

        resp = requests.get(
            CROSSREF_API_URL,
            params={
                "query": query,
                "rows": self.max_results,
                "order": "desc",
                "sort": "relevance",
            },
            timeout=30,
        )
        logger.debug("CrossRef status=%d", resp.status_code)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("message", {}).get("items", [])
        return items if items else None

    @staticmethod
    def _format(items: List[Dict[str, Any]]) -> str:
        parts = []
        for i, item in enumerate(items):
            title_list = item.get("title", [])
            title = title_list[0] if title_list else "Unknown Title"
            authors_list = item.get("author", [])
            authors = ", ".join(
                f"{a.get('given', '')} {a.get('family', '')}".strip() or "Unknown"
                for a in authors_list[:5]
            )
            if len(authors_list) > 5:
                authors += " et al."
            year = "N/A"
            if item.get("published", {}).get("date-parts"):
                year = str(item["published"]["date-parts"][0][0])
            doi = item.get("DOI", "")
            url = f"https://doi.org/{doi}" if doi else "N/A"
            cite = f"CITE: {authors} ({year}). {title}. {url}."
            container = item.get("container-title", [])
            venue = container[0] if container else "N/A"
            parts.append(
                f"{i+1}: {title}. {authors}. "
                f"{venue}, {year}.\n"
                f"DOI: {doi}\n"
                f"Abstract: (use URL for full metadata)\n"
                f"{cite}"
            )
        return "\n\n".join(parts)
