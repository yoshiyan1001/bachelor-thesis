from onoma_app import db
from onoma_app.config import SOUNDS_DIR
from onoma_app.utils import extract_advanced_feature_vector
import sys

import numpy as np
import json
import logging

logger = logging.getLogger(__name__)

PCA_SCALE = 200.0   # world-unit radius for the 3-D PCA space

def _calculate_cosine_sim(vector_a, vector_b):
    """Cosine similarity between two vectors. Returns 0.0 for zero vectors."""
    norm_a = np.linalg.norm(vector_a)
    norm_b = np.linalg.norm(vector_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(vector_a, vector_b) / (norm_a * norm_b))


def _load_variant_vectors(feature_type):
    """
    Load stored feature vectors for all variants of the given type.
    """
    out = {}
    for row in db.list_features_by_type(feature_type):
        try:
            vec = json.loads(row["data_json"])
            out[int(row["variant_id"])] = np.array(vec, dtype=float)
        except Exception:
            logger.warning("Failed to load feature for variant %s", row["variant_id"])
    return out


def _check_variant_vectors(feature_type):
    """
    Ensure every variant has a stored feature vector of the given type.
    Extracts and stores any that are missing, then returns the full dict.
    """
    if feature_type != "advanced": # make sure we use advanced feature
        raise ValueError("Similarity graph construction requires advanced feature vectors.")

    variants = db.list_variants()
    vectors = _load_variant_vectors(feature_type)

    for variant in variants:
        variant_id = int(variant["id"])
        if variant_id in vectors:
            continue

        sound_path = SOUNDS_DIR / variant["sound_file"]
        if not sound_path.exists():
            logger.warning("Sound file not found for variant %s: %s",
                           variant["id"], variant["sound_file"])
            continue

        vec = extract_advanced_feature_vector(str(sound_path))  # 62 dimensions
        if vec is None:
            logger.warning("Failed to extract features for variant %s: %s",
                           variant["id"], variant["sound_file"])
            continue

        serializable = vec.tolist() if isinstance(vec, np.ndarray) else list(vec)
        db.upsert_feature(variant_id, feature_type, serializable)
        vectors[variant_id] = np.array(serializable, dtype=float)

    return vectors


def _build_item_vectors():
    """
    Build item-level feature vectors by averaging across each item's variants.
    Returns (items, item_vectors) where item_vectors maps item_id → np.ndarray.
    """
    items = db.list_items()
    variants = db.list_variants()

    by_item = {}
    for variant in variants:
        by_item.setdefault(int(variant["item_id"]), []).append(variant)

    advanced_vectors = _check_variant_vectors("advanced")
    item_vectors = {}

    for item in items:
        item_id = int(item["id"])
        item_variants = by_item.get(item_id, [])
        vecs = [advanced_vectors[int(v["id"])]
                for v in item_variants if int(v["id"]) in advanced_vectors]
        if vecs:
            item_vectors[item_id] = np.mean(np.vstack(vecs), axis=0)

    return items, item_vectors


# ── Edge computation ──────────────────────────────────────────────────────────

def _compute_similarity_edges(item_ids, item_vectors, top_k, threshold):
    """
    Compute cosine-similarity edges between items.
    Keeps at most top_k neighbours per node above the similarity threshold.
    Returns a dict mapping (src_id, tgt_id) → similarity (src < tgt).
    """
    edges = {}

    for src_id in item_ids:
        candidates = []
        for tgt_id in item_ids:
            if src_id == tgt_id:
                continue
            sim = _calculate_cosine_sim(item_vectors[src_id], item_vectors[tgt_id])
            if sim >= threshold:
                candidates.append((tgt_id, sim))

        candidates.sort(key=lambda x: (-x[1], x[0]))

        for tgt_id, sim in candidates[:top_k]:
            key = tuple(sorted([src_id, tgt_id]))
            if key not in edges or sim > edges[key]:
                edges[key] = sim

    return edges

def build_graph_version(name="draft", top_k=sys.maxsize, threshold=0.0): # NOTE: if data is very big, we need to fix top_k and threshold values to look a graph more visible.
    """
    Build a new draft graph version from audio feature vectors and persist it.

    Node positions are not stored here — the 3-D layout is computed on demand
    by compute_pca_positions() at render time, so x/y are left as None.

    Returns:
        dict with version_id, nodes_count, edges_count.
    """
    items, item_vectors = _build_item_vectors()
    if not item_vectors:
        raise ValueError("No feature vectors available for graph build")
    
    logger.info("Building similarity graph for %d items.", len(item_vectors))

    id_to_label = {int(item["id"]): item["label"] for item in items}
    item_ids = sorted(item_vectors.keys())

    edges = _compute_similarity_edges(item_ids, item_vectors, top_k, threshold)

    # Nodes carry no 2-D position — layout is handled by PCA at render time
    nodes = [{"item_id": item_id, "label": id_to_label[item_id],
               "x": None, "y": None, "fixed": False}
             for item_id in item_ids]

    version_id = db.create_graph_version(name=name, status="draft")
    db.insert_graph_nodes(version_id, nodes)
    db.insert_graph_edges(
        version_id,
        [{"source_item_id": a, "target_item_id": b, "similarity": sim}
         for (a, b), sim in edges.items()],
    )

    return {
        "version_id":   version_id,
        "nodes_count":  len(nodes),
        "edges_count":  len(edges),
    }


def compute_pca_positions(scale=PCA_SCALE):
    """
    Project item-level feature vectors into 3-D via PCA.

    Returns a dict with:
      "positions": { item_id → { x, y, z, label } }
      "axes":      [ { name, description, variance_ratio }, ... ]  (PC1-PC3)
    """
    items, item_vectors = _build_item_vectors()
    if not item_vectors:
        return {}

    id_to_label = {int(item["id"]): item["label"] for item in items}
    item_ids    = sorted(item_vectors.keys())

    # Stack into matrix (N × D), then centre
    X = np.vstack([item_vectors[i] for i in item_ids])
    X = X - X.mean(axis=0)

    # With only one item, centering produces an all-zero matrix — PCA is
    # meaningless, so place the single node at the origin and return stub axes.
    if len(item_ids) < 2 or np.allclose(X, 0):
        positions = {
            item_id: {"x": 0.0, "y": 0.0, "z": 0.0,
                      "label": id_to_label.get(item_id, str(item_id))}
            for item_id in item_ids
        }
        axes = [
            {"name": f"PC{i+1}", "description": "Not enough data for PCA.", "variance_ratio": 0.0}
            for i in range(3)
        ]
        return {"positions": positions, "axes": axes}

    # PCA via SVD — works even when N < D
    _, S, Vt = np.linalg.svd(X, full_matrices=False)

    # Variance explained per component — guard against all-zero S
    var       = S ** 2
    total_var = var.sum()
    var_ratio = var / total_var if total_var > 0 else np.zeros_like(var)

    # Pad to at least 3 components when N < 3 (too few data points for full PCA)
    n_components = Vt.shape[0]
    if n_components < 3:
        pad_rows = 3 - n_components
        Vt        = np.vstack([Vt,        np.zeros((pad_rows, Vt.shape[1]))])
        var_ratio = np.concatenate([var_ratio, np.zeros(pad_rows)])

    # Project onto first 3 PCs -> (N, 3), then normalise to fit within `scale`
    coords  = X @ Vt[:3].T
    max_abs = np.abs(coords).max()
    if max_abs > 0:
        coords = coords / max_abs * scale

    # Interpret each PC by its dominant feature group
    # Feature layout in the 62-dim vector (matches utils.py):
    #   [0:13]   MFCC mean          — timbre / spectral shape
    #   [13:26]  MFCC delta mean    — timbre dynamics (rate of change)
    #   [26:39]  MFCC delta² mean   — timbre acceleration
    #   [39:51]  Chroma mean        — pitch-class / harmonic content
    #   [51:55]  Scalars            — brightness, noisiness, rolloff, bandwidth
    #   [55:62]  Spectral contrast  — texture / roughness
    FEATURE_GROUPS = [
        (slice(0,  13), "timbre (MFCC)"),
        (slice(13, 26), "timbre dynamics (MFCC Δ)"),
        (slice(26, 39), "timbre acceleration (MFCC Δ²)"),
        (slice(39, 51), "pitch / harmonic content (chroma)"),
        (slice(51, 55), "brightness & noisiness (spectral scalars)"),
        (slice(55, 62), "texture / roughness (spectral contrast)"),
    ]

    def _describe_pc(pc_vec):
        loadings = sorted(
            [(float(np.abs(pc_vec[slc]).sum()), name) for slc, name in FEATURE_GROUPS],
            reverse=True,
        )
        total = sum(l for l, _ in loadings) or 1.0
        top = [name for _, name in loadings[:3]]
        parts = ", ".join(top)
        return f"Driven by: {parts}"

    axes = [
        {
            "name": f"PC{i + 1}",
            "description": _describe_pc(Vt[i]),
            "variance_ratio": float(round(var_ratio[i] * 100, 1)),
        }
        for i in range(3)
    ]

    positions = {
        item_id: {
            "x": float(coords[idx, 0]),
            "y": float(coords[idx, 1]),
            "z": float(coords[idx, 2]),
            "label": id_to_label.get(item_id, str(item_id)),
        }
        for idx, item_id in enumerate(item_ids)
    }

    return {"positions": positions, "axes": axes}
