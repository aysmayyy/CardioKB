"""
BindingDB Parser for CardioKB.

This module parses BindingDB data to extract drug-gene binding relationships
(chemicalBindsGene) for CardioKB.

Data Source: https://www.bindingdb.org/bind/downloads/

Output:
  - drug_binds_gene.tsv: chemicalBindsGene relationships with binding affinity
"""

import logging
import time
import zipfile
from pathlib import Path
from typing import Dict, List
import pandas as pd
import requests

from ..base_parser import BaseParser

logger = logging.getLogger(__name__)


class BindingDBParser(BaseParser):
    """
    Parser for BindingDB database.

    Extracts drug-target binding data including affinity measurements
    for use in CardioKB's chemicalBindsGene relationships.
    """

    # BindingDB download URL (update version as needed)
    BINDINGDB_URL = "https://www.bindingdb.org/rwd/bind/downloads/BindingDB_All_202603_tsv.zip"

    # Columns to read from the raw BindingDB TSV
    USECOLS = [
        'Ligand SMILES',
        'Ligand InChI',
        'Ligand InChI Key',
        'BindingDB Ligand Name',
        'Target Name',
        'Target Source Organism According to Curator or DataSource',
        'Ki (nM)',
        'IC50 (nM)',
        'Kd (nM)',
        'EC50 (nM)',
        'UniProt (SwissProt) Primary ID of Target Chain 1',
        'PubChem CID',
        'DrugBank ID of Ligand',
        'ChEMBL ID of Ligand',
    ]

    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        self.source_name = "bindingdb"

    def download_data(self) -> bool:
        """Download the BindingDB TSV file."""
        logger.info("Downloading BindingDB...")

        result = self.download_file(self.BINDINGDB_URL, "BindingDB_All.tsv.zip")

        if result:
            zip_path = self.source_dir / "BindingDB_All.tsv.zip"
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(self.source_dir)
                logger.info("Successfully extracted BindingDB")
                return True
            except Exception as e:
                logger.error(f"Failed to extract BindingDB: {e}")
                return False
        else:
            logger.error("Failed to download BindingDB")
            return False

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse the BindingDB TSV file.

        Returns:
            Dictionary with:
              - 'drug_binds_gene': DataFrame of drug-gene binding relationships
        """
        tsv_files = list(self.source_dir.glob("BindingDB_All*.tsv"))
        if not tsv_files:
            logger.error("BindingDB TSV file not found")
            return {}

        tsv_path = tsv_files[0]
        logger.info(f"Parsing BindingDB from {tsv_path}")

        try:
            df = pd.read_csv(
                tsv_path,
                sep='\t',
                usecols=lambda x: x in self.USECOLS,
                low_memory=False,
                on_bad_lines='skip',
            )
            logger.info(f"Loaded {len(df):,} BindingDB entries")

            # Filter for human targets
            org_col = 'Target Source Organism According to Curator or DataSource'
            if org_col in df.columns:
                df = df[df[org_col].str.contains('Homo sapiens', case=False, na=False)]
                logger.info(f"Human targets: {len(df):,}")

            # Extract bindings using vectorized operations
            bindings = self._extract_bindings(df)
            logger.info(f"Extracted {len(bindings):,} drug-gene binding relationships")

            return {"drug_binds_gene": bindings}

        except Exception as e:
            logger.error(f"Error parsing BindingDB: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}

    def _extract_bindings(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract drug-gene binding relationships using vectorized pandas.

        Filters to rows with DrugBank IDs and UniProt IDs, picks the best
        affinity measurement per drug-target pair, then maps UniProt IDs
        to Entrez Gene IDs via the UniProt ID mapping API.
        """
        # Resolve column names (handle variations)
        uniprot_col = self._find_column(df, [
            'UniProt (SwissProt) Primary ID of Target Chain 1',
            'UniProt (SwissProt) Primary ID of Target Chain',
            'UniProt ID',
        ])
        drugbank_col = self._find_column(df, ['DrugBank ID of Ligand', 'DrugBank ID'])
        ligand_col = self._find_column(df, ['BindingDB Ligand Name', 'Ligand Name'])
        target_col = self._find_column(df, ['Target Name'])
        ki_col = self._find_column(df, ['Ki (nM)'])
        kd_col = self._find_column(df, ['Kd (nM)'])
        ic50_col = self._find_column(df, ['IC50 (nM)'])

        if not uniprot_col or not drugbank_col:
            logger.error("Required columns not found in BindingDB data")
            return pd.DataFrame()

        # Filter: must have both DrugBank ID and UniProt ID
        mask = df[drugbank_col].notna() & (df[drugbank_col] != '')
        mask &= df[uniprot_col].notna() & (df[uniprot_col] != '')
        filtered = df[mask].copy()
        logger.info(f"Rows with DrugBank + UniProt IDs: {len(filtered):,}")

        if filtered.empty:
            return pd.DataFrame()

        # Parse affinity columns (strip >, < prefixes, convert to float)
        for col, atype in [(ki_col, 'Ki'), (kd_col, 'Kd'), (ic50_col, 'IC50')]:
            if col and col in filtered.columns:
                filtered[f'_affinity_{atype}'] = pd.to_numeric(
                    filtered[col].astype(str).str.replace(r'[><\s]', '', regex=True),
                    errors='coerce',
                )

        # Pick best affinity: Ki > Kd > IC50
        affinity_cols = []
        affinity_types = []
        for atype in ['Ki', 'Kd', 'IC50']:
            acol = f'_affinity_{atype}'
            if acol in filtered.columns:
                affinity_cols.append(acol)
                affinity_types.append(atype)

        if affinity_cols:
            # Use first available affinity per row
            filtered['affinity_nm'] = filtered[affinity_cols[0]]
            filtered['affinity_type'] = None
            for i, acol in enumerate(affinity_cols):
                has_val = filtered[acol].notna()
                if i == 0:
                    filtered.loc[has_val, 'affinity_type'] = affinity_types[i]
                else:
                    no_val_yet = filtered['affinity_nm'].isna()
                    use_this = no_val_yet & has_val
                    filtered.loc[use_this, 'affinity_nm'] = filtered.loc[use_this, acol]
                    filtered.loc[use_this, 'affinity_type'] = affinity_types[i]
        else:
            filtered['affinity_nm'] = None
            filtered['affinity_type'] = None

        # Build result DataFrame
        result = pd.DataFrame({
            'drugbank_id': filtered[drugbank_col].values,
            'uniprot_id': filtered[uniprot_col].values,
            'ligand_name': filtered[ligand_col].values if ligand_col else '',
            'target_name': filtered[target_col].values if target_col else '',
            'affinity_nm': filtered['affinity_nm'].values,
            'affinity_type': filtered['affinity_type'].values,
            'relationship': 'chemicalBindsGene',
            'source': 'BindingDB',
        })

        # Clean DrugBank IDs (some have multiple, take first)
        result['drugbank_id'] = result['drugbank_id'].astype(str).str.split(',').str[0].str.strip()

        # Deduplicate: keep best affinity per (drugbank_id, uniprot_id) pair
        result = result.sort_values('affinity_nm', na_position='last')
        result = result.drop_duplicates(subset=['drugbank_id', 'uniprot_id'], keep='first')
        logger.info(f"After dedup: {len(result):,} unique drug-target pairs")

        # Map UniProt → Entrez Gene IDs
        unique_uniprots = result['uniprot_id'].unique().tolist()
        logger.info(f"Mapping {len(unique_uniprots):,} unique UniProt IDs to Entrez Gene IDs...")
        mapping = self._map_uniprot_to_entrez(unique_uniprots)
        logger.info(f"Mapped {len(mapping):,} UniProt IDs to Entrez Gene IDs")

        result['entrez_gene_id'] = result['uniprot_id'].map(mapping)
        before = len(result)
        result = result.dropna(subset=['entrez_gene_id'])
        result['entrez_gene_id'] = result['entrez_gene_id'].astype(int)
        logger.info(f"After Entrez mapping: {len(result):,} rows ({before - len(result):,} dropped)")

        result = result.reset_index(drop=True)
        return result

    def _map_uniprot_to_entrez(self, uniprot_ids: List[str]) -> Dict[str, int]:
        """
        Map UniProt accession IDs to Entrez Gene IDs using UniProt ID mapping API.

        Uses cached results if available.
        """
        cache_path = self.source_dir / 'uniprot_to_entrez.tsv'

        # Try loading cache
        if cache_path.exists():
            try:
                cache_df = pd.read_csv(cache_path, sep='\t')
                mapping = dict(zip(cache_df['uniprot_id'], cache_df['entrez_gene_id']))
                logger.info(f"Loaded {len(mapping):,} cached UniProt→Entrez mappings")
                # Check if cache covers all IDs
                missing = set(uniprot_ids) - set(mapping.keys())
                if not missing:
                    return mapping
                logger.info(f"{len(missing):,} UniProt IDs not in cache, querying API...")
                ids_to_query = list(missing)
            except Exception:
                mapping = {}
                ids_to_query = uniprot_ids
        else:
            mapping = {}
            ids_to_query = uniprot_ids

        # Query UniProt API in batches
        BATCH_SIZE = 5000
        for i in range(0, len(ids_to_query), BATCH_SIZE):
            batch = ids_to_query[i:i + BATCH_SIZE]
            batch_mapping = self._query_uniprot_api(batch)
            mapping.update(batch_mapping)
            logger.info(
                f"  API batch {i // BATCH_SIZE + 1}: "
                f"mapped {len(batch_mapping)}/{len(batch)} IDs"
            )

        # Save full cache
        if mapping:
            cache_df = pd.DataFrame([
                {'uniprot_id': k, 'entrez_gene_id': v}
                for k, v in mapping.items()
            ])
            cache_df.to_csv(cache_path, sep='\t', index=False)
            logger.info(f"Saved {len(mapping):,} mappings to {cache_path}")

        return mapping

    def _query_uniprot_api(self, uniprot_ids: List[str]) -> Dict[str, int]:
        """Query UniProt ID mapping API for a batch of UniProt IDs."""
        mapping = {}
        PAGE_SIZE = 500

        try:
            # Submit job
            resp = requests.post(
                'https://rest.uniprot.org/idmapping/run',
                data={
                    'from': 'UniProtKB_AC-ID',
                    'to': 'GeneID',
                    'ids': ','.join(uniprot_ids),
                },
                timeout=60,
            )
            resp.raise_for_status()
            job_id = resp.json()['jobId']

            # Poll for completion
            for _ in range(60):
                status_resp = requests.get(
                    f'https://rest.uniprot.org/idmapping/status/{job_id}',
                    timeout=30,
                )
                status_resp.raise_for_status()
                status_data = status_resp.json()

                if 'results' in status_data or 'failedIds' in status_data:
                    break
                if 'redirectURL' in status_data:
                    break
                if status_data.get('jobStatus') == 'RUNNING':
                    time.sleep(2)
                    continue
                time.sleep(2)
            else:
                logger.warning("UniProt API polling timed out")
                return mapping

            # Fetch all results with pagination (default page size is 25)
            url = f'https://rest.uniprot.org/idmapping/results/{job_id}?size={PAGE_SIZE}'
            while url:
                results_resp = requests.get(url, timeout=60)
                results_resp.raise_for_status()
                results_data = results_resp.json()

                for item in results_data.get('results', []):
                    from_id = item.get('from', '')
                    to_id = item.get('to', '')
                    if from_id and to_id:
                        try:
                            mapping[from_id] = int(to_id)
                        except (ValueError, TypeError):
                            pass

                # Check for next page via Link header
                link_header = results_resp.headers.get('Link', '')
                if 'rel="next"' in link_header:
                    url = link_header.split('<')[1].split('>')[0]
                else:
                    url = None

        except Exception as e:
            logger.warning(f"UniProt API error: {e}")

        return mapping

    def _find_column(self, df: pd.DataFrame, candidates: List[str]) -> str:
        """Find first matching column name from candidates."""
        for col in candidates:
            if col in df.columns:
                return col
        return None

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """Get the schema for BindingDB data."""
        return {
            "drug_binds_gene": {
                "drugbank_id": "DrugBank ID of ligand",
                "uniprot_id": "UniProt ID of target",
                "entrez_gene_id": "Entrez Gene ID of target (mapped from UniProt)",
                "ligand_name": "Ligand/drug name",
                "target_name": "Target protein name",
                "affinity_nm": "Binding affinity in nM",
                "affinity_type": "Type of affinity measurement (Ki, Kd, IC50)",
                "relationship": "Relationship type (chemicalBindsGene)",
                "source": "Data source (BindingDB)",
            }
        }
