"""
Train CompGCN embeddings on CardioKB (HPC version).

CompGCN jointly embeds nodes and relations via composition operators
during message passing. Uses the same 80/10/10 stratified split as
RotatE for fair comparison.

Output: node embeddings saved as .npz for downstream XGBoost link prediction.
"""

import csv
import time
import json
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.amp import autocast, GradScaler
from pathlib import Path

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
TRAIN_SAMPLE_SIZE = 500_000
NEG_RATIO = 1


def load_nodes():
    """Load node metadata and build int_id mapping."""
    nodes = {}
    with open(DATA_DIR / "nodes.tsv") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            nodes[int(row["int_id"])] = row["label"]
    return nodes


def load_split_edges(split_name):
    """Load edges from a split file as numpy arrays."""
    src, dst, rels = [], [], []
    rel_set = set()
    with open(SPLIT_DIR / f"{split_name}_edges.tsv") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            src.append(int(row["src"]))
            dst.append(int(row["dst"]))
            rels.append(row["rel_type"])
            rel_set.add(row["rel_type"])
    return np.array(src, dtype=np.int64), np.array(dst, dtype=np.int64), rels, rel_set


def build_relation_mapping(rel_sets):
    """Build relation-to-index mapping from all splits."""
    all_rels = set()
    for rs in rel_sets:
        all_rels |= rs
    return {r: i for i, r in enumerate(sorted(all_rels))}


def build_edge_index_and_type(src_arr, dst_arr, rel_strs, rel_to_id):
    """Convert edge arrays to PyG format with inverse relations using numpy."""
    num_base_rels = len(rel_to_id)
    rel_ids = np.array([rel_to_id[r] for r in rel_strs], dtype=np.int64)

    all_src = np.concatenate([src_arr, dst_arr])
    all_dst = np.concatenate([dst_arr, src_arr])
    all_rel = np.concatenate([rel_ids, rel_ids + num_base_rels])

    edge_index = torch.from_numpy(np.stack([all_src, all_dst]))
    edge_type = torch.from_numpy(all_rel)
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

        deg = torch.zeros(num_nodes, device=x.device, dtype=x.dtype)
        deg.scatter_add_(0, dst, torch.ones(dst.size(0), device=x.device, dtype=x.dtype))
        deg_inv = 1.0 / deg.clamp(min=1)

        agg = torch.zeros(num_nodes, self.out_dim, device=x.device, dtype=msg.dtype)
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


def sample_negatives_np(src, dst, rel_ids, num_nodes, num_neg=1, rng=None):
    """Vectorized negative sampling using numpy."""
    n = len(src)
    neg_dst = rng.randint(0, num_nodes, size=(n * num_neg,)).astype(np.int64)
    neg_src = np.repeat(src, num_neg)
    neg_rel = np.repeat(rel_ids, num_neg)
    return neg_src, neg_dst, neg_rel


def compute_loss(predictor, x, rel, pos_src, pos_dst, pos_rel,
                 neg_src, neg_dst, neg_rel):
    """Compute BCE loss on positive and negative edges."""
    pos_score = predictor(x[pos_src], rel[pos_rel], x[pos_dst])
    neg_score = predictor(x[neg_src], rel[neg_rel], x[neg_dst])
    pos_loss = F.binary_cross_entropy_with_logits(
        pos_score, torch.ones_like(pos_score))
    neg_loss = F.binary_cross_entropy_with_logits(
        neg_score, torch.zeros_like(neg_score))
    return (pos_loss + neg_loss) / 2


def evaluate_ranking(model, predictor, val_src, val_dst, val_rel_ids,
                     edge_index, edge_type, num_nodes, device, rng):
    """Compute loss on validation set."""
    model.eval()
    predictor.eval()
    with torch.no_grad():
        with autocast("cuda"):
            x, rel = model(edge_index, edge_type)

            neg_src, neg_dst, neg_rel = sample_negatives_np(
                val_src, val_dst, val_rel_ids, num_nodes, rng=rng)

            ps = torch.from_numpy(val_src).to(device)
            pd = torch.from_numpy(val_dst).to(device)
            pr = torch.from_numpy(val_rel_ids).to(device)
            ns = torch.from_numpy(neg_src).to(device)
            nd = torch.from_numpy(neg_dst).to(device)
            nr = torch.from_numpy(neg_rel).to(device)

            loss = compute_loss(predictor, x, rel, ps, pd, pr, ns, nd, nr)

    return loss.item()


def main():
    torch.manual_seed(SEED)
    np.random.seed(SEED)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"CompGCN config:")
    print(f"  hidden_dim={HIDDEN_DIM}, num_layers={NUM_LAYERS}")
    print(f"  composition={COMPOSITION}, dropout={DROPOUT}")
    print(f"  lr={LEARNING_RATE}, epochs={NUM_EPOCHS}, patience={PATIENCE}")
    print(f"  train_sample_size={TRAIN_SAMPLE_SIZE}")
    print(f"  seed={SEED}, device={device}")
    if device == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
        print(f"  GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

    print("\nLoading data...")
    t0 = time.time()

    nodes = load_nodes()
    num_nodes = max(nodes.keys()) + 1
    print(f"  Nodes: {len(nodes):,} (id range 0-{num_nodes - 1})")

    train_src, train_dst, train_rels, train_rel_set = load_split_edges("train")
    val_src, val_dst, val_rels, val_rel_set = load_split_edges("val")
    test_src, test_dst, test_rels, test_rel_set = load_split_edges("test")
    print(f"  Train: {len(train_src):,} edges")
    print(f"  Val:   {len(val_src):,} edges")
    print(f"  Test:  {len(test_src):,} edges")

    rel_to_id = build_relation_mapping([train_rel_set, val_rel_set, test_rel_set])
    num_base_rels = len(rel_to_id)
    print(f"  Relations: {num_base_rels} base types ({num_base_rels * 2} with inverse)")

    train_rel_ids = np.array([rel_to_id[r] for r in train_rels], dtype=np.int64)
    val_rel_ids = np.array([rel_to_id[r] for r in val_rels], dtype=np.int64)
    print(f"  Mapped relation IDs")

    print(f"  Building edge index (numpy)...")
    train_edge_index, train_edge_type = build_edge_index_and_type(
        train_src, train_dst, train_rels, rel_to_id)
    print(f"  Edge index shape: {train_edge_index.shape}")
    train_edge_index = train_edge_index.to(device)
    train_edge_type = train_edge_type.to(device)
    print(f"  Moved edge data to {device}")

    print(f"  Data loaded in {time.time() - t0:.1f}s")

    del train_rels, val_rels, test_rels
    del test_src, test_dst, test_rel_set

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

    if device == "cuda":
        alloc = torch.cuda.memory_allocated() / 1e9
        print(f"  GPU memory allocated: {alloc:.2f} GB")

    optimizer = torch.optim.Adam(
        list(model.parameters()) + list(predictor.parameters()),
        lr=LEARNING_RATE,
    )
    scaler = GradScaler("cuda")

    print(f"\nTraining (subsampling {TRAIN_SAMPLE_SIZE:,} edges per epoch)...")
    t1 = time.time()
    rng = np.random.RandomState(SEED)
    val_rng = np.random.RandomState(SEED + 1)

    best_val_loss = float("inf")
    best_epoch = 0
    patience_counter = 0
    best_state = None
    n_train = len(train_src)

    for epoch in range(1, NUM_EPOCHS + 1):
        model.train()
        predictor.train()
        optimizer.zero_grad()

        with autocast("cuda"):
            x, rel = model(train_edge_index, train_edge_type)

            idx = rng.choice(n_train, size=min(TRAIN_SAMPLE_SIZE, n_train), replace=False)
            batch_src = train_src[idx]
            batch_dst = train_dst[idx]
            batch_rel = train_rel_ids[idx]

            neg_src, neg_dst, neg_rel = sample_negatives_np(
                batch_src, batch_dst, batch_rel, num_nodes, rng=rng)

            ps = torch.from_numpy(batch_src).to(device)
            pd = torch.from_numpy(batch_dst).to(device)
            pr = torch.from_numpy(batch_rel).to(device)
            ns = torch.from_numpy(neg_src).to(device)
            nd = torch.from_numpy(neg_dst).to(device)
            nr = torch.from_numpy(neg_rel).to(device)

            loss = compute_loss(predictor, x, rel, ps, pd, pr, ns, nd, nr)

        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        scaler.step(optimizer)
        scaler.update()

        if epoch % 10 == 0 or epoch == 1:
            val_loss = evaluate_ranking(
                model, predictor, val_src, val_dst, val_rel_ids,
                train_edge_index, train_edge_type, num_nodes, device, val_rng)

            gpu_info = ""
            if device == "cuda":
                gpu_info = f"  gpu={torch.cuda.memory_allocated() / 1e9:.1f}GB"
            print(f"  Epoch {epoch:3d}/{NUM_EPOCHS}  train_loss={loss.item():.4f}  "
                  f"val_loss={val_loss:.4f}  best={best_val_loss:.4f}{gpu_info}")

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
        with autocast("cuda"):
            x, rel = model(train_edge_index, train_edge_type)
        node_embeddings = x.float().cpu().numpy()
        rel_embeddings = rel.float().cpu().numpy()

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
        "train_sample_size": TRAIN_SAMPLE_SIZE,
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
