"""``python -m src.publish --record <path> [--record <path> ...] --out site/``.

See ``src/publish/README.md`` and ``src/publish/gate.py``.
"""

from __future__ import annotations

from .gate import main

if __name__ == "__main__":
    raise SystemExit(main())
