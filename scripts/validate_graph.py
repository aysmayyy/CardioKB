"""Full graph validation script for CardioKB."""
import os, sys
from pathlib import Path

# Load .env
for line in Path('.env').read_text().splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ[k.strip()] = v.strip()

from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USERNAME'], os.environ['NEO4J_PASSWORD'])
)

def q(cypher, **params):
    with driver.session() as s:
        return [dict(r) for r in s.run(cypher, **params)]


# ========== CHECK 1 ==========
print('=' * 60)
print('CHECK 1: Source labels in Neo4j')
print('=' * 60)

expected_sources = {
    'Bgee', 'BindingDB', 'CTD', 'ClinPGx', 'ClinVar', 'ClinicalTrials.gov',
    'DoRothEA', 'DrugAge', 'DrugBank', 'DrugCentral', 'Gene Ontology',
    'HGNC', 'HPO', 'Jensen TISSUES', 'LINCS L1000', 'MEDLINE',
    'OpenTargets', 'PubTator', 'Reactome', 'SIDER', 'STRING'
}

source_counts = q('''
    MATCH ()-[r]->()
    WHERE r.source IS NOT NULL
    RETURN r.source AS source, count(*) AS cnt
    ORDER BY cnt DESC
''')
found_sources = {row['source']: row['cnt'] for row in source_counts}

for src in sorted(expected_sources):
    cnt = found_sources.get(src, 0)
    status = 'OK' if cnt > 0 else 'MISSING'
    print(f'  {src:30s} {cnt:>12,}  {status}')

unexpected = set(found_sources.keys()) - expected_sources
if unexpected:
    print(f'  Unexpected sources: {unexpected}')

missing = expected_sources - set(found_sources.keys())
zero_count = [s for s in expected_sources if found_sources.get(s, 0) == 0]
check1 = len(missing) == 0 and len(zero_count) == 0
print(f'\nCHECK 1 RESULT: {"PASS" if check1 else "FAIL"}')
if missing:
    print(f'  Missing: {missing}')

# Node-only sources
print('\n  Node-only sources:')
node_only = {
    'Disease Ontology': 'Disease',
    'Uberon': 'BodyPart',
    'NCBI Gene': 'Gene',
    'NCBI MeSH': 'Symptom',
    'AnAge': 'Species',
}
for name, label in node_only.items():
    cnt = q(f'MATCH (n:{label}) RETURN count(n) AS c')[0]['c']
    print(f'  {name:30s} {cnt:>12,} {label} nodes  {"OK" if cnt > 0 else "MISSING"}')


# ========== CHECK 2 ==========
print('\n' + '=' * 60)
print('CHECK 2: Edge types with 0 relationships')
print('=' * 60)

edge_types = q('MATCH ()-[r]->() RETURN DISTINCT type(r) AS rt')
zero_edges = []
for row in edge_types:
    rt = row['rt']
    cnt = q('MATCH ()-[r]->() WHERE type(r) = $rt RETURN count(r) AS cnt', rt=rt)[0]['cnt']
    status = 'OK' if cnt > 0 else 'ZERO'
    if cnt == 0:
        zero_edges.append(rt)
    print(f'  {rt:50s} {cnt:>12,}  {status}')

check2 = len(zero_edges) == 0
print(f'\nCHECK 2 RESULT: {"PASS" if check2 else "FAIL"}')
if zero_edges:
    print(f'  Zero-count edge types: {zero_edges}')


# ========== CHECK 3 ==========
print('\n' + '=' * 60)
print('CHECK 3: Spot check 5 random disease nodes for connections')
print('=' * 60)

# Pick 5 random CVD-relevant diseases (ones likely to have connections)
diseases = q('''
    MATCH (d:Disease)-[r]-()
    WITH d, count(r) AS rels
    WHERE rels > 0
    WITH d, rand() AS r
    ORDER BY r
    LIMIT 5
    RETURN d.commonName AS name, d.xrefDiseaseOntology AS did
''')

check3_pass = True
for d in diseases:
    name = d['name'] or d['did']
    did = d['did']
    print(f'\n  Disease: {name} ({did})')

    genes = q(
        'MATCH (d:Disease {xrefDiseaseOntology: $did})-[r]-(g:Gene) '
        'RETURN count(DISTINCT g) AS c, collect(DISTINCT type(r))[..3] AS types',
        did=did
    )
    drugs = q(
        'MATCH (d:Disease {xrefDiseaseOntology: $did})-[r]-(dr:Drug) '
        'RETURN count(DISTINCT dr) AS c, collect(DISTINCT type(r))[..3] AS types',
        did=did
    )
    trials = q(
        'MATCH (d:Disease {xrefDiseaseOntology: $did})-[r]-(t:ClinicalTrial) '
        'RETURN count(DISTINCT t) AS c',
        did=did
    )

    gc, gt = genes[0]['c'], genes[0]['types']
    dc, dt = drugs[0]['c'], drugs[0]['types']
    tc = trials[0]['c']

    print(f'    Genes: {gc:,} (via {gt})')
    print(f'    Drugs: {dc:,} (via {dt})')
    print(f'    ClinicalTrials: {tc:,}')

    if gc == 0 and dc == 0 and tc == 0:
        check3_pass = False
        print('    WARNING: No connections at all!')

print(f'\nCHECK 3 RESULT: {"PASS" if check3_pass else "FAIL"}')


# ========== CHECK 4 ==========
print('\n' + '=' * 60)
print('CHECK 4: CVD disease ontology terms present as Disease nodes')
print('=' * 60)

cvd_terms = []
for line in Path('ontology/diseases/cvd.txt').read_text().splitlines():
    line = line.strip()
    if line and not line.startswith('#'):
        cvd_terms.append(line)

print(f'  Total CVD terms in ontology: {len(cvd_terms)}')

all_names = q('MATCH (d:Disease) RETURN collect(d.commonName) AS names')
names_lower = {n.lower() for n in all_names[0]['names'] if n}

# Also check synonyms
all_syns = q('MATCH (d:Disease) WHERE d.synonyms IS NOT NULL RETURN collect(d.synonyms) AS syns')
syn_lower = set()
for s in all_syns[0].get('syns', []):
    if isinstance(s, list):
        for x in s:
            syn_lower.add(str(x).lower())
    elif s:
        syn_lower.add(str(s).lower())

found = []
not_found = []
for term in cvd_terms:
    tl = term.lower()
    if tl in names_lower or tl in syn_lower:
        found.append(term)
    else:
        not_found.append(term)

print(f'  Found as Disease nodes: {len(found)}/{len(cvd_terms)}')
print(f'  Not found: {len(not_found)}')
if not_found:
    for t in not_found[:30]:
        print(f'    - {t}')
    if len(not_found) > 30:
        print(f'    ... and {len(not_found) - 30} more')

abbrevs = [t for t in not_found if len(t) <= 5 or t.isupper()]
pct = len(found) / len(cvd_terms) * 100
check4 = pct >= 50
print(f'\n  Coverage: {pct:.1f}%')
print(f'  Abbreviations/acronyms (not expected in DOID): {len(abbrevs)}')
print(f'\nCHECK 4 RESULT: {"PASS" if check4 else "FAIL"} ({len(found)}/{len(cvd_terms)} terms matched)')


# ========== CHECK 5 ==========
print('\n' + '=' * 60)
print('CHECK 5: Orphaned node types (no relationships)')
print('=' * 60)

node_labels = q('MATCH (n) RETURN DISTINCT labels(n) AS l')
orphaned = []
for row in node_labels:
    label = row['l'][0] if row['l'] else None
    if not label:
        continue
    if label.startswith('_'):
        continue
    total_n = q(f'MATCH (n:{label}) RETURN count(n) AS total')[0]['total']
    if total_n == 0:
        continue
    connected = q(
        'MATCH (n:' + label + ')-[]-() RETURN count(n) AS c LIMIT 1'
    )[0]['c']
    status = 'OK' if connected > 0 else 'ORPHANED'
    if connected == 0:
        orphaned.append(label)
    print(f'  {label:25s} {total_n:>12,} total, {"connected" if connected > 0 else "ORPHANED":>12s}  {status}')

check5 = len(orphaned) == 0
print(f'\nCHECK 5 RESULT: {"PASS" if check5 else "FAIL"}')
if orphaned:
    print(f'  Orphaned: {orphaned}')


# ========== SUMMARY ==========
print('\n' + '=' * 60)
print('VALIDATION SUMMARY')
print('=' * 60)
checks = [
    ('Check 1: Source labels present with non-zero counts', check1),
    ('Check 2: No edge types with 0 relationships', check2),
    ('Check 3: Disease nodes connected to genes/drugs/trials', check3_pass),
    ('Check 4: CVD ontology terms present as Disease nodes', check4),
    ('Check 5: No orphaned node types', check5),
]
for name, passed in checks:
    print(f'  {"PASS" if passed else "FAIL":4s}  {name}')

overall = all(p for _, p in checks)
print(f'\nOVERALL: {"ALL PASS" if overall else "SOME FAILURES"}')

driver.close()
