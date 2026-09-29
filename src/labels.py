"""Load the category list and decide which groups a photo belongs to."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Category:
    name: str
    prompt: str


@dataclass(frozen=True)
class Settings:
    model: str
    min_score: float
    review_label: str
    categories: tuple[Category, ...]

    @property
    def prompts(self) -> list[str]:
        return [category.prompt for category in self.categories]

    @property
    def names(self) -> list[str]:
        return [category.name for category in self.categories]


def load_settings(path: Path) -> Settings:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a mapping of settings.")

    model = str(raw.get("model") or "").strip()
    if not model:
        raise ValueError(f"{path} is missing model.")

    try:
        min_score = float(raw.get("min_score", 0.10))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} has an invalid min_score.") from exc
    if not 0.0 <= min_score <= 1.0:
        raise ValueError(f"{path} min_score must be between 0 and 1.")

    review_label = str(raw.get("review_label") or "Needs review").strip()
    if not review_label:
        raise ValueError(f"{path} review_label is empty.")

    entries = raw.get("categories")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path} needs at least one category.")

    categories: list[Category] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{path} has a category that is not a mapping.")
        name = str(entry.get("name") or "").strip()
        prompt = str(entry.get("prompt") or "").strip()
        if not name or not prompt:
            raise ValueError(f"{path} has a category without a name and prompt.")
        if name.casefold() in seen:
            raise ValueError(f"{path} repeats the category {name!r}.")
        if name.casefold() == review_label.casefold():
            raise ValueError(f"{path} uses {review_label!r} both as a category and as the review folder.")
        seen.add(name.casefold())
        categories.append(Category(name=name, prompt=prompt))

    return Settings(
        model=model,
        min_score=min_score,
        review_label=review_label,
        categories=tuple(categories),
    )


def save_category_prompt(path: Path, name: str, prompt: str) -> None:
    """Replace one group's description and keep the comment header."""
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("The group description cannot be empty.")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("categories"), list):
        raise ValueError(f"{path} does not contain a category list.")

    matched = False
    for entry in raw["categories"]:
        if isinstance(entry, dict) and str(entry.get("name") or "").strip() == name:
            entry["prompt"] = prompt
            matched = True
            break
    if not matched:
        raise ValueError(f"No group named {name!r} in {path}.")

    lines = path.read_text(encoding="utf-8").splitlines()
    header: list[str] = []
    for line in lines:
        if line.startswith("#") or not line.strip():
            header.append(line)
            continue
        break
    while header and not header[-1].strip():
        header.pop()

    dumped = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, default_flow_style=False)
    text = ("\n".join(header) + "\n\n" + dumped) if header else dumped
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def assign_labels(
    scores: dict[str, float],
    min_score: float,
    review_label: str,
) -> tuple[str, list[str]]:
    """Return the primary group and any extra groups at or above min_score.

    The primary group is the highest score. Extra groups keep that same
    highest-first order, without repeating the primary. When every score is
    below min_score, the photo belongs only in the review folder.
    """
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    matched = [name for name, score in ranked if score >= min_score]
    if not matched:
        return review_label, []
    return matched[0], matched[1:]
