#!/usr/bin/env python3
"""
Preprocess CardioKB CSV exports for Memgraph LOAD CSV import.

The BaseAgent exporter produces edge CSVs in two formats:
  1. Simple: start_id,end_id (internal node IDs) — no properties
  2. Rich: :START_ID,:END_ID,:TYPE,prop1,... (external DB IDs) — with properties

This script remaps the rich-format external IDs to internal node IDs so
LOAD CSV can MATCH on the indexed `id` property.

Usage:
    python scripts/prepare_import.py
"""

import csv
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'output')


def build_gene_lookup(data_dir):
    """NCBIGene ID (string) -> internal node id."""
    lookup = {}
    with open(os.path.join(data_dir, 'nodes_Gene.csv')) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ncbi = row.get('xrefNcbiGene', '').strip()
            if ncbi:
                lookup[ncbi] = row['id']
    print(f"  Gene lookup: {len(lookup)} entries")
    return lookup


def build_drug_dc_lookup(data_dir):
    """DrugCentral ID (string) -> internal node id."""
    lookup = {}
    with open(os.path.join(data_dir, 'nodes_Drug.csv')) as f:
        reader = csv.DictReader(f)
        for row in reader:
            dc = row.get('xrefDrugCentral', '').strip()
            if dc:
                lookup[dc] = row['id']
    print(f"  Drug (DrugCentral) lookup: {len(lookup)} entries")
    return lookup


def convert_id(ext_id, gene_lookup, drug_dc_lookup):
    """Convert an external DB ID to an internal node ID."""
    if ext_id.startswith('NCBIGene:'):
        ncbi_id = ext_id.split(':', 1)[1]
        result = gene_lookup.get(ncbi_id)
        if not result:
            return None, f"NCBIGene:{ncbi_id} not found in gene lookup"
        return result, None

    if ext_id.startswith('UBERON:'):
        uberon_id = ext_id.split(':', 1)[1]
        return f"bodypart_uberon{uberon_id}", None

    if ext_id.startswith('DOID:'):
        doid_id = ext_id.split(':', 1)[1]
        return f"disease_doid{doid_id}", None

    if ext_id.startswith('DrugBank:'):
        db_id = ext_id.split(':', 1)[1]
        return f"drug_{db_id.lower()}", None

    if ext_id.startswith('DrugCentral:'):
        dc_id = ext_id.split(':', 1)[1]
        result = drug_dc_lookup.get(dc_id)
        if not result:
            return None, f"DrugCentral:{dc_id} not found in drug lookup"
        return result, None

    if ext_id.startswith('CTD:MESH:'):
        mesh_id = ext_id.split('CTD:MESH:', 1)[1]
        return f"drug_mesh{mesh_id.lower()}", None

    if ext_id.startswith('HGNC:'):
        return ext_id, None

    if ext_id.startswith('ClinVar:'):
        variant_id = ext_id.split(':', 1)[1]
        return f"variant_{variant_id}", None

    return None, f"Unknown ID prefix: {ext_id}"


RICH_EDGE_FILES = [
    'edges_AFFECTS_RESPONSE_TO.csv',
    'edges_bodyPartOverexpressesGene.csv',
    'edges_chemicalDecreasesExpression.csv',
    'edges_chemicalIncreasesExpression.csv',
    'edges_drugTreatsDisease.csv',
    'edges_geneAssociatesWithDisease.csv',
    'edges_transcriptionFactorInteractsWithGene.csv',
    'edges_variantAssociatedWithDisease.csv',
]


def process_rich_edge_file(filepath, gene_lookup, drug_dc_lookup):
    """Remap :START_ID/:END_ID to internal IDs, rename to start_id/end_id."""
    rows_in = 0
    rows_out = 0
    errors = {}

    with open(filepath) as f:
        reader = csv.DictReader(f)
        old_fields = reader.fieldnames
        prop_fields = [c for c in old_fields if c not in (':START_ID', ':END_ID', ':TYPE')]
        new_fields = ['start_id', 'end_id'] + prop_fields

        out_path = filepath
        tmp_path = filepath + '.tmp'

        with open(tmp_path, 'w', newline='') as out:
            writer = csv.DictWriter(out, fieldnames=new_fields)
            writer.writeheader()

            for row in reader:
                rows_in += 1
                start_ext = row[':START_ID']
                end_ext = row[':END_ID']

                start_id, err1 = convert_id(start_ext, gene_lookup, drug_dc_lookup)
                end_id, err2 = convert_id(end_ext, gene_lookup, drug_dc_lookup)

                if err1:
                    errors[err1] = errors.get(err1, 0) + 1
                    continue
                if err2:
                    errors[err2] = errors.get(err2, 0) + 1
                    continue

                new_row = {'start_id': start_id, 'end_id': end_id}
                for p in prop_fields:
                    new_row[p] = row[p]
                writer.writerow(new_row)
                rows_out += 1

    os.replace(tmp_path, out_path)
    return rows_in, rows_out, errors


def main():
    data_dir = os.path.abspath(DATA_DIR)
    print(f"Data directory: {data_dir}")

    print("Building lookup tables...")
    gene_lookup = build_gene_lookup(data_dir)
    drug_dc_lookup = build_drug_dc_lookup(data_dir)

    print(f"\nProcessing {len(RICH_EDGE_FILES)} rich edge files...")
    total_in = 0
    total_out = 0
    all_errors = {}

    for filename in RICH_EDGE_FILES:
        filepath = os.path.join(data_dir, filename)
        if not os.path.exists(filepath):
            print(f"  SKIP {filename} (not found)")
            continue

        rows_in, rows_out, errors = process_rich_edge_file(
            filepath, gene_lookup, drug_dc_lookup
        )
        total_in += rows_in
        total_out += rows_out
        dropped = rows_in - rows_out
        status = f"({dropped} dropped)" if dropped else ""
        print(f"  {filename}: {rows_in} -> {rows_out} {status}")

        if errors:
            for msg, count in sorted(errors.items(), key=lambda x: -x[1])[:5]:
                print(f"    WARNING: {msg} (x{count})")
                all_errors[msg] = all_errors.get(msg, 0) + count

    print(f"\nDone. {total_in} rows in, {total_out} rows out, {total_in - total_out} dropped.")
    if all_errors:
        print(f"Total unique error types: {len(all_errors)}")


if __name__ == '__main__':
    main()
