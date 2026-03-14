# Cardiovascular Disease Ontology

## Overview

CardioKB uses a comprehensive cardiovascular disease (CVD) ontology for filtering and classifying clinical trials, research papers, and other data sources. This ensures consistent terminology across all parsers and analyses.

## Ontology File

**Location**: [`ontology/disease_filter.txt`](../ontology/disease_filter.txt)

This file contains 35+ curated CVD terms organized hierarchically:

### Categories

1. **General cardiovascular terms**
   - Cardiovascular disease
   - Heart disease
   - Cardiac disease

2. **Arrhythmias**
   - Arrhythmia, Atrial fibrillation
   - Ventricular tachycardia/fibrillation
   - Long QT syndrome, Brugada syndrome
   - Heart block

3. **Coronary conditions**
   - Coronary artery disease
   - Myocardial infarction (heart attack)
   - Angina, Ischemic heart disease
   - Atherosclerosis

4. **Heart failure**
   - Heart failure
   - Congestive heart failure
   - Cardiac failure

5. **Cardiomyopathy**
   - Hypertrophic cardiomyopathy
   - Dilated cardiomyopathy

6. **Hypertension**
   - Hypertension
   - High blood pressure

7. **Stroke**
   - Ischemic stroke
   - Hemorrhagic stroke
   - Cerebrovascular disease

8. **Miscellaneous**
   - Valvular heart disease
   - Pericarditis, Myocarditis, Endocarditis

## Usage in Code

### Loading CVD Terms

```python
from src.utils import load_cvd_terms

# Load all CVD terms
cvd_terms = load_cvd_terms()
# Returns: {'cardiovascular disease', 'heart attack', ...}
```

### Filtering DataFrames

```python
from src.parsers import ClinicalTrialsParser

parser = ClinicalTrialsParser()
parser.download_data()
data = parser.parse_data()
trials_df = data['rna_therapeutics_trials']

# Filter using comprehensive CVD ontology
cvd_trials = parser.filter_cardiovascular_trials(trials_df)
```

### Checking Individual Text

```python
from src.utils import is_cardiovascular_related

text = "Study of Atrial Fibrillation in Elderly Patients"
is_cvd = is_cardiovascular_related(text)
# Returns: True
```

### Getting Search Pattern

```python
from src.utils import get_cvd_search_pattern

# Get regex pattern for all CVD terms
pattern = get_cvd_search_pattern()
# Use with pandas: df[df['condition'].str.contains(pattern, case=False)]
```

## Updating the Ontology

To add new CVD terms:

1. Edit [`ontology/disease_filter.txt`](../ontology/disease_filter.txt)
2. Add terms one per line (comments start with `#`)
3. All parsers will automatically use the updated terms

Example:
```txt
# New arrhythmia types
Supraventricular tachycardia
Wolff-Parkinson-White syndrome
```

## Benefits

✓ **Consistency**: All parsers use the same terminology
✓ **Maintainability**: Single source of truth in one file
✓ **Extensibility**: Easy to add new terms without code changes
✓ **Comprehensiveness**: Covers 35+ CVD terms including synonyms
✓ **Case-insensitive**: Automatic lowercase matching

## Related Files

- [`src/utils.py`](../src/utils.py) - Utility functions for loading and using CVD terms
- [`src/parsers/clinicaltrials_parser.py`](../src/parsers/clinicaltrials_parser.py) - Parser using CVD filtering
- [`examples/test_cvd_filtering.py`](../examples/test_cvd_filtering.py) - Test script for CVD filtering

## Testing

Run the test script to verify CVD filtering:

```bash
python examples/test_cvd_filtering.py
```

This will:
1. Load all CVD terms from the ontology
2. Generate the search pattern
3. Test matching against sample texts
4. Report pass/fail status
