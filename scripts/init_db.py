"""Create or migrate the production DuckDB file. Usage (from repo root):

    python scripts/init_db.py
    python scripts/init_db.py /tmp/spends.duckdb
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import DEFAULT_PROD_PATH, initialize_database


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else None
    path = initialize_database(target)
    print(f"DuckDB ready: {path}")
    if target is None:
        print(f"Default production path: {DEFAULT_PROD_PATH}")


if __name__ == "__main__":
    main()
