"""
AnAgeParser: Parser for the AnAge (Animal Aging and Longevity) database.

Downloads species longevity and aging data from the senescence.info database.
Produces Species nodes and their aging-related properties.

Source: https://genomics.senescence.info/species/dataset.zip
Access: Public (no credentials required)
License: Creative Commons
"""

import logging
import zipfile
from typing import Dict, Optional

import pandas as pd

from .base_parser import BaseParser

logger = logging.getLogger(__name__)


class AnAgeParser(BaseParser):
    """Parser for AnAge species longevity and aging database."""

    DOWNLOAD_URL = "https://genomics.senescence.info/species/dataset.zip"
    ZIP_FILENAME = "dataset.zip"
    TSV_FILENAME = "anage_data.txt"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download AnAge ZIP file."""
        logger.info("Downloading AnAge data...")
        result = self.download_file(self.DOWNLOAD_URL, self.ZIP_FILENAME)
        if result is None:
            return False

        # Extract the ZIP file
        try:
            zip_path = self.source_dir / self.ZIP_FILENAME
            logger.info(f"Extracting ZIP file: {zip_path}")
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # List contents to find the actual TSV file
                file_list = zip_ref.namelist()
                logger.info(f"ZIP contents: {file_list}")
                
                # Extract all files to source_dir
                zip_ref.extractall(self.source_dir)
            
            logger.info(f"✓ Extracted ZIP file successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to extract ZIP file: {e}")
            return False

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse AnAge TSV data into species nodes."""
        # Try to find the TSV file
        tsv_path = self.source_dir / self.TSV_FILENAME
        
        # Also check if it might be in a subdirectory
        if not tsv_path.exists():
            # Look for any .txt files in the directory
            txt_files = list(self.source_dir.glob("**/*.txt"))
            if txt_files:
                tsv_path = txt_files[0]
                logger.info(f"Found TSV file: {tsv_path}")
            else:
                logger.error(f"AnAge TSV file not found: {tsv_path}")
                return {}
        
        try:
            # Read the TSV file
            df = pd.read_csv(tsv_path, sep='\t', dtype=str, low_memory=False)
            logger.info(f"AnAge raw: {len(df)} rows, columns: {list(df.columns)}")
            
            # Identify key columns (handle variations in naming)
            col_names = {col.lower().strip(): col for col in df.columns}
            
            # Get actual column names from the file
            actual_cols = df.columns.tolist()
            
            # Create species nodes with available data
            species_nodes = pd.DataFrame()
            
            # Use whatever identifying column is available
            # Common columns in AnAge: species, Common name, NCBI taxonomic ID, etc.
            if 'species' in col_names:
                species_nodes['speciesName'] = df[col_names['species']]
            elif any('species' in col.lower() for col in actual_cols):
                species_col = [col for col in actual_cols if 'species' in col.lower()][0]
                species_nodes['speciesName'] = df[species_col]
            elif any('common name' in col.lower() for col in actual_cols):
                name_col = [col for col in actual_cols if 'common name' in col.lower()][0]
                species_nodes['speciesName'] = df[name_col]
            else:
                # Use first column as fallback
                species_nodes['speciesName'] = df[actual_cols[0]]
            
            # Add NCBI taxonomic ID if available
            if any('ncbi' in col.lower() or 'taxonomy' in col.lower() for col in actual_cols):
                tax_col = [col for col in actual_cols if 'ncbi' in col.lower() or 'taxonomy' in col.lower()][0]
                species_nodes['ncbiTaxonomyId'] = df[tax_col]
            
            # Add maximum lifespan if available
            if any('max' in col.lower() and 'life' in col.lower() for col in actual_cols):
                lifespan_col = [col for col in actual_cols if 'max' in col.lower() and 'life' in col.lower()][0]
                species_nodes['maximumLifespan'] = df[lifespan_col]
            
            # Add sample size if available
            if any('sample' in col.lower() or 'n ' in col.lower() for col in actual_cols):
                sample_col = [col for col in actual_cols if 'sample' in col.lower() or 'n ' in col.lower()][0]
                species_nodes['sampleSize'] = df[sample_col]
            
            species_nodes['sourceDatabase'] = 'AnAge'
            
            # Remove duplicates on speciesName
            species_nodes = species_nodes.drop_duplicates(subset=['speciesName'])
            species_nodes = species_nodes.dropna(subset=['speciesName'])
            
            logger.info(f"AnAge: {len(species_nodes)} unique species")
            
            return {
                'species_nodes': species_nodes,
            }
            
        except Exception as e:
            logger.error(f"Failed to parse AnAge data: {e}")
            return {}

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            'species_nodes': {
                'speciesName': 'Species scientific or common name',
                'ncbiTaxonomyId': 'NCBI Taxonomy ID',
                'maximumLifespan': 'Maximum recorded lifespan (years)',
                'sampleSize': 'Sample size for longevity data',
                'sourceDatabase': 'Source database identifier',
            },
        }