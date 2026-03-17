"""
GenAgeParser: Parser for the GenAge database of aging-related genes.

Downloads human aging genes from the GenAge database and produces
Gene nodes with aging-related annotations.

Source: https://genomics.senescence.info/genes/human_genes.zip
Access: Public (no credentials required)
License: CC BY 4.0
"""

import logging
import zipfile
from typing import Dict, Optional

import pandas as pd

from .base_parser import BaseParser

logger = logging.getLogger(__name__)


class GenAgeParser(BaseParser):
    """Parser for GenAge human aging genes database."""

    DOWNLOAD_URL = "https://genomics.senescence.info/genes/human_genes.zip"
    FILENAME = "human_genes.zip"
    CSV_FILENAME = "genage_human.csv"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download GenAge human genes ZIP file."""
        logger.info("Downloading GenAge data...")
        result = self.download_file(self.DOWNLOAD_URL, self.FILENAME)
        return result is not None

    def _extract_zip_and_get_csv(self) -> Optional[str]:
        """
        Extract the ZIP file and return path to the CSV file.
        
        Returns:
            Path to extracted CSV file, or None if failed
        """
        zip_path = self.source_dir / self.FILENAME
        if not zip_path.exists():
            logger.error(f"ZIP file not found: {zip_path}")
            return None

        try:
            # Extract ZIP
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Find the CSV file in the ZIP
                csv_files = [f for f in zip_ref.namelist() if f.endswith('.csv')]
                if not csv_files:
                    logger.error("No CSV file found in ZIP")
                    return None
                
                csv_name = csv_files[0]
                logger.info(f"Found CSV in ZIP: {csv_name}")
                
                # Extract to source_dir
                extracted_path = zip_ref.extract(csv_name, self.source_dir)
                logger.info(f"✓ Extracted to: {extracted_path}")
                return extracted_path

        except Exception as e:
            logger.error(f"Failed to extract ZIP: {e}")
            return None

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse GenAge data into gene nodes and aging annotations."""
        # Extract ZIP and get CSV path
        csv_path = self._extract_zip_and_get_csv()
        if not csv_path:
            logger.error("Failed to extract CSV from ZIP")
            return {}

        # Read CSV with automatic delimiter detection
        try:
            df = pd.read_csv(csv_path, dtype=str)
            logger.info(f"GenAge raw: {len(df)} rows, {len(df.columns)} columns")
            logger.info(f"Columns: {list(df.columns)}")
        except Exception as e:
            logger.error(f"Failed to read CSV: {e}")
            return {}

        if df.empty:
            logger.warning("GenAge CSV is empty")
            return {}

        # Detect gene ID column (common names: gene_id, Gene ID, EntrezID, etc.)
        gene_id_col = None
        gene_symbol_col = None
        
        for col in df.columns:
            col_lower = col.lower().strip()
            if any(x in col_lower for x in ['gene_id', 'entrez', 'ncbi']):
                gene_id_col = col
            elif any(x in col_lower for x in ['symbol', 'gene_name', 'gene symbol']):
                gene_symbol_col = col

        if not gene_id_col and not gene_symbol_col:
            logger.warning("Could not identify gene ID or symbol column")
            logger.info("Available columns: " + ", ".join(df.columns))
            # Use first column as fallback
            gene_id_col = df.columns[0]

        logger.info(f"Using gene ID column: {gene_id_col}")
        if gene_symbol_col:
            logger.info(f"Using gene symbol column: {gene_symbol_col}")

        # Build gene nodes
        gene_nodes = pd.DataFrame()
        
        # Create IRI from gene symbol if available, otherwise use gene ID
        if gene_symbol_col and gene_symbol_col in df.columns:
            gene_nodes['geneSymbol'] = df[gene_symbol_col].astype(str).str.strip()
        elif gene_id_col and gene_id_col in df.columns:
            gene_nodes['geneSymbol'] = df[gene_id_col].astype(str).str.strip()
        else:
            logger.error("Cannot create gene nodes: missing both gene ID and symbol")
            return {}

        # Add NCBI Gene ID reference if available
        if gene_id_col and gene_id_col in df.columns:
            gene_nodes['xrefNcbiGene'] = df[gene_id_col].astype(str).str.strip()
        
        # Add aging-related annotations if available
        for col in df.columns:
            col_lower = col.lower().strip()
            # Skip ID/symbol columns already handled
            if any(x in col_lower for x in ['gene_id', 'symbol', 'gene_name', 'entrez']):
                continue
            
            # Add other columns as properties (aging type, longevity influence, etc.)
            if col in df.columns:
                gene_nodes[col] = df[col].astype(str).str.strip()

        # Drop duplicates on gene symbol
        gene_nodes = gene_nodes.drop_duplicates(subset=['geneSymbol'])
        gene_nodes['sourceDatabase'] = 'GenAge'
        
        logger.info(f"GenAge: {len(gene_nodes)} unique genes")

        return {
            'gene_nodes': gene_nodes,
        }

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            'gene_nodes': {
                'geneSymbol': 'Gene symbol or NCBI Entrez Gene ID',
                'xrefNcbiGene': 'NCBI Entrez Gene ID (cross-reference)',
                'sourceDatabase': 'Source database identifier',
            },
        }