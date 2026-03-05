"""
ClinicalTrialsParser: Parser for ClinicalTrials.gov API.

Queries the ClinicalTrials.gov API v2 to extract clinical trial data.
Supports querying by cardiovascular disease conditions (default),
RNA therapeutics interventions, or custom queries.

Source: https://clinicaltrials.gov/data-api/api
API Version: 2.0
Note: Rate limited to ~50 requests per minute per IP.
"""

import logging
import time
from typing import Dict, Optional, List
import pandas as pd
import requests
from .base_parser import BaseParser
from ..utils import get_cvd_search_pattern

logger = logging.getLogger(__name__)


class ClinicalTrialsParser(BaseParser):
    """
    Parser for ClinicalTrials.gov API v2.

    Queries the API for clinical trials data and returns standardized DataFrames.
    Supports three query modes:
        - "cvd": Broad cardiovascular disease condition queries (default)
        - "rna": RNA therapeutics intervention queries
        - "custom": User-defined query term and field
    """

    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

    # Broad CVD category queries grouping terms from ontology.
    # Each string is an OR-joined query for the ClinicalTrials.gov API.
    CVD_CATEGORY_QUERIES = [
        "cardiovascular disease OR heart disease OR cardiac disease",
        "arrhythmia OR atrial fibrillation OR atrial flutter OR ventricular tachycardia OR ventricular fibrillation OR long QT syndrome OR Brugada syndrome OR sick sinus syndrome",
        "coronary artery disease OR myocardial infarction OR angina OR ischemic heart disease OR atherosclerosis",
        "heart failure OR congestive heart failure OR HFrEF OR HFpEF",
        "cardiomyopathy OR hypertrophic cardiomyopathy OR dilated cardiomyopathy OR restrictive cardiomyopathy OR arrhythmogenic right ventricular cardiomyopathy",
        "hypertension OR pulmonary hypertension OR resistant hypertension",
        "stroke OR cerebrovascular disease OR ischemic stroke OR hemorrhagic stroke OR transient ischemic attack",
        "peripheral arterial disease OR peripheral vascular disease OR aortic aneurysm OR aortic dissection OR thromboembolism OR venous thromboembolism",
        "hypercholesterolemia OR dyslipidemia OR familial hypercholesterolemia",
        "valvular heart disease OR aortic stenosis OR aortic regurgitation OR mitral stenosis OR mitral regurgitation OR mitral valve prolapse",
    ]

    def __init__(self, data_dir: Optional[str] = None,
                 query_mode: str = "cvd",
                 query_term: Optional[str] = None,
                 query_field: str = "query.cond",
                 max_results: int = 1000):
        """
        Initialize ClinicalTrials.gov parser.

        Args:
            data_dir: Directory for storing cached data.
            query_mode: Query strategy - "cvd" (default), "rna", or "custom".
            query_term: Search term (used for "custom" mode; ignored for "cvd").
            query_field: API query field for "custom" mode (default: "query.cond").
            max_results: Maximum number of results per query/category (default: 1000).
        """
        super().__init__(data_dir)
        self.query_mode = query_mode
        self.query_term = query_term
        self.query_field = query_field
        self.max_results = max_results
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CardioKB-Parser/0.1.0',
            'Accept': 'application/json'
        })
        self._trials_data = None

    def _fetch_trials(self, query_field: str, query_value: str,
                      max_results: int) -> List[dict]:
        """
        Fetch trials from the API with pagination.

        Args:
            query_field: API parameter name (e.g., "query.cond", "query.intr").
            query_value: Search term.
            max_results: Maximum trials to retrieve for this query.

        Returns:
            List of study JSON objects.
        """
        trials = []
        page_token = None
        page_size = 100

        while len(trials) < max_results:
            params = {
                query_field: query_value,
                'pageSize': min(page_size, max_results - len(trials)),
                'format': 'json'
            }
            if page_token:
                params['pageToken'] = page_token

            logger.info(f"  Fetching page (fetched so far: {len(trials)})...")

            response = self.session.get(
                self.BASE_URL, params=params, timeout=30
            )
            response.raise_for_status()

            data = response.json()
            studies = data.get('studies', [])
            if not studies:
                break

            trials.extend(studies)
            logger.info(f"  Fetched {len(studies)} studies (total: {len(trials)})")

            next_page_token = data.get('nextPageToken')
            if not next_page_token:
                break
            page_token = next_page_token

            # Respect rate limits (~50 requests/minute)
            time.sleep(1.5)

        return trials

    def download_data(self) -> bool:
        """
        Query ClinicalTrials.gov API for trials.

        In "cvd" mode, iterates over CVD_CATEGORY_QUERIES searching by condition
        and deduplicates results by NCT ID. In "rna" mode, searches by RNA
        therapeutics intervention. In "custom" mode, uses the provided query.

        Returns:
            True if successful, False otherwise.
        """
        logger.info(f"Query mode: {self.query_mode}")
        logger.info(f"API endpoint: {self.BASE_URL}")

        try:
            if self.query_mode == "cvd":
                return self._download_cvd()
            elif self.query_mode == "rna":
                return self._download_single("query.intr", "RNA therapeutics")
            elif self.query_mode == "custom":
                if not self.query_term:
                    logger.error("query_term is required for 'custom' mode")
                    return False
                return self._download_single(self.query_field, self.query_term)
            else:
                logger.error(f"Unknown query_mode: {self.query_mode}")
                return False

        except requests.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 429:
                    logger.error("Rate limit exceeded. Please wait before retrying.")
            return False
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _download_cvd(self) -> bool:
        """Query all CVD categories and deduplicate by NCT ID."""
        logger.info(f"Querying {len(self.CVD_CATEGORY_QUERIES)} CVD categories...")

        all_trials = []
        seen_nct_ids = set()

        for i, category_query in enumerate(self.CVD_CATEGORY_QUERIES, 1):
            logger.info(f"Category {i}/{len(self.CVD_CATEGORY_QUERIES)}: {category_query[:60]}...")

            try:
                trials = self._fetch_trials(
                    "query.cond", category_query, self.max_results
                )
            except requests.HTTPError as e:
                logger.warning(f"Failed to fetch category {i}: {e}")
                continue

            # Deduplicate by NCT ID
            new_count = 0
            for trial in trials:
                nct_id = (trial.get('protocolSection', {})
                          .get('identificationModule', {})
                          .get('nctId'))
                if nct_id and nct_id not in seen_nct_ids:
                    seen_nct_ids.add(nct_id)
                    all_trials.append(trial)
                    new_count += 1

            logger.info(f"  Added {new_count} new trials (total unique: {len(all_trials)})")

            # Delay between category batches
            if i < len(self.CVD_CATEGORY_QUERIES):
                time.sleep(2.0)

        self._trials_data = all_trials
        logger.info(f"Successfully retrieved {len(all_trials)} unique CVD trials")
        return True

    def _download_single(self, query_field: str, query_value: str) -> bool:
        """Run a single query (used for rna and custom modes)."""
        logger.info(f"Querying: {query_field}={query_value}")

        trials = self._fetch_trials(query_field, query_value, self.max_results)
        self._trials_data = trials
        logger.info(f"Successfully retrieved {len(trials)} trials")
        return True

    def _parse_study(self, study: dict) -> Optional[dict]:
        """Parse a single study JSON into a flat record."""
        protocol = study.get('protocolSection', {})

        id_module = protocol.get('identificationModule', {})
        trial_id = id_module.get('nctId', 'Unknown')
        title = id_module.get('briefTitle', id_module.get('officialTitle', 'No title'))

        status_module = protocol.get('statusModule', {})
        overall_status = status_module.get('overallStatus', 'Unknown')

        design_module = protocol.get('designModule', {})
        phases = design_module.get('phases', [])
        phase = ', '.join(phases) if phases else 'Not specified'

        conditions_module = protocol.get('conditionsModule', {})
        conditions = conditions_module.get('conditions', [])
        condition = '; '.join(conditions) if conditions else 'Not specified'

        arms_module = protocol.get('armsInterventionsModule', {})
        interventions = arms_module.get('interventions', [])
        intervention_names = [
            inv.get('name', '') for inv in interventions if inv.get('name')
        ]
        intervention_name = '; '.join(intervention_names) if intervention_names else 'Not specified'

        return {
            'trial_id': trial_id,
            'title': title,
            'intervention_name': intervention_name,
            'condition': condition,
            'phase': phase,
            'status': overall_status,
            'source_database': 'ClinicalTrials.gov'
        }

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse clinical trials data into structured DataFrames.

        Returns:
            Dictionary with 'clinical_trials' DataFrame.
        """
        logger.info("Parsing clinical trials data...")

        if self._trials_data is None:
            logger.error("No data to parse. Call download_data() first.")
            return {}

        trials_list = []
        for study in self._trials_data:
            try:
                record = self._parse_study(study)
                if record:
                    trials_list.append(record)
            except Exception as e:
                logger.warning(f"Failed to parse study: {e}")
                continue

        df = pd.DataFrame(trials_list)
        logger.info(f"Parsed {len(df)} trials")

        if len(df) > 0:
            logger.info("Status distribution:")
            for status, count in df['status'].value_counts().head(5).items():
                logger.info(f"  {status}: {count}")
            logger.info("Phase distribution:")
            for phase, count in df['phase'].value_counts().head(5).items():
                logger.info(f"  {phase}: {count}")

        return {'clinical_trials': df}

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """
        Get the schema for clinical trials data.

        Returns:
            Dictionary describing the schema for trial entities.
        """
        return {
            'clinical_trials': {
                'trial_id': 'ClinicalTrials.gov NCT identifier',
                'title': 'Study title',
                'intervention_name': 'Drug/intervention name(s)',
                'condition': 'Disease/condition(s) being studied',
                'phase': 'Study phase (e.g., PHASE1, PHASE2, PHASE3)',
                'status': 'Recruitment/overall status',
                'source_database': 'Source database (ClinicalTrials.gov)'
            }
        }

    def filter_cardiovascular_trials(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter trials for cardiovascular diseases.

        Uses comprehensive CVD terminology from ontology/cvd_disease_hierarchy.txt.
        Most useful when query_mode is "rna" or "custom" to post-filter results.

        Args:
            df: DataFrame of all trials

        Returns:
            Filtered DataFrame of cardiovascular-related trials
        """
        logger.info("Filtering for cardiovascular disease trials...")

        pattern = get_cvd_search_pattern()

        mask = (
            df['condition'].str.contains(pattern, case=False, na=False) |
            df['title'].str.contains(pattern, case=False, na=False)
        )

        cvd_trials = df[mask].copy()
        logger.info(f"Found {len(cvd_trials)} cardiovascular disease trials")

        return cvd_trials
