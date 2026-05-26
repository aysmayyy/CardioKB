"""
Ontology Populator for CardioKB pipeline.

Populates an OWL ontology from TSV files using rdflib.
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL
import owlready2
import csv

logger = logging.getLogger(__name__)


class OntologyPopulator:
    """Populate OWL ontology from TSV files using rdflib."""

    def __init__(self, ontology_path: str, data_dir: str,
                 mysql_config: Optional[Dict[str, str]] = None,
                 ontology_mappings: Optional[Dict[str, Any]] = None):
        self.ontology_path = Path(ontology_path)
        self.data_dir = Path(data_dir)
        self.mysql_config = mysql_config
        
        if ontology_mappings is None:
            raise ValueError("ontology_mappings must be provided")
        self.ontology_mappings = ontology_mappings
        
        if not self.ontology_path.exists():
            raise FileNotFoundError(f"Ontology file not found: {self.ontology_path}")
        
        # Load the ontology with rdflib
        self.graph = Graph()
        self.graph.parse(str(self.ontology_path), format="xml")
        
        # Also load with owlready2 for reference
        self.ontology = owlready2.get_ontology(f"file://{self.ontology_path.absolute()}").load()
        logger.info(f"Loaded ontology: {self.ontology.base_iri}")
        logger.info(f"Initial triples: {len(self.graph)}")

    def populate_from_config(self, config_key: str):
        """Populate from a config entry."""
        if config_key not in self.ontology_mappings:
            logger.warning(f"Config key not found: {config_key}")
            return
        
        config = self.ontology_mappings[config_key]
        if config.get("skip", False):
            return
        
        source_name = config_key.split(".")[0]
        source_dir = self.data_dir / source_name
        
        if not source_dir.exists():
            logger.info(f"Source directory not found: {source_dir}")
            return
        
        # Get TSV filename
        tsv_filename = config.get("source_filename")
        if not tsv_filename:
            logger.warning(f"No source_filename for {config_key}")
            return
        
        tsv_path = source_dir / tsv_filename
        if not tsv_path.exists():
            logger.warning(f"TSV file not found: {tsv_path}")
            return
        
        logger.info(f"Populating from {tsv_path}")
        self._populate_from_tsv(tsv_path, config, source_name)

    def _populate_from_tsv(self, tsv_path: Path, config: Dict, source_name: str):
        """Read TSV and add individuals to RDF graph."""
        try:
            with open(tsv_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f, delimiter='\t')
                count = 0
                for row in reader:
                    self._add_row_as_individual(row, config, source_name)
                    count += 1
                    if count % 50000 == 0:
                        logger.info(f"  Processed {count} rows, graph size: {len(self.graph)}")
                logger.info(f"  Total: {count} rows")
        except Exception as e:
            logger.error(f"Error reading {tsv_path}: {e}")

    def _add_row_as_individual(self, row: Dict, config: Dict, source_name: str):
        """Add a single row as RDF individual."""
        try:
            # Use owl_class instead of node_type
            node_type = config.get("owl_class", "")
            if not node_type:
                return
            
            # Get ID column
            id_column = config.get("id_column", "id")
            if id_column not in row:
                return
            
            ind_id = str(row[id_column]).strip()
            if not ind_id:
                return
            
            # Create URI for individual
            uri = URIRef(f"{self.ontology.base_iri}{node_type}/{source_name}/{ind_id}")
            
            # Add type triple
            cls_uri = URIRef(f"{self.ontology.base_iri}{node_type}")
            self.graph.add((uri, RDF.type, cls_uri))
            
            # Add properties from row
            for col, value in row.items():
                if col == id_column or not value or str(value).strip() == "":
                    continue
                
                # Create property URI
                prop_uri = URIRef(f"{self.ontology.base_iri}{col}")
                
                # Add literal triple
                self.graph.add((uri, prop_uri, Literal(str(value).strip())))
        except Exception:
            pass

    def save_ontology(self, output_path: str):
        """Save the populated RDF graph."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save the rdflib graph directly (not owlready2)
        self.graph.serialize(destination=str(output_path), format="xml")
        logger.info(f"Successfully saved ontology to: {output_path}")

    def print_stats(self):
        """Print statistics."""
        logger.info(f"Ontology Statistics:")
        logger.info(f"  classes: {len(list(self.ontology.classes()))}")
        logger.info(f"  individuals: {len(list(self.ontology.individuals()))}")
        logger.info(f"  triples: {len(self.graph)}")
