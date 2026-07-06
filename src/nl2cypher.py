"""Natural language to Cypher translation for CardioKB.

Adapted from CypherGPT (Eng2Cypher) by Jay Moran.
Uses Claude API to translate natural language questions into Cypher queries,
validates against the live graph schema, and auto-corrects errors.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path
from functools import lru_cache

import anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

CACHE_DIR = Path(__file__).parent.parent / "config" / "nl2cypher"
CACHE_TTL = 86400  # 24 hours

PREFERRED_PROPS = {
    "Gene": "geneSymbol",
    "Disease": "diseaseName",
    "Drug": "commonName",
    "Variant": "variantName or variantId",
    "ClinicalTrial": "title",
    "Pathway": "pathwayName",
    "BodyPart": "bodyPartName",
    "Phenotype": "phenotypeName",
    "SideEffect": "sideEffectName",
    "TranscriptionFactor": "tfSymbol",
    "BiologicalProcess": "processName",
    "MolecularFunction": "functionName",
    "CellularComponent": "componentName",
    "GeneFamily": "familyName",
    "PharmacologicClass": "className",
    "Symptom": "symptomName",
    "DrugLabel": "labelName",
}

NODE_DESCRIPTIONS = {
    "Gene": "Human genes (protein-coding and non-coding) from NCBI Gene",
    "Disease": "Cardiovascular and related diseases from Disease Ontology",
    "Drug": "Drugs and chemical compounds from DrugBank and CTD",
    "Variant": "Genetic variants from ClinVar with clinical significance",
    "ClinicalTrial": "Clinical trials from ClinicalTrials.gov studying CVD conditions",
    "Pathway": "Biological pathways from Reactome",
    "BodyPart": "Anatomical structures from Uberon ontology",
    "Phenotype": "Human phenotypes from HPO (Human Phenotype Ontology)",
    "SideEffect": "Drug side effects from SIDER",
    "TranscriptionFactor": "Transcription factors from DoRothEA",
    "BiologicalProcess": "GO Biological Processes from Gene Ontology",
    "MolecularFunction": "GO Molecular Functions from Gene Ontology",
    "CellularComponent": "GO Cellular Components from Gene Ontology",
    "GeneFamily": "Gene families from HGNC",
    "PharmacologicClass": "Pharmacologic drug classes from DrugCentral",
    "Symptom": "Symptoms from MeSH",
    "DrugLabel": "Pharmacogenomic drug labels from ClinPGx",
}

REL_DESCRIPTIONS = {
    "geneAssociatesWithDisease": "Gene is statistically or experimentally associated with the disease (PubTator literature mining + OpenTargets curated evidence)",
    "drugTreatsDisease": "Drug is an approved or indicated treatment for the disease",
    "predictedTreatsDisease": "ML-predicted drug-disease treatment (not clinically validated, has confidence score)",
    "drugBindsGene": "Drug physically binds to the gene's protein product (DrugBank)",
    "chemicalBindsGene": "Chemical compound binds to gene's protein product (BindingDB)",
    "compoundCausesSideEffect": "Drug causes the side effect (SIDER)",
    "geneInteractsWithGene": "Genes produce physically-interacting proteins (STRING, confidence > 700)",
    "geneInPathway": "Gene participates in the biological pathway (Reactome)",
    "geneParticipatesInBiologicalProcess": "Gene participates in the GO biological process",
    "geneHasMolecularFunction": "Gene has the GO molecular function",
    "geneAssociatedWithCellularComponent": "Gene is associated with the GO cellular component",
    "geneAssociatesWithPhenotype": "Gene is associated with the phenotype (HPO)",
    "bodyPartOverexpressesGene": "Gene is over-expressed in the body part (Bgee, has expressionScore)",
    "chemicalIncreasesExpression": "Drug increases gene expression (CTD)",
    "chemicalDecreasesExpression": "Drug decreases gene expression (CTD)",
    "compoundUpregulatesGene": "Drug upregulates gene expression (LINCS L1000)",
    "compoundDownregulatesGene": "Drug downregulates gene expression (LINCS L1000)",
    "transcriptionFactorInteractsWithGene": "Transcription factor regulates target gene (DoRothEA, has morScore + confidence)",
    "variantInGene": "Variant is located in the gene (ClinVar)",
    "variantAssociatedWithDisease": "Variant is associated with the disease (ClinVar)",
    "hasVariant": "Gene has the variant (ClinVar)",
    "diseaseIsSubtypeOf": "Disease is a subtype of another disease (Disease Ontology hierarchy)",
    "geneInFamily": "Gene belongs to the gene family (HGNC)",
    "compoundInPharmacologicClass": "Drug belongs to the pharmacologic class (DrugCentral)",
    "STUDIES_CONDITION": "Clinical trial studies the disease condition (ClinicalTrials.gov)",
    "TESTS_INTERVENTION": "Clinical trial tests the drug intervention (ClinicalTrials.gov)",
    "AFFECTS_RESPONSE_TO": "Gene affects response to drug (ClinPGx pharmacogenomics)",
}

# ---------------------------------------------------------------------------
# Schema introspection (adapted from Eng2Cypher schema_cache.py)
# ---------------------------------------------------------------------------

def _run(driver, cypher):
    with driver.session() as s:
        return [r.data() for r in s.run(cypher)]


def get_schema(driver):
    labels = sorted({
        lbl for r in _run(driver, "MATCH (n) RETURN DISTINCT labels(n) AS l")
        for lbl in r["l"]
        if not lbl.startswith("_")
    })
    rels = sorted(
        r["t"] for r in _run(driver, "MATCH ()-[r]->() RETURN DISTINCT type(r) AS t")
    )
    props_raw = _run(driver, """
        MATCH (n)
        WITH labels(n) AS lbls, keys(n) AS props
        UNWIND lbls AS label
        UNWIND props AS prop
        WITH label, prop WHERE NOT label STARTS WITH '_'
        RETURN label, collect(DISTINCT prop) AS properties
        ORDER BY label
    """)
    props = {row["label"]: sorted(row["properties"]) for row in props_raw}
    return {"labels": labels, "relationships": rels, "properties": props}


def get_directed_topology(driver):
    rows = _run(driver, """
        MATCH (a)-[r]->(b)
        RETURN DISTINCT type(r) AS relationshipType,
               labels(a)[0] AS source,
               labels(b)[0] AS target
    """)
    seen, topo = set(), []
    for row in rows:
        key = (row["relationshipType"], row["source"], row["target"])
        if key not in seen:
            topo.append({
                "relationship": row["relationshipType"],
                "source": row["source"],
                "target": row["target"],
            })
            seen.add(key)
    return sorted(topo, key=lambda x: (x["relationship"], x["source"], x["target"]))


# ---------------------------------------------------------------------------
# Metadata caching
# ---------------------------------------------------------------------------

@dataclass
class CardioKBMetadata:
    schema: dict = field(default_factory=dict)
    topology: list = field(default_factory=list)
    preferred_props: dict = field(default_factory=lambda: dict(PREFERRED_PROPS))
    description: dict = field(default_factory=dict)

    @property
    def schema_json_text(self):
        return json.dumps(self.schema, separators=(",", ":"))

    @property
    def topology_json_text(self):
        return json.dumps(self.topology, separators=(",", ":"))

    @property
    def preferred_props_json_text(self):
        return json.dumps(self.preferred_props, separators=(",", ":"))

    @property
    def description_json_text(self):
        return json.dumps(self.description, separators=(",", ":"))


_metadata_cache = None
_metadata_time = 0


def _cache_path(name):
    return CACHE_DIR / f"{name}.json"


def _load_or_introspect(driver):
    schema_path = _cache_path("schema")
    topo_path = _cache_path("topology")

    if (schema_path.exists() and topo_path.exists()
            and time.time() - schema_path.stat().st_mtime < CACHE_TTL):
        schema = json.loads(schema_path.read_text())
        topology = json.loads(topo_path.read_text())
    else:
        schema = get_schema(driver)
        topology = get_directed_topology(driver)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(json.dumps(schema, separators=(",", ":")))
        topo_path.write_text(json.dumps(topology, separators=(",", ":")))

    desc = {"nodes": NODE_DESCRIPTIONS, "relationships": REL_DESCRIPTIONS}
    return CardioKBMetadata(
        schema=schema,
        topology=topology,
        preferred_props=dict(PREFERRED_PROPS),
        description=desc,
    )


def get_metadata(driver):
    global _metadata_cache, _metadata_time
    if _metadata_cache and time.time() - _metadata_time < CACHE_TTL:
        return _metadata_cache
    _metadata_cache = _load_or_introspect(driver)
    _metadata_time = time.time()
    return _metadata_cache


def refresh_metadata(driver):
    global _metadata_cache, _metadata_time
    for name in ("schema", "topology"):
        p = _cache_path(name)
        if p.exists():
            p.unlink()
    _metadata_cache = None
    _metadata_time = 0
    return get_metadata(driver)


# ---------------------------------------------------------------------------
# Cypher validation (adapted from Eng2Cypher validate.py)
# ---------------------------------------------------------------------------

def extract_labels_and_props(cypher):
    label_pattern = r"\([^)]*:([A-Z][A-Za-z0-9_]*)"
    rel_pattern = r"\[:([A-Za-z][A-Za-z0-9_]*)\]"
    prop_pattern = r"\.(\w+)"
    labels = set(re.findall(label_pattern, cypher))
    rels = set(re.findall(rel_pattern, cypher))
    props = set(re.findall(prop_pattern, cypher))
    return labels, rels, props


def validate_cypher(cypher, schema):
    labels, rels, props = extract_labels_and_props(cypher)
    known_labels = set(schema["labels"])
    known_rels = set(schema["relationships"])
    known_props = set()
    for lp in schema["properties"].values():
        known_props.update(lp)
    return (
        sorted(l for l in labels if l not in known_labels),
        sorted(r for r in rels if r not in known_rels),
        sorted(p for p in props if p not in known_props),
    )


def _all_props(schema):
    props = set()
    for pl in schema["properties"].values():
        props.update(pl)
    return list(props)


def suggest_fixes(cypher, schema):
    invalid_labels, _, invalid_props = validate_cypher(cypher, schema)
    suggestions = {}
    for prop in invalid_props:
        close = get_close_matches(prop, _all_props(schema), n=1)
        if close:
            suggestions[f".{prop}"] = f".{close[0]}"
    for label in invalid_labels:
        close = get_close_matches(label, schema["labels"], n=1)
        if close:
            suggestions[f":{label}"] = f":{close[0]}"
    if not suggestions:
        return cypher, {}
    fixed = cypher
    for old, new in suggestions.items():
        fixed = re.sub(rf"{re.escape(old)}\b", new, fixed)
    return fixed, suggestions


_CODEFENCE_LINE = re.compile(r"^\s*```.*\s*$", re.M)
_PARTIAL_OP = r"(?:CONTAINS|STARTS\s+WITH|ENDS\s+WITH)"

_RX = re.compile(
    rf"""
    (?P<lhs>\b(?:toLower\()?\s*\w+\.\w+\s*\)?)
    \s+
    (?P<op>{_PARTIAL_OP})
    \s+
    (?P<rhs>
        (?:toLower\()\s*(?P<lit1>"[^"]*"|'[^']*')\s*\)
        |
        (?P<lit2>"[^"]*"|'[^']*')
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_EQ_CI = re.compile(
    r"""
    (?P<lhs>\b(?:toLower\(\s*)?\w+\.\w+\s*\)?)
    \s*=\s*
    (?P<q>["'])
    (?P<val>[^"']*)
    (?P=q)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _wrap_tolower(term):
    t = term.strip()
    if re.match(r"^toLower\s*\(", t, re.IGNORECASE):
        return t
    return f"toLower({t})"


def _lower_literal_quotes(lit):
    q = lit[0]
    return q + lit[1:-1].lower() + q


def enforce_case_insensitive_equals(cypher):
    cypher = re.sub(r'=\s*""', '= "', cypher)
    cypher = re.sub(r"=\s*''", "= '", cypher)

    def repl(m):
        lhs = m.group("lhs")
        q, val = m.group("q"), m.group("val")
        if not re.match(r"^\s*toLower\(", lhs, re.IGNORECASE):
            lhs = f"toLower({lhs})"
        return f"{lhs} = toLower({q}{val}{q})"
    return _EQ_CI.sub(repl, cypher)


def enforce_case_insensitive_partials(cypher):
    def repl(m):
        lhs = m.group("lhs")
        op = m.group("op")
        lit1, lit2 = m.group("lit1"), m.group("lit2")
        lhs_norm = _wrap_tolower(lhs)
        if lit1 is not None:
            lit_norm = _lower_literal_quotes(lit1)
        else:
            lit_norm = _lower_literal_quotes(lit2)
        return f"{lhs_norm} {op} toLower({lit_norm})"
    return _RX.sub(repl, cypher)


def _strip_arrows(s):
    """Remove directed arrows from MATCH clauses — graph has mixed directions."""
    s = re.sub(r'\]->', ']-', s)
    s = re.sub(r'<-\[', '-[', s)
    return s


def _normalize_phase(s):
    """Fix 'phase 3' → 'phase3' etc. Phase values are stored without spaces."""
    return re.sub(
        r'(?i)(phase)\s+(\d)',
        lambda m: m.group(1).lower() + m.group(2),
        s,
    )


def sanitize_cypher(s):
    s = _CODEFENCE_LINE.sub("", s).strip()
    s = _strip_arrows(s)
    s = _normalize_phase(s)
    s = enforce_case_insensitive_equals(s)
    s = enforce_case_insensitive_partials(s)
    return s


# ---------------------------------------------------------------------------
# Prompt builder (adapted from Eng2Cypher webapp/prompts.py)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4)
def _read_md(path_str, mtime):
    return Path(path_str).read_text(encoding="utf-8").strip()


def _text(p):
    if not p or not p.exists():
        return ""
    return _read_md(str(p), p.stat().st_mtime)


def build_system_prompt(metadata):
    preferred = metadata.preferred_props

    disease_prop = preferred.get("Disease", "diseaseName").split(" or ")[0]
    gene_props = re.split(r"\s+or\s+", preferred.get("Gene", "geneSymbol"))
    gene_props = [p.strip() for p in gene_props if p.strip()]

    gene_where, gene_return = [], []
    for p in gene_props:
        gene_where.append(f'toLower(g.{p}) CONTAINS toLower("tp53")')
        gene_return.append(f"g.{p}")

    instr = _text(CACHE_DIR / "instructions.md")
    examples = (_text(CACHE_DIR / "examples.md")
                .replace("{{DISEASE_PROP}}", disease_prop)
                .replace("{{GENE_WHERE}}", " OR ".join(gene_where))
                .replace("{{GENE_RETURN}}", ", ".join(gene_return)))

    header = (
        "You are an assistant that converts natural language questions into "
        "valid Cypher queries for a cardiovascular disease knowledge graph called CardioKB.\n\n"
        "Use only these JSON specs (minified):\n"
        f"SCHEMA_JSON:{metadata.schema_json_text}\n"
        f"TOPOLOGY_JSON:{metadata.topology_json_text}\n"
        f"PREFERRED_PROPS_JSON:{metadata.preferred_props_json_text}\n"
    )
    if metadata.description_json_text:
        header += f"DESCRIPTION_JSON:{metadata.description_json_text}\n"

    return f"{header}\n{instr}\n\n{examples}\n"


# ---------------------------------------------------------------------------
# LLM call (Claude API)
# ---------------------------------------------------------------------------

def _get_anthropic_client():
    foundry_key = os.getenv("ANTHROPIC_FOUNDRY_API_KEY")
    foundry_url = os.getenv("ANTHROPIC_FOUNDRY_BASE_URL")
    if foundry_key and foundry_url:
        return anthropic.Anthropic(api_key=foundry_key, base_url=foundry_url)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        return anthropic.Anthropic(api_key=api_key)

    raise RuntimeError(
        "No Anthropic API key configured. "
        "Set ANTHROPIC_API_KEY or ANTHROPIC_FOUNDRY_API_KEY in .env"
    )


def ask_claude(system_prompt, user_input):
    client = _get_anthropic_client()
    model = os.getenv("NL2CYPHER_MODEL") or os.getenv("ANTHROPIC_FOUNDRY_MODEL") or "claude-sonnet-4-6"
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0.0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_input}],
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def nl_to_cypher(question, driver):
    metadata = get_metadata(driver)
    system_prompt = build_system_prompt(metadata)
    raw = ask_claude(system_prompt, question)
    cypher = sanitize_cypher(raw)

    invalid_labels, invalid_rels, invalid_props = validate_cypher(
        cypher, metadata.schema
    )
    fixes = {}
    warnings = []
    if invalid_labels or invalid_rels or invalid_props:
        cypher, fixes = suggest_fixes(cypher, metadata.schema)
        remaining_l, remaining_r, remaining_p = validate_cypher(
            cypher, metadata.schema
        )
        if remaining_l:
            warnings.append(f"Unknown labels: {', '.join(remaining_l)}")
        if remaining_r:
            warnings.append(f"Unknown relationships: {', '.join(remaining_r)}")
        if remaining_p:
            warnings.append(f"Unknown properties: {', '.join(remaining_p)}")

    return {
        "cypher": cypher,
        "raw_cypher": raw,
        "fixes": fixes,
        "warnings": warnings,
    }
