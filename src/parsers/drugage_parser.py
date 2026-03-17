"""
DrugAgeParser: Parser for DrugAge database (CellAge subset).

Downloads cell aging-related genes and their properties from the
DrugAge/CellAge database.

Source: https://genomics.senescence.info/cells/cellAge.zip
Access: Public (no credentials required)
License: Public domain
"""

import logging
from typing import Dict, Optional
import zipfile

import pandas as pd

from .base_parser import BaseParser

logger = logging.getLogger(__name__)


class DrugAgeParser(BaseParser):
    """Parser for DrugAge/CellAge cell aging genes database."""

    DOWNLOAD_URL = "https://genomics.senescence.info/cells/cellAge.zip"
    FILENAME = "cellAge.zip"
    TSV_FILENAME = "cellage3.tsv"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download CellAge ZIP file."""
        logger.info("Downloading DrugAge/CellAge data...")
        result = self.download_file(self.DOWNLOAD_URL, self.FILENAME)
        if result is None:
            return False

        # Extract the ZIP file
        try:
            zip_path = self.source_dir / self.FILENAME
            logger.info(f"Extracting ZIP file: {zip_path}")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.source_dir)
            logger.info("✓ ZIP file extracted successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to extract ZIP file: {e}")
            return False

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse CellAge TSV data into gene nodes and aging associations.

        CellAge columns: Entrez ID, Gene symbol, Gene name, Cancer Cell,
        Type of senescence, Senescence Effect, Reference
        """
        tsv_path = self.source_dir / self.TSV_FILENAME
        if not tsv_path.exists():
            tsv_files = list(self.source_dir.glob("*.tsv"))
            if not tsv_files:
                logger.error(f"No TSV file found in {self.source_dir}")
                return {}
            tsv_path = tsv_files[0]

        df = self.read_tsv(str(tsv_path))
        if df is None or df.empty:
            logger.error(f"Failed to read CellAge data: {tsv_path}")
            return {}

        logger.info(f"CellAge raw: {len(df)} rows, columns: {list(df.columns)}")

        # Gene nodes — merge with existing Gene nodes via Entrez ID
        gene_nodes = df[['Entrez ID', 'Gene symbol', 'Gene name']].drop_duplicates(
            subset=['Entrez ID']
        ).copy()
        gene_nodes = gene_nodes.rename(columns={
            'Entrez ID': 'geneId',
            'Gene symbol': 'geneName',
            'Gene name': 'geneFullName',
        })
        gene_nodes['geneId'] = gene_nodes['geneId'].astype(str)
        gene_nodes['sourceDatabase'] = 'DrugAge'
        logger.info(f"CellAge: {len(gene_nodes)} unique genes")

        # Gene-aging association edges (Senescence Effect: Induces/Inhibits/Unclear)
        aging_edges = df[['Entrez ID', 'Senescence Effect']].dropna(
            subset=['Senescence Effect']
        ).drop_duplicates().copy()
        aging_edges = aging_edges.rename(columns={
            'Entrez ID': 'geneId',
            'Senescence Effect': 'agingProperty',
        })
        aging_edges['geneId'] = aging_edges['geneId'].astype(str)
        logger.info(f"CellAge: {len(aging_edges)} gene-aging associations")

        # AgeingProperty nodes (Induces, Inhibits, Unclear)
        unique_props = aging_edges[['agingProperty']].drop_duplicates()
        unique_props = unique_props.rename(columns={'agingProperty': 'propertyName'})
        unique_props['sourceDatabase'] = 'DrugAge'
        logger.info(f"CellAge: {len(unique_props)} AgeingProperty nodes")

        return {
            'gene_nodes': gene_nodes,
            'aging_property_nodes': unique_props,
            'gene_aging_association': aging_edges,
        }

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            'gene_nodes': {
                'geneId': 'Gene identifier (NCBI Entrez Gene ID)',
                'geneName': 'Gene name or symbol',
                'sourceDatabase': 'Source database identifier (DrugAge)',
            },
            'gene_aging_association': {
                'geneId': 'Gene identifier',
                'agingProperty': 'Aging-related property or category',
                'source': 'Source database identifier',
            },
        }