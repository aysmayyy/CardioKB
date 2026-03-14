"""
JensenLabParser: Parser for Jensen Lab DISEASES database.

Integrates curated (knowledge) and experimental gene-disease associations
from the DISEASES database (https://diseases.jensenlab.org). Produces
geneAssociatesWithDisease edges linking Gene nodes (by geneSymbol) to
Disease nodes (by xrefDiseaseOntology / DOID).

Source: https://diseases.jensenlab.org/Downloads
Access: Public (no credentials required)
License: CC BY 4.0
"""

import logging
from typing import Dict, Optional

import pandas as pd

from .base_parser import BaseParser

logger = logging.getLogger(__name__)

# Column names for the header-less TSV files
COLUMNS_KNOWLEDGE = [
    'ensp_id', 'gene_symbol', 'disease_id', 'disease_name',
    'source_db', 'evidence_type', 'confidence',
]
COLUMNS_EXPERIMENTS = [
    'ensp_id', 'gene_symbol', 'disease_id', 'disease_name',
    'source_db', 'source_score', 'confidence',
]


class JensenLabParser(BaseParser):
    """Parser for Jensen Lab DISEASES database."""

    BASE_URL = "https://download.jensenlab.org/"
    KNOWLEDGE_FILE = "human_disease_knowledge_filtered.tsv"
    EXPERIMENTS_FILE = "human_disease_experiments_filtered.tsv"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download knowledge and experiments filtered files."""
        logger.info("Downloading Jensen Lab DISEASES data...")

        ok = True
        for filename in (self.KNOWLEDGE_FILE, self.EXPERIMENTS_FILE):
            result = self.download_file(f"{self.BASE_URL}{filename}", filename)
            if not result:
                logger.error(f"Failed to download {filename}")
                ok = False

        return ok

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse downloaded TSVs into a single gene-disease relationship DataFrame."""
        frames = []

        # --- Knowledge (curated) channel ---
        knowledge_path = self.source_dir / self.KNOWLEDGE_FILE
        if knowledge_path.exists():
            df_k = pd.read_csv(
                knowledge_path, sep='\t', header=None,
                names=COLUMNS_KNOWLEDGE, dtype=str,
            )
            df_k['channel'] = 'knowledge'
            df_k['confidence'] = pd.to_numeric(df_k['confidence'], errors='coerce')
            logger.info(f"Knowledge channel: {len(df_k)} raw rows")
            frames.append(df_k[['gene_symbol', 'disease_id', 'disease_name',
                                'confidence', 'channel']])
        else:
            logger.warning(f"Knowledge file not found: {knowledge_path}")

        # --- Experiments channel ---
        experiments_path = self.source_dir / self.EXPERIMENTS_FILE
        if experiments_path.exists():
            df_e = pd.read_csv(
                experiments_path, sep='\t', header=None,
                names=COLUMNS_EXPERIMENTS, dtype=str,
            )
            df_e['channel'] = 'experiments'
            df_e['confidence'] = pd.to_numeric(df_e['confidence'], errors='coerce')
            logger.info(f"Experiments channel: {len(df_e)} raw rows")
            frames.append(df_e[['gene_symbol', 'disease_id', 'disease_name',
                                'confidence', 'channel']])
        else:
            logger.warning(f"Experiments file not found: {experiments_path}")

        if not frames:
            logger.error("No Jensen DISEASES data files found")
            return {}

        combined = pd.concat(frames, ignore_index=True)

        # Drop rows missing gene symbol or DOID
        combined = combined.dropna(subset=['gene_symbol', 'disease_id'])
        combined = combined[
            (combined['gene_symbol'] != '') & (combined['disease_id'] != '')
        ]

        # Keep only DOID-prefixed disease IDs (drop AmyCo and other non-DOID)
        non_doid = combined[~combined['disease_id'].str.startswith('DOID:')]
        if len(non_doid) > 0:
            logger.info(f"Dropping {len(non_doid)} rows with non-DOID disease IDs")
        combined = combined[combined['disease_id'].str.startswith('DOID:')]

        # Keep highest confidence per (gene_symbol, disease_id) pair
        combined = combined.sort_values('confidence', ascending=False)
        combined = combined.drop_duplicates(
            subset=['gene_symbol', 'disease_id'], keep='first',
        )

        combined['source_database'] = 'Jensen DISEASES'

        logger.info(
            f"Jensen DISEASES: {len(combined)} unique gene-disease associations "
            f"({combined['gene_symbol'].nunique()} genes, "
            f"{combined['disease_id'].nunique()} diseases)"
        )

        return {
            'gene_disease_associations': combined,
        }

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """Return schema description for each output DataFrame."""
        return {
            'gene_disease_associations': {
                'gene_symbol': 'Gene symbol (e.g., TP53)',
                'disease_id': 'Disease Ontology ID (e.g., DOID:114)',
                'disease_name': 'Disease name',
                'confidence': 'Association confidence score',
                'channel': 'Evidence channel (knowledge or experiments)',
                'source_database': 'Source database identifier',
            },
        }
