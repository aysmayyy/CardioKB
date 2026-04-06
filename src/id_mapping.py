"""
ID Mapping utilities for CardioKB.

Two roles:
1. Post-processing remaps (PubTator MESH->DOID, GWAS trait->DOID) used during
   pipeline parsing — called from main.py before Neo4j load.
2. Central ID mapping module: builds in-memory cross-reference lookups from
   Neo4j node properties, exposes map_id(), validate_mapping(),
   suggest_mapping(), and create_missing_nodes(). Runnable as a CLI.
"""

import argparse
import logging
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ID system registry: (node_label, property_name) for each known system
# ---------------------------------------------------------------------------
ID_SYSTEMS: Dict[str, Tuple[str, str]] = {
    # Genes
    'ncbi_gene':     ('Gene', 'xrefNcbiGene'),
    'ensembl':       ('Gene', 'xrefEnsembl'),
    'gene_symbol':   ('Gene', 'geneSymbol'),
    'omim_gene':     ('Gene', 'xrefOMIM'),
    # Diseases
    'doid':          ('Disease', 'xrefDiseaseOntology'),
    'umls':          ('Disease', 'xrefUmlsCUI'),
    'omim_disease':  ('Disease', 'xrefOMIM'),
    # Drugs
    'mesh':          ('Drug', 'xrefMeSH'),
    'drugbank':      ('Drug', 'xrefDrugbank'),
    'cas':           ('Drug', 'xrefCasRN'),
    'dtxsid':        ('Drug', 'xrefDTXSID'),
    # Anatomy / BodyPart
    'uberon':        ('BodyPart', 'xrefUberon'),
    'bodypart_name': ('BodyPart', 'commonName'),
    # Phenotype
    'hpo':           ('Phenotype', 'xrefHPO'),
    # GO terms
    'go_bp':         ('BiologicalProcess', 'geneOntologyId'),
    'go_mf':         ('MolecularFunction', 'geneOntologyId'),
    'go_cc':         ('CellularComponent', 'geneOntologyId'),
}


class IDMapper:
    """Builds cross-reference lookups from Neo4j and provides mapping utilities."""

    def __init__(self, driver=None):
        """
        Args:
            driver: neo4j.Driver instance. If None, creates one from env vars.
        """
        self._owns_driver = driver is None
        if driver is None:
            from dotenv import load_dotenv
            from neo4j import GraphDatabase
            load_dotenv()
            uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
            user = os.getenv('NEO4J_USERNAME', 'neo4j')
            pw = os.getenv('NEO4J_PASSWORD', '')
            driver = GraphDatabase.driver(uri, auth=(user, pw))
        self.driver = driver
        # Lookup tables: id_system -> {value -> internal_id}
        # Internal ID = (node_label, primary_prop_value)
        self._lookups: Dict[str, Dict[str, str]] = {}
        # Reverse: internal_id -> {id_system -> value}
        self._reverse: Dict[str, Dict[str, str]] = defaultdict(dict)
        self._loaded_labels: set = set()

    def close(self):
        if self._owns_driver:
            self.driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------
    # Loading lookups from Neo4j
    # ------------------------------------------------------------------

    def _load_label(self, label: str):
        """Load all xref properties for a given node label into memory."""
        if label in self._loaded_labels:
            return
        self._loaded_labels.add(label)

        # Gather all ID systems for this label
        systems = [(sys_name, prop) for sys_name, (lbl, prop) in ID_SYSTEMS.items()
                    if lbl == label]
        if not systems:
            return

        props_needed = list(set(prop for _, prop in systems))
        return_clause = ', '.join(f'n.{p} AS {p}' for p in props_needed)
        query = f'MATCH (n:{label}) RETURN {return_clause}'

        with self.driver.session() as session:
            result = session.run(query)
            for record in result:
                vals = {p: record[p] for p in props_needed}
                # Use first non-null xref as internal key
                internal_key = None
                for p in props_needed:
                    if vals[p] is not None:
                        internal_key = f'{label}::{vals[p]}'
                        break
                if internal_key is None:
                    continue

                for sys_name, prop in systems:
                    v = vals.get(prop)
                    if v is not None:
                        v_str = str(v)
                        if sys_name not in self._lookups:
                            self._lookups[sys_name] = {}
                        self._lookups[sys_name][v_str] = internal_key
                        self._reverse[internal_key][sys_name] = v_str

        for sys_name, prop in systems:
            count = len(self._lookups.get(sys_name, {}))
            if count > 0:
                logger.info(f"Loaded {count} {sys_name} ({label}.{prop}) entries")

    def _ensure_systems_loaded(self, *system_names: str):
        for s in system_names:
            if s in ID_SYSTEMS:
                self._load_label(ID_SYSTEMS[s][0])

    # ------------------------------------------------------------------
    # map_id
    # ------------------------------------------------------------------

    def map_id(self, source_id: str, from_system: str, to_system: str) -> Optional[str]:
        """
        Map an ID from one system to another.

        Args:
            source_id: The ID to map (e.g., "7157").
            from_system: Source system name (e.g., "ncbi_gene").
            to_system: Target system name (e.g., "ensembl").

        Returns:
            Mapped ID string, or None if not found.
        """
        self._ensure_systems_loaded(from_system, to_system)
        lookup = self._lookups.get(from_system, {})
        internal = lookup.get(str(source_id))
        if internal is None:
            return None
        return self._reverse.get(internal, {}).get(to_system)

    # ------------------------------------------------------------------
    # validate_mapping
    # ------------------------------------------------------------------

    def validate_mapping(self, tsv_path: str, id_column: str,
                         node_label: str, node_property: str,
                         sample_size: int = 500) -> Dict:
        """
        Check what percentage of IDs in a TSV match existing Neo4j nodes.

        Args:
            tsv_path: Path to TSV file.
            id_column: Column name containing IDs to validate.
            node_label: Neo4j node label to match against.
            node_property: Neo4j node property to match against.
            sample_size: Number of unique IDs to sample for spot-check.

        Returns:
            Dict with match_rate, total_unique, matched, unmatched,
            sample_matched, sample_unmatched.
        """
        df = pd.read_csv(tsv_path, sep='\t', dtype=str)
        if id_column not in df.columns:
            return {'error': f"Column '{id_column}' not found. Available: {list(df.columns)}"}

        unique_ids = df[id_column].dropna().unique()
        total = len(unique_ids)

        # Query Neo4j for existing values
        with self.driver.session() as session:
            result = session.run(
                f'MATCH (n:{node_label}) WHERE n.{node_property} IS NOT NULL '
                f'RETURN n.{node_property} AS val'
            )
            existing = set(str(r['val']) for r in result)

        matched_ids = [uid for uid in unique_ids if uid in existing]
        unmatched_ids = [uid for uid in unique_ids if uid not in existing]

        match_rate = len(matched_ids) / total if total > 0 else 0

        # Count edges per unmatched ID
        unmatched_edge_counts = (
            df[df[id_column].isin(unmatched_ids)]
            .groupby(id_column).size()
            .sort_values(ascending=False)
        )

        # Sample mismatches (top by edge count)
        sample_unmatched = unmatched_edge_counts.head(sample_size)

        return {
            'tsv_path': tsv_path,
            'id_column': id_column,
            'node_label': node_label,
            'node_property': node_property,
            'total_unique': total,
            'matched': len(matched_ids),
            'unmatched': len(unmatched_ids),
            'match_rate': match_rate,
            'unmatched_edges_total': int(unmatched_edge_counts.sum()),
            'sample_unmatched': sample_unmatched.to_dict(),
        }

    # ------------------------------------------------------------------
    # suggest_mapping
    # ------------------------------------------------------------------

    def suggest_mapping(self, tsv_path: str, id_column: str,
                        node_label: str) -> List[Dict]:
        """
        Try all known ID systems for a node label and rank by match rate.

        Returns:
            List of dicts sorted by match_rate descending.
        """
        candidates = [(sys_name, prop) for sys_name, (lbl, prop) in ID_SYSTEMS.items()
                       if lbl == node_label]

        results = []
        for sys_name, prop in candidates:
            report = self.validate_mapping(tsv_path, id_column, node_label, prop)
            if 'error' in report:
                continue
            results.append({
                'id_system': sys_name,
                'property': prop,
                'match_rate': report['match_rate'],
                'matched': report['matched'],
                'total': report['total_unique'],
            })

        results.sort(key=lambda x: x['match_rate'], reverse=True)
        return results

    # ------------------------------------------------------------------
    # create_missing_nodes
    # ------------------------------------------------------------------

    def create_missing_nodes(self, tsv_path: str, id_column: str,
                             node_label: str, id_property: str,
                             name_column: Optional[str] = None,
                             min_edges: int = 10,
                             dry_run: bool = False) -> Dict:
        """
        Create new nodes for unmatched IDs that appear in enough edges.

        When validate_mapping() finds unmatched IDs representing real biological
        entities, this function creates new nodes with the source ID as a
        cross-reference property.

        Args:
            tsv_path: Path to TSV file.
            id_column: Column with IDs to check.
            node_label: Neo4j node label to create (e.g., "BodyPart").
            id_property: Neo4j property to store the ID as (e.g., "xrefUberon").
            name_column: Optional column for commonName. If None, uses id_column.
            min_edges: Only create nodes for IDs appearing in >= this many edges.
            dry_run: If True, report what would be created without writing.

        Returns:
            Dict with created count, skipped count, and details.
        """
        df = pd.read_csv(tsv_path, sep='\t', dtype=str)
        if id_column not in df.columns:
            return {'error': f"Column '{id_column}' not found."}

        # Find existing node values
        with self.driver.session() as session:
            result = session.run(
                f'MATCH (n:{node_label}) WHERE n.{id_property} IS NOT NULL '
                f'RETURN n.{id_property} AS val'
            )
            existing = set(str(r['val']) for r in result)

        # Count edges per ID
        edge_counts = df.groupby(id_column).size()
        unique_ids = set(df[id_column].dropna().unique())
        unmatched = unique_ids - existing

        # Filter by min_edges threshold
        candidates = {uid: int(edge_counts.get(uid, 0)) for uid in unmatched
                      if edge_counts.get(uid, 0) >= min_edges}
        skipped = {uid: int(edge_counts.get(uid, 0)) for uid in unmatched
                   if edge_counts.get(uid, 0) < min_edges}

        if dry_run:
            return {
                'dry_run': True,
                'would_create': len(candidates),
                'would_skip': len(skipped),
                'total_unmatched': len(unmatched),
                'total_edges_recovered': sum(candidates.values()),
                'total_edges_skipped': sum(skipped.values()),
                'top_candidates': dict(
                    sorted(candidates.items(), key=lambda x: -x[1])[:20]
                ),
            }

        # Build rows to create
        name_col = name_column or id_column
        rows_to_create = []
        for uid in candidates:
            name_val = uid
            if name_col != id_column and name_col in df.columns:
                # Get name from first row with this ID
                match_rows = df[df[id_column] == uid]
                if not match_rows.empty:
                    name_val = match_rows.iloc[0].get(name_col, uid)
            rows_to_create.append({'id_val': uid, 'name_val': name_val})

        if not rows_to_create:
            return {'created': 0, 'skipped': len(skipped), 'message': 'No candidates above threshold.'}

        # MERGE nodes into Neo4j
        query = (
            f"UNWIND $rows AS row "
            f"MERGE (n:{node_label} {{{id_property}: row.id_val}}) "
            f"ON CREATE SET n.commonName = row.name_val, "
            f"n.sourceDatabase = 'IDMapper'"
        )
        with self.driver.session() as session:
            result = session.run(query, rows=rows_to_create)
            summary = result.consume()
            created = summary.counters.nodes_created

        logger.info(
            f"create_missing_nodes: {created} new {node_label} nodes created, "
            f"{len(skipped)} skipped (< {min_edges} edges)"
        )

        return {
            'created': created,
            'merged_existing': len(rows_to_create) - created,
            'skipped': len(skipped),
            'total_edges_recovered': sum(candidates.values()),
            'total_edges_skipped': sum(skipped.values()),
        }


# =========================================================================
# Post-processing remap functions (used by main.py during pipeline)
# =========================================================================

def remap_pubtator_mesh_to_doid(parsed_data: Dict[str, Dict[str, pd.DataFrame]]) -> None:
    """
    Remap PubTator MESH disease IDs to DOID using Disease Ontology cross-references.

    Modifies parsed_data['pubtator'] DataFrames in place:
    - disease_disease_cooccurrence: remaps disease1_id, disease2_id
    - gene_disease_literature: remaps disease_id

    Drops rows without a valid MESH->DOID mapping and removes self-loops.
    """
    do_data = parsed_data.get('disease_ontology', {})
    pt_data = parsed_data.get('pubtator', {})

    xrefs_df = do_data.get('disease_xrefs')
    if xrefs_df is None or xrefs_df.empty:
        logger.warning("No disease_xrefs available for MESH->DOID mapping; skipping PubTator remap")
        return

    # Build MESH:Dxxxx -> DOID:xxxx lookup
    mesh_rows = xrefs_df[xrefs_df['xref'].str.startswith('MESH:', na=False)].copy()
    mesh_to_doid = dict(zip(mesh_rows['xref'], mesh_rows['doid']))
    logger.info(f"Built MESH->DOID lookup with {len(mesh_to_doid)} entries")

    def _remap_disease_col(col: pd.Series, lookup: dict) -> pd.Series:
        """Remap MESH IDs to DOID; preserve values already in DOID format."""
        is_mesh = col.str.startswith('MESH:', na=False)
        result = col.copy()
        result[is_mesh] = col[is_mesh].map(lookup)
        return result

    # Remap disease-disease co-occurrence
    dd_key = 'disease_disease_cooccurrence'
    if dd_key in pt_data:
        df = pt_data[dd_key]
        before = len(df)
        df['disease1_id'] = _remap_disease_col(df['disease1_id'], mesh_to_doid)
        df['disease2_id'] = _remap_disease_col(df['disease2_id'], mesh_to_doid)
        df = df.dropna(subset=['disease1_id', 'disease2_id'])
        # Remove self-loops created by MESH->DOID many-to-one collapse
        df = df[df['disease1_id'] != df['disease2_id']]
        pt_data[dd_key] = df
        logger.info(f"PubTator {dd_key}: {before} -> {len(df)} rows after MESH->DOID remap")

    # Remap gene-disease literature
    gd_key = 'gene_disease_literature'
    if gd_key in pt_data:
        df = pt_data[gd_key]
        before = len(df)
        df['disease_id'] = _remap_disease_col(df['disease_id'], mesh_to_doid)
        df = df.dropna(subset=['disease_id'])

        # Explode semicolon-delimited gene_ids (PubTator multi-gene annotations)
        df['gene_id'] = df['gene_id'].astype(str)
        has_semi = df['gene_id'].str.contains(';', na=False)
        if has_semi.any():
            df = df.assign(gene_id=df['gene_id'].str.split(';')).explode('gene_id')
            df['gene_id'] = df['gene_id'].str.strip()
            logger.info(f"PubTator {gd_key}: exploded semicolons -> {len(df)} rows")

        # Coerce gene_id to int (required for Neo4j xrefNcbiGene matching)
        df['gene_id'] = pd.to_numeric(df['gene_id'], errors='coerce')
        df = df.dropna(subset=['gene_id'])
        df['gene_id'] = df['gene_id'].astype(int)

        pt_data[gd_key] = df
        logger.info(f"PubTator {gd_key}: {before} -> {len(df)} rows after MESH->DOID remap")


def remap_drugcentral_cui_to_doid(parsed_data: Dict[str, Dict[str, pd.DataFrame]]) -> None:
    """
    Remap DrugCentral UMLS CUI disease IDs to DOID using Disease Ontology cross-references.

    Modifies parsed_data['drugcentral'] DataFrames in place:
    - drug_treats_disease: adds 'doid' column mapped from 'umls_cui'
    - drug_palliates_disease: adds 'doid' column mapped from 'umls_cui'

    Drops rows without a valid CUI->DOID mapping.
    """
    do_data = parsed_data.get('disease_ontology', {})
    dc_data = parsed_data.get('drugcentral', {})

    xrefs_df = do_data.get('disease_xrefs')
    if xrefs_df is None or xrefs_df.empty:
        logger.warning("No disease_xrefs available for CUI->DOID mapping; skipping DrugCentral remap")
        return

    # Build UMLS_CUI:Cxxxx -> DOID:xxxx lookup
    cui_rows = xrefs_df[xrefs_df['xref'].str.startswith('UMLS_CUI:', na=False)].copy()
    # Strip prefix: "UMLS_CUI:C0020538" -> "C0020538"
    cui_to_doid = dict(zip(
        cui_rows['xref'].str.replace('UMLS_CUI:', '', regex=False),
        cui_rows['doid']
    ))
    logger.info(f"Built CUI->DOID lookup with {len(cui_to_doid)} entries")

    for key in ('drug_treats_disease', 'drug_palliates_disease'):
        if key not in dc_data:
            continue
        df = dc_data[key]
        before = len(df)
        df['doid'] = df['umls_cui'].map(cui_to_doid)
        df = df.dropna(subset=['doid'])
        dc_data[key] = df
        logger.info(f"DrugCentral {key}: {before} -> {len(df)} rows after CUI->DOID remap")


def remap_gwas_disease_to_doid(parsed_data: Dict[str, Dict[str, pd.DataFrame]]) -> None:
    """
    Remap GWAS disease traits to DOID using three strategies:
    1. Case-insensitive name matching on disease_trait (free text)
    2. Case-insensitive name matching on mapped_trait (curated ontology name)
    3. Ontology URI cross-reference matching on mapped_trait_uri (EFO, MONDO, etc.)

    Adds a 'disease_doid' column to parsed_data['gwas']['gene_disease_gwas']
    and drops rows without a mapping.
    """
    do_data = parsed_data.get('disease_ontology', {})
    gwas_data = parsed_data.get('gwas', {})

    nodes_df = do_data.get('disease_nodes')
    xrefs_df = do_data.get('disease_xrefs')
    if nodes_df is None or nodes_df.empty:
        logger.warning("No disease_nodes available for GWAS disease mapping; skipping")
        return

    gd_key = 'gene_disease_gwas'
    if gd_key not in gwas_data:
        logger.warning(f"No {gd_key} in GWAS data; skipping disease remap")
        return

    # Build case-insensitive name -> DOID lookup (primary names + synonyms)
    name_to_doid = {}
    for _, row in nodes_df.iterrows():
        doid = row['doid']
        # Primary name
        name = str(row.get('name', '')).strip().lower()
        if name:
            name_to_doid[name] = doid

        # Synonyms are pipe-delimited, format: "text" EXACT []
        synonyms_raw = str(row.get('synonyms', ''))
        if synonyms_raw and synonyms_raw != 'nan':
            for syn_entry in synonyms_raw.split('|'):
                syn_entry = syn_entry.strip()
                # Extract text between quotes if present
                if '"' in syn_entry:
                    parts = syn_entry.split('"')
                    if len(parts) >= 2:
                        syn_text = parts[1].strip().lower()
                        if syn_text:
                            name_to_doid[syn_text] = doid
                else:
                    syn_text = syn_entry.strip().lower()
                    if syn_text:
                        name_to_doid[syn_text] = doid

    logger.info(f"Built disease name->DOID lookup with {len(name_to_doid)} entries (names + synonyms)")

    # Build ontology xref -> DOID lookup (EFO, MONDO, MIM, etc.)
    xref_to_doid = {}
    if xrefs_df is not None and not xrefs_df.empty:
        xref_to_doid = dict(zip(xrefs_df['xref'], xrefs_df['doid']))
        logger.info(f"Built xref->DOID lookup with {len(xref_to_doid)} entries")

    df = gwas_data[gd_key]
    before = len(df)

    # If disease_doid already exists and is populated, this is idempotent — skip
    if 'disease_doid' in df.columns and df['disease_doid'].notna().all():
        logger.info(f"GWAS {gd_key}: disease_doid already populated ({len(df)} rows), skipping remap")
        return

    # Strategy 1: Match by disease_trait (free text)
    df['disease_doid'] = df['disease_trait'].str.strip().str.lower().map(name_to_doid)
    matched_1 = df['disease_doid'].notna().sum()

    # Strategy 2: Match by mapped_trait (curated name) for unmatched rows
    if 'mapped_trait' in df.columns:
        unmatched = df['disease_doid'].isna()
        df.loc[unmatched, 'disease_doid'] = (
            df.loc[unmatched, 'mapped_trait'].str.strip().str.lower().map(name_to_doid)
        )
        matched_2 = df['disease_doid'].notna().sum() - matched_1
    else:
        matched_2 = 0

    # Strategy 3: Match by mapped_trait_uri ontology cross-references
    matched_3 = 0
    if 'mapped_trait_uri' in df.columns and xref_to_doid:
        unmatched = df['disease_doid'].isna()
        if unmatched.any():
            def _uri_to_doid(uri_str):
                if pd.isna(uri_str):
                    return None
                for uri in str(uri_str).split(', '):
                    uri = uri.strip()
                    # EFO: http://www.ebi.ac.uk/efo/EFO_0004703 -> EFO:0004703
                    if '/efo/EFO_' in uri:
                        eid = uri.split('/efo/')[1].replace('_', ':', 1)
                        if eid in xref_to_doid:
                            return xref_to_doid[eid]
                    # OBO: http://purl.obolibrary.org/obo/MONDO_0005148 -> MONDO:0005148
                    elif '/obo/' in uri:
                        oid = uri.split('/obo/')[1].replace('_', ':', 1)
                        if oid in xref_to_doid:
                            return xref_to_doid[oid]
                return None

            df.loc[unmatched, 'disease_doid'] = (
                df.loc[unmatched, 'mapped_trait_uri'].apply(_uri_to_doid)
            )
            matched_3 = df['disease_doid'].notna().sum() - matched_1 - matched_2

    df = df.dropna(subset=['disease_doid'])
    gwas_data[gd_key] = df
    logger.info(
        f"GWAS {gd_key}: {before} -> {len(df)} rows after remap "
        f"(name: {matched_1}, mapped_trait: {matched_2}, URI xref: {matched_3})"
    )


# =========================================================================
# CLI
# =========================================================================

def _print_validation_report(report: Dict):
    """Pretty-print a validation report."""
    if 'error' in report:
        print(f"ERROR: {report['error']}")
        return

    rate = report['match_rate'] * 100
    print(f"\n{'='*60}")
    print(f"ID Mapping Validation Report")
    print(f"{'='*60}")
    print(f"  TSV:           {report['tsv_path']}")
    print(f"  Column:        {report['id_column']}")
    print(f"  Target:        {report['node_label']}.{report['node_property']}")
    print(f"  Unique IDs:    {report['total_unique']}")
    print(f"  Matched:       {report['matched']}")
    print(f"  Unmatched:     {report['unmatched']}")
    print(f"  Match rate:    {rate:.1f}%")
    print(f"  Unmatched edges: {report['unmatched_edges_total']}")

    sample = report.get('sample_unmatched', {})
    if sample:
        print(f"\n  Top unmatched IDs (by edge count):")
        for i, (uid, count) in enumerate(sorted(sample.items(), key=lambda x: -x[1])):
            if i >= 20:
                break
            print(f"    {uid:40s} {count:>6} edges")
    print()


def main():
    parser = argparse.ArgumentParser(
        description='CardioKB ID Mapping CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  python src/id_mapping.py --validate data/processed/jensentissues/gene_tissue_associations.tsv \\\n'
            '    --id-col tissue_name --node BodyPart --prop commonName\n'
            '\n'
            '  python src/id_mapping.py --suggest data/processed/jensentissues/gene_tissue_associations.tsv \\\n'
            '    --id-col tissue_name --node BodyPart\n'
            '\n'
            '  python src/id_mapping.py --map 7157 --from ncbi_gene --to ensembl\n'
            '\n'
            '  python src/id_mapping.py --create-missing data/processed/jensentissues/gene_tissue_associations.tsv \\\n'
            '    --id-col tissue_name --node BodyPart --id-prop commonName --min-edges 10\n'
        ),
    )

    parser.add_argument('--validate', metavar='TSV',
                        help='Validate IDs in a TSV against Neo4j')
    parser.add_argument('--suggest', metavar='TSV',
                        help='Suggest best ID system for a TSV column')
    parser.add_argument('--create-missing', metavar='TSV',
                        help='Create missing nodes for unmatched IDs')
    parser.add_argument('--map', metavar='ID',
                        help='Map a single ID between systems')
    parser.add_argument('--id-col', help='TSV column containing IDs')
    parser.add_argument('--node', help='Neo4j node label')
    parser.add_argument('--prop', help='Neo4j node property to match')
    parser.add_argument('--id-prop', help='Neo4j property to store ID as (for --create-missing)')
    parser.add_argument('--name-col', help='TSV column for commonName (for --create-missing)')
    parser.add_argument('--min-edges', type=int, default=10,
                        help='Min edge count threshold for --create-missing (default: 10)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview --create-missing without writing')
    parser.add_argument('--from', dest='from_sys', help='Source ID system (for --map)')
    parser.add_argument('--to', dest='to_sys', help='Target ID system (for --map)')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

    if args.map:
        if not args.from_sys or not args.to_sys:
            parser.error('--map requires --from and --to')
        with IDMapper() as mapper:
            result = mapper.map_id(args.map, args.from_sys, args.to_sys)
            if result:
                print(f"{args.map} ({args.from_sys}) -> {result} ({args.to_sys})")
            else:
                print(f"No mapping found for {args.map} ({args.from_sys} -> {args.to_sys})")
        return

    if args.validate:
        if not args.id_col or not args.node or not args.prop:
            parser.error('--validate requires --id-col, --node, --prop')
        with IDMapper() as mapper:
            report = mapper.validate_mapping(args.validate, args.id_col,
                                             args.node, args.prop)
            _print_validation_report(report)
        return

    if args.suggest:
        if not args.id_col or not args.node:
            parser.error('--suggest requires --id-col and --node')
        with IDMapper() as mapper:
            results = mapper.suggest_mapping(args.suggest, args.id_col, args.node)
            print(f"\nSuggested mappings for {args.id_col} -> {args.node}:")
            print(f"{'System':<20s} {'Property':<20s} {'Matched':>8s} {'Total':>8s} {'Rate':>8s}")
            print('-' * 66)
            for r in results:
                rate = r['match_rate'] * 100
                print(f"{r['id_system']:<20s} {r['property']:<20s} "
                      f"{r['matched']:>8d} {r['total']:>8d} {rate:>7.1f}%")
        return

    if args.create_missing:
        if not args.id_col or not args.node or not args.id_prop:
            parser.error('--create-missing requires --id-col, --node, --id-prop')
        with IDMapper() as mapper:
            result = mapper.create_missing_nodes(
                args.create_missing, args.id_col, args.node, args.id_prop,
                name_column=args.name_col,
                min_edges=args.min_edges,
                dry_run=args.dry_run,
            )
            if 'error' in result:
                print(f"ERROR: {result['error']}")
            elif result.get('dry_run'):
                print(f"\nDry run: would create {result['would_create']} {args.node} nodes")
                print(f"  Would skip: {result['would_skip']} (< {args.min_edges} edges)")
                print(f"  Edges recovered: {result['total_edges_recovered']}")
                print(f"  Edges lost: {result['total_edges_skipped']}")
                if result.get('top_candidates'):
                    print(f"\n  Top candidates:")
                    for uid, count in result['top_candidates'].items():
                        print(f"    {uid:40s} {count:>6} edges")
            else:
                print(f"\nCreated {result['created']} new {args.node} nodes")
                print(f"  Already existed: {result['merged_existing']}")
                print(f"  Skipped: {result['skipped']} (< {args.min_edges} edges)")
                print(f"  Edges recovered: {result['total_edges_recovered']}")
        return

    parser.print_help()


if __name__ == '__main__':
    main()
