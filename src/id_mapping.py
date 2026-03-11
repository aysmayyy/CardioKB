"""
ID Mapping utilities for CardioKB post-processing.

Remaps identifiers in parsed data so that relationship merge queries
in Neo4j can match existing nodes.

- PubTator uses MESH:Dxxxx disease IDs; Disease nodes use DOID:xxxx
- GWAS uses free-text disease_trait; Disease nodes use DOID identifiers
"""

import logging
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


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
