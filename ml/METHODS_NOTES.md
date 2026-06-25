# CardioKB Link Prediction — Methods Notes

## 1. Method Progression: Node2Vec → RotatE → CompGCN

**Node2Vec (Baseline)**
Shallow embedding method that learns node representations via biased random walks
on the graph structure. Chosen as the starting baseline because it is fast to train,
well-understood, and captures local/global graph topology through the p/q parameters.
Limitation: treats all edge types identically — the random walks ignore relation
semantics, so the 25 distinct relationship types in CardioKB are collapsed.

**RotatE (Knowledge Graph Embedding)**
Models each relation as a rotation in complex embedding space, giving each of the
25 relation types its own learned transformation. Chosen as the second method to test
whether relation-aware embeddings improve over Node2Vec's structure-only approach.
Result: +0.015 AUROC over Node2Vec, confirming that relation semantics matter for
drug repurposing prediction on this graph.

**CompGCN (Graph Neural Network)**
Message-passing GNN that jointly embeds nodes and relations through composition
operators (sub, mult, or corr) applied during neighborhood aggregation. Chosen as
the third method because it captures multi-hop relational patterns that RotatE's
single-triple scoring cannot. Preferred over R-GCN because R-GCN allocates a separate
weight matrix per relation type — with 25 relation types and only 3,782 target edges,
this risks overfitting. CompGCN shares parameters across relations via composition,
scaling better to high relation-type counts.

## 2. Data: drugTreatsDisease Edge Breakdown

| Source | Edges | Notes |
|--------|------:|-------|
| CTD (Comparative Toxicogenomics Database) | 2,757 | Curated chemical-disease therapeutic relationships |
| ClinicalTrials.gov | 868 | Extracted from trial intervention-condition pairs |
| DrugCentral | 157 | FDA-approved indications |
| **Total** | **3,782** | Deduplicated by (Drug, Disease) pair |

Drug nodes filtered to therapeutic drugs only (those with at least one edge of type:
drugBindsGene, compoundInPharmacologicClass, compoundCausesSideEffect,
drugTreatsDisease, AFFECTS_RESPONSE_TO, or TESTS_INTERVENTION).

Candidate space: 9,735 therapeutic drugs × 457 diseases.

## 3. Train/Val/Test Split

- **Ratio**: 80% train / 10% validation / 10% test
- **Strategy**: Stratified by edge type — each of the 25 relationship types is split
  proportionally so all types appear in all splits
- **Random seed**: 42 (numpy RandomState), identical across all three methods
- **Script**: `ml/split_edges.py`
- **Output**: `ml/data/splits/{train,val,test}_edges.tsv`

The train split is used exclusively for embedding training (Node2Vec random walks,
RotatE triple scoring, CompGCN message passing). Validation is used for early stopping
and hyperparameter selection. Test is held out for final evaluation only.

## 4. Negative Sampling

- **Ratio**: 1:1 (one negative per positive edge)
- **Strategy**: Random Drug-Disease pairs not present in the full graph
  (not just the train set — avoids false negatives from val/test positives)
- **Seeded**: Same random seed (42) for reproducibility
- Applied identically in all three methods' link prediction scripts

## 5. Decoder: XGBoost (All Methods)

All three methods use XGBoost as the primary decoder for fair comparison:

- **Input features**: `|emb_src - emb_dst|` (element-wise absolute difference) +
  `emb_src * emb_dst` (Hadamard product) → 2× embedding dimension
- **Hyperparameters**: n_estimators=500, max_depth=6, learning_rate=0.1,
  eval_metric=logloss, early_stopping_rounds=50
- **Training**: Fit on train set, early stopping on validation set
- **Rationale**: XGBoost on concatenated features captures non-linear interactions
  between embedding dimensions. Cosine similarity and MLP decoders also evaluated
  but XGBoost consistently performs best across both Node2Vec and RotatE.

## 6. Key Hyperparameters

### Node2Vec (PecanPy SparseOTF)
| Parameter | Value | Notes |
|-----------|-------|-------|
| dimensions | 128 | Embedding dimensionality |
| walk_length | 80 | Steps per random walk |
| num_walks | 10 | Walks per node |
| p | 1.0 | Return parameter (BFS-like) |
| q | 0.5 | In-out parameter (favors exploration) |
| window | 10 | Word2Vec context window |
| epochs | 5 | Word2Vec training epochs |
| workers | 8 | Parallel threads |
| min_count | 0 | Include all nodes |

### RotatE (PyKEEN)
| Parameter | Value | Notes |
|-----------|-------|-------|
| embedding_dim | 128 | Complex dim (256 real after concat) |
| num_epochs | 200 | Max epochs (early stopping active) |
| batch_size | 4,096 | Training batch size |
| learning_rate | 1e-4 | Adam optimizer |
| negative_samples | 64 | Negatives per positive triple |
| loss | NSSALoss | Margin=9.0, adversarial_temperature=1.0 |
| early_stopping | patience=10, frequency=10 | On inverse_harmonic_mean_rank |
| seed | 42 | PyTorch + NumPy |

### CompGCN (PyTorch Geometric) — Planned
| Parameter | Value | Notes |
|-----------|-------|-------|
| hidden_dim | 128 | Hidden layer dimensionality |
| num_layers | 2 | Message-passing layers |
| composition | sub | Composition operator (sub/mult/corr) |
| dropout | 0.3 | Applied after each layer |
| learning_rate | 1e-3 | Adam optimizer |
| num_epochs | 200 | Max epochs (early stopping active) |
| batch_size | full graph | Full-batch training (mini-batch for neg sampling) |
| seed | 42 | For reproducibility |

## 7. Results Summary

| Method | Embedding Dim | Decoder | Test AUROC | Test AUPRC | Hits@100 | Hits@200 |
|--------|:---:|---------|:---:|:---:|:---:|:---:|
| Node2Vec | 128 | Cosine | 0.7195 | 0.7195 | — | — |
| Node2Vec | 128 | **XGBoost** | **0.9504** | **0.9579** | 31.1% | — |
| Node2Vec | 128 | MLP | 0.9441 | 0.9441 | — | — |
| RotatE | 256 (128 complex) | Cosine | 0.5299 | 0.5401 | 19.3% | 32.3% |
| RotatE | 256 (128 complex) | **XGBoost** | **0.9652** | **0.9655** | 31.1% | 60.0% |
| RotatE | 256 (128 complex) | MLP | 0.9607 | 0.9588 | 30.7% | 60.9% |
| CompGCN | 128 | XGBoost | — | — | — | — |

RotatE + XGBoost is the current best: +0.015 AUROC and +0.008 AUPRC over Node2Vec + XGBoost.

RotatE's native MRR on the full test set is 0.1119 (PyKEEN filtered ranking). This is
modest because ranking evaluates all 459K entities as candidates; the XGBoost decoder
on the Drug×Disease candidate space is the operationally relevant metric.

## 8. Why CompGCN over R-GCN

**R-GCN** (Relational Graph Convolutional Network) learns a separate weight matrix
W_r for each relation type. With 25 relation types and d-dimensional hidden layers,
each R-GCN layer has 25 × d × d parameters. On a target task with only 3,782 positive
edges, this creates a high parameter-to-sample ratio and overfitting risk. Basis
decomposition (reducing to B basis matrices) partially mitigates this but introduces
a tuning burden (choosing B) and still scales linearly with relation count.

**CompGCN** instead learns a single d-dimensional embedding per relation and combines
it with neighbor embeddings through a composition operator φ(e_s, e_r) before the
shared weight matrix. This means each layer has only d × d + R × d parameters
(one W plus R relation embeddings), dramatically fewer than R-GCN's R × d × d.

For CardioKB specifically:
- 25 relation types → R-GCN would need 25 weight matrices per layer
- 3,782 drugTreatsDisease target edges → limited supervision signal
- CompGCN's parameter sharing prevents overfitting while still learning
  relation-specific semantics through the composition operator

## 9. Prediction Storage

Top 500 predictions per method (confidence ≥ 0.5) stored in Memgraph as
`predictedTreatsDisease` edges with properties:
- `confidence`: XGBoost probability score
- `source`: `Node2Vec_LinkPrediction`, `RotatE_LinkPrediction`, or `CompGCN_LinkPrediction`

Displayed in the web UI as orange dashed edges with a "not clinically validated" warning.
