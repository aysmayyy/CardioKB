# CardioKB Setup Guide

## Prerequisites

- Python 3.9 or higher
- pip or conda package manager
- (Optional) MySQL for AOP-DB parser

## Installation

### 1. Create a Virtual Environment

**Using conda:**
```bash
conda create -n cardiokb python=3.11
conda activate cardiokb
```

**Using venv:**
```bash
python -m venv cardiokb
source cardiokb/bin/activate  # On macOS/Linux
# or
cardiokb\Scripts\activate  # On Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- **requests**: For API calls (ClinicalTrials.gov, etc.)
- **pandas & numpy**: Data processing and analysis
- **neo4j**: Knowledge graph database connectivity
- **scipy**: Scientific computing (optional)
- **jupyter**: Notebook environment for exploration
- **matplotlib**: Visualization
- **pytest**: Testing framework

### 3. Optional Dependencies

For MySQL/AOP-DB parser:
```bash
pip install mysql-connector-python
```

## Verify Installation

Run the example script to test the setup:

```bash
python examples/clinicaltrials_rna_example.py
```

This should:
1. Query ClinicalTrials.gov for RNA therapeutics
2. Parse and display summary statistics
3. Filter for cardiovascular trials
4. Save results to CSV files in `examples/`

## Project Structure

```
Cardio-KB/
├── src/
│   └── parsers/          # Data source parsers
│       ├── base_parser.py
│       └── clinicaltrials_parser.py
├── examples/             # Example scripts
├── notebooks/            # Jupyter notebooks
├── .claude/
│   └── skills/          # Claude Code skills
└── requirements.txt      # Python dependencies
```

## Configuration

### Environment Variables

Create a `.env` file in the project root for sensitive configuration:

```bash
# MySQL/AOP-DB (if using)
AOPDB_HOST=localhost
AOPDB_USER=root
AOPDB_PASSWORD=your_password
AOPDB_DATABASE=aopdb

# Neo4j (for knowledge graph)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# API keys (if needed)
# NCBI_API_KEY=your_key
```

## Development

### Running Tests

```bash
pytest tests/
```

### Using Parsers

```python
from src.parsers import ClinicalTrialsParser

# Initialize parser
parser = ClinicalTrialsParser(
    query_term="RNA therapeutics",
    max_results=1000
)

# Download data
parser.download_data()

# Parse to DataFrame
data = parser.parse_data()
trials_df = data['rna_therapeutics_trials']

# Filter results
cvd_trials = parser.filter_cardiovascular_trials(trials_df)
```

## Troubleshooting

### Module Not Found Errors

If you get `ModuleNotFoundError`, ensure:
1. Virtual environment is activated
2. Dependencies are installed: `pip install -r requirements.txt`
3. Python path includes src: `export PYTHONPATH="${PYTHONPATH}:${PWD}"`

### API Rate Limits

ClinicalTrials.gov API has rate limits (~50 requests/minute). The parser automatically:
- Adds 1.5s delays between requests
- Implements pagination
- Handles rate limit errors gracefully

### Large Datasets

For large queries, consider:
- Reducing `max_results` parameter
- Using more specific query terms
- Caching results locally

## Next Steps

1. **Create more parsers**: Follow the BaseParser pattern for new data sources
2. **Build knowledge graph**: Use Neo4j to connect entities
3. **Add analysis notebooks**: Explore data in Jupyter notebooks
4. **Extend filtering**: Add domain-specific filters for your use case

## Resources

- [ClinicalTrials.gov API Docs](https://clinicaltrials.gov/data-api/api)
- [Neo4j Python Driver](https://neo4j.com/docs/python-manual/current/)
- [Pandas Documentation](https://pandas.pydata.org/docs/)
