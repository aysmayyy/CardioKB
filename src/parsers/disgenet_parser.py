"""
DisGeNETParser: Parser for DisGeNET data with API support, adapted for CVD.

DisGeNET is a comprehensive database of gene-disease associations
from various sources including literature and databases.

Source: https://www.disgenet.org/
API Documentation: https://www.disgenet.org/api/

Adapted from AlzKB: searches for cardiovascular diseases instead of Alzheimer's.
"""

import logging
import os
import time
from typing import Dict, Optional, Tuple

import pandas as pd
import requests

from .base_parser import BaseParser
from ..ontology_configs import (
    DISGENET_DISEASE_CLASSIFICATIONS,
    DISGENET_DISEASE_MAPPINGS,
    DISGENET_GENE_DISEASE_ASSOCIATIONS,
)
from ..utils import load_cvd_terms

logger = logging.getLogger(__name__)


class DisGeNETParser(BaseParser):
    """
    Parser for DisGeNET gene-disease association data with API support.

    Supports both API-based retrieval and manual file-based parsing.
    CVD-scoped: searches for cardiovascular disease terms from the ontology.
    """

    API_BASE_URL = "https://api.disgenet.com/api/v1"

    # CVD search terms for DisGeNET free-text search
    # Each term generates a separate API query; results are combined
    CVD_SEARCH_TERMS = [
        "cardiovascular",
        "coronary artery disease",
        "heart failure",
        "myocardial infarction",
        "atrial fibrillation",
        "cardiomyopathy",
        "hypertension",
        "stroke",
        "atherosclerosis",
        "arrhythmia",
        "aortic",
        "valvular heart",
        "thromboembolism",
        "peripheral arterial disease",
    ]

    def __init__(self, data_dir: str, api_key: Optional[str] = None):
        """
        Initialize DisGeNET parser.

        Args:
            data_dir: Directory for storing data files
            api_key: DisGeNET API key (optional, for API access)
        """
        super().__init__(data_dir)
        self.api_key = api_key or os.getenv('DISGENET_API_KEY')
        self.session = requests.Session()

        if self.api_key:
            self.session.headers.update({
                'Authorization': self.api_key,
                'accept': 'application/json',
            })
            logger.info("DisGeNET API key configured")
        else:
            logger.warning("No DisGeNET API key provided. Will attempt file-based parsing.")

    def download_data(self) -> bool:
        """
        Download or check for DisGeNET data.

        Returns:
            True if data is available, False otherwise.
        """
        if self.api_key:
            return self._download_via_api()
        else:
            return self._check_manual_files()

    def _check_manual_files(self) -> bool:
        """Check for manually downloaded DisGeNET files."""
        logger.info("Checking for DisGeNET data files...")
        logger.info("Note: DisGeNET data must be downloaded manually from:")
        logger.info("  https://www.disgenet.org/downloads")

        required_files = [
            f"{DISGENET_GENE_DISEASE_ASSOCIATIONS}.tsv",
            f"{DISGENET_DISEASE_CLASSIFICATIONS}.tsv",
            f"{DISGENET_DISEASE_MAPPINGS}.tsv"
        ]

        all_exist = True
        for filename in required_files:
            filepath = self.get_file_path(filename)
            if os.path.exists(filepath):
                logger.info(f"Found {filename}")
            else:
                logger.error(f"{filename} not found at: {filepath}")
                all_exist = False

        if not all_exist:
            logger.error("Please download manually or provide API key")
            return False

        return True

    def _download_via_api(self) -> bool:
        """
        Download DisGeNET data via API for CVD diseases.

        Returns:
            True if successful, False otherwise.
        """
        logger.info("Downloading DisGeNET data via API (CVD scope)...")

        try:
            # Step 1: Get CVD disease IDs and metadata
            disease_classifications, disease_mappings = self.get_cvd_disease_ids()

            if disease_classifications is None or disease_mappings is None:
                logger.error("Failed to retrieve CVD disease IDs from API")
                return False

            # Save disease data frames
            classifications_path = self.get_file_path(f"api_{DISGENET_DISEASE_CLASSIFICATIONS}.tsv")
            disease_classifications.to_csv(classifications_path, sep='\t', index=False)
            logger.info(f"Saved disease classifications: {classifications_path}")

            mappings_path = self.get_file_path(f"api_{DISGENET_DISEASE_MAPPINGS}.tsv")
            disease_mappings.to_csv(mappings_path, sep='\t', index=False)
            logger.info(f"Saved disease mappings: {mappings_path}")

            # Step 2: Get unique disease IDs
            unique_disease_ids = disease_mappings['diseaseId'].dropna().unique().tolist()
            logger.info(f"Found {len(unique_disease_ids)} unique CVD disease IDs")

            if not unique_disease_ids:
                logger.warning("No disease IDs found to query associations")
                return False

            # Step 3: Fetch gene-disease associations for each disease ID
            all_associations = []
            for disease_id in unique_disease_ids:
                logger.info(f"Fetching associations for disease ID: {disease_id}")
                associations = self._get_disease_associations_by_id(disease_id)

                if associations is not None and len(associations) > 0:
                    all_associations.append(associations)
                    logger.info(f"  Retrieved {len(associations)} associations")
                else:
                    logger.warning(f"  No associations found for {disease_id}")

                time.sleep(0.5)

            # Step 4: Combine all associations
            if all_associations:
                combined_associations = pd.concat(all_associations, ignore_index=True)
                initial_count = len(combined_associations)
                combined_associations = combined_associations.drop_duplicates()
                final_count = len(combined_associations)

                if initial_count != final_count:
                    logger.info(f"Removed {initial_count - final_count} duplicate associations")

                output_path = self.get_file_path(f"api_{DISGENET_GENE_DISEASE_ASSOCIATIONS}.tsv")
                combined_associations.to_csv(output_path, sep='\t', index=False)
                logger.info(f"Downloaded {len(combined_associations)} total gene-disease associations via API")
                return True
            else:
                logger.error("No gene-disease associations retrieved")
                return False

        except Exception as e:
            logger.error(f"API download failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def get_cvd_disease_ids(self) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """
        Get CVD disease IDs and related information from DisGeNET API.

        Searches for multiple CVD terms and combines results.

        Returns:
            Tuple of (disease_classifications DataFrame, disease_mappings DataFrame)
        """
        logger.info("Querying DisGeNET API for CVD disease entities...")

        all_classifications = []
        all_mappings = []
        seen_disease_ids = set()

        for search_term in self.CVD_SEARCH_TERMS:
            logger.info(f"  Searching: '{search_term}'")

            endpoint = f"{self.API_BASE_URL}/entity/disease"
            params = {
                'disease_free_text_search_string': search_term,
            }

            try:
                response = self.session.get(endpoint, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if 'payload' not in data:
                    logger.debug(f"  No results for '{search_term}'")
                    time.sleep(0.5)
                    continue

                payload = data['payload']
                logger.info(f"  Retrieved {len(payload)} disease entities")

                for item in payload:
                    disease_id = item.get('diseaseUMLSCUI', '')
                    if disease_id in seen_disease_ids:
                        continue
                    seen_disease_ids.add(disease_id)

                    # Classification row
                    all_classifications.append({
                        'diseaseName': item.get('name', ''),
                        'diseaseId': disease_id,
                        'diseaseClasses_MSH': ','.join(item.get('diseaseClasses_MSH', [])),
                        'diseaseClasses_UMLS_ST': ','.join(item.get('diseaseClasses_UMLS_ST', [])),
                        'diseaseClasses_DO': ','.join(item.get('diseaseClasses_DO', [])),
                        'diseaseClasses_HPO': ','.join(item.get('diseaseClasses_HPO', [])),
                    })

                    # Mapping row
                    base_data = {
                        'diseaseName': item.get('name', ''),
                        'diseaseId': disease_id,
                    }
                    code_dict = {}
                    for code_item in item.get('diseaseCodes', []):
                        vocabulary = code_item.get('vocabulary', '')
                        code = code_item.get('code', '')
                        if vocabulary:
                            code_dict[vocabulary] = code

                    all_mappings.append({**base_data, **code_dict})

                time.sleep(0.5)

            except requests.RequestException as e:
                logger.warning(f"  API request failed for '{search_term}': {e}")
                time.sleep(1.0)
                continue

        if not all_classifications:
            logger.error("No CVD disease entities found")
            return None, None

        disease_classifications = pd.DataFrame(all_classifications)
        disease_classifications['sourceDatabase'] = 'DisGeNET'
        logger.info(f"Total unique CVD disease classifications: {len(disease_classifications)}")

        disease_mappings = pd.DataFrame(all_mappings)
        disease_mappings['sourceDatabase'] = 'DisGeNET'
        logger.info(f"Total unique CVD disease mappings: {len(disease_mappings)}")

        return disease_classifications, disease_mappings

    def _get_disease_associations_by_id(self, disease_id: str,
                                         limit: int = 10000) -> Optional[pd.DataFrame]:
        """
        Get disease-gene associations from DisGeNET API using disease ID.

        Args:
            disease_id: Disease ID (UMLS CUI)
            limit: Maximum number of results

        Returns:
            DataFrame of associations or None if failed
        """
        endpoint = f"{self.API_BASE_URL}/gda/summary"
        params = {
            'disease': f'UMLS_{disease_id}',
            'source': 'CURATED',
        }

        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if 'payload' not in data:
                return None

            payload = data['payload']

            gda_data = []
            for item in payload:
                gda_data.append({
                    'geneId': item.get('geneNcbiID', ''),
                    'geneSymbol': item.get('symbolOfGene', ''),
                    'geneType': item.get('geneNcbiType', ''),
                    'diseaseId': item.get('diseaseUMLSCUI', ''),
                    'diseaseName': item.get('diseaseName', ''),
                    'diseaseClasses_MSH': ','.join(item.get('diseaseClasses_MSH', [])),
                    'diseaseClasses_UMLS_ST': ','.join(item.get('diseaseClasses_UMLS_ST', [])),
                    'diseaseClasses_DO': ','.join(item.get('diseaseClasses_DO', [])),
                    'diseaseClasses_HPO': ','.join(item.get('diseaseClasses_HPO', [])),
                    'diseaseMapping': ','.join(item.get('diseaseVocabularies', [])),
                    'diseaseType': item.get('diseaseType', ''),
                    'score': item.get('score', ''),
                })

            gda_df = pd.DataFrame(gda_data)
            gda_df['sourceDatabase'] = 'DisGeNET'
            return gda_df

        except requests.RequestException as e:
            logger.error(f"API request failed: {e}")
            return None

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse DisGeNET data.

        Returns:
            Dictionary with gene_disease_associations, disease_mappings,
            and disease_classifications DataFrames.
        """
        logger.info("Parsing DisGeNET data...")
        result = {}

        # Try API file first for gene-disease associations
        api_gda_file = self.get_file_path(f"api_{DISGENET_GENE_DISEASE_ASSOCIATIONS}.tsv")
        try:
            assoc_df = self.read_tsv(api_gda_file)
            if assoc_df is not None:
                assoc_df['sourceDatabase'] = 'DisGeNET'
                result['gene_disease_associations'] = assoc_df
                logger.info(f"Parsed {len(assoc_df)} gene-disease associations from API")
        except (FileNotFoundError, Exception):
            pass

        # Fall back to manual files
        if 'gene_disease_associations' not in result:
            gda_file = self.get_file_path(f"{DISGENET_GENE_DISEASE_ASSOCIATIONS}.tsv")
            try:
                assoc_df = self.read_tsv(gda_file)
                if assoc_df is not None:
                    assoc_df['sourceDatabase'] = 'DisGeNET'
                    result['gene_disease_associations'] = assoc_df
                    logger.info(f"Parsed {len(assoc_df)} gene-disease associations")
            except (FileNotFoundError, Exception):
                logger.error("Gene-disease associations file not found")

        # Disease mappings
        api_mappings_file = self.get_file_path(f"api_{DISGENET_DISEASE_MAPPINGS}.tsv")
        try:
            mappings_df = self.read_tsv(api_mappings_file)
            if mappings_df is not None:
                mappings_df['sourceDatabase'] = 'DisGeNET'
                result['disease_mappings'] = mappings_df
                logger.info(f"Parsed {len(mappings_df)} disease mappings from API")
        except (FileNotFoundError, Exception):
            pass

        if 'disease_mappings' not in result:
            mappings_file = self.get_file_path(f"{DISGENET_DISEASE_MAPPINGS}.tsv")
            try:
                mappings_df = self.read_tsv(mappings_file)
                if mappings_df is not None:
                    mappings_df['sourceDatabase'] = 'DisGeNET'
                    result['disease_mappings'] = mappings_df
            except (FileNotFoundError, Exception):
                pass

        # Disease classifications
        api_classifications_file = self.get_file_path(f"api_{DISGENET_DISEASE_CLASSIFICATIONS}.tsv")
        try:
            classifications_df = self.read_tsv(api_classifications_file)
            if classifications_df is not None:
                classifications_df['sourceDatabase'] = 'DisGeNET'
                result['disease_classifications'] = classifications_df
                logger.info(f"Parsed {len(classifications_df)} disease classifications from API")
        except (FileNotFoundError, Exception):
            pass

        if 'disease_classifications' not in result:
            classifications_file = self.get_file_path(f"{DISGENET_DISEASE_CLASSIFICATIONS}.tsv")
            try:
                classifications_df = self.read_tsv(classifications_file)
                if classifications_df is not None:
                    classifications_df['sourceDatabase'] = 'DisGeNET'
                    result['disease_classifications'] = classifications_df
            except (FileNotFoundError, Exception):
                pass

        return result

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """Get the schema for DisGeNET data."""
        return {
            DISGENET_GENE_DISEASE_ASSOCIATIONS: {
                'geneId': 'NCBI Gene ID',
                'geneSymbol': 'Gene symbol',
                'geneType': 'Gene NCBI type',
                'diseaseId': 'Disease identifier (UMLS CUI)',
                'diseaseName': 'Disease name',
                'diseaseType': 'Disease type',
                'score': 'Association score',
                'sourceDatabase': 'Source database',
            },
            DISGENET_DISEASE_MAPPINGS: {
                'diseaseName': 'Disease name',
                'diseaseId': 'Disease identifier (UMLS CUI)',
                'sourceDatabase': 'Source database',
            },
            DISGENET_DISEASE_CLASSIFICATIONS: {
                'diseaseName': 'Disease name',
                'diseaseId': 'Disease identifier (UMLS CUI)',
                'sourceDatabase': 'Source database',
            }
        }

    def filter_cvd_associations(self, assoc_df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter associations for cardiovascular diseases using CVD ontology terms.

        Args:
            assoc_df: DataFrame of all gene-disease associations

        Returns:
            Filtered DataFrame of CVD-related associations
        """
        logger.info("Filtering for cardiovascular disease associations...")

        cvd_terms = load_cvd_terms()
        text_lower = assoc_df['diseaseName'].str.lower()

        mask = text_lower.apply(
            lambda x: any(term in x for term in cvd_terms) if pd.notna(x) else False
        )

        cvd_assoc = assoc_df[mask].copy()
        logger.info(f"Found {len(cvd_assoc)} CVD gene-disease associations")

        if len(cvd_assoc) > 0:
            unique_diseases = cvd_assoc['diseaseName'].unique()
            logger.info(f"Unique CVD diseases: {len(unique_diseases)}")
            for disease in unique_diseases[:10]:
                logger.info(f"  - {disease}")

        return cvd_assoc
