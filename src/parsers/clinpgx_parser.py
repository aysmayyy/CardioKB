"""
ClinPGxParser: Parser for ClinPGx pharmacogenomics database.

Queries the ClinPGx REST API (api.clinpgx.org) to extract pharmacogenomics
data including clinical annotations, drug labels, gene info, and variant data,
focused on cardiovascular pharmacogenes and drugs.

Source: https://api.clinpgx.org/v1/data/
Authentication: Not required for basic access.
Rate limit: 2 requests/second; uses 1-second delays to be respectful.
License: Creative Commons Attribution-ShareAlike 4.0
"""

import json
import logging
import time
from typing import Dict, List, Optional
import pandas as pd
import requests
from .base_parser import BaseParser

logger = logging.getLogger(__name__)


class ClinPGxParser(BaseParser):
    """
    Parser for ClinPGx REST API.

    Queries the ClinPGx API for pharmacogenomics data focused on
    cardiovascular pharmacogenes and drugs. Supports caching API
    responses to avoid repeated queries.

    API patterns:
    - clinicalAnnotation?relatedChemicals.name={drug}
    - drugLabel?relatedGenes.symbol={gene}
    - variant?relatedGenes.symbol={gene}
    - gene?symbol={gene}
    - chemical?name={drug}
    """

    BASE_URL = "https://api.clinpgx.org/v1/data/"
    RATE_LIMIT_DELAY = 1.0  # seconds between requests

    # Cardiovascular pharmacogenes with known clinical significance
    CVD_PHARMACOGENES = [
        "CYP2C19",   # clopidogrel metabolism
        "CYP2C9",    # warfarin metabolism
        "VKORC1",    # warfarin target
        "CYP2D6",    # beta-blocker metabolism (metoprolol, carvedilol)
        "SLCO1B1",   # statin transport (simvastatin myopathy)
        "CYP3A4",    # statin metabolism
        "CYP3A5",    # tacrolimus (post-transplant)
        "ADRB1",     # beta-blocker response
        "ADRB2",     # beta-blocker response
        "ACE",       # ACE inhibitor response
        "CETP",      # lipid-related
        "HMGCR",     # statin target
        "PCSK9",     # lipid-related
        "NOS3",      # nitric oxide / vascular
        "F5",        # Factor V Leiden / thrombosis
        "F2",        # prothrombin / thrombosis
        "MTHFR",     # homocysteine / vascular
    ]

    # Cardiovascular drugs with pharmacogenomic significance
    CVD_DRUGS = [
        "warfarin", "clopidogrel", "ticagrelor", "prasugrel",
        "simvastatin", "atorvastatin", "rosuvastatin",
        "metoprolol", "carvedilol", "propranolol",
        "digoxin", "amiodarone", "flecainide",
        "lisinopril", "enalapril", "losartan", "valsartan",
        "heparin", "enoxaparin", "rivaroxaban", "apixaban",
        "aspirin", "nitroglycerin", "hydralazine",
    ]

    def __init__(self, data_dir: Optional[str] = None,
                 genes: Optional[List[str]] = None,
                 drugs: Optional[List[str]] = None,
                 use_cache: bool = True,
                 max_retries: int = 3):
        """
        Initialize ClinPGx parser.

        Args:
            data_dir: Directory for storing cached data.
            genes: List of gene symbols to query. Defaults to CVD_PHARMACOGENES.
            drugs: List of drug names to query. Defaults to CVD_DRUGS.
            use_cache: If True, cache API responses as JSON files.
            max_retries: Max retry attempts for failed API calls.
        """
        super().__init__(data_dir)
        self.genes = genes or self.CVD_PHARMACOGENES
        self.drugs = drugs or self.CVD_DRUGS
        self.use_cache = use_cache
        self.max_retries = max_retries

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CardioKB-Parser/0.1.0',
            'Accept': 'application/json'
        })

        # Cache directory
        self.cache_dir = self.source_dir / "cache"
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Raw data storage
        self._clinical_annotations = []
        self._drug_labels = []
        self._variants = []
        self._gene_info = []

    def _rate_limited_request(self, url: str,
                              params: Optional[dict] = None) -> Optional[dict]:
        """
        Make an API request with rate limiting and retry logic.

        Args:
            url: Full API URL.
            params: Query parameters.

        Returns:
            Parsed JSON response, or None if all retries failed.
        """
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, params=params, timeout=20)

                if response.status_code == 200:
                    time.sleep(self.RATE_LIMIT_DELAY)
                    return response.json()
                elif response.status_code == 429:
                    wait_time = 5 * (attempt + 1)
                    logger.warning(f"Rate limit hit. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                elif response.status_code == 404:
                    logger.debug(f"Not found: {url}")
                    time.sleep(self.RATE_LIMIT_DELAY)
                    return None
                elif response.status_code == 400:
                    logger.debug(f"Bad request: {url} - {response.text[:100]}")
                    time.sleep(self.RATE_LIMIT_DELAY)
                    return None
                else:
                    logger.warning(f"HTTP {response.status_code} for {url}")
                    time.sleep(self.RATE_LIMIT_DELAY)

            except requests.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(3 * (attempt + 1))

        logger.error(f"All retries exhausted for {url}")
        return None

    def _cached_request(self, cache_key: str, url: str,
                        params: Optional[dict] = None) -> Optional[dict]:
        """
        Make a cached API request. Checks cache first, then queries API.
        """
        cache_file = self.cache_dir / f"{cache_key}.json"

        if self.use_cache and cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Cache read failed for {cache_key}: {e}")

        data = self._rate_limited_request(url, params)

        if data is not None and self.use_cache:
            try:
                with open(cache_file, 'w') as f:
                    json.dump(data, f, indent=2)
            except IOError as e:
                logger.warning(f"Cache write failed for {cache_key}: {e}")

        return data

    def _extract_data_list(self, response: Optional[dict]) -> List[dict]:
        """Extract the data list from a ClinPGx API response."""
        if response is None:
            return []
        if isinstance(response, list):
            return response
        if isinstance(response, dict):
            data = response.get('data', [])
            if isinstance(data, list):
                return data
            return [data] if data else []
        return []

    def download_data(self) -> bool:
        """
        Query ClinPGx API for pharmacogenomics data.

        Queries clinical annotations (per drug), drug labels (per gene),
        variants (per gene), and gene info (per gene).

        Returns:
            True if at least some data was retrieved, False on total failure.
        """
        logger.info("Querying ClinPGx API for pharmacogenomics data...")
        logger.info(f"Genes: {len(self.genes)}, Drugs: {len(self.drugs)}")

        success = False

        # 1. Clinical annotations (per drug via relatedChemicals.name)
        logger.info("Fetching clinical annotations by drug...")
        for drug in self.drugs:
            cache_key = f"ca_{drug.replace(' ', '_').lower()}"
            url = f"{self.BASE_URL}clinicalAnnotation"
            resp = self._cached_request(
                cache_key, url,
                params={"relatedChemicals.name": drug, "view": "max"}
            )
            items = self._extract_data_list(resp)
            if items:
                # Tag each item with the queried drug for easier parsing
                for item in items:
                    item['_queried_drug'] = drug
                self._clinical_annotations.extend(items)
        logger.info(f"  Retrieved {len(self._clinical_annotations)} clinical annotations")
        if self._clinical_annotations:
            success = True

        # 2. Drug labels (per gene via relatedGenes.symbol)
        logger.info("Fetching drug labels by gene...")
        seen_label_ids = set()
        for gene in self.genes:
            cache_key = f"dl_{gene.lower()}"
            url = f"{self.BASE_URL}drugLabel"
            resp = self._cached_request(
                cache_key, url,
                params={"relatedGenes.symbol": gene, "view": "max"}
            )
            items = self._extract_data_list(resp)
            for item in items:
                label_id = item.get('id', '')
                if label_id not in seen_label_ids:
                    seen_label_ids.add(label_id)
                    item['_queried_gene'] = gene
                    self._drug_labels.append(item)
        logger.info(f"  Retrieved {len(self._drug_labels)} unique drug labels")
        if self._drug_labels:
            success = True

        # 3. Variants (per gene via relatedGenes.symbol)
        logger.info("Fetching variants by gene...")
        for gene in self.genes:
            cache_key = f"var_{gene.lower()}"
            url = f"{self.BASE_URL}variant"
            resp = self._cached_request(
                cache_key, url,
                params={"relatedGenes.symbol": gene, "view": "max"}
            )
            items = self._extract_data_list(resp)
            for item in items:
                item['_queried_gene'] = gene
            self._variants.extend(items)
        logger.info(f"  Retrieved {len(self._variants)} variants")
        if self._variants:
            success = True

        # 4. Gene info (per gene)
        logger.info("Fetching gene info...")
        for gene in self.genes:
            cache_key = f"gene_{gene.lower()}"
            url = f"{self.BASE_URL}gene"
            resp = self._cached_request(
                cache_key, url,
                params={"symbol": gene, "view": "max"}
            )
            items = self._extract_data_list(resp)
            self._gene_info.extend(items)
        logger.info(f"  Retrieved {len(self._gene_info)} gene records")
        if self._gene_info:
            success = True

        if success:
            logger.info("ClinPGx data download completed successfully")
        else:
            logger.error("No data retrieved from ClinPGx API")

        return success

    def _load_from_cache(self) -> bool:
        """
        Load data from cached JSON files when download was skipped.

        Reads the cache directory and populates in-memory lists from
        previously cached API responses, matching the same logic as
        download_data().

        Returns:
            True if any cached data was loaded, False otherwise.
        """
        if not self.cache_dir.exists():
            return False

        cache_files = list(self.cache_dir.glob("*.json"))
        if not cache_files:
            return False

        logger.info(f"Loading ClinPGx data from {len(cache_files)} cached files...")

        seen_label_ids = set()

        for cache_file in sorted(cache_files):
            try:
                with open(cache_file, 'r') as f:
                    resp = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to read cache file {cache_file.name}: {e}")
                continue

            items = self._extract_data_list(resp)
            if not items:
                continue

            prefix = cache_file.stem.split('_')[0]

            if prefix == 'ca':
                # Clinical annotations — infer drug from filename
                drug = cache_file.stem[3:].replace('_', ' ')
                for item in items:
                    item.setdefault('_queried_drug', drug)
                self._clinical_annotations.extend(items)

            elif prefix == 'dl':
                # Drug labels — deduplicate by label id
                gene = cache_file.stem[3:].upper()
                for item in items:
                    label_id = item.get('id', '')
                    if label_id not in seen_label_ids:
                        seen_label_ids.add(label_id)
                        item.setdefault('_queried_gene', gene)
                        self._drug_labels.append(item)

            elif prefix == 'var':
                # Variants
                gene = cache_file.stem[4:].upper()
                for item in items:
                    item.setdefault('_queried_gene', gene)
                self._variants.extend(items)

            elif prefix == 'gene':
                # Gene info
                self._gene_info.extend(items)

        loaded = (len(self._clinical_annotations) + len(self._drug_labels)
                  + len(self._variants) + len(self._gene_info))
        logger.info(f"  Loaded from cache: {len(self._clinical_annotations)} annotations, "
                    f"{len(self._drug_labels)} drug labels, "
                    f"{len(self._variants)} variants, "
                    f"{len(self._gene_info)} gene records")
        return loaded > 0

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse ClinPGx API responses into structured DataFrames.

        If in-memory data is empty (e.g. --skip-download), loads from
        cached JSON files in data/raw/clinpgx/cache/.

        Returns:
            Dictionary with DataFrames for clinical_annotations, drug_labels,
            variants, and gene_info.
        """
        # Load from cache if download was skipped
        has_data = (self._clinical_annotations or self._drug_labels
                    or self._variants or self._gene_info)
        if not has_data:
            self._load_from_cache()

        logger.info("Parsing ClinPGx data...")

        result = {}
        result['clinical_annotations'] = self._parse_clinical_annotations()
        result['drug_labels'] = self._parse_drug_labels()
        result['variants'] = self._parse_variants()
        result['gene_info'] = self._parse_gene_info()

        for key, df in result.items():
            logger.info(f"  {key}: {len(df)} rows")

        return result

    def _parse_clinical_annotations(self) -> pd.DataFrame:
        """Parse clinical annotation data into a DataFrame."""
        records = []
        for item in self._clinical_annotations:
            # Extract gene from location.genes
            genes = []
            location = item.get('location', {})
            if isinstance(location, dict):
                for g in location.get('genes', []):
                    genes.append(g.get('symbol', ''))

            # Extract drugs from relatedChemicals
            drugs = []
            for chem in item.get('relatedChemicals', []):
                drugs.append(chem.get('name', ''))

            # Extract evidence level
            loe = item.get('levelOfEvidence', {})
            evidence_level = loe.get('term', '') if isinstance(loe, dict) else str(loe)

            # Extract variant display name
            display_name = location.get('displayName', '') if isinstance(location, dict) else ''

            records.append({
                'annotation_id': item.get('accessionId', item.get('id', '')),
                'gene': '; '.join(genes) if genes else '',
                'drug': '; '.join(drugs) if drugs else item.get('_queried_drug', ''),
                'variant': display_name,
                'evidence_level': evidence_level,
                'types': '; '.join(item.get('types', [])),
                'source_database': 'ClinPGx'
            })

        if not records:
            return pd.DataFrame(columns=[
                'annotation_id', 'gene', 'drug', 'variant',
                'evidence_level', 'types', 'source_database'
            ])
        return pd.DataFrame(records)

    def _parse_drug_labels(self) -> pd.DataFrame:
        """Parse drug label data into a DataFrame."""
        records = []
        for item in self._drug_labels:
            # Extract genes
            genes = []
            for g in item.get('relatedGenes', []):
                genes.append(g.get('symbol', ''))

            # Extract drugs
            drugs = []
            for c in item.get('relatedChemicals', []):
                drugs.append(c.get('name', ''))

            records.append({
                'label_id': item.get('id', ''),
                'name': item.get('name', ''),
                'drug': '; '.join(drugs) if drugs else '',
                'gene': '; '.join(genes) if genes else '',
                'source': item.get('source', ''),
                'biomarker_status': item.get('biomarkerStatus', ''),
                'testing': item.get('testing', {}).get('term', '') if isinstance(item.get('testing'), dict) else str(item.get('testing', '')),
                'alternate_drug_available': item.get('alternateDrugAvailable', ''),
                'source_database': 'ClinPGx'
            })

        if not records:
            return pd.DataFrame(columns=[
                'label_id', 'name', 'drug', 'gene', 'source',
                'biomarker_status', 'testing', 'alternate_drug_available',
                'source_database'
            ])
        return pd.DataFrame(records)

    def _parse_variants(self) -> pd.DataFrame:
        """Parse variant data into a DataFrame."""
        records = []
        for item in self._variants:
            # Extract genes
            genes = []
            for g in item.get('relatedGenes', []):
                genes.append(g.get('symbol', ''))

            # Extract location info
            locations = item.get('locations', [])
            chromosome = ''
            position = ''
            if locations and isinstance(locations[0], dict):
                chromosome = locations[0].get('chromosomeName', '')
                position = str(locations[0].get('gpPosition', ''))

            records.append({
                'variant_id': item.get('symbol', item.get('id', '')),
                'variant_name': item.get('name', ''),
                'gene': '; '.join(genes) if genes else item.get('_queried_gene', ''),
                'chromosome': chromosome,
                'position': position,
                'change_classification': item.get('changeClassification', ''),
                'source_database': 'ClinPGx'
            })

        if not records:
            return pd.DataFrame(columns=[
                'variant_id', 'variant_name', 'gene', 'chromosome',
                'position', 'change_classification', 'source_database'
            ])
        return pd.DataFrame(records)

    def _parse_gene_info(self) -> pd.DataFrame:
        """Parse gene info into a DataFrame."""
        records = []
        for item in self._gene_info:
            chr_info = item.get('chr', {})
            records.append({
                'clinpgx_id': item.get('id', ''),
                'gene_symbol': item.get('symbol', ''),
                'gene_name': item.get('name', ''),
                'chromosome': chr_info.get('name', '') if isinstance(chr_info, dict) else '',
                'cpic_gene': item.get('cpicGene', False),
                'vip_tier': item.get('vipTier', ''),
                'source_database': 'ClinPGx'
            })

        if not records:
            return pd.DataFrame(columns=[
                'clinpgx_id', 'gene_symbol', 'gene_name', 'chromosome',
                'cpic_gene', 'vip_tier', 'source_database'
            ])
        return pd.DataFrame(records)

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """
        Get the schema for ClinPGx/ClinPGx parsed data.

        Returns:
            Dictionary describing the schema for each entity type.
        """
        return {
            'clinical_annotations': {
                'annotation_id': 'ClinPGx accession ID',
                'gene': 'Gene symbol(s)',
                'drug': 'Drug name(s)',
                'variant': 'Variant display name (e.g., rs number)',
                'evidence_level': 'Level of evidence (1A, 1B, 2A, 2B, 3, 4)',
                'types': 'Annotation types',
                'source_database': 'Source database (ClinPGx)'
            },
            'drug_labels': {
                'label_id': 'ClinPGx label annotation ID',
                'name': 'Label annotation name',
                'drug': 'Drug name(s)',
                'gene': 'Gene symbol(s)',
                'source': 'Regulatory source (FDA, EMA, etc.)',
                'biomarker_status': 'Biomarker status',
                'testing': 'Testing recommendation',
                'alternate_drug_available': 'Whether alternate drug is available',
                'source_database': 'Source database (ClinPGx)'
            },
            'variants': {
                'variant_id': 'Variant rsID (e.g., rs4244285)',
                'variant_name': 'Variant name',
                'gene': 'Gene symbol',
                'chromosome': 'Chromosome',
                'position': 'Genomic position (GRCh38)',
                'change_classification': 'Type of change (Missense, Synonymous, etc.)',
                'source_database': 'Source database (ClinPGx)'
            },
            'gene_info': {
                'clinpgx_id': 'ClinPGx gene ID',
                'gene_symbol': 'Gene symbol',
                'gene_name': 'Full gene name',
                'chromosome': 'Chromosome',
                'cpic_gene': 'Whether gene has CPIC guideline',
                'vip_tier': 'VIP (Very Important Pharmacogene) tier',
                'source_database': 'Source database (ClinPGx)'
            }
        }
