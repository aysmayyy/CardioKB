"""
NCBIGeneParser: Parser for NCBI Gene data.

NCBI Gene provides comprehensive gene information for multiple organisms.
For CardioKB, we focus on human genes (Homo sapiens).

Source: https://ftp.ncbi.nlm.nih.gov/gene/DATA/GENE_INFO/Mammalia/

Adapted from AlzKB (disease-agnostic).
"""

import logging
import pandas as pd

from typing import Dict, Optional
from pathlib import Path
from .base_parser import BaseParser
from ..ontology_configs import NCBI_GENES

logger = logging.getLogger(__name__)


class NCBIGeneParser(BaseParser):
    """
    Parser for NCBI Gene data.

    Downloads and parses human gene information from NCBI.
    Optionally filters genes based on tissue expression using Bgee data.
    """

    GENE_INFO_URL = "https://ftp.ncbi.nlm.nih.gov/gene/DATA/GENE_INFO/Mammalia/Homo_sapiens.gene_info.gz"
    GENE_INFO_FILE = "Homo_sapiens.gene_info"
    BGEE_URL = "https://bgee.org/ftp/bgee_v15_0/download/calls/expr_calls/Homo_sapiens_expr_advanced.tsv.gz"
    BGEE_FILE = "Homo_sapiens_expr_advanced.tsv"

    def __init__(self, data_dir: str, tissue_filter: Optional[str] = None):
        """
        Initialize NCBI Gene parser.

        Args:
            data_dir: Directory for storing data files
            tissue_filter: Optional tissue name to filter genes by expression (e.g., "heart")
        """
        super().__init__(data_dir)
        self.tissue_filter = tissue_filter
        if self.tissue_filter:
            logger.info(f"Gene filtering enabled for tissue: {self.tissue_filter}")

    def download_data(self) -> bool:
        """
        Download NCBI Gene data.

        Returns:
            True if successful, False otherwise.
        """
        logger.info("Downloading NCBI Gene data...")

        gene_info_gz = self.download_file(self.GENE_INFO_URL, Path(self.GENE_INFO_URL).name)
        if not gene_info_gz:
            logger.error("Failed to download NCBI gene info file")
            return False

        gene_info_file = self.extract_gzip(gene_info_gz)
        if not gene_info_file:
            logger.error("Failed to extract NCBI gene info file")
            return False

        # Optionally download Bgee expression data
        logger.info("Attempting to download Bgee expression data (optional)...")
        try:
            bgee_gz = self.download_file(self.BGEE_URL, Path(self.BGEE_URL).name)
            if bgee_gz:
                self.extract_gzip(bgee_gz)
        except Exception as e:
            logger.warning(f"Could not download Bgee data (optional): {e}")

        return True

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse NCBI Gene data.

        Returns:
            Dictionary with 'genes' DataFrame.
        """
        logger.info("Parsing NCBI Gene data...")

        result = {}
        gene_info_file = self.get_file_path(self.GENE_INFO_FILE)

        if not Path(gene_info_file).exists():
            logger.error(f"NCBI gene info file not found: {gene_info_file}")
            return {}

        columns = [
            'tax_id', 'GeneID', 'Symbol', 'LocusTag', 'Synonyms', 'dbXrefs',
            'chromosome', 'map_location', 'description', 'type_of_gene',
            'Symbol_from_nomenclature_authority',
            'Full_name_from_nomenclature_authority',
            'Nomenclature_status', 'Other_designations',
            'Modification_date', 'Feature_type'
        ]

        genes_df = self.read_tsv(gene_info_file, names=columns, skiprows=1,
                                 low_memory=False)

        if genes_df is not None:
            genes_df = genes_df[genes_df['tax_id'] == 9606].copy()
            logger.info(f"Parsed {len(genes_df)} human genes")

            gene_types = genes_df['type_of_gene'].value_counts()
            logger.info(f"Gene types: {dict(gene_types)}")

            genes_df = self.parse_dbxrefs(genes_df)

            if self.tissue_filter:
                genes_df = self.filter_genes_by_tissue(genes_df, self.tissue_filter)

            genes_df['source_database'] = 'NCBI Gene'
            result[NCBI_GENES] = genes_df

        return result

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """Get the schema for NCBI Gene data."""
        return {
            NCBI_GENES: {
                'GeneID': 'NCBI Gene ID',
                'Symbol': 'Gene symbol',
                'description': 'Gene description',
                'type_of_gene': 'Type of gene (protein-coding, ncRNA, etc.)',
                'chromosome': 'Chromosome location',
                'dbXrefs': 'Cross-references to other databases',
                'xref_MIM': 'MIM (OMIM) identifier',
                'xref_HGNC': 'HGNC identifier',
                'xref_Ensembl': 'Ensembl gene identifier',
                'Synonyms': 'Alternative gene symbols',
                'Full_name_from_nomenclature_authority': 'Official full name',
                'source_database': 'Source database (NCBI Gene)',
            }
        }

    def parse_dbxrefs(self, genes_df: pd.DataFrame) -> pd.DataFrame:
        """Parse the dbXrefs column to extract cross-references."""
        logger.info("Parsing database cross-references...")
        df = genes_df.copy()

        dbs_to_extract = ['MIM', 'HGNC', 'Ensembl']
        for db in dbs_to_extract:
            df[f'xref_{db}'] = df['dbXrefs'].str.extract(
                f'{db}:([^|]+)', expand=False
            )

        logger.info("Parsed cross-references")
        return df

    def filter_genes_by_tissue(self, genes_df: pd.DataFrame, tissue_name: str) -> pd.DataFrame:
        """
        Filter genes based on tissue expression from Bgee data.

        Args:
            genes_df: DataFrame of all genes
            tissue_name: Name of tissue to filter by (e.g., "heart")

        Returns:
            Filtered DataFrame of genes expressed in the specified tissue
        """
        logger.info(f"Filtering for genes expressed in '{tissue_name}'...")

        bgee_file = Path(self.get_file_path(self.BGEE_FILE))
        if not bgee_file.exists():
            logger.warning(f"Bgee file not found at {bgee_file}")
            logger.warning("Tissue filtering requires Bgee data. Returning unfiltered genes.")
            return genes_df

        try:
            tissue_gene_ids = set()
            logger.info(f"Reading Bgee expression file: {bgee_file}")
            with open(bgee_file, 'r', encoding='utf-8') as f:
                next(f, None)
                for line in f:
                    if tissue_name.lower() in line.lower():
                        parts = line.split('\t')
                        if parts:
                            gene_id = parts[0].strip()
                            if gene_id:
                                tissue_gene_ids.add(gene_id)

            logger.info(f"Found {len(tissue_gene_ids)} unique Ensembl gene IDs expressed in '{tissue_name}'")

            if not tissue_gene_ids:
                logger.warning(f"No genes found with '{tissue_name}' expression in Bgee data")
                return genes_df

            if 'xref_Ensembl' not in genes_df.columns:
                logger.error("xref_Ensembl column not found. Expected parse_dbxrefs() to be called first.")
                return genes_df

            filtered_genes = genes_df[
                genes_df['xref_Ensembl'].isin(tissue_gene_ids)
            ].copy()

            logger.info(f"Filtered to {len(filtered_genes)} genes expressed in '{tissue_name}'")
            return filtered_genes

        except Exception as e:
            logger.error(f"Error filtering genes by tissue: {e}")
            return genes_df
