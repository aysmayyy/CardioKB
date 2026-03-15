"""
WikiPathwaysParser: Parser for WikiPathways GMT data.

Downloads the human GMT file and produces Pathway nodes and geneInPathway edges.
GMT format: pathway_name<TAB>pathway_id<TAB>gene1<TAB>gene2<TAB>...

Source: https://data.wikipathways.org/current/gmt/
Access: Public (no credentials required)
License: CC BY 3.0
"""

import logging
import re
from typing import Dict, Optional

import pandas as pd
import requests

from .base_parser import BaseParser

logger = logging.getLogger(__name__)


class WikiPathwaysParser(BaseParser):
    """Parser for WikiPathways GMT data (human only)."""

    INDEX_URL = "https://data.wikipathways.org/current/gmt/"
    FILENAME = "wikipathways-gmt-Homo_sapiens.gmt"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download WikiPathways GMT file (auto-discovers dated filename)."""
        logger.info("Downloading WikiPathways data...")

        # Check for existing file first
        if (self.source_dir / self.FILENAME).exists():
            logger.info(f"File already exists: {self.source_dir / self.FILENAME}")
            return True

        # Discover actual filename from index page
        try:
            resp = requests.get(self.INDEX_URL, timeout=30)
            resp.raise_for_status()
            match = re.search(r'(wikipathways-\d+-gmt-Homo_sapiens\.gmt)', resp.text)
            if not match:
                logger.error("Could not find WikiPathways GMT filename in index")
                return False
            actual_filename = match.group(1)
            url = f"{self.INDEX_URL}{actual_filename}"
        except Exception as e:
            logger.error(f"Failed to discover WikiPathways URL: {e}")
            return False

        result = self.download_file(url, self.FILENAME)
        return result is not None

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse GMT file into pathway nodes and gene-pathway edges."""
        filepath = self.source_dir / self.FILENAME
        if not filepath.exists():
            logger.error(f"WikiPathways file not found: {filepath}")
            return {}

        pathway_rows = []
        edge_rows = []

        with open(filepath, 'r') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) < 3:
                    continue
                # GMT: col0 = "Name%WikiPathways_DATE%WPID%Homo sapiens"
                # col1 = URL, col2+ = Entrez Gene IDs
                name_field = parts[0]
                gene_ids = parts[2:]

                # Parse name field
                name_parts = name_field.split('%')
                pathway_name = name_parts[0] if name_parts else name_field

                pathway_rows.append({
                    'pathwayName': pathway_name,
                    'sourceDatabase': 'WikiPathways',
                })

                for gid in gene_ids:
                    gid = gid.strip()
                    if gid:
                        edge_rows.append({
                            'ncbi_gene_id': gid,
                            'pathway_name': pathway_name,
                            'source_database': 'WikiPathways',
                        })

        pathway_nodes = pd.DataFrame(pathway_rows).drop_duplicates(subset=['pathwayName'])
        gene_pathway = pd.DataFrame(edge_rows).drop_duplicates(
            subset=['ncbi_gene_id', 'pathway_name']
        )

        logger.info(f"WikiPathways: {len(pathway_nodes)} pathways")
        logger.info(
            f"WikiPathways: {len(gene_pathway)} gene-pathway edges "
            f"({gene_pathway['ncbi_gene_id'].nunique()} genes, "
            f"{gene_pathway['pathway_name'].nunique()} pathways)"
        )

        return {
            'pathway_nodes': pathway_nodes,
            'gene_pathway': gene_pathway,
        }

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            'pathway_nodes': {
                'pathwayName': 'Pathway name',
                'sourceDatabase': 'Source database identifier',
            },
            'gene_pathway': {
                'ncbi_gene_id': 'NCBI Entrez Gene ID',
                'pathway_name': 'Pathway name',
                'source_database': 'Source database identifier',
            },
        }
