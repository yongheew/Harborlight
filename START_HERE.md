# Start here: Harborlight handoff

The source ZIP is your **runnable web application**. It contains the Python service, frontend, synthetic sample cases, tests, setup instructions, demo script and validation report. The separate **harborlight_participant_submission.json** file contains predictions for the 520 imported participant emails only. The original `submission.json` uploaded with this chat had 532 entries and included 12 fictional demo cases; avoid accidentally submitting those extra IDs.

## What the files you uploaded do

- `harborlight.zip`: the source code and local SQLite workspace Codex built. Keep your original copy as a backup. This final source package omits the live SQLite database and other runtime/user data intentionally.
- `harborlight-report.json`: a full evidence export with classifications, extracted documents, audit, and both demo and participant cases. Large; intended for inspection rather than the organizer's prediction submission.
- `discrepancies.csv`: human-readable spreadsheet-style comparison export. Not the organizer's official prediction JSON.
- `submission.json`: original all-workspace prediction export containing 532 IDs, including 12 demo IDs. Use the **separate 520-record participant-only submission file** instead if the organizer wants the 520 supplied participant cases.
- `Pasted markdown(1).md`: the earlier Codex conversation transcript, helpful for understanding past progress and what remains unverified.

## Run on Windows

Extract the source ZIP, open a PowerShell terminal inside its `harborlight` folder, and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

If you use **Git Bash in VS Code with Python 3.13**, use these commands from the folder with `run.py` instead:

```bash
py -3.13 -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
python run.py
```

For later restarts in the same folder, only run `source .venv/Scripts/activate` and `python run.py`. Keep `var/` untouched to retain your imported 520 emails plus the 12 built-in demo cases. This source ZIP intentionally excludes `var/`, so a new extraction starts with 12 cases and needs its own one-time import. Do not upload a participant-filled `var/` to a public repository or deployment without organizer permission.

Open `http://127.0.0.1:8000` in Chrome or Edge. On first launch, 12 clearly labeled fictional demonstration cases appear automatically. If you want to keep the 532-case workspace currently shown in Codex, leave its original `var/harborlight.sqlite3` untouched and use the updated code in that original project folder after backing it up. Extracting the clean source ZIP into a **new** directory starts a new database.

For OCR of scanned shipping documents, install Tesseract with English language data on Windows, ensure it is on PATH or set `TESSERACT_CMD`, restart the app and run `python scripts/check_ocr.py`. Alternatively build with Docker using `docker compose up --build`, which installs OCR in the container.

## What is complete and what still needs you

- Tests and local API: passing in the handoff environment. Real OCR on the fictional scanned case also passed. See `docs/VALIDATION.md` for commands and precise limitations.
- The new official JSON endpoint automatically excludes the synthetic demo cases when imported cases are in the workspace. Explicit filters: `/api/export/submission?scope=imported` and `?scope=all`.
- Public deployment, GitHub publishing, demo-video recording, team information, and any official submission form still require your access and participation. The optional cloud model path was tested with mocks; a live API call was not verified and should not be claimed as completed.

For the judge demo, follow `docs/DEMO_SCRIPT.md` and `docs/SUBMISSION.md`. Do not upload the user-data database or any API credentials to a public repository.
