"""
Enrich Drug nodes with MeSH cross-references from CTD chemicals vocabulary.

Maps Drug.xrefCAS and Drug.commonName to MeSH IDs using the CTD
CTD_chemicals.tsv.gz vocabulary file (179K chemicals with CAS, synonym,
and name-based matching).

Run after graph loading to fill Drug.xrefMeSH for nodes that lack it.
Also callable as a library function from the pipeline.
"""

import gzip
import logging
from pathlib import Path

import requests
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CTD_CHEMICALS_URL = "https://ctdbase.org/reports/CTD_chemicals.tsv.gz"
CTD_CHEMICALS_PATH = PROJECT_ROOT / "data" / "raw" / "ctd" / "CTD_chemicals.tsv.gz"

MEMGRAPH_URI = "bolt://localhost:7687"


def download_ctd_chemicals():
    """Download CTD chemicals vocabulary if not cached."""
    if CTD_CHEMICALS_PATH.exists():
        log.info("Using cached %s", CTD_CHEMICALS_PATH)
        return CTD_CHEMICALS_PATH

    CTD_CHEMICALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    log.info("Downloading %s ...", CTD_CHEMICALS_URL)
    resp = requests.get(CTD_CHEMICALS_URL, timeout=120)
    resp.raise_for_status()
    CTD_CHEMICALS_PATH.write_bytes(resp.content)
    log.info("Downloaded %.1f MB", len(resp.content) / 1e6)
    return CTD_CHEMICALS_PATH


def build_mesh_maps(gz_path):
    """Build name→MeSH, CAS→MeSH, synonym→MeSH from CTD chemicals vocabulary."""
    name_to_mesh = {}
    cas_to_mesh = {}
    synonym_to_mesh = {}

    with gzip.open(gz_path, "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 2:
                continue

            mesh_id = fields[1].strip()
            if not mesh_id.startswith("MESH:"):
                mesh_id = f"MESH:{mesh_id}"

            chem_name = fields[0].strip().lower()
            cas = fields[2].strip() if len(fields) > 2 else ""
            synonyms = fields[7].strip() if len(fields) > 7 else ""

            if chem_name:
                name_to_mesh[chem_name] = mesh_id
            if cas:
                cas_to_mesh[cas] = mesh_id
            if synonyms:
                for syn in synonyms.split("|"):
                    syn = syn.strip().lower()
                    if syn:
                        synonym_to_mesh[syn] = mesh_id

    log.info(
        "CTD MeSH maps: %d names, %d CAS, %d synonyms",
        len(name_to_mesh),
        len(cas_to_mesh),
        len(synonym_to_mesh),
    )
    return name_to_mesh, cas_to_mesh, synonym_to_mesh


def enrich(driver=None):
    """Enrich Drug nodes missing xrefMeSH. Returns count of updated nodes."""
    gz_path = download_ctd_chemicals()
    name_to_mesh, cas_to_mesh, synonym_to_mesh = build_mesh_maps(gz_path)

    own_driver = driver is None
    if own_driver:
        driver = GraphDatabase.driver(MEMGRAPH_URI, auth=("", ""))

    try:
        with driver.session() as s:
            r = s.run(
                "MATCH (d:Drug) "
                "WHERE d.xrefMeSH IS NULL OR d.xrefMeSH = '' "
                "RETURN d.id AS id, toLower(d.commonName) AS name, d.xrefCAS AS cas"
            )
            missing = [dict(rec) for rec in r]

        log.info("Drug nodes missing xrefMeSH: %d", len(missing))

        batch = []
        for d in missing:
            mesh = None
            cas = d.get("cas") or ""
            name = d.get("name") or ""
            if cas and cas in cas_to_mesh:
                mesh = cas_to_mesh[cas]
            elif name and name in name_to_mesh:
                mesh = name_to_mesh[name]
            elif name and name in synonym_to_mesh:
                mesh = synonym_to_mesh[name]
            if mesh:
                batch.append({"id": d["id"], "mesh": mesh})

        log.info("MeSH IDs to apply: %d", len(batch))

        updated = 0
        for i in range(0, len(batch), 500):
            chunk = batch[i : i + 500]
            with driver.session() as s:
                result = s.run(
                    "UNWIND $batch AS row "
                    "MATCH (d:Drug {id: row.id}) "
                    "SET d.xrefMeSH = row.mesh "
                    "RETURN count(d) AS updated",
                    batch=chunk,
                )
                updated += result.single()["updated"]

        log.info("Updated %d Drug nodes with xrefMeSH", updated)

        with driver.session() as s:
            r = s.run(
                "MATCH (d:Drug) RETURN count(d) AS total, "
                "count(CASE WHEN d.xrefMeSH IS NOT NULL AND d.xrefMeSH <> '' "
                "THEN 1 END) AS with_mesh"
            )
            rec = r.single()
            pct = 100 * rec["with_mesh"] / rec["total"] if rec["total"] else 0
            log.info(
                "Drug.xrefMeSH coverage: %d/%d (%.1f%%)",
                rec["with_mesh"],
                rec["total"],
                pct,
            )

        return updated
    finally:
        if own_driver:
            driver.close()


if __name__ == "__main__":
    enrich()
