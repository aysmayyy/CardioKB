"""
STRINGParser: Parser for STRING protein-protein interaction database.

Downloads human protein links and produces geneInteractsWithGene edges
filtered by combined confidence score > 700.

Source: https://string-db.org/
Access: Public (no credentials required)
License: CC BY 4.0
"""

import logging
from typing import Dict, Optional

import pandas as pd

from .base_parser import BaseParser

logger = logging.getLogger(__name__)


class STRINGParser(BaseParser):
    """Parser for STRING PPI data (human, high confidence)."""

    DOWNLOAD_URL = "https://stringdb-downloads.org/download/protein.links.v12.0/9606.protein.links.v12.0.txt.gz"
    GZ_FILENAME = "9606.protein.links.v12.0.txt.gz"
    FILENAME = "9606.protein.links.v12.0.txt"

    # STRING uses Ensembl protein IDs (ENSP). We need to map to gene symbols.
    # Download the aliases file to map ENSP -> gene symbol
    ALIASES_URL = "https://stringdb-downloads.org/download/protein.aliases.v12.0/9606.protein.aliases.v12.0.txt.gz"
    ALIASES_GZ = "9606.protein.aliases.v12.0.txt.gz"
    ALIASES_FILE = "9606.protein.aliases.v12.0.txt"

    MIN_CONFIDENCE = 700

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download STRING protein links and aliases files."""
        logger.info("Downloading STRING data...")

        links_gz = self.download_file(self.DOWNLOAD_URL, self.GZ_FILENAME)
        if not links_gz:
            return False
        self.extract_gzip(links_gz)

        aliases_gz = self.download_file(self.ALIASES_URL, self.ALIASES_GZ)
        if not aliases_gz:
            return False
        self.extract_gzip(aliases_gz)

        return True

    def _build_ensp_to_gene(self) -> Dict[str, str]:
        """Build ENSP -> gene symbol mapping from aliases file."""
        aliases_path = self.source_dir / self.ALIASES_FILE
        if not aliases_path.exists():
            logger.error(f"Aliases file not found: {aliases_path}")
            return {}

        # The aliases file has columns: string_protein_id, alias, source
        # We want BioMart_HUGO entries which give official gene symbols
        mapping = {}
        chunks = pd.read_csv(
            aliases_path, sep='\t', dtype=str,
            chunksize=500000,
        )
        for chunk in chunks:
            # Filter to BioMart_HUGO or Ensembl_HGNC sources for gene symbols
            hugo = chunk[chunk['source'].isin([
                'BioMart_HUGO', 'Ensembl_HGNC',
                'Ensembl_HGNC_symbol', 'BioMart_HUGO_symbol',
            ])]
            for _, row in hugo.iterrows():
                ensp = row.iloc[0]  # string_protein_id (e.g., 9606.ENSP00000000233)
                symbol = row.iloc[1]  # alias (gene symbol)
                if ensp and symbol and symbol.strip():
                    mapping[ensp] = symbol.strip()

        logger.info(f"STRING: mapped {len(mapping)} ENSP IDs to gene symbols")
        return mapping

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse STRING data into gene-gene interaction edges."""
        filepath = self.source_dir / self.FILENAME
        if not filepath.exists():
            logger.error(f"STRING file not found: {filepath}")
            return {}

        # Build ENSP -> gene symbol mapping
        ensp_to_gene = self._build_ensp_to_gene()
        if not ensp_to_gene:
            logger.error("Failed to build ENSP to gene mapping")
            return {}

        # Read protein links (space-separated)
        df = pd.read_csv(filepath, sep=' ', dtype={'combined_score': int})
        logger.info(f"STRING raw: {len(df)} interactions")

        # Filter by confidence score
        df = df[df['combined_score'] >= self.MIN_CONFIDENCE]
        logger.info(f"STRING confidence >= {self.MIN_CONFIDENCE}: {len(df)} interactions")

        # Map ENSP IDs to gene symbols
        df['gene_symbol_a'] = df['protein1'].map(ensp_to_gene)
        df['gene_symbol_b'] = df['protein2'].map(ensp_to_gene)

        # Drop unmapped
        before = len(df)
        df = df.dropna(subset=['gene_symbol_a', 'gene_symbol_b'])
        logger.info(f"STRING mapped: {len(df)} interactions ({before - len(df)} unmapped)")

        # Remove self-interactions
        df = df[df['gene_symbol_a'] != df['gene_symbol_b']]

        # Normalize direction (alphabetical) to avoid duplicates
        mask = df['gene_symbol_a'] > df['gene_symbol_b']
        df.loc[mask, ['gene_symbol_a', 'gene_symbol_b']] = (
            df.loc[mask, ['gene_symbol_b', 'gene_symbol_a']].values
        )
        df = df.drop_duplicates(subset=['gene_symbol_a', 'gene_symbol_b'])

        result = df[['gene_symbol_a', 'gene_symbol_b', 'combined_score']].copy()
        result['source_database'] = 'STRING'

        logger.info(
            f"STRING: {len(result)} unique gene-gene interactions "
            f"({result['gene_symbol_a'].nunique() + result['gene_symbol_b'].nunique()} genes)"
        )

        return {
            'gene_interacts_gene': result,
        }

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            'gene_interacts_gene': {
                'gene_symbol_a': 'Gene symbol A',
                'gene_symbol_b': 'Gene symbol B',
                'combined_score': 'STRING combined confidence score (0-1000)',
                'source_database': 'Source database identifier',
            },
        }
