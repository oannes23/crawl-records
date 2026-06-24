"""Export the published client contract to openapi.json.

Admin routes already set ``include_in_schema=False``, so the app's generated schema
contains only the §4 public surface — this dumps it verbatim as the committed artifact
the game client codegens against. Run via ``make openapi``.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

OUT = Path(__file__).resolve().parent.parent / "openapi.json"


def main() -> None:
    schema = app.openapi()
    # sanity: the contract must not leak admin paths
    leaked = [p for p in schema.get("paths", {}) if p.startswith("/admin")]
    if leaked:
        raise SystemExit(f"admin paths leaked into contract: {leaked}")
    OUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT} ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()
