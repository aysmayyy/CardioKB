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

from src.ontology_configs import ONTOLOGY_CONFIGS, CT_TRIAL_STUDIES_CONDITION, CT_TRIAL_TESTS_INTERVENTION
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

            # Step 4: Generate stats and release notes
            logger.info("=" * 80)
            logger.info("STEP 4: Release Notes Generation")
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

        for source_name, parser in parsers.items():
            logger.info(f"{'=' * 60}")
            logger.info(f"Processing {source_name.upper()}")
            logger.info(f"{'=' * 60}")

            try:
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

        # Post-processing: prepare OMIM CVD gene-disease edges
        if 'omim' in parsed_data:
            omim_data = parsed_data['omim']
            if 'gene_disease_relationships' in omim_data:
                gdr = omim_data['gene_disease_relationships'].copy()
                # Filter to CVD-related only
                gdr = gdr[gdr['is_cvd'] == True].copy()
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
                omim_data['cvd_gene_disease'] = gdr
                # Also store under node config key so both configs use
                # in-memory data with consistent string types
                omim_data['cvd_gene_disease_nodes'] = gdr
                logger.info(
                    f"Created {len(gdr)} OMIM CVD gene-disease edges "
                    f"({gdr['primary_gene_symbol'].nunique()} unique genes)"
                )

        # Post-processing: remap PubTator MESH IDs to DOID
        from src.id_mapping import remap_pubtator_mesh_to_doid, remap_gwas_disease_to_doid
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
            query_mode="cvd",
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

        except Exception as e:
            logger.error(f"Neo4j loading failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

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
