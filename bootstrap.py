"""Restore the approved 520-case baseline on each fresh ephemeral Render instance."""
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("HARBORLIGHT_DATA_DIR", str(ROOT / "var")))
TARGET = DATA_DIR / "harborlight.sqlite3"
SEED = ROOT / "seed" / "harborlight.sqlite3"

def initialize_database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not TARGET.exists():
        if not SEED.is_file():
            raise RuntimeError("Missing approved 520-case baseline: seed/harborlight.sqlite3")
        shutil.copy2(SEED, TARGET)
        print("Restored 520-case baseline from packaged snapshot", flush=True)

if __name__ == "__main__":
    initialize_database()
    os.execv(sys.executable, [sys.executable, str(ROOT / "run.py")])
