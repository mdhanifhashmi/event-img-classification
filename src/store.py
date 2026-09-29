"""Read and write the embedding cache stored beside a sort run."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CACHE_DIRNAME = ".cache"
EMBEDDINGS_NAME = "embeddings.npz"
INDEX_NAME = "index.json"


@dataclass
class EmbeddingCache:
    model: str
    paths: list[str]
    mtimes_ns: list[int]
    sizes: list[int]
    embeddings: np.ndarray

    def __post_init__(self) -> None:
        self._index = {
            (path, mtime, size): index
            for index, (path, mtime, size) in enumerate(zip(self.paths, self.mtimes_ns, self.sizes, strict=True))
        }

    def lookup(self, path: str, mtime_ns: int, size: int) -> np.ndarray | None:
        index = self._index.get((path, mtime_ns, size))
        if index is None:
            return None
        return np.array(self.embeddings[index], dtype=np.float32, copy=True)


def cache_dir(output_dir: Path) -> Path:
    return output_dir / CACHE_DIRNAME


def load_cache(output_dir: Path) -> EmbeddingCache | None:
    folder = cache_dir(output_dir)
    index_path = folder / INDEX_NAME
    embeddings_path = folder / EMBEDDINGS_NAME
    if not index_path.is_file() or not embeddings_path.is_file():
        return None

    index = json.loads(index_path.read_text(encoding="utf-8"))
    model = str(index.get("model") or "")
    if not model:
        return None

    paths = [str(path) for path in index.get("paths", [])]
    mtimes_ns = [int(value) for value in index.get("mtimes_ns", [])]
    sizes = [int(value) for value in index.get("sizes", [])]
    with np.load(embeddings_path) as data:
        embeddings = np.array(data["embeddings"], dtype=np.float32, copy=True)
    if embeddings.ndim != 2 or len(paths) != len(embeddings) or len(paths) != len(mtimes_ns) or len(paths) != len(sizes):
        return None

    return EmbeddingCache(
        model=model,
        paths=paths,
        mtimes_ns=mtimes_ns,
        sizes=sizes,
        embeddings=embeddings,
    )


def save_cache(
    output_dir: Path,
    model: str,
    paths: list[str],
    mtimes_ns: list[int],
    sizes: list[int],
    embeddings: np.ndarray,
) -> None:
    folder = cache_dir(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    matrix = np.asarray(embeddings, dtype=np.float32)
    if matrix.ndim != 2 or len(paths) != len(matrix):
        raise ValueError("Embedding cache paths and vectors do not match.")
    temporary_embeddings = folder / "embeddings.tmp.npz"
    np.savez_compressed(temporary_embeddings, embeddings=matrix)
    temporary_embeddings.replace(folder / EMBEDDINGS_NAME)
    payload = {
        "model": model,
        "paths": paths,
        "mtimes_ns": mtimes_ns,
        "sizes": sizes,
    }
    temporary_index = folder / "index.tmp.json"
    temporary_index.write_text(json.dumps(payload), encoding="utf-8")
    temporary_index.replace(folder / INDEX_NAME)


def merge_cache(
    output_dir: Path,
    model: str,
    paths: list[str],
    mtimes_ns: list[int],
    sizes: list[int],
    embeddings: np.ndarray,
) -> None:
    """Add these embeddings to the cache, leaving vectors from earlier inputs in place."""
    rows: dict[str, tuple[int, int, np.ndarray]] = {}
    current = load_cache(output_dir)
    if current is not None and current.model == model:
        for path, mtime, size, vector in zip(
            current.paths,
            current.mtimes_ns,
            current.sizes,
            current.embeddings,
            strict=True,
        ):
            rows[path] = (mtime, size, np.array(vector, dtype=np.float32, copy=True))
    for path, mtime, size, vector in zip(paths, mtimes_ns, sizes, embeddings, strict=True):
        rows[path] = (int(mtime), int(size), np.asarray(vector, dtype=np.float32))
    if not rows:
        return
    ordered = list(rows.items())
    save_cache(
        output_dir,
        model,
        [path for path, _item in ordered],
        [item[0] for _path, item in ordered],
        [item[1] for _path, item in ordered],
        np.stack([item[2] for _path, item in ordered]),
    )


def file_signature(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return str(path.resolve()), stat.st_mtime_ns, stat.st_size
