"""
MEDLINE Cooccurrence Parser for CardioKB.

This module parses MEDLINE co-occurrence data to extract:
- Disease-Symptom (presents) edges (DpS) via PubMed co-occurrence
- Disease-Anatomy (localizes) edges (DlA) via PubMed co-occurrence
- Disease-Disease (resembles) edges (DrD) via PubMed co-occurrence

Data Source: https://github.com/hetio/medline
Pre-computed cooccurrence files are downloaded and optionally filtered
to a disease scope (defaults to CVD).

Output:
  - disease_symptom_cooccurrence.tsv: DpS edges
  - disease_anatomy_cooccurrence.tsv: DlA edges
  - disease_disease_cooccurrence.tsv: DrD edges
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Set

import pandas as pd

from ..base_parser import BaseParser
from ...utils import load_disease_terms

logger = logging.getLogger(__name__)


class MEDLINECooccurrenceParser(BaseParser):
    """
    Parser for MEDLINE literature co-occurrence data.

    Extracts disease-symptom, disease-anatomy, and disease-disease
    relationships based on PubMed co-occurrence analysis with
    Fisher's exact test for statistical significance.

    When a disease_filter is provided, edges are filtered to only include
    diseases matching the filter terms (matched via Disease Ontology names).
    """

    # MEDLINE co-occurrence data from dhimmel hetionet repository
    HETIONET_COMMIT = "2cc3e1d7d9c0d3a6be3ed3b2c8b6f1e37be04a1a"
    MEDLINE_BASE_URL = "https://raw.githubusercontent.com/hetio/medline"

    # Pre-computed cooccurrence file URLs (from hetio/medline repo)
    DISEASE_SYMPTOM_URL = f"{MEDLINE_BASE_URL}/main/data/disease-symptom-cooccurrence.tsv"
    DISEASE_ANATOMY_URL = f"{MEDLINE_BASE_URL}/main/data/disease-uberon-cooccurrence.tsv"
    DISEASE_DISEASE_URL = f"{MEDLINE_BASE_URL}/main/data/disease-disease-cooccurrence.tsv"

    # P-value threshold for significant co-occurrence
    P_FISHER_THRESHOLD = 0.005

    def __init__(self, data_dir: str, disease_filter: Optional[str] = None):
        """
        Initialize the MEDLINE cooccurrence parser.

        Args:
            data_dir: Directory to store downloaded and processed data
            disease_filter: Path to disease terms file for scoping.
                Defaults to ontology/disease_filter.txt (CVD).
                Pass None to load all diseases (no filtering).
        """
        super().__init__(data_dir)
        self.source_name = "medline"
        self.disease_filter = disease_filter
        self._doid_filter: Optional[Set[str]] = None

    def _build_doid_filter(self) -> Optional[Set[str]]:
        """
        Build a set of DOID codes matching the disease filter terms.

        Uses the Disease Ontology disease_nodes.tsv to map disease names
        to DOID codes. Falls back gracefully if the file isn't available.
        """
        if self._doid_filter is not None:
            return self._doid_filter if self._doid_filter else None

        terms = load_disease_terms(self.disease_filter)
        if not terms:
            self._doid_filter = set()
            return None

        # Find Disease Ontology TSV in processed data
        do_paths = [
            Path(self.data_dir).parent / "processed" / "disease_ontology" / "disease_nodes.tsv",
            Path(self.data_dir) / ".." / "processed" / "disease_ontology" / "disease_nodes.tsv",
        ]

        do_df = None
        for do_path in do_paths:
            resolved = do_path.resolve()
            if resolved.exists():
                do_df = pd.read_csv(resolved, sep='\t', dtype=str)
                break

        if do_df is None or 'doid' not in do_df.columns or 'name' not in do_df.columns:
            logger.warning(
                "Disease Ontology disease_nodes.tsv not found — "
                "cannot filter MEDLINE by disease scope, loading all edges"
            )
            self._doid_filter = set()
            return None

        # Match disease names (case-insensitive substring match, same as DisGeNET)
        matched_doids = set()
        do_df['name_lower'] = do_df['name'].fillna('').str.lower()

        # Also check synonyms column if available
        has_synonyms = 'synonyms' in do_df.columns

        for _, row in do_df.iterrows():
            name_lower = row['name_lower']
            doid = row['doid']

            # Check if any filter term matches the disease name
            for term in terms:
                if term in name_lower:
                    matched_doids.add(doid)
                    break

            # Also check synonyms
            if has_synonyms and doid not in matched_doids:
                syn_lower = str(row.get('synonyms', '')).lower()
                for term in terms:
                    if term in syn_lower:
                        matched_doids.add(doid)
                        break

        logger.info(
            f"MEDLINE disease filter: {len(matched_doids)} DOIDs matched "
            f"from {len(terms)} disease terms"
        )
        self._doid_filter = matched_doids
        return matched_doids if matched_doids else None

    def download_data(self) -> bool:
        """Download MEDLINE co-occurrence data files."""
        logger.info("Downloading MEDLINE co-occurrence data...")

        success = True

        result = self.download_file(self.DISEASE_SYMPTOM_URL, "disease-symptom-cooccurrence.tsv")
        if not result:
            logger.warning("Failed to download disease-symptom cooccurrence")
            success = False

        result = self.download_file(self.DISEASE_ANATOMY_URL, "disease-uberon-cooccurrence.tsv")
        if not result:
            logger.warning("Failed to download disease-anatomy cooccurrence")
            success = False

        result = self.download_file(self.DISEASE_DISEASE_URL, "disease-disease-cooccurrence.tsv")
        if not result:
            logger.warning("Failed to download disease-disease cooccurrence")
            success = False

        if success:
            logger.info("Successfully downloaded MEDLINE co-occurrence data")
        else:
            logger.warning("Some MEDLINE files could not be downloaded")

        return success

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse the MEDLINE co-occurrence data files.

        If a disease_filter is set, only edges involving matching DOIDs
        are retained.
        """
        result = {}

        dps = self._parse_disease_symptom()
        if dps is not None:
            result["disease_symptom_cooccurrence"] = dps

        dla = self._parse_disease_anatomy()
        if dla is not None:
            result["disease_anatomy_cooccurrence"] = dla

        drd = self._parse_disease_disease()
        if drd is not None:
            result["disease_disease_cooccurrence"] = drd

        return result

    def _read_cooccurrence_file(self, *filenames: str) -> Optional[pd.DataFrame]:
        """Try to read a cooccurrence TSV from source_dir."""
        for filename in filenames:
            file_path = self.source_dir / filename
            if file_path.exists():
                return pd.read_csv(file_path, sep='\t', compression='infer')
        return None

    def _parse_disease_symptom(self) -> Optional[pd.DataFrame]:
        """Parse disease-symptom co-occurrence (DpS edges)."""
        df = self._read_cooccurrence_file(
            "disease-symptom-cooccurrence.tsv",
            "disease-symptom-cooccurrence.tsv.gz",
        )
        if df is None:
            logger.warning("Disease-symptom cooccurrence file not found")
            return None

        logger.info(f"Raw disease-symptom cooccurrence: {len(df)} rows")

        df = df[df['p_fisher'] < self.P_FISHER_THRESHOLD]

        # Apply disease filter
        doid_filter = self._build_doid_filter()
        if doid_filter:
            before = len(df)
            df = df[df['doid_code'].isin(doid_filter)]
            logger.info(f"Disease filter: {before} → {len(df)} DpS edges")

        edges = pd.DataFrame({
            'doid_code': df['doid_code'],
            'mesh_id': df['mesh_id'],
            'p_fisher': df['p_fisher'],
            'cooccurrence': df['cooccurrence'] if 'cooccurrence' in df.columns else None,
            'enrichment': df['enrichment'] if 'enrichment' in df.columns else None,
            'source': 'MEDLINE cooccurrence',
            'unbiased': False,
            'license': 'CC0 1.0',
            'sourceDatabase': 'MEDLINE'
        })

        logger.info(f"Parsed {len(edges)} Disease-presents-Symptom edges")
        return edges

    def _parse_disease_anatomy(self) -> Optional[pd.DataFrame]:
        """Parse disease-anatomy co-occurrence (DlA edges)."""
        df = self._read_cooccurrence_file(
            "disease-uberon-cooccurrence.tsv",
            "disease-uberon-cooccurrence.tsv.gz",
        )
        if df is None:
            logger.warning("Disease-anatomy cooccurrence file not found")
            return None

        logger.info(f"Raw disease-anatomy cooccurrence: {len(df)} rows")

        df = df[df['p_fisher'] < self.P_FISHER_THRESHOLD]

        doid_filter = self._build_doid_filter()
        if doid_filter:
            before = len(df)
            df = df[df['doid_code'].isin(doid_filter)]
            logger.info(f"Disease filter: {before} → {len(df)} DlA edges")

        edges = pd.DataFrame({
            'doid_code': df['doid_code'],
            'uberon_id': df['uberon_id'],
            'p_fisher': df['p_fisher'],
            'cooccurrence': df['cooccurrence'] if 'cooccurrence' in df.columns else None,
            'enrichment': df['enrichment'] if 'enrichment' in df.columns else None,
            'source': 'MEDLINE cooccurrence',
            'unbiased': False,
            'license': 'CC0 1.0',
            'sourceDatabase': 'MEDLINE'
        })

        logger.info(f"Parsed {len(edges)} Disease-localizes-Anatomy edges")
        return edges

    def _parse_disease_disease(self) -> Optional[pd.DataFrame]:
        """Parse disease-disease co-occurrence (DrD edges)."""
        df = self._read_cooccurrence_file(
            "disease-disease-cooccurrence.tsv",
            "disease-disease-cooccurrence.tsv.gz",
        )
        if df is None:
            logger.warning("Disease-disease cooccurrence file not found")
            return None

        logger.info(f"Raw disease-disease cooccurrence: {len(df)} rows")

        df = df[df['p_fisher'] < self.P_FISHER_THRESHOLD]

        # Remove duplicate pairs (keep only one direction)
        df['pair'] = df.apply(
            lambda row: frozenset([row['doid_code_0'], row['doid_code_1']]),
            axis=1
        )
        df = df.drop_duplicates(subset=['pair'])
        df = df.drop(columns=['pair'])

        # For disease-disease, keep edges where EITHER disease matches
        doid_filter = self._build_doid_filter()
        if doid_filter:
            before = len(df)
            df = df[
                df['doid_code_0'].isin(doid_filter) |
                df['doid_code_1'].isin(doid_filter)
            ]
            logger.info(f"Disease filter: {before} → {len(df)} DrD edges")

        edges = pd.DataFrame({
            'doid_code_0': df['doid_code_0'],
            'doid_code_1': df['doid_code_1'],
            'p_fisher': df['p_fisher'],
            'cooccurrence': df['cooccurrence'] if 'cooccurrence' in df.columns else None,
            'enrichment': df['enrichment'] if 'enrichment' in df.columns else None,
            'source': 'MEDLINE cooccurrence',
            'unbiased': False,
            'license': 'CC0 1.0',
            'sourceDatabase': 'MEDLINE'
        })

        logger.info(f"Parsed {len(edges)} Disease-resembles-Disease edges")
        return edges

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            "disease_symptom_cooccurrence": {
                "doid_code": "Disease Ontology ID",
                "mesh_id": "MeSH ID of symptom",
                "p_fisher": "Fisher's exact test p-value",
                "cooccurrence": "Number of co-occurring PubMed articles",
                "enrichment": "Enrichment ratio",
                "source": "Data source (MEDLINE cooccurrence)",
                "unbiased": "Whether edge is unbiased (False)",
                "license": "License (CC0 1.0)",
                "sourceDatabase": "Source database name (MEDLINE)"
            },
            "disease_anatomy_cooccurrence": {
                "doid_code": "Disease Ontology ID",
                "uberon_id": "UBERON anatomy ID",
                "p_fisher": "Fisher's exact test p-value",
                "cooccurrence": "Number of co-occurring PubMed articles",
                "enrichment": "Enrichment ratio",
                "source": "Data source (MEDLINE cooccurrence)",
                "unbiased": "Whether edge is unbiased (False)",
                "license": "License (CC0 1.0)",
                "sourceDatabase": "Source database name (MEDLINE)"
            },
            "disease_disease_cooccurrence": {
                "doid_code_0": "Disease Ontology ID of first disease",
                "doid_code_1": "Disease Ontology ID of second disease",
                "p_fisher": "Fisher's exact test p-value",
                "cooccurrence": "Number of co-occurring PubMed articles",
                "enrichment": "Enrichment ratio",
                "source": "Data source (MEDLINE cooccurrence)",
                "unbiased": "Whether edge is unbiased (False)",
                "license": "License (CC0 1.0)",
                "sourceDatabase": "Source database name (MEDLINE)"
            }
        }
