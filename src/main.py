"""
Disease KG Pipeline — Build a Disease Knowledge Graph

Runs the full pipeline in four steps:
  1. Extract   — download and parse data from biomedical databases
  2. Export TSV — save parsed DataFrames to data/processed/
  3. Populate  — populate the OWL ontology using ista
  4. Export graph — write Memgraph-compatible CSV files to data/output/

Usage:
    python src/main.py                            # full pipeline
    python src/main.py --source disgenet          # one source only
    python src/main.py --log-level DEBUG          # verbose logging
    python src/main.py --force-download           # re-download all source files
"""

import inspect
import logging
import os
import sys
import argparse
from pathlib import Path

import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from ontology_configs import ONTOLOGY_CONFIGS
from memgraph_loader import Neo4jLoader
from compute_specificity import compute_specificity

from parsers import (
    AOPDBParser,
    EvolutionaryRateCovariationParser,
    BgeeParser,
    BindingDBParser,
    CollectTRIParser,
    CTDParser,
    DiseaseOntologyParser,
    DisGeNETParser,
    DoRothEAParser,
    DrugBankParser,
    DrugCentralParser,
    GeneOntologyParser,
    MEDLINEParser,
    MeSHParser,
    NCBIGeneParser,
    ReactomeParser,
    UberonParser,
    StringParser,
    # Phase 2: New parsers
    ClinVarParser,
    HPOParser,
    HGNCFamiliesParser,
    PubTatorParser,
    JensenTissuesParser,
    SIDERParser,
    ClinicalTrialsParser,
    ClinPGxParser,
    LINCSParser,
    OpenTargetsParser,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parser lookup: source name in databases.yaml → parser class
# ---------------------------------------------------------------------------

PARSERS = {
    "aopdb": AOPDBParser,
    "bgee": BgeeParser,
    "bindingdb": BindingDBParser,
    "ctd": CTDParser,
    "disease_ontology": DiseaseOntologyParser,
    "disgenet": DisGeNETParser,
    "collectri": CollectTRIParser,
    "dorothea": DoRothEAParser,
    "drugbank": DrugBankParser,
    "drugcentral": DrugCentralParser,
    "gene_ontology": GeneOntologyParser,
    "medline": MEDLINEParser,
    "mesh": MeSHParser,
    "ncbigene": NCBIGeneParser,
    "uberon": UberonParser,
    "evolutionary_rate_covariation": EvolutionaryRateCovariationParser,
    "reactome": ReactomeParser,
    "string": StringParser,
    # Phase 2: New parsers
    "clinvar": ClinVarParser,
    "hpo": HPOParser,
    "hgnc": HGNCFamiliesParser,
    "pubtator": PubTatorParser,
    "jensen_tissues": JensenTissuesParser,
    "sider": SIDERParser,
    "clinicaltrials": ClinicalTrialsParser,
    "clinpgx": ClinPGxParser,
    "lincs": LINCSParser,
    "opentargets": OpenTargetsParser,
}

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CONFIG_DIR = Path(__file__).parent.parent / "config"


def _resolve_env_vars(config):
    """Recursively replace *_env keys with their environment variable values."""
    if not isinstance(config, dict):
        return config
    resolved = {}
    for key, value in config.items():
        if isinstance(value, dict):
            resolved[key] = _resolve_env_vars(value)
        elif isinstance(value, str) and key.endswith("_env"):
            new_key = key[:-4]
            env_value = os.environ.get(value)
            if env_value is None:
                logger.warning(f"Environment variable '{value}' is not set")
            resolved[new_key] = env_value
        else:
            resolved[key] = value
    return resolved


def load_config():
    """Load and return (project_config, databases, ontology_mappings)."""
    project = yaml.safe_load((CONFIG_DIR / "project.yaml").read_text())["project"]

    databases_raw = yaml.safe_load((CONFIG_DIR / "databases.yaml").read_text())["databases"]
    for source in databases_raw.values():
        if isinstance(source, dict) and "args" in source:
            source["args"] = _resolve_env_vars(source["args"])

    mappings_raw = yaml.safe_load((CONFIG_DIR / "ontology_mappings.yaml").read_text())
    mappings = mappings_raw.get("mappings", mappings_raw)
    mappings = {k: v for k, v in mappings.items() if v is not None}

    return project, databases_raw, mappings


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def extract(databases, project_config, raw_dir, force_download=False):
    """Download and parse data from all enabled source databases."""
    parsed_data = {}
    disease_scope = project_config.get("disease_scope", {})

    for source_name, db_config in databases.items():
        if not isinstance(db_config, dict) or not db_config.get("enabled", False):
            continue
        if source_name not in PARSERS:
            logger.warning(f"No parser found for '{source_name}'; skipping")
            continue

        logger.info(f"{'=' * 60}")
        logger.info(f"Processing {source_name.upper()}")
        logger.info(f"{'=' * 60}")

        parser_cls = PARSERS[source_name]
        args = dict(db_config.get("args", {}))
        args["data_dir"] = str(raw_dir)

        # Inject disease_scope only for parsers that declare it
        if "disease_scope" in inspect.signature(parser_cls.__init__).parameters:
            args["disease_scope"] = disease_scope

        try:
            parser = parser_cls(**args)
            parser.force = force_download
            if not parser.download_data():
                logger.warning(f"Download incomplete for {source_name}; trying existing files")
            data = parser.parse_data()
            if data:
                parsed_data[source_name] = data
                for key, df in data.items():
                    logger.info(f"  {key}: {len(df)} records")
            else:
                logger.warning(f"No data returned for {source_name}")
        except Exception:
            logger.exception(f"Failed to process {source_name}")

    return parsed_data


def export_tsv(parsed_data, processed_dir):
    """Save parsed DataFrames to TSV files in data/processed/<source>/."""
    for source_name, data in parsed_data.items():
        source_dir = processed_dir / source_name
        source_dir.mkdir(parents=True, exist_ok=True)
        for data_name, df in data.items():
            tsv_file = source_dir / f"{data_name}.tsv"
            df.to_csv(tsv_file, sep="\t", index=False)
            logger.info(f"  Saved {source_name}/{data_name}.tsv ({len(df)} rows)")


def populate(project_config, databases, ontology_mappings, processed_dir):
    """Populate the OWL ontology from processed TSV files using ista."""
    from ontology.populator import OntologyPopulator

    base_dir = Path(__file__).parent.parent
    ontology_path = base_dir / project_config["ontology"]["base_file"]
    output_rdf = base_dir / project_config["ontology"]["populated_output"]
    output_rdf.parent.mkdir(parents=True, exist_ok=True)

    populator = OntologyPopulator(
        ontology_path=str(ontology_path),
        data_dir=str(processed_dir),
        ontology_mappings=ontology_mappings,
    )

    for key, config in ontology_mappings.items():
        if config.get("skip", False):
            continue
        source_name = key.split(".")[0]
        db_config = databases.get(source_name)
        if not isinstance(db_config, dict) or not db_config.get("enabled", False):
            logger.info(f"{source_name} not enabled in databases.yaml, skipping {key}")
            continue
        if not (processed_dir / source_name).exists():
            logger.info(f"No data for {source_name}, skipping {key}")
            continue
        logger.info(f"Populating {key}...")
        try:
            populator.populate_from_config(key)
        except Exception:
            logger.exception(f"Error populating {key}")

    populator.save_ontology(str(output_rdf))
    populator.print_stats()
    logger.info(f"Saved populated ontology: {output_rdf}")
    return str(output_rdf)


def export_graph(project_config, output_dir, processed_dir):
    """Export processed TSVs to Memgraph-compatible CSV files."""
    from export.tsv_exporter import TSVMemgraphExporter

    base_dir = Path(__file__).parent.parent
    ontology_mappings_file = base_dir / "config" / "ontology_mappings.yaml"

    if not ontology_mappings_file.exists():
        logger.error(f"Ontology mappings not found: {ontology_mappings_file}")
        return

    exporter = TSVMemgraphExporter(
        str(processed_dir),
        str(ontology_mappings_file),
        str(output_dir)
    )
    result = exporter.export()
    logger.info(f"Exported {result['nodes_count']} nodes, {result['edges_count']} edges")


def load_to_memgraph(processed_dir):
    """Load data into Memgraph using Neo4jLoader with ontology configs."""
    uri = os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687")
    username = os.environ.get("MEMGRAPH_USERNAME", "")
    password = os.environ.get("MEMGRAPH_PASSWORD", "")

    logger.info(f"Connecting to Memgraph at {uri}")

    with Neo4jLoader(uri, username, password) as loader:
        # Create indexes on id for all node types first
        logger.info("Creating indexes on node types...")
        node_types = set()
        for config_key, config in ONTOLOGY_CONFIGS.items():
            if config.get('data_type') == 'node' and not config.get('skip'):
                node_types.add(config['node_type'])

        with loader.driver.session() as session:
            for node_type in sorted(node_types):
                try:
                    session.run(f"CREATE INDEX ON :{node_type}(id)")
                    logger.info(f"  Created index on :{node_type}(id)")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        logger.info(f"  Index on :{node_type}(id) already exists")
                    else:
                        logger.warning(f"  Failed to create index on :{node_type}(id): {e}")

        # Load data using configs
        logger.info("Loading data into Memgraph...")
        loader.load_from_configs(
            parsed_data={},  # Empty - will fall back to TSV files
            ontology_configs=ONTOLOGY_CONFIGS,
            processed_dir=processed_dir
        )

        # Print verification stats
        stats = loader.verify_graph()
        logger.info(f"Graph loaded: {stats['total_nodes']:,} nodes, {stats['total_relationships']:,} relationships")
        for label, count in sorted(stats['node_counts'].items()):
            logger.info(f"  {label}: {count:,}")

        return stats


# ---------------------------------------------------------------------------
# Logging + CLI
# ---------------------------------------------------------------------------

def setup_logging(log_level="INFO"):
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("kg_build.log"), logging.StreamHandler()],
        force=True,
    )
    logger.info(f"Log level: {log_level.upper()}")


def main():
    parser = argparse.ArgumentParser(
        description="Disease KG Pipeline — build a disease knowledge graph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/main.py                         run the full pipeline
  python src/main.py --source disgenet       run only DisGeNET extraction
  python src/main.py --step export           run only the graph export step
  python src/main.py --step populate         run only the ontology populate step
  python src/main.py --step extract          run only the extract + TSV export step
  python src/main.py --skip-download         use existing TSVs, load into Memgraph only
  python src/main.py --skip-neo4j            extract + export only, no Memgraph load
  python src/main.py --log-level DEBUG       verbose output
        """,
    )
    parser.add_argument(
        "--source",
        help="Run only this source (e.g., disgenet, aopdb). Skips populate and export.",
    )
    parser.add_argument(
        "--step",
        choices=["extract", "populate", "export", "load"],
        help="Run a single pipeline step: extract (download+TSV), populate (OWL), export (Memgraph CSV), or load (Memgraph).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity (default: INFO)",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download source files even if they already exist.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip downloading and parsing; use existing TSVs in data/processed/ and run only the load step.",
    )
    parser.add_argument(
        "--skip-neo4j",
        action="store_true",
        help="Skip Memgraph loading; run only extract and TSV export.",
    )
    args = parser.parse_args()

    setup_logging(args.log_level)
    load_dotenv()

    base_dir = Path(__file__).parent.parent
    raw_dir = base_dir / "data" / "raw"
    processed_dir = base_dir / "data" / "processed"
    output_dir = base_dir / "data" / "output"
    for d in [raw_dir, processed_dir, output_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # databases = all listed (enabled + disabled) sources from config
    project_config, databases, ontology_mappings = load_config()
    enabled_databases = {
        k: v for k, v in databases.items()
        if isinstance(v, dict) and v.get("enabled", False)
    }

    if args.source:
        source_config = databases.get(args.source, {})
        source_config["enabled"] = True
        selected_database = {args.source: source_config}
        parsed_data = extract(selected_database, project_config, raw_dir, force_download=args.force_download)
        export_tsv(parsed_data, processed_dir)
        logger.info(f"Single-source run for '{args.source}' complete.")
        return

    if args.step == "extract":
        logger.info("Running extract step only")
        parsed_data = extract(enabled_databases, project_config, raw_dir, force_download=args.force_download)
        export_tsv(parsed_data, processed_dir)
        logger.info("Extract step complete.")
        return

    if args.step == "populate":
        logger.info("Running populate step only")
        populate(project_config, enabled_databases, ontology_mappings, processed_dir)
        logger.info("Populate step complete.")
        return

    if args.step == "export":
        logger.info("Running export step only")
        export_graph(project_config, output_dir, processed_dir)
        logger.info("Export step complete.")
        return

    if args.step == "load":
        logger.info("Running load step only (loading into Memgraph)")
        load_to_memgraph(processed_dir)
        logger.info("Computing specificity scores...")
        compute_specificity()
        logger.info("Load step complete.")
        return

    # --skip-download: use existing TSVs, skip to load
    if args.skip_download:
        logger.info("Skipping download/parse; using existing TSVs in data/processed/")
        if not args.skip_neo4j:
            load_to_memgraph(processed_dir)
            logger.info("Computing specificity scores...")
            compute_specificity()
        logger.info("Pipeline complete (skip-download mode).")
        return

    logger.info(f"Starting {project_config.get('display_name', 'KG')} pipeline")
    parsed_data = extract(enabled_databases, project_config, raw_dir, force_download=args.force_download)
    export_tsv(parsed_data, processed_dir)
    populate(project_config, enabled_databases, ontology_mappings, processed_dir)
    export_graph(project_config, output_dir, processed_dir)
    if not args.skip_neo4j:
        load_to_memgraph(processed_dir)
        logger.info("Computing specificity scores...")
        compute_specificity()
    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
