"""Copy grouped photos into folders and write manifest.csv."""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


MANIFEST_NAME = "manifest.csv"
MANIFEST_FIELDS = [
    "source_path",
    "primary_label",
    "other_labels",
    "scores_json",
    "destinations",
    "error",
]


@dataclass(frozen=True)
class PhotoRecord:
    source: Path
    primary: str
    others: list[str]
    scores: dict[str, float]
    error: str = ""


def safe_folder_name(name: str) -> str:
    cleaned = "".join("_" if char in '<>:"/\\|?*' else char for char in name).strip().rstrip(".")
    return cleaned or "category"


def flat_filename(source: Path, root: Path) -> str:
    relative = source.resolve().relative_to(root.resolve())
    parts = list(relative.parts)
    filename = parts[-1]
    if len(parts) == 1:
        return _safe_filename(filename)
    parent = "_".join(_safe_filename(part) for part in parts[:-1])
    return f"{parent}__{_safe_filename(filename)}"


def _safe_filename(name: str) -> str:
    cleaned = "".join("_" if char in '<>:"/\\|?*' else char for char in name).strip().rstrip(".")
    return cleaned or "photo"


def allocate_filenames(records: list[PhotoRecord], root: Path) -> dict[Path, str]:
    """Give each source a unique destination filename, case-insensitive."""
    used: set[str] = set()
    mapping: dict[Path, str] = {}
    for record in records:
        if record.error:
            continue
        base = flat_filename(record.source, root)
        stem = Path(base).stem
        ext = Path(base).suffix
        candidate = base
        number = 2
        while candidate.casefold() in used:
            candidate = f"{stem}_{number}{ext}"
            number += 1
        used.add(candidate.casefold())
        mapping[record.source] = candidate
    return mapping


def managed_folders(output_dir: Path, folder_names: list[str]) -> list[str]:
    names = list(folder_names)
    manifest = output_dir / MANIFEST_NAME
    if not manifest.is_file():
        return names
    with manifest.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            for destination in (row.get("destinations") or "").split("|"):
                if not destination:
                    continue
                top = Path(destination).parts[0]
                if top and top not in names and top != ".cache":
                    names.append(top)
    return names


def reset_group_folders(output_dir: Path, folder_names: list[str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in folder_names:
        folder = output_dir / name
        if folder.is_dir():
            try:
                shutil.rmtree(folder)
            except OSError as exc:
                raise RuntimeError(
                    f"Could not replace {folder}. Close any photos open from that folder and run again."
                ) from exc


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def export_records(
    records: list[PhotoRecord],
    input_dir: Path,
    output_dir: Path,
    folder_names: list[str],
) -> Path:
    """Replace group folders, copy photos into each matching group, write the manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    reset_group_folders(output_dir, managed_folders(output_dir, folder_names))
    filenames = allocate_filenames(records, input_dir)
    manifest_path = output_dir / MANIFEST_NAME

    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for record in records:
            destinations: list[str] = []
            if not record.error:
                filename = filenames[record.source]
                for label in [record.primary, *record.others]:
                    folder = output_dir / safe_folder_name(label)
                    folder.mkdir(parents=True, exist_ok=True)
                    target = folder / filename
                    shutil.copy2(record.source, target)
                    destinations.append(target.relative_to(output_dir).as_posix())
            writer.writerow(
                {
                    "source_path": str(record.source),
                    "primary_label": record.primary,
                    "other_labels": "|".join(record.others),
                    "scores_json": json.dumps({name: round(score, 4) for name, score in record.scores.items()}),
                    "destinations": "|".join(destinations),
                    "error": record.error,
                }
            )
    return manifest_path
