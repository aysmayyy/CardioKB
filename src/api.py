"""
CardioKB Web API

Flask backend that serves the web interface and streams pipeline health
check progress via Server-Sent Events (SSE).

Usage:
    python src/api.py
    python src/api.py --port 5050
"""

import json
import os
import queue
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.orchestrator import (
    DISEASE_FILTERS,
    EXPECTED_PARSERS,
    run_health_check,
)

load_dotenv()

app = Flask(__name__,
            static_folder=str(Path(_project_root) / 'interface'),
            static_url_path='')


def _get_neo4j_driver():
    """Create a Neo4j driver from environment variables."""
    from neo4j import GraphDatabase
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', '')
    if not password:
        return None
    return GraphDatabase.driver(uri, auth=(username, password))


@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/api/diseases')
def list_diseases():
    """Return available disease filters."""
    from src.utils import load_disease_terms
    diseases = []
    for key, path in DISEASE_FILTERS.items():
        abs_path = Path(_project_root) / path
        try:
            terms = load_disease_terms(str(abs_path))
            count = len(terms)
        except Exception:
            count = 0
        diseases.append({'key': key, 'label': key.replace('_', ' ').title(),
                         'term_count': count})
    return jsonify(diseases)


@app.route('/api/parsers')
def list_parsers():
    """Return expected parser list."""
    return jsonify(EXPECTED_PARSERS)


@app.route('/api/graph-stats')
def graph_stats():
    """Query Neo4j for current graph statistics."""
    driver = _get_neo4j_driver()
    if not driver:
        return jsonify({'error': 'NEO4J_PASSWORD not set'}), 503

    try:
        with driver.session(database='neo4j') as session:
            # Node counts by label
            node_counts = {}
            total_nodes = 0
            labels = [r['label'] for r in session.run(
                "CALL db.labels() YIELD label RETURN label")]
            for label in sorted(labels):
                cnt = session.run(
                    f"MATCH (n:{label}) RETURN count(n) AS cnt"
                ).single()['cnt']
                node_counts[label] = cnt
                total_nodes += cnt

            # Relationship counts by type
            rel_counts = {}
            total_rels = 0
            rel_types = [r['relationshipType'] for r in session.run(
                "CALL db.relationshipTypes() YIELD relationshipType "
                "RETURN relationshipType")]
            for rt in sorted(rel_types):
                cnt = session.run(
                    f"MATCH ()-[r:`{rt}`]->() RETURN count(r) AS cnt"
                ).single()['cnt']
                rel_counts[rt] = cnt
                total_rels += cnt

            # Source counts from relationship properties (with per-source edge counts)
            source_result = session.run(
                "MATCH ()-[r]->() WHERE r.source IS NOT NULL "
                "RETURN r.source AS source, count(r) AS cnt "
                "ORDER BY source")
            source_counts = {}
            sources = []
            for r in source_result:
                sources.append(r['source'])
                source_counts[r['source']] = r['cnt']

        return jsonify({
            'node_counts': node_counts,
            'rel_counts': rel_counts,
            'total_nodes': total_nodes,
            'total_relationships': total_rels,
            'node_types': len(node_counts),
            'rel_types': len(rel_counts),
            'source_count': len(sources),
            'sources': sources,
            'source_edge_counts': source_counts,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        driver.close()


@app.route('/api/disease-stats')
def disease_stats():
    """Query Neo4j for disease subgraph statistics.

    Query params:
        disease: Disease key (default: cvd)
    """
    from src.utils import load_disease_terms

    disease = request.args.get('disease', 'cvd')
    if disease not in DISEASE_FILTERS:
        disease = 'cvd'

    abs_path = str(Path(_project_root) / DISEASE_FILTERS[disease])
    try:
        terms = load_disease_terms(abs_path)
    except Exception as e:
        return jsonify({'error': f'Failed to load disease terms: {e}'}), 500

    driver = _get_neo4j_driver()
    if not driver:
        return jsonify({'error': 'NEO4J_PASSWORD not set'}), 503

    try:
        with driver.session(database='neo4j') as session:
            # Find Disease nodes matching the filter terms
            term_list = list(terms)
            disease_nodes = session.run(
                "MATCH (d:Disease) "
                "WHERE any(term IN $terms WHERE toLower(d.commonName) CONTAINS term) "
                "RETURN d.commonName AS name, d.xrefDiseaseOntology AS doid",
                terms=term_list,
            )
            diseases_found = []
            doids = []
            for rec in disease_nodes:
                diseases_found.append(rec['name'])
                if rec['doid']:
                    doids.append(rec['doid'])

            # Get neighbor counts by label and relationship type
            node_breakdown = {}
            rel_breakdown = {}
            total_neighbors = 0

            if doids:
                neighbors = session.run(
                    "MATCH (d:Disease)-[r]-(n) "
                    "WHERE d.xrefDiseaseOntology IN $doids "
                    "RETURN labels(n)[0] AS label, type(r) AS rel_type, "
                    "count(*) AS cnt",
                    doids=doids,
                )
                for row in neighbors:
                    label = row['label']
                    rel_type = row['rel_type']
                    cnt = row['cnt']
                    node_breakdown[label] = node_breakdown.get(label, 0) + cnt
                    rel_breakdown[rel_type] = rel_breakdown.get(rel_type, 0) + cnt
                    total_neighbors += cnt

        return jsonify({
            'disease': disease,
            'diseases_matched': len(diseases_found),
            'node_breakdown': node_breakdown,
            'rel_breakdown': rel_breakdown,
            'total_neighbors': total_neighbors,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        driver.close()


@app.route('/api/agent/build', methods=['POST'])
def agent_build_sse():
    """
    Run the disease agent and stream progress as Server-Sent Events.

    Request body (JSON):
        disease: Disease name to process (e.g., "parkinson's disease", "PD")

    SSE events:
        status  — progress updates with phase and message
        result  — final result dict
        error   — error message
    """
    body = request.get_json(silent=True) or {}
    disease = (body.get('disease') or '').strip()
    if not disease:
        return jsonify({'error': 'Missing "disease" field'}), 400

    q = queue.Queue()

    def on_progress(event: str, data: dict):
        q.put((event, data))

    def run():
        try:
            from src.agent import run_agent
            result = run_agent(disease, on_progress=on_progress)
            q.put(('result', result))
        except Exception as e:
            q.put(('error', {'message': str(e)}))
        finally:
            q.put(None)  # sentinel

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    def generate():
        while True:
            item = q.get()
            if item is None:
                break
            event, data = item
            payload = json.dumps(data, default=str)
            yield f"event: {event}\ndata: {payload}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


@app.route('/api/graph')
def graph_data():
    """Return a two-layer disease subgraph for vis.js visualization.

    Core layer: direct neighbors of seed diseases, ranked by pre-computed
    specificityScore (top-N most disease-specific per type).

    Discovery layer: 2-hop neighbors of core nodes, also ranked by
    specificityScore, filling remaining budget.

    Reads n.specificityScore (pre-computed by scripts/compute_specificity.py)
    instead of counting Disease neighbors at query time.

    Query params:
        disease: Disease key (default: cvd)
        search: Optional free-text search term (e.g. "atrial fibrillation")
        limit: Max total nodes (default: 200, max 1000)
    """
    from src.utils import load_disease_terms

    disease = request.args.get('disease', 'cvd')
    if disease not in DISEASE_FILTERS:
        disease = 'cvd'
    search = request.args.get('search', '').strip()
    limit = min(int(request.args.get('limit', 200)), 1000)

    # If a search term is provided, use it directly; otherwise use the
    # disease filter file terms
    if search:
        term_list = [search.lower()]
    else:
        abs_path = str(Path(_project_root) / DISEASE_FILTERS[disease])
        try:
            terms = load_disease_terms(abs_path)
        except Exception as e:
            return jsonify({'error': f'Failed to load disease terms: {e}'}), 500
        term_list = list(terms)

    driver = _get_neo4j_driver()
    if not driver:
        return jsonify({'error': 'NEO4J_PASSWORD not set'}), 503

    try:
        with driver.session(database='neo4j') as session:

            nodes = {}
            edges = []
            core_nids = set()

            # --- Seed diseases (layer=core) ---
            seed_result = session.run(
                "MATCH (d:Disease)--() "
                "WHERE any(term IN $terms WHERE toLower(d.commonName) CONTAINS term) "
                "RETURN DISTINCT elementId(d) AS did, d.commonName AS name, "
                "       d.xrefDiseaseOntology AS doid "
                "LIMIT 10",
                terms=term_list,
            )
            seed_ids = []
            for rec in seed_result:
                seed_ids.append(rec['did'])
                nodes[rec['did']] = {
                    'id': rec['did'],
                    'label': rec['name'] or rec['did'],
                    'type': 'Disease',
                    'layer': 'core',
                    'properties': {
                        'commonName': rec['name'],
                        'xrefDiseaseOntology': rec['doid'],
                    },
                }

            # --- Core layer: per-seed neighbors ranked by specificityScore ---
            # Process each seed disease individually to avoid OOM on broad
            # terms like "asthma" that match many high-degree disease nodes.
            core_per_type = max(limit // 4, 20)
            # Hard cap on rows per seed to keep Neo4j memory bounded
            fetch_cap = core_per_type * 10

            for sid in seed_ids:
                core_result = session.run(
                    "MATCH (d)-[r]-(n) "
                    "WHERE elementId(d) = $did "
                    "WITH d, r, n LIMIT $fetch "
                    "WITH d, r, n, labels(n)[0] AS ntype, "
                    "     coalesce(n.specificityScore, 0.0) AS spec "
                    "ORDER BY ntype, spec DESC "
                    "WITH ntype, collect({d: d, r: r, n: n, spec: spec})[..$cap] AS bucket "
                    "UNWIND bucket AS b "
                    "WITH b.d AS d, b.r AS r, b.n AS n, b.spec AS spec "
                    "RETURN d.commonName AS d_name, "
                    "       d.xrefDiseaseOntology AS d_id, "
                    "       type(r) AS rel_type, r.source AS source, "
                    "       labels(n)[0] AS n_label, "
                    "       properties(n) AS n_props, "
                    "       elementId(d) AS did, elementId(n) AS nid, "
                    "       spec",
                    did=sid,
                    fetch=fetch_cap,
                    cap=core_per_type,
                )

                for row in core_result:
                    did = row['did']
                    nid = row['nid']

                    if did not in nodes:
                        nodes[did] = {
                            'id': did,
                            'label': row['d_name'] or did,
                            'type': 'Disease',
                            'layer': 'core',
                            'properties': {
                                'commonName': row['d_name'],
                                'xrefDiseaseOntology': row['d_id'],
                            },
                        }

                    if nid not in nodes:
                        props = dict(row['n_props']) if row['n_props'] else {}
                        display = (props.get('commonName') or props.get('name')
                                   or props.get('symbol') or props.get('title')
                                   or props.get('nctId') or nid)
                        nodes[nid] = {
                            'id': nid,
                            'label': str(display)[:60],
                            'type': row['n_label'],
                            'layer': 'core',
                            'specificity': round(row['spec'], 6),
                            'properties': {k: str(v)[:200] for k, v in props.items()
                                           if v is not None},
                        }

                    edges.append({
                        'from': did,
                        'to': nid,
                        'label': row['rel_type'],
                        'source': row['source'],
                        'layer': 'core',
                    })
                    core_nids.add(nid)

            # --- Discovery layer: per-core-node, ranked by specificityScore ---
            # Process in small batches to stay within memory limits.
            discovery_budget = limit - len(nodes)
            if core_nids and discovery_budget > 0:
                disc_per_type = max(discovery_budget // 8, 5)
                disc_fetch = disc_per_type * 10
                exclude_ids = list(core_nids | set(nodes.keys()))

                # Process core nodes in batches of 20
                core_list = list(core_nids)
                batch_size = 20
                for i in range(0, len(core_list), batch_size):
                    batch = core_list[i:i + batch_size]
                    disc_result = session.run(
                        "MATCH (n1)-[r]-(n2) "
                        "WHERE elementId(n1) IN $nids "
                        "AND NOT elementId(n2) IN $exclude "
                        "WITH n1, r, n2 LIMIT $fetch "
                        "WITH n1, r, n2, labels(n2)[0] AS n2type, "
                        "     coalesce(n2.specificityScore, 0.0) AS spec "
                        "ORDER BY n2type, spec DESC "
                        "WITH n2type, collect({n1: n1, r: r, n2: n2, "
                        "     spec: spec})[..$cap] AS bucket "
                        "UNWIND bucket AS b "
                        "WITH b.n1 AS n1, b.r AS r, b.n2 AS n2, b.spec AS spec "
                        "RETURN elementId(n1) AS from_id, "
                        "       type(r) AS rel_type, r.source AS source, "
                        "       labels(n2)[0] AS n_label, "
                        "       properties(n2) AS n_props, "
                        "       elementId(n2) AS nid, "
                        "       spec",
                        nids=batch,
                        exclude=exclude_ids,
                        fetch=disc_fetch,
                        cap=disc_per_type,
                    )

                    for row in disc_result:
                        nid = row['nid']
                        if nid not in nodes:
                            props = dict(row['n_props']) if row['n_props'] else {}
                            display = (props.get('commonName') or props.get('name')
                                       or props.get('symbol') or props.get('title')
                                       or props.get('nctId') or nid)
                            nodes[nid] = {
                                'id': nid,
                                'label': str(display)[:60],
                                'type': row['n_label'],
                                'layer': 'discovery',
                                'specificity': round(row['spec'], 6),
                                'properties': {k: str(v)[:200] for k, v in props.items()
                                               if v is not None},
                            }
                        edges.append({
                            'from': row['from_id'],
                            'to': nid,
                            'label': row['rel_type'],
                            'source': row['source'],
                            'layer': 'discovery',
                        })

                    if len(nodes) >= limit:
                        break

        return jsonify({
            'nodes': list(nodes.values()),
            'edges': edges,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        driver.close()


@app.route('/api/specificity-info')
def specificity_info():
    """Return metadata about when specificity scores were last computed."""
    from neo4j import GraphDatabase

    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    pwd = os.getenv('NEO4J_PASSWORD', '')
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    try:
        with driver.session(database='neo4j') as session:
            result = session.run(
                "MATCH (m:_Metadata {key: 'specificityScoreComputed'}) "
                "RETURN m.timestamp AS ts, m.totalNodes AS total"
            )
            row = result.single()
            if row:
                return jsonify(timestamp=row['ts'], totalNodes=row['total'])
            return jsonify(timestamp=None, totalNodes=None)
    finally:
        driver.close()


@app.route('/api/id-mapping-report')
def id_mapping_report():
    """Return cached ID mapping validation report.

    The report is generated during pipeline runs and saved to
    reports/id_mapping_report.json. This endpoint reads and returns it.
    """
    report_path = Path(_project_root) / 'reports' / 'id_mapping_report.json'
    if not report_path.exists():
        return jsonify({
            'error': 'No report available. Run the pipeline first to generate the ID mapping report.',
        }), 404

    try:
        with open(report_path) as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/query', methods=['POST'])
def run_query():
    """Execute a Cypher query and return results as JSON.

    Request body (JSON):
        query: Cypher query string

    Returns nodes/edges if the query returns graph patterns,
    otherwise returns tabular rows.
    """
    body = request.get_json(silent=True) or {}
    cypher = (body.get('query') or '').strip()
    if not cypher:
        return jsonify({'error': 'Missing "query" field'}), 400

    # Block write operations
    upper = cypher.upper()
    blocked = ['CREATE', 'MERGE', 'DELETE', 'DETACH', 'SET ', 'REMOVE ',
               'DROP ', 'CALL {', 'FOREACH']
    for kw in blocked:
        if kw in upper:
            return jsonify({'error': f'Write operations are not allowed ({kw.strip()})'}), 403

    driver = _get_neo4j_driver()
    if not driver:
        return jsonify({'error': 'NEO4J_PASSWORD not set'}), 503

    try:
        with driver.session(database='neo4j') as session:
            result = session.run(cypher)
            keys = result.keys()
            rows = []
            nodes = {}
            edges = []

            for record in result:
                row = {}
                for key in keys:
                    val = record[key]
                    # Check for Node objects
                    if hasattr(val, 'labels'):
                        node_id = str(val.id)
                        props = dict(val)
                        display = (props.get('commonName') or props.get('name')
                                   or props.get('symbol') or props.get('title')
                                   or node_id)
                        if node_id not in nodes:
                            nodes[node_id] = {
                                'id': node_id,
                                'label': str(display)[:60],
                                'type': list(val.labels)[0] if val.labels else 'Unknown',
                                'properties': {k: str(v)[:200] for k, v in props.items()
                                               if v is not None},
                            }
                        row[key] = str(display)
                    elif hasattr(val, 'type'):
                        # Relationship
                        edges.append({
                            'from': str(val.start_node.id) if hasattr(val, 'start_node') else '',
                            'to': str(val.end_node.id) if hasattr(val, 'end_node') else '',
                            'label': val.type,
                            'source': dict(val).get('source', ''),
                        })
                        row[key] = val.type
                    else:
                        row[key] = val if isinstance(val, (str, int, float, bool, type(None))) else str(val)
                rows.append(row)

        return jsonify({
            'columns': list(keys),
            'rows': rows[:500],
            'nodes': list(nodes.values()),
            'edges': edges,
            'row_count': len(rows),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        driver.close()


@app.route('/api/admin/verify', methods=['POST'])
def admin_verify():
    """Verify the admin password."""
    body = request.get_json(silent=True) or {}
    password = (body.get('password') or '').strip()
    admin_pw = os.getenv('ADMIN_PASSWORD', '')
    if not admin_pw:
        return jsonify({'error': 'ADMIN_PASSWORD not configured on server'}), 503
    if password == admin_pw:
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Invalid password'}), 403


@app.route('/api/agent/add-database', methods=['POST'])
def agent_add_database():
    """Add a new database source via the agent.

    Request body (JSON):
        name: Database name
        url: Database URL
        password: Admin password
    """
    body = request.get_json(silent=True) or {}
    admin_pw = os.getenv('ADMIN_PASSWORD', '')
    if not admin_pw or (body.get('password') or '') != admin_pw:
        return jsonify({'error': 'Unauthorized'}), 403

    name = (body.get('name') or '').strip()
    url = (body.get('url') or '').strip()
    if not name or not url:
        return jsonify({'error': 'Missing "name" and/or "url" fields'}), 400

    q = queue.Queue()

    def on_progress(event, data):
        q.put((event, data))

    def run():
        try:
            from src.agent import run_agent
            result = run_agent(f"Add database: {name} from {url}",
                               on_progress=on_progress)
            q.put(('result', result))
        except Exception as e:
            q.put(('error', {'message': str(e)}))
        finally:
            q.put(None)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    def generate():
        while True:
            item = q.get()
            if item is None:
                break
            event, data = item
            payload = json.dumps(data, default=str)
            yield f"event: {event}\ndata: {payload}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


@app.route('/api/pipeline/run', methods=['POST'])
def pipeline_run_sse():
    """Run the full pipeline and stream progress as SSE.

    Request body (JSON):
        password: Admin password
    """
    body = request.get_json(silent=True) or {}
    admin_pw = os.getenv('ADMIN_PASSWORD', '')
    if not admin_pw or (body.get('password') or '') != admin_pw:
        return jsonify({'error': 'Unauthorized'}), 403

    q = queue.Queue()

    def run():
        import subprocess
        try:
            q.put(('status', {'message': 'Starting pipeline (python src/main.py)...'}))
            proc = subprocess.Popen(
                ['python', 'src/main.py'],
                cwd=_project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                line = line.rstrip('\n')
                if line:
                    q.put(('log', {'message': line}))
            proc.wait()
            if proc.returncode == 0:
                q.put(('status', {'message': 'Pipeline completed successfully.'}))
            else:
                q.put(('error', {'message': f'Pipeline exited with code {proc.returncode}'}))
        except Exception as e:
            q.put(('error', {'message': str(e)}))
        finally:
            q.put(None)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    def generate():
        while True:
            item = q.get()
            if item is None:
                break
            event, data = item
            payload = json.dumps(data, default=str)
            yield f"event: {event}\ndata: {payload}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


@app.route('/api/health-check')
def health_check_sse():
    """
    Stream health check progress as Server-Sent Events.

    Query params:
        disease: Disease key (default: cvd)
    """
    disease = request.args.get('disease', 'cvd')
    if disease not in DISEASE_FILTERS:
        disease = 'cvd'

    q = queue.Queue()

    def on_progress(event: str, data: dict):
        q.put((event, data))

    def run():
        try:
            run_health_check(
                disease=disease,
                log_file='cardiokb_build.log',
                on_progress=on_progress,
            )
        except Exception as e:
            q.put(('error', {'message': str(e)}))
        finally:
            q.put(None)  # sentinel

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    def generate():
        while True:
            item = q.get()
            if item is None:
                break
            event, data = item
            # Serialize datetimes
            payload = json.dumps(data, default=str)
            yield f"event: {event}\ndata: {payload}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


def _reload_unloaded_parsers():
    """
    Startup check: for every parser that has TSV files in data/processed/
    but 0 nodes/edges in Neo4j, reload from TSVs automatically.
    """
    import logging as _logging
    import pandas as pd
    from neo4j import GraphDatabase
    from src.ontology_configs import ONTOLOGY_CONFIGS
    from src.neo4j_loader import Neo4jLoader
    from src.orchestrator import _build_parser_metadata

    log = _logging.getLogger('cardiokb.startup')

    password = os.getenv('NEO4J_PASSWORD', '')
    if not password:
        return

    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')

    proc_dir = Path(_project_root) / 'data' / 'processed'
    meta = _build_parser_metadata()

    # Query Neo4j for current per-parser counts
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session(database='neo4j') as session:
            # Relationship counts by source
            source_counts = {}
            for rec in session.run(
                "MATCH ()-[r]->() WHERE r.source IS NOT NULL "
                "RETURN r.source AS source, count(r) AS cnt"
            ):
                source_counts[rec['source']] = rec['cnt']

            # Node counts by label
            node_counts = {}
            for rec in session.run("CALL db.labels() YIELD label RETURN label"):
                label = rec['label']
                cnt = session.run(
                    f"MATCH (n:`{label}`) RETURN count(n) AS cnt"
                ).single()['cnt']
                node_counts[label] = cnt
    finally:
        driver.close()

    # Find parsers with TSVs on disk but 0 in Neo4j
    to_reload = []
    for parser_name, pmeta in meta.items():
        rel_count = sum(source_counts.get(s, 0) for s in pmeta['source_labels'])
        ncount = sum(node_counts.get(nt, 0) for nt in pmeta['node_types'])

        if rel_count > 0 or ncount > 0:
            continue  # already loaded

        # Check if processed TSVs exist
        src_dir = proc_dir / parser_name
        if src_dir.is_dir() and any(src_dir.glob('*.tsv')):
            to_reload.append(parser_name)

    if not to_reload:
        return

    log.info(f"Auto-reloading {len(to_reload)} parser(s) with TSVs but 0 in Neo4j: {to_reload}")

    # Build parsed_data from TSVs and load via Neo4jLoader
    parsed_data = {}
    for parser_name in to_reload:
        src_dir = proc_dir / parser_name
        tsv_data = {}
        for tsv_path in src_dir.glob('*.tsv'):
            try:
                df = pd.read_csv(tsv_path, sep='\t')
                if len(df) > 0:
                    tsv_data[tsv_path.stem] = df
            except Exception as e:
                log.warning(f"  Failed to read {tsv_path}: {e}")
        if tsv_data:
            parsed_data[parser_name] = tsv_data
            log.info(f"  {parser_name}: {len(tsv_data)} TSV file(s)")

    if not parsed_data:
        return

    try:
        with Neo4jLoader(uri, username, password) as loader:
            loader.load_from_configs(parsed_data, ONTOLOGY_CONFIGS, proc_dir)
            stats = loader.get_stats()
            log.info(
                f"Startup reload complete: "
                f"{stats['nodes_created']} nodes created, "
                f"{stats['nodes_merged']} merged, "
                f"{stats['relationships_merged']} relationships"
            )
    except Exception as e:
        log.error(f"Startup reload failed: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='CardioKB Web API')
    parser.add_argument('--port', type=int, default=5050)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    # Auto-reload parsers that have TSVs but 0 data in Neo4j
    try:
        _reload_unloaded_parsers()
    except Exception as e:
        print(f"  Warning: startup reload check failed: {e}")

    print(f"\n  CardioKB Web Interface")
    print(f"  http://{args.host}:{args.port}\n")

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == '__main__':
    main()
