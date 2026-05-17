"""
Uberon Anatomy Parser for CardioKB.

This module parses the Uberon anatomy ontology to extract anatomical structure
nodes (BodyPart) for CardioKB.

Data Source: http://purl.obolibrary.org/obo/uberon.obo

Output:
  - anatomy_nodes.tsv: UBERON ID, name, definition
"""

import logging
from pathlib import Path
from typing import Dict
import pandas as pd

try:
    import obonet
except ImportError:
    obonet = None

try:
    import pronto
except ImportError:
    pronto = None

from ..base_parser import BaseParser

logger = logging.getLogger(__name__)


class UberonParser(BaseParser):
    """
    Parser for the Uberon anatomy ontology.

    Extracts anatomical structure concepts for use as BodyPart nodes in CardioKB.
    """

    # Uberon OBO URL
    UBERON_URL = "http://purl.obolibrary.org/obo/uberon.obo"

    def __init__(self, data_dir: str):
        """
        Initialize the Uberon parser.

        Args:
            data_dir: Directory to store downloaded and processed data
        """
        super().__init__(data_dir)
        self.source_name = "uberon"

    def download_data(self) -> bool:
        """
        Download the Uberon OBO file.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Downloading Uberon ontology...")

        result = self.download_file(self.UBERON_URL, "uberon.obo")

        if result:
            logger.info(f"Successfully downloaded Uberon to {result}")
            return True
        else:
            logger.error("Failed to download Uberon")
            return False

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse the Uberon OBO file.

        Returns:
            Dictionary with:
              - 'anatomy_nodes': DataFrame of anatomical structure concepts
        """
        obo_path = self.source_dir / "uberon.obo"

        if not obo_path.exists():
            logger.error(f"Uberon file not found: {obo_path}")
            return {}

        logger.info(f"Parsing Uberon from {obo_path}")

        if obonet:
            return self._parse_with_obonet(obo_path)
        elif pronto:
            return self._parse_with_pronto(obo_path)
        else:
            logger.error("Neither obonet nor pronto is installed")
            return {}

    def _parse_with_obonet(self, obo_path: Path) -> Dict[str, pd.DataFrame]:
        """Parse using obonet library."""
        logger.info("Parsing Uberon with obonet...")

        try:
            graph = obonet.read_obo(str(obo_path))

            anatomy_terms = []

            for node_id, node_data in graph.nodes(data=True):
                if not node_id.startswith("UBERON:"):
                    continue

                if node_data.get("is_obsolete", False):
                    continue

                term = {
                    "uberon_id": node_id,
                    "name": node_data.get("name", ""),
                    "definition": self._clean_definition(node_data.get("def", "")),
                    "synonyms": "|".join(node_data.get("synonym", []))
                }
                anatomy_terms.append(term)

            logger.info(f"Parsed {len(anatomy_terms)} Uberon anatomy terms")

            return {
                "anatomy_nodes": pd.DataFrame(anatomy_terms)
            }

        except Exception as e:
            logger.error(f"Error parsing Uberon with obonet: {e}")
            return {}

    def _preprocess_obo(self, obo_path: Path) -> Path:
        """
        Return a sanitised copy of the OBO file with malformed xref lines removed.

        Some Uberon releases contain xref URIs with backslashes (e.g.
        ``xref: http://neurolex.org/wiki/Category\:Embryonic_organism``)
        which are illegal in OBO format and cause pronto to raise a SyntaxError.
        We strip those lines so the rest of the ontology can be parsed normally.

        Args:
            obo_path: Path to the original OBO file.

        Returns:
            Path to the sanitised OBO file (written alongside the original).
        """
        sanitised_path = obo_path.parent / (obo_path.stem + "_sanitised.obo")

        # Only rebuild if the source is newer than the cached sanitised copy
        if (
            sanitised_path.exists()
            and sanitised_path.stat().st_mtime >= obo_path.stat().st_mtime
        ):
            logger.info(f"Using cached sanitised OBO: {sanitised_path}")
            return sanitised_path

        logger.info("Sanitising Uberon OBO file (removing malformed xref lines)...")
        removed = 0
        with open(obo_path, "r", encoding="utf-8", errors="replace") as src, \
             open(sanitised_path, "w", encoding="utf-8") as dst:
            for line in src:
                # Drop xref lines that contain a backslash — these are
                # malformed URIs that pronto's fastobo backend cannot parse.
                if line.startswith("xref:") and "\\" in line:
                    removed += 1
                    continue
                dst.write(line)

        logger.info(f"Removed {removed} malformed xref lines; sanitised file: {sanitised_path}")
        return sanitised_path

    def _parse_with_pronto(self, obo_path: Path) -> Dict[str, pd.DataFrame]:
        """Parse using pronto library (with sanitised OBO fallback to manual parser)."""
        logger.info("Parsing Uberon with pronto...")

        # Sanitise the OBO file first to avoid SyntaxErrors on malformed xrefs
        sanitised_path = self._preprocess_obo(obo_path)

        try:
            ontology = pronto.Ontology(str(sanitised_path))

            anatomy_terms = []

            for term in ontology.terms():
                if not term.id.startswith("UBERON:"):
                    continue

                if term.obsolete:
                    continue

                term_data = {
                    "uberon_id": term.id,
                    "name": term.name or "",
                    "definition": str(term.definition) if term.definition else "",
                    "synonyms": "|".join(str(s) for s in term.synonyms)
                }
                anatomy_terms.append(term_data)

            logger.info(f"Parsed {len(anatomy_terms)} Uberon anatomy terms")

            return {
                "anatomy_nodes": pd.DataFrame(anatomy_terms)
            }

        except Exception as e:
            logger.warning(
                f"pronto failed ({e}); falling back to manual OBO parser"
            )
            return self._parse_obo_manual(sanitised_path)

    def _parse_obo_manual(self, obo_path: Path) -> Dict[str, pd.DataFrame]:
        """
        Lightweight line-by-line OBO parser.

        Handles Uberon files that reference external ontology terms (e.g.
        COB:0000013) which cause pronto's symmetrize_lineage step to raise
        a KeyError.  We only need id / name / def / synonym — no lineage
        traversal required.
        """
        logger.info(f"Manual OBO parse: {obo_path}")

        anatomy_terms = []
        in_term = False
        current: dict = {}

        def _flush(current: dict):
            uid = current.get("id", "")
            if uid.startswith("UBERON:") and not current.get("is_obsolete"):
                anatomy_terms.append({
                    "uberon_id": uid,
                    "name": current.get("name", ""),
                    "definition": self._clean_definition(current.get("def", "")),
                    "synonyms": "|".join(current.get("synonyms", [])),
                })

        try:
            with open(obo_path, "r", encoding="utf-8", errors="replace") as fh:
                for raw_line in fh:
                    line = raw_line.rstrip()
                    if line == "[Term]":
                        if in_term:
                            _flush(current)
                        current = {}
                        in_term = True
                    elif line.startswith("[") and line.endswith("]"):
                        # [Typedef] or other stanza — stop collecting
                        if in_term:
                            _flush(current)
                        current = {}
                        in_term = False
                    elif in_term:
                        if line.startswith("id: "):
                            current["id"] = line[4:].strip()
                        elif line.startswith("name: "):
                            current["name"] = line[6:].strip()
                        elif line.startswith("def: "):
                            current["def"] = line[5:].strip()
                        elif line.startswith("synonym: "):
                            current.setdefault("synonyms", []).append(line[9:].strip())
                        elif line.startswith("is_obsolete: true"):
                            current["is_obsolete"] = True

            # Flush the last term
            if in_term:
                _flush(current)

            logger.info(f"Manual OBO parser: {len(anatomy_terms)} Uberon anatomy terms")
            return {"anatomy_nodes": pd.DataFrame(anatomy_terms)}

        except Exception as e:
            logger.error(f"Manual OBO parser failed: {e}")
            return {}

    def _clean_definition(self, definition: str) -> str:
        """Clean up definition string from OBO format."""
        if not definition:
            return ""
        definition = definition.strip('"')
        if " [" in definition:
            definition = definition.split(" [")[0]
        return definition

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """
        Get the schema for Uberon data.

        Returns:
            Dictionary defining the schema for anatomy nodes
        """
        return {
            "anatomy_nodes": {
                "uberon_id": "Uberon ID (e.g., UBERON:0000955)",
                "name": "Anatomical structure name",
                "definition": "Structure definition",
                "synonyms": "Pipe-separated list of synonyms"
            }
        }
