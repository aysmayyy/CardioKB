"""
OMIMParser: Parser for Online Mendelian Inheritance in Man (OMIM).

Parses OMIM bulk data files (genemap2.txt, morbidmap.txt) for gene-disease
relationships, inheritance patterns, and phenotype mappings. Optionally
enriches data via the OMIM API if an API key is available.

Source: https://omim.org/
Bulk files: https://data.omim.org/downloads/{API_KEY}/
API: https://api.omim.org/api (requires API key)
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Set
import pandas as pd
import requests
from .base_parser import BaseParser
from ..utils import is_cardiovascular_related, load_cvd_terms

logger = logging.getLogger(__name__)


class OMIMParser(BaseParser):
    """
    Parser for OMIM genetic disease data.

    Primary mode: Parse genemap2.txt and morbidmap.txt bulk files.
    Optional: Enrich with OMIM API for clinical synopses and variant details.
    """

    OMIM_API_URL = "https://api.omim.org/api"
    OMIM_DOWNLOAD_URL = "https://data.omim.org/downloads"
    GENEMAP2_FILENAME = "genemap2.txt"
    MORBIDMAP_FILENAME = "morbidmap.txt"
    API_RATE_DELAY = 0.3  # seconds between API requests

    # genemap2.txt column names (from the file's header comment)
    GENEMAP2_COLUMNS = [
        'chromosome', 'genomic_position_start', 'genomic_position_end',
        'cyto_location', 'computed_cyto_location', 'mim_number',
        'gene_symbols', 'gene_name', 'approved_gene_symbol',
        'entrez_gene_id', 'ensembl_gene_id', 'comments',
        'phenotypes', 'mouse_gene_symbol_id'
    ]

    # morbidmap.txt column names
    MORBIDMAP_COLUMNS = [
        'phenotype', 'gene_symbols', 'mim_number', 'cyto_location'
    ]

    def __init__(self, data_dir: Optional[str] = None,
                 api_key: Optional[str] = None,
                 use_api_enrichment: bool = True,
                 genemap2_path: Optional[str] = None,
                 morbidmap_path: Optional[str] = None):
        """
        Initialize OMIM parser.

        Args:
            data_dir: Directory for storing data files.
            api_key: OMIM API key. If None, reads from OMIM_API_KEY env var.
            use_api_enrichment: Whether to use API for additional data.
            genemap2_path: Override path for genemap2.txt file.
            morbidmap_path: Override path for morbidmap.txt file.
        """
        super().__init__(data_dir)

        if api_key is None:
            api_key = os.environ.get('OMIM_API_KEY')
        self.api_key = api_key
        self.has_api_access = api_key is not None
        self.use_api_enrichment = use_api_enrichment and self.has_api_access

        self.genemap2_path = genemap2_path or str(
            self.source_dir / self.GENEMAP2_FILENAME
        )
        self.morbidmap_path = morbidmap_path or str(
            self.source_dir / self.MORBIDMAP_FILENAME
        )

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CardioKB-Parser/0.1.0',
            'Accept': 'application/json'
        })

        # Cache for API enrichment
        self.cache_dir = self.source_dir / "cache"

        # Parsed data
        self._genemap2_df = None
        self._morbidmap_df = None

    def download_data(self) -> bool:
        """
        Download or locate OMIM bulk data files.

        If an API key is available, downloads genemap2.txt and morbidmap.txt
        from the OMIM data portal. Otherwise, checks if files already exist
        in the data directory (user-placed).

        Returns:
            True if at least genemap2.txt is available, False otherwise.
        """
        if self.has_api_access:
            logger.info("OMIM API key found. Downloading bulk files...")
            base_url = f"{self.OMIM_DOWNLOAD_URL}/{self.api_key}"

            genemap2_url = f"{base_url}/{self.GENEMAP2_FILENAME}"
            result = self.download_file(genemap2_url, self.GENEMAP2_FILENAME)
            if result:
                self.genemap2_path = result

            morbidmap_url = f"{base_url}/{self.MORBIDMAP_FILENAME}"
            result = self.download_file(morbidmap_url, self.MORBIDMAP_FILENAME)
            if result:
                self.morbidmap_path = result
        else:
            logger.info("No OMIM API key. Checking for existing bulk files...")

        # Verify files exist
        has_genemap2 = Path(self.genemap2_path).exists()
        has_morbidmap = Path(self.morbidmap_path).exists()

        if has_genemap2:
            logger.info(f"genemap2.txt found: {self.genemap2_path}")
        else:
            logger.error(
                f"genemap2.txt not found at {self.genemap2_path}. "
                "Set OMIM_API_KEY in .env to download, or place the file manually."
            )

        if has_morbidmap:
            logger.info(f"morbidmap.txt found: {self.morbidmap_path}")
        else:
            logger.warning(
                f"morbidmap.txt not found at {self.morbidmap_path}. "
                "Gene-disease relationships will not be available."
            )

        return has_genemap2

    def _read_omim_file(self, filepath: str, column_names: List[str]) -> Optional[pd.DataFrame]:
        """
        Read an OMIM tab-separated file, skipping comment lines.

        OMIM files use '#' for comments and the last comment line
        contains column headers. Data lines follow.

        Args:
            filepath: Path to the file.
            column_names: Expected column names.

        Returns:
            DataFrame, or None on failure.
        """
        try:
            # Read all non-comment lines
            data_lines = []
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.rstrip('\n')
                    if not line.startswith('#') and line.strip():
                        data_lines.append(line)

            if not data_lines:
                logger.warning(f"No data lines found in {filepath}")
                return None

            # Parse tab-separated data
            from io import StringIO
            data_text = '\n'.join(data_lines)
            df = pd.read_csv(
                StringIO(data_text),
                sep='\t',
                header=None,
                names=column_names[:],  # Use provided column names
                dtype=str,
                on_bad_lines='warn'
            )

            # Trim to expected column count if file has fewer columns
            if len(df.columns) > len(column_names):
                df = df.iloc[:, :len(column_names)]

            logger.info(f"Read {len(df)} rows from {filepath}")
            return df

        except Exception as e:
            logger.error(f"Failed to read {filepath}: {e}")
            return None

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse OMIM bulk files into structured DataFrames.

        Returns:
            Dictionary with gene_phenotype_map, gene_disease_relationships,
            and omim_cvd_genes DataFrames.
        """
        logger.info("Parsing OMIM data...")
        result = {}

        # 1. Parse genemap2.txt
        result['gene_phenotype_map'] = self._parse_genemap2()

        # 2. Parse morbidmap.txt
        result['gene_disease_relationships'] = self._parse_morbidmap()

        # 3. Derive CVD-specific gene summary
        result['omim_cvd_genes'] = self._derive_cvd_genes(
            result['gene_disease_relationships']
        )

        # 4. Optional API enrichment
        if self.use_api_enrichment and len(result['omim_cvd_genes']) > 0:
            result['gene_disease_relationships'] = self._enrich_with_api(
                result['gene_disease_relationships']
            )

        for key, df in result.items():
            logger.info(f"  {key}: {len(df)} rows")

        return result

    def _parse_genemap2(self) -> pd.DataFrame:
        """Parse genemap2.txt into a gene-phenotype map DataFrame."""
        empty = pd.DataFrame(columns=[
            'mim_number', 'gene_symbol', 'gene_name', 'chromosome',
            'cyto_location', 'entrez_gene_id', 'ensembl_gene_id',
            'phenotypes_raw', 'source_database'
        ])

        if not Path(self.genemap2_path).exists():
            logger.warning("genemap2.txt not available")
            return empty

        df = self._read_omim_file(self.genemap2_path, self.GENEMAP2_COLUMNS)
        if df is None or len(df) == 0:
            return empty

        # Select and rename relevant columns
        records = []
        for _, row in df.iterrows():
            try:
                records.append({
                    'mim_number': str(row.get('mim_number', '')).strip(),
                    'gene_symbol': str(row.get('approved_gene_symbol', '')).strip(),
                    'gene_name': str(row.get('gene_name', '')).strip(),
                    'chromosome': str(row.get('chromosome', '')).strip(),
                    'cyto_location': str(row.get('cyto_location', '')).strip(),
                    'entrez_gene_id': str(row.get('entrez_gene_id', '')).strip(),
                    'ensembl_gene_id': str(row.get('ensembl_gene_id', '')).strip(),
                    'phenotypes_raw': str(row.get('phenotypes', '')).strip(),
                    'source_database': 'OMIM'
                })
            except Exception as e:
                logger.debug(f"Skipping row: {e}")
                continue

        result = pd.DataFrame(records)

        # Drop rows without a MIM number
        result = result[result['mim_number'].str.strip().astype(bool)].copy()

        logger.info(f"Parsed {len(result)} gene-phenotype entries from genemap2")
        return result

    def _parse_morbidmap(self) -> pd.DataFrame:
        """
        Parse morbidmap.txt into gene-disease relationship DataFrame.

        Extracts phenotype name, MIM numbers, mapping key, and inheritance
        pattern from the phenotype field. Adds CVD relevance flag.
        """
        empty = pd.DataFrame(columns=[
            'phenotype', 'phenotype_mim', 'gene_symbols', 'gene_mim',
            'cyto_location', 'mapping_key', 'inheritance', 'is_cvd',
            'source_database'
        ])

        if not Path(self.morbidmap_path).exists():
            logger.warning("morbidmap.txt not available")
            return empty

        df = self._read_omim_file(self.morbidmap_path, self.MORBIDMAP_COLUMNS)
        if df is None or len(df) == 0:
            return empty

        cvd_terms = load_cvd_terms()
        records = []

        for _, row in df.iterrows():
            try:
                raw_phenotype = str(row.get('phenotype', '')).strip()
                if not raw_phenotype:
                    continue

                phenotype_name, phenotype_mim, mapping_key, inheritance = \
                    self._parse_phenotype_field(raw_phenotype)

                records.append({
                    'phenotype': phenotype_name,
                    'phenotype_mim': phenotype_mim,
                    'gene_symbols': str(row.get('gene_symbols', '')).strip(),
                    'gene_mim': str(row.get('mim_number', '')).strip(),
                    'cyto_location': str(row.get('cyto_location', '')).strip(),
                    'mapping_key': mapping_key,
                    'inheritance': inheritance,
                    'is_cvd': is_cardiovascular_related(
                        phenotype_name, cvd_terms
                    ),
                    'source_database': 'OMIM'
                })
            except Exception as e:
                logger.debug(f"Skipping morbidmap row: {e}")
                continue

        result = pd.DataFrame(records)
        cvd_count = result['is_cvd'].sum() if len(result) > 0 else 0
        logger.info(
            f"Parsed {len(result)} gene-disease relationships "
            f"({cvd_count} CVD-related)"
        )
        return result

    def _parse_phenotype_field(self, phenotype_text: str) -> tuple:
        """
        Parse the OMIM phenotype field into components.

        Format: "Phenotype name, MIM_NUMBER (mapping_key), inheritance"
        Example: "Long QT syndrome 1, 192500 (3), Autosomal dominant"

        Returns:
            Tuple of (phenotype_name, phenotype_mim, mapping_key, inheritance).
        """
        phenotype_name = phenotype_text
        phenotype_mim = ''
        mapping_key = ''
        inheritance = ''

        # Extract mapping key: number in parentheses at end, e.g., "(3)"
        mapping_match = re.search(r'\((\d)\)\s*$', phenotype_text)
        if mapping_match:
            mapping_key = mapping_match.group(1)
            phenotype_text = phenotype_text[:mapping_match.start()].strip()
            # Remove trailing comma if present
            phenotype_text = phenotype_text.rstrip(',').strip()

        # Extract MIM number: 6-digit number near end
        mim_match = re.search(r',?\s*(\d{6})\s*$', phenotype_text)
        if mim_match:
            phenotype_mim = mim_match.group(1)
            phenotype_name = phenotype_text[:mim_match.start()].strip()
            phenotype_name = phenotype_name.rstrip(',').strip()
        else:
            phenotype_name = phenotype_text

        # Extract inheritance patterns from phenotype name
        inheritance_patterns = []
        for pattern in ['Autosomal dominant', 'Autosomal recessive',
                        'X-linked', 'X-linked dominant', 'X-linked recessive',
                        'Y-linked', 'Mitochondrial',
                        'Digenic dominant', 'Digenic recessive',
                        'Somatic mutation', 'Somatic mosaicism',
                        'Isolated cases', 'Multifactorial',
                        '?Autosomal dominant', '?Autosomal recessive']:
            if pattern.lower() in phenotype_name.lower():
                inheritance_patterns.append(pattern)

        if inheritance_patterns:
            inheritance = '; '.join(inheritance_patterns)

        # Clean up phenotype name: remove leading special chars
        phenotype_name = re.sub(r'^[\[\{?\#]+\s*', '', phenotype_name).strip()

        return phenotype_name, phenotype_mim, mapping_key, inheritance

    def _derive_cvd_genes(self, gene_disease_df: pd.DataFrame) -> pd.DataFrame:
        """
        Derive a CVD-specific gene summary from gene-disease relationships.

        Args:
            gene_disease_df: DataFrame from _parse_morbidmap().

        Returns:
            DataFrame with one row per CVD-related gene.
        """
        empty = pd.DataFrame(columns=[
            'gene_symbol', 'gene_mim', 'cvd_phenotypes',
            'cvd_phenotype_count', 'inheritance_patterns', 'source_database'
        ])

        if len(gene_disease_df) == 0 or 'is_cvd' not in gene_disease_df.columns:
            return empty

        cvd_df = gene_disease_df[gene_disease_df['is_cvd']].copy()
        if len(cvd_df) == 0:
            logger.info("No CVD-related genes found in morbidmap data")
            return empty

        # Group by gene
        records = []
        for gene_symbols, group in cvd_df.groupby('gene_symbols'):
            # Take the first gene symbol if multiple are listed
            primary_symbol = str(gene_symbols).split(',')[0].strip()

            phenotypes = group['phenotype'].dropna().unique()
            mim_numbers = group['gene_mim'].dropna().unique()
            inheritances = group['inheritance'].dropna()
            inheritances = inheritances[inheritances.str.strip().astype(bool)]

            records.append({
                'gene_symbol': primary_symbol,
                'gene_mim': '; '.join(str(m) for m in mim_numbers),
                'cvd_phenotypes': '; '.join(phenotypes),
                'cvd_phenotype_count': len(phenotypes),
                'inheritance_patterns': '; '.join(inheritances.unique()),
                'source_database': 'OMIM'
            })

        result = pd.DataFrame(records)
        result = result.sort_values('cvd_phenotype_count',
                                    ascending=False).reset_index(drop=True)

        logger.info(f"Derived {len(result)} CVD-related genes from OMIM")
        return result

    def _enrich_with_api(self, gene_disease_df: pd.DataFrame) -> pd.DataFrame:
        """
        Enrich gene-disease data with OMIM API details.

        Queries the API for CVD-related MIM numbers to get clinical synopses,
        allelic variant counts, and reference counts.

        Args:
            gene_disease_df: DataFrame to enrich.

        Returns:
            Enriched DataFrame with additional columns.
        """
        if not self.has_api_access:
            return gene_disease_df

        logger.info("Enriching CVD entries with OMIM API data...")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Get unique CVD-related phenotype MIM numbers
        cvd_entries = gene_disease_df[gene_disease_df['is_cvd']]
        mim_numbers = cvd_entries['phenotype_mim'].dropna().unique()
        mim_numbers = [m for m in mim_numbers if m.strip()]

        logger.info(f"Querying API for {len(mim_numbers)} CVD MIM numbers...")

        enrichment_data = {}
        for mim in mim_numbers:
            cache_file = self.cache_dir / f"entry_{mim}.json"

            if cache_file.exists():
                try:
                    with open(cache_file, 'r') as f:
                        enrichment_data[mim] = json.load(f)
                    continue
                except (json.JSONDecodeError, IOError):
                    pass

            try:
                response = self.session.get(
                    f"{self.OMIM_API_URL}/entry",
                    params={
                        'mimNumber': mim,
                        'include': 'clinicalSynopsis,allelicVariantList',
                        'format': 'json',
                        'apiKey': self.api_key
                    },
                    timeout=15
                )

                if response.status_code == 200:
                    data = response.json()
                    enrichment_data[mim] = data

                    with open(cache_file, 'w') as f:
                        json.dump(data, f, indent=2)
                elif response.status_code == 403:
                    logger.warning("OMIM API key may be invalid or expired")
                    break
                else:
                    logger.debug(f"API returned {response.status_code} for MIM {mim}")

                time.sleep(self.API_RATE_DELAY)

            except requests.RequestException as e:
                logger.warning(f"API request failed for MIM {mim}: {e}")
                continue

        # Add enrichment columns
        clinical_synopses = {}
        variant_counts = {}
        ref_counts = {}

        for mim, data in enrichment_data.items():
            entries = (data.get('omim', {})
                       .get('entryList', []))
            if not entries:
                continue
            entry = entries[0].get('entry', {})

            # Clinical synopsis
            synopsis = entry.get('clinicalSynopsis')
            if synopsis:
                synopsis_parts = []
                for key, value in synopsis.items():
                    if key not in ('mimNumber', 'prefix', 'oldFormatExists',
                                   'exists'):
                        if isinstance(value, str):
                            synopsis_parts.append(f"{key}: {value}")
                clinical_synopses[mim] = '; '.join(synopsis_parts[:5])

            # Allelic variants count
            variants = entry.get('allelicVariantList', [])
            variant_counts[mim] = len(variants)

            # References count
            refs = entry.get('referenceList', [])
            ref_counts[mim] = len(refs)

        # Map enrichment to DataFrame
        gene_disease_df = gene_disease_df.copy()
        gene_disease_df['clinical_synopsis'] = gene_disease_df['phenotype_mim'].map(
            clinical_synopses
        ).fillna('')
        gene_disease_df['allelic_variant_count'] = gene_disease_df['phenotype_mim'].map(
            variant_counts
        ).fillna(0).astype(int)
        gene_disease_df['references_count'] = gene_disease_df['phenotype_mim'].map(
            ref_counts
        ).fillna(0).astype(int)

        enriched_count = len([m for m in mim_numbers if m in enrichment_data])
        logger.info(f"Enriched {enriched_count}/{len(mim_numbers)} CVD entries via API")

        return gene_disease_df

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """
        Get the schema for OMIM parsed data.

        Returns:
            Dictionary describing the schema for each entity type.
        """
        schema = {
            'gene_phenotype_map': {
                'mim_number': 'OMIM MIM number',
                'gene_symbol': 'Approved gene symbol',
                'gene_name': 'Full gene name',
                'chromosome': 'Chromosome',
                'cyto_location': 'Cytogenetic location',
                'entrez_gene_id': 'NCBI Entrez gene ID',
                'ensembl_gene_id': 'Ensembl gene ID',
                'phenotypes_raw': 'Raw phenotype string from OMIM',
                'source_database': 'Source database (OMIM)'
            },
            'gene_disease_relationships': {
                'phenotype': 'Disease/phenotype name',
                'phenotype_mim': 'Phenotype MIM number',
                'gene_symbols': 'Associated gene symbol(s)',
                'gene_mim': 'Gene MIM number',
                'cyto_location': 'Cytogenetic location',
                'mapping_key': 'Phenotype mapping confidence (1-4)',
                'inheritance': 'Inheritance pattern (AD, AR, XL, etc.)',
                'is_cvd': 'Whether phenotype is CVD-related',
                'source_database': 'Source database (OMIM)'
            },
            'omim_cvd_genes': {
                'gene_symbol': 'Gene symbol',
                'gene_mim': 'Gene MIM number',
                'cvd_phenotypes': 'Semicolon-joined CVD phenotype names',
                'cvd_phenotype_count': 'Number of CVD phenotypes',
                'inheritance_patterns': 'Unique inheritance patterns',
                'source_database': 'Source database (OMIM)'
            }
        }

        # Add enrichment columns if API is available
        if self.use_api_enrichment:
            schema['gene_disease_relationships'].update({
                'clinical_synopsis': 'Clinical synopsis from OMIM API',
                'allelic_variant_count': 'Number of allelic variants',
                'references_count': 'Number of references'
            })

        return schema
