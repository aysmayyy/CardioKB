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

    # Remap disease-disease co-occurrence
    dd_key = 'disease_disease_cooccurrence'
    if dd_key in pt_data:
        df = pt_data[dd_key]
        before = len(df)
        df['disease1_id'] = df['disease1_id'].map(mesh_to_doid)
        df['disease2_id'] = df['disease2_id'].map(mesh_to_doid)
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
        df['disease_id'] = df['disease_id'].map(mesh_to_doid)
        df = df.dropna(subset=['disease_id'])
        pt_data[gd_key] = df
        logger.info(f"PubTator {gd_key}: {before} -> {len(df)} rows after MESH->DOID remap")


def remap_gwas_disease_to_doid(parsed_data: Dict[str, Dict[str, pd.DataFrame]]) -> None:
    """
    Remap GWAS free-text disease_trait to DOID using Disease Ontology node names and synonyms.

    Adds a 'disease_doid' column to parsed_data['gwas']['gene_disease_gwas']
    and drops rows without a mapping.
    """
    do_data = parsed_data.get('disease_ontology', {})
    gwas_data = parsed_data.get('gwas', {})

    nodes_df = do_data.get('disease_nodes')
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

    df = gwas_data[gd_key]
    before = len(df)
    df['disease_doid'] = df['disease_trait'].str.strip().str.lower().map(name_to_doid)
    df = df.dropna(subset=['disease_doid'])
    gwas_data[gd_key] = df
    logger.info(f"GWAS {gd_key}: {before} -> {len(df)} rows after disease_trait->DOID remap")
