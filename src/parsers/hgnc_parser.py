"""
HGNCParser: Parser for HUGO Gene Nomenclature Committee database.

Downloads the complete HGNC gene dataset and produces Gene nodes,
GeneFamily nodes, and geneInFamily relationship edges.

Source: https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt
Access: Public (no credentials required)
License: Creative Commons Attribution 4.0
"""

import logging
from typing import Dict, Optional

import pandas as pd

from .base_parser import BaseParser

logger = logging.getLogger(__name__)


class HGNCParser(BaseParser):
    """Parser for HGNC gene nomenclature data."""

    DOWNLOAD_URL = "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt"
    FILENAME = "hgnc_complete_set.txt"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download HGNC complete gene set."""
        logger.info("Downloading HGNC data...")
        result = self.download_file(self.DOWNLOAD_URL, self.FILENAME)
        return result is not None

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse HGNC data into gene nodes, family nodes, and relationships."""
        filepath = self.source_dir / self.FILENAME
        if not filepath.exists():
            logger.error(f"HGNC file not found: {filepath}")
            return {}

        # Read HGNC TSV
        df = self.read_tsv(str(filepath))
        if df is None or len(df) == 0:
            logger.error("Failed to read HGNC file or file is empty")
            return {}

        logger.info(f"HGNC raw: {len(df)} rows")

        # Build gene nodes
        gene_nodes = pd.DataFrame()
        gene_nodes['hgnc_id'] = df['hgnc_id'].fillna('').astype(str)
        gene_nodes['geneSymbol'] = df['symbol'].fillna('').astype(str)
        gene_nodes['geneName'] = df['name'].fillna('').astype(str)
        gene_nodes['sourceDatabase'] = 'HGNC'

        # Add cross-references
        gene_nodes['xrefNcbiGene'] = df['entrez_id'].fillna('').astype(str).replace('', None)
        gene_nodes['xrefEnsembl'] = df['ensembl_gene_id'].fillna('').astype(str).replace('', None)
        gene_nodes['xrefUcsc'] = df['ucsc_id'].fillna('').astype(str).replace('', None)
        gene_nodes['xrefRefseq'] = df['refseq_accession'].fillna('').astype(str).replace('', None)

        # Add gene location if available
        if 'location' in df.columns:
            gene_nodes['chromosomeLocation'] = df['location'].fillna('').astype(str).replace('', None)

        # Filter to rows with valid HGNC IDs and gene symbols
        gene_nodes = gene_nodes[
            (gene_nodes['hgnc_id'] != '') & 
            (gene_nodes['geneSymbol'] != '')
        ].drop_duplicates(subset=['hgnc_id'])

        logger.info(f"HGNC: {len(gene_nodes)} unique genes")

        # Build gene family nodes (if available)
        gene_family_nodes = pd.DataFrame()
        family_edges = pd.DataFrame()

        if 'gene_family' in df.columns:
            # Extract unique gene families
            family_df = df[
                (df['gene_family'].notna()) & 
                (df['gene_family'] != '')
            ][['gene_family']].drop_duplicates()
            
            if len(family_df) > 0:
                gene_family_nodes['familyName'] = family_df['gene_family'].astype(str)
                gene_family_nodes['sourceDatabase'] = 'HGNC'
                logger.info(f"HGNC: {len(gene_family_nodes)} unique gene families")

                # Build gene-family edges
                family_map_df = df[
                    (df['gene_family'].notna()) & 
                    (df['gene_family'] != '') &
                    (df['hgnc_id'].notna()) &
                    (df['hgnc_id'] != '')
                ][['hgnc_id', 'gene_family']].drop_duplicates()

                family_edges['hgnc_id'] = family_map_df['hgnc_id'].astype(str)
                family_edges['family_name'] = family_map_df['gene_family'].astype(str)
                family_edges['source_database'] = 'HGNC'
                
                logger.info(
                    f"HGNC: {len(family_edges)} gene-family edges "
                    f"({family_edges['hgnc_id'].nunique()} genes, "
                    f"{family_edges['family_name'].nunique()} families)"
                )

        result = {
            'gene_nodes': gene_nodes,
        }

        if len(gene_family_nodes) > 0:
            result['gene_family_nodes'] = gene_family_nodes

        if len(family_edges) > 0:
            result['gene_family_edges'] = family_edges

        return result

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            'gene_nodes': {
                'hgnc_id': 'HGNC ID (e.g., HGNC:1234)',
                'geneSymbol': 'Gene symbol (approved)',
                'geneName': 'Gene name (full)',
                'sourceDatabase': 'Source database identifier',
                'xrefNcbiGene': 'NCBI Entrez Gene ID',
                'xrefEnsembl': 'Ensembl Gene ID',
                'xrefUcsc': 'UCSC ID',
                'xrefRefseq': 'RefSeq accession',
                'chromosomeLocation': 'Chromosome location',
            },
            'gene_family_nodes': {
                'familyName': 'Gene family name',
                'sourceDatabase': 'Source database identifier',
            },
            'gene_family_edges': {
                'hgnc_id': 'HGNC ID',
                'family_name': 'Gene family name',
                'source_database': 'Source database identifier',
            },
        }