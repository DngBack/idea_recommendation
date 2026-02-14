"""
arXiv search tool for literature discovery.
Uses the arXiv API (Atom feed) to find relevant papers.
"""

import logging
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import backoff
import requests

from .base import BaseTool

logger = logging.getLogger(__name__)

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _on_backoff(details: Dict) -> None:
    logger.warning(
        "Backing off %.1f seconds after %d tries calling %s",
        details["wait"],
        details["tries"],
        details["target"].__name__,
    )


class ArxivSearchTool(BaseTool):
    """Search for papers on arXiv."""

    def __init__(self, max_results: int = 10):
        parameters = [
            {
                "name": "query",
                "type": "str",
                "description": "The search query to find relevant papers on arXiv.",
            }
        ]
        super().__init__(
            name="SearchArxiv",
            description=(
                "Search for relevant papers on arXiv. "
                "Provide a search query to find recent preprints and publications."
            ),
            parameters=parameters,
        )
        self.max_results = max_results

    def use_tool(self, query: str) -> Optional[str]:
        papers = self._search(query)
        if papers:
            return self._format(papers)
        return "No papers found on arXiv."

    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.HTTPError, requests.exceptions.ConnectionError),
        on_backoff=_on_backoff,
        max_tries=5,
    )
    def _search(self, query: str) -> Optional[List[Dict]]:
        if not query:
            return None

        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": self.max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        rsp = requests.get(ARXIV_API_URL, params=params, timeout=30)
        logger.debug("arXiv status=%d", rsp.status_code)
        rsp.raise_for_status()

        # Be polite to the arXiv API
        time.sleep(1.0)

        return self._parse_atom(rsp.text)

    @staticmethod
    def _parse_atom(xml_text: str) -> Optional[List[Dict]]:
        """Parse the Atom XML response from arXiv."""
        root = ET.fromstring(xml_text)
        entries = root.findall(f"{ATOM_NS}entry")
        if not entries:
            return None

        papers: List[Dict] = []
        for entry in entries:
            title_el = entry.find(f"{ATOM_NS}title")
            summary_el = entry.find(f"{ATOM_NS}summary")
            published_el = entry.find(f"{ATOM_NS}published")
            authors_els = entry.findall(f"{ATOM_NS}author")
            link_el = entry.find(f"{ATOM_NS}id")

            authors = []
            for a in authors_els:
                name_el = a.find(f"{ATOM_NS}name")
                if name_el is not None and name_el.text:
                    authors.append(name_el.text.strip())

            title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else "Unknown"
            abstract = summary_el.text.strip().replace("\n", " ") if summary_el is not None and summary_el.text else ""
            year = published_el.text[:4] if published_el is not None and published_el.text else "N/A"
            url = link_el.text.strip() if link_el is not None and link_el.text else ""

            doi = ""
            for link in entry.findall(f"{ATOM_NS}link"):
                href = link.get("href") or ""
                if "doi.org" in href:
                    doi = href
                    break

            papers.append({
                "title": title,
                "authors": authors,
                "year": year,
                "abstract": abstract,
                "url": url,
                "doi": doi or None,
            })
        return papers if papers else None

    @staticmethod
    def _format(papers: List[Dict]) -> str:
        parts = []
        for i, p in enumerate(papers):
            authors = ", ".join(p.get("authors", ["Unknown"]))
            year = p.get("year", "N/A")
            title = p.get("title", "Unknown Title")
            url = p.get("url", "N/A")
            if p.get("doi"):
                url = p["doi"]
            cite = f"CITE: {authors} ({year}). {title}. {url}."
            parts.append(
                f"{i+1}: {title}. {authors}. "
                f"arXiv, {year}.\n"
                f"URL: {p.get('url', 'N/A')}\n"
                f"Abstract: {p.get('abstract', 'No abstract available.')}\n"
                f"{cite}"
            )
        return "\n\n".join(parts)
