"""Sort a mixed event-photo folder into named groups."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

try:
    from src.classify import collect_embeddings, embed_texts, load_backend, pick_device
    from src.export import PhotoRecord, already_sorted_sources, export_records, safe_folder_name
    from src.labels import assign_labels, load_settings
    from src.scan import register_heif, scan_images
    from src.scores import sigmoid_scores
    from src.store import load_cache, merge_cache, save_cache
except ModuleNotFoundError as exc:
    print(f"Missing library '{exc.name}'. Follow the setup steps in README.md.", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "categories.yaml"
LAST_RUN = ROOT / ".last_run.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Copy event photos into named groups using a local SigLIP model."
    )
    parser.add_argument("--input", required=True, type=Path, help="Folder of mixed event photos")
    parser.add_argument("--output", required=True, type=Path, help="Folder to receive the grouped copies")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Category YAML file")
    parser.add_argument("--threshold", type=float, default=None, help="Override min_score from the config")
    parser.add_argument("--batch-size", type=int, default=4, help="Photos embedded at once (lower uses less RAM)")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--model", default=None, help="Override the SigLIP model id from the config")
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Add photos to the output groups instead of replacing those groups",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        return 1


def run(args: argparse.Namespace) -> int:
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1.")
    if args.threshold is not None and not 0.0 <= args.threshold <= 1.0:
        raise ValueError("--threshold must be between 0 and 1.")

    input_dir = args.input.expanduser().resolve()
    output_dir = args.output.expanduser().resolve()
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input folder not found: {input_dir}")
    if output_dir == input_dir:
        raise ValueError("Output folder must be different from the input folder.")

    config_path = args.config.expanduser().resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"Config not found: {config_path}")

    settings = load_settings(config_path)
    min_score = settings.min_score if args.threshold is None else args.threshold
    model_id = args.model or settings.model

    folder_names = [safe_folder_name(name) for name in [*settings.names, settings.review_label]]
    if len({name.casefold() for name in folder_names}) != len(folder_names):
        raise ValueError("Two categories would use the same folder name.")

    keep_existing = bool(getattr(args, "keep_existing", False))
    register_heif()
    photos = scan_images(input_dir, exclude=output_dir if _is_inside(output_dir, input_dir) else None)
    if not photos:
        raise ValueError(f"No images found in {input_dir}")
    if keep_existing:
        already = already_sorted_sources(output_dir)
        fresh = [photo for photo in photos if str(photo.resolve()) not in already]
        kept = len(photos) - len(fresh)
        if kept:
            _notify(
                args,
                f"Keeping existing groups. {kept} photo{'s' if kept != 1 else ''} already sorted will stay.",
            )
        photos = fresh
        if not photos:
            _notify(args, "Nothing new to add. The output folder was left as it is.")
            return 0

    _notify(args, f"Found {len(photos)} image{'s' if len(photos) != 1 else ''} in {input_dir}")
    device = pick_device(args.device)
    _notify(args, f"Loading {model_id} on {device} (first run downloads the model)...")
    backend = load_backend(model_id, device)
    cache = load_cache(output_dir)
    if cache is not None and cache.model != model_id:
        _notify(args, f"Cached embeddings are for {cache.model}, so photos will be embedded again.")
        cache = None
    vectors, failures, cache_paths, cache_mtimes, cache_sizes, matrix = collect_embeddings(
        backend,
        photos,
        cache,
        args.batch_size,
        on_status=getattr(args, "on_status", None),
    )
    if len(matrix):
        if keep_existing:
            merge_cache(output_dir, model_id, cache_paths, cache_mtimes, cache_sizes, matrix)
        else:
            save_cache(output_dir, model_id, cache_paths, cache_mtimes, cache_sizes, matrix)

    text_embeds = embed_texts(backend, settings.prompts)
    failure_by_path = {path: message for path, message in failures}
    records: list[PhotoRecord] = []
    for path in photos:
        failure = failure_by_path.get(path, "")
        if failure:
            _notify(args, f"Skipped unreadable file: {path.name}")
            records.append(
                PhotoRecord(
                    source=path,
                    primary="Unreadable",
                    others=[],
                    scores={},
                    error=failure,
                )
            )
            continue
        key = str(path.resolve())
        image_row = vectors[key]
        probabilities = sigmoid_scores(image_row, text_embeds, backend.logit_scale, backend.logit_bias)[0]
        scores = {name: float(score) for name, score in zip(settings.names, probabilities, strict=True)}
        primary, others = assign_labels(scores, min_score, settings.review_label)
        records.append(PhotoRecord(source=path, primary=primary, others=others, scores=scores))

    if keep_existing:
        _notify(args, "Adding photos to the existing groups...")
    else:
        _notify(args, "Copying photos into group folders...")
    manifest = export_records(
        records,
        input_dir,
        output_dir,
        [*folder_names, "Unreadable"],
        keep_existing=keep_existing,
    )
    LAST_RUN.write_text(
        json.dumps({"output": str(output_dir), "min_score": min_score, "model": model_id}),
        encoding="utf-8",
    )
    _print_summary(records, output_dir, manifest, min_score, args)
    return 0


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _notify(args: argparse.Namespace, message: str) -> None:
    print(message)
    callback = getattr(args, "on_status", None)
    if callback is not None:
        callback(message)


def _print_summary(
    records: list[PhotoRecord],
    output_dir: Path,
    manifest: Path,
    min_score: float,
    args: argparse.Namespace,
) -> None:
    counts: Counter[str] = Counter()
    for record in records:
        counts[record.primary] += 1
        for label in record.others:
            counts[label] += 1
    _notify(args, f"Threshold: {min_score:.2f}")
    _notify(args, f"Manifest: {manifest}")
    for label, count in counts.most_common():
        _notify(args, f"  {label}: {count}")
    _notify(args, f"Grouped copies are in {output_dir}")
    _notify(args, "Originals were left in place.")


if __name__ == "__main__":
    raise SystemExit(main())
