import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
for sub in ("src", "scripts"):
    path = str(ROOT / sub)
    if path not in sys.path:
        sys.path.insert(0, path)
