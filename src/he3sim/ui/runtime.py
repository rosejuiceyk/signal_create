"""Runtime paths shared by source and frozen UI builds."""

from __future__ import annotations

import sys
from pathlib import Path


def application_root() -> Path:
    """Return the writable directory containing the portable executable."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def resource_path(relative_path: str | Path) -> Path:
    """Resolve a packaged read-only resource or a source-tree file."""

    bundle_root = getattr(sys, "_MEIPASS", None)
    root = Path(bundle_root) if bundle_root else Path(__file__).resolve().parents[3]
    relative = Path(relative_path)
    candidate = root / relative
    if bundle_root or candidate.exists():
        return candidate
    return root / "src" / relative
