"""
Train CompGCN embeddings on CardioKB (HPC version).

CompGCN jointly embeds nodes and relations via composition operators
during message passing. Uses the same 80/10/10 stratified split as
Node2Vec and RotatE for fair comparison.

Output: node embeddings saved as .npz for downstream XGBoost link prediction.
"""

import csv
import time
import json
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).resolve().parent / "data"
SPLIT_DIR = DATA_DIR / "splits"
OUTPUT_DIR = DATA_DIR / "compgcn"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HIDDEN_DIM = 128
NUM_LAYERS = 2
COMPOSITION = "sub"
DROPOUT = 0.3
LEARNING_RATE = 1e-3
NUM_EPOCHS = 200
PATIENCE = 20
SEED = 42


def load_nodes():
    """Load node metadata and build int_id mapping."""
    nodes = {}
    with open(DATA_DIR / "nodes.tsv") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            nodes[int(row["int_id"])] = row["label"]
    return nodes


def load_split_edges(split_name):
    """Load edges from a split file."""
    edges = []
    with open(SPLIT_DIR / f"{split_name}_edges.tsv") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            edges.append((int(row["src"]), int(row["dst"]), row["rel_type"]))
    return edges


def build_relation_mapping(train_edges, val_edges, test_edges):
    """Build relation-to-index mapping from all splits."""
    rel_types = set()
    for edges in [train_edges, val_edges, test_edges]:
        for _, _, r in edges:
            rel_types.add(r)
    rel_to_id = {r: i for i, r in enumerate(sorted(rel_types))}
    return rel_to_id


def build_edge_index_and_type(edges, rel_to_id, num_nodes):
    """Convert edge list to PyG format with inverse relations."""
    num_base_rels = len(rel_to_id)

    src_list, dst_list, rel_list = [], [], []
    for s, d, r in edges:
        rid = rel_to_id[r]
        src_list.extend([s, d])
        dst_list.extend([d, s])
        rel_list.extend([rid, rid + num_base_rels])

    edge_index = torch.tensor([src_list, dst_list], dtype=torch.long)
    edge_type = torch.tensor(rel_list, dtype=torch.long)
    return edge_index, edge_type


class CompGCNConv(nn.Module):
    """Single CompGCN convolution layer."""

    def __init__(self, in_dim, out_dim, num_rels, composition="sub"):
        super().__init__()
        self.in_dim = in_dim
        self.out_dim = out_dim
        self.num_rels = num_rels
        self.composition = composition

        self.W_node = nn.Linear(in_dim, out_dim, bias=False)
        self.W_self = nn.Linear(in_dim, out_dim, bias=False)
        self.W_rel = nn.Linear(in_dim, out_dim, bias=False)
        self.bias = nn.Parameter(torch.zeros(out_dim))
        self.bn = nn.BatchNorm1d(out_dim)

    def compose(self, node_emb, rel_emb):
        if self.composition == "sub":
            return node_emb - rel_emb
        elif self.composition == "mult":
            return node_emb * rel_emb
        elif self.composition == "corr":
            node_fft = torch.fft.rfft(node_emb, dim=-1)
            rel_fft = torch.fft.rfft(rel_emb, dim=-1)
            return torch.fft.irfft(node_fft * torch.conj(rel_fft), n=node_emb.shape[-1], dim=-1)
        else:
            raise ValueError(f"Unknown composition: {self.composition}")

    def forward(self, x, edge_index, edge_type, rel_emb):
        src, dst = edge_index
        num_nodes = x.size(0)

        src_emb = x[src]
        rel_for_edges = rel_emb[edge_type]
        composed = self.compose(src_emb, rel_for_edges)
        msg = self.W_node(composed)

        deg = torch.zeros(num_nodes, device=x.device)
        deg.scatter_add_(0, dst, torch.ones(dst.size(0), device=x.device))
        deg_inv = 1.0 / deg.clamp(min=1)

        agg = torch.zeros(num_nodes, self.out_dim, device=x.device)
        agg.scatter_add_(0, dst.unsqueeze(1).expand_as(msg), msg)
        agg = agg * deg_inv.unsqueeze(1)

        out = agg + self.W_self(x) + self.bias
        out = self.bn(out)

        rel_out = self.W_rel(rel_emb)
        return out, rel_out


class CompGCN(nn.Module):
    """Multi-layer CompGCN encoder."""

    def __init__(self, num_nodes, num_rels, hidden_dim, num_layers,
                 composition="sub", dropout=0.3):
        super().__init__()
        self.num_rels = num_rels
        self.num_total_rels = num_rels * 2

        self.node_emb = nn.Embedding(num_nodes, hidden_dim)
        self.rel_emb = nn.Embedding(self.num_total_rels, hidden_dim)

        nn.init.xavier_uniform_(self.node_emb.weight)
        nn.init.xavier_uniform_(self.rel_emb.weight)

        self.layers = nn.ModuleList()
        for _ in range(num_layers):
            self.layers.append(CompGCNConv(hidden_dim, hidden_dim, self.num_total_rels, composition))

        self.dropout = dropout

    def forward(self, edge_index, edge_type):
        x = self.node_emb.weight
        rel = self.rel_emb.weight

        for layer in self.layers:
            x, rel = layer(x, edge_index, edge_type, rel)
            x = F.relu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)

        return x, rel


class LinkPredictor(nn.Module):
    """DistMult-style link prediction head for training signal."""

    def __init__(self, hidden_dim):
        super().__init__()
        self.W = nn.Parameter(torch.empty(hidden_dim))
        nn.init.uniform_(self.W, -1.0, 1.0)

    def forward(self, h, r, t):
        return torch.sum(h * r * t, dim=-1)


def sample_negatives(pos_edges, num_nodes, num_neg=1, seed=None):
    """Sample negative edges by corrupting tail entities."""
    rng = np.random.RandomState(seed)
    pos_set = set((s, d) for s, d, _ in pos_edges)
    neg_edges = []
    for s, d, r in pos_edges:
        for _ in range(num_neg):
            while True:
                neg_t = rng.randint(0, num_nodes)
                if (s, neg_t) not in pos_set:
                    neg_edges.append((s, neg_t, r))
                    break
    return neg_edges


def evaluate_ranking(model, predictor, pos_edges, neg_edges, edge_index,
                     edge_type, device):
    """Compute loss on validation set."""
    model.eval()
    predictor.eval()
    with torch.no_grad():
        x, rel = model(edge_index, edge_type)

        pos_src = torch.tensor([s for s, _, _ in pos_edges], device=device)
        pos_dst = torch.tensor([d for _, d, _ in pos_edges], device=device)
        pos_rel = torch.tensor([r for _, _, r in pos_edges], device=device)

        neg_src = torch.tensor([s for s, _, _ in neg_edges], device=device)
        neg_dst = torch.tensor([d for _, d, _ in neg_edges], device=device)
        neg_rel = torch.tensor([r for _, _, r in neg_edges], device=device)

        pos_score = predictor(x[pos_src], rel[pos_rel], x[pos_dst])
        neg_score = predictor(x[neg_src], rel[neg_rel], x[neg_dst])

        pos_loss = F.binary_cross_entropy_with_logits(
            pos_score, torch.ones_like(pos_score))
        neg_loss = F.binary_cross_entropy_with_logits(
            neg_score, torch.zeros_like(neg_score))
        loss = (pos_loss + neg_loss) / 2

    return loss.item()


def main():
    torch.manual_seed(SEED)
    np.random.seed(SEED)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"CompGCN config:")
    print(f"  hidden_dim={HIDDEN_DIM}, num_layers={NUM_LAYERS}")
    print(f"  composition={COMPOSITION}, dropout={DROPOUT}")
    print(f"  lr={LEARNING_RATE}, epochs={NUM_EPOCHS}, patience={PATIENCE}")
    print(f"  seed={SEED}, device={device}")
    if device == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")

    print("\nLoading data...")
    t0 = time.time()

    nodes = load_nodes()
    num_nodes = max(nodes.keys()) + 1
    print(f"  Nodes: {len(nodes):,} (id range 0-{num_nodes - 1})")

    train_edges = load_split_edges("train")
    val_edges = load_split_edges("val")
    test_edges = load_split_edges("test")
    print(f"  Train: {len(train_edges):,} edges")
    print(f"  Val:   {len(val_edges):,} edges")
    print(f"  Test:  {len(test_edges):,} edges")

    rel_to_id = build_relation_mapping(train_edges, val_edges, test_edges)
    num_base_rels = len(rel_to_id)
    print(f"  Relations: {num_base_rels} base types ({num_base_rels * 2} with inverse)")

    train_edges_indexed = [(s, d, rel_to_id[r]) for s, d, r in train_edges]

    train_edge_index, train_edge_type = build_edge_index_and_type(
        train_edges, rel_to_id, num_nodes)
    train_edge_index = train_edge_index.to(device)
    train_edge_type = train_edge_type.to(device)

    val_edges_indexed = [(s, d, rel_to_id[r]) for s, d, r in val_edges]
    val_neg = sample_negatives(val_edges, num_nodes, seed=SEED + 1)
    val_neg_indexed = [(s, d, rel_to_id[r]) for s, d, r in val_neg]

    print(f"  Data loaded in {time.time() - t0:.1f}s")

    print("\nInitializing CompGCN...")
    model = CompGCN(
        num_nodes=num_nodes,
        num_rels=num_base_rels,
        hidden_dim=HIDDEN_DIM,
        num_layers=NUM_LAYERS,
        composition=COMPOSITION,
        dropout=DROPOUT,
    ).to(device)

    predictor = LinkPredictor(HIDDEN_DIM).to(device)

    total_params = sum(p.numel() for p in model.parameters()) + \
                   sum(p.numel() for p in predictor.parameters())
    print(f"  Total parameters: {total_params:,}")

    optimizer = torch.optim.Adam(
        list(model.parameters()) + list(predictor.parameters()),
        lr=LEARNING_RATE,
    )

    print("\nTraining...")
    t1 = time.time()

    best_val_loss = float("inf")
    best_epoch = 0
    patience_counter = 0
    best_state = None

    for epoch in range(1, NUM_EPOCHS + 1):
        model.train()
        predictor.train()
        optimizer.zero_grad()

        x, rel = model(train_edge_index, train_edge_type)

        neg_train = sample_negatives(train_edges, num_nodes, seed=SEED + epoch)
        neg_train_indexed = [(s, d, rel_to_id[r]) for s, d, r in neg_train]

        pos_src = torch.tensor([s for s, _, _ in train_edges_indexed], device=device)
        pos_dst = torch.tensor([d for _, d, _ in train_edges_indexed], device=device)
        pos_rel_idx = torch.tensor([r for _, _, r in train_edges_indexed], device=device)

        neg_src = torch.tensor([s for s, _, _ in neg_train_indexed], device=device)
        neg_dst = torch.tensor([d for _, d, _ in neg_train_indexed], device=device)
        neg_rel_idx = torch.tensor([r for _, _, r in neg_train_indexed], device=device)

        pos_score = predictor(x[pos_src], rel[pos_rel_idx], x[pos_dst])
        neg_score = predictor(x[neg_src], rel[neg_rel_idx], x[neg_dst])

        pos_loss = F.binary_cross_entropy_with_logits(
            pos_score, torch.ones_like(pos_score))
        neg_loss = F.binary_cross_entropy_with_logits(
            neg_score, torch.zeros_like(neg_score))
        loss = (pos_loss + neg_loss) / 2

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        if epoch % 10 == 0 or epoch == 1:
            val_loss = evaluate_ranking(
                model, predictor, val_edges_indexed, val_neg_indexed,
                train_edge_index, train_edge_type, device)
            print(f"  Epoch {epoch:3d}/{NUM_EPOCHS}  train_loss={loss.item():.4f}  "
                  f"val_loss={val_loss:.4f}  best={best_val_loss:.4f}")

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_epoch = epoch
                patience_counter = 0
                best_state = {
                    "model": {k: v.cpu().clone() for k, v in model.state_dict().items()},
                    "predictor": {k: v.cpu().clone() for k, v in predictor.state_dict().items()},
                }
            else:
                patience_counter += 1
                if patience_counter >= PATIENCE // 10:
                    print(f"  Early stopping at epoch {epoch} (best epoch: {best_epoch})")
                    break

    train_time = time.time() - t1
    print(f"\nTraining complete in {train_time:.1f}s (best epoch: {best_epoch})")

    if best_state:
        model.load_state_dict({k: v.to(device) for k, v in best_state["model"].items()})

    print("\nExtracting embeddings...")
    model.eval()
    with torch.no_grad():
        x, rel = model(train_edge_index, train_edge_type)
        node_embeddings = x.cpu().numpy()
        rel_embeddings = rel.cpu().numpy()

    node_ids = np.array(sorted(nodes.keys()))
    embeddings = node_embeddings[node_ids]

    emb_path = OUTPUT_DIR / "compgcn_embeddings.npz"
    np.savez_compressed(
        emb_path,
        node_ids=node_ids,
        embeddings=embeddings,
    )
    print(f"Saved node embeddings: {embeddings.shape} to {emb_path}")

    id_to_rel = {v: k for k, v in rel_to_id.items()}
    rel_path = OUTPUT_DIR / "compgcn_relation_embeddings.npz"
    np.savez_compressed(
        rel_path,
        relation_names=np.array([id_to_rel[i] for i in range(num_base_rels)]),
        embeddings=rel_embeddings[:num_base_rels],
    )
    print(f"Saved relation embeddings: {rel_embeddings[:num_base_rels].shape} to {rel_path}")

    rel_map_path = OUTPUT_DIR / "relation_to_id.json"
    with open(rel_map_path, "w") as f:
        json.dump(rel_to_id, f, indent=2)

    summary = {
        "model": "CompGCN",
        "hidden_dim": HIDDEN_DIM,
        "num_layers": NUM_LAYERS,
        "composition": COMPOSITION,
        "dropout": DROPOUT,
        "learning_rate": LEARNING_RATE,
        "node_embedding_shape": list(embeddings.shape),
        "num_nodes": len(nodes),
        "num_base_relations": num_base_rels,
        "total_parameters": total_params,
        "best_epoch": best_epoch,
        "best_val_loss": round(best_val_loss, 4),
        "training_time_seconds": round(train_time, 1),
        "device": device,
    }
    with open(OUTPUT_DIR / "training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nTotal time: {time.time() - t0:.1f}s")
    print("Done.")


if __name__ == "__main__":
    main()
