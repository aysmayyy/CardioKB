"""
CardioKB - Main Pipeline

Orchestrates the complete CardioKB knowledge base construction pipeline:
1. Data retrieval and parsing from all sources
2. Export to TSV format for archival
3. Load into Neo4j via Cypher (replaces AlzKB's ista/RDF/Memgraph pathway)
4. Statistics and release notes generation
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict

import pandas as pd

# Ensure project root is on path so 'src' package is importable
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.ontology_configs import (
    ONTOLOGY_CONFIGS,
    CT_TRIAL_STUDIES_CONDITION,
    CT_TRIAL_TESTS_INTERVENTION,
    CLINPGX_CLINICAL_ANNOTATIONS,
    CLINPGX_CLINICAL_ANNOTATIONS_PHARMA_CLASS,
    CLINPGX_DRUG_LABEL_ANNOTATES_GENE,
    CLINPGX_DRUG_LABEL_DESCRIBES_DRUG,
)
from src.neo4j_loader import Neo4jLoader
from src.parsers import (
    ClinicalTrialsParser,
    ClinPGxParser,
    OMIMParser,
    AOPDBParser,
    DisGeNETParser,
    DrugBankParser,
    NCBIGeneParser,
    DoRothEAParser,
    # Hetionet component parsers
    DiseaseOntologyParser,
    GeneOntologyParser,
    UberonParser,
    MeSHParser,
    GWASParser,
    DrugCentralParser,
    BindingDBParser,
    BgeeParser,
    CTDParser,
    HetionetPrecomputedParser,
    PubTatorParser,
    SIDERParser,
    LINCS1000Parser,
    MEDLINECooccurrenceParser,
    JensenLabParser,
    JensenTissuesParser,
    HPOParser,
    ReactomeParser,
    WikiPathwaysParser,
    STRINGParser,
    OpenTargetsParser,
)

logger = logging.getLogger(__name__)


def setup_logging(log_level: str = None):
    """
    Configure project-wide logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                   If None, checks CARDIOKB_LOG_LEVEL env var, defaults to INFO.
    """
    if log_level is None:
        log_level = os.environ.get('CARDIOKB_LOG_LEVEL', 'INFO')

    level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('cardiokb_build.log'),
            logging.StreamHandler()
        ],
        force=True
    )

    logger.info(f"Logging level set to: {log_level.upper()}")


class CardioKBPipeline:
    """Main pipeline for building CardioKB."""

    def __init__(self, base_dir: str):
        """
        Initialize the CardioKB pipeline.

        Args:
            base_dir: Base directory for the project
        """
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.output_dir = self.data_dir / "output"

        # Create directories
        for dir_path in [self.raw_dir, self.processed_dir, self.output_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Statistics
        self.stats = {
            'sources_processed': 0,
            'sources_failed': 0,
            'total_nodes': 0,
            'total_edges': 0,
            'start_time': datetime.now(),
            'end_time': None,
            'source_details': {},
        }

    def run_full_pipeline(self, skip_download: bool = False,
                          skip_neo4j: bool = False):
        """
        Run the complete CardioKB construction pipeline.

        Args:
            skip_download: If True, skip data download (use existing files)
            skip_neo4j: If True, skip Neo4j loading (parse + TSV export only)
        """
        logger.info("=" * 80)
        logger.info("CardioKB - Complete Pipeline")
        logger.info("=" * 80)
        logger.info(f"Start time: {self.stats['start_time']}")
        logger.info(f"Base directory: {self.base_dir}")
        logger.info(f"Skip download: {skip_download}")
        logger.info(f"Skip Neo4j: {skip_neo4j}")
        logger.info("=" * 80)

        try:
            # Step 1: Retrieve and parse data
            logger.info("=" * 80)
            logger.info("STEP 1: Data Retrieval and Parsing")
            logger.info("=" * 80)
            parsed_data = self.retrieve_and_parse_data(skip_download)

            # Step 2: Export to TSV
            logger.info("=" * 80)
            logger.info("STEP 2: Export to TSV")
            logger.info("=" * 80)
            self.export_to_tsv(parsed_data)

            # Step 3: Load into Neo4j
            if not skip_neo4j:
                logger.info("=" * 80)
                logger.info("STEP 3: Neo4j Loading")
                logger.info("=" * 80)
                self.load_to_neo4j(parsed_data)
            else:
                logger.info("=" * 80)
                logger.info("STEP 3: Neo4j Loading (SKIPPED)")
                logger.info("=" * 80)

            # Step 4: Compute specificity scores
            if not skip_neo4j:
                logger.info("=" * 80)
                logger.info("STEP 4: Compute Disease-Specificity Scores")
                logger.info("=" * 80)
                from scripts.compute_specificity import compute_specificity
                compute_specificity()
            else:
                logger.info("=" * 80)
                logger.info("STEP 4: Specificity Scores (SKIPPED — no Neo4j)")
                logger.info("=" * 80)

            # Step 5: Generate stats and release notes
            logger.info("=" * 80)
            logger.info("STEP 5: Release Notes Generation")
            logger.info("=" * 80)
            self.generate_stats_and_notes()

            self.stats['end_time'] = datetime.now()
            duration = self.stats['end_time'] - self.stats['start_time']

            logger.info("=" * 80)
            logger.info("Pipeline Completed Successfully!")
            logger.info("=" * 80)
            logger.info(f"Duration: {duration}")
            logger.info(f"Sources processed: {self.stats['sources_processed']}")
            logger.info(f"Sources failed: {self.stats['sources_failed']}")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(f"{'=' * 80}")
            logger.error(f"Pipeline Failed: {e}")
            logger.error(f"{'=' * 80}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def retrieve_and_parse_data(self, skip_download: bool = False) -> Dict[str, Dict]:
        """
        Retrieve and parse data from all sources.

        Args:
            skip_download: If True, skip download step.

        Returns:
            Dictionary mapping source names to parsed data.
        """
        parsed_data = {}

        from dotenv import load_dotenv
        load_dotenv()

        parsers = self._get_parsers()

        # Sources with very slow raw-file parsing; prefer cached TSVs when available
        SLOW_PARSERS = {'pubtator', 'bgee'}

        for source_name, parser in parsers.items():
            logger.info(f"{'=' * 60}")
            logger.info(f"Processing {source_name.upper()}")
            logger.info(f"{'=' * 60}")

            try:
                # For slow parsers with --skip-download, prefer cached TSVs
                if skip_download and source_name in SLOW_PARSERS:
                    src_dir = self.processed_dir / source_name
                    if src_dir.exists():
                        tsv_files = list(src_dir.glob('*.tsv'))
                        tsv_data = {}
                        for tsv_path in tsv_files:
                            df = pd.read_csv(tsv_path, sep='\t')
                            if len(df) > 0:
                                tsv_data[tsv_path.stem] = df
                        if tsv_data:
                            parsed_data[source_name] = tsv_data
                            self.stats['sources_processed'] += 1
                            logger.info(f"Loaded {source_name} from cached TSVs (skipped slow re-parse)")
                            for key, df in tsv_data.items():
                                logger.info(f"  - {key}: {len(df)} records")
                                self.stats['source_details'][f"{source_name}.{key}"] = len(df)
                            continue

                if not skip_download:
                    logger.info(f"Downloading {source_name} data...")
                    download_success = parser.download_data()
                    if not download_success:
                        logger.warning(f"Download failed for {source_name}, attempting to use existing data")

                logger.info(f"Parsing {source_name} data...")
                data = parser.parse_data()

                if data:
                    parsed_data[source_name] = data
                    self.stats['sources_processed'] += 1
                    logger.info(f"Successfully processed {source_name}")

                    for key, df in data.items():
                        if hasattr(df, '__len__'):
                            logger.info(f"  - {key}: {len(df)} records")
                            self.stats['source_details'][f"{source_name}.{key}"] = len(df)
                else:
                    logger.warning(f"No data parsed for {source_name}")
                    self.stats['sources_failed'] += 1

            except Exception as e:
                logger.error(f"Failed to process {source_name}: {e}")
                self.stats['sources_failed'] += 1
                import traceback
                logger.error(traceback.format_exc())

        # Post-processing: explode clinical trial edges
        if 'clinicaltrials' in parsed_data:
            ct_data = parsed_data['clinicaltrials']
            edge_dfs = self._explode_clinical_trial_edges(ct_data)
            ct_data.update(edge_dfs)

        # Post-processing: case-match ClinicalTrials conditions/interventions
        # to Disease.commonName and Drug.commonName (graph uses lowercase Disease
        # Ontology names and title-case DrugBank names)
        if 'clinicaltrials' in parsed_data:
            ct_data = parsed_data['clinicaltrials']
            self._normalize_clinical_trial_edges(ct_data, parsed_data)

        # Post-processing: create variant_in_gene edges from ClinPGx variants
        if 'clinpgx' in parsed_data:
            cpgx = parsed_data['clinpgx']
            if 'variants' in cpgx:
                variants_df = cpgx['variants']
                if 'variant_id' in variants_df.columns and 'gene' in variants_df.columns:
                    vig = variants_df[['variant_id', 'gene']].dropna().copy()
                    vig = vig[vig['gene'] != '']
                    cpgx['variant_in_gene'] = vig
                    logger.info(f"Created {len(vig)} variant_in_gene edges")

        # Post-processing: normalize ClinPGx clinical_annotations drug names
        if 'clinpgx' in parsed_data:
            cpgx = parsed_data['clinpgx']
            drug_df, pharma_df = self._normalize_clinpgx_annotations(
                cpgx, parsed_data
            )
            if drug_df is not None:
                cpgx[CLINPGX_CLINICAL_ANNOTATIONS] = drug_df
            if pharma_df is not None:
                cpgx[CLINPGX_CLINICAL_ANNOTATIONS_PHARMA_CLASS] = pharma_df

        # Post-processing: create DrugLabel edge DataFrames from drug_labels
        if 'clinpgx' in parsed_data:
            cpgx = parsed_data['clinpgx']
            if 'drug_labels' in cpgx:
                dl = cpgx['drug_labels']
                if 'label_id' in dl.columns and 'gene' in dl.columns:
                    # Explode semicolon-delimited genes
                    gene_edges = dl[['label_id', 'gene']].copy()
                    gene_edges['gene'] = gene_edges['gene'].astype(str)
                    gene_edges = gene_edges.assign(
                        gene=gene_edges['gene'].str.split('; ')
                    ).explode('gene')
                    gene_edges['gene'] = gene_edges['gene'].str.strip()
                    gene_edges = gene_edges[
                        gene_edges['gene'].notna()
                        & (gene_edges['gene'] != '')
                        & (gene_edges['gene'] != 'nan')
                    ]
                    gene_edges = gene_edges.drop_duplicates()
                    cpgx[CLINPGX_DRUG_LABEL_ANNOTATES_GENE] = gene_edges
                    logger.info(f"Created {len(gene_edges)} drug_label→gene edges")

                if 'label_id' in dl.columns and 'drug' in dl.columns:
                    # Explode semicolon-delimited drugs and case-match to DrugBank
                    drug_edges = dl[['label_id', 'drug']].copy()
                    drug_edges['drug'] = drug_edges['drug'].astype(str)
                    drug_edges = drug_edges.assign(
                        drug=drug_edges['drug'].str.split('; ')
                    ).explode('drug')
                    drug_edges['drug'] = drug_edges['drug'].str.strip()
                    drug_edges = drug_edges[
                        drug_edges['drug'].notna()
                        & (drug_edges['drug'] != '')
                        & (drug_edges['drug'] != 'nan')
                    ]
                    # Build case-insensitive DrugBank lookup for name matching
                    db_lookup = {}
                    if 'drugbank' in parsed_data and 'drugs' in parsed_data['drugbank']:
                        db_drugs = parsed_data['drugbank']['drugs']
                        if 'drug_name' in db_drugs.columns:
                            for name in db_drugs['drug_name'].dropna():
                                db_lookup[name.lower()] = name
                    if db_lookup:
                        drug_edges['drug'] = drug_edges['drug'].apply(
                            lambda x: db_lookup.get(x.lower(), x)
                        )
                    drug_edges = drug_edges.drop_duplicates()
                    cpgx[CLINPGX_DRUG_LABEL_DESCRIBES_DRUG] = drug_edges
                    logger.info(f"Created {len(drug_edges)} drug_label→drug edges")

        # Post-processing: prepare OMIM gene-disease edges
        if 'omim' in parsed_data:
            omim_data = parsed_data['omim']
            if 'gene_disease_relationships' in omim_data:
                gdr = omim_data['gene_disease_relationships'].copy()
                # Extract primary gene symbol (first before comma)
                gdr['primary_gene_symbol'] = (
                    gdr['gene_symbols'].str.split(',').str[0].str.strip()
                )
                # Keep rows with valid gene symbol and phenotype MIM
                gdr = gdr.dropna(subset=['primary_gene_symbol', 'phenotype_mim'])
                gdr = gdr[
                    (gdr['primary_gene_symbol'] != '') &
                    (gdr['phenotype_mim'] != '')
                ].copy()
                # Ensure phenotype_mim is string to match xrefOMIM in Neo4j
                gdr['phenotype_mim'] = gdr['phenotype_mim'].astype(str)
                omim_data['gene_disease'] = gdr
                # Also store under node config key so both configs use
                # in-memory data with consistent string types
                omim_data['gene_disease_nodes'] = gdr
                logger.info(
                    f"Created {len(gdr)} OMIM gene-disease edges "
                    f"({gdr['primary_gene_symbol'].nunique()} unique genes)"
                )

        # Post-processing: prefix CTD chemical_id with 'MESH:' to match Drug.xrefMeSH
        if 'ctd' in parsed_data:
            for key in ('chemical_increases_expression', 'chemical_decreases_expression'):
                if key in parsed_data['ctd']:
                    df = parsed_data['ctd'][key]
                    if 'chemical_id' in df.columns:
                        df['chemical_id'] = df['chemical_id'].apply(
                            lambda x: f'MESH:{x}' if pd.notna(x) and not str(x).startswith('MESH:') else x
                        )
                        logger.info(f"Prefixed CTD {key} chemical_id with MESH:")

        # Post-processing: remap PubTator MESH IDs to DOID, GWAS trait to DOID
        from src.id_mapping import remap_pubtator_mesh_to_doid, remap_gwas_disease_to_doid

        # TSV fallback: for sources that failed parsing or returned all-empty
        # DataFrames, load from existing processed TSVs
        for source_name in list(parsers.keys()):
            needs_fallback = source_name not in parsed_data
            if not needs_fallback and source_name in parsed_data:
                # Check if all DataFrames are empty (e.g. ClinPGx with --skip-download)
                all_empty = all(
                    hasattr(df, '__len__') and len(df) == 0
                    for df in parsed_data[source_name].values()
                )
                if all_empty and parsed_data[source_name]:
                    needs_fallback = True

            if needs_fallback:
                src_dir = self.processed_dir / source_name
                if src_dir.exists():
                    tsv_files = list(src_dir.glob('*.tsv'))
                    if tsv_files:
                        fallback_data = {}
                        for tsv_path in tsv_files:
                            data_name = tsv_path.stem
                            df = pd.read_csv(tsv_path, sep='\t')
                            if len(df) > 0:
                                fallback_data[data_name] = df
                                logger.info(f"Loaded {source_name}/{data_name} from TSV fallback ({len(df)} rows)")
                        if fallback_data:
                            parsed_data[source_name] = fallback_data

        if 'pubtator' in parsed_data and 'disease_ontology' in parsed_data:
            remap_pubtator_mesh_to_doid(parsed_data)
        if 'gwas' in parsed_data and 'disease_ontology' in parsed_data:
            remap_gwas_disease_to_doid(parsed_data)

        return parsed_data

    def _get_parsers(self) -> Dict:
        """
        Instantiate all parsers with appropriate configurations.

        Returns:
            Dictionary of {source_name: parser_instance}.
        """
        parsers = {}

        # Custom parsers (always enabled)
        parsers['clinicaltrials'] = ClinicalTrialsParser(
            data_dir=str(self.raw_dir),
        )
        parsers['clinpgx'] = ClinPGxParser(
            data_dir=str(self.raw_dir),
        )

        # Base KB parsers
        parsers['ncbigene'] = NCBIGeneParser(
            data_dir=str(self.raw_dir),
        )
        parsers['dorothea'] = DoRothEAParser(
            data_dir=str(self.raw_dir),
        )

        # Hetionet component parsers (all disease-agnostic, no credentials needed)
        parsers['disease_ontology'] = DiseaseOntologyParser(
            data_dir=str(self.raw_dir),
        )
        parsers['gene_ontology'] = GeneOntologyParser(
            data_dir=str(self.raw_dir),
        )
        parsers['uberon'] = UberonParser(
            data_dir=str(self.raw_dir),
        )
        parsers['mesh'] = MeSHParser(
            data_dir=str(self.raw_dir),
        )
        parsers['sider'] = SIDERParser(
            data_dir=str(self.raw_dir),
        )
        parsers['lincs'] = LINCS1000Parser(
            data_dir=str(self.raw_dir),
        )
        parsers['medline'] = MEDLINECooccurrenceParser(
            data_dir=str(self.raw_dir),
        )
        parsers['drugcentral'] = DrugCentralParser(
            data_dir=str(self.raw_dir),
        )
        parsers['gwas'] = GWASParser(
            data_dir=str(self.raw_dir),
        )
        parsers['pubtator'] = PubTatorParser(
            data_dir=str(self.raw_dir),
        )
        parsers['bindingdb'] = BindingDBParser(
            data_dir=str(self.raw_dir),
        )
        parsers['ctd'] = CTDParser(
            data_dir=str(self.raw_dir),
        )
        parsers['bgee'] = BgeeParser(
            data_dir=str(self.raw_dir),
        )
        parsers['hetionet_precomputed'] = HetionetPrecomputedParser(
            data_dir=str(self.raw_dir),
        )
        parsers['jensenlab'] = JensenLabParser(
            data_dir=str(self.raw_dir),
        )
        parsers['jensentissues'] = JensenTissuesParser(
            data_dir=str(self.raw_dir),
        )
        parsers['hpo'] = HPOParser(
            data_dir=str(self.raw_dir),
        )
        parsers['reactome'] = ReactomeParser(
            data_dir=str(self.raw_dir),
        )
        parsers['wikipathways'] = WikiPathwaysParser(
            data_dir=str(self.raw_dir),
        )
        parsers['string'] = STRINGParser(
            data_dir=str(self.raw_dir),
        )
        parsers['opentargets'] = OpenTargetsParser(
            data_dir=str(self.raw_dir),
        )

        # Parsers requiring credentials (only add if configured)
        if os.getenv('OMIM_API_KEY'):
            parsers['omim'] = OMIMParser(
                data_dir=str(self.raw_dir),
                api_key=os.getenv('OMIM_API_KEY'),
            )
        else:
            logger.warning("OMIM_API_KEY not set - OMIM parser disabled")

        if os.getenv('DISGENET_API_KEY'):
            parsers['disgenet'] = DisGeNETParser(
                data_dir=str(self.raw_dir),
                api_key=os.getenv('DISGENET_API_KEY'),
            )
        else:
            logger.warning("DISGENET_API_KEY not set - DisGeNET parser disabled")

        if os.getenv('DRUGBANK_USERNAME') and os.getenv('DRUGBANK_PASSWORD'):
            parsers['drugbank'] = DrugBankParser(
                data_dir=str(self.raw_dir),
                username=os.getenv('DRUGBANK_USERNAME'),
                password=os.getenv('DRUGBANK_PASSWORD'),
            )
        else:
            # Check for XML file (no credentials required)
            drugbank_dir = self.raw_dir / 'drugbank'
            xml_files = list(drugbank_dir.glob('*.xml')) if drugbank_dir.exists() else []
            if xml_files:
                logger.info("DRUGBANK credentials not set, but XML found - enabling DrugBank parser")
                parsers['drugbank'] = DrugBankParser(data_dir=str(self.raw_dir))
            else:
                logger.warning("DRUGBANK credentials not set and no XML found - DrugBank parser disabled")

        mysql_user = os.getenv('MYSQL_USERNAME')
        mysql_pass = os.getenv('MYSQL_PASSWORD')
        if mysql_user and mysql_pass:
            parsers['aopdb'] = AOPDBParser(
                data_dir=str(self.raw_dir),
                mysql_config={
                    'host': 'localhost',
                    'user': mysql_user,
                    'password': mysql_pass,
                    'database': os.getenv('MYSQL_DB_NAME', 'aopdb'),
                }
            )
        else:
            # Check for SQL dump file (no MySQL required)
            aopdb_dir = self.raw_dir / 'aopdb'
            sql_dumps = list(aopdb_dir.glob('*.sql')) if aopdb_dir.exists() else []
            if sql_dumps:
                logger.info("MySQL credentials not set, but SQL dump found - enabling AOP-DB parser")
                parsers['aopdb'] = AOPDBParser(data_dir=str(self.raw_dir))
            else:
                logger.warning("MySQL credentials not set and no SQL dump found - AOP-DB parser disabled")

        return parsers

    def _explode_clinical_trial_edges(self, ct_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """
        Explode semicolon-delimited conditions and interventions into edge DataFrames.

        Args:
            ct_data: ClinicalTrials parsed data containing 'clinical_trials' DataFrame.

        Returns:
            Dictionary with trial_studies_condition and trial_tests_intervention DataFrames.
        """
        result = {}

        if 'clinical_trials' not in ct_data:
            return result

        trials_df = ct_data['clinical_trials']

        # Trial -> condition edges
        if 'condition' in trials_df.columns:
            rows = []
            for _, row in trials_df.iterrows():
                conditions = str(row.get('condition', '')).split('; ')
                for cond in conditions:
                    cond = cond.strip()
                    if cond and cond != 'Not specified':
                        rows.append({
                            'trial_id': row['trial_id'],
                            'condition': cond,
                        })
            if rows:
                result[CT_TRIAL_STUDIES_CONDITION] = pd.DataFrame(rows)
                logger.info(f"Created {len(rows)} trial-condition edges")

        # Trial -> intervention edges
        if 'intervention_name' in trials_df.columns:
            rows = []
            for _, row in trials_df.iterrows():
                interventions = str(row.get('intervention_name', '')).split('; ')
                for intv in interventions:
                    intv = intv.strip()
                    if intv and intv != 'Not specified':
                        rows.append({
                            'trial_id': row['trial_id'],
                            'intervention_name': intv,
                        })
            if rows:
                result[CT_TRIAL_TESTS_INTERVENTION] = pd.DataFrame(rows)
                logger.info(f"Created {len(rows)} trial-intervention edges")

        return result

    def _normalize_clinical_trial_edges(
        self, ct_data: Dict[str, pd.DataFrame], parsed_data: Dict
    ):
        """
        Case-match ClinicalTrials condition and intervention names to
        Disease.commonName and Drug.commonName so the Neo4j loader's exact
        MATCH succeeds.
        """
        # Build Disease case-insensitive lookup from Disease Ontology + DisGeNET + OMIM
        disease_lookup: Dict[str, str] = {}
        for src in ('disease_ontology', 'disgenet', 'omim'):
            if src not in parsed_data:
                continue
            for key, df in parsed_data[src].items():
                name_col = None
                for candidate in ('commonName', 'diseaseName', 'disease_name'):
                    if candidate in df.columns:
                        name_col = candidate
                        break
                if name_col:
                    for name in df[name_col].dropna():
                        disease_lookup[str(name).lower()] = str(name)

        # Build Drug case-insensitive lookup from DrugBank + AOP-DB
        drug_lookup: Dict[str, str] = {}
        for src in ('drugbank', 'aopdb'):
            if src not in parsed_data:
                continue
            for key, df in parsed_data[src].items():
                name_col = None
                for candidate in ('drug_name', 'chemical_name', 'commonName'):
                    if candidate in df.columns:
                        name_col = candidate
                        break
                if name_col:
                    for name in df[name_col].dropna():
                        drug_lookup[str(name).lower()] = str(name)

        logger.info(
            f"ClinicalTrials normalization: "
            f"{len(disease_lookup)} disease names, {len(drug_lookup)} drug names"
        )

        # Normalize condition names
        if CT_TRIAL_STUDIES_CONDITION in ct_data and disease_lookup:
            df = ct_data[CT_TRIAL_STUDIES_CONDITION]
            before = df['condition'].isin(disease_lookup.values()).sum()
            df['condition'] = df['condition'].apply(
                lambda x: disease_lookup.get(str(x).lower(), x)
            )
            after = df['condition'].isin(disease_lookup.values()).sum()
            logger.info(
                f"  Conditions: {before} exact -> {after} after case-match "
                f"({after - before} new matches)"
            )

        # Normalize intervention names
        if CT_TRIAL_TESTS_INTERVENTION in ct_data and drug_lookup:
            df = ct_data[CT_TRIAL_TESTS_INTERVENTION]
            before = df['intervention_name'].isin(drug_lookup.values()).sum()
            df['intervention_name'] = df['intervention_name'].apply(
                lambda x: drug_lookup.get(str(x).lower(), x)
            )
            after = df['intervention_name'].isin(drug_lookup.values()).sum()
            logger.info(
                f"  Interventions: {before} exact -> {after} after case-match "
                f"({after - before} new matches)"
            )

    # Manual synonym map: ClinPGx drug name -> (node_type, exact_name)
    CLINPGX_DRUG_SYNONYMS = {
        'aspirin': ('Drug', 'Acetylsalicylic acid'),
        'simvastatin acid': ('Drug', 'Simvastatin'),
        'HMG-CoA reductase inhibitors': ('PharmacologicClass', 'HMG-CoA Reductase Inhibitor'),
        'Bisphosphonates': ('PharmacologicClass', 'Bisphosphonate'),
        'diuretics': ('PharmacologicClass', 'Diuretics'),
        'Beta Blocking Agents': ('PharmacologicClass', 'beta-Adrenergic Blocker'),
        'Antibiotics': ('PharmacologicClass', 'Antibiotics, Antineoplastic'),
        'Ace Inhibitors, Plain': ('PharmacologicClass', 'Angiotensin-converting Enzyme Inhibitors'),
        'Angiotensin II Antagonists': ('PharmacologicClass', 'Angiotensin II Type 1 Receptor Blockers'),
        'antipsychotics': ('PharmacologicClass', 'Antipsychotic Agents'),
    }

    # Drug entries with no match (drug class names without a good node)
    CLINPGX_DROP = {
        'Antiinflammatory agents, non-steroids',
        'Pyrazolones',
        'propionic acid derivatives',
    }

    def _normalize_clinpgx_annotations(
        self, cpgx: Dict[str, pd.DataFrame], parsed_data: Dict
    ):
        """
        Normalize ClinPGx clinical_annotations: explode semicolons,
        case-match drug names to DrugBank, and split Drug vs PharmacologicClass.

        Returns:
            (drug_df, pharma_df) — two DataFrames, or (None, None) if no data.
        """
        if CLINPGX_CLINICAL_ANNOTATIONS not in cpgx:
            return None, None

        ann = cpgx[CLINPGX_CLINICAL_ANNOTATIONS].copy()
        if 'drug' not in ann.columns or 'gene' not in ann.columns:
            return None, None

        # Step 1: Explode semicolon-delimited drug entries
        ann['drug'] = ann['drug'].astype(str)
        ann = ann.assign(drug=ann['drug'].str.split('; ')).explode('drug')
        ann['drug'] = ann['drug'].str.strip()
        ann = ann[ann['drug'].notna() & (ann['drug'] != '') & (ann['drug'] != 'nan')]

        # Build DrugBank case-insensitive lookup
        db_lookup = {}
        if 'drugbank' in parsed_data and 'drugs' in parsed_data['drugbank']:
            db_drugs = parsed_data['drugbank']['drugs']
            if 'drug_name' in db_drugs.columns:
                for name in db_drugs['drug_name'].dropna():
                    db_lookup[name.lower()] = name

        drug_rows = []
        pharma_rows = []

        for _, row in ann.iterrows():
            drug_name = row['drug']
            gene = row.get('gene', '')

            if not gene or pd.isna(gene) or str(gene).strip() == '':
                continue

            # Check if it should be dropped
            if drug_name in self.CLINPGX_DROP:
                continue

            # Check synonym map first
            if drug_name in self.CLINPGX_DRUG_SYNONYMS:
                node_type, exact_name = self.CLINPGX_DRUG_SYNONYMS[drug_name]
                new_row = row.to_dict()
                if node_type == 'Drug':
                    new_row['drug'] = exact_name
                    drug_rows.append(new_row)
                else:
                    new_row['pharma_class'] = exact_name
                    pharma_rows.append(new_row)
                continue

            # Try case-insensitive DrugBank match
            db_match = db_lookup.get(drug_name.lower())
            if db_match:
                new_row = row.to_dict()
                new_row['drug'] = db_match
                drug_rows.append(new_row)
            else:
                logger.debug(f"ClinPGx drug not matched: {drug_name}")

        drug_df = pd.DataFrame(drug_rows) if drug_rows else None
        pharma_df = pd.DataFrame(pharma_rows) if pharma_rows else None

        if drug_df is not None:
            drug_df = drug_df.drop_duplicates(subset=['gene', 'drug'])
            logger.info(
                f"ClinPGx AFFECTS_RESPONSE_TO (Drug): {len(drug_df)} edges"
            )
        if pharma_df is not None:
            pharma_df = pharma_df.drop_duplicates(subset=['gene', 'pharma_class'])
            logger.info(
                f"ClinPGx AFFECTS_RESPONSE_TO (PharmacologicClass): {len(pharma_df)} edges"
            )

        return drug_df, pharma_df

    def export_to_tsv(self, parsed_data: Dict[str, Dict]):
        """
        Export parsed data to TSV files.

        Args:
            parsed_data: Dictionary of parsed data from all sources.
        """
        for source_name, data in parsed_data.items():
            logger.info(f"Exporting {source_name} to TSV...")

            output_dir = self.processed_dir / source_name
            output_dir.mkdir(parents=True, exist_ok=True)

            try:
                for data_name, df in data.items():
                    tsv_file = output_dir / f"{data_name}.tsv"
                    # Guard: never overwrite a non-empty TSV with an empty DataFrame
                    if len(df) == 0 and tsv_file.exists():
                        existing_lines = sum(1 for _ in open(tsv_file)) - 1  # subtract header
                        if existing_lines > 0:
                            logger.warning(
                                f"  Skipping export of empty {data_name} "
                                f"(existing TSV has {existing_lines} rows)"
                            )
                            continue
                    df.to_csv(tsv_file, sep='\t', index=False)
                    logger.info(f"  Exported {data_name} ({len(df)} records)")
            except Exception as e:
                logger.error(f"  Failed to export {source_name}: {e}")

    def load_to_neo4j(self, parsed_data: Dict[str, Dict]):
        """
        Load parsed data into Neo4j.

        Args:
            parsed_data: Dictionary of parsed data from all sources.
        """
        uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
        username = os.getenv('NEO4J_USERNAME', 'neo4j')
        password = os.getenv('NEO4J_PASSWORD', '')

        if not password:
            logger.error("NEO4J_PASSWORD not set. Set it in .env or environment.")
            return

        try:
            with Neo4jLoader(uri, username, password) as loader:
                # Setup schema
                loader.setup_constraints(ONTOLOGY_CONFIGS)
                loader.setup_indexes(ONTOLOGY_CONFIGS)

                # Load data
                loader.load_from_configs(
                    parsed_data, ONTOLOGY_CONFIGS, self.processed_dir
                )

                # Post-load: validate relationship ID match rates and fix gaps
                self._validate_and_fix_mappings(parsed_data, loader)

                # Verify
                verification = loader.verify_graph()
                logger.info("Neo4j Graph Verification:")
                logger.info(f"  Node counts: {verification['node_counts']}")
                logger.info(f"  Relationship counts: {verification['relationship_counts']}")
                logger.info(f"  Total nodes: {verification['total_nodes']}")
                logger.info(f"  Total relationships: {verification['total_relationships']}")

                self.stats['total_nodes'] = verification['total_nodes']
                self.stats['total_edges'] = verification['total_relationships']

                # Loading stats
                load_stats = loader.get_stats()
                if load_stats['errors']:
                    logger.warning(f"  Loading errors: {len(load_stats['errors'])}")

                # Post-load: tag CVD-relevant Disease nodes
                self._tag_cvd_diseases(loader)

        except Exception as e:
            logger.error(f"Neo4j loading failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _validate_and_fix_mappings(self, parsed_data: Dict, loader):
        """
        Validate relationship ID match rates after initial Neo4j load.

        For each relationship ontology config, checks what percentage of
        subject/object IDs in the TSV actually matched existing nodes.
        If match rate < 70%, attempts to create missing nodes (for the
        object side) and re-loads those relationships.

        Saves results to reports/id_mapping_report.json for the web UI.
        """
        import json as _json
        from src.id_mapping import IDMapper

        logger.info("=" * 60)
        logger.info("ID Mapping Validation & Gap Repair")
        logger.info("=" * 60)

        mapper = IDMapper(driver=loader.driver)
        fixes_applied = []
        report_entries = []

        for config_key, config in ONTOLOGY_CONFIGS.items():
            if config.get('data_type') != 'relationship' or config.get('skip'):
                continue

            source_name = config_key.split('.', 1)[0]
            pc = config['parse_config']

            # Locate TSV file
            tsv_path = self.processed_dir / source_name / config['source_filename']
            if not tsv_path.exists():
                continue

            entry = {
                'config': config_key,
                'relationship_type': config.get('relationship_type', ''),
                'source_label': config.get('source_label', ''),
                'sides': [],
            }

            # Validate both subject and object sides
            for side, col, node_type, match_prop in [
                ('subject', pc['subject_column_name'], pc['subject_node_type'],
                 pc['subject_match_property']),
                ('object', pc['object_column_name'], pc['object_node_type'],
                 pc['object_match_property']),
            ]:
                report = mapper.validate_mapping(
                    str(tsv_path), col, node_type, match_prop,
                    sample_size=5,
                )
                if 'error' in report:
                    continue

                rate = report['match_rate']
                total = report['total_unique']
                matched = report['matched']
                unmatched = report['unmatched']

                # Log report for every config
                if rate >= 0.95:
                    level = 'OK'
                elif rate >= 0.70:
                    level = 'WARN'
                else:
                    level = 'LOW'

                logger.info(
                    f"  [{level}] {config_key} {side}: "
                    f"{matched}/{total} {node_type}.{match_prop} "
                    f"({rate*100:.1f}% match)"
                )

                side_entry = {
                    'side': side,
                    'node_type': node_type,
                    'property': match_prop,
                    'column': col,
                    'total': total,
                    'matched': matched,
                    'unmatched': unmatched,
                    'match_rate': round(rate * 100, 1),
                    'unmatched_edges': report['unmatched_edges_total'],
                    'sample_unmatched': dict(
                        list(report.get('sample_unmatched', {}).items())[:5]
                    ),
                    'nodes_created': 0,
                    'edges_recovered': 0,
                }

                # Only attempt fixes for low match rates on the object side
                if rate < 0.70 and side == 'object':
                    logger.info(
                        f"    -> Attempting suggest_mapping for {col} -> {node_type}"
                    )
                    suggestions = mapper.suggest_mapping(str(tsv_path), col, node_type)
                    best = suggestions[0] if suggestions else None

                    if best and best['match_rate'] > rate:
                        logger.info(
                            f"    -> Better mapping found: {best['property']} "
                            f"({best['match_rate']*100:.1f}% vs {rate*100:.1f}%)"
                        )

                    # Create missing nodes for unmatched IDs with enough edges
                    if unmatched > 0 and report['unmatched_edges_total'] > 0:
                        result = mapper.create_missing_nodes(
                            str(tsv_path), col, node_type, match_prop,
                            min_edges=10,
                        )
                        if 'error' not in result and result.get('created', 0) > 0:
                            logger.info(
                                f"    -> Created {result['created']} new {node_type} nodes "
                                f"(recovering {result['total_edges_recovered']} edges)"
                            )
                            side_entry['nodes_created'] = result['created']
                            side_entry['edges_recovered'] = result['total_edges_recovered']
                            fixes_applied.append({
                                'config_key': config_key,
                                'nodes_created': result['created'],
                                'edges_recovered': result['total_edges_recovered'],
                            })

                entry['sides'].append(side_entry)

            if entry['sides']:
                report_entries.append(entry)

        # Re-load relationship configs that got fixes
        if fixes_applied:
            logger.info(f"  Re-loading {len(fixes_applied)} relationship configs after gap repair...")
            fixed_keys = {f['config_key'] for f in fixes_applied}
            fixed_configs = {k: v for k, v in ONTOLOGY_CONFIGS.items() if k in fixed_keys}
            loader.load_from_configs(parsed_data, fixed_configs, self.processed_dir)

            total_nodes = sum(f['nodes_created'] for f in fixes_applied)
            total_edges = sum(f['edges_recovered'] for f in fixes_applied)
            logger.info(f"  Gap repair complete: {total_nodes} nodes created, ~{total_edges} edges recovered")
        else:
            logger.info("  No gap repairs needed.")

        # Save report to JSON for web UI
        report_dir = self.base_dir / 'reports'
        report_dir.mkdir(exist_ok=True)
        report_path = report_dir / 'id_mapping_report.json'
        report_data = {
            'generated_at': datetime.now().isoformat(),
            'entries': report_entries,
            'fixes_applied': fixes_applied,
        }
        with open(report_path, 'w') as f:
            _json.dump(report_data, f, indent=2)
        logger.info(f"  Saved ID mapping report to {report_path}")

        logger.info("=" * 60)

    def _tag_cvd_diseases(self, loader):
        """
        Set cvdRelevant=true on Disease nodes whose commonName
        case-insensitively matches any term from the CVD ontology file
        as a whole word (not a substring of another word).
        """
        import re

        ontology_path = self.base_dir / "ontology" / "disease_filter.txt"
        if not ontology_path.exists():
            logger.warning(f"CVD ontology file not found: {ontology_path}")
            return

        terms = []
        with open(ontology_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    terms.append(line)

        if not terms:
            logger.warning("No CVD terms loaded from ontology file")
            return

        # Build word-boundary regex patterns for Neo4j (Java regex).
        # Escape regex metacharacters, then wrap with (?i) and \b.
        patterns = []
        for term in terms:
            escaped = re.escape(term)
            patterns.append(f"(?i).*\\b{escaped}\\b.*")

        logger.info(
            f"Tagging CVD-relevant Disease nodes using "
            f"{len(patterns)} whole-word patterns..."
        )

        query = (
            "UNWIND $patterns AS pattern "
            "MATCH (d:Disease) "
            "WHERE d.commonName =~ pattern "
            "SET d.cvdRelevant = true "
            "RETURN count(DISTINCT d) AS tagged"
        )

        with loader.driver.session(database=loader.database) as session:
            result = session.run(query, patterns=patterns)
            tagged = result.single()['tagged']
            logger.info(f"  Tagged {tagged} Disease nodes with cvdRelevant=true")

    def generate_stats_and_notes(self):
        """Generate release notes for this build."""
        logger.info("Generating release notes...")

        self.stats['end_time'] = self.stats.get('end_time') or datetime.now()

        release_notes = f"""# CardioKB Release Notes

## Release Information
- **Version**: 1.0
- **Release Date**: {datetime.now().strftime('%Y-%m-%d')}
- **Build Duration**: {self.stats['end_time'] - self.stats['start_time'] if self.stats['end_time'] else 'N/A'}

## Data Sources

### Base KB (adapted from AlzKB)
- **NCBI Gene**: Human gene information
- **DrugBank**: Drug information (requires credentials)
- **AOP-DB**: Adverse Outcome Pathway Database (requires MySQL)
- **DisGeNET**: Gene-disease associations, CVD-scoped (requires API key)
- **DoRothEA**: Transcription factor regulatory network

### Custom Parsers
- **ClinicalTrials.gov**: CVD clinical trials (API v2)
- **ClinPGx**: Pharmacogenomics (gene-drug interactions)

### Phase 2 (Hetionet Components)
- SIDER, LINCS, MEDLINE, DrugCentral

## Statistics
- **Sources Processed**: {self.stats['sources_processed']}
- **Sources Failed**: {self.stats['sources_failed']}
- **Total Nodes**: {self.stats['total_nodes']:,}
- **Total Relationships**: {self.stats['total_edges']:,}

## Data Details
"""
        for key, count in sorted(self.stats['source_details'].items()):
            release_notes += f"- **{key}**: {count:,} records\n"

        release_notes += f"""
## Neo4j Schema

### Node Types
Gene, Disease, Drug, Pathway, TranscriptionFactor, ClinicalTrial, Variant,
DrugLabel, SideEffect, PharmacologicClass

### Key Relationship Types
- geneAssociatesWithDisease, geneInPathway
- STUDIES_CONDITION, TESTS_INTERVENTION (ClinicalTrials)
- AFFECTS_RESPONSE_TO, VARIANT_IN (ClinPGx)
- transcriptionFactorInteractsWithGene
- compoundCausesSideEffect, compoundUpregulatesGene, compoundDownregulatesGene

## Usage
```bash
# Parse + TSV export only
python src/main.py --skip-neo4j

# Full pipeline with Neo4j
python src/main.py

# Verify graph
python scripts/verify_graph.py
```
"""

        release_file = self.output_dir / "RELEASE_NOTES.md"
        with open(release_file, 'w') as f:
            f.write(release_notes)

        logger.info(f"Created release notes: {release_file}")
        print("\n" + release_notes)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='CardioKB Pipeline')
    parser.add_argument('--base-dir', default='.', help='Base directory for the project')
    parser.add_argument('--log-level',
                        default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Set logging verbosity level (default: INFO)')
    parser.add_argument('--skip-download', action='store_true',
                        help='Skip data download (use existing files)')
    parser.add_argument('--skip-neo4j', action='store_true',
                        help='Skip Neo4j loading (parse + TSV export only)')

    args = parser.parse_args()

    setup_logging(args.log_level)

    pipeline = CardioKBPipeline(args.base_dir)
    pipeline.run_full_pipeline(
        skip_download=args.skip_download,
        skip_neo4j=args.skip_neo4j,
    )


if __name__ == '__main__':
    main()
