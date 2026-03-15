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

            # Source counts from relationship properties
            source_result = session.run(
                "MATCH ()-[r]->() WHERE r.source IS NOT NULL "
                "RETURN DISTINCT r.source AS source")
            sources = sorted([r['source'] for r in source_result])

        return jsonify({
            'node_counts': node_counts,
            'rel_counts': rel_counts,
            'total_nodes': total_nodes,
            'total_relationships': total_rels,
            'node_types': len(node_counts),
            'rel_types': len(rel_counts),
            'source_count': len(sources),
            'sources': sources,
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


def main():
    import argparse
    parser = argparse.ArgumentParser(description='CardioKB Web API')
    parser.add_argument('--port', type=int, default=5050)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    print(f"\n  CardioKB Web Interface")
    print(f"  http://{args.host}:{args.port}\n")

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == '__main__':
    main()
