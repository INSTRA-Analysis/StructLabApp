"""Regenerate golden.json — run ONLY when a number is meant to change.

    python tests/golden/generate.py

Review the diff of golden.json; a commit that changes it should say why.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.golden.fingerprint import fingerprint   # noqa: E402
from tests.golden.models import MODELS             # noqa: E402

if __name__ == "__main__":
    golden = {name: fingerprint(build()) for name, build in MODELS.items()}
    out = Path(__file__).with_name("golden.json")
    out.write_text(json.dumps(golden, indent=1), encoding="utf-8")
    print(f"wrote {out} ({len(golden)} models)")
