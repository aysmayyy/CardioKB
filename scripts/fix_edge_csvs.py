#!/usr/bin/env python3
"""
Fix edge CSVs by resolving IDs using ALL identifier properties from node CSVs.

Strategy:
1. Build comprehensive lookup maps from all identifier columns in each node CSV
2. For each edge, try to resolve source/target using any matching identifier
3. Write fixed edge CSVs with canonical node IDs

Identifier properties used:
- Gene: id, geneId, geneSymbol, xrefEnsembl, xrefHGNC, xrefOMIM
- Disease: id, xrefDiseaseOntology, xrefUmlsCUI
- BodyPart: id, xrefUberon, xrefMeSH, xrefFMA
- Drug: id, xrefDrugBank, xrefMeSH, xrefChEMBL, xrefPubChem, xrefCAS, xrefKEGG
- Symptom: id, xrefMeSH
"""

import pandas as pd
from pathlib import Path
from typing import Optional, Dict, Set
import sys

OUT = Path(__file__).parent.parent / "data" / "output"

print("=" * 70)
print("Building comprehensive ID lookup maps from ALL node properties...")
print("=" * 70)
sys.stdout.flush()

# Master lookup: any identifier value -> canonical node_id
# We build ONE comprehensive lookup per node type
lookups: Dict[str, Dict[str, str]] = {}


def add_lookup(node_type: str, key: str, node_id: str):
    """Add a lookup entry with multiple key formats."""
    if node_type not in lookups:
        lookups[node_type] = {}
    if not key or pd.isna(key):
        return
    key = str(key).strip()
    if not key:
        return
    lookups[node_type][key] = node_id
    lookups[node_type][key.lower()] = node_id


# ============================================================================
# Gene lookups: id, geneId, geneSymbol, xrefEnsembl, xrefHGNC, xrefOMIM
# ============================================================================
df = pd.read_csv(OUT / "nodes_Gene.csv")
for _, row in df.iterrows():
    nid = row["id"]

    # Primary ID
    add_lookup("Gene", nid, nid)

    # geneId (numeric NCBI Gene ID)
    if pd.notna(row.get("geneId")):
        gid = str(int(row["geneId"]) if isinstance(row["geneId"], float) else row["geneId"])
        add_lookup("Gene", gid, nid)
        add_lookup("Gene", f"NCBIGene:{gid}", nid)
        add_lookup("Gene", f"Entrez:{gid}", nid)

    # geneSymbol
    if pd.notna(row.get("geneSymbol")):
        add_lookup("Gene", str(row["geneSymbol"]), nid)

    # xrefEnsembl (ENSG...)
    if pd.notna(row.get("xrefEnsembl")):
        ens = str(row["xrefEnsembl"])
        add_lookup("Gene", ens, nid)
        add_lookup("Gene", f"Ensembl:{ens}", nid)
        add_lookup("Gene", f"ENSG:{ens}", nid)

    # xrefHGNC
    if pd.notna(row.get("xrefHGNC")):
        hgnc = str(row["xrefHGNC"])
        add_lookup("Gene", hgnc, nid)
        add_lookup("Gene", f"HGNC:{hgnc}", nid)

    # xrefOMIM
    if pd.notna(row.get("xrefOMIM")):
        omim = str(row["xrefOMIM"])
        add_lookup("Gene", omim, nid)
        add_lookup("Gene", f"OMIM:{omim}", nid)

print(f"Gene: {len(df)} nodes, {len(lookups.get('Gene', {}))} lookup entries")

# ============================================================================
# Disease lookups: id, xrefDiseaseOntology, xrefUmlsCUI
# ============================================================================
df = pd.read_csv(OUT / "nodes_Disease.csv")
for _, row in df.iterrows():
    nid = row["id"]

    # Primary ID (DOID:DOID:xxxx format)
    add_lookup("Disease", nid, nid)

    # xrefDiseaseOntology (DOID:xxxx)
    if pd.notna(row.get("xrefDiseaseOntology")):
        doid = str(row["xrefDiseaseOntology"])
        add_lookup("Disease", doid, nid)
        add_lookup("Disease", f"DOID:{doid}", nid)
        # Also bare number
        if doid.startswith("DOID:"):
            add_lookup("Disease", doid.replace("DOID:", ""), nid)

    # xrefUmlsCUI
    if pd.notna(row.get("xrefUmlsCUI")):
        cui = str(row["xrefUmlsCUI"])
        add_lookup("Disease", cui, nid)
        add_lookup("Disease", f"UMLS:{cui}", nid)
        add_lookup("Disease", f"CUI:{cui}", nid)

    # diseaseName for fuzzy matching
    if pd.notna(row.get("diseaseName")):
        add_lookup("Disease", str(row["diseaseName"]), nid)

print(f"Disease: {len(df)} nodes, {len(lookups.get('Disease', {}))} lookup entries")

# ============================================================================
# BodyPart lookups: id, xrefUberon, xrefMeSH, xrefFMA
# ============================================================================
df = pd.read_csv(OUT / "nodes_BodyPart.csv")
for _, row in df.iterrows():
    nid = row["id"]

    # Primary ID (UBERON:UBERON:xxxx format)
    add_lookup("BodyPart", nid, nid)
    add_lookup("Anatomy", nid, nid)

    # xrefUberon
    if pd.notna(row.get("xrefUberon")):
        ub = str(row["xrefUberon"])
        add_lookup("BodyPart", ub, nid)
        add_lookup("BodyPart", f"UBERON:{ub}", nid)
        add_lookup("Anatomy", ub, nid)
        add_lookup("Anatomy", f"UBERON:{ub}", nid)
        # Also bare number
        if ub.startswith("UBERON:"):
            bare = ub.replace("UBERON:", "")
            add_lookup("BodyPart", bare, nid)
            add_lookup("Anatomy", bare, nid)

    # xrefMeSH (for anatomy)
    if pd.notna(row.get("xrefMeSH")):
        mesh = str(row["xrefMeSH"])
        add_lookup("BodyPart", mesh, nid)
        add_lookup("BodyPart", f"MeSH:{mesh}", nid)
        add_lookup("BodyPart", f"MESH:{mesh}", nid)
        add_lookup("Anatomy", mesh, nid)
        add_lookup("Anatomy", f"MeSH:{mesh}", nid)

    # xrefFMA
    if pd.notna(row.get("xrefFMA")):
        fma = str(row["xrefFMA"])
        add_lookup("BodyPart", fma, nid)
        add_lookup("BodyPart", f"FMA:{fma}", nid)
        add_lookup("Anatomy", fma, nid)

    # bodyPartName
    if pd.notna(row.get("bodyPartName")):
        add_lookup("BodyPart", str(row["bodyPartName"]), nid)
        add_lookup("Anatomy", str(row["bodyPartName"]), nid)

print(f"BodyPart: {len(df)} nodes, {len(lookups.get('BodyPart', {}))} lookup entries")

# ============================================================================
# Drug lookups: id, xrefDrugBank, xrefMeSH, xrefChEMBL, xrefPubChem, etc.
# ============================================================================
df = pd.read_csv(OUT / "nodes_Drug.csv")
for _, row in df.iterrows():
    nid = row["id"]

    # Primary ID
    add_lookup("Drug", nid, nid)
    add_lookup("Compound", nid, nid)

    # xrefDrugBank
    if pd.notna(row.get("xrefDrugBank")):
        db = str(row["xrefDrugBank"])
        add_lookup("Drug", db, nid)
        add_lookup("Drug", f"DrugBank:{db}", nid)
        add_lookup("Compound", db, nid)
        add_lookup("Compound", f"DrugBank:{db}", nid)

    # xrefMeSH
    if pd.notna(row.get("xrefMeSH")):
        mesh = str(row["xrefMeSH"])
        add_lookup("Drug", mesh, nid)
        add_lookup("Drug", f"MeSH:{mesh}", nid)
        add_lookup("Drug", f"MESH:{mesh}", nid)
        add_lookup("Compound", mesh, nid)
        add_lookup("Compound", f"MeSH:{mesh}", nid)

    # xrefChEMBL
    if pd.notna(row.get("xrefChEMBL")):
        chembl = str(row["xrefChEMBL"])
        add_lookup("Drug", chembl, nid)
        add_lookup("Drug", f"ChEMBL:{chembl}", nid)
        add_lookup("Drug", f"CHEMBL:{chembl}", nid)
        add_lookup("Compound", chembl, nid)

    # xrefPubChem
    if pd.notna(row.get("xrefPubChem")):
        pc = str(row["xrefPubChem"])
        add_lookup("Drug", pc, nid)
        add_lookup("Drug", f"PubChem:{pc}", nid)
        add_lookup("Drug", f"CID:{pc}", nid)
        add_lookup("Compound", pc, nid)

    # xrefCAS
    if pd.notna(row.get("xrefCAS")):
        cas = str(row["xrefCAS"])
        add_lookup("Drug", cas, nid)
        add_lookup("Drug", f"CAS:{cas}", nid)
        add_lookup("Compound", cas, nid)

    # xrefKEGG
    if pd.notna(row.get("xrefKEGG")):
        kegg = str(row["xrefKEGG"])
        add_lookup("Drug", kegg, nid)
        add_lookup("Drug", f"KEGG:{kegg}", nid)
        add_lookup("Compound", kegg, nid)

    # commonName
    if pd.notna(row.get("commonName")):
        add_lookup("Drug", str(row["commonName"]), nid)
        add_lookup("Compound", str(row["commonName"]), nid)

print(f"Drug: {len(df)} nodes, {len(lookups.get('Drug', {}))} lookup entries")

# ============================================================================
# Symptom lookups: id, xrefMeSH
# ============================================================================
if (OUT / "nodes_Symptom.csv").exists():
    df = pd.read_csv(OUT / "nodes_Symptom.csv")
    for _, row in df.iterrows():
        nid = row["id"]
        add_lookup("Symptom", nid, nid)

        if pd.notna(row.get("xrefMeSH")):
            mesh = str(row["xrefMeSH"])
            add_lookup("Symptom", mesh, nid)
            add_lookup("Symptom", f"MeSH:{mesh}", nid)
            add_lookup("Symptom", f"MESH:{mesh}", nid)

        if pd.notna(row.get("symptomName")):
            add_lookup("Symptom", str(row["symptomName"]), nid)

    print(f"Symptom: {len(df)} nodes, {len(lookups.get('Symptom', {}))} lookup entries")

# ============================================================================
# Other entity lookups (direct ID matching)
# ============================================================================
for label, filename, extra_cols in [
    ("BiologicalProcess", "nodes_BiologicalProcess.csv", ["xrefGeneOntology"]),
    ("MolecularFunction", "nodes_MolecularFunction.csv", ["xrefGeneOntology"]),
    ("CellularComponent", "nodes_CellularComponent.csv", ["xrefGeneOntology"]),
    ("Pathway", "nodes_Pathway.csv", ["pathwayId"]),
    ("SideEffect", "nodes_SideEffect.csv", []),
    ("Phenotype", "nodes_Phenotype.csv", []),
    ("GeneFamily", "nodes_GeneFamily.csv", []),
    ("PharmacologicClass", "nodes_PharmacologicClass.csv", []),
    ("Variant", "nodes_Variant.csv", []),
    ("TranscriptionFactor", "nodes_TranscriptionFactor.csv", []),
    ("ClinicalTrial", "nodes_ClinicalTrial.csv", ["nctId"]),
    ("DrugLabel", "nodes_DrugLabel.csv", []),
]:
    fpath = OUT / filename
    if fpath.exists():
        df = pd.read_csv(fpath)
        for _, row in df.iterrows():
            nid = str(row["id"])
            add_lookup(label, nid, nid)

            # Also add with/without common prefixes
            for prefix in ["GO:", "HP:", "Reactome:", "R-HSA-", "HGNC:", "ClinVar:", "NCT"]:
                if nid.startswith(prefix):
                    add_lookup(label, nid.replace(prefix, ""), nid)
                else:
                    add_lookup(label, f"{prefix}{nid}", nid)

            # Extra columns
            for col in extra_cols:
                if col in df.columns and pd.notna(row.get(col)):
                    add_lookup(label, str(row[col]), nid)

        print(f"{label}: {len(df)} nodes, {len(lookups.get(label, {}))} lookup entries")

# Also build a master set of all node IDs for direct matching
all_node_ids: Set[str] = set()
for lookup in lookups.values():
    all_node_ids.update(v for v in lookup.values())

print(f"\nTotal unique node IDs: {len(all_node_ids)}")


# ============================================================================
# Resolution function
# ============================================================================
def resolve_id(raw_id: str, hint_type: str = None) -> Optional[str]:
    """
    Resolve an edge ID to an exact node ID.

    Args:
        raw_id: The ID from the edge file
        hint_type: Optional node type hint (e.g., "Gene", "Disease")
    """
    raw_id = str(raw_id).strip()
    if not raw_id:
        return None

    # 1. Check if it's already a valid node ID
    if raw_id in all_node_ids:
        return raw_id

    # 2. Try the hinted type first
    if hint_type and hint_type in lookups:
        if raw_id in lookups[hint_type]:
            return lookups[hint_type][raw_id]
        if raw_id.lower() in lookups[hint_type]:
            return lookups[hint_type][raw_id.lower()]

    # 3. Try to infer type from ID prefix and lookup
    prefix_to_types = {
        "NCBIGene:": ["Gene"],
        "ENSG": ["Gene"],
        "Ensembl:": ["Gene"],
        "HGNC:": ["Gene", "GeneFamily"],
        "DrugBank:": ["Drug", "Compound"],
        "DrugCentral:": ["Drug", "Compound"],
        "CTD:": ["Drug", "Compound"],
        "MeSH:": ["Drug", "Symptom", "BodyPart"],
        "MESH:": ["Drug", "Symptom", "BodyPart"],
        "DOID:": ["Disease"],
        "UMLS:": ["Disease"],
        "UBERON:": ["BodyPart", "Anatomy"],
        "GO:": ["BiologicalProcess", "MolecularFunction", "CellularComponent"],
        "HP:": ["Phenotype"],
        "Reactome:": ["Pathway"],
        "R-HSA-": ["Pathway"],
        "ClinVar:": ["Variant"],
        "NCT": ["ClinicalTrial"],
    }

    for prefix, types in prefix_to_types.items():
        if raw_id.startswith(prefix):
            for t in types:
                if t in lookups and raw_id in lookups[t]:
                    return lookups[t][raw_id]
                if t in lookups and raw_id.lower() in lookups[t]:
                    return lookups[t][raw_id.lower()]

    # 4. Try all lookups
    for node_type, lookup in lookups.items():
        if raw_id in lookup:
            return lookup[raw_id]
        if raw_id.lower() in lookup:
            return lookup[raw_id.lower()]

    return None


def parse_edge_id(raw):
    """Extract type hint and value from edge ID like 'Gene:123' or 'NCBIGene:123'."""
    raw = str(raw).strip()

    # Map known prefixes to node types
    prefix_to_type = {
        "NCBIGene": "Gene",
        "Entrez": "Gene",
        "Gene": "Gene",
        "ENSG": "Gene",
        "Ensembl": "Gene",
        "DrugBank": "Drug",
        "DrugCentral": "Drug",
        "CTD": "Drug",
        "Drug": "Drug",
        "Compound": "Drug",
        "DOID": "Disease",
        "Disease": "Disease",
        "UMLS": "Disease",
        "UBERON": "BodyPart",
        "Anatomy": "BodyPart",
        "BodyPart": "BodyPart",
        "GO": "BiologicalProcess",  # Could also be MF/CC
        "HP": "Phenotype",
        "Phenotype": "Phenotype",
        "Reactome": "Pathway",
        "Pathway": "Pathway",
        "MeSH": "Symptom",  # Could also be Drug
        "MESH": "Symptom",
        "Symptom": "Symptom",
        "SideEffect": "SideEffect",
        "ClinVar": "Variant",
        "Variant": "Variant",
        "GeneFamily": "GeneFamily",
        "TranscriptionFactor": "TranscriptionFactor",
        "ClinicalTrial": "ClinicalTrial",
        "PharmacologicClass": "PharmacologicClass",
    }

    if ":" in raw:
        prefix = raw.split(":")[0]
        if prefix in prefix_to_type:
            return prefix_to_type[prefix], raw

    return None, raw


# ============================================================================
# Process each edge CSV
# ============================================================================
print("\n" + "=" * 70)
print("Fixing edge CSVs with comprehensive ID resolution...")
print("=" * 70)
sys.stdout.flush()

total_orig = 0
total_fixed = 0
unresolved_samples = {}

for ef in sorted(OUT.glob("edges_*.csv")):
    if ef.name.startswith("fixed_"):
        continue

    df = pd.read_csv(ef)
    if ":START_ID" not in df.columns:
        continue

    orig_count = len(df)
    total_orig += orig_count

    new_start = []
    new_end = []
    keep_rows = []
    unresolved_start = set()
    unresolved_end = set()

    for idx, row in df.iterrows():
        src_hint, src_raw = parse_edge_id(row[":START_ID"])
        tgt_hint, tgt_raw = parse_edge_id(row[":END_ID"])

        src_id = resolve_id(src_raw, src_hint)
        tgt_id = resolve_id(tgt_raw, tgt_hint)

        if src_id and tgt_id:
            new_start.append(src_id)
            new_end.append(tgt_id)
            keep_rows.append(idx)
        else:
            if not src_id and len(unresolved_start) < 5:
                unresolved_start.add(str(row[":START_ID"]))
            if not tgt_id and len(unresolved_end) < 5:
                unresolved_end.add(str(row[":END_ID"]))

    if keep_rows:
        df_fixed = df.loc[keep_rows].copy()
        df_fixed[":START_ID"] = new_start
        df_fixed[":END_ID"] = new_end

        fixed_path = OUT / f"fixed_{ef.name}"
        df_fixed.to_csv(fixed_path, index=False)

        fixed_count = len(df_fixed)
        total_fixed += fixed_count
        pct = (fixed_count / orig_count * 100) if orig_count > 0 else 0
        status = "OK" if pct == 100 else "PARTIAL"
        print(f"  [{status}] {ef.name}: {fixed_count:,}/{orig_count:,} ({pct:.1f}%)")
    else:
        print(f"  [FAIL] {ef.name}: 0/{orig_count:,} (0.0%) - NO MATCHES")
        if unresolved_start or unresolved_end:
            unresolved_samples[ef.name] = {
                "start": list(unresolved_start)[:3],
                "end": list(unresolved_end)[:3]
            }

    sys.stdout.flush()

print("\n" + "=" * 70)
pct = (total_fixed / total_orig * 100) if total_orig > 0 else 0
print(f"Total: {total_fixed:,}/{total_orig:,} edges fixed ({pct:.1f}%)")
print(f"Fixed files written to: {OUT}/fixed_*.csv")
print("=" * 70)

# Show sample unresolved IDs for debugging
if unresolved_samples:
    print("\nSample unresolved IDs (for debugging):")
    for fname, samples in list(unresolved_samples.items())[:10]:
        print(f"  {fname}:")
        if samples["start"]:
            print(f"    START: {samples['start']}")
        if samples["end"]:
            print(f"    END: {samples['end']}")
