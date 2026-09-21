# Harborlight

**Shipping verification with evidence, explainable priority and a complete human review loop.**

Harborlight classifies a mixed operations inbox, compares a Shipping Instruction (SI) with a draft Bill of Lading (BL), and identifies exactly which of seven fields differ. Unreadable documents, missing information and uncertain email intent go to a human. Operators can inspect source evidence, preview a correction, save a versioned decision, retry original sources, and export results.

**Status:** working local application with tested imports, verification, review persistence, retries and exports. Docker/cloud configuration is included. A public deployment and live cloud API calls have not been verified. See [validation](docs/VALIDATION.md) for measured results and [submission checklist](docs/SUBMISSION.md) for the remaining external deliverables.

## Start locally

Use standard **CPython 3.11 or newer** (3.12 was tested in the handoff environment; 3.13 has also been run locally by the project owner). Run commands from the directory containing `run.py` and `requirements.txt`.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Open **http://127.0.0.1:8000**. The first start loads 12 explicitly labeled, fictional demo cases. Press Ctrl+C in the server terminal to stop. The optional `start.ps1` performs these steps. If the machine's `python` is an MSYS/MinGW build, use a standard Windows Python installation, for example `py -3.12 -m venv .venv`.

### Windows Git Bash (VS Code)

With Python 3.13 installed, create a project-specific environment once, activate it, install dependencies, and run:

```bash
py -3.13 -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
python run.py
```

On subsequent launches of the **same project folder**, you only need `source .venv/Scripts/activate` and `python run.py`. Confirm the selected environment with `python -c "import sys; print(sys.executable)"`; its path should end in `.venv\Scripts\python.exe`. Python 3.12 may be used instead with `py -3.12` if your dependencies or machine require it. If port 8000 is occupied, stop the older server before starting another. Keep the terminal open while using the app, then press Ctrl+C to stop.

**Imported case persistence:** Imported emails and original sources are retained under `var/` in this project. After importing the participant ZIP, the current 532-case workspace persists across server restarts as long as you keep the same `var/` directory. A fresh extraction of the source ZIP deliberately starts with 12 synthetic demo cases because this archive does not bundle your imported database or confidential participant records. Import is a one-time operation for each new workspace. Do not commit `.venv/`, `var/`, credentials or participant inbox records to a public GitHub repository. Public deployments require a separately configured persistent volume, and the 520 participant cases must not be published without permission.

### macOS / Linux

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

Alternatively run `sh start.sh`. No frontend build, Node.js, API key or network connection is required after dependencies are installed.

### Docker, including OCR

```sh
docker compose up --build
```

Open the same local URL. The image installs English Tesseract OCR. A named volume preserves SQLite cases, original source bytes and audit records. The Compose port is bound to loopback. Docker is not available in the build/test machine, so the image itself has not been executed here.

## What is implemented

- Five email categories: BL comparison, SI request, invoice query, general correspondence and spam.
- A reproducible local Naive Bayes classifier trained on 75 independently authored examples, plus transparent intent rules; quoted history and misleading subjects are handled separately.
- TXT, digital PDF, DOCX tables/paragraphs, XLSX cells, image files and scanned-PDF OCR handling. Content determines SI/BL identity; an invoice named `BL.pdf` is not accepted as a BL.
- Seven SI-reference fields: shipper, consignee, notify party, loading port, discharge port, container count and gross weight in kg.
- Case/spacing/legal-suffix normalization, explicit unit conversion, decimal arithmetic and container-equipment quantities. Missing or conflicting values remain uncertain.
- Source excerpts, original values, normalized values, document locations, extraction method and SHA-256 hashes.
- An exception queue with explained priority points; these are policy weights, not failure probabilities.
- An unsaved **Preview impact** calculation, followed by attributed category/field review with notes, optimistic concurrency and preserved previous evidence.
- Retry from original attachments, with earlier reviews retained in the audit trail. A retry resets current extraction corrections and human-review status.
- SQLite persistence, atomic case/audit writes, a locally verifiable hash chain, source downloads, and three export formats.
- Optional OpenAI structured classification and fallback extraction. Cloud suggestions require literal source quotes; uncertainty cannot be resolved merely by quoting unreliable OCR text.
- Bounded ZIP/file ingestion, path-traversal rejection, visible import failures, safe HTML text rendering, optional HTTP Basic authentication, same-origin writes, CSV formula escaping and dependency/test workflows.

## Import your inbox

Click **Import documents**, choose a ZIP containing `inbox/*.json` and its referenced attachments, then **Verify documents**. You can also select multiple email JSON files and attachments together. ZIP folder prefixes are supported. Ambiguous duplicate attachment names are not chosen arbitrarily.

```text
participant-data/
  inbox/
    shipment-001.json
  attachments/
    shipment-001_SI.pdf
    shipment-001_BL.docx
```

```json
{
  "email_id": "shipment-001",
  "from": "operations@example.test",
  "subject": "Please verify the draft BL",
  "body": "Compare the attached draft BL against our shipping instruction.",
  "attachments": [
    "attachments/shipment-001_SI.pdf",
    "attachments/shipment-001_BL.docx"
  ]
}
```

Limits: 40 MB HTTP upload body, 16 MB per attachment, 120 MB expanded ZIP batch, 2,500 archive members and 20 attachments per email. Readers additionally limit PDF pages, text, image dimensions and worksheet cells. Legacy binary `.doc`/`.xls` are not supported; use `.docx`/`.xlsx`.

Re-importing an existing `email_id` replaces the current analysis and attachments, with an audit event and prior review history. Importing or choosing **Explore demo** is not a preview. Use unique IDs for unrelated shipments. Demo fixtures are fictional and labeled **Synthetic demo data**; imported records are labeled **Imported data**.

Only participant inbox records and supported attachments are consumed. Organizer answer keys, generators and sample-output files are excluded. The application never uses an answer key to make predictions.

## Review and resolve a case

1. Search or filter the queue; open the relevant case.
2. Open a source citation or **Source files** to inspect the original evidence. SI is always the reference.
3. Open **Review desk**. Confirm or correct the email category and add your name and a note.
4. If an extraction is wrong, choose **Correct extracted values**, change only the relevant fields and click **Preview impact**. Nothing is saved by a preview.
5. Click **Record review**. The result, previous evidence and review attribution are persisted. A stale version returns a conflict rather than overwriting another reviewer.
6. For missing/wrong/unreadable documents, supply corrected source files with the same email ID through import. For a temporary reader/OCR/cloud failure, use **Re-analyze**.

Confirming incomplete evidence does not mark the case clean. Changing an email category reruns the appropriate comparison against preserved documents. A genuine BL discrepancy should remain recorded until the source amendment is handled; an extraction edit is not a shipment approval or an instruction to change the source document.

## Export and evaluate

- **Official JSON:** one record per email ID, with `category`, `status`, `review_reason`, `has_defect` and `defect_fields`.
- **Full evidence report:** documents, comparison rows, reviews, provenance and audit history.
- **Discrepancy CSV:** one row per field (or classification-only record), for spreadsheet inspection.

The default **Official JSON** export automatically excludes built-in fictional demo cases whenever imported participant records exist. With only the demo loaded, it exports the demo for testing. Use `/api/export/submission?scope=imported` to export imported records explicitly or `?scope=all` to export the entire workspace. **The full evidence report and CSV still include all workspace cases**; do not submit these as the organizer's official prediction JSON.

```sh
python -m harborlight /path/to/participant-data --out results
python -m harborlight http://localhost:8080 --out results --evaluate http://localhost:8080
```

The CLI writes `submission.json`, `reports.json` and `metrics.json`. `--evaluate` posts only the prediction JSON to the organizer's `/submit` endpoint and saves its aggregate scoreboard. `--ai` explicitly opts in to cloud processing.

The richer internal reason `uncertain_intent` is retained in the full report; official v2 JSON exports `review_reason: null` with `status: NEEDS_REVIEW` because its reason vocabulary does not include uncertain intent. Missing-attachment comparison requests always require review, even where the supplied benchmark convention labels them `OK`.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `HOST` | `127.0.0.1` | Native server bind address; Docker uses `0.0.0.0` |
| `PORT` | `8000` | Server port |
| `HARBORLIGHT_DATA_DIR` | project `var/` | Persistent SQLite and source storage directory |
| `HARBORLIGHT_SEED_DEMO` | `1` | Set `0` for an empty new workspace |
| `HARBORLIGHT_PASSWORD` | unset | Enables HTTP Basic access control when set |
| `HARBORLIGHT_USERNAME` | `judge` | Username used with the password |
| `OPENAI_API_KEY` | unset | Enables cloud opt-in; server-side secret |
| `OPENAI_MODEL` | `gpt-4o-mini` | Configurable structured-output model |
| `TESSERACT_CMD` | `tesseract` on PATH | Optional absolute local executable path |
| `OCR_LANG` | `eng` | Installed Tesseract language data to use |

`docker compose` reads `.env`; native `run.py` reads actual environment variables and does **not** automatically load `.env`. Example for native PowerShell: `$env:PORT = '8001'`. Set API credentials in the environment, not in code, screenshots or Git. Cloud processing requires both a server key and a checked UI opt-in/CLI `--ai`; local mode does not send documents externally. API requests incur provider charges.

To use OCR without Docker, install Tesseract and its English language data, add it to PATH (or set `TESSERACT_CMD`), restart the server and retry the scanned case. `GET /api/health` reports executable availability. Availability is not an OCR accuracy guarantee. See the [model card](docs/MODEL_CARD.md) for confidence and evidence policies.

## Tests

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

JavaScript syntax can additionally be checked with `node --check web/app.js`. The test suite includes reader, classifier, normalization, API, review, audit, import-safety and mocked cloud scenarios. `scripts/build_demo.py` regenerates the original fictional fixtures and needs the development dependencies.

See [docs/VALIDATION.md](docs/VALIDATION.md) for the exact tested environment, 520-email benchmark, browser checks and untested paths. Test data is independently authored; organizer labels are accessed only by the supplied separate scoring program.

## Architecture and project structure

```text
Browser / CLI -> bounded inbox ingestion -> local ML (optional cloud)
             -> document readers / OCR -> evidence-linked field comparison
             -> review or verified result -> SQLite + audit -> exports
```

| Path | Responsibility |
|---|---|
| `harborlight/app.py` | FastAPI endpoints, authentication and uploads |
| `harborlight/ingest.py` | Safe ZIP, file and inbox records |
| `harborlight/classifier.py` | Trained local model and intent routing |
| `harborlight/readers.py` | Format-specific extraction and OCR |
| `harborlight/engine.py` | Normalization, comparison and uncertainty |
| `harborlight/cloud.py` | Optional structured cloud boundary |
| `harborlight/service.py` | Shared orchestration, preview and export logic |
| `harborlight/store.py` | Persistence, version checks and audit verification |
| `web/` | Same-origin responsive interface; no build step |
| `demo/` | Clearly fictional demo inbox and documents |
| `tests/` | Unit, workflow, API and cloud-boundary tests |
| `docs/` | Validation, model card, submission mapping and demo script |
| `Dockerfile`, `compose.yaml`, `render.yaml` | Local/container/cloud deployment configuration |

FastAPI interactive endpoint documentation is available at `/docs`. The [five-minute demo script](docs/DEMO_SCRIPT.md) provides the exact judging flow.

## Cloud deployment and submission

`render.yaml` defines a single Docker service with a persistent disk and generated access password. It uses a paid plan: review current provider pricing before deployment. See [cloud deployment instructions](docs/DEPLOYMENT.md). No cloud service or public repository is created by running the local application.

The brief also requires a public prototype, repository link, documentation/deck link and a video of at most five minutes. Code and documentation are packaged here; publishing them and supplying team details are separate external steps. Do not claim cloud integration was demonstrated until the actual deployment/provider run is tested. Read [SUBMISSION.md](docs/SUBMISSION.md).

## Challenges faced

* **Mixed document formats and unreliable scans:** Shipping documents can arrive as text files, digital PDFs, Word documents, Excel sheets, image files, or scanned PDFs. Harborlight uses format-specific readers and routes missing, unreadable, conflicting, or low-confidence values to human review rather than guessing a comparison result.
* **Separating real email intent from misleading context:** Email subjects, quoted history, signatures, and forwarded messages can conflict with the latest request. The solution combines a local Naive Bayes classifier with transparent intent rules so that the current message is prioritised.
* **Maintaining evidence and a safe review process:** A discrepancy must be traceable to the original SI and draft BL. The system retains source excerpts, original and normalised values, extraction methods, document hashes, and a versioned audit trail for human corrections and retries.
* **Deployment and persistence constraints:** The prototype uses SQLite for a simple, portable workflow. Public free-tier hosting can restart or clear temporary storage, so production use would require persistent storage and a shared database.

## Future roadmap

* Move persistence from SQLite to a managed database and store original attachments in object storage so cases, reviews, and audit history survive redeployments and support multiple users.
* Add role-based access, reviewer assignment, notification workflows, and integration with a monitored email inbox.
* Expand the evaluation set with more real-world layouts, languages, handwritten scans, and multi-shipment documents; use the results to improve extraction and classification coverage.
* Add a shipping-port reference dataset, stronger document-pairing logic, and more configurable business rules for different operators and carriers.
* Provide operational analytics, such as recurring discrepancy trends, reviewer turnaround time, and document-quality metrics.

## Limits and next validation

This is a single-instance hackathon prototype, not an authenticated multi-tenant shipping platform. The optional shared password does not prove reviewer identity. SQLite and source blobs need a persistent volume; multiple replicas need a shared database/object store and a worker queue. Reader byte/page/cell limits do not replace a separate sandbox for hostile documents. The local hash chain detects partial changes but is not externally anchored or administrator-proof.

The small English classifier, alias rules and document layouts need representative held-out evaluation. Source quotes and high OCR scores do not guarantee semantic correctness. DOCX evidence uses logical document order; XLSX evidence identifies sheets, not physical printed pages. Scans need installed language data; low confidence routes to review. Handwriting, multilingual OCR, complex arbitrary layouts, multiple-shipment pairing and legacy Office formats are not comprehensively supported. Matching seven fields does not authenticate documents or validate every shipment detail. No competition result is guaranteed.
