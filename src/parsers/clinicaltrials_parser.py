"""
ClinicalTrialsParser: Parser for ClinicalTrials.gov via the public API v2.

Queries the ClinicalTrials.gov API v2 for clinical trials matching a disease
filter (defaults to CVD terms). Paginates through results and caches responses
as JSON files. Produces the same output schema as the previous AACT-based
parser so downstream pipeline code is unchanged.

Source: https://clinicaltrials.gov/api/v2/studies
Access: Public (no credentials required)
Rate limit: ~3 requests/second (no hard cap, but be polite)
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional

import pandas as pd
import requests

from .base_parser import BaseParser
from ..utils import load_disease_terms

logger = logging.getLogger(__name__)

# ClinicalTrials.gov API v2 base URL
_API_BASE = "https://clinicaltrials.gov/api/v2/studies"

# Fields to retrieve (minimises response size)
_FIELDS = [
    "protocolSection.identificationModule.nctId",
    "protocolSection.identificationModule.briefTitle",
    "protocolSection.statusModule.overallStatus",
    "protocolSection.designModule.phases",
    "protocolSection.conditionsModule.conditions",
    "protocolSection.armsInterventionsModule.interventions",
]

# Maximum page size allowed by the API
_PAGE_SIZE = 1000

# Delay between API requests (seconds)
_REQUEST_DELAY = 0.35


class ClinicalTrialsParser(BaseParser):
    """
    Parser for ClinicalTrials.gov via the public REST API v2.

    Queries for clinical trials matching disease terms from a filter file
    (defaults to CVD). Results are cached as JSON so repeat runs skip the
    network requests.
    """

    def __init__(self, data_dir: Optional[str] = None,
                 disease_filter: Optional[str] = None, **kwargs):
        """
        Args:
            data_dir: Directory for storing cached data.
            disease_filter: Path to disease terms file (one term per line).
                Defaults to ontology/disease_filter.txt (CVD).
        """
        super().__init__(data_dir)
        self.disease_filter = disease_filter
        self._cache_dir = Path(self.data_dir) / "clinicaltrials_cache"

    # ------------------------------------------------------------------
    # Download (= query API and cache)
    # ------------------------------------------------------------------

    def download_data(self) -> bool:
        """Query ClinicalTrials.gov API v2 for each disease term and cache."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        terms = load_disease_terms(self.disease_filter)
        logger.info(
            f"Querying ClinicalTrials.gov API v2 for {len(terms)} disease terms"
        )

        success = True
        total_studies = 0

        for term in sorted(terms):
            cache_file = self._cache_file_for(term)
            if cache_file.exists():
                cached = json.loads(cache_file.read_text())
                n = len(cached)
                total_studies += n
                logger.debug(f"  Cached: {term!r} ({n} studies)")
                continue

            studies = self._query_term(term)
            if studies is None:
                logger.warning(f"  Failed to query: {term!r}")
                success = False
                continue

            cache_file.write_text(json.dumps(studies, separators=(",", ":")))
            total_studies += len(studies)
            logger.info(f"  Fetched: {term!r} ({len(studies)} studies)")

        logger.info(
            f"ClinicalTrials.gov: {total_studies} total studies across "
            f"{len(terms)} disease terms"
        )
        return success

    def _cache_file_for(self, term: str) -> Path:
        """Return the cache file path for a disease term."""
        safe = term.replace("/", "_").replace(" ", "_").replace(":", "_")
        return self._cache_dir / f"{safe}.json"

    def _query_term(self, term: str) -> Optional[List[dict]]:
        """
        Paginate through all API v2 results for a single condition query.

        Returns list of raw study JSON objects, or None on failure.
        """
        all_studies: List[dict] = []
        page_token: Optional[str] = None

        while True:
            params = {
                "query.cond": term,
                "fields": ",".join(_FIELDS),
                "pageSize": _PAGE_SIZE,
                "format": "json",
            }
            if page_token:
                params["pageToken"] = page_token

            try:
                time.sleep(_REQUEST_DELAY)
                resp = requests.get(_API_BASE, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"API error for {term!r}: {e}")
                return None

            studies = data.get("studies", [])
            all_studies.extend(studies)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return all_studies

    # ------------------------------------------------------------------
    # Parse cached JSON into the standard DataFrame schema
    # ------------------------------------------------------------------

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse cached API responses into a clinical_trials DataFrame.

        Output schema matches the previous AACT parser:
            trial_id, title, intervention_name, condition, phase, status,
            source_database
        """
        terms = load_disease_terms(self.disease_filter)

        # Collect all studies, deduplicating by NCT ID
        seen_nct: set = set()
        records: List[dict] = []

        for term in sorted(terms):
            cache_file = self._cache_file_for(term)
            if not cache_file.exists():
                continue

            studies = json.loads(cache_file.read_text())
            for study in studies:
                row = self._extract_study(study)
                if row and row["trial_id"] not in seen_nct:
                    seen_nct.add(row["trial_id"])
                    records.append(row)

        if not records:
            logger.warning("No clinical trial records parsed")
            return {"clinical_trials": pd.DataFrame(columns=[
                "trial_id", "title", "intervention_name", "condition",
                "phase", "status", "source_database",
            ])}

        df = pd.DataFrame(records)
        df = df[["trial_id", "title", "intervention_name", "condition",
                 "phase", "status", "source_database"]]

        logger.info(f"Parsed {len(df):,} unique clinical trials (CVD-scoped)")

        if len(df) > 0:
            logger.info("Status distribution:")
            for status, count in df["status"].value_counts().head(5).items():
                logger.info(f"  {status}: {count:,}")
            logger.info("Phase distribution:")
            for phase, count in df["phase"].value_counts().head(5).items():
                logger.info(f"  {phase}: {count:,}")

        return {"clinical_trials": df}

    @staticmethod
    def _extract_study(study: dict) -> Optional[dict]:
        """Extract a flat record from an API v2 study JSON object."""
        proto = study.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        status_mod = proto.get("statusModule", {})
        design = proto.get("designModule", {})
        cond_mod = proto.get("conditionsModule", {})
        arms_mod = proto.get("armsInterventionsModule", {})

        nct_id = ident.get("nctId")
        if not nct_id:
            return None

        # Phases: list like ["PHASE1", "PHASE2"] → "Phase 1; Phase 2"
        raw_phases = design.get("phases", [])
        if raw_phases:
            phase = "; ".join(
                p.replace("PHASE", "Phase ").replace("NA", "Not Applicable")
                for p in raw_phases
            )
        else:
            phase = "Not specified"

        # Conditions: list of strings
        conditions = cond_mod.get("conditions", [])
        condition_str = "; ".join(conditions) if conditions else "Not specified"

        # Interventions: list of objects with "name" key
        interventions = arms_mod.get("interventions", [])
        intv_names = [i.get("name", "") for i in interventions if i.get("name")]
        intervention_str = "; ".join(intv_names) if intv_names else "Not specified"

        return {
            "trial_id": nct_id,
            "title": ident.get("briefTitle", ""),
            "intervention_name": intervention_str,
            "condition": condition_str,
            "phase": phase,
            "status": status_mod.get("overallStatus", "Unknown"),
            "source_database": "ClinicalTrials.gov",
        }

    # ------------------------------------------------------------------

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            "clinical_trials": {
                "trial_id": "ClinicalTrials.gov NCT identifier",
                "title": "Study title",
                "intervention_name": "Drug/intervention name(s)",
                "condition": "Disease/condition(s) being studied",
                "phase": "Study phase",
                "status": "Recruitment/overall status",
                "source_database": "Source database (ClinicalTrials.gov)",
            }
        }
