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
