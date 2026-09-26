"""Find image files in a folder."""

from __future__ import annotations

from pathlib import Path


def register_heif() -> None:
    """Allow Pillow to open iPhone HEIC and HEIF photos."""
    try:
        from pillow_heif import register_heif_opener
    except ImportError as exc:
        raise RuntimeError("pillow-heif is required to read HEIC photos. Install requirements.txt.") from exc
    register_heif_opener()


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".heic",
    ".heif",
    ".bmp",
    ".tif",
    ".tiff",
}


def scan_images(input_dir: Path, exclude: Path | None = None) -> list[Path]:
    """Return image files under input_dir, skipping hidden folders and exclude.

    exclude is typically the output folder when it sits inside the input folder,
    so copies from an earlier run are not sorted again.
    """
    root = input_dir.resolve()
    excluded = exclude.resolve() if exclude is not None else None
    found: list[Path] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        resolved = path.resolve()
        if excluded is not None and (resolved == excluded or excluded in resolved.parents):
            continue
        found.append(resolved)

    found.sort()
    return found
