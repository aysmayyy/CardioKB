"""
ClinVarParser: Parser for ClinVar variant database.

Downloads ClinVar variant summary data and produces Variant nodes,
Variant-Disease relationships, and Variant-Gene relationships.

Source: https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz
Access: Public (no credentials required)
License: Public domain (NCBI)
"""

import logging
from typing import Dict, Optional

import pandas as pd

from .base_parser import BaseParser

logger = logging.getLogger(__name__)


class ClinVarParser(BaseParser):
    """Parser for ClinVar variant data."""

    DOWNLOAD_URL = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz"
    FILENAME = "variant_summary.txt.gz"
    EXTRACTED_FILENAME = "variant_summary.txt"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download ClinVar variant summary file."""
        logger.info("Downloading ClinVar data...")
        result = self.download_file(self.DOWNLOAD_URL, self.FILENAME)
        if result is None:
            return False

        # Extract gzip file
        extracted = self.extract_gzip(result)
        return extracted is not None

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse ClinVar data into variants, variant-disease, and variant-gene relationships."""
        filepath = self.source_dir / self.EXTRACTED_FILENAME
        if not filepath.exists():
            logger.error(f"ClinVar file not found: {filepath}")
            return {}

        # Read the entire file
        df = pd.read_csv(
            filepath, sep='\t', dtype=str, low_memory=False
        )
        logger.info(f"ClinVar raw: {len(df)} rows, {len(df.columns)} columns")

        # Keep only rows with ClinVar accession (valid variants)
        df = df.dropna(subset=['#Allele ID'])
        logger.info(f"ClinVar with accessions: {len(df)} rows")

        # Build variant nodes
        variant_nodes = self._build_variant_nodes(df)
        logger.info(f"ClinVar: {len(variant_nodes)} unique variants")

        # Build variant-disease relationships
        variant_disease = self._build_variant_disease_edges(df)
        logger.info(f"ClinVar: {len(variant_disease)} variant-disease relationships")

        # Build variant-gene relationships
        variant_gene = self._build_variant_gene_edges(df)
        logger.info(f"ClinVar: {len(variant_gene)} variant-gene relationships")

        return {
            'variant_nodes': variant_nodes,
            'variant_disease': variant_disease,
            'variant_gene': variant_gene,
        }

    def _build_variant_nodes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Build variant nodes from ClinVar data."""
        # Select relevant columns and rename
        variant_cols = ['#Allele ID', 'Chromosome', 'Start', 'Stop', 'ReferenceAllele', 
                       'AlternateAllele', 'Variation ID', 'Type', 'Assembly']
        
        # Use only columns that exist
        available_cols = [col for col in variant_cols if col in df.columns]
        variants = df[available_cols].copy()
        
        # Keep unique variants by Allele ID
        variants = variants.drop_duplicates(subset=['#Allele ID'])
        
        # Rename columns for consistency
        variants = variants.rename(columns={
            '#Allele ID': 'clinvarAlleleId',
            'Variation ID': 'variationId',
            'Type': 'variantType',
            'Chromosome': 'chromosome',
            'Start': 'start',
            'Stop': 'stop',
            'ReferenceAllele': 'referenceAllele',
            'AlternateAllele': 'alternateAllele',
            'Assembly': 'assembly',
        })
        
        # Add source
        variants['sourceDatabase'] = 'ClinVar'
        
        # Ensure clinvarAlleleId is string and handle NaN
        variants['clinvarAlleleId'] = variants['clinvarAlleleId'].fillna('').astype(str)
        
        # Keep only non-empty IDs
        variants = variants[variants['clinvarAlleleId'] != '']
        
        return variants

    def _build_variant_disease_edges(self, df: pd.DataFrame) -> pd.DataFrame:
        """Build variant-disease relationship edges."""
        # ClinVar has Condition(s) column with disease info
        if 'Condition(s)' not in df.columns:
            logger.warning("Condition(s) column not found in ClinVar data")
            return pd.DataFrame()
        
        edges_list = []
        
        for _, row in df.iterrows():
            allele_id = str(row.get('#Allele ID', '')).strip()
            conditions = str(row.get('Condition(s)', '')).strip()
            clinical_sig = str(row.get('ClinicalSignificance', '')).strip()
            review_status = str(row.get('ReviewStatus', '')).strip()
            
            # Skip if missing key data
            if not allele_id or allele_id == 'nan' or not conditions or conditions == '-':
                continue
            
            # Split multiple conditions (sometimes separated by semicolon or pipe)
            condition_list = [c.strip() for c in conditions.split(';') if c.strip()]
            
            for condition in condition_list:
                if condition and condition != '-' and condition != '':
                    edges_list.append({
                        'clinvarAlleleId': allele_id,
                        'condition': condition,
                        'clinicalSignificance': clinical_sig if clinical_sig != '-' else '',
                        'reviewStatus': review_status if review_status != '-' else '',
                    })
        
        variant_disease = pd.DataFrame(edges_list)
        
        if len(variant_disease) > 0:
            # Remove duplicates
            variant_disease = variant_disease.drop_duplicates(
                subset=['clinvarAlleleId', 'condition']
            )
            variant_disease['source_database'] = 'ClinVar'
        
        return variant_disease

    def _build_variant_gene_edges(self, df: pd.DataFrame) -> pd.DataFrame:
        """Build variant-gene relationship edges."""
        if 'GeneID' not in df.columns:
            logger.warning("GeneID column not found in ClinVar data")
            return pd.DataFrame()
        
        edges_list = []
        
        for _, row in df.iterrows():
            allele_id = str(row.get('#Allele ID', '')).strip()
            gene_id = str(row.get('GeneID', '')).strip()
            gene_symbol = str(row.get('GeneSymbol', '')).strip()
            
            # Skip if missing key data
            if not allele_id or allele_id == 'nan':
                continue
            
            if not gene_id or gene_id == '-' or gene_id == 'nan':
                continue
            
            edges_list.append({
                'clinvarAlleleId': allele_id,
                'geneId': gene_id,
                'geneSymbol': gene_symbol if gene_symbol and gene_symbol != '-' else '',
            })
        
        variant_gene = pd.DataFrame(edges_list)
        
        if len(variant_gene) > 0:
            # Remove duplicates
            variant_gene = variant_gene.drop_duplicates(
                subset=['clinvarAlleleId', 'geneId']
            )
            variant_gene['source_database'] = 'ClinVar'
        
        return variant_gene

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            'variant_nodes': {
                'clinvarAlleleId': 'ClinVar Allele ID (unique variant identifier)',
                'variationId': 'ClinVar Variation ID',
                'variantType': 'Type of variant (SNV, Indel, Deletion, etc.)',
                'chromosome': 'Chromosome',
                'start': 'Start position (0-based)',
                'stop': 'Stop position',
                'referenceAllele': 'Reference allele sequence',
                'alternateAllele': 'Alternate allele sequence',
                'assembly': 'Genome assembly version (GRCh37, GRCh38, etc.)',
                'sourceDatabase': 'Source database identifier',
            },
            'variant_disease': {
                'clinvarAlleleId': 'ClinVar Allele ID',
                'condition': 'Disease/phenotype name',
                'clinicalSignificance': 'Clinical significance (Pathogenic, Benign, VUS, etc.)',
                'reviewStatus': 'Review status and evidence level',
                'source_database': 'Source database identifier',
            },
            'variant_gene': {
                'clinvarAlleleId': 'ClinVar Allele ID',
                'geneId': 'NCBI Entrez Gene ID',
                'geneSymbol': 'Gene symbol/name',
                'source_database': 'Source database identifier',
            },
        }