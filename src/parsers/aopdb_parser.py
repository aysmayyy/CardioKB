"""
AOPDBParser: Parser for AOP-DB (Adverse Outcome Pathway Database).

AOP-DB is a MySQL database containing information about adverse outcome
pathways, which describe causal relationships between molecular initiating
events and adverse outcomes.

Source: https://gaftp.epa.gov/EPADataCommons/ORD/AOP-DB/
Note: This is a large MySQL database that must be downloaded and imported.
Alternatively, the SQL dump file can be parsed directly without MySQL.

Adapted from AlzKB (disease-agnostic).
"""

import logging
import re
from pathlib import Path
from typing import Dict, Optional, List
import pandas as pd
from .base_parser import BaseParser
from ..ontology_configs import (
    AOPDB_TABLE_MAPPING,
    AOPDB_AOPS,
    AOPDB_PATHWAYS,
    AOPDB_GENE_PATHWAY_RELATIONSHIPS,
    AOPDB_DRUGS,
)

logger = logging.getLogger(__name__)

# Column definitions for each table (from CREATE TABLE statements in the dump)
CHEMICAL_INFO_COLUMNS = [
    'ChemicalName', 'ChemicalID', 'CasRN', 'Definition',
    'ParentIDs', 'TreeNumbers', 'ParentTreeNumbers', 'Synonyms',
    'DrugBankIDs', 'DTX_id',
]

PATHWAY_GENE_COLUMNS = [
    'id', 'source_geneID', 'entrez', 'path_id', 'path_name',
    'tax_id', 'int_source', 'ext_source',
]

AOP_INFO_COLUMNS = ['AOP_id', 'AOP_name']


def _parse_sql_values(values_str: str) -> List[list]:
    """
    Parse the VALUES portion of a MySQL INSERT statement into rows.

    Handles quoted strings with escaped quotes, NULL, and numeric values.
    E.g.: ('val1','val2',3,NULL),('val3','val4',5,NULL)

    Args:
        values_str: Everything after "VALUES " in the INSERT line.

    Returns:
        List of rows, each row is a list of Python values.
    """
    rows = []
    i = 0
    n = len(values_str)

    while i < n:
        # Find start of tuple
        if values_str[i] != '(':
            i += 1
            continue

        i += 1  # skip '('
        row = []

        while i < n:
            if values_str[i] == ')':
                i += 1  # skip ')'
                break
            elif values_str[i] == ',':
                i += 1  # skip comma between fields
                continue
            elif values_str[i] == '\'':
                # Quoted string - find end
                i += 1  # skip opening quote
                parts = []
                while i < n:
                    if values_str[i] == '\\' and i + 1 < n:
                        # Escaped character
                        parts.append(values_str[i + 1])
                        i += 2
                    elif values_str[i] == '\'' and i + 1 < n and values_str[i + 1] == '\'':
                        # Double-quote escape
                        parts.append('\'')
                        i += 2
                    elif values_str[i] == '\'':
                        i += 1  # skip closing quote
                        break
                    else:
                        parts.append(values_str[i])
                        i += 1
                row.append(''.join(parts))
            elif values_str[i:i+4] == 'NULL':
                row.append(None)
                i += 4
            else:
                # Numeric or other unquoted value
                j = i
                while j < n and values_str[j] not in (',', ')'):
                    j += 1
                token = values_str[i:j]
                # Try to convert to int/float
                try:
                    row.append(int(token))
                except ValueError:
                    try:
                        row.append(float(token))
                    except ValueError:
                        row.append(token)
                i = j

        rows.append(row)

    return rows


class AOPDBParser(BaseParser):
    """
    Parser for AOP-DB MySQL database.

    Connects to a MySQL database and extracts relevant
    adverse outcome pathway data, or parses directly from a SQL dump file.
    """

    def __init__(self, data_dir: Optional[str] = None,
                 mysql_config: Optional[Dict[str, str]] = None):
        """
        Initialize the AOP-DB parser.

        Args:
            data_dir: Directory for cached data
            mysql_config: MySQL connection configuration with keys:
                         'host', 'user', 'password', 'database'
        """
        super().__init__(data_dir)
        self.mysql_config = mysql_config or {}
        self.connection = None
        self._mysql_available = False
        self._sql_dump_path = self._find_sql_dump()

        if mysql_config:
            try:
                import mysql.connector
                self._mysql_available = True
                logger.info("MySQL connector is available")
            except ImportError:
                logger.warning("MySQL connector not available. Install with: pip install mysql-connector-python")

        if self._sql_dump_path:
            logger.info(f"Found SQL dump file: {self._sql_dump_path}")

    def _find_sql_dump(self) -> Optional[Path]:
        """Look for a SQL dump file in the AOP-DB data directory."""
        for f in self.source_dir.glob('*.sql'):
            return f
        return None

    def _get_table_names(self) -> List[str]:
        """Get list of available tables in the database."""
        if not self.connection:
            return []
        try:
            cursor = self.connection.cursor()
            cursor.execute("SHOW TABLES")
            tables = [table[0] for table in cursor.fetchall()]
            cursor.close()
            return tables
        except Exception as e:
            logger.error(f"Failed to get table names: {e}")
            return []

    def download_data(self) -> bool:
        """
        Check for AOP-DB database accessibility.

        Returns:
            True if database is accessible (MySQL or SQL dump), False otherwise.
        """
        logger.info("Checking for AOP-DB database...")

        # Check for SQL dump first
        if self._sql_dump_path and self._sql_dump_path.exists():
            size_gb = self._sql_dump_path.stat().st_size / (1024**3)
            logger.info(f"SQL dump available: {self._sql_dump_path} ({size_gb:.1f} GB)")
            return True

        if not self._mysql_available:
            logger.error("MySQL connector not available and no SQL dump found")
            return False

        if not self.mysql_config:
            logger.error("MySQL configuration not provided and no SQL dump found")
            return False

        try:
            import mysql.connector

            conn = mysql.connector.connect(
                host=self.mysql_config.get('host', 'localhost'),
                user=self.mysql_config.get('user', 'root'),
                password=self.mysql_config.get('password', ''),
                database=self.mysql_config.get('database', 'aopdb')
            )

            self.connection = conn
            logger.info("Successfully connected to AOP-DB")

            tables = self._get_table_names()
            logger.info(f"Found {len(tables)} tables in database")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to AOP-DB: {e}")
            return False

    def _parse_from_sql_dump(self, sql_file: Path) -> Dict[str, pd.DataFrame]:
        """
        Parse AOP-DB data directly from a SQL dump file.

        Streams the file line-by-line, extracting INSERT statements for
        the 3 needed tables: chemical_info, pathway_gene, aop_info.

        Args:
            sql_file: Path to the SQL dump file.

        Returns:
            Dictionary of DataFrames keyed by result name.
        """
        logger.info(f"Parsing SQL dump: {sql_file}")

        target_tables = {'chemical_info', 'pathway_gene', 'aop_info'}
        table_rows: Dict[str, list] = {t: [] for t in target_tables}

        # Compile patterns for matching INSERT lines
        insert_patterns = {
            t: re.compile(rf'^INSERT INTO `{t}` VALUES ')
            for t in target_tables
        }

        line_count = 0
        with open(sql_file, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line_count += 1
                if line_count % 5_000_000 == 0:
                    logger.info(f"  Processed {line_count:,} lines...")

                for table_name, pattern in insert_patterns.items():
                    if pattern.match(line):
                        # Extract everything after "VALUES "
                        values_start = line.index('VALUES ') + 7
                        values_str = line[values_start:].rstrip(';\n\r')
                        rows = _parse_sql_values(values_str)
                        table_rows[table_name].extend(rows)
                        break

        # Log extraction results
        for t in target_tables:
            logger.info(f"  Extracted {len(table_rows[t]):,} rows from {t}")

        result = {}

        # --- chemical_info → drugs ---
        if table_rows['chemical_info']:
            df_chem = pd.DataFrame(table_rows['chemical_info'], columns=CHEMICAL_INFO_COLUMNS)
            df_chem['source_database'] = 'AOPDB'
            result[AOPDB_DRUGS] = df_chem
            logger.info(f"  drugs: {len(df_chem):,} rows")

        # --- aop_info → aops ---
        if table_rows['aop_info']:
            df_aops = pd.DataFrame(table_rows['aop_info'], columns=AOP_INFO_COLUMNS)
            df_aops['source_database'] = 'AOPDB'
            result[AOPDB_AOPS] = df_aops
            logger.info(f"  aops: {len(df_aops):,} rows")

        # --- pathway_gene → pathways + gene_pathway_relationships ---
        if table_rows['pathway_gene']:
            df_pg = pd.DataFrame(table_rows['pathway_gene'], columns=PATHWAY_GENE_COLUMNS)

            # Filter to human (tax_id=9606)
            df_pg['tax_id'] = pd.to_numeric(df_pg['tax_id'], errors='coerce')
            df_human = df_pg[df_pg['tax_id'] == 9606].copy()
            logger.info(f"  pathway_gene human rows: {len(df_human):,} (of {len(df_pg):,} total)")

            # Clean path_name: strip HTML tags and " - Homo sapiens (human)"
            def clean_path_name(name):
                if not isinstance(name, str):
                    return name
                name = name.replace('<sub>', '').replace('</sub>', '')
                name = name.replace('<i>', '').replace('</i>', '')
                name = name.replace(' - Homo sapiens (human)', '')
                return name.strip()

            df_human['path_name'] = df_human['path_name'].apply(clean_path_name)

            # --- pathways: GROUP BY path_name ---
            pathways = (
                df_human
                .groupby('path_name', as_index=False)
                .agg({
                    'path_id': lambda x: ','.join(sorted(set(str(v) for v in x if pd.notna(v)))),
                    'ext_source': lambda x: 'AOPDB - ' + ','.join(sorted(set(str(v) for v in x if pd.notna(v)))),
                })
            )
            pathways['source_database'] = 'AOPDB'
            result[AOPDB_PATHWAYS] = pathways
            logger.info(f"  pathways: {len(pathways):,} rows")

            # --- gene_pathway_relationships: SELECT DISTINCT entrez, path_id, path_name ---
            gene_pw = (
                df_human[['entrez', 'path_id', 'path_name']]
                .drop_duplicates()
                .copy()
            )
            gene_pw['source_database'] = 'AOPDB'
            result[AOPDB_GENE_PATHWAY_RELATIONSHIPS] = gene_pw
            logger.info(f"  gene_pathway_relationships: {len(gene_pw):,} rows")

        return result

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """
        Parse AOP-DB data from MySQL or SQL dump.

        Returns:
            Dictionary of DataFrames for different AOP entities.
        """
        logger.info("Parsing AOP-DB data...")

        # Prefer SQL dump if no MySQL connection
        if not self.connection and self._sql_dump_path and self._sql_dump_path.exists():
            return self._parse_from_sql_dump(self._sql_dump_path)

        if not self.connection:
            logger.error("Not connected to database and no SQL dump found. Call download_data() first.")
            return {}

        result = {}
        available_tables = self._get_table_names()
        logger.info(f"Available tables: {available_tables}")

        query = dict()
        for result_key, table_name in AOPDB_TABLE_MAPPING.items():
            query[result_key] = f"SELECT * FROM {table_name}"

        query[AOPDB_PATHWAYS] = """
            SELECT path_name,
                GROUP_CONCAT(DISTINCT path_id) as path_id,
                CONCAT('AOPDB - ', GROUP_CONCAT(DISTINCT ext_source)) as ext_source
            FROM(
                SELECT DISTINCT path_id,
                TRIM(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(path_name, '<sub>', ''), '</sub>', ''), '<i>', ''), '</i>', ''), ' - Homo sapiens (human)', '')) as path_name,
                ext_source
                FROM pathway_gene
                WHERE tax_id = 9606)data
            GROUP BY path_name;
        """
        query[AOPDB_GENE_PATHWAY_RELATIONSHIPS] = """
            SELECT DISTINCT entrez,
                path_id,
                TRIM(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(path_name, '<sub>', ''), '</sub>', ''), '<i>', ''), '</i>', ''), ' - Homo sapiens (human)', '')) as path_name
            FROM pathway_gene
            WHERE tax_id = 9606;
        """

        for result_key, table_name in AOPDB_TABLE_MAPPING.items():
            if table_name in available_tables:
                try:
                    df = pd.read_sql(query[result_key], self.connection)
                    df['source_database'] = 'AOPDB'
                    result[result_key] = df
                    logger.info(f"Parsed {len(df)} rows from {table_name} (as {result_key})")
                except Exception as e:
                    logger.warning(f"Failed to query {table_name}: {e}")

        return result

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """Get the schema for AOP-DB data."""
        return {
            AOPDB_AOPS: {
                'aop_id': 'AOP identifier',
                'aop_name': 'AOP name',
                'description': 'AOP description',
                'source_database': 'Source database'
            },
            AOPDB_PATHWAYS: {
                'path_id': 'Pathway identifier',
                'path_name': 'Pathway name',
                'ext_source': 'External source',
                'source_database': 'Source database'
            },
            AOPDB_GENE_PATHWAY_RELATIONSHIPS: {
                'entrez': 'Entrez identifier',
                'path_id': 'Pathway identifier',
                'path_name': 'Pathway name',
                'source_database': 'Source database'
            },
            AOPDB_DRUGS: {
                'chemical_id': 'Chemical identifier',
                'chemical_name': 'Chemical name',
                'source_database': 'Source database'
            }
        }

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Closed database connection")

    def __del__(self):
        """Cleanup: close connection on deletion."""
        self.close()
