"""
CardioKB Pipeline Orchestrator

Runs pipeline health checks against the Neo4j graph and the latest build log,
then generates a self-contained HTML report at reports/pipeline_report.html.

Usage:
    python src/orchestrator.py
    python src/orchestrator.py --log-file cardiokb_build.log
    python src/orchestrator.py --output reports/pipeline_report.html
"""

import os
import re
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from dotenv import load_dotenv

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logger = logging.getLogger(__name__)

# All expected parsers in pipeline order
EXPECTED_PARSERS = [
    'clinicaltrials', 'clinpgx', 'ncbigene', 'dorothea',
    'disease_ontology', 'gene_ontology', 'uberon', 'mesh',
    'sider', 'lincs', 'medline', 'drugcentral', 'gwas',
    'pubtator', 'bindingdb', 'ctd', 'bgee', 'hetionet_precomputed',
    'jensenlab', 'jensentissues', 'hpo', 'omim', 'disgenet',
    'drugbank', 'aopdb',
]


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

        # Pipeline start/end
        if 'Start time:' in line and results['pipeline_start'] is None:
            results['pipeline_start'] = timestamp

        if 'Pipeline Completed Successfully' in line:
            results['pipeline_end'] = timestamp

        # Parser tracking
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


def query_neo4j_stats(uri: str, username: str, password: str,
                      database: str = 'neo4j') -> Dict:
    """Query Neo4j for node counts, relationship counts, and health checks."""
    from neo4j import GraphDatabase

    stats = {
        'node_counts': {},
        'rel_counts': {},
        'total_nodes': 0,
        'total_relationships': 0,
        'orphan_nodes': {},
        'cvd_subgraph': {},
    }

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session(database=database) as session:
            # Node counts by label
            labels = [r['label'] for r in session.run(
                "CALL db.labels() YIELD label RETURN label"
            )]
            for label in sorted(labels):
                cnt = session.run(
                    f"MATCH (n:{label}) RETURN count(n) AS cnt"
                ).single()['cnt']
                stats['node_counts'][label] = cnt
                stats['total_nodes'] += cnt

            # Relationship counts by type
            rel_types = [r['relationshipType'] for r in session.run(
                "CALL db.relationshipTypes() YIELD relationshipType "
                "RETURN relationshipType"
            )]
            for rt in sorted(rel_types):
                cnt = session.run(
                    f"MATCH ()-[r:`{rt}`]->() RETURN count(r) AS cnt"
                ).single()['cnt']
                stats['rel_counts'][rt] = cnt
                stats['total_relationships'] += cnt

            # Orphan nodes (nodes with no relationships) per label
            for label in sorted(labels):
                cnt = session.run(
                    f"MATCH (n:{label}) WHERE NOT (n)--() "
                    f"RETURN count(n) AS cnt"
                ).single()['cnt']
                if cnt > 0:
                    stats['orphan_nodes'][label] = cnt

            # CVD subgraph: atrial fibrillation
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

    # Find the disease node
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

    # Count neighbor nodes by label
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


def generate_html_report(log_data: Dict, neo4j_stats: Dict,
                         output_path: str) -> str:
    """Generate a self-contained HTML report with Chart.js visualizations."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Prepare parser table rows
    parser_rows = []
    for name in EXPECTED_PARSERS:
        if name in log_data['parsers']:
            p = log_data['parsers'][name]
            status = p['status']
            dur = f"{p['duration_sec']:.1f}s" if p['duration_sec'] else '-'
        else:
            status = 'skipped'
            dur = '-'

        status_class = 'success' if 'success' in status else (
            'failed' if status in ('failed', 'no data') else 'skipped'
        )
        parser_rows.append(
            f'<tr class="{status_class}">'
            f'<td>{name}</td>'
            f'<td><span class="badge badge-{status_class}">{status}</span></td>'
            f'<td>{dur}</td>'
            f'</tr>'
        )
    parser_table = '\n'.join(parser_rows)

    # Node chart data
    node_labels = json.dumps(list(neo4j_stats['node_counts'].keys()))
    node_values = json.dumps(list(neo4j_stats['node_counts'].values()))

    # Relationship chart data (sorted by count descending)
    rel_sorted = sorted(neo4j_stats['rel_counts'].items(), key=lambda x: x[1], reverse=True)
    rel_labels = json.dumps([r[0] for r in rel_sorted])
    rel_values = json.dumps([r[1] for r in rel_sorted])

    # Health check items
    health_items = []

    # Zero-count node types
    zero_nodes = [k for k, v in neo4j_stats['node_counts'].items() if v == 0]
    if zero_nodes:
        health_items.append(
            f'<div class="health-item health-warn">'
            f'<strong>Node types with 0 count:</strong> {", ".join(zero_nodes)}'
            f'</div>'
        )
    else:
        health_items.append(
            '<div class="health-item health-ok">'
            'All node types have non-zero counts'
            '</div>'
        )

    # Zero-count relationship types
    zero_rels = [k for k, v in neo4j_stats['rel_counts'].items() if v == 0]
    if zero_rels:
        health_items.append(
            f'<div class="health-item health-warn">'
            f'<strong>Relationship types with 0 count:</strong> {", ".join(zero_rels)}'
            f'</div>'
        )
    else:
        health_items.append(
            '<div class="health-item health-ok">'
            'All relationship types have non-zero counts'
            '</div>'
        )

    # Orphan nodes
    if neo4j_stats['orphan_nodes']:
        orphan_details = ', '.join(
            f'{label}: {cnt:,}' for label, cnt in
            sorted(neo4j_stats['orphan_nodes'].items(), key=lambda x: x[1], reverse=True)
        )
        health_items.append(
            f'<div class="health-item health-warn">'
            f'<strong>Orphan nodes (no relationships):</strong> {orphan_details}'
            f'</div>'
        )
    else:
        health_items.append(
            '<div class="health-item health-ok">'
            'No orphan nodes detected'
            '</div>'
        )

    # Failed parsers
    failed = [n for n in EXPECTED_PARSERS
              if log_data['parsers'].get(n, {}).get('status') in ('failed', 'no data')]
    if failed:
        health_items.append(
            f'<div class="health-item health-warn">'
            f'<strong>Parsers with no data:</strong> {", ".join(failed)}'
            f'</div>'
        )
    else:
        health_items.append(
            '<div class="health-item health-ok">'
            'All parsers produced data'
            '</div>'
        )

    health_html = '\n'.join(health_items)

    # CVD subgraph section
    cvd = neo4j_stats['cvd_subgraph']
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
        </div>
        '''
    else:
        cvd_html = '<p class="health-warn">Atrial fibrillation disease node not found in graph.</p>'

    # Pipeline summary
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
    :root {{
        --bg: #0f172a;
        --surface: #1e293b;
        --surface2: #334155;
        --border: #475569;
        --text: #e2e8f0;
        --text-muted: #94a3b8;
        --accent: #38bdf8;
        --green: #4ade80;
        --red: #f87171;
        --yellow: #fbbf24;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
        background: var(--bg);
        color: var(--text);
        line-height: 1.6;
        padding: 2rem;
    }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    header {{
        text-align: center;
        margin-bottom: 2rem;
        padding-bottom: 1.5rem;
        border-bottom: 1px solid var(--border);
    }}
    header h1 {{ font-size: 1.8rem; color: var(--accent); margin-bottom: 0.5rem; }}
    header p {{ color: var(--text-muted); font-size: 0.9rem; }}
    .stats-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 1rem;
        margin-bottom: 2rem;
    }}
    .stat-card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 1.2rem;
        text-align: center;
    }}
    .stat-card .value {{
        font-size: 1.8rem;
        font-weight: 700;
        color: var(--accent);
    }}
    .stat-card .label {{
        color: var(--text-muted);
        font-size: 0.85rem;
        margin-top: 0.25rem;
    }}
    section {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
    }}
    section h2 {{
        font-size: 1.2rem;
        color: var(--accent);
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid var(--border);
    }}
    section h4 {{ color: var(--text); margin-bottom: 0.5rem; }}
    table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.88rem;
    }}
    th, td {{
        padding: 0.5rem 0.75rem;
        text-align: left;
        border-bottom: 1px solid var(--surface2);
    }}
    th {{
        color: var(--text-muted);
        font-weight: 600;
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
    }}
    tr.success td:first-child {{ border-left: 3px solid var(--green); padding-left: calc(0.75rem - 3px); }}
    tr.failed td:first-child {{ border-left: 3px solid var(--red); padding-left: calc(0.75rem - 3px); }}
    tr.skipped td:first-child {{ border-left: 3px solid var(--yellow); padding-left: calc(0.75rem - 3px); }}
    .badge {{
        display: inline-block;
        padding: 0.15rem 0.5rem;
        border-radius: 4px;
        font-size: 0.78rem;
        font-weight: 600;
    }}
    .badge-success {{ background: rgba(74,222,128,0.15); color: var(--green); }}
    .badge-failed {{ background: rgba(248,113,113,0.15); color: var(--red); }}
    .badge-skipped {{ background: rgba(251,191,36,0.15); color: var(--yellow); }}
    .chart-container {{
        position: relative;
        height: 400px;
        margin: 1rem 0;
    }}
    .health-item {{
        padding: 0.6rem 1rem;
        border-radius: 6px;
        margin-bottom: 0.5rem;
        font-size: 0.9rem;
    }}
    .health-ok {{ background: rgba(74,222,128,0.1); border-left: 3px solid var(--green); }}
    .health-warn {{ background: rgba(248,113,113,0.1); border-left: 3px solid var(--red); }}
    .cvd-tables {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 1.5rem;
        margin-top: 1rem;
    }}
    .data-table {{ font-size: 0.85rem; }}
    .data-table th {{ background: var(--surface2); }}
    @media (max-width: 768px) {{
        body {{ padding: 1rem; }}
        .cvd-tables {{ grid-template-columns: 1fr; }}
        .chart-container {{ height: 300px; }}
    }}
</style>
</head>
<body>
<div class="container">
    <header>
        <h1>CardioKB Pipeline Report</h1>
        <p>Generated {now} | Last pipeline run: {pipeline_start}</p>
    </header>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="value">{neo4j_stats["total_nodes"]:,}</div>
            <div class="label">Total Nodes</div>
        </div>
        <div class="stat-card">
            <div class="value">{neo4j_stats["total_relationships"]:,}</div>
            <div class="label">Total Relationships</div>
        </div>
        <div class="stat-card">
            <div class="value">{len(neo4j_stats["node_counts"])}</div>
            <div class="label">Node Types</div>
        </div>
        <div class="stat-card">
            <div class="value">{len(neo4j_stats["rel_counts"])}</div>
            <div class="label">Relationship Types</div>
        </div>
        <div class="stat-card">
            <div class="value">{log_data["sources_processed"]}</div>
            <div class="label">Sources Processed</div>
        </div>
        <div class="stat-card">
            <div class="value">{pipeline_dur}</div>
            <div class="label">Pipeline Duration</div>
        </div>
    </div>

    <section>
        <h2>Pipeline Run Summary</h2>
        <table>
            <thead><tr><th>Parser</th><th>Status</th><th>Duration</th></tr></thead>
            <tbody>
{parser_table}
            </tbody>
        </table>
    </section>

    <section>
        <h2>Node Counts by Type</h2>
        <div class="chart-container">
            <canvas id="nodeChart"></canvas>
        </div>
    </section>

    <section>
        <h2>Relationship Counts by Type</h2>
        <div class="chart-container">
            <canvas id="relChart"></canvas>
        </div>
    </section>

    <section>
        <h2>Graph Health Checks</h2>
        {health_html}
    </section>

    <section>
        <h2>CVD Subgraph: Atrial Fibrillation</h2>
        {cvd_html}
    </section>
</div>

<script>
const chartDefaults = {{
    color: '#94a3b8',
    borderColor: '#475569',
    font: {{ family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif" }}
}};
Chart.defaults.color = chartDefaults.color;
Chart.defaults.font.family = chartDefaults.font.family;

// Node counts bar chart
new Chart(document.getElementById('nodeChart'), {{
    type: 'bar',
    data: {{
        labels: {node_labels},
        datasets: [{{
            label: 'Count',
            data: {node_values},
            backgroundColor: 'rgba(56, 189, 248, 0.6)',
            borderColor: 'rgba(56, 189, 248, 1)',
            borderWidth: 1,
            borderRadius: 4,
        }}]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
            legend: {{ display: false }},
            tooltip: {{
                callbacks: {{
                    label: ctx => ctx.parsed.y.toLocaleString() + ' nodes'
                }}
            }}
        }},
        scales: {{
            y: {{
                type: 'logarithmic',
                grid: {{ color: '#334155' }},
                ticks: {{
                    callback: v => v.toLocaleString()
                }}
            }},
            x: {{
                grid: {{ display: false }},
                ticks: {{ maxRotation: 45, minRotation: 45 }}
            }}
        }}
    }}
}});

// Relationship counts bar chart
new Chart(document.getElementById('relChart'), {{
    type: 'bar',
    data: {{
        labels: {rel_labels},
        datasets: [{{
            label: 'Count',
            data: {rel_values},
            backgroundColor: 'rgba(74, 222, 128, 0.6)',
            borderColor: 'rgba(74, 222, 128, 1)',
            borderWidth: 1,
            borderRadius: 4,
        }}]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
            legend: {{ display: false }},
            tooltip: {{
                callbacks: {{
                    label: ctx => ctx.parsed.y.toLocaleString() + ' relationships'
                }}
            }}
        }},
        scales: {{
            y: {{
                type: 'logarithmic',
                grid: {{ color: '#334155' }},
                ticks: {{
                    callback: v => v.toLocaleString()
                }}
            }},
            x: {{
                grid: {{ display: false }},
                ticks: {{ maxRotation: 45, minRotation: 45 }}
            }}
        }}
    }}
}});
</script>
</body>
</html>'''

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(html)

    return output_path


def main():
    import argparse

    parser = argparse.ArgumentParser(description='CardioKB Pipeline Health Report')
    parser.add_argument('--log-file', default='cardiokb_build.log',
                        help='Path to the build log file')
    parser.add_argument('--output', default='reports/pipeline_report.html',
                        help='Output HTML report path')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    load_dotenv()

    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', '')

    if not password:
        logger.error("NEO4J_PASSWORD not set. Set it in .env or environment.")
        sys.exit(1)

    logger.info("Parsing build log...")
    log_data = parse_build_log(args.log_file)
    logger.info(f"  Found {len(log_data['parsers'])} parsers in log "
                f"({log_data['sources_processed']} processed, "
                f"{log_data['sources_failed']} failed)")

    logger.info("Querying Neo4j for graph stats...")
    neo4j_stats = query_neo4j_stats(uri, username, password)
    logger.info(f"  {neo4j_stats['total_nodes']:,} nodes, "
                f"{neo4j_stats['total_relationships']:,} relationships")

    logger.info("Generating HTML report...")
    output = generate_html_report(log_data, neo4j_stats, args.output)
    logger.info(f"Report saved to: {output}")
    print(f"\nReport: {output}")


if __name__ == '__main__':
    main()
