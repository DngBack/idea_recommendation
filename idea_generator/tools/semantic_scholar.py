"""
Semantic Scholar search tool for literature discovery.
"""

import logging
import os
import time
import warnings
from typing import Dict, List, Optional

import backoff
import requests

from .base import BaseTool

logger = logging.getLogger(__name__)


def _on_backoff(details: Dict) -> None:
    logger.warning(
        "Backing off %.1f seconds after %d tries calling %s",
        details["wait"],
        details["tries"],
        details["target"].__name__,
    )


class SemanticScholarSearchTool(BaseTool):
    """Search for papers via the Semantic Scholar API."""

    def __init__(self, max_results: int = 10):
        parameters = [
            {
                "name": "query",
                "type": "str",
                "description": "The search query to find relevant papers.",
            }
        ]
        super().__init__(
            name="SearchSemanticScholar",
            description=(
                "Search for relevant literature using Semantic Scholar. "
                "Provide a search query to find relevant papers."
            ),
            parameters=parameters,
        )
        self.max_results = max_results
        self.S2_API_KEY = os.getenv("S2_API_KEY")
        if not self.S2_API_KEY:
            warnings.warn(
                "No S2_API_KEY found. Requests will be subject to stricter rate limits."
            )

    def use_tool(self, query: str) -> Optional[str]:
        papers = self._search(query)
        if papers:
            return self._format(papers)
        return "No papers found."

    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.HTTPError, requests.exceptions.ConnectionError),
        on_backoff=_on_backoff,
        max_tries=5,
    )
    def _search(self, query: str) -> Optional[List[Dict]]:
        if not query:
            return None

        headers: Dict[str, str] = {}
        if self.S2_API_KEY:
            headers["X-API-KEY"] = self.S2_API_KEY

        rsp = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            headers=headers,
            params={
                "query": query,
                "limit": self.max_results,
                "fields": "title,authors,venue,year,abstract,citationCount",
            },
            timeout=30,
        )
        logger.debug("S2 status=%d body=%s", rsp.status_code, rsp.text[:300])
        rsp.raise_for_status()

        results = rsp.json()
        if results.get("total", 0) == 0:
            return None

        papers = results.get("data", [])
        papers.sort(key=lambda x: x.get("citationCount", 0), reverse=True)
        return papers

    @staticmethod
    def _format(papers: List[Dict]) -> str:
        parts = []
        for i, p in enumerate(papers):
            authors = ", ".join(
                a.get("name", "Unknown") for a in p.get("authors", [])
            )
            parts.append(
                f"{i+1}: {p.get('title', 'Unknown Title')}. {authors}. "
                f"{p.get('venue', 'Unknown Venue')}, {p.get('year', 'N/A')}.\n"
                f"Citations: {p.get('citationCount', 'N/A')}\n"
                f"Abstract: {p.get('abstract', 'No abstract available.')}"
            )
        return "\n\n".join(parts)
