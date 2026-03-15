"""
ReactomeParser: Parser for Reactome pathway database.

Downloads NCBI-to-Reactome mapping for human pathways and produces
Pathway nodes and geneInPathway relationship edges.

Source: https://reactome.org/download/current/NCBI2Reactome_All_Levels.txt
Access: Public (no credentials required)
License: CC BY 4.0
"""

import logging
from typing import Dict, Optional

import pandas as pd

from .base_parser import BaseParser

logger = logging.getLogger(__name__)

COLUMNS = [
    'ncbi_gene_id', 'reactome_id', 'url', 'pathway_name',
    'evidence_code', 'species',
]


class ReactomeParser(BaseParser):
    """Parser for Reactome pathway data (human only)."""

    DOWNLOAD_URL = "https://reactome.org/download/current/NCBI2Reactome_All_Levels.txt"
    FILENAME = "NCBI2Reactome_All_Levels.txt"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download NCBI-to-Reactome mapping file."""
        logger.info("Downloading Reactome data...")
        result = self.download_file(self.DOWNLOAD_URL, self.FILENAME)
        return result is not None

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse Reactome data into pathway nodes and gene-pathway edges."""
        filepath = self.source_dir / self.FILENAME
        if not filepath.exists():
            logger.error(f"Reactome file not found: {filepath}")
            return {}

        df = pd.read_csv(
            filepath, sep='\t', header=None, names=COLUMNS, dtype=str,
        )
        logger.info(f"Reactome raw: {len(df)} rows")

        # Filter to human only
        df = df[df['species'] == 'Homo sapiens']
        logger.info(f"Reactome human: {len(df)} rows")

        # Build pathway nodes (merge key is pathwayName due to Neo4j constraint)
        pathway_nodes = (
            df[['pathway_name']]
            .drop_duplicates(subset=['pathway_name'])
            .rename(columns={
                'pathway_name': 'pathwayName',
            })
        )
        pathway_nodes['sourceDatabase'] = 'Reactome'
        logger.info(f"Reactome: {len(pathway_nodes)} unique pathways")

        # Build gene-pathway edges (match on pathway_name for Neo4j)
        gene_pathway = (
            df[['ncbi_gene_id', 'pathway_name', 'evidence_code']]
            .drop_duplicates(subset=['ncbi_gene_id', 'pathway_name'])
        )
        gene_pathway['source_database'] = 'Reactome'
        logger.info(
            f"Reactome: {len(gene_pathway)} gene-pathway edges "
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
                'pathwayId': 'Reactome stable ID (e.g., R-HSA-123456)',
                'pathwayName': 'Pathway name',
                'sourceDatabase': 'Source database identifier',
            },
            'gene_pathway': {
                'ncbi_gene_id': 'NCBI Entrez Gene ID',
                'reactome_id': 'Reactome stable ID',
                'evidence_code': 'Evidence code (IEA, TAS, etc.)',
                'source_database': 'Source database identifier',
            },
        }
