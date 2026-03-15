"""
HGNCFamiliesParser: Parser for HGNC gene family assignments.

Extracts gene family nodes and gene-family membership edges from the
gene_group / gene_group_id columns in the HGNC complete set file
(already downloaded by HGNCParser).

Source: https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt
Access: Public (no credentials required)
License: CC BY 4.0
"""

import logging
from typing import Dict, Optional

import pandas as pd

from .base_parser import BaseParser

logger = logging.getLogger(__name__)


class HGNCFamiliesParser(BaseParser):
    """Parser for HGNC gene family data (from hgnc_complete_set.txt)."""

    # Same file as HGNCParser — reuses the already-downloaded data
    DOWNLOAD_URL = "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt"
    FILENAME = "hgnc_complete_set.txt"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)
        # Share the hgnc source directory so we reuse the same downloaded file
        self.source_dir = self.data_dir / 'hgnc'

    def download_data(self) -> bool:
        """Download HGNC complete set (if not already present from HGNCParser)."""
        filepath = self.source_dir / self.FILENAME
        if filepath.exists():
            logger.info("HGNC complete set already downloaded, reusing")
            return True
        logger.info("Downloading HGNC data for families...")
        self.source_dir.mkdir(parents=True, exist_ok=True)
        result = self.download_file(self.DOWNLOAD_URL, self.FILENAME)
        return result is not None

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse gene family assignments from HGNC complete set."""
        filepath = self.source_dir / self.FILENAME
        if not filepath.exists():
            logger.error(f"HGNC file not found: {filepath}")
            return {}

        df = pd.read_csv(
            filepath, sep='\t',
            usecols=['symbol', 'gene_group', 'gene_group_id'],
            dtype=str, low_memory=False,
        )
        logger.info(f"HGNC raw: {len(df)} rows")

        # Keep only rows with gene family assignments
        df = df.dropna(subset=['gene_group', 'gene_group_id'])
        df = df[df['gene_group'].str.strip() != '']
        logger.info(f"HGNC rows with gene_group: {len(df)}")

        # Explode pipe-delimited gene_group and gene_group_id
        # Each gene can belong to multiple families: "FamA|FamB" / "1|2"
        df['gene_group'] = df['gene_group'].str.split('|')
        df['gene_group_id'] = df['gene_group_id'].str.split('|')
        df = df.explode(['gene_group', 'gene_group_id'])
        df['gene_group'] = df['gene_group'].str.strip()
        df['gene_group_id'] = df['gene_group_id'].str.strip()
        df = df[df['gene_group_id'] != '']
        logger.info(f"HGNC after explode: {len(df)} gene-family pairs")

        # Build GeneFamily nodes
        family_nodes = (
            df[['gene_group_id', 'gene_group']]
            .drop_duplicates(subset=['gene_group_id'])
            .rename(columns={
                'gene_group_id': 'familyId',
                'gene_group': 'familyName',
            })
        )
        family_nodes['sourceDatabase'] = 'HGNC'
        logger.info(f"HGNC Families: {len(family_nodes)} unique gene families")

        # Build gene-family edges (geneSymbol -> familyId)
        gene_family_edges = (
            df[['symbol', 'gene_group_id']]
            .drop_duplicates()
            .rename(columns={
                'symbol': 'geneSymbol',
                'gene_group_id': 'familyId',
            })
        )
        logger.info(
            f"HGNC Families: {len(gene_family_edges)} gene-family edges "
            f"({gene_family_edges['geneSymbol'].nunique()} genes, "
            f"{gene_family_edges['familyId'].nunique()} families)"
        )

        return {
            'gene_family_nodes': family_nodes,
            'gene_family_edges': gene_family_edges,
        }

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            'gene_family_nodes': {
                'familyId': 'HGNC gene group ID',
                'familyName': 'Gene family name',
                'sourceDatabase': 'Source database identifier',
            },
            'gene_family_edges': {
                'geneSymbol': 'HGNC approved gene symbol',
                'familyId': 'HGNC gene group ID',
            },
        }
