"""
DrugBankParser: Parser for DrugBank data with authentication support.

DrugBank is a comprehensive database of drug information including
drug targets, interactions, and pharmacology.

Source: https://go.drugbank.com/releases/latest
Note: Requires free academic account for access.

Supports three data modes:
1. Authenticated CSV download (drug-links endpoint)
2. Manual CSV file (drugs.csv)
3. Full database XML file (full database.xml)

Adapted from AlzKB (disease-agnostic).
"""

import base64
import logging
import os
import pandas as pd
import requests
import zipfile
import io
import xml.etree.ElementTree as ET

from pathlib import Path
from typing import Dict, Optional, List
from .base_parser import BaseParser
from ..ontology_configs import DRUGBANK_DRUGS, DRUGBANK_DRUG_BINDS_GENE

logger = logging.getLogger(__name__)

NS = '{http://www.drugbank.ca}'


class DrugBankParser(BaseParser):
    """
    Parser for DrugBank data with HTTP Basic Authentication support.

    Supports authenticated download, manual CSV, and full database XML parsing.
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
        self._xml_path = self._find_xml()
        self.session = requests.Session()

        if self.username and self.password:
            self.session.auth = (self.username, self.password)
            logger.info("DrugBank credentials configured with HTTP Basic Auth")
        elif self._xml_path:
            logger.info(f"Found DrugBank XML: {self._xml_path}")
        else:
            logger.warning("No DrugBank credentials or XML file provided. Will attempt CSV-based parsing.")

    def _find_xml(self) -> Optional[Path]:
        """Look for a DrugBank XML file in the data directory."""
        for f in self.source_dir.glob('*.xml'):
            return f
        return None

    def download_data(self) -> bool:
        """
        Download or check for DrugBank data.

        Returns:
            True if data is available, False otherwise.
        """
        # Check for XML first (richest data source)
        if self._xml_path and self._xml_path.exists():
            size_gb = self._xml_path.stat().st_size / (1024**3)
            logger.info(f"DrugBank XML available: {self._xml_path} ({size_gb:.1f} GB)")
            return True

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
            logger.error("Please download manually, provide credentials, or place XML file in data/raw/drugbank/")
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

    def _parse_from_xml(self, xml_path: Path) -> Dict[str, pd.DataFrame]:
        """
        Parse DrugBank full database XML via streaming iterparse.

        Extracts drug ID, name, CAS number, type, and cross-references
        without loading the entire 1.8GB XML into memory.

        Args:
            xml_path: Path to the DrugBank XML file.

        Returns:
            Dictionary with 'drugs' DataFrame.
        """
        logger.info(f"Parsing DrugBank XML: {xml_path}")

        rows: List[dict] = []
        target_rows: List[dict] = []
        drug_tag = f'{NS}drug'
        count = 0

        context = ET.iterparse(str(xml_path), events=('start', 'end'))
        depth = 0

        for event, elem in context:
            if event == 'start' and elem.tag == drug_tag:
                depth += 1
            elif event == 'end' and elem.tag == drug_tag:
                depth -= 1
                if depth == 0:
                    # Top-level <drug> element
                    dbid_elem = elem.find(f'{NS}drugbank-id[@primary="true"]')
                    name_elem = elem.find(f'{NS}name')
                    cas_elem = elem.find(f'{NS}cas-number')
                    drug_type = elem.attrib.get('type', '')

                    drugbank_id = dbid_elem.text if dbid_elem is not None else None
                    drug_name = name_elem.text if name_elem is not None else None
                    cas_number = cas_elem.text if cas_elem is not None else None

                    if not drugbank_id:
                        elem.clear()
                        continue

                    row = {
                        'drugbank_id': drugbank_id,
                        'drug_name': drug_name or '',
                        'cas_number': cas_number or '',
                        'drug_type': drug_type,
                    }

                    # Extract external identifiers for cross-references
                    for ei in elem.findall(f'.//{NS}external-identifier'):
                        res = ei.find(f'{NS}resource')
                        ident = ei.find(f'{NS}identifier')
                        if res is None or ident is None:
                            continue
                        resource = res.text
                        identifier = ident.text
                        if resource == 'PubChem Compound':
                            row['pubchem_cid'] = identifier
                        elif resource == 'PubChem Substance':
                            row['pubchem_sid'] = identifier
                        elif resource == 'ChEMBL':
                            row['chembl_id'] = identifier
                        elif resource == 'ChEBI':
                            row['chebi_id'] = identifier
                        elif resource == 'KEGG Compound':
                            row['kegg_compound_id'] = identifier
                        elif resource == 'KEGG Drug':
                            row['kegg_drug_id'] = identifier
                        elif resource == 'PharmGKB':
                            row['pharmgkb_id'] = identifier
                        elif resource == 'UniProtKB':
                            row['uniprot_id'] = identifier

                    rows.append(row)

                    # Extract drug-target bindings
                    targets_elem = elem.find(f'{NS}targets')
                    if targets_elem is not None:
                        for target in targets_elem.findall(f'{NS}target'):
                            # Get gene name from polypeptide
                            polypeptide = target.find(f'{NS}polypeptide')
                            if polypeptide is None:
                                continue
                            gene_name_elem = polypeptide.find(f'{NS}gene-name')
                            if gene_name_elem is None or not gene_name_elem.text:
                                continue
                            gene_symbol = gene_name_elem.text.strip()

                            # Get action(s)
                            actions = []
                            actions_elem = target.find(f'{NS}actions')
                            if actions_elem is not None:
                                for action in actions_elem.findall(f'{NS}action'):
                                    if action.text:
                                        actions.append(action.text)

                            target_rows.append({
                                'drugbank_id': drugbank_id,
                                'gene_symbol': gene_symbol,
                                'actions': '|'.join(actions) if actions else '',
                                'source_database': 'DrugBank',
                            })

                    count += 1

                    if count % 5000 == 0:
                        logger.info(f"  Parsed {count:,} drugs...")

                    # Free memory
                    elem.clear()

        logger.info(f"Parsed {count:,} drugs from XML")

        drugs_df = pd.DataFrame(rows)
        drugs_df['source_database'] = 'DrugBank'

        result = {'drugs': drugs_df}

        if target_rows:
            targets_df = pd.DataFrame(target_rows).drop_duplicates(
                subset=['drugbank_id', 'gene_symbol']
            )
            logger.info(
                f"DrugBank: {len(targets_df)} drug-target edges "
                f"({targets_df['drugbank_id'].nunique()} drugs, "
                f"{targets_df['gene_symbol'].nunique()} genes)"
            )
            result[DRUGBANK_DRUG_BINDS_GENE] = targets_df

        return result

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse DrugBank data from XML or CSV.

        Returns:
            Dictionary with 'drugs' DataFrame.
        """
        logger.info("Parsing DrugBank data...")

        # Prefer XML if available
        if self._xml_path and self._xml_path.exists():
            return self._parse_from_xml(self._xml_path)

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
            },
            DRUGBANK_DRUG_BINDS_GENE: {
                'drugbank_id': 'DrugBank identifier',
                'gene_symbol': 'Target gene symbol',
                'actions': 'Pipe-delimited pharmacological actions',
                'source_database': 'Source database (DrugBank)',
            },
        }
