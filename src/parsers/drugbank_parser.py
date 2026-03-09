"""
DrugBankParser: Parser for DrugBank data with authentication support.

DrugBank is a comprehensive database of drug information including
drug targets, interactions, and pharmacology.

Source: https://go.drugbank.com/releases/latest
Note: Requires free academic account for access.

Adapted from AlzKB (disease-agnostic).
"""

import base64
import logging
import os
import pandas as pd
import requests
import zipfile
import io

from pathlib import Path
from typing import Dict, Optional
from .base_parser import BaseParser
from ..ontology_configs import DRUGBANK_DRUGS

logger = logging.getLogger(__name__)


class DrugBankParser(BaseParser):
    """
    Parser for DrugBank data with HTTP Basic Authentication support.

    Supports both authenticated download and manual file-based parsing.
    """

    BASE_URL = "https://go.drugbank.com"

    def __init__(self, data_dir: str, username: Optional[str] = None,
                 password: Optional[str] = None, version: str = "latest"):
        """
        Initialize DrugBank parser.

        Args:
            data_dir: Directory for storing data files
            username: DrugBank username/email (optional)
            password: DrugBank password (optional)
            version: DrugBank release version (e.g., "5-1-14" or "latest")
        """
        super().__init__(data_dir)
        self.username = username or os.getenv('DRUGBANK_USERNAME')
        self.password = password or os.getenv('DRUGBANK_PASSWORD')
        self.version = version
        self.session = requests.Session()

        if self.username and self.password:
            self.session.auth = (self.username, self.password)
            logger.info("DrugBank credentials configured with HTTP Basic Auth")
        else:
            logger.warning("No DrugBank credentials provided. Will attempt file-based parsing.")

    def download_data(self) -> bool:
        """
        Download or check for DrugBank data.

        Returns:
            True if data is available, False otherwise.
        """
        if self.username and self.password:
            return self._download_with_auth()
        else:
            return self._check_manual_files()

    def _check_manual_files(self) -> bool:
        """Check for manually downloaded DrugBank files."""
        logger.info("Checking for DrugBank data files...")
        logger.info(f"  Required file: {DRUGBANK_DRUGS}.csv (extract from zip)")

        drug_links_path = self.get_file_path(f"{DRUGBANK_DRUGS}.csv")
        if os.path.exists(drug_links_path):
            logger.info(f"Found {DRUGBANK_DRUGS}.csv")
            return True
        else:
            logger.error(f"{DRUGBANK_DRUGS}.csv not found at: {drug_links_path}")
            logger.error("Please download manually or provide credentials")
            return False

    def _download_with_auth(self) -> bool:
        """
        Download DrugBank data with HTTP Basic Authentication.

        Uses an explicit Authorization header so credentials persist across
        redirects (requests drops session.auth on cross-host redirects).

        Returns:
            True if successful, False otherwise.
        """
        logger.info("Downloading DrugBank data with HTTP Basic Authentication...")

        download_url = f"{self.BASE_URL}/releases/{self.version}/downloads/all-drug-links"
        logger.info(f"Downloading from: {download_url}")

        # Build explicit Authorization header so it persists across redirects
        credentials = base64.b64encode(
            f"{self.username}:{self.password}".encode()
        ).decode()
        headers = {"Authorization": f"Basic {credentials}"}

        try:
            response = self.session.get(
                download_url, headers=headers,
                timeout=120, allow_redirects=True, stream=True,
            )
            response.raise_for_status()

            content = response.content

            # Validate response isn't an HTML error page
            content_start = content[:500].decode('utf-8', errors='replace').strip().lower()
            if content_start.startswith('<!doctype') or content_start.startswith('<html'):
                logger.error(
                    "DrugBank returned HTML instead of CSV — authentication "
                    "may have failed or the download URL has changed"
                )
                return False

            # Sanity check: DrugBank CSV should be >10 KB
            if len(content) < 10_000:
                logger.error(
                    f"DrugBank response too small ({len(content)} bytes) — "
                    "expected CSV data, likely got an error page"
                )
                return False

            output_path = self.get_file_path(f"{DRUGBANK_DRUGS}.csv")
            content_type = response.headers.get('content-type', '')

            if 'zip' in content_type or download_url.endswith('.zip'):
                logger.info("Extracting ZIP archive...")
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
                    if csv_files:
                        with zf.open(csv_files[0]) as csv_file:
                            with open(output_path, 'wb') as out_file:
                                out_file.write(csv_file.read())
                        logger.info(f"Extracted and saved to {output_path}")
                    else:
                        logger.error("No CSV file found in zip archive")
                        return False
            else:
                with open(output_path, 'wb') as f:
                    f.write(content)
                logger.info(f"Downloaded to {output_path}")

            return True

        except requests.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Authentication failed - invalid username or password")
            elif e.response.status_code == 403:
                logger.error("Access forbidden - check account permissions")
            elif e.response.status_code == 404:
                logger.error(f"File not found at {download_url}")
            else:
                logger.error(f"HTTP error {e.response.status_code}: {e}")
            return False
        except requests.RequestException as e:
            logger.error(f"Download failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during download: {e}")
            return False

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse DrugBank data.

        Returns:
            Dictionary with 'drugs' DataFrame.
        """
        logger.info("Parsing DrugBank data...")
        result = {}

        drug_links_file = self.get_file_path(f"{DRUGBANK_DRUGS}.csv")
        if not Path(drug_links_file).exists():
            logger.error(f"Drug links file not found: {drug_links_file}")
            return result

        try:
            drugs_df = self.read_csv(drug_links_file)

            if drugs_df is not None:
                column_mapping = {
                    'DrugBank ID': 'drugbank_id',
                    'Name': 'drug_name',
                    'CAS Number': 'cas_number',
                    'Drug Type': 'drug_type',
                    'PubChem Compound ID': 'pubchem_cid',
                    'PubChem Substance ID': 'pubchem_sid',
                    'ChEMBL ID': 'chembl_id',
                    'ChEBI ID': 'chebi_id',
                    'KEGG Compound ID': 'kegg_compound_id',
                    'KEGG Drug ID': 'kegg_drug_id',
                    'PharmGKB ID': 'pharmgkb_id',
                    'Uniprot Title': 'uniprot_title',
                    'UniProt ID': 'uniprot_id',
                    'GenBank ID': 'genbank_id',
                }

                existing_cols = {k: v for k, v in column_mapping.items() if k in drugs_df.columns}
                drugs_df = drugs_df.rename(columns=existing_cols)
                drugs_df['source_database'] = 'DrugBank'
                result['drugs'] = drugs_df
                logger.info(f"Parsed {len(drugs_df)} drugs")

        except Exception as e:
            logger.error(f"Failed to parse DrugBank data: {e}")

        return result

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """Get the schema for DrugBank data."""
        return {
            DRUGBANK_DRUGS: {
                'drugbank_id': 'DrugBank identifier',
                'drug_name': 'Drug name',
                'cas_number': 'CAS Registry Number',
                'drug_type': 'Drug type',
                'source_database': 'Source database (DrugBank)',
            }
        }
