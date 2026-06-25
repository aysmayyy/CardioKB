"""
Train RotatE embeddings on CardioKB using PyKEEN (HPC version).

RotatE models relations as rotations in complex embedding space.
Uses the same 80/10/10 stratified split as Node2Vec for fair comparison.
"""

import time
import json
import numpy as np
import torch
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
SPLIT_DIR = DATA_DIR / "splits"
OUTPUT_DIR = DATA_DIR / "rotate"
OUTPUT_DIR.mkdir(exist_ok=True)

EMBEDDING_DIM = 128
NUM_EPOCHS = 200
BATCH_SIZE = 4096
LEARNING_RATE = 1e-4
NEGATIVE_SAMPLES = 64
SEED = 42


def load_triples(split_name):
    """Load split file as numpy array of [head, relation, tail] strings."""
    import csv
    triples = []
    with open(SPLIT_DIR / f"{split_name}_edges.tsv") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            triples.append([row["src"], row["rel_type"], row["dst"]])
    return triples


def main():
    from pykeen.triples import TriplesFactory
    from pykeen.pipeline import pipeline
    from pykeen.models import RotatE

    print(f"RotatE config:")
    print(f"  embedding_dim={EMBEDDING_DIM}, epochs={NUM_EPOCHS}")
    print(f"  batch_size={BATCH_SIZE}, lr={LEARNING_RATE}")
    print(f"  negative_samples={NEGATIVE_SAMPLES}, seed={SEED}")

    torch.manual_seed(SEED)
    np.random.seed(SEED)

    print("\nLoading splits...")
    t0 = time.time()

    train_triples = load_triples("train")
    val_triples = load_triples("val")
    test_triples = load_triples("test")

    print(f"  Train: {len(train_triples):,} triples")
    print(f"  Val:   {len(val_triples):,} triples")
    print(f"  Test:  {len(test_triples):,} triples")

    train_tf = TriplesFactory.from_labeled_triples(
        np.array(train_triples, dtype=str),
        create_inverse_triples=False,
    )
    val_tf = TriplesFactory.from_labeled_triples(
        np.array(val_triples, dtype=str),
        entity_to_id=train_tf.entity_to_id,
        relation_to_id=train_tf.relation_to_id,
    )
    test_tf = TriplesFactory.from_labeled_triples(
        np.array(test_triples, dtype=str),
        entity_to_id=train_tf.entity_to_id,
        relation_to_id=train_tf.relation_to_id,
    )

    print(f"  Entities: {train_tf.num_entities:,}")
    print(f"  Relations: {train_tf.num_relations}")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    print(f"\nTraining RotatE...")
    t1 = time.time()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  Device: {device}")
    if device == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")

    result = pipeline(
        training=train_tf,
        validation=val_tf,
        testing=test_tf,
        model="RotatE",
        model_kwargs={
            "embedding_dim": EMBEDDING_DIM,
        },
        optimizer="Adam",
        optimizer_kwargs={
            "lr": LEARNING_RATE,
        },
        training_kwargs={
            "num_epochs": NUM_EPOCHS,
            "batch_size": BATCH_SIZE,
        },
        negative_sampler="basic",
        negative_sampler_kwargs={
            "num_negs_per_pos": NEGATIVE_SAMPLES,
        },
        loss="NSSALoss",
        loss_kwargs={
            "margin": 9.0,
            "adversarial_temperature": 1.0,
        },
        stopper="early",
        stopper_kwargs={
            "patience": 10,
            "frequency": 10,
            "metric": "inverse_harmonic_mean_rank",
        },
        evaluator_kwargs={
            "filtered": True,
        },
        random_seed=SEED,
        device=device,
    )

    train_time = time.time() - t1
    print(f"\nTraining complete in {train_time:.1f}s")

    print("\n" + "=" * 60)
    print("TEST SET EVALUATION (PyKEEN native metrics)")
    print("=" * 60)
    metrics = result.metric_results.to_dict()
    for key in ["both.realistic.inverse_harmonic_mean_rank",
                "both.realistic.hits_at_10",
                "both.realistic.hits_at_100"]:
        if key in metrics:
            print(f"  {key}: {metrics[key]:.4f}")

    model = result.model
    entity_embeddings = model.entity_representations[0](
        indices=torch.arange(train_tf.num_entities, device=model.device)
    ).detach().cpu().numpy()

    if np.iscomplexobj(entity_embeddings):
        entity_real = entity_embeddings.real
        entity_imag = entity_embeddings.imag
        entity_concat = np.concatenate([entity_real, entity_imag], axis=1)
    else:
        emb_shape = entity_embeddings.shape
        if len(emb_shape) == 2 and emb_shape[1] == 2 * EMBEDDING_DIM:
            entity_real = entity_embeddings[:, :EMBEDDING_DIM]
            entity_imag = entity_embeddings[:, EMBEDDING_DIM:]
            entity_concat = entity_embeddings
        else:
            entity_concat = entity_embeddings

    id_to_entity = {v: int(k) for k, v in train_tf.entity_to_id.items()}
    node_ids = np.array([id_to_entity[i] for i in range(train_tf.num_entities)])

    emb_path = OUTPUT_DIR / "rotate_embeddings.npz"
    np.savez_compressed(
        emb_path,
        node_ids=node_ids,
        embeddings=entity_concat,
    )
    print(f"\nSaved entity embeddings: {entity_concat.shape} to {emb_path}")

    rel_embeddings = model.relation_representations[0](
        indices=torch.arange(train_tf.num_relations, device=model.device)
    ).detach().cpu().numpy()
    rel_id_to_name = {v: k for k, v in train_tf.relation_to_id.items()}

    rel_path = OUTPUT_DIR / "rotate_relation_embeddings.npz"
    np.savez_compressed(
        rel_path,
        relation_names=np.array([rel_id_to_name[i] for i in range(train_tf.num_relations)]),
        embeddings=rel_embeddings if not np.iscomplexobj(rel_embeddings)
                   else np.concatenate([rel_embeddings.real, rel_embeddings.imag], axis=1),
    )
    print(f"Saved relation embeddings: shape {rel_embeddings.shape} to {rel_path}")

    model_path = OUTPUT_DIR / "rotate_model.pkl"
    torch.save(model.state_dict(), model_path)
    print(f"Saved model state dict to {model_path}")

    id_map_path = OUTPUT_DIR / "entity_to_id.json"
    with open(id_map_path, "w") as f:
        json.dump(train_tf.entity_to_id, f)

    rel_map_path = OUTPUT_DIR / "relation_to_id.json"
    with open(rel_map_path, "w") as f:
        json.dump(train_tf.relation_to_id, f)

    summary = {
        "model": "RotatE",
        "embedding_dim": EMBEDDING_DIM,
        "entity_embedding_shape": list(entity_concat.shape),
        "num_entities": train_tf.num_entities,
        "num_relations": train_tf.num_relations,
        "num_epochs_trained": result.stopper.best_epoch if hasattr(result, "stopper") and result.stopper else NUM_EPOCHS,
        "training_time_seconds": round(train_time, 1),
        "device": device,
        "test_metrics": {
            k: round(v, 4) if isinstance(v, float) else v
            for k, v in metrics.items()
            if "realistic" in k and "both" in k
        },
    }
    with open(OUTPUT_DIR / "training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nTotal time: {time.time() - t0:.1f}s")
    print("Done.")


if __name__ == "__main__":
    main()
