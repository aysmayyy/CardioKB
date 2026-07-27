from neo4j import GraphDatabase
import os, re
from dotenv import load_dotenv
load_dotenv()
driver = GraphDatabase.driver(os.getenv('MEMGRAPH_URI'), auth=(os.getenv('MEMGRAPH_USERNAME',''), os.getenv('MEMGRAPH_PASSWORD','')))

with driver.session() as s:
    r = s.run('MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY cnt DESC')
    live_nodes = {rec['label']: rec['cnt'] for rec in r}
    r2 = s.run('MATCH (a)-[r]->(b) RETURN DISTINCT type(r) AS rt, labels(a)[0] AS src, labels(b)[0] AS tgt ORDER BY rt')
    live_edges = [(rec['rt'], rec['src'], rec['tgt']) for rec in r2]
driver.close()

with open('/Users/nawaza/Desktop/Cardio-KB/docs/cardiokb_schema.drawio') as f:
    content = f.read()

node_pattern = re.compile(r'id="(\w+)"[^>]*value="([^"]+)"[^>]*vertex="1"')
drawio_nodes = {}
skip_ids = {'legend_box', 'legend_title', 'leg1l', 'leg2l', 'leg3l', 'leg4l', 'leg5l', 'leg6l'}
for m in node_pattern.finditer(content):
    nid, val = m.group(1), m.group(2)
    if nid in skip_ids or not val.strip():
        continue
    match = re.match(r'(.+?)\s*\(([0-9,]+)\)', val)
    if match:
        drawio_nodes[nid] = (match.group(1).strip(), int(match.group(2).replace(',', '')))

edge_pattern = re.compile(r'value="([^"]+)"[^>]*edge="1"[^>]*source="(\w+)"[^>]*target="(\w+)"')
drawio_edges = []
for m in edge_pattern.finditer(content):
    val, src, tgt = m.group(1), m.group(2), m.group(3)
    if src.startswith('leg') or not val.strip():
        continue
    drawio_edges.append((val.replace(' (ML)', ''), src, tgt))

label_map = {
    'gene': 'Gene', 'disease': 'Disease', 'drug': 'Drug', 'variant': 'Variant',
    'pathway': 'Pathway', 'bp': 'BiologicalProcess', 'mf': 'MolecularFunction',
    'cc': 'CellularComponent', 'bodypart': 'BodyPart', 'ct': 'ClinicalTrial',
    'tf': 'TranscriptionFactor', 'phenotype': 'Phenotype', 'se': 'SideEffect',
    'symptom': 'Symptom', 'gf': 'GeneFamily', 'pc': 'PharmacologicClass', 'dl': 'DrugLabel'
}

print('=' * 60)
print('NODE COUNT VERIFICATION')
print('=' * 60)
for nid, (name, count) in sorted(drawio_nodes.items(), key=lambda x: -x[1][1]):
    label = label_map.get(nid, name)
    live_count = live_nodes.get(label, 'MISSING')
    ok = '  OK' if live_count == count else '  *** MISMATCH ***'
    print(f'  {label:25s}  drawio={count:>10,}  live={str(live_count):>10s}{ok}')

drawio_labels = {label_map.get(nid, name) for nid, (name, _) in drawio_nodes.items()}
for label in sorted(live_nodes):
    if label not in drawio_labels and label != '_Metadata':
        print(f'  {label:25s}  *** MISSING FROM DRAWIO ***  live={live_nodes[label]:,}')

print(f'\n  Drawio node types: {len(drawio_nodes)}')
print(f'  Live node types:   {len(live_nodes)}')

print()
print('=' * 60)
print('EDGE TYPE VERIFICATION')
print('=' * 60)

drawio_edge_labels = set()
for val, src_id, tgt_id in drawio_edges:
    drawio_edge_labels.add((val, label_map.get(src_id, src_id), label_map.get(tgt_id, tgt_id)))

live_edge_set = set(live_edges)

print('\n  Drawio edges vs live graph:')
for val, src, tgt in sorted(drawio_edge_labels):
    ok = '  OK' if (val, src, tgt) in live_edge_set else '  *** NOT IN LIVE GRAPH ***'
    print(f'    {src} --[{val}]--> {tgt}{ok}')

print('\n  Live graph edges vs drawio:')
for rt, src, tgt in sorted(live_edge_set):
    ok = '  OK' if (rt, src, tgt) in drawio_edge_labels else '  *** MISSING FROM DRAWIO ***'
    print(f'    {src} --[{rt}]--> {tgt}{ok}')

print(f'\n  Drawio edge types: {len(drawio_edge_labels)}')
print(f'  Live edge types:   {len(live_edge_set)}')
