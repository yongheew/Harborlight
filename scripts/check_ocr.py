"""Real OCR smoke test; run after installing Tesseract + English language data."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harborlight.readers import read_document, ocr_available
from harborlight.engine import compare

if not ocr_available():
    raise SystemExit("Tesseract is unavailable. Install it or set TESSERACT_CMD before this real OCR test.")
si = read_document((ROOT / "demo/attachments/HL-006_SI.txt").read_bytes(), "SI.txt")
bl = read_document((ROOT / "demo/attachments/HL-006_BL.pdf").read_bytes(), "scan.pdf")
assert not bl["error"], bl["error"]
assert bl["kind"] == "BL", bl["kind"]
assert any(p["method"].startswith("ocr:") for p in bl["pages"])
rows = compare(si, bl)
assert len(rows) == 7 and all(row["outcome"] == "match" for row in rows), rows
print("Real OCR passed: scanned BL read by Tesseract; all seven fields match the text SI.")
