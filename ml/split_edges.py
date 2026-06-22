"""
Stratified 80/10/10 train/val/test split of CardioKB edges.

Splits edges proportionally within each relationship type so all
edge types are represented in all splits. Saves train-only edgelist
for Node2Vec (no val/test leakage) and split metadata for downstream
link prediction.
"""

import csv
import json
import numpy as np
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).resolve().parent / "data"
EDGES_PATH = DATA_DIR / "edges.tsv"

TRAIN_RATIO = 0.8
VAL_RATIO = 0.1
TEST_RATIO = 0.1
SEED = 42


def load_edges():
    """Load all edges grouped by relationship type."""
    edges_by_type = defaultdict(list)
    with open(EDGES_PATH) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            src, dst, rel = int(row["src"]), int(row["dst"]), row["rel_type"]
            edges_by_type[rel].append((src, dst))
    return edges_by_type


def stratified_split(edges_by_type):
    """Split edges 80/10/10 within each edge type."""
    rng = np.random.RandomState(SEED)

    train_edges = []
    val_edges = []
    test_edges = []
    stats = {}

    for rel_type, edges in sorted(edges_by_type.items()):
        arr = np.array(edges)
        n = len(arr)
        idx = rng.permutation(n)

        n_test = max(1, int(n * TEST_RATIO))
        n_val = max(1, int(n * VAL_RATIO))
        n_train = n - n_val - n_test

        test_idx = idx[:n_test]
        val_idx = idx[n_test:n_test + n_val]
        train_idx = idx[n_test + n_val:]

        for i in train_idx:
            train_edges.append((edges[i][0], edges[i][1], rel_type))
        for i in val_idx:
            val_edges.append((edges[i][0], edges[i][1], rel_type))
        for i in test_idx:
            test_edges.append((edges[i][0], edges[i][1], rel_type))

        stats[rel_type] = {
            "total": n,
            "train": len(train_idx),
            "val": len(val_idx),
            "test": len(test_idx),
        }

    return train_edges, val_edges, test_edges, stats


def save_split(train_edges, val_edges, test_edges, stats):
    """Save split files."""
    split_dir = DATA_DIR / "splits"
    split_dir.mkdir(exist_ok=True)

    # Train edgelist for Node2Vec (plain src\tdst, no header, no rel_type)
    train_edgelist_path = split_dir / "train_edgelist.txt"
    with open(train_edgelist_path, "w") as f:
        for src, dst, _ in train_edges:
            f.write(f"{src}\t{dst}\n")

    # Full split files with rel_type (for link prediction)
    for name, edges in [("train", train_edges), ("val", val_edges), ("test", test_edges)]:
        path = split_dir / f"{name}_edges.tsv"
        with open(path, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(["src", "dst", "rel_type"])
            for src, dst, rel in edges:
                writer.writerow([src, dst, rel])

    # Stats
    with open(split_dir / "split_stats.json", "w") as f:
        json.dump({
            "total_edges": len(train_edges) + len(val_edges) + len(test_edges),
            "train": len(train_edges),
            "val": len(val_edges),
            "test": len(test_edges),
            "per_type": stats,
        }, f, indent=2)

    return train_edgelist_path


def main():
    print("Loading edges...")
    edges_by_type = load_edges()
    total = sum(len(v) for v in edges_by_type.values())
    print(f"Total edges: {total:,} across {len(edges_by_type)} types")

    print("\nSplitting 80/10/10 stratified by edge type...")
    train_edges, val_edges, test_edges, stats = stratified_split(edges_by_type)

    print(f"\nSplit sizes:")
    print(f"  Train: {len(train_edges):,} ({100*len(train_edges)/total:.1f}%)")
    print(f"  Val:   {len(val_edges):,} ({100*len(val_edges)/total:.1f}%)")
    print(f"  Test:  {len(test_edges):,} ({100*len(test_edges)/total:.1f}%)")

    print(f"\nPer edge type:")
    print(f"  {'Type':<45} {'Total':>8} {'Train':>8} {'Val':>6} {'Test':>6}")
    print(f"  {'-'*75}")
    for rel, s in sorted(stats.items(), key=lambda x: -x[1]["total"]):
        print(f"  {rel:<45} {s['total']:>8,} {s['train']:>8,} {s['val']:>6,} {s['test']:>6,}")

    # Key stat: drugTreatsDisease split
    dtt = stats.get("drugTreatsDisease", {})
    print(f"\ndrugTreatsDisease split: {dtt.get('train',0)} train / "
          f"{dtt.get('val',0)} val / {dtt.get('test',0)} test")

    train_edgelist_path = save_split(train_edges, val_edges, test_edges, stats)
    print(f"\nSaved to {DATA_DIR / 'splits'}:")
    print(f"  train_edgelist.txt  — Node2Vec input ({len(train_edges):,} edges, no val/test)")
    print(f"  train_edges.tsv     — with rel_type column")
    print(f"  val_edges.tsv       — validation set")
    print(f"  test_edges.tsv      — test set")
    print(f"  split_stats.json    — split statistics")


if __name__ == "__main__":
    main()
