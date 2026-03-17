"""
CellAgeParser: Parser for CellAge cellular senescence database.

Downloads gene list and cellular senescence information from CellAge,
a curated list of genes associated with cellular senescence.

Source: https://genomics.senescence.info/cells/cellAge.zip
Access: Public (no credentials required)
License: CC BY 4.0
"""

import logging
import zipfile
from typing import Dict, Optional

import pandas as pd

from .base_parser import BaseParser

logger = logging.getLogger(__name__)


class CellAgeParser(BaseParser):
    """Parser for CellAge cellular senescence gene database."""

    DOWNLOAD_URL = "https://genomics.senescence.info/cells/cellAge.zip"
    FILENAME = "cellage.zip"
    EXTRACTED_FILENAME = "cellage3.tsv"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download CellAge ZIP file."""
        logger.info("Downloading CellAge data...")
        result = self.download_file(self.DOWNLOAD_URL, self.FILENAME)
        return result is not None

    def _extract_zip(self) -> Optional[str]:
        """
        Extract TSV file from ZIP archive.
        
        Returns:
            Path to extracted TSV file, or None if extraction failed
        """
        zip_path = self.source_dir / self.FILENAME
        
        if not zip_path.exists():
            logger.error(f"ZIP file not found: {zip_path}")
            return None
        
        try:
            logger.info(f"Extracting {zip_path}")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # List contents to find the TSV file
                file_list = zip_ref.namelist()
                logger.info(f"ZIP contents: {file_list}")
                
                # Extract all files
                zip_ref.extractall(self.source_dir)
            
            # Check for the extracted TSV
            tsv_path = self.source_dir / self.EXTRACTED_FILENAME
            if tsv_path.exists():
                logger.info(f"✓ Extracted to: {tsv_path}")
                return str(tsv_path)
            
            # If exact filename doesn't match, look for any .tsv file
            tsv_files = list(self.source_dir.glob("*.tsv"))
            if tsv_files:
                logger.info(f"Found TSV files: {tsv_files}")
                return str(tsv_files[0])
            
            logger.error("No TSV file found in archive")
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract {zip_path}: {e}")
            return None

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse CellAge data into gene nodes and senescence properties."""
        
        # Extract ZIP file
        tsv_path = self._extract_zip()
        if not tsv_path:
            logger.error("Could not extract CellAge TSV file")
            return {}
        
        # Read TSV with automatic header detection
        try:
            df = pd.read_csv(tsv_path, sep='\t', dtype=str, low_memory=False)
        except Exception as e:
            logger.error(f"Failed to read {tsv_path}: {e}")
            return {}
        
        logger.info(f"CellAge raw: {len(df)} rows")
        logger.info(f"Columns: {list(df.columns)}")
        
        if df.empty:
            logger.warning("CellAge data is empty")
            return {}
        
        # Normalize column names (lowercase, strip whitespace)
        df.columns = df.columns.str.strip().str.lower()
        
        # Identify key columns (handle various naming conventions)
        gene_col = None
        for col in df.columns:
            if 'gene' in col or 'symbol' in col or 'name' in col:
                gene_col = col
                break
        
        if not gene_col:
            logger.error(f"Could not identify gene column. Available: {list(df.columns)}")
            return {}
        
        logger.info(f"Using '{gene_col}' as gene identifier")
        
        # Remove empty rows
        df = df.dropna(subset=[gene_col])
        df = df[df[gene_col].astype(str).str.strip() != '']
        
        logger.info(f"CellAge after removing empty rows: {len(df)} rows")
        
        if df.empty:
            logger.warning("No valid gene entries in CellAge")
            return {}
        
        # Build gene nodes
        gene_nodes = df[[gene_col]].drop_duplicates()
        gene_nodes = gene_nodes.rename(columns={gene_col: 'geneSymbol'})
        gene_nodes['geneSymbol'] = gene_nodes['geneSymbol'].astype(str).str.strip()
        gene_nodes = gene_nodes.drop_duplicates(subset=['geneSymbol'])
        gene_nodes['sourceDatabase'] = 'CellAge'
        
        # Add additional properties if available
        if len(df.columns) > 1:
            # Create a comprehensive gene property table
            gene_properties = df.copy()
            gene_properties = gene_properties.rename(columns={gene_col: 'geneSymbol'})
            gene_properties['geneSymbol'] = gene_properties['geneSymbol'].astype(str).str.strip()
            gene_properties['sourceDatabase'] = 'CellAge'
        else:
            gene_properties = gene_nodes.copy()
        
        logger.info(f"CellAge: {len(gene_nodes)} unique genes")
        
        return {
            'gene_nodes': gene_nodes,
            'gene_properties': gene_properties,
        }

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            'gene_nodes': {
                'geneSymbol': 'HGNC gene symbol or identifier',
                'sourceDatabase': 'Source database identifier',
            },
            'gene_properties': {
                'geneSymbol': 'HGNC gene symbol or identifier',
                'sourceDatabase': 'Source database identifier',
            },
        }