"""Find the processors this PC can sort with, and remember the user's choice.

Run as `python -m src.devices` to print the detected devices as JSON. The window
does this in a separate process so it never has to load torch itself.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_FILE = ROOT / ".settings.json"
AUTO = "auto"
CPU = "cpu"


def detect() -> dict:
    """Return {"devices": [{"id", "name", "memory_gb"}], "other_gpus": [...], "note": str}."""
    devices: list[dict] = []
    note = ""
    try:
        import torch

        if torch.cuda.is_available():
            for index in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(index)
                devices.append(
                    {
                        "id": f"cuda:{index}",
                        "name": props.name,
                        "memory_gb": round(props.total_memory / 1024**3, 1),
                    }
                )
        elif getattr(torch.version, "cuda", None) is None:
            note = "The installed PyTorch is the CPU-only build, so no GPU can be used."
        else:
            note = "PyTorch was built with GPU support, but no compatible NVIDIA GPU or driver was found."
    except Exception as exc:  # noqa: BLE001 - detection must never crash the window
        note = f"Could not check for GPUs: {type(exc).__name__}"
    return {"devices": devices, "other_gpus": _system_gpus(devices), "note": note}


def _system_gpus(usable: list[dict]) -> list[str]:
    """Names of GPUs Windows reports that PyTorch cannot use (AMD, Intel, or no driver)."""
    if sys.platform != "win32":
        return []
    try:
        result = subprocess.run(  # noqa: S603, S607 - fixed command
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return []
    usable_names = {item["name"].casefold() for item in usable}
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [name for name in names if name.casefold() not in usable_names]


def load_choice() -> str:
    """Saved device: "auto", "cpu", or "cuda:N"."""
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return AUTO
    value = str(data.get("device", AUTO)) if isinstance(data, dict) else AUTO
    return value if is_valid(value) else AUTO


def save_choice(choice: str) -> None:
    if not is_valid(choice):
        raise ValueError(f"Unknown device: {choice}")
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data["device"] = choice
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def is_valid(value: str) -> bool:
    if value in (AUTO, CPU, "cuda"):
        return True
    prefix, _, index = value.partition(":")
    return prefix == "cuda" and index.isdigit()


if __name__ == "__main__":
    print(json.dumps(detect()))
