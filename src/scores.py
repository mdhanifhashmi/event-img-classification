"""SigLIP probability math. No model code lives here, so tests can run without PyTorch."""

from __future__ import annotations

import math

import numpy as np


def sigmoid_scores(
    image_embeds: np.ndarray,
    text_embeds: np.ndarray,
    logit_scale: float,
    logit_bias: float,
) -> np.ndarray:
    """Return SigLIP probabilities for each image against each text.

    image_embeds is (N, D) and text_embeds is (C, D). Both are L2-normalized
    here so cached vectors and freshly encoded text share one scale.
    """
    images = _l2_normalize(np.asarray(image_embeds, dtype=np.float32))
    texts = _l2_normalize(np.asarray(text_embeds, dtype=np.float32))
    if images.ndim == 1:
        images = images.reshape(1, -1)
    if texts.ndim == 1:
        texts = texts.reshape(1, -1)
    logits = images @ texts.T
    logits = logits * math.exp(float(logit_scale)) + float(logit_bias)
    return _stable_sigmoid(logits)


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return vectors / norms


def _stable_sigmoid(logits: np.ndarray) -> np.ndarray:
    positive = logits >= 0
    result = np.empty_like(logits, dtype=np.float32)
    result[positive] = 1.0 / (1.0 + np.exp(-logits[positive]))
    exp_logits = np.exp(logits[~positive])
    result[~positive] = exp_logits / (1.0 + exp_logits)
    return result
