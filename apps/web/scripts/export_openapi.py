"""Write the API's OpenAPI schema to ``src/lib/generated/openapi.json``.

The frontend's TypeScript types are generated from that file, so it is step one of
regenerating them after any change to an API schema or route:

    python apps/web/scripts/export_openapi.py        # 1. the schema (needs no server, no DB)
    cd apps/web && npm run generate:api              # 2. the TypeScript types

or both at once with ``make api-types``. The file is exactly what ``/openapi.json``
serves: both are built by ``groundtruth.platform.api.openapi_schema``.
"""

from __future__ import annotations

from pathlib import Path

from groundtruth.platform.api.app import app
from groundtruth.platform.api.openapi_schema import write_snapshot

SNAPSHOT = Path(__file__).resolve().parents[1] / "src" / "lib" / "generated" / "openapi.json"

if __name__ == "__main__":
    write_snapshot(app, SNAPSHOT)
    print(f"wrote {SNAPSHOT}")
