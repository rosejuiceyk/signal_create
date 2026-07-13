"""Export the Pydantic configuration schema as a deterministic JSON document."""

from __future__ import annotations

import json
from pathlib import Path

from he3sim.config import He3SimConfig


def main() -> None:
    """Write the current schema below ``configs/schemas``."""
    project_root = Path(__file__).resolve().parents[1]
    output_path = project_root / "configs" / "schemas" / "he3sim.schema.json"
    rendered = json.dumps(He3SimConfig.model_json_schema(), ensure_ascii=False, indent=2)
    output_path.write_text(f"{rendered}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
