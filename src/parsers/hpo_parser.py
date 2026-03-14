"""
HPOParser: Parser for the Human Phenotype Ontology (HPO).

Extracts phenotype nodes from the HPO OBO file and gene-phenotype
associations from the HPO annotations file (genes_to_phenotype.txt).
Produces Phenotype nodes (HP: IDs) and geneAssociatesWithPhenotype edges
linking Gene nodes (by Entrez ID) to Phenotype nodes (by HP: ID).

Sources:
  - OBO file: https://purl.obolibrary.org/obo/hp.obo
  - Annotations: https://purl.obolibrary.org/obo/hp/hpoa/genes_to_phenotype.txt
Access: Public (no credentials required)
License: HPO License (free for academic use)
"""

import logging
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

try:
    import obonet
except ImportError:
    obonet = None

try:
    import pronto
except ImportError:
    pronto = None

from .base_parser import BaseParser

logger = logging.getLogger(__name__)


class HPOParser(BaseParser):
    """Parser for the Human Phenotype Ontology (HPO)."""

    HPO_URL = "https://purl.obolibrary.org/obo/hp.obo"
    ANNOTATIONS_URL = "https://purl.obolibrary.org/obo/hp/hpoa/genes_to_phenotype.txt"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download the HPO OBO file and gene-phenotype annotations."""
        logger.info("Downloading Human Phenotype Ontology...")

        ok = True
        result = self.download_file(self.HPO_URL, "hp.obo")
        if not result:
            logger.error("Failed to download HPO OBO file")
            ok = False

        result = self.download_file(self.ANNOTATIONS_URL, "genes_to_phenotype.txt")
        if not result:
            logger.error("Failed to download HPO annotations")
            ok = False

        return ok

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse HPO OBO file and gene-phenotype annotations."""
        result = {}

        # --- Phenotype nodes from OBO ---
        obo_path = self.source_dir / "hp.obo"
        if obo_path.exists():
            if obonet:
                result.update(self._parse_obo_with_obonet(obo_path))
            elif pronto:
                result.update(self._parse_obo_with_pronto(obo_path))
            else:
                logger.error("Neither obonet nor pronto is installed. Cannot parse OBO file.")
        else:
            logger.warning(f"HPO OBO file not found: {obo_path}")

        # --- Gene-phenotype edges from annotations ---
        annot_path = self.source_dir / "genes_to_phenotype.txt"
        if annot_path.exists():
            result.update(self._parse_annotations(annot_path))
        else:
            logger.warning(f"HPO annotations file not found: {annot_path}")

        return result

    def _parse_obo_with_obonet(self, obo_path: Path) -> Dict[str, pd.DataFrame]:
        """Parse OBO file using obonet library."""
        logger.info("Parsing HPO OBO with obonet...")

        try:
            graph = obonet.read_obo(str(obo_path))
            phenotypes = []

            for node_id, node_data in graph.nodes(data=True):
                if not node_id.startswith("HP:"):
                    continue
                if node_data.get("is_obsolete", False):
                    continue

                phenotypes.append({
                    "hpo_id": node_id,
                    "name": node_data.get("name", ""),
                    "definition": self._clean_definition(node_data.get("def", "")),
                    "synonyms": "|".join(node_data.get("synonym", [])),
                })

            logger.info(f"Parsed {len(phenotypes)} HPO phenotype terms")
            return {"phenotype_nodes": pd.DataFrame(phenotypes)}

        except Exception as e:
            logger.error(f"Error parsing HPO with obonet: {e}")
            return {}

    def _parse_obo_with_pronto(self, obo_path: Path) -> Dict[str, pd.DataFrame]:
        """Parse OBO file using pronto library."""
        logger.info("Parsing HPO OBO with pronto...")

        try:
            ontology = pronto.Ontology(str(obo_path))
            phenotypes = []

            for term in ontology.terms():
                if not term.id.startswith("HP:"):
                    continue
                if term.obsolete:
                    continue

                phenotypes.append({
                    "hpo_id": term.id,
                    "name": term.name or "",
                    "definition": str(term.definition) if term.definition else "",
                    "synonyms": "|".join(str(s) for s in term.synonyms),
                })

            logger.info(f"Parsed {len(phenotypes)} HPO phenotype terms")
            return {"phenotype_nodes": pd.DataFrame(phenotypes)}

        except Exception as e:
            logger.error(f"Error parsing HPO with pronto: {e}")
            return {}

    def _parse_annotations(self, annot_path: Path) -> Dict[str, pd.DataFrame]:
        """Parse genes_to_phenotype.txt into gene-phenotype edges."""
        logger.info(f"Parsing HPO gene-phenotype annotations from {annot_path}")

        df = self.read_tsv(str(annot_path))
        if df is None or df.empty:
            return {}

        # Rename columns to match our schema
        df = df.rename(columns={
            'ncbi_gene_id': 'gene_id',
            'hpo_id': 'hpo_id',
            'hpo_name': 'hpo_name',
            'frequency': 'frequency',
            'disease_id': 'disease_id',
        })

        # Ensure gene_id is string for Neo4j matching
        df['gene_id'] = df['gene_id'].astype(str)

        # Deduplicate to unique (gene_id, hpo_id) pairs
        deduped = df.drop_duplicates(subset=['gene_id', 'hpo_id'])

        deduped = deduped[['gene_id', 'hpo_id']].copy()
        deduped['source_database'] = 'HPO'

        logger.info(
            f"HPO annotations: {len(deduped)} unique gene-phenotype associations "
            f"({deduped['gene_id'].nunique()} genes, "
            f"{deduped['hpo_id'].nunique()} phenotypes)"
        )

        return {"gene_phenotype_associations": deduped}

    def _clean_definition(self, definition: str) -> str:
        """Clean up definition string from OBO format."""
        if not definition:
            return ""
        definition = definition.strip('"')
        if " [" in definition:
            definition = definition.split(" [")[0]
        return definition

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """Return schema description for each output DataFrame."""
        return {
            "phenotype_nodes": {
                "hpo_id": "HPO ID (e.g., HP:0001627)",
                "name": "Phenotype name",
                "definition": "Phenotype definition",
                "synonyms": "Pipe-separated list of synonyms",
            },
            "gene_phenotype_associations": {
                "gene_id": "Entrez gene ID (e.g., 7157)",
                "hpo_id": "HPO ID (e.g., HP:0001627)",
                "source_database": "Source database identifier",
            },
        }
