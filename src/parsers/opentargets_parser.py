"""
OpenTargetsParser: Parser for Open Targets gene-disease associations.

Downloads overall direct association scores (Parquet) and disease metadata
to map EFO disease IDs to DOID, producing geneAssociatesWithDisease edges.

Source: https://platform.opentargets.org/
Access: Public (no credentials required)
License: CC BY-SA 4.0
"""

import logging
import re
from typing import Dict, Optional

import pandas as pd
import requests

from .base_parser import BaseParser

logger = logging.getLogger(__name__)

ASSOC_BASE_URL = "https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/25.12/output/association_overall_direct/"
DISEASE_URL = "https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/25.12/output/disease/disease.parquet"


class OpenTargetsParser(BaseParser):
    """Parser for Open Targets gene-disease association data."""

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download association parquet files and disease metadata."""
        logger.info("Downloading Open Targets data...")

        # Download disease metadata for EFO->DOID mapping
        disease_path = self.source_dir / 'disease.parquet'
        if not disease_path.exists():
            result = self.download_file(DISEASE_URL, 'disease.parquet')
            if not result:
                logger.error("Failed to download disease metadata")
                return False

        # Check if association files already downloaded
        existing = list(self.source_dir.glob('part-*.parquet'))
        if existing:
            logger.info(f"Found {len(existing)} existing association parquet files")
            return True

        # Discover parquet file names from directory listing
        try:
            resp = requests.get(ASSOC_BASE_URL, timeout=30)
            resp.raise_for_status()
            filenames = re.findall(r'href="(part-\d+[^"]*\.parquet)"', resp.text)
            if not filenames:
                logger.error("No parquet files found in index")
                return False
            logger.info(f"Found {len(filenames)} parquet files to download")
        except Exception as e:
            logger.error(f"Failed to list parquet files: {e}")
            return False

        for i, fname in enumerate(filenames):
            result = self.download_file(f"{ASSOC_BASE_URL}{fname}", fname)
            if not result:
                logger.error(f"Failed to download {fname}")
                return False
            if (i + 1) % 5 == 0:
                logger.info(f"  Downloaded {i + 1}/{len(filenames)} files")

        logger.info(f"Downloaded all {len(filenames)} parquet files")
        return True

    def _build_efo_to_doid(self) -> Dict[str, str]:
        """Build EFO ID -> DOID mapping from disease metadata."""
        import pyarrow.parquet as pq

        disease_path = self.source_dir / 'disease.parquet'
        if not disease_path.exists():
            return {}

        df = pq.read_table(str(disease_path)).to_pandas()
        mapping = {}

        for _, row in df.iterrows():
            ot_id = row['id']  # e.g., "EFO_0000378" or "DOID_10113"

            # If it's already DOID, map directly
            if isinstance(ot_id, str) and ot_id.startswith('DOID_'):
                doid = ot_id.replace('_', ':', 1)
                mapping[ot_id] = doid
                continue

            # Check dbXRefs for DOID cross-references
            xrefs = row.get('dbXRefs')
            if xrefs is not None:
                for xref in xrefs:
                    if isinstance(xref, str) and xref.startswith('DOID:'):
                        mapping[ot_id] = xref
                        break

        logger.info(f"OpenTargets: mapped {len(mapping)} disease IDs to DOID")
        return mapping

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse parquet files into gene-disease association edges."""
        import pyarrow.parquet as pq

        # Build EFO->DOID mapping
        efo_to_doid = self._build_efo_to_doid()
        if not efo_to_doid:
            logger.error("Failed to build EFO->DOID mapping")
            return {}

        # Read association files
        parquet_files = sorted(self.source_dir.glob('part-*.parquet'))
        if not parquet_files:
            logger.error("No association parquet files found")
            return {}

        frames = []
        for pf in parquet_files:
            table = pq.read_table(str(pf))
            frames.append(table.to_pandas())

        df = pd.concat(frames, ignore_index=True)
        logger.info(f"Open Targets raw: {len(df)} associations")

        # Map disease IDs to DOID
        df['disease_id'] = df['diseaseId'].map(efo_to_doid)
        before = len(df)
        df = df.dropna(subset=['disease_id'])
        logger.info(f"Open Targets DOID-mapped: {len(df)} associations ({before - len(df)} unmapped)")

        # Ensembl gene IDs
        df['ensembl_id'] = df['targetId']

        result = df[['ensembl_id', 'disease_id', 'score', 'evidenceCount']].copy()
        result = result.drop_duplicates(subset=['ensembl_id', 'disease_id'])
        result['source_database'] = 'OpenTargets'

        logger.info(
            f"Open Targets: {len(result)} gene-disease associations "
            f"({result['ensembl_id'].nunique()} genes, "
            f"{result['disease_id'].nunique()} diseases)"
        )

        return {
            'gene_disease': result,
        }

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            'gene_disease': {
                'ensembl_id': 'Ensembl Gene ID',
                'disease_id': 'Disease Ontology ID (DOID:nnnnnnn)',
                'score': 'Overall association score (0-1)',
                'evidenceCount': 'Number of supporting evidence items',
                'source_database': 'Source database identifier',
            },
        }
