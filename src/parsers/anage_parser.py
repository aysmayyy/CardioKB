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

    # Known AnAge column names (from anage_data.txt header)
    KNOWN_COLUMNS = {
        'hagrid': 'HAGRID',
        'genus': 'Genus',
        'species': 'Species',
        'common name': 'Common name',
        'maximum longevity (yrs)': 'Maximum longevity (yrs)',
        'sample size': 'Sample size',
    }

    def _find_col(self, df: pd.DataFrame, target: str) -> str:
        """Find a column by case-insensitive match. Returns '' if not found."""
        col_map = {col.lower().strip(): col for col in df.columns}
        return col_map.get(target.lower().strip(), '')

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse AnAge TSV data into species nodes."""
        tsv_path = self.source_dir / self.TSV_FILENAME

        if not tsv_path.exists():
            txt_files = list(self.source_dir.glob("**/*.txt"))
            if txt_files:
                tsv_path = txt_files[0]
                logger.info(f"Found TSV file: {tsv_path}")
            else:
                logger.error(f"AnAge TSV file not found: {tsv_path}")
                return {}

        try:
            df = pd.read_csv(tsv_path, sep='\t', dtype=str, low_memory=False)
            logger.info(f"AnAge raw: {len(df)} rows, columns: {list(df.columns)}")

            species_nodes = pd.DataFrame()

            # Build full binomial name from Genus + Species columns
            genus_col = self._find_col(df, 'Genus')
            species_col = self._find_col(df, 'Species')
            common_col = self._find_col(df, 'Common name')

            if genus_col and species_col:
                species_nodes['speciesName'] = (
                    df[genus_col].fillna('').str.strip()
                    + ' '
                    + df[species_col].fillna('').str.strip()
                ).str.strip()
            elif species_col:
                species_nodes['speciesName'] = df[species_col]
            else:
                logger.error("AnAge: no Genus/Species columns found")
                return {}

            if common_col:
                species_nodes['commonName'] = df[common_col]

            # Maximum longevity
            lifespan_col = self._find_col(df, 'Maximum longevity (yrs)')
            if lifespan_col:
                species_nodes['maximumLifespan'] = df[lifespan_col]

            # Sample size
            sample_col = self._find_col(df, 'Sample size')
            if sample_col:
                species_nodes['sampleSize'] = df[sample_col]

            species_nodes['sourceDatabase'] = 'AnAge'

            species_nodes = species_nodes.drop_duplicates(subset=['speciesName'])
            species_nodes = species_nodes.dropna(subset=['speciesName'])
            species_nodes = species_nodes[species_nodes['speciesName'] != '']

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
                'speciesName': 'Binomial species name (Genus species)',
                'commonName': 'Common name',
                'maximumLifespan': 'Maximum recorded lifespan (years)',
                'sampleSize': 'Sample size for longevity data',
                'sourceDatabase': 'Source database identifier',
            },
        }