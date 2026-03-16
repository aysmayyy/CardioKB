# Cardiovascular Disease Ontology

## Overview

CardioKB uses a disease term filtering system that supports multiple disease areas. Disease term files live in `ontology/diseases/` (one term per line, `#` for comments). The active filter is controlled by a symlink at `ontology/disease_filter.txt`.

## Disease Filter Files

| File | Terms | Disease Area |
|------|-------|-------------|
| `ontology/diseases/cvd.txt` | 90 | Cardiovascular disease (default) |
| `ontology/diseases/alzheimers.txt` | 35 | Alzheimer's & related dementias |
| `ontology/diseases/cancer.txt` | 70 | Cancer / oncology |
| `ontology/diseases/asthma.txt` | 48 | Asthma & respiratory diseases |
| `ontology/diseases/diabetes.txt` | 52 | Diabetes & metabolic diseases |

`ontology/disease_filter.txt` is a symlink to `diseases/cvd.txt` by default.

## CVD Term Categories (90 terms)

The CVD filter (`ontology/diseases/cvd.txt`) covers:

1. **General** — Cardiovascular disease, Heart disease, Cardiac disease
2. **Arrhythmias** — Atrial fibrillation/flutter, Ventricular tachycardia/fibrillation, Long QT syndrome, Brugada syndrome, CPVT, Sick sinus syndrome, Heart block
3. **Coronary conditions** — CAD, Myocardial infarction, Angina, Ischemic heart disease, Atherosclerosis
4. **Heart failure** — CHF, HFrEF, HFpEF, Acute/Chronic heart failure
5. **Cardiomyopathy** — HCM, DCM, Restrictive, ARVC, Takotsubo
6. **Hypertension** — Essential, Secondary, Pulmonary, Resistant
7. **Stroke** — Ischemic, Hemorrhagic, Thrombotic, Embolic, TIA
8. **Vascular diseases** — PAD, Thromboembolism, VTE, Aortic aneurysm/dissection
9. **Lipid disorders** — Hypercholesterolemia, Dyslipidemia, Familial hypercholesterolemia
10. **Valvular disease** — Aortic stenosis/regurgitation, Mitral stenosis/regurgitation/prolapse
11. **Other** — Pericarditis, Myocarditis, Endocarditis, Cardiac/Heart transplant

## Which Parsers Use Disease Filtering?

Most parsers (30 of 32) are **disease-agnostic** — they load all data regardless of disease area.

- **DisGeNETParser** — accepts a `disease_filter` parameter; defaults to `ontology/disease_filter.txt` (CVD)
- **OMIMParser** — reads the symlink to tag rows with `is_cvd` but loads all data regardless

All other parsers load complete datasets without filtering.

## Usage in Code

### Loading Disease Terms

```python
from src.utils import load_disease_terms

# Load terms from the active filter (symlink)
terms = load_disease_terms()
# Returns: {'cardiovascular disease', 'heart attack', ...}

# Load a specific disease file
terms = load_disease_terms('ontology/diseases/alzheimers.txt')
```

### Checking Text Against Terms

```python
from src.utils import is_cardiovascular_related

text = "Study of Atrial Fibrillation in Elderly Patients"
is_cvd = is_cardiovascular_related(text)
# Returns: True
```

### Getting Search Pattern

```python
from src.utils import get_disease_search_pattern

# Get regex pattern for all terms in the active filter
pattern = get_disease_search_pattern()
# Use with pandas: df[df['condition'].str.contains(pattern, case=False)]
```

## Switching Disease Area

To switch the active disease filter:

```bash
cd ontology
rm disease_filter.txt
ln -s diseases/alzheimers.txt disease_filter.txt
```

Then re-run the pipeline. Only DisGeNET and OMIM CVD-tagging are affected; all other parsers produce the same output.

## Updating Terms

Edit the relevant file in `ontology/diseases/` — one term per line, `#` for comments:

```txt
# New arrhythmia types
Supraventricular tachycardia
Wolff-Parkinson-White syndrome
```

All parsers that use the filter will automatically pick up changes on next run.
