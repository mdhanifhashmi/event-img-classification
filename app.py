"""Browse grouped event photos in a local browser page."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.export import MANIFEST_NAME, read_manifest
from src.labels import load_settings
from src.scan import register_heif

LAST_RUN = ROOT / ".last_run.json"
CONFIG = ROOT / "config" / "categories.yaml"
PAGE_SIZE = 24
COLUMNS = 4


def main() -> None:
    st.set_page_config(page_title="Event photos", layout="wide")
    try:
        register_heif()
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()

    st.title("Event photos")
    st.caption("Photos are grouped on this PC. The original folder is not changed.")

    default_output = _default_output()
    output_text = st.sidebar.text_input("Sorted folder", value=default_output)
    if not output_text.strip():
        st.info("Run the sorter, then paste the output folder here.")
        st.code('python -m src.cli --input D:\\Events\\all --output D:\\Events\\sorted', language="powershell")
        st.stop()

    output_dir = Path(output_text).expanduser().resolve()
    manifest_path = output_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        st.error(f"No {MANIFEST_NAME} in {output_dir}. Sort a folder first.")
        st.code(
            f'python -m src.cli --input D:\\Events\\all --output "{output_dir}"',
            language="powershell",
        )
        st.stop()

    rows = read_manifest(manifest_path)
    visible = [row for row in rows if not (row.get("error") or "").strip()]
    labels = _label_order(visible)
    counts = _counts(visible)

    failed = [row for row in rows if (row.get("error") or "").strip()]
    if failed:
        st.sidebar.caption(
            f"{len(failed)} unreadable file{'s' if len(failed) != 1 else ''} left out of the groups."
        )

    choice = st.sidebar.radio(
        "Group",
        options=["All", *labels],
        format_func=lambda label: "All photos" if label == "All" else f"{label} ({counts.get(label, 0)})",
    )

    with st.sidebar.form("search"):
        query = st.text_input("Search", placeholder="stage, flowers, mandap")
        search_submitted = st.form_submit_button("Search")

    if search_submitted:
        text = query.strip()
        if not text:
            st.session_state.pop("search", None)
        else:
            try:
                with st.spinner("Scoring this search with the local model..."):
                    st.session_state["search"] = {
                        "query": text,
                        "hits": _search(output_dir, text),
                    }
            except Exception as exc:
                st.session_state.pop("search", None)
                st.error(str(exc))

    search = st.session_state.get("search")
    if search and st.sidebar.button("Clear search"):
        st.session_state.pop("search", None)
        search = None
        st.rerun()

    if search:
        floor = st.slider(
            "Minimum score",
            min_value=0.0,
            max_value=1.0,
            value=_default_floor(output_dir),
            step=0.01,
            key=f"floor-{output_dir}",
        )
        hits = [(path, score) for path, score in search["hits"] if score >= floor]
        by_source = {str(Path(row["source_path"]).resolve()): row for row in rows}
        if choice != "All":
            hits = [item for item in hits if _in_group(by_source, item[0], choice)]
        st.subheader(f"Search: {search['query']}")
        st.caption(f"{len(hits)} photo{'s' if len(hits) != 1 else ''} at or above {floor:.0%}.")
        cards = [_search_card(output_dir, by_source, path, score) for path, score in hits]
        _show_cards(cards, f"search-{search['query']}-{choice}")
        return

    selected = visible if choice == "All" else [row for row in visible if choice in _row_labels(row)]
    title = "All photos" if choice == "All" else choice
    st.subheader(title)
    st.caption(f"{len(selected)} photo{'s' if len(selected) != 1 else ''}.")
    cards = [_group_card(output_dir, row, None if choice == "All" else choice) for row in selected]
    _show_cards(cards, f"group-{choice}")


def _show_cards(cards: list[dict[str, str]], page_key: str) -> None:
    if not cards:
        st.info("Nothing to show in this group.")
        return
    pages = max(1, (len(cards) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = 1
    if pages > 1:
        page = int(
            st.number_input(
                "Page",
                min_value=1,
                max_value=pages,
                value=1,
                step=1,
                key=f"page-{page_key}-{len(cards)}",
            )
        )
    start = (page - 1) * PAGE_SIZE
    chunk = cards[start : start + PAGE_SIZE]
    for offset in range(0, len(chunk), COLUMNS):
        columns = st.columns(COLUMNS)
        for column, card in zip(columns, chunk[offset : offset + COLUMNS], strict=False):
            with column:
                path = Path(card["path"])
                if path.is_file():
                    st.image(str(path), width="stretch")
                else:
                    st.warning("File missing")
                st.caption(card["caption"])
                if path.is_file() and st.button("Open", key=card["key"]):
                    _open_path(path)


def _group_card(output_dir: Path, row: dict[str, str], group: str | None) -> dict[str, str]:
    scores = _scores(row)
    label = group or row.get("primary_label") or "Photo"
    score = scores.get(label)
    score_text = "" if score is None else f" · {score:.0%}"
    others = [name for name in _row_labels(row) if name != label]
    extra = f" · also {', '.join(others)}" if others else ""
    path = _photo_file(output_dir, row)
    return {
        "path": str(path),
        "caption": f"{path.name}{score_text}{extra}",
        "key": f"open-{row.get('source_path', path)}-{label}",
    }


def _in_group(by_source: dict[str, dict[str, str]], source: str, group: str) -> bool:
    row = by_source.get(str(Path(source).resolve()))
    return row is not None and group in _row_labels(row)


def _search_card(
    output_dir: Path,
    by_source: dict[str, dict[str, str]],
    source: str,
    score: float,
) -> dict[str, str]:
    row = by_source.get(str(Path(source).resolve()))
    if row is None:
        path = Path(source)
        caption = f"{path.name} · {score:.0%}"
        key = f"search-{source}"
    else:
        path = _photo_file(output_dir, row)
        primary = row.get("primary_label") or "Photo"
        caption = f"{path.name} · {score:.0%} · {primary}"
        key = f"search-{row.get('source_path', source)}"
    return {"path": str(path), "caption": caption, "key": key}


def _search(output_dir: Path, query: str) -> list[tuple[str, float]]:
    from src.classify import embed_texts, load_backend, pick_device
    from src.scores import sigmoid_scores

    cache = load_cache(output_dir)
    if cache is None or len(cache.embeddings) == 0:
        raise RuntimeError("This folder has no embedding cache. Sort the photos again so search can score them.")
    device = pick_device("auto")
    backend = _load_backend(cache.model, str(device))
    text_embeds = embed_texts(backend, [query])
    scores = sigmoid_scores(cache.embeddings, text_embeds, backend.logit_scale, backend.logit_bias).reshape(-1)
    ranked = sorted(zip(cache.paths, scores.tolist(), strict=True), key=lambda item: item[1], reverse=True)
    return [(path, float(score)) for path, score in ranked]


@st.cache_resource(show_spinner="Loading the vision model...")
def _load_backend(model_id: str, device_name: str):
    import torch
    from src.classify import load_backend

    return load_backend(model_id, torch.device(device_name))


def _photo_file(output_dir: Path, row: dict[str, str]) -> Path:
    for destination in (row.get("destinations") or "").split("|"):
        if not destination:
            continue
        candidate = output_dir / destination
        if candidate.is_file():
            return candidate
    return Path(row.get("source_path") or "")


def _row_labels(row: dict[str, str]) -> list[str]:
    labels = []
    primary = (row.get("primary_label") or "").strip()
    if primary and primary != "Unreadable":
        labels.append(primary)
    for extra in (row.get("other_labels") or "").split("|"):
        extra = extra.strip()
        if extra and extra not in labels:
            labels.append(extra)
    return labels


def _scores(row: dict[str, str]) -> dict[str, float]:
    raw = row.get("scores_json") or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    scores: dict[str, float] = {}
    for name, value in parsed.items():
        try:
            scores[str(name)] = float(value)
        except (TypeError, ValueError):
            continue
    return scores


def _counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for label in _row_labels(row):
            counts[label] = counts.get(label, 0) + 1
    return counts


def _label_order(rows: list[dict[str, str]]) -> list[str]:
    present = set(_counts(rows))
    preferred: list[str] = []
    if CONFIG.is_file():
        settings = load_settings(CONFIG)
        preferred = [*settings.names, settings.review_label]
    ordered = [label for label in preferred if label in present]
    ordered.extend(sorted(present - set(ordered)))
    return ordered


def _default_output() -> str:
    if not LAST_RUN.is_file():
        return ""
    try:
        payload = json.loads(LAST_RUN.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return str(payload.get("output") or "")


def _default_floor(output_dir: Path) -> float:
    if not LAST_RUN.is_file():
        return 0.1
    try:
        payload = json.loads(LAST_RUN.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0.1
    recorded = payload.get("output")
    if not recorded:
        return 0.1
    try:
        same_folder = Path(recorded).expanduser().resolve() == output_dir
    except OSError:
        same_folder = False
    if not same_folder:
        return 0.1
    try:
        value = float(payload.get("min_score", 0.1))
    except (TypeError, ValueError):
        return 0.1
    return min(1.0, max(0.0, value))


def _open_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - the user asked to open this local photo
        return
    command = ["open", str(path)] if sys.platform == "darwin" else ["xdg-open", str(path)]
    subprocess.run(command, check=False)


main()
