"""
PubMed search tool for literature discovery.
Uses NCBI eutils (esearch + efetch) for medicine, biology, and related fields.
"""

import logging
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import backoff
import requests

from .base import BaseTool

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
def _strip_ns(tag: str) -> str:
    """Return local part of tag (strip namespace)."""
    return tag.split("}")[-1] if "}" in tag else tag


def _on_backoff(details: Dict) -> None:
    logger.warning(
        "Backing off %.1f seconds after %d tries calling %s",
        details["wait"],
        details["tries"],
        details["target"].__name__,
    )


class PubMedSearchTool(BaseTool):
    """Search for papers on PubMed (medicine, biology, NLP)."""

    def __init__(self, max_results: int = 10):
        parameters = [
            {
                "name": "query",
                "type": "str",
                "description": "The search query to find relevant papers on PubMed.",
            }
        ]
        super().__init__(
            name="SearchPubMed",
            description=(
                "Search for relevant literature using PubMed. "
                "Provide a search query for medicine, biology, or health-related papers."
            ),
            parameters=parameters,
        )
        self.max_results = max_results

    def use_tool(self, query: str) -> Optional[str]:
        papers = self._search(query)
        if papers:
            return self._format(papers)
        return "No papers found on PubMed."

    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.HTTPError, requests.exceptions.ConnectionError),
        on_backoff=_on_backoff,
        max_tries=5,
    )
    def _search(self, query: str) -> Optional[List[Dict]]:
        if not query:
            return None

        # esearch: get PMID list
        rsp = requests.get(
            ESEARCH_URL,
            params={
                "db": "pubmed",
                "term": query,
                "retmax": self.max_results,
                "sort": "relevance",
                "retmode": "json",
            },
            timeout=30,
        )
        logger.debug("PubMed esearch status=%d", rsp.status_code)
        rsp.raise_for_status()
        data = rsp.json()
        id_list = data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return None

        time.sleep(0.4)  # rate limit

        # efetch: get details (XML)
        rsp2 = requests.get(
            EFETCH_URL,
            params={
                "db": "pubmed",
                "id": ",".join(id_list),
                "retmode": "xml",
            },
            timeout=30,
        )
        logger.debug("PubMed efetch status=%d", rsp2.status_code)
        rsp2.raise_for_status()
        return self._parse_xml(rsp2.text)

    def _parse_xml(self, xml_text: str) -> Optional[List[Dict]]:
        root = ET.fromstring(xml_text)
        articles = [
            e for e in root.iter()
            if _strip_ns(e.tag) == "PubmedArticle"
        ]
        if not articles:
            return None

        papers: List[Dict] = []
        for article in articles:
            medline = next(
                (e for e in article.iter() if _strip_ns(e.tag) == "MedlineCitation"),
                article,
            )

            pmid_el = next((e for e in medline.iter() if _strip_ns(e.tag) == "PMID"), None)
            pmid = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else ""
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "N/A"

            article_el = next(
                (e for e in medline.iter() if _strip_ns(e.tag) == "Article"),
                medline,
            )

            title_el = next(
                (e for e in article_el.iter() if _strip_ns(e.tag) == "ArticleTitle"),
                None,
            )
            title = ""
            if title_el is not None:
                title = " ".join(title_el.itertext()).strip().replace("\n", " ")

            abstract_el = next(
                (e for e in article_el.iter() if _strip_ns(e.tag) == "AbstractText"),
                None,
            )
            abstract = ""
            if abstract_el is not None:
                abstract = " ".join(abstract_el.itertext()).strip().replace("\n", " ")

            year = ""
            pub_date = next(
                (e for e in medline.iter() if _strip_ns(e.tag) in ("PubDate", "ArticleDate")),
                None,
            )
            if pub_date is not None:
                year_el = next((e for e in pub_date.iter() if _strip_ns(e.tag) == "Year"), None)
                if year_el is not None and year_el.text:
                    year = year_el.text[:4]
                elif pub_date.text:
                    year = pub_date.text.strip()[:4]

            authors = []
            for author_el in article_el.iter():
                if _strip_ns(author_el.tag) != "Author":
                    continue
                last = next((e for e in author_el.iter() if _strip_ns(e.tag) == "LastName"), None)
                fore = next((e for e in author_el.iter() if _strip_ns(e.tag) == "ForeName"), None)
                if last is not None and last.text:
                    name = last.text
                    if fore is not None and fore.text:
                        name = f"{fore.text} {name}"
                    authors.append(name)

            author_str = ", ".join(authors) if authors else "Unknown"

            papers.append({
                "title": title or "Unknown Title",
                "authors": author_str,
                "year": year or "N/A",
                "abstract": abstract or "No abstract available.",
                "url": url,
            })
        return papers if papers else None

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
                f"PubMed, {year}.\n"
                f"URL: {url}\n"
                f"Abstract: {p.get('abstract', 'No abstract available.')}\n"
                f"{cite}"
            )
        return "\n\n".join(parts)
