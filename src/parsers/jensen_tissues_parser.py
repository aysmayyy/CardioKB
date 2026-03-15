"""
JensenTissuesParser: Parser for Jensen Lab TISSUES database.

Integrates curated (knowledge) and experimental gene-tissue expression
associations from the TISSUES database (https://tissues.jensenlab.org).
Produces geneExpressedInBodyPart edges linking Gene nodes (by geneSymbol)
to BodyPart nodes (by BTO tissue ID).

Source: https://download.jensenlab.org/
Access: Public (no credentials required)
License: CC BY 4.0
"""

import logging
from typing import Dict, Optional

import pandas as pd

from .base_parser import BaseParser

logger = logging.getLogger(__name__)

# Header-less TSV columns (same structure as DISEASES files)
COLUMNS_KNOWLEDGE = [
    'ensp_id', 'gene_symbol', 'tissue_id', 'tissue_name',
    'source_db', 'evidence_type', 'confidence',
]
COLUMNS_EXPERIMENTS = [
    'ensp_id', 'gene_symbol', 'tissue_id', 'tissue_name',
    'source_db', 'source_score', 'confidence',
]


class JensenTissuesParser(BaseParser):
    """Parser for Jensen Lab TISSUES database."""

    BASE_URL = "https://download.jensenlab.org/"
    KNOWLEDGE_FILE = "human_tissue_knowledge_filtered.tsv"
    EXPERIMENTS_FILE = "human_tissue_experiments_filtered.tsv"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download knowledge and experiments filtered files."""
        logger.info("Downloading Jensen Lab TISSUES data...")

        ok = True
        for filename in (self.KNOWLEDGE_FILE, self.EXPERIMENTS_FILE):
            result = self.download_file(f"{self.BASE_URL}{filename}", filename)
            if not result:
                logger.error(f"Failed to download {filename}")
                ok = False

        return ok

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse downloaded TSVs into gene-tissue relationship DataFrame."""
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
            frames.append(df_k[['gene_symbol', 'tissue_id', 'tissue_name',
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
            frames.append(df_e[['gene_symbol', 'tissue_id', 'tissue_name',
                                'confidence', 'channel']])
        else:
            logger.warning(f"Experiments file not found: {experiments_path}")

        if not frames:
            logger.error("No Jensen TISSUES data files found")
            return {}

        combined = pd.concat(frames, ignore_index=True)

        # Drop rows missing gene symbol or tissue ID
        combined = combined.dropna(subset=['gene_symbol', 'tissue_id'])
        combined = combined[
            (combined['gene_symbol'] != '') & (combined['tissue_id'] != '')
        ]

        # Keep only BTO-prefixed tissue IDs
        non_bto = combined[~combined['tissue_id'].str.startswith('BTO:')]
        if len(non_bto) > 0:
            logger.info(f"Dropping {len(non_bto)} rows with non-BTO tissue IDs")
        combined = combined[combined['tissue_id'].str.startswith('BTO:')]

        # Keep highest confidence per (gene_symbol, tissue_id) pair
        combined = combined.sort_values('confidence', ascending=False)
        combined = combined.drop_duplicates(
            subset=['gene_symbol', 'tissue_id'], keep='first',
        )

        # Lowercase tissue names to match BodyPart.commonName (Uberon convention)
        combined['tissue_name'] = combined['tissue_name'].str.lower()

        combined['source_database'] = 'Jensen TISSUES'

        logger.info(
            f"Jensen TISSUES: {len(combined)} unique gene-tissue associations "
            f"({combined['gene_symbol'].nunique()} genes, "
            f"{combined['tissue_id'].nunique()} tissues)"
        )

        # Build tissue node table for BTO tissues not already in Uberon.
        # Filter out tissues whose lowercased name already exists as a
        # BodyPart.commonName from Uberon to avoid duplicate MATCH hits.
        all_tissues = (
            combined[['tissue_id', 'tissue_name']]
            .drop_duplicates(subset=['tissue_id'])
            .rename(columns={'tissue_id': 'xrefUberon',
                             'tissue_name': 'commonName'})
        )
        uberon_path = self.source_dir.parent.parent / 'processed' / 'uberon' / 'anatomy_nodes.tsv'
        if uberon_path.exists():
            uberon_names = set(
                pd.read_csv(uberon_path, sep='\t', usecols=['name'])['name']
                .str.lower().dropna()
            )
            tissue_nodes = all_tissues[~all_tissues['commonName'].isin(uberon_names)]
            logger.info(
                f"Jensen TISSUES: {len(all_tissues)} total tissues, "
                f"{len(all_tissues) - len(tissue_nodes)} already in Uberon, "
                f"{len(tissue_nodes)} new BTO nodes to create"
            )
        else:
            tissue_nodes = all_tissues
            logger.warning(
                f"Uberon TSV not found at {uberon_path}; "
                f"creating all {len(tissue_nodes)} BTO tissue nodes"
            )

        return {
            'tissue_nodes': tissue_nodes,
            'gene_tissue_associations': combined,
        }

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """Return schema description for each output DataFrame."""
        return {
            'gene_tissue_associations': {
                'gene_symbol': 'Gene symbol (e.g., TP53)',
                'tissue_id': 'BTO tissue ID (e.g., BTO:0000142)',
                'tissue_name': 'Tissue name',
                'confidence': 'Association confidence score',
                'channel': 'Evidence channel (knowledge or experiments)',
                'source_database': 'Source database identifier',
            },
        }
