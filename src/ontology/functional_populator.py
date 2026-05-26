"""
Functional ontology populator using rdflib.

This module populates an OWL ontology from TSV files using rdflib,
bypassing the ista dependency.
"""

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL
import owlready2

logger = logging.getLogger(__name__)


class FunctionalOntologyPopulator:
    """Populate OWL ontology from TSV files using rdflib."""

    def __init__(self, ontology_path: str, data_dir: str, ontology_mappings: Optional[Dict[str, Any]] = None):
        self.ontology_path = Path(ontology_path)
        self.data_dir = Path(data_dir)
        self.ontology_mappings = ontology_mappings or {}
        
        # Load the ontology with rdflib
        self.graph = Graph()
        self.graph.parse(str(self.ontology_path), format="xml")
        
        # Load with owlready2 for class/property access
        self.ontology = owlready2.get_ontology(f"file://{self.ontology_path.absolute()}").load()
        
        logger.info(f"Loaded ontology: {self.ontology.base_iri}")
        logger.info(f"Triples in graph: {len(self.graph)}")

    def populate_from_config(self, config_key: str):
        """Populate from a config entry (e.g., 'ncbigene.genes')."""
        if config_key not in self.ontology_mappings:
            logger.warning(f"Config key not found: {config_key}")
            return
        
        config = self.ontology_mappings[config_key]
        if config.get("skip", False):
            return
        
        source_name, data_key = config_key.split(".", 1)
        source_dir = self.data_dir / source_name
        
        if not source_dir.exists():
            logger.warning(f"Source directory not found: {source_dir}")
            return
        
        # Get the TSV filename from config or use data_key
        tsv_filename = config.get("source_filename", f"{data_key}.tsv")
        tsv_path = source_dir / tsv_filename
        
        if not tsv_path.exists():
            logger.warning(f"TSV file not found: {tsv_path}")
            return
        
        logger.info(f"Populating from {tsv_path}")
        
        # Read TSV and add to graph
        try:
            with open(tsv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='\t')
                count = 0
                for row in reader:
                    # Create RDF triples based on config
                    self._add_row_to_graph(row, config, source_name)
                    count += 1
                    if count % 10000 == 0:
                        logger.info(f"  Processed {count} rows")
                logger.info(f"  Total: {count} rows processed")
        except Exception as e:
            logger.error(f"Error reading {tsv_path}: {e}")

    def _add_row_to_graph(self, row: Dict, config: Dict, source_name: str):
        """Add a single row from TSV as RDF triples."""
        # This is a placeholder - actual implementation would depend on config structure
        pass

    def save_ontology(self, output_path: str):
        """Save the populated ontology."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save with owlready2
        self.ontology.save(file=str(output_path), format="rdfxml")
        logger.info(f"Saved ontology to: {output_path}")

    def print_stats(self):
        """Print ontology statistics."""
        logger.info(f"Ontology Statistics:")
        logger.info(f"  Classes: {len(list(self.ontology.classes()))}")
        logger.info(f"  Individuals: {len(list(self.ontology.individuals()))}")
        logger.info(f"  Triples: {len(self.graph)}")
