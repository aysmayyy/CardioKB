# CardioKB Evaluation Form

> **Instructions for creating in Google Forms**: Copy each section below into a Google Form.
> Set the form title, sections, and question types as indicated.
> Share link with evaluators after they complete the task scenarios.

---

## Google Form Configuration

**Form Title**: CardioKB Domain Expert Evaluation
**Form Description**:
Thank you for evaluating CardioKB. This form takes approximately 10 minutes. Your responses will help us improve the tool and will be included (anonymized) in a publication. All questions are required unless marked optional.

---

## Section 1: Participant Information

**Section Header**: Background Information

---

**Q1.1** — What best describes your role?
- *Type*: Multiple choice
- *Options*:
  - Cardiologist / Clinical physician
  - Clinical researcher (CVD focus)
  - Basic science researcher (CVD focus)
  - Bioinformatician / Computational biologist
  - Pharmacologist
  - Other (short answer)

---

**Q1.2** — How many years of experience do you have in cardiovascular research or practice?
- *Type*: Multiple choice
- *Options*:
  - 0–2 years
  - 3–5 years
  - 6–10 years
  - 11–20 years
  - 20+ years

---

**Q1.3** — How often do you use biomedical databases (e.g., PubMed, ClinVar, DrugBank, STRING) in your work?
- *Type*: Multiple choice
- *Options*:
  - Daily
  - Weekly
  - Monthly
  - Rarely
  - Never

---

**Q1.4** — Have you used a knowledge graph or network visualization tool before? (e.g., Cytoscape, Neo4j, DisGeNET, Hetionet)
- *Type*: Multiple choice
- *Options*:
  - Yes, regularly
  - Yes, occasionally
  - No, this is my first time

---

## Section 2: System Usability Scale (SUS)

**Section Header**: Usability
**Section Description**: Please rate your agreement with each statement on a scale of 1 (Strongly Disagree) to 5 (Strongly Agree). Answer based on your experience completing the 5 tasks.

> **Google Forms setup**: Use a Linear Scale (1–5) for each question.
> Label: 1 = Strongly Disagree, 5 = Strongly Agree

---

**Q2.1** — I think that I would like to use CardioKB frequently.
- *Type*: Linear scale 1–5

**Q2.2** — I found CardioKB unnecessarily complex.
- *Type*: Linear scale 1–5

**Q2.3** — I thought CardioKB was easy to use.
- *Type*: Linear scale 1–5

**Q2.4** — I think that I would need the support of a technical person to be able to use CardioKB.
- *Type*: Linear scale 1–5

**Q2.5** — I found the various functions in CardioKB were well integrated.
- *Type*: Linear scale 1–5

**Q2.6** — I thought there was too much inconsistency in CardioKB.
- *Type*: Linear scale 1–5

**Q2.7** — I would imagine that most people would learn to use CardioKB very quickly.
- *Type*: Linear scale 1–5

**Q2.8** — I found CardioKB very cumbersome to use.
- *Type*: Linear scale 1–5

**Q2.9** — I felt very confident using CardioKB.
- *Type*: Linear scale 1–5

**Q2.10** — I needed to learn a lot of things before I could get going with CardioKB.
- *Type*: Linear scale 1–5

> **SUS Scoring Reference** (do not include in form):
> For odd-numbered items (1,3,5,7,9): score = response - 1
> For even-numbered items (2,4,6,8,10): score = 5 - response
> Sum all 10 scores, multiply by 2.5. Range: 0–100. Average: 68.

---

## Section 3: Task-Specific Responses

**Section Header**: Task Feedback
**Section Description**: Please answer based on your experience with each task. If you did not complete a task, select "Did not attempt."

---

### Task 1: Gene–Disease Investigation (PCSK9)

**Q3.1** — Were you able to find diseases, drugs, and pathways connected to PCSK9?
- *Type*: Multiple choice
- *Options*: Yes, all three / Yes, some / No / Did not attempt

**Q3.2** — Did the PCSK9 network match your existing domain knowledge?
- *Type*: Linear scale 1–5 (1 = Not at all, 5 = Completely)

**Q3.3** — Was anything important missing from the PCSK9 results? *(Optional)*
- *Type*: Long answer

---

### Task 2: Treatment Lookup (Natural Language Query)

**Q3.4** — Did the natural language query return relevant drugs for atrial fibrillation?
- *Type*: Multiple choice
- *Options*: Yes, mostly relevant / Partially relevant / Not relevant / Query failed / Did not attempt

**Q3.5** — How accurate were the returned drug–disease associations?
- *Type*: Linear scale 1–5 (1 = Many errors, 5 = All accurate)

**Q3.6** — Were any expected drugs missing? If so, which ones? *(Optional)*
- *Type*: Long answer

---

### Task 3: Drug Repurposing Exploration

**Q3.7** — Was the distinction between known relationships (solid lines) and ML predictions (dashed cyan lines) clear?
- *Type*: Linear scale 1–5 (1 = Very confusing, 5 = Very clear)

**Q3.8** — For the predicted drug you examined, did the repurposing suggestion seem biologically plausible?
- *Type*: Multiple choice
- *Options*: Yes, plausible / Possibly plausible / Not plausible / Not sure / Did not attempt

**Q3.9** — What minimum confidence score would you consider worth investigating further?
- *Type*: Multiple choice
- *Options*: ≥50% / ≥60% / ≥70% / ≥80% / ≥90%

**Q3.10** — Any comments on the drug repurposing predictions? *(Optional)*
- *Type*: Long answer

---

### Task 4: Variant-to-Drug Path Tracing (SCN5A)

**Q3.11** — Were you able to trace a path from variant → gene → disease?
- *Type*: Multiple choice
- *Options*: Yes, complete path / Partial path only / No / Did not attempt

**Q3.12** — Are the source annotations on edges (e.g., "OpenTargets", "ClinVar") useful for assessing evidence quality?
- *Type*: Linear scale 1–5 (1 = Not useful, 5 = Very useful)

**Q3.13** — Did the graph reveal any connections you were not already aware of? *(Optional)*
- *Type*: Long answer

---

### Task 5: Disease Subgraph Extraction (HCM)

**Q3.14** — Was the exported data (JSON/CSV) in a format you could use for downstream analysis?
- *Type*: Multiple choice
- *Options*: Yes, ready to use / Needs minor formatting / Not usable / Did not attempt

**Q3.15** — Would you use this feature to generate datasets for your own research?
- *Type*: Linear scale 1–5 (1 = Definitely not, 5 = Definitely yes)

---

## Section 4: Domain-Specific Evaluation

**Section Header**: Accuracy, Completeness, and Clinical Relevance
**Section Description**: Please rate the following based on your overall experience with CardioKB.

---

### Accuracy

**Q4.1** — The biological relationships shown in CardioKB matched my domain knowledge.
- *Type*: Linear scale 1–5 (1 = Strongly Disagree, 5 = Strongly Agree)

**Q4.2** — I encountered incorrect or misleading information in the results.
- *Type*: Multiple choice
- *Options*: Never / Once or twice / Several times / Frequently

**Q4.3** — If you found inaccuracies, please describe them. *(Optional)*
- *Type*: Long answer

---

### Completeness

**Q4.4** — The knowledge graph covered the entities (genes, drugs, diseases) I expected for CVD.
- *Type*: Linear scale 1–5 (1 = Many gaps, 5 = Very comprehensive)

**Q4.5** — Were there specific databases, entities, or relationship types you expected but were missing? *(Optional)*
- *Type*: Long answer

---

### Clinical Relevance

**Q4.6** — CardioKB could support my research workflow (e.g., hypothesis generation, literature review, data exploration).
- *Type*: Linear scale 1–5 (1 = Strongly Disagree, 5 = Strongly Agree)

**Q4.7** — The drug repurposing predictions are useful for identifying candidates worth investigating.
- *Type*: Linear scale 1–5 (1 = Strongly Disagree, 5 = Strongly Agree)

**Q4.8** — Which research tasks would CardioKB be most useful for? *(Select all that apply)*
- *Type*: Checkboxes
- *Options*:
  - Hypothesis generation
  - Literature review / context gathering
  - Drug repurposing candidate identification
  - Gene–disease association exploration
  - Pharmacogenomics lookup
  - Dataset preparation for computational analysis
  - Teaching / education
  - None of the above

---

### Trust

**Q4.9** — I trust the curated (database-sourced) relationships shown in CardioKB.
- *Type*: Linear scale 1–5 (1 = No trust, 5 = Full trust)

**Q4.10** — I trust the ML-predicted drug–disease links shown in CardioKB.
- *Type*: Linear scale 1–5 (1 = No trust, 5 = Full trust)

**Q4.11** — The provenance information (source database labels on edges) increased my confidence in the results.
- *Type*: Linear scale 1–5 (1 = Strongly Disagree, 5 = Strongly Agree)

---

### Comparative

**Q4.12** — Compared to tools you currently use (e.g., PubMed, CTD, DrugBank, STRING, DisGeNET), CardioKB provides:
- *Type*: Multiple choice
- *Options*:
  - Significantly more value (integrates multiple sources I normally query separately)
  - Somewhat more value
  - About the same
  - Less value
  - I don't use comparable tools

**Q4.13** — What does CardioKB do better than existing tools you use? *(Optional)*
- *Type*: Long answer

**Q4.14** — What do existing tools do better than CardioKB? *(Optional)*
- *Type*: Long answer

---

## Section 5: Open-Ended Feedback

**Section Header**: Final Thoughts

**Q5.1** — What did you like most about CardioKB?
- *Type*: Long answer

**Q5.2** — What was the most frustrating or confusing aspect?
- *Type*: Long answer

**Q5.3** — What one feature or improvement would make CardioKB most useful for your work? *(Optional)*
- *Type*: Long answer

**Q5.4** — Any additional comments? *(Optional)*
- *Type*: Long answer

---

## Form Settings

- **Collect email addresses**: Yes (for follow-up if needed; note this in consent)
- **Limit to 1 response**: Yes
- **Edit after submit**: Yes
- **Confirmation message**: "Thank you for evaluating CardioKB. Your feedback is invaluable to our research."
