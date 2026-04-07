"""
CardioKB Database Agent — Autonomous parser generator for new data sources.

Accepts a database name and URL, uses Claude to generate a complete parser
(extending BaseParser), ontology configs, and pipeline registration, then
runs the parser and validates the results.

Usage:
    python src/database_agent.py "Reactome" "https://reactome.org/download/current/NCBI2Reactome.txt"

Or via API:
    POST /api/agent/add-database (see src/api.py)
"""

import ast
import json
import logging
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger('cardiokb.database_agent')

PROJECT_ROOT = Path(__file__).parent.parent
MODEL = os.getenv('DATABASE_AGENT_MODEL', 'claude-haiku-4-5-20251001')


def _get_client():
    """Create an Anthropic client."""
    import anthropic
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=api_key)


def _read_skill():
    """Read the database-parsing SKILL.md."""
    path = PROJECT_ROOT / '.claude' / 'skills' / 'database-parsing' / 'SKILL.md'
    return path.read_text()


def _list_existing_parsers():
    """List existing parser files and their class names."""
    parsers_dir = PROJECT_ROOT / 'src' / 'parsers'
    parsers = []
    for f in sorted(parsers_dir.glob('*_parser.py')):
        parsers.append(f.name)
    return parsers


def _read_base_parser():
    """Read BaseParser source for context."""
    path = PROJECT_ROOT / 'src' / 'parsers' / 'base_parser.py'
    return path.read_text()


def _read_example_parser():
    """Read ReactomeParser as an example of a simple, well-structured parser."""
    path = PROJECT_ROOT / 'src' / 'parsers' / 'reactome_parser.py'
    return path.read_text()


def _read_example_ontology_config():
    """Read Reactome ontology configs as an example."""
    from src.ontology_configs import ONTOLOGY_CONFIGS
    examples = {}
    for key, val in ONTOLOGY_CONFIGS.items():
        if key.startswith('reactome.'):
            examples[key] = val
    return json.dumps(examples, indent=2, default=str)


def _sanitize_name(name: str) -> str:
    """Convert a database name to a safe snake_case identifier."""
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', name)
    return '_'.join(clean.lower().split())


def _download_sample(db_url: str, source_key: str, emit=None) -> dict:
    """
    Download the first portion of a file to discover column names and format.

    Returns dict with:
        - columns: list of column names (or None if not tabular)
        - sample_rows: first few rows as text
        - format: detected format ('tsv', 'csv', 'json', 'xml', 'obo', 'unknown')
        - error: str if download failed
    """
    import io
    import requests
    import gzip

    emit = emit or (lambda e, d: None)
    emit('status', {'phase': 'sampling', 'message': f'Downloading sample from {db_url}...'})

    result = {'columns': None, 'sample_rows': '', 'format': 'unknown', 'error': None}

    try:
        # Stream just the first 64KB to detect format and columns
        resp = requests.get(db_url, stream=True, timeout=30,
                            headers={'User-Agent': 'CardioKB/1.0'})
        resp.raise_for_status()

        chunks = []
        downloaded = 0
        limit = 64 * 1024  # 64KB
        for chunk in resp.iter_content(chunk_size=8192):
            chunks.append(chunk)
            downloaded += len(chunk)
            if downloaded >= limit:
                break
        resp.close()

        raw_bytes = b''.join(chunks)

        # Decompress gzip if needed (handle partial downloads)
        if db_url.endswith('.gz') or raw_bytes[:2] == b'\x1f\x8b':
            try:
                # For partial gzip, use streaming decompressor
                decompressor = gzip.GzipFile(fileobj=io.BytesIO(raw_bytes))
                raw_bytes = decompressor.read(limit)
            except (EOFError, OSError):
                # Partial gzip is expected — use what we got
                try:
                    decompressor = gzip.GzipFile(fileobj=io.BytesIO(raw_bytes))
                    parts = []
                    while True:
                        try:
                            chunk = decompressor.read(4096)
                            if not chunk:
                                break
                            parts.append(chunk)
                        except (EOFError, OSError):
                            break
                    if parts:
                        raw_bytes = b''.join(parts)
                except Exception:
                    pass

        # Try to decode as text
        try:
            text = raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text = raw_bytes.decode('latin-1')
            except Exception:
                result['error'] = 'Could not decode file as text'
                return result

        lines = text.split('\n')

        # Detect format
        if db_url.endswith(('.json', '.json.gz')):
            result['format'] = 'json'
            result['sample_rows'] = '\n'.join(lines[:20])
        elif db_url.endswith(('.xml', '.xml.gz')):
            result['format'] = 'xml'
            result['sample_rows'] = '\n'.join(lines[:30])
        elif db_url.endswith('.obo'):
            result['format'] = 'obo'
            result['sample_rows'] = '\n'.join(lines[:30])
        else:
            # Try TSV/CSV detection
            # Find the header line: skip blank lines and pure comment lines,
            # but treat a line starting with '#' that contains delimiters as a header
            # (e.g., ClinVar's "#AlleleID\tType\t...")
            header_idx = 0
            for i, line in enumerate(lines):
                if line.strip() == '':
                    header_idx = i + 1
                elif line.startswith('#') and '\t' not in line and ',' not in line:
                    header_idx = i + 1
                else:
                    break

            if header_idx < len(lines):
                header_line = lines[header_idx]
                tab_count = header_line.count('\t')
                comma_count = header_line.count(',')

                if tab_count >= 1:
                    result['format'] = 'tsv'
                    cols = header_line.split('\t')
                    # Preserve original column names exactly as they appear,
                    # including '#' prefixes (e.g., "#AlleleID" stays "#AlleleID").
                    # pd.read_csv() will read them the same way, so Claude must
                    # generate code using these exact names.
                    result['columns'] = cols
                elif comma_count >= 1:
                    result['format'] = 'csv'
                    # Use csv module for proper parsing
                    import csv
                    reader = csv.reader(io.StringIO(header_line))
                    result['columns'] = next(reader, [])
                elif ' ' in header_line.strip():
                    # Space-delimited (e.g., STRING)
                    result['format'] = 'space-delimited'
                    result['columns'] = header_line.split()
                else:
                    result['format'] = 'unknown'

            # Capture first few data lines as sample
            sample_lines = lines[header_idx:header_idx + 6]
            result['sample_rows'] = '\n'.join(sample_lines)

        emit('status', {
            'phase': 'sampled',
            'message': f'Detected format: {result["format"]}, '
                       f'columns: {len(result["columns"]) if result["columns"] else "N/A"}',
        })

    except Exception as e:
        result['error'] = f'Sample download failed: {e}'
        emit('status', {'phase': 'sample_error', 'message': result['error']})

    return result


def _extract_code_block(text: str, label: str = '') -> str:
    """Extract the first code block from Claude's response."""
    # Try labeled fence first
    pattern = r'```(?:python|py)?\s*\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        code = matches[0].strip()
    else:
        # Fallback: return text as-is (it might be raw code)
        code = text.strip()
    # Safety: strip any trailing fence markers that slipped through
    while code.endswith('```'):
        code = code[:-3].rstrip()
    return code


def _extract_json_block(text: str) -> str:
    """Extract JSON from Claude's response."""
    pattern = r'```(?:json)?\s*\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return matches[0].strip()
    # Try raw JSON
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        return text[start:end + 1]
    return text.strip()


def _validate_column_refs(parser_code: str, actual_columns: list) -> list:
    """
    Check that column references in generated parser code match actual file headers.

    Scans for df['col'], df["col"], subset=['col'], rename(columns={'col': ...}),
    and row.get('col') patterns. Returns a list of mismatched column names.
    """
    if not actual_columns:
        return []

    col_set = set(actual_columns)

    # Patterns that reference source column names (before rename):
    #   df['ColName'], df["ColName"], subset=['ColName'], row.get('ColName')
    #   rename(columns={'ColName': ...}), .get('ColName'), ['ColName'] in list context
    patterns = [
        r"df\[(['\"])(.+?)\1\]",                           # df['col'] or df["col"]
        r"subset\s*=\s*\[(['\"])(.+?)\1\]",                # subset=['col']
        r"row\.get\((['\"])(.+?)\1",                        # row.get('col')
        r"rename\s*\(\s*columns\s*=\s*\{(['\"])(.+?)\1",   # rename(columns={'col': ...})
    ]
    # For rename, extract all keys from the dict
    rename_pattern = r"rename\s*\(\s*columns\s*=\s*\{([^}]+)\}"

    referenced_cols = set()

    for pattern in patterns:
        for m in re.finditer(pattern, parser_code):
            referenced_cols.add(m.group(2))

    # Also extract all keys from rename(columns={...}) dicts
    for m in re.finditer(rename_pattern, parser_code):
        dict_body = m.group(1)
        for key_match in re.finditer(r"(['\"])(.+?)\1\s*:", dict_body):
            referenced_cols.add(key_match.group(2))

    # Filter: only flag references that look like source columns (not output column names).
    # Output columns (after rename) are camelCase — source columns are typically
    # PascalCase, ALLCAPS, or #-prefixed. We flag any referenced column that isn't
    # in the actual column set AND isn't a known output/derived name.
    mismatches = []
    for col in referenced_cols:
        if col in col_set:
            continue
        # Skip clearly-derived output names (camelCase, snake_case patterns)
        if col[0].islower() or '_' in col:
            continue
        mismatches.append(col)

    return mismatches


def generate_parser(db_name: str, db_url: str, emit=None) -> dict:
    """
    Use Claude to generate a parser for a new database.

    Downloads a sample of the file first to discover actual column names,
    then passes them to Claude to prevent hallucination.

    Returns dict with:
        - parser_code: str
        - ontology_configs: dict
        - parser_class_name: str
        - parser_file_name: str
        - source_key: str
    """
    emit = emit or (lambda e, d: None)

    client = _get_client()
    skill_md = _read_skill()
    base_parser_src = _read_base_parser()
    example_parser = _read_example_parser()
    example_config = _read_example_ontology_config()
    existing_parsers = _list_existing_parsers()
    source_key = _sanitize_name(db_name)

    # Download a sample to discover actual column names and format
    sample = _download_sample(db_url, source_key, emit)

    sample_section = ""
    if sample.get('error'):
        sample_section = f"(Could not download sample: {sample['error']})"
    else:
        sample_section = f"**Detected format**: {sample['format']}\n"
        if sample['columns']:
            col_list = sample['columns']
            sample_section += f"**Actual column names** (from file header): {col_list}\n\n"
            sample_section += (
                "⚠️ STRICT RULE: You MUST ONLY use these exact column names: "
                f"{col_list}. Do NOT invent, combine, or guess column names that "
                "are not in this list. If you need a derived field (e.g., genomic "
                "position), build it from the individual columns listed above "
                "(e.g., Chromosome, Start, Stop) — never reference a column name "
                "like 'Position(GRCh38)' that does not appear in this list.\n"
            )
        if sample['sample_rows']:
            sample_section += f"\n**First rows of the file**:\n```\n{sample['sample_rows']}\n```"

    system_prompt = textwrap.dedent("""\
        You are an expert biomedical data engineer building parsers for CardioKB,
        a cardiovascular disease knowledge graph stored in Neo4j. You write clean,
        production-quality Python code.

        You MUST follow the SKILL.md guide exactly. Every parser extends BaseParser
        and implements download_data(), parse_data(), and get_schema().

        Key rules:
        - Use self.download_file(url, filename) for downloads
        - Use self.read_tsv() / self.read_csv() for file I/O
        - parse_data() returns Dict[str, pd.DataFrame]
        - Each DataFrame key becomes a TSV filename in data/processed/
        - Node DataFrames need an IRI/ID column and property columns
        - Relationship DataFrames need subject ID, object ID, and optional properties
        - All relationships MUST have a source_label in the ontology config
        - Use existing node types (Gene, Disease, Drug, Pathway, etc.) when possible
        - Match on existing node properties (xrefNcbiGene, xrefDiseaseOntology, etc.)
        - Set merge: True for node types that already exist in the graph
        - CRITICAL: Only use column names that actually exist in the source data.
          A sample of the file with actual column names is provided below.
          Do NOT invent or guess column names.
        - COLUMN NAMES WITH '#': Some bioinformatics files have column names that
          start with '#' (e.g., '#AlleleID'). pd.read_csv() preserves the '#' in
          the column name. You MUST use the exact column name including the '#'
          prefix when referencing it in code (e.g., df['#AlleleID']).
          Store such columns as a class constant for clarity.
        - ID COLUMNS AS STRINGS: All identifier columns used as node IRI or
          relationship match keys MUST be explicitly cast to str in your parser
          (e.g., df['id'] = df['id'].astype(str)). Neo4j MERGE requires exact type
          matching — an int ID will not match a string ID. Always use string.
        - PERFORMANCE: Use vectorized pandas operations (rename, assign, explode,
          str.split, etc.) for data transformations. NEVER use df.iterrows() or
          row-by-row iteration — these are too slow for files with millions of rows.
    """)

    user_prompt = textwrap.dedent(f"""\
        Generate a complete parser for this database:

        Database name: {db_name}
        URL: {db_url}
        Source key (for file naming): {source_key}

        ## File Sample (downloaded from the actual URL)

        {sample_section}

        ## Context

        ### SKILL.md (integration guide):
        {skill_md}

        ### BaseParser (base class):
        ```python
        {base_parser_src}
        ```

        ### Example parser (ReactomeParser):
        ```python
        {example_parser}
        ```

        ### Example ontology configs (Reactome):
        ```json
        {example_config}
        ```

        ### Existing parsers:
        {json.dumps(existing_parsers)}

        ## Instructions

        CRITICAL: You MUST ONLY reference column names that appear in the "Actual column
        names" list above. Do NOT invent or combine column names. If a column you expect
        does not exist, use the available columns to derive the information you need, or
        skip that field entirely. Every `df['column_name']` and every `rename(columns=...)`
        key in your parser MUST match an actual column from the list above.

        Generate:

        1. **PARSER CODE**: A complete Python parser file. The class name should be
           `{db_name.replace(' ', '')}Parser`. Include proper imports, docstring with
           source URL and access type, and handle edge cases (file not found, etc.).

        2. **ONTOLOGY CONFIGS**: A JSON object with ontology config entries for every
           DataFrame your parser produces. Use the format:
           `"{source_key}.<dataframe_key>": {{config...}}`

        Return your response in this EXACT format:

        PARSER_CODE:
        ```python
        <full parser code>
        ```

        ONTOLOGY_CONFIGS:
        ```json
        {{<ontology config entries>}}
        ```

        PARSER_CLASS_NAME: <ClassName>
    """)

    emit('status', {
        'phase': 'generating',
        'message': f'Asking Claude to generate parser for {db_name}...',
    })

    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = next(
        (b.text for b in response.content if b.type == "text"), ""
    ).strip()

    # Parse response sections
    parser_code = ''
    ontology_json = ''
    class_name = ''

    # Extract parser code
    if 'PARSER_CODE:' in text:
        after_parser = text.split('PARSER_CODE:', 1)[1]
        before_next = after_parser.split('ONTOLOGY_CONFIGS:', 1)[0] if 'ONTOLOGY_CONFIGS:' in after_parser else after_parser
        parser_code = _extract_code_block(before_next)

    # Extract ontology configs
    if 'ONTOLOGY_CONFIGS:' in text:
        after_config = text.split('ONTOLOGY_CONFIGS:', 1)[1]
        before_next = after_config.split('PARSER_CLASS_NAME:', 1)[0] if 'PARSER_CLASS_NAME:' in after_config else after_config
        ontology_json = _extract_json_block(before_next)

    # Extract class name
    if 'PARSER_CLASS_NAME:' in text:
        class_line = text.split('PARSER_CLASS_NAME:', 1)[1].strip().split('\n')[0].strip()
        class_name = class_line.strip('` ')

    # Fallback class name from code
    if not class_name and parser_code:
        m = re.search(r'class\s+(\w+Parser)', parser_code)
        if m:
            class_name = m.group(1)

    if not class_name:
        class_name = f"{db_name.replace(' ', '')}Parser"

    # Parse ontology configs
    try:
        ontology_configs = json.loads(ontology_json)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse ontology configs JSON, using empty dict")
        ontology_configs = {}

    parser_file_name = f"{source_key}_parser.py"

    # Validate column references in generated code against actual file headers
    actual_cols = sample.get('columns') or []
    if parser_code and actual_cols:
        mismatches = _validate_column_refs(parser_code, actual_cols)
        if mismatches:
            emit('status', {
                'phase': 'column_mismatch',
                'message': (
                    f'Column mismatch detected: {mismatches} not in actual '
                    f'headers. Asking Claude to fix...'
                ),
            })
            logger.warning(f"Column mismatch in generated code: {mismatches}")

            # Ask Claude to fix the column references
            fix_prompt = (
                f"The parser code you generated references these column names "
                f"that do NOT exist in the actual file headers:\n\n"
                f"  Mismatched: {mismatches}\n"
                f"  Actual columns: {actual_cols}\n\n"
                f"Rewrite the COMPLETE parser code, using ONLY column names "
                f"from the actual columns list. Do NOT rename or strip any "
                f"characters from column names (e.g., keep '#AlleleID' as-is).\n\n"
                f"Return ONLY the corrected parser code in a python code block."
            )
            try:
                fix_response = client.messages.create(
                    model=MODEL,
                    max_tokens=8192,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": user_prompt},
                        {"role": "assistant", "content": text},
                        {"role": "user", "content": fix_prompt},
                    ],
                )
                fix_text = next(
                    (b.text for b in fix_response.content if b.type == "text"), ""
                ).strip()
                fixed_code = _extract_code_block(fix_text)
                if fixed_code:
                    # Validate again
                    remaining = _validate_column_refs(fixed_code, actual_cols)
                    if len(remaining) < len(mismatches):
                        parser_code = fixed_code
                        logger.info(
                            f"Column fix applied. Remaining mismatches: {remaining}"
                        )
                    else:
                        logger.warning(
                            f"Fix attempt did not reduce mismatches: {remaining}"
                        )
            except Exception as e:
                logger.warning(f"Column fix attempt failed: {e}")

    # Check for iterrows() anti-pattern
    if parser_code and 'iterrows()' in parser_code:
        emit('status', {
            'phase': 'perf_warning',
            'message': 'Generated code uses iterrows() — requesting vectorized rewrite...',
        })
        logger.warning("Generated parser uses iterrows() — requesting fix")
        perf_prompt = (
            "The parser code uses df.iterrows() which is extremely slow for "
            "large files (millions of rows). Rewrite the COMPLETE parser code "
            "using vectorized pandas operations instead (rename, assign, explode, "
            "str.split, dropna, etc.). Do NOT use iterrows() or any row-by-row "
            "loop.\n\nReturn ONLY the corrected parser code in a python code block."
        )
        try:
            perf_response = client.messages.create(
                model=MODEL,
                max_tokens=8192,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": perf_prompt},
                ],
            )
            perf_text = next(
                (b.text for b in perf_response.content if b.type == "text"), ""
            ).strip()
            perf_code = _extract_code_block(perf_text)
            if perf_code and 'iterrows()' not in perf_code:
                parser_code = perf_code
                logger.info("Replaced iterrows() code with vectorized version")
        except Exception as e:
            logger.warning(f"Performance fix attempt failed: {e}")

    return {
        'parser_code': parser_code,
        'ontology_configs': ontology_configs,
        'parser_class_name': class_name,
        'parser_file_name': parser_file_name,
        'source_key': source_key,
        'raw_response_length': len(text),
    }


def _validate_syntax(parser_code: str, parser_file_name: str, emit=None) -> str:
    """
    Check parser code for syntax errors by compiling it.

    Returns the (possibly fixed) parser code. If a syntax error is found,
    asks Claude to fix it up to 2 times before giving up.
    """
    emit = emit or (lambda e, d: None)
    max_attempts = 2

    for attempt in range(max_attempts + 1):
        try:
            compile(parser_code, parser_file_name, 'exec')
            if attempt > 0:
                emit('status', {
                    'phase': 'syntax_fixed',
                    'message': f'Syntax error fixed on attempt {attempt}',
                })
                logger.info(f"Syntax error fixed on attempt {attempt}")
            return parser_code
        except SyntaxError as e:
            if attempt == max_attempts:
                emit('status', {
                    'phase': 'syntax_error',
                    'message': f'Syntax error persists after {max_attempts} fix attempts: {e}',
                })
                logger.error(f"Unfixable syntax error: {e}")
                return parser_code

            emit('status', {
                'phase': 'syntax_error',
                'message': f'Syntax error at line {e.lineno}: {e.msg} — asking Claude to fix...',
            })
            logger.warning(f"Syntax error in generated code: line {e.lineno}: {e.msg}")

            # Show context around the error
            lines = parser_code.split('\n')
            start = max(0, (e.lineno or 1) - 3)
            end = min(len(lines), (e.lineno or 1) + 2)
            context = '\n'.join(f"  {i+1}: {lines[i]}" for i in range(start, end))

            try:
                client = _get_client()
                fix_response = client.messages.create(
                    model=MODEL,
                    max_tokens=8192,
                    system=(
                        "You are fixing a Python syntax error. Return ONLY the "
                        "complete corrected Python code in a ```python code block. "
                        "Do not explain."
                    ),
                    messages=[{"role": "user", "content": (
                        f"This Python file has a syntax error:\n\n"
                        f"Error: line {e.lineno}: {e.msg}\n\n"
                        f"Context around error:\n{context}\n\n"
                        f"Full code:\n```python\n{parser_code}\n```\n\n"
                        f"Fix the syntax error and return the complete corrected code."
                    )}],
                )
                fix_text = next(
                    (b.text for b in fix_response.content if b.type == "text"), ""
                ).strip()
                fixed = _extract_code_block(fix_text)
                if fixed:
                    parser_code = fixed
            except Exception as fix_err:
                logger.warning(f"Syntax fix attempt failed: {fix_err}")
                return parser_code

    return parser_code


def _validate_config_keys(source_key: str, new_configs: dict, emit=None) -> dict:
    """
    Check for duplicate config keys against existing ONTOLOGY_CONFIGS.

    Removes duplicates from new_configs (the existing entry wins unless it
    belongs to the same source). Returns the deduplicated configs.
    """
    emit = emit or (lambda e, d: None)

    import importlib
    import src.ontology_configs as _oc_mod
    importlib.reload(_oc_mod)
    existing = _oc_mod.ONTOLOGY_CONFIGS

    dupes = []
    for key in list(new_configs.keys()):
        if key in existing:
            # Same source re-run is OK (will be overwritten by add_ontology_configs)
            if not key.startswith(f'{source_key}.'):
                dupes.append(key)
                del new_configs[key]

    if dupes:
        emit('status', {
            'phase': 'config_dedup',
            'message': f'Removed {len(dupes)} duplicate config key(s): {dupes}',
        })
        logger.warning(f"Removed duplicate config keys: {dupes}")

    return new_configs


def _validate_config_vs_output(source_key: str, ontology_configs: dict,
                                parsed_data: dict, emit=None) -> dict:
    """
    Validate that ontology config column references match actual parser output.

    For each config entry, checks:
    - Node configs: iri_column_name and data_property_map keys exist in the DataFrame
    - Relationship configs: subject_column_name and object_column_name exist

    Auto-fixes mismatches by renaming config references to the closest matching
    actual column (edit-distance based).
    """
    emit = emit or (lambda e, d: None)

    issues = []
    for config_key, config in ontology_configs.items():
        if not config_key.startswith(f'{source_key}.'):
            continue

        _, data_name = config_key.split('.', 1)
        df = parsed_data.get(data_name)
        if df is None:
            continue

        actual_cols = set(df.columns)
        pc = config.get('parse_config', {})

        if config.get('data_type') == 'node':
            # Check IRI column
            iri_col = pc.get('iri_column_name', '')
            if iri_col and iri_col not in actual_cols:
                best = _closest_column(iri_col, actual_cols)
                if best:
                    issues.append(f'{config_key}: iri_column_name {iri_col!r} -> {best!r}')
                    pc['iri_column_name'] = best

            # Check data_property_map keys
            prop_map = pc.get('data_property_map', {})
            fixed_map = {}
            for src_col, neo4j_prop in prop_map.items():
                if src_col in actual_cols:
                    fixed_map[src_col] = neo4j_prop
                else:
                    best = _closest_column(src_col, actual_cols)
                    if best:
                        issues.append(f'{config_key}: prop map {src_col!r} -> {best!r}')
                        fixed_map[best] = neo4j_prop
                    else:
                        issues.append(f'{config_key}: dropped missing prop {src_col!r}')
            pc['data_property_map'] = fixed_map

        elif config.get('data_type') == 'relationship':
            for prefix in ('subject', 'object'):
                col_key = f'{prefix}_column_name'
                col = pc.get(col_key, '')
                if col and col not in actual_cols:
                    best = _closest_column(col, actual_cols)
                    if best:
                        issues.append(f'{config_key}: {col_key} {col!r} -> {best!r}')
                        pc[col_key] = best

            # Check data_property_map keys
            prop_map = pc.get('data_property_map', {})
            fixed_map = {}
            for src_col, neo4j_prop in prop_map.items():
                if src_col in actual_cols:
                    fixed_map[src_col] = neo4j_prop
                else:
                    best = _closest_column(src_col, actual_cols)
                    if best:
                        issues.append(f'{config_key}: prop map {src_col!r} -> {best!r}')
                        fixed_map[best] = neo4j_prop
                    else:
                        issues.append(f'{config_key}: dropped missing prop {src_col!r}')
            pc['data_property_map'] = fixed_map

    if issues:
        emit('status', {
            'phase': 'config_column_fix',
            'message': f'Fixed {len(issues)} config-vs-output column mismatch(es)',
            'fixes': issues,
        })
        logger.warning(f"Config column fixes: {issues}")

        # Re-write ontology_configs.py with the corrected configs
        source_configs = {
            k: v for k, v in ontology_configs.items()
            if k.startswith(f'{source_key}.')
        }
        if source_configs:
            add_ontology_configs(source_key, source_configs)
            logger.info("Re-wrote ontology configs with column fixes")

    return ontology_configs


def _closest_column(target: str, candidates: set, threshold: float = 0.5) -> str:
    """Find the closest matching column name using normalized edit distance."""
    if not candidates:
        return ''

    target_lower = target.lower().replace('_', '').replace(' ', '')
    best_col = ''
    best_score = 0.0

    for col in candidates:
        col_lower = col.lower().replace('_', '').replace(' ', '')
        # Simple character overlap ratio
        common = sum(1 for c in target_lower if c in col_lower)
        max_len = max(len(target_lower), len(col_lower), 1)
        score = common / max_len
        if score > best_score:
            best_score = score
            best_col = col

    return best_col if best_score >= threshold else ''


def save_parser(parser_code: str, parser_file_name: str) -> Path:
    """Save generated parser code to src/parsers/."""
    path = PROJECT_ROOT / 'src' / 'parsers' / parser_file_name
    path.write_text(parser_code)
    logger.info(f"Saved parser to {path}")
    return path


def _syntax_check_ontology_configs() -> Optional[str]:
    """Parse ontology_configs.py and return error string, or None if valid."""
    config_path = PROJECT_ROOT / 'src' / 'ontology_configs.py'
    try:
        ast.parse(config_path.read_text())
        return None
    except SyntaxError as e:
        return f"{e.msg} (line {e.lineno})"


def add_ontology_configs(source_key: str, configs: dict) -> bool:
    """Append ontology configs to src/ontology_configs.py.

    If entries for this source_key already exist, they are removed first
    to avoid duplicates from re-runs.
    """
    config_path = PROJECT_ROOT / 'src' / 'ontology_configs.py'
    # Keep a backup so we can restore on syntax error
    backup = config_path.read_text()
    content = backup

    # Remove ALL existing auto-generated blocks for this source_key.
    # Match from the header comment through all config entries until the next
    # header block or the dict closing brace (stop before consuming `}`).
    block_pattern = (
        rf'\n    # =+\n'
        rf'    # {re.escape(source_key)} \(auto-generated by database agent\)\n'
        rf'    # =+\n'
        rf'(?:(?!    # =+)(?!}}\s*$).+\n)*'  # stop before next header OR closing brace
    )
    # Apply repeatedly in case there are multiple stale blocks
    prev = None
    while prev != content:
        prev = content
        content = re.sub(block_pattern, '\n', content, flags=re.MULTILINE)

    # Also remove any bare config entries for this source key (from previous runs)
    # that might not have the header comment. Use DOTALL for multi-line values.
    entry_pattern = rf"    '{re.escape(source_key)}\.[^']+': \{{[^}}]*\}},\n"
    content = re.sub(entry_pattern, '', content)

    # Find the closing brace of ONTOLOGY_CONFIGS dict
    # We'll add entries before the final closing }
    lines = content.rstrip().split('\n')

    # Build new config entries as Python code
    new_entries = []
    new_entries.append('')
    new_entries.append(f'    # =========================================================================')
    new_entries.append(f'    # {source_key} (auto-generated by database agent)')
    new_entries.append(f'    # =========================================================================')

    for key, config in configs.items():
        new_entries.append(f'    {repr(key)}: {{')
        for k, v in config.items():
            if isinstance(v, dict):
                new_entries.append(f'        {repr(k)}: {{')
                for dk, dv in v.items():
                    new_entries.append(f'            {repr(dk)}: {repr(dv)},')
                new_entries.append(f'        }},')
            else:
                new_entries.append(f'        {repr(k)}: {repr(v)},')
        new_entries.append(f'    }},')

    # Find the last '}' which closes ONTOLOGY_CONFIGS
    insert_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == '}':
            insert_idx = i
            break

    if insert_idx is None:
        # Closing brace was lost (e.g., regex removal consumed it) — re-add it
        logger.warning("ONTOLOGY_CONFIGS closing brace missing — re-adding")
        lines.append('}')
        insert_idx = len(lines) - 1

    # Insert before the closing brace
    for j, entry in enumerate(new_entries):
        lines.insert(insert_idx + j, entry)

    final_content = '\n'.join(lines) + '\n'
    config_path.write_text(final_content)

    # Syntax check — if invalid, restore backup and report failure
    err = _syntax_check_ontology_configs()
    if err:
        logger.error(f"ontology_configs.py syntax error after write: {err}")
        logger.info("Restoring backup of ontology_configs.py")
        config_path.write_text(backup)
        return False

    logger.info(f"Added {len(configs)} ontology config(s) to ontology_configs.py (syntax OK)")
    return True


def register_in_main(source_key: str, class_name: str, parser_file_name: str) -> bool:
    """Register the new parser in src/parsers/__init__.py and src/main.py."""
    module_name = parser_file_name.replace('.py', '')

    # 1. Add to src/parsers/__init__.py
    init_path = PROJECT_ROOT / 'src' / 'parsers' / '__init__.py'
    init_content = init_path.read_text()

    if class_name not in init_content:
        # Add import
        import_line = f"from .{module_name} import {class_name}"
        # Find the end of the last import statement (handling multi-line imports)
        lines = init_content.split('\n')
        last_import_end = 0
        in_multiline = False
        for i, line in enumerate(lines):
            if in_multiline:
                if ')' in line:
                    in_multiline = False
                    last_import_end = i
            elif line.startswith(('from ', 'import ')):
                if '(' in line and ')' not in line:
                    in_multiline = True
                else:
                    last_import_end = i
        lines.insert(last_import_end + 1, import_line)

        # Add to __all__
        all_close_idx = None
        for i, line in enumerate(lines):
            if line.strip() == ']':
                all_close_idx = i
                break
        if all_close_idx:
            lines.insert(all_close_idx, f"    '{class_name}',")

        init_path.write_text('\n'.join(lines))
        logger.info(f"Added {class_name} to src/parsers/__init__.py")

    # 2. Add import and registration to src/main.py (checked independently)
    main_path = PROJECT_ROOT / 'src' / 'main.py'
    main_content = main_path.read_text()
    main_lines = main_content.split('\n')
    main_modified = False

    # 2a. Add import in the 'from src.parsers import (...)' block
    import_present = any(class_name in line and 'import' in line
                         for line in main_lines)
    if not import_present:
        in_import = False
        last_parser_import_idx = 0
        for i, line in enumerate(main_lines):
            if 'from src.parsers import' in line:
                in_import = True
            if in_import:
                if line.strip().endswith(')'):
                    last_parser_import_idx = i
                    in_import = False
                    break
        main_lines.insert(last_parser_import_idx, f"    {class_name},")
        main_modified = True
        logger.info(f"Added {class_name} import to src/main.py")

    # 2b. Add registration in _get_parsers() — check independently of import
    registration_present = any(f"parsers['{source_key}']" in line
                               for line in main_lines)
    if not registration_present:
        for i, line in enumerate(main_lines):
            if '# Parsers requiring credentials' in line:
                registration = [
                    f"        parsers['{source_key}'] = {class_name}(",
                    f"            data_dir=str(self.raw_dir),",
                    f"        )",
                ]
                for j, reg_line in enumerate(registration):
                    main_lines.insert(i + j, reg_line)
                main_modified = True
                logger.info(f"Registered {class_name} in src/main.py _get_parsers()")
                break
        else:
            logger.warning(
                f"Could not find '# Parsers requiring credentials' marker "
                f"in main.py — {class_name} not registered in _get_parsers()"
            )

    if main_modified:
        main_path.write_text('\n'.join(main_lines))

    return True


def run_parser(source_key: str, class_name: str, parser_file_name: str, emit=None) -> dict:
    """Run just the new parser: download, parse, export TSVs."""
    import importlib
    import pandas as pd

    emit = emit or (lambda e, d: None)

    module_name = parser_file_name.replace('.py', '')

    emit('status', {
        'phase': 'running_parser',
        'message': f'Running {class_name}: download + parse + TSV export',
    })

    # Reload the parsers package and the specific parser module so that
    # back-to-back agent runs in the same Flask process pick up changes.
    try:
        # Reload __init__.py first (register_in_main added new imports there)
        parsers_pkg = 'src.parsers'
        if parsers_pkg in sys.modules:
            importlib.reload(sys.modules[parsers_pkg])

        full_module = f'src.parsers.{module_name}'
        if full_module in sys.modules:
            mod = importlib.reload(sys.modules[full_module])
        else:
            mod = importlib.import_module(full_module)
        ParserClass = getattr(mod, class_name)
    except Exception as e:
        return {'success': False, 'error': f'Failed to import {class_name}: {e}'}

    raw_dir = str(PROJECT_ROOT / 'data' / 'raw')
    parser = ParserClass(data_dir=raw_dir)

    # Step A: Download
    emit('status', {'phase': 'downloading', 'message': f'{class_name}: downloading data...'})
    try:
        dl_ok = parser.download_data()
        if not dl_ok:
            return {'success': False, 'error': 'download_data() returned False'}
    except Exception as e:
        return {'success': False, 'error': f'Download failed: {e}'}

    # Step B: Parse
    emit('status', {'phase': 'parsing_data', 'message': f'{class_name}: parsing data...'})
    try:
        parsed = parser.parse_data()
        if not parsed:
            return {'success': False, 'error': 'parse_data() returned empty dict'}
    except Exception as e:
        return {'success': False, 'error': f'Parse failed: {e}'}

    # Step C: Export TSVs
    proc_dir = PROJECT_ROOT / 'data' / 'processed' / source_key
    proc_dir.mkdir(parents=True, exist_ok=True)

    for name, df in parsed.items():
        out_path = proc_dir / f'{name}.tsv'
        df.to_csv(out_path, sep='\t', index=False)
        logger.info(f"  Exported {len(df)} rows -> {out_path}")

    # Gather TSV info
    tsv_info = {}
    for f in proc_dir.glob('*.tsv'):
        try:
            df = pd.read_csv(f, sep='\t', nrows=5)
            row_count = sum(1 for _ in open(f)) - 1
            tsv_info[f.name] = {
                'rows': row_count,
                'columns': list(df.columns),
            }
        except Exception as e:
            tsv_info[f.name] = {'error': str(e)}

    return {
        'success': True,
        'tsv_files': tsv_info,
        'parsed_data': parsed,
    }


def validate_id_mappings(source_key: str, emit=None) -> dict:
    """Run ID mapping validation for the new parser's TSV files."""
    emit = emit or (lambda e, d: None)

    emit('status', {
        'phase': 'validating_ids',
        'message': 'Validating ID mappings against Neo4j...',
    })

    proc_dir = PROJECT_ROOT / 'data' / 'processed' / source_key
    if not proc_dir.exists():
        return {'error': 'No processed directory found'}

    # Reload ontology configs to pick up newly added entries
    import importlib
    import src.ontology_configs as _oc_mod
    importlib.reload(_oc_mod)
    ONTOLOGY_CONFIGS = _oc_mod.ONTOLOGY_CONFIGS
    results = {}

    for config_key, config in ONTOLOGY_CONFIGS.items():
        if not config_key.startswith(f'{source_key}.'):
            continue
        if config.get('data_type') != 'relationship':
            continue

        pc = config.get('parse_config', {})
        tsv_name = config.get('source_filename', '')
        tsv_path = proc_dir / tsv_name

        if not tsv_path.exists():
            results[config_key] = {'error': f'{tsv_name} not found'}
            continue

        # Validate subject IDs
        subj_col = pc.get('subject_column_name')
        subj_node = pc.get('subject_node_type')
        subj_prop = pc.get('subject_match_property')

        obj_col = pc.get('object_column_name')
        obj_node = pc.get('object_node_type')
        obj_prop = pc.get('object_match_property')

        validation = {'config_key': config_key}

        for label, col, node_type, prop in [
            ('subject', subj_col, subj_node, subj_prop),
            ('object', obj_col, obj_node, obj_prop),
        ]:
            if not all([col, node_type, prop]):
                continue

            try:
                result = subprocess.run(
                    ['python', 'src/id_mapping.py',
                     '--validate', str(tsv_path),
                     '--id-col', col,
                     '--node', node_type,
                     '--prop', prop],
                    cwd=str(PROJECT_ROOT),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                validation[f'{label}_validation'] = result.stdout[-1000:]
            except Exception as e:
                validation[f'{label}_validation'] = f'Error: {e}'

        results[config_key] = validation

    return results


def verify_neo4j_load(source_key: str, source_label: str, emit=None) -> dict:
    """Verify edges were loaded into Neo4j."""
    emit = emit or (lambda e, d: None)

    emit('status', {
        'phase': 'verifying_neo4j',
        'message': f'Verifying Neo4j load for source: {source_label}...',
    })

    from src.utils import _get_neo4j_driver
    driver = _get_neo4j_driver()
    if not driver:
        return {'error': 'NEO4J_PASSWORD not set'}

    try:
        with driver.session() as session:
            result = session.run(
                "MATCH ()-[r]->() WHERE r.source = $source "
                "RETURN type(r) AS rel_type, count(r) AS count",
                source=source_label,
            )
            edge_counts = {}
            total = 0
            for rec in result:
                edge_counts[rec['rel_type']] = rec['count']
                total += rec['count']

            return {
                'source_label': source_label,
                'edge_counts': edge_counts,
                'total_edges': total,
            }
    except Exception as e:
        return {'error': str(e)}
    finally:
        driver.close()


def _load_single_source(source_key: str, parsed_data: dict, emit=None) -> bool:
    """Load a single parser's data into Neo4j via the existing loader."""
    emit = emit or (lambda e, d: None)

    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', '')
    if not password:
        emit('status', {'phase': 'neo4j_skip', 'message': 'NEO4J_PASSWORD not set — skipping Neo4j load'})
        return False

    import importlib
    from src.neo4j_loader import Neo4jLoader
    import src.ontology_configs as _oc_mod
    importlib.reload(_oc_mod)
    ONTOLOGY_CONFIGS = _oc_mod.ONTOLOGY_CONFIGS

    # Filter to only this source's configs so we don't re-load all 29 parsers
    source_configs = {
        k: v for k, v in ONTOLOGY_CONFIGS.items()
        if k.startswith(f'{source_key}.')
    }
    if not source_configs:
        emit('status', {'phase': 'neo4j_skip', 'message': f'No ontology configs found for {source_key}'})
        return False

    data_for_loader = {source_key: parsed_data}

    try:
        with Neo4jLoader(uri, username, password) as loader:
            loader.load_from_configs(data_for_loader, source_configs, None)
            stats = loader.get_stats()
            emit('status', {
                'phase': 'neo4j_loaded',
                'message': (
                    f'Neo4j: {stats["nodes_created"]} nodes created, '
                    f'{stats["nodes_merged"]} merged, '
                    f'{stats["relationships_merged"]} relationships'
                ),
            })
            logger.info(f"Neo4j load: {stats}")
        return True
    except Exception as e:
        logger.error(f"Neo4j load error: {e}")
        emit('status', {'phase': 'neo4j_error', 'message': f'Neo4j load error: {e}'})
        return False


def run_database_agent(db_name: str, db_url: str, on_progress=None) -> dict:
    """
    Main entry point for the database agent.

    Steps:
    1. Call Claude to generate parser + ontology config
    2. Validate parser syntax (auto-fix via Claude if errors found)
    3. Save parser to src/parsers/
    4. Validate & deduplicate ontology config keys, add to ontology_configs.py
    5. Register parser in main.py and __init__.py
    6. Run parser (download + parse + TSV export)
    6b. Validate ontology config column refs vs actual parser output (auto-fix)
    7. Validate ID mappings
    8. Load into Neo4j
    9. Verify Neo4j load
    """
    def emit(event: str, data: dict):
        if on_progress:
            on_progress(event, data)

    source_key = _sanitize_name(db_name)
    logger.info(f"Database agent: {db_name} ({db_url}) -> {source_key}")

    emit('status', {
        'phase': 'start',
        'message': f"Starting database agent for '{db_name}'...",
        'source_key': source_key,
    })

    # Step 1: Generate parser via Claude
    try:
        gen = generate_parser(db_name, db_url, emit)
    except Exception as e:
        emit('error', {'message': f'Parser generation failed: {e}'})
        return {'success': False, 'error': f'Generation failed: {e}'}

    parser_code = gen['parser_code']
    class_name = gen['parser_class_name']
    parser_file_name = gen['parser_file_name']
    ontology_configs = gen['ontology_configs']

    if not parser_code:
        emit('error', {'message': 'Claude returned empty parser code'})
        return {'success': False, 'error': 'Empty parser code'}

    emit('status', {
        'phase': 'generated',
        'message': f'Generated {class_name} ({len(parser_code)} chars, '
                   f'{len(ontology_configs)} config entries)',
        'class_name': class_name,
        'config_count': len(ontology_configs),
    })

    # Step 2: Validate syntax before saving
    emit('status', {'phase': 'validating_syntax', 'message': 'Checking parser for syntax errors...'})
    parser_code = _validate_syntax(parser_code, parser_file_name, emit)

    # Step 3: Save parser file
    emit('status', {'phase': 'saving', 'message': f'Saving {parser_file_name}...'})
    try:
        parser_path = save_parser(parser_code, parser_file_name)
    except Exception as e:
        emit('error', {'message': f'Failed to save parser: {e}'})
        return {'success': False, 'error': f'Save failed: {e}'}

    # Step 4: Add ontology configs (after dedup check)
    if ontology_configs:
        ontology_configs = _validate_config_keys(source_key, ontology_configs, emit)
        emit('status', {'phase': 'configs', 'message': 'Adding ontology configs...'})
        try:
            add_ontology_configs(source_key, ontology_configs)
        except Exception as e:
            emit('error', {'message': f'Failed to add configs: {e}'})
            return {'success': False, 'error': f'Config failed: {e}'}

    # Step 5: Register in main.py and __init__.py
    emit('status', {'phase': 'registering', 'message': 'Registering parser in pipeline...'})
    try:
        register_in_main(source_key, class_name, parser_file_name)
    except Exception as e:
        emit('error', {'message': f'Failed to register parser: {e}'})
        return {'success': False, 'error': f'Registration failed: {e}'}

    # Step 6: Run parser (download + parse + TSV export)
    emit('status', {'phase': 'parsing', 'message': 'Running parser (download + parse + export)...'})
    try:
        parse_result = run_parser(source_key, class_name, parser_file_name, emit)
    except Exception as e:
        emit('error', {'message': f'Parser failed: {e}'})
        return {'success': False, 'error': f'Parser failed: {e}'}

    if not parse_result['success']:
        emit('error', {
            'message': f'Parser run failed',
            'details': parse_result.get('error', ''),
        })
        return {
            'success': False,
            'error': 'Parser run failed',
            'parse_output': parse_result,
        }

    # Step 6b: Validate ontology config columns against actual parser output
    if ontology_configs and parse_result.get('parsed_data'):
        emit('status', {
            'phase': 'validating_columns',
            'message': 'Validating ontology config columns vs parser output...',
        })
        ontology_configs = _validate_config_vs_output(
            source_key, ontology_configs, parse_result['parsed_data'], emit
        )

    emit('status', {
        'phase': 'parsed',
        'message': f'Parser produced {len(parse_result["tsv_files"])} TSV file(s)',
        'tsv_files': parse_result['tsv_files'],
    })

    # Step 6: Validate ID mappings
    emit('status', {'phase': 'validating', 'message': 'Validating ID mappings...'})
    try:
        id_results = validate_id_mappings(source_key, emit)
    except Exception as e:
        id_results = {'error': str(e)}

    emit('status', {
        'phase': 'validated',
        'message': 'ID mapping validation complete',
        'id_mapping_results': id_results,
    })

    # Step 7: Determine source_label from ontology configs
    source_label = db_name
    for cfg in ontology_configs.values():
        if 'source_label' in cfg:
            source_label = cfg['source_label']
            break

    # Step 8: Load just this parser's data into Neo4j
    emit('status', {'phase': 'loading_neo4j', 'message': f'Loading {source_key} into Neo4j...'})
    neo4j_loaded = False
    try:
        neo4j_loaded = _load_single_source(source_key, parse_result.get('parsed_data', {}), emit)
    except Exception as e:
        logger.error(f"Neo4j load failed: {e}")
        emit('status', {'phase': 'neo4j_error', 'message': f'Neo4j load failed: {e}'})

    # Step 9: Verify Neo4j load
    neo4j_verification = {}
    if neo4j_loaded:
        try:
            neo4j_verification = verify_neo4j_load(source_key, source_label, emit)
        except Exception as e:
            neo4j_verification = {'error': str(e)}

    result = {
        'success': True,
        'source_key': source_key,
        'class_name': class_name,
        'parser_file': str(parser_path),
        'ontology_configs_count': len(ontology_configs),
        'tsv_files': parse_result['tsv_files'],
        'id_mapping_results': id_results,
        'neo4j_loaded': neo4j_loaded,
        'neo4j_verification': neo4j_verification,
    }

    emit('result', result)
    logger.info(f"Database agent complete: {json.dumps(result, indent=2, default=str)}")
    return result


def main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-7s | %(name)s | %(message)s',
    )

    parser = argparse.ArgumentParser(
        description="CardioKB Database Agent — auto-generate parsers for new data sources"
    )
    parser.add_argument('name', help='Database name (e.g., "PhosphoSitePlus")')
    parser.add_argument('url', help='Database URL or data download URL')
    parser.add_argument('--dry-run', action='store_true',
                        help='Generate parser code only, do not save or run')

    args = parser.parse_args()

    def on_progress(event, data):
        print(f"[{event}] {data.get('message', json.dumps(data, default=str))}")

    if args.dry_run:
        gen = generate_parser(args.name, args.url, on_progress)
        print("\n=== Generated Parser ===")
        print(gen['parser_code'])
        print("\n=== Ontology Configs ===")
        print(json.dumps(gen['ontology_configs'], indent=2))
        print(f"\nClass: {gen['parser_class_name']}")
        print(f"File:  {gen['parser_file_name']}")
    else:
        result = run_database_agent(args.name, args.url, on_progress)
        print(f"\n{'='*60}")
        print(json.dumps(result, indent=2, default=str))
        print(f"{'='*60}")


if __name__ == '__main__':
    sys.path.insert(0, str(PROJECT_ROOT))
    main()
