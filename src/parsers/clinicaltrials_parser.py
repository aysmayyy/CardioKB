"""
ClinicalTrialsParser: Parser for ClinicalTrials.gov via AACT bulk download.

Downloads the full AACT pipe-delimited flat files (all 500K+ trials) and
loads them unfiltered. No disease filter is applied — the entire database
is ingested into the knowledge graph.

Source: https://aact.ctti-clinicaltrials.org/
Data: Pipe-delimited flat files updated daily from ClinicalTrials.gov.
"""

import logging
import os
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

from .base_parser import BaseParser

logger = logging.getLogger(__name__)

# AACT daily flat-file export URL
_AACT_FLAT_FILES_URL = (
    "https://ctti-aact.nyc3.digitaloceanspaces.com/"
    "khccdvkl4fl75sojt682es0mvu0a"
)

# Files we need from the ZIP (pipe-delimited .txt)
_NEEDED_FILES = {'studies.txt', 'conditions.txt', 'interventions.txt'}


class ClinicalTrialsParser(BaseParser):
    """
    Parser for ClinicalTrials.gov via AACT bulk flat files.

    Downloads the full AACT database dump (~2.4 GB ZIP) containing all
    registered clinical trials. Extracts studies, conditions, and
    interventions tables, joins them, and outputs the same schema as the
    previous API-based parser so downstream pipeline code is unchanged.
    """

    def __init__(self, data_dir: Optional[str] = None, **kwargs):
        """
        Initialize ClinicalTrials.gov bulk parser.

        Args:
            data_dir: Directory for storing cached data.
            **kwargs: Accepted for backwards compatibility (query_mode,
                disease_filter, etc.) but ignored — all trials are loaded.
        """
        super().__init__(data_dir)
        self._zip_path = os.path.join(self.data_dir, 'aact_flat_files.zip')
        self._studies_df = None
        self._conditions_df = None
        self._interventions_df = None

    def download_data(self) -> bool:
        """
        Download the AACT flat-file ZIP if not already cached.

        Returns:
            True if the ZIP is available, False on failure.
        """
        if os.path.exists(self._zip_path):
            size_gb = os.path.getsize(self._zip_path) / 1e9
            logger.info(f"AACT flat files already cached ({size_gb:.2f} GB)")
            return True

        logger.info("Downloading AACT flat files from ClinicalTrials.gov...")
        logger.info(f"URL: {_AACT_FLAT_FILES_URL}")

        try:
            r = requests.get(_AACT_FLAT_FILES_URL, stream=True, timeout=60)
            r.raise_for_status()

            total = int(r.headers.get('Content-Length', 0))
            logger.info(f"Download size: {total / 1e9:.2f} GB")

            downloaded = 0
            tmp_path = self._zip_path + '.tmp'
            with open(tmp_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total and downloaded % (500 * 1024 * 1024) < 8 * 1024 * 1024:
                        pct = 100 * downloaded / total
                        logger.info(f"  {downloaded / 1e9:.2f} GB ({pct:.0f}%)")

            os.rename(tmp_path, self._zip_path)
            logger.info(f"Download complete: {downloaded / 1e9:.2f} GB")
            return True

        except Exception as e:
            logger.error(f"AACT download failed: {e}")
            # Clean up partial file
            for p in (self._zip_path, self._zip_path + '.tmp'):
                if os.path.exists(p):
                    os.remove(p)
            return False

    def _read_pipe_file(self, zf: zipfile.ZipFile, filename: str) -> Optional[pd.DataFrame]:
        """Read a pipe-delimited file from the AACT ZIP."""
        # The file may be at the root or inside a subdirectory
        matching = [n for n in zf.namelist() if n.endswith('/' + filename) or n == filename]
        if not matching:
            logger.warning(f"  {filename} not found in ZIP")
            return None

        path = matching[0]
        logger.info(f"  Reading {path}...")
        with zf.open(path) as f:
            df = pd.read_csv(f, sep='|', dtype=str, low_memory=False)
        logger.info(f"  {filename}: {len(df):,} rows, {len(df.columns)} columns")
        return df

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse AACT flat files into the clinical_trials DataFrame.

        Joins studies + conditions + interventions to produce the same
        output schema as the previous API-based parser:
            trial_id, title, intervention_name, condition, phase, status,
            source_database

        Returns:
            Dictionary with 'clinical_trials' DataFrame.
        """
        logger.info("Parsing AACT flat files...")

        if not os.path.exists(self._zip_path):
            logger.error("AACT ZIP not found. Call download_data() first.")
            return {}

        # Read the three tables we need
        with zipfile.ZipFile(self._zip_path, 'r') as zf:
            studies = self._read_pipe_file(zf, 'studies.txt')
            conditions = self._read_pipe_file(zf, 'conditions.txt')
            interventions = self._read_pipe_file(zf, 'interventions.txt')

        if studies is None:
            logger.error("studies.txt not found in AACT ZIP")
            return {}

        # --- Build the unified DataFrame ---

        # Studies: nct_id, brief_title, overall_status, phase
        studies = studies.rename(columns={
            'nct_id': 'trial_id',
            'brief_title': 'title',
            'overall_status': 'status',
        })
        # Normalize phase values (AACT uses "Phase 1", API used "PHASE1")
        if 'phase' in studies.columns:
            studies['phase'] = studies['phase'].fillna('Not specified')
        else:
            studies['phase'] = 'Not specified'

        studies['status'] = studies['status'].fillna('Unknown')
        studies['title'] = studies['title'].fillna('')

        # Conditions: aggregate per trial (semicolon-delimited)
        if conditions is not None and 'nct_id' in conditions.columns and 'name' in conditions.columns:
            cond_agg = (conditions.dropna(subset=['name'])
                        .groupby('nct_id')['name']
                        .apply(lambda x: '; '.join(x.unique()))
                        .reset_index()
                        .rename(columns={'nct_id': 'trial_id', 'name': 'condition'}))
        else:
            cond_agg = pd.DataFrame(columns=['trial_id', 'condition'])
            logger.warning("No conditions data available")

        # Interventions: aggregate per trial (semicolon-delimited)
        if interventions is not None and 'nct_id' in interventions.columns and 'name' in interventions.columns:
            intv_agg = (interventions.dropna(subset=['name'])
                        .groupby('nct_id')['name']
                        .apply(lambda x: '; '.join(x.unique()))
                        .reset_index()
                        .rename(columns={'nct_id': 'trial_id', 'name': 'intervention_name'}))
        else:
            intv_agg = pd.DataFrame(columns=['trial_id', 'intervention_name'])
            logger.warning("No interventions data available")

        # Join
        df = studies[['trial_id', 'title', 'phase', 'status']].copy()
        df = df.merge(cond_agg, on='trial_id', how='left')
        df = df.merge(intv_agg, on='trial_id', how='left')

        df['condition'] = df['condition'].fillna('Not specified')
        df['intervention_name'] = df['intervention_name'].fillna('Not specified')
        df['source_database'] = 'ClinicalTrials.gov'

        # Ensure expected column order
        df = df[['trial_id', 'title', 'intervention_name', 'condition',
                 'phase', 'status', 'source_database']]

        logger.info(f"Parsed {len(df):,} total trials (all ClinicalTrials.gov)")

        if len(df) > 0:
            logger.info("Status distribution:")
            for status, count in df['status'].value_counts().head(5).items():
                logger.info(f"  {status}: {count:,}")
            logger.info("Phase distribution:")
            for phase, count in df['phase'].value_counts().head(5).items():
                logger.info(f"  {phase}: {count:,}")

        return {'clinical_trials': df}

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """Get the schema for clinical trials data."""
        return {
            'clinical_trials': {
                'trial_id': 'ClinicalTrials.gov NCT identifier',
                'title': 'Study title',
                'intervention_name': 'Drug/intervention name(s)',
                'condition': 'Disease/condition(s) being studied',
                'phase': 'Study phase',
                'status': 'Recruitment/overall status',
                'source_database': 'Source database (ClinicalTrials.gov)'
            }
        }
