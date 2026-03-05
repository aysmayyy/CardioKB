"""
DoRothEA Parser for CardioKB.

Parses DoRothEA data to extract transcription factor nodes and
TF-gene regulatory relationships.

DoRothEA is a gene regulatory network containing signed TF-target interactions.
Data is retrieved from OmniPath API which provides DoRothEA interactions.

Data Source:
  - OmniPath API: https://omnipathdb.org/

Adapted from AlzKB (disease-agnostic).
"""

import logging
import pandas as pd
import requests

from pathlib import Path
from typing import Dict, List, Optional
from .base_parser import BaseParser
from ..ontology_configs import DOROTHEA_TRANSCRIPTION_FACTORS, DOROTHEA_TF_GENE_INTERACTIONS

logger = logging.getLogger(__name__)


class DoRothEAParser(BaseParser):
    """
    Parser for DoRothEA transcription factor regulatory network.

    Uses OmniPath API to retrieve DoRothEA data with:
    - Confidence levels A, B, C, D (A = highest confidence)
    - Mode of regulation (stimulation/inhibition)
    - Curation effort scores
    """

    OMNIPATH_DOROTHEA_URL = (
        "https://omnipathdb.org/interactions"
        "?datasets=dorothea"
        "&fields=curation_effort,dorothea_level"
        "&genesymbols=1"
        "&license=academic"
    )

    DEFAULT_CONFIDENCE_LEVELS = ['A', 'B', 'C', 'D']

    def __init__(self, data_dir: str, confidence_levels: Optional[List[str]] = None):
        """
        Initialize the DoRothEA parser.

        Args:
            data_dir: Directory to store downloaded and processed data
            confidence_levels: List of confidence levels to include (A, B, C, D)
        """
        super().__init__(data_dir)
        self.confidence_levels = confidence_levels or self.DEFAULT_CONFIDENCE_LEVELS

    def download_data(self) -> bool:
        """
        Download DoRothEA data from OmniPath API.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Downloading DoRothEA TF-gene regulatory network from OmniPath...")

        try:
            response = requests.get(self.OMNIPATH_DOROTHEA_URL, timeout=120)
            response.raise_for_status()

            dorothea_path = self.get_file_path(f"{DOROTHEA_TF_GENE_INTERACTIONS}.tsv")
            with open(dorothea_path, 'w') as f:
                f.write(response.text)

            line_count = len(response.text.strip().split('\n'))
            logger.info(f"Downloaded {line_count - 1} interactions")
            return True

        except Exception as e:
            logger.error(f"Failed to download DoRothEA from OmniPath: {e}")
            return False

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse DoRothEA TF-gene regulatory data.

        Returns:
            Dictionary with 'transcription_factors' and 'tf_gene_interactions' DataFrames.
        """
        dorothea_path = self.get_file_path(f"{DOROTHEA_TF_GENE_INTERACTIONS}.tsv")

        if not Path(dorothea_path).exists():
            logger.error(f"DoRothEA file not found: {dorothea_path}")
            return {}

        logger.info(f"Parsing DoRothEA from {dorothea_path}")

        try:
            df = pd.read_csv(dorothea_path, sep='\t')
            logger.info(f"Loaded {len(df)} DoRothEA TF-target interactions")

            # Filter by confidence levels
            if 'dorothea_level' in df.columns:
                def matches_confidence(level_str):
                    if pd.isna(level_str):
                        return False
                    levels = str(level_str).split(';')
                    return any(lvl in self.confidence_levels for lvl in levels)

                df = df[df['dorothea_level'].apply(matches_confidence)]
                logger.info(f"After filtering by confidence levels {self.confidence_levels}: {len(df)} interactions")

            # Extract unique TFs as nodes
            tfs = df['source_genesymbol'].dropna().unique()
            tf_nodes = [{
                "tf_symbol": tf,
                "node_type": "TranscriptionFactor",
                "source_database": "DoRothEA"
            } for tf in tfs]
            logger.info(f"Found {len(tf_nodes)} unique transcription factors")

            # Format TF-gene interactions
            interactions = []
            for _, row in df.iterrows():
                tf = row.get('source_genesymbol', '')
                target = row.get('target_genesymbol', '')

                if not tf or not target or pd.isna(tf) or pd.isna(target):
                    continue

                is_stimulation = row.get('is_stimulation', 0)
                is_inhibition = row.get('is_inhibition', 0)

                if is_stimulation and not is_inhibition:
                    mor = "activation"
                    mor_score = 1
                elif is_inhibition and not is_stimulation:
                    mor = "repression"
                    mor_score = -1
                elif is_stimulation and is_inhibition:
                    mor = "dual"
                    mor_score = 0
                else:
                    mor = "unknown"
                    mor_score = 0

                interactions.append({
                    "tf_symbol": tf,
                    "target_gene": target,
                    "tf_uniprot": row.get('source', ''),
                    "target_uniprot": row.get('target', ''),
                    "confidence": row.get('dorothea_level', ''),
                    "curation_effort": row.get('curation_effort', 0),
                    "mode_of_regulation": mor,
                    "mor_score": mor_score,
                    "is_directed": row.get('is_directed', 1),
                    "relationship": "transcriptionFactorInteractsWithGene",
                    "source_database": "DoRothEA"
                })

            logger.info(f"Total TF-gene interactions: {len(interactions)}")

            return {
                DOROTHEA_TRANSCRIPTION_FACTORS: pd.DataFrame(tf_nodes),
                DOROTHEA_TF_GENE_INTERACTIONS: pd.DataFrame(interactions)
            }

        except Exception as e:
            logger.error(f"Error parsing DoRothEA: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """Get the schema for DoRothEA data."""
        return {
            DOROTHEA_TRANSCRIPTION_FACTORS: {
                "tf_symbol": "Transcription factor gene symbol",
                "node_type": "Node type (TranscriptionFactor)",
                "source_database": "Data source (DoRothEA)"
            },
            DOROTHEA_TF_GENE_INTERACTIONS: {
                "tf_symbol": "Transcription factor gene symbol",
                "target_gene": "Target gene symbol",
                "confidence": "DoRothEA confidence level (A-D)",
                "curation_effort": "Number of supporting publications/databases",
                "mode_of_regulation": "Mode of regulation (activation/repression/dual/unknown)",
                "mor_score": "Mode of regulation score (1=activation, -1=repression, 0=unknown/dual)",
                "source_database": "Data source (DoRothEA)"
            }
        }
