"""
PubTator Central Parser for the knowledge graph.

Uses the PubTator Central REST API to retrieve literature-mined
gene-disease and drug-disease co-occurrences for cardiovascular diseases.

API: https://www.ncbi.nlm.nih.gov/research/pubtator3-api/

Output:
  - pubtator_gene_disease.tsv : gene-disease co-occurrences from literature
    Columns: pmid, gene_id, gene_symbol, disease_id, disease_name, source_database
"""

import logging
import time
from typing import Dict, List, Optional

import pandas as pd
import requests

from .base_parser import BaseParser
from config_loader import get_disease_scope

logger = logging.getLogger(__name__)

_DEFAULT_URL = "https://ftp.ncbi.nlm.nih.gov/pub/lu/PubTator/"

_API_BASE = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api"
_SEARCH_URL = f"{_API_BASE}/search/"
_EXPORT_URL = f"{_API_BASE}/publications/export/biocjson"

GENE_DISEASE_OUTPUT = "pubtator_gene_disease"

_PAGE_SIZE = 100       # results per API page
_MAX_PAGES = 5         # max pages per search term (500 articles)
_MAX_TERMS = 20        # max disease terms to query
_CALL_DELAY = 0.5      # seconds between API calls


class PubTatorParser(BaseParser):
    """
    Parser for PubTator Central literature mining data.

    Queries the PubTator Central REST API for publications mentioning
    cardiovascular disease terms, then extracts gene and disease entity
    co-occurrences from the annotation data.

    Constructor args (injected from databases.yaml):
        data_dir      – base directory for raw/cached files
        source_url    – ignored; API URL is fixed
        disease_scope – disease scope dict (injected by main.py)
        entity_types  – entity types to extract (default: Gene, Disease)
    """

    def __init__(
        self,
        data_dir: str,
        source_url: Optional[str] = None,
        disease_scope: Optional[Dict] = None,
        entity_types: Optional[list] = None,
    ):
        super().__init__(data_dir)
        self.source_name = "pubtator"
        self.source_dir = self.data_dir / self.source_name
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.entity_types = entity_types or ["Gene", "Disease", "Chemical"]

        _scope = disease_scope if disease_scope else get_disease_scope()
        self._primary_terms = _scope.get("primary_terms", [])

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download_data(self) -> bool:
        """Data fetched via API in parse_data(); no pre-download needed."""
        return True

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Query PubTator Central API for CVD-related publications and extract
        gene-disease co-occurrences.
        """
        # Select representative search terms
        search_terms = self._select_search_terms()
        logger.info("PubTator: querying %d disease terms ...", len(search_terms))

        all_pmids: set = set()
        for term in search_terms:
            pmids = self._search_pmids(term)
            all_pmids.update(pmids)
            logger.info("  '%s': %d PMIDs (total: %d)", term, len(pmids), len(all_pmids))
            time.sleep(_CALL_DELAY)

        if not all_pmids:
            logger.warning("No PubTator PMIDs found for disease scope.")
            return {}

        logger.info("PubTator: fetching annotations for %d PMIDs ...", len(all_pmids))

        # Fetch annotations in batches
        rows: List[dict] = []
        pmid_list = sorted(all_pmids)
        batch_size = 100
        for i in range(0, len(pmid_list), batch_size):
            batch = pmid_list[i:i + batch_size]
            batch_rows = self._fetch_annotations(batch)
            rows.extend(batch_rows)
            if (i // batch_size) % 5 == 0:
                logger.info("  Processed %d / %d PMIDs, %d associations so far",
                            min(i + batch_size, len(pmid_list)), len(pmid_list), len(rows))
            time.sleep(_CALL_DELAY)

        if not rows:
            logger.warning("No PubTator gene-disease associations found.")
            return {}

        df = pd.DataFrame(rows)
        df = df.drop_duplicates().reset_index(drop=True)
        df["source_database"] = "PubTator"
        logger.info("PubTator: %d gene-disease associations", len(df))

        return {GENE_DISEASE_OUTPUT: df}

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    def _select_search_terms(self) -> List[str]:
        """Select representative CVD search terms (avoid too many API calls)."""
        # Prefer longer, more specific terms (skip abbreviations < 5 chars)
        candidates = [t for t in self._primary_terms if len(t) >= 5]
        # Sort by length descending to get most specific terms first
        sorted_terms = sorted(candidates, key=len, reverse=True)
        selected: List[str] = []
        seen_lower: set = set()
        for term in sorted_terms:
            tl = term.lower()
            # Skip if this term is a substring of an already-selected term
            if not any(tl in s for s in seen_lower):
                selected.append(term)
                seen_lower.add(tl)
            if len(selected) >= _MAX_TERMS:
                break
        return selected

    def _search_pmids(self, term: str) -> List[str]:
        """Search PubTator Central for PMIDs mentioning a disease term."""
        pmids: List[str] = []
        for page in range(_MAX_PAGES):
            params = {
                "text": term,
                "page": page + 1,
                "sort": "score desc",
            }
            try:
                resp = requests.get(_SEARCH_URL, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.debug("PubTator search error for '%s': %s", term, exc)
                break

            results = data.get("results", [])
            if not results:
                break

            for r in results:
                # pmid is an integer in the API response
                pmid = r.get("pmid") or r.get("_id", "")
                if pmid:
                    pmids.append(str(pmid).strip())

            # Check pagination using total_pages
            total_pages = data.get("total_pages", 1)
            if page + 1 >= min(total_pages, _MAX_PAGES):
                break
            time.sleep(_CALL_DELAY)

        return pmids

    def _fetch_annotations(self, pmids: List[str]) -> List[dict]:
        """
        Fetch BioC JSON annotations for a batch of PMIDs.
        Extracts Gene and Disease entity pairs per article.

        Response structure: {"PubTator3": [{"id": pmid, "passages": [...]}]}
        """
        rows: List[dict] = []
        try:
            params = {"pmids": ",".join(pmids)}
            resp = requests.get(_EXPORT_URL, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.debug("PubTator export error: %s", exc)
            return rows

        # PubTator3 response: {"PubTator3": [doc1, doc2, ...]}
        if isinstance(data, dict):
            docs = data.get("PubTator3", [])
        elif isinstance(data, list):
            docs = data
        else:
            return rows

        for doc in docs:
            pmid = str(doc.get("id", "")).strip()
            if not pmid:
                continue

            # Collect gene and disease entities per passage
            genes: List[dict] = []
            diseases: List[dict] = []

            for passage in doc.get("passages", []):
                for ann in passage.get("annotations", []):
                    infons = ann.get("infons", {})
                    etype = infons.get("type", "")
                    identifier = infons.get("identifier", "") or infons.get("normalized_id", "")
                    text = ann.get("text", "")
                    name = infons.get("name", text)

                    if etype == "Gene" and identifier and identifier not in ("-", ""):
                        genes.append({
                            "gene_id":     identifier,
                            "gene_symbol": text,
                        })
                    elif etype == "Disease" and identifier and identifier not in ("-", ""):
                        diseases.append({
                            "disease_id":   identifier,
                            "disease_name": name or text,
                        })

            # Create co-occurrence pairs (gene × disease per article)
            for gene in genes:
                for disease in diseases:
                    rows.append({
                        "pmid":         pmid,
                        "gene_id":      gene["gene_id"],
                        "gene_symbol":  gene["gene_symbol"],
                        "disease_id":   disease["disease_id"],
                        "disease_name": disease["disease_name"],
                    })

        return rows

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            GENE_DISEASE_OUTPUT: {
                "pmid":            "PubMed ID",
                "gene_id":         "NCBI Gene ID",
                "gene_symbol":     "Gene symbol (text mention)",
                "disease_id":      "Disease identifier (MeSH or OMIM)",
                "disease_name":    "Disease name (text mention)",
                "source_database": "Source database (PubTator)",
            },
        }
