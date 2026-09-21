# Harborlight validation and handoff, 21 September 2026

This file distinguishes **checks reproduced on the delivered source**, **checks supported only by previously recorded Codex activity**, and **work requiring the team's environment or external services**. It describes the uploaded project snapshot with the participant-only export safeguard and validation document added at handoff.

## Reproduced in this handoff environment

- Environment: Linux, CPython 3.13.5, pytest 9.0.2; installed dependency versions may differ from the pinned production `requirements.txt`. The project supports CPython 3.11+ and CI config targets Python 3.12. No clean installation of every pinned dependency was independently performed here.
- `python -m pytest -q`: **110 passed, 38 subtests passed**. Includes a new regression ensuring the official export excludes demo records after participant imports, while the explicit `scope=all` route still exports the full workspace.
- `python scripts/check_ocr.py`: **passed with real Tesseract 5.5.0**. The fictional scanned `HL-006_BL.pdf` was read with OCR and all seven fields matched its text SI. This does not establish performance on unseen scans or prove that Tesseract is installed on Windows.
- `node --check web/app.js`: **passed** (Node 22.16.0). This checks JavaScript syntax only.
- Fresh temporary database and HTTP API smoke via FastAPI TestClient: homepage, health, 12 fictional seeded demo cases, valid audit chain, scan case `HL-006` marked `OK`, and all three export routes returned HTTP 200 with download headers. The isolated database was disposable; no user records were altered.
- Original uploaded database: **532 cases** and **547 audit events**, with `Store.audit()` reporting **valid**. Its case breakdown was 520 imported participant records and 12 synthetic demo fixtures. The independently uploaded evidence report and JSON export also contained the same 532 IDs and matching status fields.
- Submission safety: a separate **520-record participant-only JSON** was generated from the uploaded report using the application's official five-field export schema. It excludes all 12 demo IDs; every retained record matches the corresponding entry in the uploaded all-cases `submission.json`. Counts: 349 `OK`, 123 `NEEDS_REVIEW`, 48 `MISMATCH`. These counts are predictions, **not ground-truth accuracy statistics**. This participant-only JSON must be the one used if the organizer expects exactly the 520 participant email IDs.

## Earlier activity recorded in the supplied Codex transcript

- The transcript reports a separate organizer CLI run on the original 520-email dataset with **100% category accuracy and 45 of 46 labeled defect cases detected with exact field sets**. The original organizer input files, answer key, scoring code, and machine-readable scoreboard were not supplied in this handoff. **Those claims have not been independently reproduced here and must not be presented as newly verified measurements.** There is also a documented policy difference: Harborlight escalates missing-attachment comparison requests even when the benchmark labels them `OK`.
- The transcript records a previous successful browser check of correction preview, saved-review reload, retry, importing 520 messages and downloading three formats. In this separate handoff runtime, real Chromium opened but local navigation was blocked by the administrator (`ERR_BLOCKED_BY_ADMINISTRATOR`), so a fresh visual/browser interaction test could not be completed. TestClient exercises the corresponding HTTP functions and persistence.

## Not verified here, still requiring action

1. A fresh Windows install with all pinned dependencies, Tesseract and English language data; rerun `python -m pytest -q`, `python scripts/check_ocr.py`, then test the UI in a local browser.
2. Building and starting the Docker image, restarting its service and checking volume persistence. Docker was not available in this environment.
3. A live opt-in cloud model call: no API key or approved external credentials were supplied. Local trained ML and evidence comparison run without a key. Cloud functionality has mocked tests, not a live provider success record.
4. A hosted public demo, published repository, video, final submission form, team details and live links. Deployment instructions/configuration exist, but configuration is not evidence of a completed deployment.
5. Independent rerun of the organizer benchmark and evaluation of unseen, representative shipping documents. The original brief PDFs and organizer sample bundle used in the earlier Codex workspace are not present in this upload, although the earlier work's requirement mapping is included in `docs/SUBMISSION.md`.

## Recommended verification before submitting

From the project root on the target machine:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/check_ocr.py
.\.venv\Scripts\python.exe run.py
```

Open `http://127.0.0.1:8000` and test a clean case, a real mismatch, the OCR case, correction preview without saving, save/reload review, retry, source download, and the three exports. If `py -3.12` is unavailable, use a standard installed CPython 3.11+ interpreter. For an organizer submission, check that the JSON contains **exactly the IDs supplied by the organizer** and no `HL-...` demo IDs. The default Official JSON export now filters synthetic cases automatically when participant data exists; use `/api/export/submission?scope=imported` for an explicit filter.

## Data handling

The delivered **source ZIP intentionally excludes** the user's 532-case SQLite database, generated export files, temporary logs, Python bytecode, environment secrets, and organizer answer keys. The original uploaded ZIP and reports remain separate from this clean source package. A public source repository should contain code, tests, docs and clearly labeled synthetic fixtures only. Do not publish operational reports or third-party sample inboxes without permission.
