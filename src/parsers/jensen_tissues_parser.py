"""
Jensen TISSUES Parser for the knowledge graph.

Downloads the Jensen TISSUES experiment-based gene-tissue association file
and produces geneExpressedInBodyPart edges.

Data Source:
  https://download.jensenlab.org/human_tissue_experiments_full.tsv

Output:
  - tissue_gene_associations.tsv : geneExpressedInBodyPart edges
    Columns: gene_id, gene_symbol, tissue_id, tissue_name, score,
             evidence_type, source_database
"""

import logging
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from .base_parser import BaseParser

logger = logging.getLogger(__name__)

_DEFAULT_URL = "https://download.jensenlab.org/human_tissue_experiments_full.tsv"
_FILENAME    = "human_tissue_experiments_full.tsv"
# Alternate URL (from databases.yaml - without _full suffix, try full version)
_ALT_URL     = "https://download.jensenlab.org/human_tissue_experiments_full.tsv"

TISSUE_GENE_OUTPUT = "tissue_gene_associations"

# Minimum confidence score to retain (Jensen TISSUES scores are 0–5)
_MIN_SCORE = 2.0


class JensenTissuesParser(BaseParser):
    """
    Parser for Jensen TISSUES experiment-based gene expression data.

    Downloads and parses the human tissue experiments file from the Jensen Lab,
    producing geneExpressedInBodyPart relationship data.

    Constructor args (injected from databases.yaml):
        data_dir   – base directory for raw/cached files
        source_url – URL of the Jensen TISSUES TSV file
    """

    def __init__(self, data_dir: str, source_url: Optional[str] = None):
        super().__init__(data_dir)
        self.source_name = "jensen_tissues"
        self.source_dir = self.data_dir / self.source_name
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.source_url = source_url or _DEFAULT_URL

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download_data(self) -> bool:
        # Always use the _full version URL regardless of what databases.yaml says
        url = _DEFAULT_URL
        logger.info("Downloading Jensen TISSUES data from %s ...", url)
        result = self.download_file(url, _FILENAME)
        if not result:
            logger.error("Failed to download Jensen TISSUES file.")
            return False
        return True

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        filepath = self.source_dir / _FILENAME
        if not filepath.exists():
            logger.error("Jensen TISSUES file not found: %s", filepath)
            return {}

        logger.info("Parsing Jensen TISSUES from %s ...", filepath)

        # The actual file format (tab-separated, no header, 7 columns):
        # ensembl_protein_id  gene_symbol  tissue_id  tissue_name  evidence_type  value  score
        # Example:
        # ENSP00000000233  ARF5  BTO:0000000  tissues...  Cardiac proteome  6.7E7...  0.726
        try:
            df = pd.read_csv(
                filepath,
                sep="\t",
                header=None,
                names=["gene_id", "gene_symbol", "tissue_id", "tissue_name",
                       "evidence_type", "evidence_value", "score"],
                dtype=str,
                low_memory=False,
            )
        except Exception as exc:
            logger.error("Failed to read Jensen TISSUES file: %s", exc)
            return {}

        logger.info("Jensen TISSUES raw: %d rows", len(df))

        # Convert score to numeric and filter
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
        df = df[df["score"] >= _MIN_SCORE].copy()
        logger.info("After score >= %.1f filter: %d rows", _MIN_SCORE, len(df))

        if df.empty:
            logger.warning("No Jensen TISSUES associations passed score filter.")
            return {}

        df = df.drop_duplicates().reset_index(drop=True)
        df["source_database"] = "Jensen TISSUES"

        logger.info("Jensen TISSUES: %d gene-tissue associations", len(df))
        return {TISSUE_GENE_OUTPUT: df}

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            TISSUE_GENE_OUTPUT: {
                "gene_id":        "Ensembl protein ID (ENSP)",
                "gene_symbol":    "Gene symbol",
                "tissue_id":      "Tissue ontology ID (BTO)",
                "tissue_name":    "Tissue name",
                "evidence_type":  "Evidence type (e.g. Cardiac proteome, RNA-seq)",
                "evidence_value": "Raw evidence value with units",
                "score":          "Jensen TISSUES confidence score (0-5)",
                "source_database": "Source database (Jensen TISSUES)",
            },
        }
