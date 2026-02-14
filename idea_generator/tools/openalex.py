"""
OpenAlex search tool for literature discovery.
Uses the OpenAlex API for broad coverage with DOI and citation info.
"""

import logging
import os
import time
from typing import Dict, List, Optional

import backoff
import requests

from .base import BaseTool

logger = logging.getLogger(__name__)

OPENALEX_URL = "https://api.openalex.org/works"


def _on_backoff(details: Dict) -> None:
    logger.warning(
        "Backing off %.1f seconds after %d tries calling %s",
        details["wait"],
        details["tries"],
        details["target"].__name__,
    )


class OpenAlexSearchTool(BaseTool):
    """Search for papers using OpenAlex."""

    def __init__(self, max_results: int = 10):
        parameters = [
            {
                "name": "query",
                "type": "str",
                "description": "The search query to find relevant papers on OpenAlex.",
            }
        ]
        super().__init__(
            name="SearchOpenAlex",
            description=(
                "Search for relevant literature using OpenAlex. "
                "Provide a search query for broad academic coverage with DOI and citations."
            ),
            parameters=parameters,
        )
        self.max_results = max_results
        self.mailto = os.getenv("OPENALEX_MAILTO", "")

    def use_tool(self, query: str) -> Optional[str]:
        papers = self._search(query)
        if papers:
            return self._format(papers)
        return "No papers found on OpenAlex."

    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.HTTPError, requests.exceptions.ConnectionError),
        on_backoff=_on_backoff,
        max_tries=5,
    )
    def _search(self, query: str) -> Optional[List[Dict]]:
        if not query:
            return None

        params: Dict[str, str] = {
            "search": query,
            "per_page": str(min(self.max_results, 25)),
        }
        if self.mailto:
            params["mailto"] = self.mailto

        rsp = requests.get(OPENALEX_URL, params=params, timeout=30)
        logger.debug("OpenAlex status=%d", rsp.status_code)
        rsp.raise_for_status()
        data = rsp.json()

        results = data.get("results", [])
        if not results:
            return None

        time.sleep(0.2)  # polite rate limit

        papers: List[Dict] = []
        for w in results:
            title = w.get("title") or w.get("display_name") or "Unknown Title"
            year = w.get("publication_year")
            year_str = str(year) if year is not None else "N/A"
            url = w.get("doi") or w.get("id") or "N/A"
            if isinstance(url, str) and not url.startswith("http"):
                url = f"https://openalex.org/{url}"

            authors_list = []
            for a in w.get("authorships") or []:
                author = a.get("author") if isinstance(a.get("author"), dict) else None
                if author:
                    name = author.get("display_name")
                    if name:
                        authors_list.append(name)
            authors = ", ".join(authors_list) if authors_list else "Unknown"

            abstract = w.get("abstract") or "No abstract available."
            if isinstance(abstract, dict):
                abstract = "No abstract available."

            papers.append({
                "title": title,
                "authors": authors,
                "year": year_str,
                "abstract": abstract,
                "url": url,
            })
        return papers

    @staticmethod
    def _format(papers: List[Dict]) -> str:
        parts = []
        for i, p in enumerate(papers):
            authors = p.get("authors", "Unknown")
            year = p.get("year", "N/A")
            title = p.get("title", "Unknown Title")
            url = p.get("url", "N/A")
            cite = f"CITE: {authors} ({year}). {title}. {url}."
            parts.append(
                f"{i+1}: {title}. {authors}. "
                f"OpenAlex, {year}.\n"
                f"URL: {url}\n"
                f"Abstract: {p.get('abstract', 'No abstract available.')}\n"
                f"{cite}"
            )
        return "\n\n".join(parts)
