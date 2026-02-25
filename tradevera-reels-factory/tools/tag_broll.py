#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.broll_select import tag_broll_directory


def main() -> int:
    broll_dir = ROOT / "assets" / "broll"
    manifest = tag_broll_directory(broll_dir)
    print(f"Tagged {len(manifest)} b-roll file(s): {broll_dir / 'tags.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
