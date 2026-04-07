"""
CardioKB Pipeline Orchestrator

Runs pipeline health checks against the Memgraph database and the latest build log,
then generates a self-contained HTML report at reports/pipeline_report.html.

Can also stream progress events for the web interface via a callback.

Usage:
    python src/orchestrator.py
    python src/orchestrator.py --log-file logs/cardiokb_build.log
    python src/orchestrator.py --output reports/pipeline_report.html
    python src/orchestrator.py --disease alzheimers
"""

import os
import re
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from dotenv import load_dotenv

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logger = logging.getLogger(__name__)


def _build_parser_metadata() -> Dict:
    """Auto-derive parser metadata from ONTOLOGY_CONFIGS.

    Returns dict keyed by parser name with:
        source_labels: list of r.source values this parser writes
        node_types: list of node labels this parser creates
        source_filenames: list of TSV filenames from configs

    Always reloads ontology_configs so back-to-back agent runs in the
    same Flask process pick up newly added configs.
    """
    import importlib
    import src.ontology_configs as _oc_mod
    importlib.reload(_oc_mod)
    ONTOLOGY_CONFIGS = _oc_mod.ONTOLOGY_CONFIGS

    meta: Dict = {}
    active_parsers: set = set()  # parsers with at least one non-skipped config
    for key, cfg in ONTOLOGY_CONFIGS.items():
        parser = key.split('.')[0]
        if parser not in meta:
            meta[parser] = {
                'source_labels': set(),
                'node_types': set(),
                'source_filenames': [],
            }
        # Only count source_labels and node_types from non-skipped configs
        if not cfg.get('skip'):
            active_parsers.add(parser)
            source = cfg.get('source_label')
            if source:
                meta[parser]['source_labels'].add(source)
            if cfg.get('data_type') == 'node':
                nt = cfg.get('node_type')
                if nt:
                    meta[parser]['node_types'].add(nt)
        sf = cfg.get('source_filename')
        if sf:
            meta[parser]['source_filenames'].append(sf)

    # Remove parsers where ALL configs are skip: True (removed sources)
    meta = {p: v for p, v in meta.items() if p in active_parsers}

    for p in meta:
        meta[p]['source_labels'] = sorted(meta[p]['source_labels'])
        meta[p]['node_types'] = sorted(meta[p]['node_types'])

    return meta


def _get_expected_parsers():
    """Return the current list of expected parsers (always fresh)."""
    return sorted(_build_parser_metadata().keys())

# Map short disease names to filter files
DISEASE_FILTERS = {
    'cvd': 'ontology/diseases/cvd.txt',
    'alzheimers': 'ontology/diseases/alzheimers.txt',
    'cancer': 'ontology/diseases/cancer.txt',
    'asthma': 'ontology/diseases/asthma.txt',
    'diabetes': 'ontology/diseases/diabetes.txt',
}


def resolve_disease_filter(disease: str = 'cvd') -> str:
    """Resolve a disease name or path to an absolute filter file path."""
    if disease in DISEASE_FILTERS:
        rel_path = DISEASE_FILTERS[disease]
    else:
        rel_path = disease
    path = Path(rel_path)
    if not path.is_absolute():
        path = Path(_project_root) / path
    return str(path)


def parse_build_log(log_path: str) -> Dict:
    """Parse the build log to extract parser results and timing."""
    results = {
        'parsers': {},
        'pipeline_start': None,
        'pipeline_end': None,
        'pipeline_duration': None,
        'sources_processed': 0,
        'sources_failed': 0,
    }

    if not os.path.exists(log_path):
        logger.warning(f"Build log not found: {log_path}")
        return results

    with open(log_path) as f:
        lines = f.readlines()

    # Find the latest pipeline run by scanning backwards for the last
    # "CardioKB - Complete Pipeline" header
    run_start_idx = 0
    for i in range(len(lines) - 1, -1, -1):
        if 'CardioKB - Complete Pipeline' in lines[i]:
            run_start_idx = i
            break

    lines = lines[run_start_idx:]

    ts_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})')
    processing_pattern = re.compile(r'Processing (\w+)')
    success_pattern = re.compile(r'Successfully processed (\w+)')
    no_data_pattern = re.compile(r'No data parsed for (\w+)')
    failed_pattern = re.compile(r'Failed to process (\w+)')
    duration_pattern = re.compile(r'Duration: (.+)')
    processed_pattern = re.compile(r'Sources processed: (\d+)')
    failed_count_pattern = re.compile(r'Sources failed: (\d+)')
    loaded_tsv_pattern = re.compile(r'Loaded (\w+) from cached TSVs')
    loaded_fallback_pattern = re.compile(r'Loaded (\w+)/\w+ from TSV fallback')

    current_parser = None
    parser_start_time = None

    for line in lines:
        ts_match = ts_pattern.match(line)
        timestamp = None
        if ts_match:
            try:
                timestamp = datetime.strptime(ts_match.group(1), '%Y-%m-%d %H:%M:%S,%f')
            except ValueError:
                pass

        if 'Start time:' in line and results['pipeline_start'] is None:
            results['pipeline_start'] = timestamp

        if 'Pipeline Completed Successfully' in line:
            results['pipeline_end'] = timestamp

        m = processing_pattern.search(line)
        if m:
            name = m.group(1).lower()
            current_parser = name
            parser_start_time = timestamp
            if name not in results['parsers']:
                results['parsers'][name] = {
                    'status': 'running',
                    'start_time': timestamp,
                    'end_time': None,
                    'duration_sec': None,
                }

        m = success_pattern.search(line)
        if m:
            name = m.group(1).lower()
            if name in results['parsers']:
                results['parsers'][name]['status'] = 'success'
                results['parsers'][name]['end_time'] = timestamp
                if results['parsers'][name]['start_time'] and timestamp:
                    delta = timestamp - results['parsers'][name]['start_time']
                    results['parsers'][name]['duration_sec'] = delta.total_seconds()

        m = loaded_tsv_pattern.search(line)
        if m:
            name = m.group(1).lower()
            if name in results['parsers']:
                results['parsers'][name]['status'] = 'success (cached TSV)'
                results['parsers'][name]['end_time'] = timestamp
                if results['parsers'][name]['start_time'] and timestamp:
                    delta = timestamp - results['parsers'][name]['start_time']
                    results['parsers'][name]['duration_sec'] = delta.total_seconds()

        m = loaded_fallback_pattern.search(line)
        if m:
            name = m.group(1).lower()
            if name not in results['parsers']:
                results['parsers'][name] = {
                    'status': 'success (TSV fallback)',
                    'start_time': None,
                    'end_time': timestamp,
                    'duration_sec': None,
                }
            else:
                results['parsers'][name]['status'] = 'success (TSV fallback)'

        m = no_data_pattern.search(line)
        if m:
            name = m.group(1).lower()
            if name in results['parsers']:
                results['parsers'][name]['status'] = 'no data'
                results['parsers'][name]['end_time'] = timestamp
                if results['parsers'][name]['start_time'] and timestamp:
                    delta = timestamp - results['parsers'][name]['start_time']
                    results['parsers'][name]['duration_sec'] = delta.total_seconds()

        m = failed_pattern.search(line)
        if m:
            name = m.group(1).lower()
            if name in results['parsers']:
                results['parsers'][name]['status'] = 'failed'
                results['parsers'][name]['end_time'] = timestamp

        m = duration_pattern.search(line)
        if m:
            results['pipeline_duration'] = m.group(1)

        m = processed_pattern.search(line)
        if m:
            results['sources_processed'] = int(m.group(1))

        m = failed_count_pattern.search(line)
        if m:
            results['sources_failed'] = int(m.group(1))

    return results


def _query_parser_status(session, project_root: str) -> Dict:
    """Query graph database for per-parser status, falling back to file system checks.

    For each parser derived from ONTOLOGY_CONFIGS:
      - If r.source count > 0 or unique node count > 0 → 'success' with counts
      - Elif raw/processed data files exist → 'parsed but not loaded'
      - Else → 'skipped'
    """
    meta = _build_parser_metadata()

    # Batch query: relationship counts grouped by r.source
    source_counts: Dict[str, int] = {}
    for rec in session.run(
        "MATCH ()-[r]->() WHERE r.source IS NOT NULL "
        "RETURN r.source AS source, count(r) AS cnt"
    ):
        source_counts[rec['source']] = rec['cnt']

    # Batch query: node counts by label
    node_counts: Dict[str, int] = {}
    labels = [r['l'][0] for r in session.run(
        "MATCH (n) RETURN DISTINCT labels(n) AS l"
    ) if r['l']]
    for label in labels:
        cnt = session.run(
            f"MATCH (n:`{label}`) RETURN count(n) AS cnt"
        ).single()['cnt']
        node_counts[label] = cnt

    # File system checks
    raw_dir = Path(project_root) / 'data' / 'raw'
    proc_dir = Path(project_root) / 'data' / 'processed'

    def _has_data_files(parser_name: str) -> bool:
        for base in (proc_dir, raw_dir):
            for candidate in (parser_name, parser_name.replace('_', '')):
                d = base / candidate
                if d.is_dir() and any(d.iterdir()):
                    return True
        return False

    statuses: Dict = {}
    for parser_name, pmeta in sorted(meta.items()):
        rel_count = sum(source_counts.get(s, 0) for s in pmeta['source_labels'])
        # For node-only parsers (no source_labels), count their node types
        # For relationship parsers, include node counts as supplementary info
        ncount = sum(node_counts.get(nt, 0) for nt in pmeta['node_types'])

        if pmeta['source_labels'] and rel_count > 0:
            parts = []
            if ncount > 0:
                parts.append(f"{ncount:,} nodes")
            parts.append(f"{rel_count:,} relationships")
            statuses[parser_name] = {
                'status': 'success',
                'count': rel_count + ncount,
                'detail': ', '.join(parts),
                'rel_count': rel_count,
                'node_count': ncount,
            }
        elif not pmeta['source_labels'] and ncount > 0:
            # Node-only parser (e.g., drugbank, mesh, ncbigene, uberon)
            statuses[parser_name] = {
                'status': 'success',
                'count': ncount,
                'detail': f"{ncount:,} nodes",
                'rel_count': 0,
                'node_count': ncount,
            }
        elif _has_data_files(parser_name):
            statuses[parser_name] = {
                'status': 'parsed but not loaded',
                'count': 0,
                'detail': 'Data files exist but 0 in graph',
                'rel_count': 0,
                'node_count': 0,
            }
        else:
            statuses[parser_name] = {
                'status': 'skipped',
                'count': 0,
                'detail': 'No data files found',
                'rel_count': 0,
                'node_count': 0,
            }

    return statuses


def query_neo4j_stats(uri: str, username: str, password: str,
                      database: str = 'neo4j') -> Dict:
    """Query graph database for node counts, relationship counts, parser status, and health checks."""
    from neo4j import GraphDatabase

    stats = {
        'node_counts': {},
        'rel_counts': {},
        'total_nodes': 0,
        'total_relationships': 0,
        'orphan_nodes': {},
        'cvd_subgraph': {},
        'parser_status': {},
    }

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session() as session:
            labels = [r['l'][0] for r in session.run(
                "MATCH (n) RETURN DISTINCT labels(n) AS l"
            ) if r['l']]
            for label in sorted(labels):
                cnt = session.run(
                    f"MATCH (n:`{label}`) RETURN count(n) AS cnt"
                ).single()['cnt']
                stats['node_counts'][label] = cnt
                stats['total_nodes'] += cnt

            rel_types = [r['rt'] for r in session.run(
                "MATCH ()-[r]->() RETURN DISTINCT type(r) AS rt"
            )]
            for rt in sorted(rel_types):
                cnt = session.run(
                    f"MATCH ()-[r:`{rt}`]->() RETURN count(r) AS cnt"
                ).single()['cnt']
                stats['rel_counts'][rt] = cnt
                stats['total_relationships'] += cnt

            for label in sorted(labels):
                cnt = session.run(
                    f"MATCH (n:`{label}`) WHERE NOT (n)--() "
                    f"RETURN count(n) AS cnt"
                ).single()['cnt']
                if cnt > 0:
                    stats['orphan_nodes'][label] = cnt

            stats['parser_status'] = _query_parser_status(session, _project_root)
            stats['cvd_subgraph'] = _query_cvd_subgraph(session)

    finally:
        driver.close()

    return stats


def _query_cvd_subgraph(session) -> Dict:
    """Query the atrial fibrillation neighborhood."""
    result = {
        'disease_name': 'atrial fibrillation',
        'disease_found': False,
        'connected_nodes': {},
        'connected_rels': {},
        'total_neighbors': 0,
    }

    rec = session.run(
        "MATCH (d:Disease) "
        "WHERE toLower(d.commonName) CONTAINS 'atrial fibrillation' "
        "RETURN d.commonName AS name, d.xrefDiseaseOntology AS doid "
        "LIMIT 1"
    ).single()

    if not rec:
        return result

    result['disease_found'] = True
    result['disease_name'] = rec['name']
    doid = rec['doid']

    neighbors = session.run(
        "MATCH (d:Disease {xrefDiseaseOntology: $doid})-[r]-(n) "
        "RETURN labels(n)[0] AS label, type(r) AS rel_type, count(*) AS cnt",
        doid=doid,
    )
    for row in neighbors:
        label = row['label']
        rel_type = row['rel_type']
        cnt = row['cnt']
        result['connected_nodes'][label] = result['connected_nodes'].get(label, 0) + cnt
        result['connected_rels'][rel_type] = result['connected_rels'].get(rel_type, 0) + cnt
        result['total_neighbors'] += cnt

    return result


def run_health_check(disease: str = 'cvd',
                     log_file: str = 'logs/cardiokb_build.log',
                     on_progress: Optional[Callable[[str, dict], None]] = None) -> Dict:
    """
    Run a full health check and return structured results.

    Args:
        disease: Disease key (cvd, alzheimers, cancer, asthma, diabetes)
            or path to a filter file.
        log_file: Path to pipeline build log.
        on_progress: Optional callback(event_type, data) for streaming updates.

    Returns:
        Dictionary with log_data, neo4j_stats, and disease info.
    """
    load_dotenv()

    def emit(event: str, data: dict):
        if on_progress:
            on_progress(event, data)

    disease_filter = resolve_disease_filter(disease)
    disease_label = disease if disease in DISEASE_FILTERS else Path(disease).stem

    emit('status', {'message': f'Starting health check for {disease_label}...',
                    'disease': disease_label})

    # Parse build log (for timing info)
    emit('status', {'message': 'Parsing build log...'})
    log_data = parse_build_log(log_file)

    # Query graph database (source of truth for parser status)
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', '')

    neo4j_stats = None
    if password:
        emit('status', {'message': 'Querying graph database for stats and parser status...'})
        try:
            neo4j_stats = query_neo4j_stats(uri, username, password)

            # Merge log timing into graph-derived parser status
            combined_parsers = {}
            for name, ps in neo4j_stats['parser_status'].items():
                log_info = log_data['parsers'].get(name, {})
                combined_parsers[name] = {
                    'status': ps['status'],
                    'detail': ps['detail'],
                    'count': ps['count'],
                    'rel_count': ps['rel_count'],
                    'node_count': ps['node_count'],
                    'duration_sec': log_info.get('duration_sec'),
                }

            emit('log_parsed', {
                'sources_processed': sum(
                    1 for p in combined_parsers.values()
                    if p['status'] == 'success'
                ),
                'sources_failed': sum(
                    1 for p in combined_parsers.values()
                    if p['status'] in ('parsed but not loaded', 'skipped')
                ),
                'pipeline_duration': log_data['pipeline_duration'],
                'pipeline_start': (log_data['pipeline_start'].isoformat()
                                   if log_data['pipeline_start'] else None),
                'parsers': combined_parsers,
            })

            emit('neo4j_stats', {
                'node_counts': neo4j_stats['node_counts'],
                'rel_counts': neo4j_stats['rel_counts'],
                'total_nodes': neo4j_stats['total_nodes'],
                'total_relationships': neo4j_stats['total_relationships'],
                'orphan_nodes': neo4j_stats['orphan_nodes'],
            })
        except Exception as e:
            emit('error', {'message': f'Graph query failed: {e}'})
    else:
        emit('error', {'message': 'NEO4J_PASSWORD not set — skipping graph stats'})

    # Health checks
    emit('status', {'message': 'Running health checks...'})
    health = _build_health_checks(log_data, neo4j_stats)
    emit('health', health)

    # Disease filter info
    try:
        from src.utils import load_disease_terms
        terms = load_disease_terms(disease_filter)
        emit('disease_info', {
            'disease': disease_label,
            'filter_file': disease_filter,
            'term_count': len(terms),
        })
    except Exception as e:
        emit('error', {'message': f'Failed to load disease terms: {e}'})

    emit('done', {'message': 'Health check complete'})

    return {
        'log_data': log_data,
        'neo4j_stats': neo4j_stats,
        'disease': disease_label,
        'disease_filter': disease_filter,
    }


def _build_health_checks(log_data: Dict, neo4j_stats: Optional[Dict]) -> Dict:
    """Build health check results."""
    checks = []

    if neo4j_stats:
        zero_nodes = [k for k, v in neo4j_stats['node_counts'].items() if v == 0]
        checks.append({
            'name': 'Node type counts',
            'ok': len(zero_nodes) == 0,
            'message': f'Zero-count node types: {", ".join(zero_nodes)}' if zero_nodes
                       else 'All node types have non-zero counts',
        })

        zero_rels = [k for k, v in neo4j_stats['rel_counts'].items() if v == 0]
        checks.append({
            'name': 'Relationship type counts',
            'ok': len(zero_rels) == 0,
            'message': f'Zero-count rel types: {", ".join(zero_rels)}' if zero_rels
                       else 'All relationship types have non-zero counts',
        })

        if neo4j_stats['orphan_nodes']:
            orphan_str = ', '.join(f'{k}: {v:,}' for k, v in
                                   sorted(neo4j_stats['orphan_nodes'].items(),
                                          key=lambda x: x[1], reverse=True))
            checks.append({
                'name': 'Orphan nodes',
                'ok': False,
                'message': f'Orphan nodes: {orphan_str}',
            })
        else:
            checks.append({
                'name': 'Orphan nodes',
                'ok': True,
                'message': 'No orphan nodes detected',
            })

    if neo4j_stats and neo4j_stats.get('parser_status'):
        ps = neo4j_stats['parser_status']
        not_loaded = [n for n, s in ps.items()
                      if s['status'] != 'success']
        loaded = [n for n, s in ps.items()
                  if s['status'] == 'success']
        checks.append({
            'name': 'Parser data (graph)',
            'ok': len(not_loaded) == 0,
            'message': (f'{len(loaded)}/{len(ps)} parsers have data in graph'
                        + (f' | Not loaded: {", ".join(sorted(not_loaded))}'
                           if not_loaded else '')),
        })
    else:
        failed = [n for n in _get_expected_parsers()
                  if log_data['parsers'].get(n, {}).get('status') in ('failed', 'no data')]
        checks.append({
            'name': 'Parser data',
            'ok': len(failed) == 0,
            'message': f'Parsers with no data: {", ".join(failed)}' if failed
                       else 'All parsers produced data',
        })

    return {'checks': checks}


def generate_html_report(log_data: Dict, neo4j_stats: Dict,
                         output_path: str) -> str:
    """Generate a self-contained HTML report with Chart.js visualizations."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    parser_rows = []
    parser_status = neo4j_stats.get('parser_status', {})
    all_parsers = sorted(set(_get_expected_parsers()) | set(parser_status.keys()))
    for name in all_parsers:
        ps = parser_status.get(name)
        log_p = log_data['parsers'].get(name, {})
        if ps:
            status = ps['status']
            detail = ps.get('detail', '')
            if detail:
                status = f'{status} ({detail})'
        else:
            status = log_p.get('status', 'skipped')
        dur = f"{log_p['duration_sec']:.1f}s" if log_p.get('duration_sec') else '-'

        status_class = 'success' if 'success' in status else (
            'failed' if status in ('failed', 'no data', 'parsed but not loaded') else 'skipped'
        )
        parser_rows.append(
            f'<tr class="{status_class}">'
            f'<td>{name}</td>'
            f'<td><span class="badge badge-{status_class}">{status}</span></td>'
            f'<td>{dur}</td>'
            f'</tr>'
        )
    parser_table = '\n'.join(parser_rows)

    node_labels = json.dumps(list(neo4j_stats['node_counts'].keys()))
    node_values = json.dumps(list(neo4j_stats['node_counts'].values()))

    rel_sorted = sorted(neo4j_stats['rel_counts'].items(), key=lambda x: x[1], reverse=True)
    rel_labels = json.dumps([r[0] for r in rel_sorted])
    rel_values = json.dumps([r[1] for r in rel_sorted])

    health = _build_health_checks(log_data, neo4j_stats)
    health_html = '\n'.join(
        f'<div class="health-item {"health-ok" if c["ok"] else "health-warn"}">'
        f'{c["message"]}</div>'
        for c in health['checks']
    )

    cvd = neo4j_stats.get('cvd_subgraph', {})
    if cvd.get('disease_found'):
        cvd_node_rows = '\n'.join(
            f'<tr><td>{label}</td><td>{cnt:,}</td></tr>'
            for label, cnt in sorted(cvd['connected_nodes'].items(),
                                     key=lambda x: x[1], reverse=True)
        )
        cvd_rel_rows = '\n'.join(
            f'<tr><td>{rt}</td><td>{cnt:,}</td></tr>'
            for rt, cnt in sorted(cvd['connected_rels'].items(),
                                  key=lambda x: x[1], reverse=True)
        )
        cvd_html = f'''
        <p>Disease node: <strong>{cvd["disease_name"]}</strong>
           | Total neighbors: <strong>{cvd["total_neighbors"]:,}</strong></p>
        <div class="cvd-tables">
            <div>
                <h4>Connected Node Types</h4>
                <table class="data-table">
                    <thead><tr><th>Node Type</th><th>Count</th></tr></thead>
                    <tbody>{cvd_node_rows}</tbody>
                </table>
            </div>
            <div>
                <h4>Relationship Types</h4>
                <table class="data-table">
                    <thead><tr><th>Relationship</th><th>Count</th></tr></thead>
                    <tbody>{cvd_rel_rows}</tbody>
                </table>
            </div>
        </div>'''
    else:
        cvd_html = '<p class="health-warn">Atrial fibrillation disease node not found.</p>'

    pipeline_start = log_data['pipeline_start'].strftime('%Y-%m-%d %H:%M:%S') if log_data['pipeline_start'] else '-'
    pipeline_dur = log_data['pipeline_duration'] or '-'

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CardioKB Pipeline Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
:root {{ --bg:#0f172a;--surface:#1e293b;--surface2:#334155;--border:#475569;--text:#e2e8f0;--text-muted:#94a3b8;--accent:#38bdf8;--green:#4ade80;--red:#f87171;--yellow:#fbbf24; }}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;padding:2rem}}
.container{{max-width:1200px;margin:0 auto}}
header{{text-align:center;margin-bottom:2rem;padding-bottom:1.5rem;border-bottom:1px solid var(--border)}}
header h1{{font-size:1.8rem;color:var(--accent);margin-bottom:.5rem}} header p{{color:var(--text-muted);font-size:.9rem}}
.stats-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1rem;margin-bottom:2rem}}
.stat-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1.2rem;text-align:center}}
.stat-card .value{{font-size:1.8rem;font-weight:700;color:var(--accent)}} .stat-card .label{{color:var(--text-muted);font-size:.85rem;margin-top:.25rem}}
section{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1.5rem;margin-bottom:1.5rem}}
section h2{{font-size:1.2rem;color:var(--accent);margin-bottom:1rem;padding-bottom:.5rem;border-bottom:1px solid var(--border)}}
table{{width:100%;border-collapse:collapse;font-size:.88rem}} th,td{{padding:.5rem .75rem;text-align:left;border-bottom:1px solid var(--surface2)}}
th{{color:var(--text-muted);font-weight:600;text-transform:uppercase;font-size:.75rem;letter-spacing:.05em}}
tr.success td:first-child{{border-left:3px solid var(--green)}} tr.failed td:first-child{{border-left:3px solid var(--red)}} tr.skipped td:first-child{{border-left:3px solid var(--yellow)}}
.badge{{display:inline-block;padding:.15rem .5rem;border-radius:4px;font-size:.78rem;font-weight:600}}
.badge-success{{background:rgba(74,222,128,.15);color:var(--green)}} .badge-failed{{background:rgba(248,113,113,.15);color:var(--red)}} .badge-skipped{{background:rgba(251,191,36,.15);color:var(--yellow)}}
.chart-container{{position:relative;height:400px;margin:1rem 0}}
.health-item{{padding:.6rem 1rem;border-radius:6px;margin-bottom:.5rem;font-size:.9rem}}
.health-ok{{background:rgba(74,222,128,.1);border-left:3px solid var(--green)}} .health-warn{{background:rgba(248,113,113,.1);border-left:3px solid var(--red)}}
.cvd-tables{{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-top:1rem}} .data-table{{font-size:.85rem}} .data-table th{{background:var(--surface2)}}
@media(max-width:768px){{body{{padding:1rem}}.cvd-tables{{grid-template-columns:1fr}}.chart-container{{height:300px}}}}
</style>
</head>
<body>
<div class="container">
<header><h1>CardioKB Pipeline Report</h1><p>Generated {now} | Last run: {pipeline_start}</p></header>
<div class="stats-grid">
<div class="stat-card"><div class="value">{neo4j_stats["total_nodes"]:,}</div><div class="label">Total Nodes</div></div>
<div class="stat-card"><div class="value">{neo4j_stats["total_relationships"]:,}</div><div class="label">Total Relationships</div></div>
<div class="stat-card"><div class="value">{len(neo4j_stats["node_counts"])}</div><div class="label">Node Types</div></div>
<div class="stat-card"><div class="value">{len(neo4j_stats["rel_counts"])}</div><div class="label">Relationship Types</div></div>
<div class="stat-card"><div class="value">{log_data["sources_processed"]}</div><div class="label">Sources Processed</div></div>
<div class="stat-card"><div class="value">{pipeline_dur}</div><div class="label">Pipeline Duration</div></div>
</div>
<section><h2>Pipeline Run Summary</h2><table><thead><tr><th>Parser</th><th>Status</th><th>Duration</th></tr></thead><tbody>
{parser_table}
</tbody></table></section>
<section><h2>Node Counts by Type</h2><div class="chart-container"><canvas id="nodeChart"></canvas></div></section>
<section><h2>Relationship Counts by Type</h2><div class="chart-container"><canvas id="relChart"></canvas></div></section>
<section><h2>Graph Health Checks</h2>{health_html}</section>
<section><h2>CVD Subgraph: Atrial Fibrillation</h2>{cvd_html}</section>
</div>
<script>
Chart.defaults.color='#94a3b8';Chart.defaults.font.family="-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif";
function makeBar(id,labels,data,color){{new Chart(document.getElementById(id),{{type:'bar',data:{{labels,datasets:[{{data,backgroundColor:color+'99',borderColor:color,borderWidth:1,borderRadius:4}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>c.parsed.y.toLocaleString()}}}}}},scales:{{y:{{type:'logarithmic',grid:{{color:'#334155'}},ticks:{{callback:v=>v.toLocaleString()}}}},x:{{grid:{{display:false}},ticks:{{maxRotation:45,minRotation:45}}}}}}}}}})}}
makeBar('nodeChart',{node_labels},{node_values},'#38bdf8');
makeBar('relChart',{rel_labels},{rel_values},'#4ade80');
</script></body></html>'''

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(html)
    return output_path


def main():
    import argparse

    parser = argparse.ArgumentParser(description='CardioKB Pipeline Health Report')
    parser.add_argument('--log-file', default='logs/cardiokb_build.log',
                        help='Path to the build log file')
    parser.add_argument('--output', default='reports/pipeline_report.html',
                        help='Output HTML report path')
    parser.add_argument('--disease', default='cvd',
                        choices=list(DISEASE_FILTERS.keys()),
                        help='Disease filter to use (default: cvd)')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    def print_progress(event, data):
        logger.info(f"[{event}] {data.get('message', json.dumps(data)[:120])}")

    result = run_health_check(
        disease=args.disease,
        log_file=args.log_file,
        on_progress=print_progress,
    )

    if result['neo4j_stats']:
        logger.info("Generating HTML report...")
        output = generate_html_report(
            result['log_data'], result['neo4j_stats'], args.output
        )
        logger.info(f"Report saved to: {output}")
        print(f"\nReport: {output}")


if __name__ == '__main__':
    main()
