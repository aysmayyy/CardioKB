"""
CardioKB Disease Agent — AI-powered disease knowledge graph builder.

Accepts a disease name (any form — abbreviations, synonyms, informal names),
standardizes it via Claude, checks the DiseaseCache (including alias lookup),
and if not cached, generates DisGeNET search terms, runs the parser,
loads results into Neo4j, caches the result, and returns subgraph stats.

Usage:
    python src/agent.py "parkinson's disease"
    python src/agent.py "PD"
    python src/agent.py --list-cached
"""

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(name)s | %(message)s',
)
logger = logging.getLogger('cardiokb.agent')

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Pre-built disease filters shipped with the project
KNOWN_FILTERS = {
    'cvd': 'ontology/diseases/cvd.txt',
    'alzheimers': 'ontology/diseases/alzheimers.txt',
    'cancer': 'ontology/diseases/cancer.txt',
    'asthma': 'ontology/diseases/asthma.txt',
    'diabetes': 'ontology/diseases/diabetes.txt',
}

# Model to use for standardization
MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')


def _get_client():
    """Create an Anthropic client using ANTHROPIC_API_KEY."""
    import anthropic
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Add it to your .env file.\n"
            "Get one free at https://console.anthropic.com/settings/keys"
        )
    return anthropic.Anthropic(api_key=api_key)


def _read_filter_file(path: str) -> list[str]:
    """Read terms from a disease filter file."""
    terms = []
    full_path = PROJECT_ROOT / path
    with open(full_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                terms.append(line.lower())
    return terms


def _standardize_disease(user_input: str) -> dict:
    """
    Use Claude to standardize a disease name and generate search terms.

    Returns a dict with:
        - canonical_key: snake_case key for cache/dirs (e.g. "parkinsons_disease")
        - canonical_name: human-readable name (e.g. "Parkinson's Disease")
        - existing_filter: key from KNOWN_FILTERS if one matches, else null
        - search_terms: list of DisGeNET search terms
    """
    # Build context about existing filters
    filter_summaries = {}
    for key, path in KNOWN_FILTERS.items():
        try:
            terms = _read_filter_file(path)
            filter_summaries[key] = {
                'file': path,
                'term_count': len(terms),
                'sample_terms': terms[:10],
            }
        except FileNotFoundError:
            pass

    system_prompt = (
        "You are a biomedical nomenclature expert helping build a disease "
        "knowledge graph. Your job is to:\n"
        "1. Standardize disease names to a single canonical form\n"
        "2. Map to existing disease filter files when appropriate\n"
        "3. Generate comprehensive DisGeNET search terms\n\n"
        "You MUST respond with ONLY a JSON object (no markdown, no explanation)."
    )

    user_prompt = (
        f'User input: "{user_input}"\n\n'
        f"Existing disease filter files:\n"
        f"{json.dumps(filter_summaries, indent=2)}\n\n"
        f"Instructions:\n"
        f"1. STANDARDIZE: Determine the canonical disease name for this input. "
        f"For example, 'PD', 'parkinsons', \"Parkinson's\", and "
        f"'parkinson disease' should ALL resolve to the same canonical form.\n\n"
        f"2. MATCH EXISTING: Check if the user's disease matches one of the "
        f"existing filter files above. If so, set existing_filter to that key "
        f"(e.g. 'cvd', 'cancer'). Consider that 'heart disease', 'CVD', "
        f"'cardiovascular', 'coronary artery disease' all match 'cvd'. "
        f"'tumors', 'oncology', 'leukemia' match 'cancer'. Etc. "
        f"If no existing filter matches, set existing_filter to null.\n\n"
        f"3. GENERATE TERMS: Produce 15-50 lowercase search terms for "
        f"querying the DisGeNET gene-disease association database. Include:\n"
        f"   - The canonical disease name\n"
        f"   - Common medical synonyms and abbreviations\n"
        f"   - Major clinical subtypes\n"
        f"   - Related conditions sharing genetic architecture\n\n"
        f"Return this exact JSON structure:\n"
        f'{{\n'
        f'  "canonical_key": "snake_case_key",\n'
        f'  "canonical_name": "Human-Readable Disease Name",\n'
        f'  "existing_filter": "cvd" or null,\n'
        f'  "search_terms": ["term1", "term2", ...]\n'
        f'}}'
    )

    logger.info(f"Asking Claude to standardize '{user_input}'...")

    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = next(
        (b.text for b in response.content if b.type == "text"), ""
    ).strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3].strip()
    if text.startswith("json"):
        text = text[4:].strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response: {e}")
        logger.error(f"Raw: {text[:500]}")
        # Fallback
        fallback_key = user_input.lower().replace("'", "").replace(" ", "_")
        fallback_key = "".join(c for c in fallback_key if c.isalnum() or c == '_')
        return {
            "canonical_key": fallback_key,
            "canonical_name": user_input,
            "existing_filter": None,
            "search_terms": [user_input.lower()],
        }

    # Validate and clean
    result.setdefault("canonical_key", user_input.lower().replace(" ", "_"))
    result.setdefault("canonical_name", user_input)
    result.setdefault("existing_filter", None)
    result.setdefault("search_terms", [user_input.lower()])

    # Sanitize key
    key = result["canonical_key"].lower().replace("'", "").replace(" ", "_")
    result["canonical_key"] = "".join(c for c in key if c.isalnum() or c == '_')

    # Ensure terms are lowercase strings
    result["search_terms"] = [
        str(t).strip().lower()
        for t in result["search_terms"]
        if str(t).strip()
    ]

    # Validate existing_filter
    if result["existing_filter"] and result["existing_filter"] not in KNOWN_FILTERS:
        result["existing_filter"] = None

    logger.info(f"  Canonical: {result['canonical_name']} (key: {result['canonical_key']})")
    if result["existing_filter"]:
        logger.info(f"  Matched existing filter: {result['existing_filter']}")
    logger.info(f"  Generated {len(result['search_terms'])} search terms")
    for t in result["search_terms"][:8]:
        logger.info(f"    - {t}")
    if len(result["search_terms"]) > 8:
        logger.info(f"    ... and {len(result['search_terms']) - 8} more")

    return result


def _write_temp_filter(terms: list[str]) -> str:
    """Write search terms to a temporary disease filter file."""
    filter_dir = PROJECT_ROOT / 'ontology' / 'diseases'
    filter_dir.mkdir(parents=True, exist_ok=True)

    fd, path = tempfile.mkstemp(
        suffix='.txt', prefix='agent_filter_', dir=str(filter_dir)
    )
    with os.fdopen(fd, 'w') as f:
        f.write("# Auto-generated disease filter\n")
        for term in terms:
            f.write(f"{term}\n")

    logger.info(f"Wrote {len(terms)} terms to {path}")
    return path


MAX_DISEASE_IDS = 200
TIMEOUT_SECONDS = 120


def _run_disgenet(disease_key: str, filter_path: str) -> dict:
    """
    Run DisGeNET parser with caps for agent use.

    Limits: max 200 disease IDs queried, 2-minute timeout.
    Returns dict with 'gda_count' and 'partial' flag.
    """
    import time as _time
    from src.parsers.disgenet_parser import DisGeNETParser
    from src.memgraph_loader import Neo4jLoader
    from src.ontology_configs import ONTOLOGY_CONFIGS

    api_key = os.getenv('DISGENET_API_KEY')
    if not api_key:
        raise RuntimeError("DISGENET_API_KEY not set")

    data_dir = str(PROJECT_ROOT / 'data' / 'raw' / f'disgenet_{disease_key}')
    os.makedirs(data_dir, exist_ok=True)

    parser = DisGeNETParser(
        data_dir=data_dir,
        api_key=api_key,
        disease_filter=filter_path,
    )

    logger.info(f"Querying DisGeNET API for '{disease_key}' "
                f"(max {MAX_DISEASE_IDS} disease IDs, {TIMEOUT_SECONDS}s timeout)...")

    # Step 1: Get disease IDs (search phase — usually fast)
    disease_classifications, disease_mappings = parser.get_cvd_disease_ids()
    if disease_classifications is None or disease_mappings is None:
        logger.error("No disease IDs found")
        return {'gda_count': 0, 'partial': False}

    # Save disease data
    classifications_path = parser.get_file_path(
        f"api_{parser.__class__.__name__}_disease_classifications.tsv")
    disease_classifications.to_csv(classifications_path, sep='\t', index=False)
    mappings_path = parser.get_file_path(
        f"api_{parser.__class__.__name__}_disease_mappings.tsv")
    disease_mappings.to_csv(mappings_path, sep='\t', index=False)

    unique_ids = disease_mappings['diseaseId'].dropna().unique().tolist()
    total_ids = len(unique_ids)
    partial = total_ids > MAX_DISEASE_IDS
    capped_ids = unique_ids[:MAX_DISEASE_IDS]

    if partial:
        logger.info(f"Capping disease IDs: {total_ids} -> {MAX_DISEASE_IDS}")

    # Step 2: Fetch associations with timeout
    all_associations = []
    deadline = _time.time() + TIMEOUT_SECONDS
    fetched_count = 0

    for disease_id in capped_ids:
        if _time.time() > deadline:
            logger.warning(f"Timeout after {TIMEOUT_SECONDS}s — fetched {fetched_count}/{len(capped_ids)} disease IDs")
            partial = True
            break

        associations = parser._get_disease_associations_by_id(disease_id)
        fetched_count += 1

        if associations is not None and len(associations) > 0:
            all_associations.append(associations)
            if fetched_count % 50 == 0:
                logger.info(f"  Progress: {fetched_count}/{len(capped_ids)} IDs, "
                            f"{sum(len(a) for a in all_associations)} associations")

        _time.sleep(0.3)

    if not all_associations:
        logger.warning("No associations fetched")
        return {'gda_count': 0, 'partial': partial}

    # Combine and deduplicate
    import pandas as pd
    combined = pd.concat(all_associations, ignore_index=True).drop_duplicates()
    combined['sourceDatabase'] = 'DisGeNET'

    # Save associations TSV (so parse_data can read it)
    from src.ontology_configs import DISGENET_GENE_DISEASE_ASSOCIATIONS
    output_path = parser.get_file_path(f"api_{DISGENET_GENE_DISEASE_ASSOCIATIONS}.tsv")
    combined.to_csv(output_path, sep='\t', index=False)
    logger.info(f"Fetched {len(combined)} associations from {fetched_count} disease IDs "
                f"({'partial' if partial else 'complete'})")

    # Step 3: Parse (reads cached TSVs) and load into Neo4j
    parsed = parser.parse_data()
    if not parsed:
        return {'gda_count': 0, 'partial': partial}

    gda = parsed.get('gene_disease_associations')
    diseases = parsed.get('diseases')
    gda_count = len(gda) if gda is not None else 0
    logger.info(f"Parsed {gda_count} gene-disease associations")

    if gda_count == 0:
        return {'gda_count': 0, 'partial': partial}

    # Export TSVs
    out_dir = PROJECT_ROOT / 'data' / 'processed' / f'disgenet_{disease_key}'
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in parsed.items():
        df.to_csv(out_dir / f'{name}.tsv', sep='\t', index=False)

    # Load into Neo4j
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', '')
    if not password:
        raise RuntimeError("NEO4J_PASSWORD not set")

    with Neo4jLoader(uri, username, password) as loader:
        if diseases is not None and len(diseases) > 0:
            counts = loader.load_disgenet_diseases(diseases)
            logger.info(f"Disease nodes: {counts}")

        rel_config = ONTOLOGY_CONFIGS.get('disgenet.gene_disease_associations')
        if rel_config and gda is not None and len(gda) > 0:
            loader._load_relationships(
                gda, rel_config, 'disgenet.gene_disease_associations'
            )

    return {'gda_count': gda_count, 'partial': partial}


def _query_subgraph_stats(disease_key: str) -> dict:
    """Query Neo4j for subgraph stats related to a disease."""
    from src.utils import _get_neo4j_driver

    driver = _get_neo4j_driver()
    if not driver:
        return {"error": "NEO4J_PASSWORD not set"}

    stats = {}
    try:
        with driver.session() as s:
            rec = s.run(
                "MATCH ()-[r:geneAssociatesWithDisease]->() "
                "WHERE r.source = 'DisGeNET' "
                "AND r.disease_scope CONTAINS $scope "
                "RETURN count(r) AS c",
                scope=disease_key,
            ).single()
            stats['disgenet_edges'] = rec['c'] if rec else 0

            rec = s.run(
                "MATCH (g:Gene)-[r:geneAssociatesWithDisease]->() "
                "WHERE r.source = 'DisGeNET' "
                "AND r.disease_scope CONTAINS $scope "
                "RETURN count(DISTINCT g) AS c",
                scope=disease_key,
            ).single()
            stats['unique_genes'] = rec['c'] if rec else 0

            rec = s.run(
                "MATCH ()-[r:geneAssociatesWithDisease]->(d:Disease) "
                "WHERE r.source = 'DisGeNET' "
                "AND r.disease_scope CONTAINS $scope "
                "RETURN count(DISTINCT d) AS c",
                scope=disease_key,
            ).single()
            stats['unique_diseases'] = rec['c'] if rec else 0

            rec = s.run("MATCH (n) RETURN count(n) AS c").single()
            stats['total_nodes'] = rec['c'] if rec else 0
            rec = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()
            stats['total_relationships'] = rec['c'] if rec else 0

    finally:
        driver.close()

    return stats


def run_agent(disease_name: str, on_progress=None) -> dict:
    """
    Main agent entry point.

    1. Standardize disease name via Claude (canonical key + search terms)
    2. Check DiseaseCache by canonical key AND by alias (fuzzy match)
    3. If cached: add the user's input as a new alias, return stats
    4. If not cached: run DisGeNET, cache result with aliases
    5. Return subgraph stats

    Args:
        disease_name: Disease name to process.
        on_progress: Optional callback(event: str, data: dict) for streaming progress.
    """
    from src.utils import (
        check_disease_cache, add_to_disease_cache, add_alias_to_disease_cache,
    )

    def emit(event: str, data: dict):
        if on_progress:
            on_progress(event, data)

    user_input = disease_name.strip()
    logger.info(f"User input: '{user_input}'")
    emit('status', {'phase': 'start', 'message': f"Processing '{user_input}'..."})

    # Step 1: Check cache with raw input first (fast path — no Claude call)
    emit('status', {'phase': 'cache_check', 'message': 'Checking disease cache...'})
    cached = check_disease_cache(user_input)
    if cached:
        logger.info(
            f"Cache hit via alias lookup "
            f"(key: {cached['disease_name']}, "
            f"loaded {cached.get('date_loaded', 'unknown')})"
        )
        add_alias_to_disease_cache(cached['disease_name'], user_input)
        stats = _query_subgraph_stats(cached['disease_name'])
        emit('status', {'phase': 'cache_hit', 'message': f"Found in cache: {cached['disease_name']}"})
        return {
            "disease_key": cached['disease_name'],
            "canonical_name": cached.get('canonical_name', cached['disease_name']),
            "user_input": user_input,
            "cached": True,
            "cache_info": cached,
            "subgraph_stats": stats,
        }

    # Step 2: Standardize via Claude (resolves abbreviations, synonyms, etc.)
    emit('status', {'phase': 'standardize', 'message': 'Standardizing disease name via Claude...'})
    std = _standardize_disease(user_input)
    canonical_key = std["canonical_key"]
    canonical_name = std["canonical_name"]
    existing_filter = std["existing_filter"]
    search_terms = std["search_terms"]

    emit('status', {
        'phase': 'standardized',
        'message': f"Resolved to: {canonical_name}",
        'canonical_key': canonical_key,
        'canonical_name': canonical_name,
        'search_terms_count': len(search_terms),
        'existing_filter': existing_filter,
    })

    # Step 3: Check cache again with the canonical key
    cached = check_disease_cache(canonical_key)
    if cached:
        logger.info(
            f"Cache hit after standardization "
            f"('{user_input}' -> key: {canonical_key})"
        )
        add_alias_to_disease_cache(canonical_key, user_input)
        stats = _query_subgraph_stats(canonical_key)
        emit('status', {'phase': 'cache_hit', 'message': f"Found in cache: {canonical_key}"})
        return {
            "disease_key": canonical_key,
            "canonical_name": canonical_name,
            "user_input": user_input,
            "cached": True,
            "cache_info": cached,
            "subgraph_stats": stats,
        }

    logger.info(f"Not in cache — loading DisGeNET for '{canonical_name}'...")
    emit('status', {'phase': 'disgenet', 'message': f"Querying DisGeNET for '{canonical_name}'..."})

    # Step 4: Determine filter file
    if existing_filter:
        filter_path = str(PROJECT_ROOT / KNOWN_FILTERS[existing_filter])
        logger.info(f"Using existing filter: {KNOWN_FILTERS[existing_filter]}")
        temp_filter = False
    else:
        filter_path = _write_temp_filter(search_terms)
        temp_filter = True

    try:
        # Step 5: Run DisGeNET (capped at 200 disease IDs / 2 min)
        disgenet_result = _run_disgenet(canonical_key, filter_path)
        gda_count = disgenet_result['gda_count']
        partial = disgenet_result['partial']

        emit('status', {
            'phase': 'disgenet_done',
            'message': f"DisGeNET: {gda_count} gene-disease associations loaded"
                       f"{' (partial)' if partial else ''}",
            'gda_count': gda_count,
            'partial': partial,
        })

        # Step 6: Cache result with aliases (only if we got actual data)
        if gda_count == 0:
            # Delete any stale cache entry so the user can retry later
            from src.utils import delete_disease_cache
            delete_disease_cache(canonical_key)
            logger.warning(f"DisGeNET returned 0 results for '{canonical_name}' — not caching")
            emit('status', {
                'phase': 'error',
                'message': f"DisGeNET returned 0 results for '{canonical_name}'. "
                           f"No data was cached. Try a different disease name or check DisGeNET availability.",
            })
            return {
                "disease_key": canonical_key,
                "canonical_name": canonical_name,
                "user_input": user_input,
                "cached": False,
                "error": f"DisGeNET returned 0 results for '{canonical_name}'",
                "subgraph_stats": {},
            }

        emit('status', {'phase': 'caching', 'message': 'Caching results...'})
        aliases = [user_input.lower()]
        if canonical_name.lower() != user_input.lower():
            aliases.append(canonical_name.lower())
        if canonical_key != user_input.lower():
            aliases.append(canonical_key)
        cache_entry = add_to_disease_cache(canonical_key, {
            'canonical_name': canonical_name,
            'filter_file': filter_path if not temp_filter else f'agent:{canonical_key}',
            'disgenet_rows': gda_count,
            'sources_loaded': ['DisGeNET'],
            'aliases': aliases,
        })
        logger.info(f"Added to DiseaseCache: {cache_entry.get('disease_name')}")

    finally:
        if temp_filter:
            try:
                os.unlink(filter_path)
            except OSError:
                pass

    # Step 7: Query and return stats
    emit('status', {'phase': 'stats', 'message': 'Querying subgraph statistics...'})
    stats = _query_subgraph_stats(canonical_key)

    result = {
        "disease_key": canonical_key,
        "canonical_name": canonical_name,
        "user_input": user_input,
        "cached": False,
        "partial": partial,
        "search_terms_count": len(search_terms),
        "disgenet_edges_loaded": gda_count,
        "subgraph_stats": stats,
    }

    logger.info(f"\nResult: {json.dumps(result, indent=2)}")
    return result


def list_cached():
    """List all diseases in the DiseaseCache."""
    from src.utils import _get_neo4j_driver

    driver = _get_neo4j_driver()
    if not driver:
        print("NEO4J_PASSWORD not set")
        return

    try:
        with driver.session() as s:
            results = s.run(
                "MATCH (c:DiseaseCache) "
                "RETURN c.disease_name AS name, "
                "       c.canonical_name AS canonical, "
                "       c.aliases AS aliases, "
                "       c.disgenet_rows AS rows, "
                "       c.date_loaded AS loaded, "
                "       c.sources_loaded AS sources "
                "ORDER BY c.date_loaded DESC"
            )
            records = list(results)

        if not records:
            print("No diseases in cache.")
            return

        print(f"\n{'Key':<20} {'Canonical Name':<30} {'Rows':>8} {'Loaded':<20} Aliases")
        print("-" * 110)
        for rec in records:
            name = rec['name'] or '?'
            canonical = rec['canonical'] or name
            rows = rec['rows'] or 0
            loaded = (rec['loaded'] or '?')[:19]
            aliases = ', '.join(rec['aliases'][:5]) if rec['aliases'] else '-'
            if rec['aliases'] and len(rec['aliases']) > 5:
                aliases += f' (+{len(rec["aliases"]) - 5} more)'
            print(f"{name:<20} {canonical:<30} {rows:>8,} {loaded:<20} {aliases}")
        print()

    finally:
        driver.close()


def main():
    parser = argparse.ArgumentParser(
        description="CardioKB Disease Agent — AI-powered disease graph builder"
    )
    parser.add_argument(
        'disease', nargs='?',
        help='Disease name to process (e.g., "parkinson\'s disease", "PD", "CVD")'
    )
    parser.add_argument(
        '--list-cached', action='store_true',
        help="List all diseases in the DiseaseCache"
    )

    args = parser.parse_args()

    if args.list_cached:
        list_cached()
        return

    if not args.disease:
        parser.print_help()
        sys.exit(1)

    result = run_agent(args.disease)
    print(f"\n{'='*60}")
    print(json.dumps(result, indent=2, default=str))
    print(f"{'='*60}")


if __name__ == '__main__':
    sys.path.insert(0, str(PROJECT_ROOT))
    main()
