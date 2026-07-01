# Rank-Based vs AUROC-Based Evaluation for Drug Repurposing

## What Each Metric Measures

### AUROC (Area Under ROC Curve)
- Measures the model's ability to **discriminate** between true drug-disease treatment
  pairs and random non-treatment pairs across all classification thresholds.
- A score of 0.97 means: given a random positive pair and a random negative pair,
  the model assigns a higher score to the positive pair 97% of the time.
- **Strength**: Threshold-independent; captures overall model quality.
- **Limitation**: Sensitive to the negative sampling strategy. Our 1:1 random negatives
  are "easy" — most random drug-disease combinations are clearly non-therapeutic.
  This inflates AUROC relative to harder evaluation settings.

### MRR (Mean Reciprocal Rank)
- For each true treatment pair (drug, disease), rank it against ALL candidate diseases
  for that drug (or all candidate drugs for that disease).
- MRR = average of 1/rank across all test positives.
- **Strength**: Measures how well the model ranks true treatments at the very top,
  which directly maps to the drug repurposing use case (finding the best candidates).
- **Limitation**: Dominated by easy cases — a few perfectly ranked pairs can mask
  poor performance on harder ones.

### Hits@K (K = 100, 200)
- Fraction of true treatment pairs that appear in the top K predictions out of
  all possible candidates for that drug.
- **Strength**: Directly measures recall in a practical screening scenario —
  "if a researcher examines the top K predictions, how many true treatments will they find?"
- **Limitation**: Sensitive to choice of K; ignores ranking within top K.

## Which Metric Matters More for Drug Repurposing?

**Rank-based metrics (MRR, Hits@K) are more meaningful for drug repurposing** because:

1. **The task is retrieval, not classification.** Drug repurposing asks: "Given a drug,
   which diseases should we investigate?" This is a ranking problem — we need true
   treatments near the top of the candidate list.

2. **AUROC overstates practical utility.** Our high AUROC (~0.97) partly reflects that
   random negatives are easy to separate. The model can achieve high AUROC by simply
   learning that most random drug-disease pairs are non-therapeutic, without necessarily
   ranking the best candidates at the top.

3. **Hits@K maps to experimental validation.** In practice, only a small number of
   predictions (10-50) can be experimentally validated. Hits@100 directly measures
   how many true treatments fall within a feasible validation set.

## Our Results in Context

| Method   | AUROC  | AUPRC  | MRR    | Hits@100 | Hits@200 |
|----------|--------|--------|--------|----------|----------|
| RotatE   | 0.9652 | 0.9655 | —      | 31.1%    | 60.0%    |
| CompGCN  | 0.9717 | 0.9709 | —      | 30.5%    | 60.6%    |

**Key observation**: While CompGCN achieves higher AUROC (+0.0065), the ranking metrics
(Hits@K) are nearly identical. This suggests:
- Both methods learn similar ranking behavior through the XGBoost decoder
- The AUROC improvement comes from better discrimination on "medium-difficulty" pairs
- **For practical drug repurposing, both methods produce comparably useful candidate lists**
- The structural features (shared neighbors, Adamic-Adar, degree) dominate ranking
  performance regardless of embedding method
