"""Score photos against category prompts with a local SigLIP model."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps

from src.control import RunControl, SortCancelled
from src.store import EmbeddingCache, file_signature

TEXT_MAX_LENGTH = 64


def pick_device(requested: str) -> torch.device:
    if requested == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")
    return torch.device(requested)


@dataclass
class Backend:
    model_id: str
    device: torch.device
    model: torch.nn.Module
    processor: object
    logit_scale: float
    logit_bias: float


def load_backend(model_id: str, device: torch.device) -> Backend:
    import logging
    import os

    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from transformers import AutoModel, AutoProcessor

    logging.getLogger("transformers").setLevel(logging.ERROR)

    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModel.from_pretrained(model_id)
    model.eval()
    model.to(device)
    scale = float(model.logit_scale.detach().float().cpu().item())
    bias_param = getattr(model, "logit_bias", None)
    bias = 0.0 if bias_param is None else float(bias_param.detach().float().cpu().item())
    return Backend(
        model_id=model_id,
        device=device,
        model=model,
        processor=processor,
        logit_scale=scale,
        logit_bias=bias,
    )


def embed_texts(backend: Backend, texts: list[str]) -> np.ndarray:
    if not texts:
        raise ValueError("No text to embed.")
    encoded = backend.processor(
        text=texts,
        padding="max_length",
        max_length=TEXT_MAX_LENGTH,
        truncation=True,
        return_tensors="pt",
    )
    tensors = {
        key: value.to(backend.device)
        for key, value in encoded.items()
        if key in {"input_ids", "attention_mask"} and torch.is_tensor(value)
    }
    with torch.inference_mode():
        features = backend.model.get_text_features(**tensors)
        return _normalize_features(features)


def embed_image_batch(backend: Backend, images: list[Image.Image]) -> np.ndarray:
    encoded = backend.processor(images=images, return_tensors="pt")
    pixel_values = encoded["pixel_values"].to(backend.device)
    with torch.inference_mode():
        features = backend.model.get_image_features(pixel_values=pixel_values)
        return _normalize_features(features)


def _normalize_features(features: object) -> np.ndarray:
    pooled = _pooled_embedding(features).float()
    if pooled.ndim == 3 and pooled.shape[1] == 1:
        pooled = pooled[:, 0, :]
    if pooled.ndim == 1:
        pooled = pooled.unsqueeze(0)
    if pooled.ndim != 2:
        raise TypeError(f"Expected image or text vectors, got shape {tuple(pooled.shape)}.")
    pooled = pooled / pooled.norm(dim=-1, keepdim=True).clamp(min=1e-12)
    return pooled.detach().cpu().numpy().astype(np.float32)


def _pooled_embedding(features: object) -> torch.Tensor:
    if isinstance(features, torch.Tensor):
        return features
    pooled = getattr(features, "pooler_output", None)
    if isinstance(pooled, torch.Tensor):
        return pooled
    if isinstance(features, (tuple, list)):
        for item in features:
            if isinstance(item, torch.Tensor) and item.ndim == 2:
                return item
    raise TypeError(f"Cannot read embeddings from {type(features).__name__}.")


def load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        transposed = ImageOps.exif_transpose(image)
        return transposed.convert("RGB")


def collect_embeddings(
    backend: Backend,
    paths: list[Path],
    cache: EmbeddingCache | None,
    batch_size: int,
    on_status: Callable[[str], None] | None = None,
    control: RunControl | None = None,
) -> tuple[dict[str, np.ndarray], list[tuple[Path, str]], list[str], list[int], list[int], np.ndarray]:
    """Embed paths, reusing cache rows whose path, mtime, and size still match.

    Returns per-path vectors for photos that loaded, unreadable files, and the
    arrays to write back to the cache (every successfully read photo).
    """
    from tqdm import tqdm

    def report(message: str) -> None:
        print(message)
        if on_status is not None:
            on_status(message)

    vectors: dict[str, np.ndarray] = {}
    failures: list[tuple[Path, str]] = []
    pending: list[Path] = []

    for path in paths:
        key, mtime_ns, size = file_signature(path)
        cached = None if cache is None else cache.lookup(key, mtime_ns, size)
        if cached is None:
            pending.append(path)
        else:
            vectors[key] = np.asarray(cached, dtype=np.float32)

    reused = len(paths) - len(pending)
    if reused:
        report(f"Reusing {reused} cached embedding{'s' if reused != 1 else ''}.")

    if pending:
        steps = range(0, len(pending), batch_size)
        report(f"Embedding {len(pending)} photo{'s' if len(pending) != 1 else ''}...")
        for start in tqdm(steps, desc="Embedding photos", unit="batch"):
            if control is not None:
                try:
                    control.checkpoint()
                except SortCancelled:
                    report("Stopping after the last finished batch...")
                    break
            chunk = pending[start : start + batch_size]
            loaded: list[tuple[Path, Image.Image]] = []
            for path in chunk:
                try:
                    loaded.append((path, load_rgb(path)))
                except Exception as exc:
                    failures.append((path, str(exc)))
            if loaded:
                try:
                    matrix = embed_image_batch(backend, [image for _, image in loaded])
                except Exception:
                    matrix = None
                if matrix is not None and len(matrix) == len(loaded):
                    for (path, _), row in zip(loaded, matrix, strict=True):
                        key, _, _ = file_signature(path)
                        vectors[key] = row
                else:
                    for path, image in loaded:
                        try:
                            row = embed_image_batch(backend, [image])[0]
                        except Exception as exc:
                            failures.append((path, str(exc)))
                            continue
                        key, _, _ = file_signature(path)
                        vectors[key] = row
            done = min(start + batch_size, len(pending))
            report(f"Embedded {done} of {len(pending)}")

    cache_paths: list[str] = []
    cache_mtimes: list[int] = []
    cache_sizes: list[int] = []
    rows: list[np.ndarray] = []
    for path in paths:
        key, mtime_ns, size = file_signature(path)
        row = vectors.get(key)
        if row is None:
            continue
        cache_paths.append(key)
        cache_mtimes.append(mtime_ns)
        cache_sizes.append(size)
        rows.append(row)

    if rows:
        matrix = np.stack(rows).astype(np.float32)
    else:
        matrix = np.zeros((0, 0), dtype=np.float32)
    return vectors, failures, cache_paths, cache_mtimes, cache_sizes, matrix
