"""Single-origin FastAPI application. Run with `python run.py`."""
import base64
import csv
import hmac
import io
import json
import os
import shutil
import threading
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from . import __version__, cloud
from .engine import CATEGORIES
from .ingest import folder_records, records_from_files
from .service import official, process, simulate, statistics
from .store import Conflict, Store, now

ROOT = Path(__file__).resolve().parent.parent


class RetryBody(BaseModel):
    use_ai: bool = False


class SimulationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    corrections: dict = Field(default_factory=dict)
    category: str | None = None


class ReviewBody(SimulationBody):
    version: int = Field(ge=1)
    reviewer: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=1, max_length=3000)
    decision: str = "confirm"


def create_app(db_path=None):
    store = Store(db_path or Path(os.getenv("HARBORLIGHT_DATA_DIR", str(ROOT / "var"))) / "harborlight.sqlite3")
    processing_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        if os.getenv("HARBORLIGHT_SEED_DEMO", "1") == "1" and not store.list():
            for email, files in folder_records(ROOT / "demo"):
                store.save(dict(process(email, files), data_origin="synthetic_demo"), "demo_loaded", files=files)
        yield

    app = FastAPI(title="Harborlight", version=__version__, lifespan=lifespan,
                  description="Evidence-first shipping document verification. SI is the reference.")
    app.state.store = store

    @app.middleware("http")
    async def security(request, call_next):
        password = os.getenv("HARBORLIGHT_PASSWORD")
        if password and request.url.path != "/api/health":
            supplied = request.headers.get("authorization", "")
            wanted = base64.b64encode((os.getenv("HARBORLIGHT_USERNAME", "judge") + ":" + password).encode()).decode()
            if not hmac.compare_digest(supplied, "Basic " + wanted):
                return Response("Authentication required", 401, headers={"WWW-Authenticate": 'Basic realm="Harborlight", charset="UTF-8"'})
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin writes are not allowed"}, 403)
            length = request.headers.get("content-length")
            if length:
                try:
                    if int(length) > 40 * 1024 * 1024:
                        return JSONResponse({"detail": "Request exceeds the 40 MB upload limit"}, 413)
                except ValueError:
                    return JSONResponse({"detail": "Invalid Content-Length"}, 400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if not request.url.path.startswith(("/docs", "/redoc")):
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, 409)

    def get_case(case_id):
        try:
            return store.get(case_id)
        except KeyError:
            raise HTTPException(404, "Case not found") from None

    def import_batch(records, use_ai=False, action="imported"):
        if not processing_lock.acquire(blocking=False):
            raise HTTPException(409, "Another import is running. Please retry when it completes.")
        results, errors = [], []
        try:
            for email, files in records:
                try:
                    try:
                        current_version = store.get(email["email_id"])["version"]
                    except KeyError:
                        current_version = 0
                    report = process(email, files, use_ai)
                    report["data_origin"] = "synthetic_demo" if action == "demo_loaded" else "user_import"
                    results.append(store.save(report, action, files=files, expected_version=current_version))
                except Exception as exc:
                    errors.append(f"{email['email_id']}: processing failed ({type(exc).__name__}); case was not overwritten")
        finally:
            processing_lock.release()
        return {"processed": len(results), "errors": errors, "cases": results}

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__, "ai": {"local": "Trained multinomial Naive Bayes + intent guards", "cloud_configured": cloud.enabled(), "cloud_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini")},
                "ocr": bool(shutil.which(os.getenv("TESSERACT_CMD", "tesseract"))), "storage": "SQLite", "demo_only": False}

    @app.get("/api/cases")
    def list_cases():
        reports = store.list()
        # The detail API supplies source text, full evidence and history on demand.
        summaries = [{k: v for k, v in r.items() if k not in ("documents", "audit")} for r in reports]
        return {"cases": summaries, "stats": statistics(reports), "audit_valid": store.audit()["valid"]}

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str):
        return get_case(case_id)

    @app.post("/api/demo")
    def seed_demo():
        return import_batch(list(folder_records(ROOT / "demo")), action="demo_loaded")

    @app.post("/api/import")
    async def import_files(request: Request):
        # Bound the complete body too, including chunked requests without Content-Length.
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 40 * 1024 * 1024:
                raise HTTPException(413, "Request exceeds the 40 MB upload limit")
            chunks.append(chunk)
        request._body = b"".join(chunks)
        try:
            async with request.form(max_files=1200, max_fields=20, max_part_size=40 * 1024 * 1024) as form:
                uploads = form.getlist("files")
                if not uploads:
                    raise HTTPException(422, "Upload an inbox ZIP or email JSON plus attachments")
                files = []
                for upload in uploads:
                    if not hasattr(upload, "read"):
                        raise ValueError("files must contain uploaded files")
                    files.append((upload.filename, await upload.read()))
                use_ai = str(form.get("use_ai", "false")).lower() in ("true", "1", "on")
                if use_ai and not cloud.enabled():
                    raise HTTPException(422, "Cloud mode requested, but OPENAI_API_KEY is not configured. Select local mode.")
                records, errors, ignored = records_from_files(files)
            result = await run_in_threadpool(import_batch, records, use_ai)
            result["errors"] = errors + result["errors"]
            result["ignored_files"] = ignored
            return result
        except (ValueError, OSError, zipfile.BadZipFile, NotImplementedError) as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/cases/{case_id}/retry")
    def retry(case_id: str, body: RetryBody):
        if body.use_ai and not cloud.enabled():
            raise HTTPException(422, "Cloud mode requested, but OPENAI_API_KEY is not configured. Select local mode.")
        before = get_case(case_id)
        files = {}
        for idx, filename in enumerate(before["email"]["attachments"]):
            try:
                stored = store.attachment(case_id, idx)
                files[idx] = (filename, stored["data"])
            except KeyError:
                pass
        after = process(before["email"], files, body.use_ai)
        after["data_origin"] = before.get("data_origin", "user_import")
        return store.save(after, "retried", {"source": "original attachments", "previous_review_replaced": before.get("reviewed", False)}, expected_version=before["version"])

    @app.post("/api/cases/{case_id}/simulate")
    def simulate_case(case_id: str, body: SimulationBody):
        try:
            before = get_case(case_id)
            proposed = with_category(before, body.category, "preview")
            preview = simulate(proposed, body.corrections)
            preview["before"] = before
            if body.category and body.category != before["category"]:
                preview["changes"].insert(0, {"field": "category", "before": before["category"], "after": body.category})
            return preview
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    def with_category(report, category, reviewer):
        if category is None:
            return report
        if category not in CATEGORIES:
            raise ValueError("Category must be one of the five supported email workflows")
        return dict(report, classification={"category": category, "method": "human_review", "reviewer": reviewer,
            "needs_review": False, "confidence": None, "scores": {}, "reason": "Email category confirmed by the reviewer",
            "previous": report.get("classification", {})})

    @app.post("/api/cases/{case_id}/review")
    def review_case(case_id: str, body: ReviewBody):
        if body.decision not in ("confirm", "correct"):
            raise HTTPException(422, "decision must be confirm or correct")
        if not body.reviewer.strip() or not body.note.strip():
            raise HTTPException(422, "Reviewer name and note are required")
        before = get_case(case_id)
        if before["version"] != body.version:
            raise Conflict("This case changed. Refresh before saving your review.")
        if body.decision == "confirm" and any(body.corrections.values()):
            raise HTTPException(422, "Choose correct when supplying changed field values")
        try:
            proposed = with_category(before, body.category, body.reviewer.strip())
            preview = simulate(proposed, body.corrections)
            if body.category and body.category != before["category"]:
                preview["changes"].insert(0, {"field": "category", "before": before["category"], "after": body.category})
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        after = preview["after"]
        if body.decision == "correct" and not preview["changes"]:
            raise HTTPException(422, "Provide at least one changed field, or confirm the current findings")
        after.update(reviewed=True, review={"reviewer": body.reviewer.strip(), "note": body.note.strip(),
            "decision": body.decision, "at": now(), "resolved": after["status"] != "NEEDS_REVIEW"})
        return store.save(after, "reviewed", dict(after["review"], changes=preview["changes"]), expected_version=body.version)

    @app.get("/api/cases/{case_id}/attachments/{idx}")
    def attachment(case_id: str, idx: int):
        get_case(case_id)
        try:
            row = store.attachment(case_id, idx)
        except KeyError:
            raise HTTPException(404, "Attachment was not supplied") from None
        # Download as opaque bytes: an uploaded document must never execute in our origin.
        filename = Path(row["filename"].replace("\\", "/")).name.encode("ascii", "replace").decode().replace('"', "_").replace("\r", "_").replace("\n", "_")
        return Response(row["data"], media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Source-SHA256": row["sha256"]})

    @app.get("/api/export/submission")
    def export_submission(scope: Literal["auto", "imported", "all"] = "auto"):
        """Avoid accidentally submitting the 12 fictional demo cases with participant records.

        The demo-only workspace remains exportable for judging; when imported cases
        exist, the default export includes those records only. The explicit `all`
        scope is available for a complete workspace snapshot.
        """
        reports = store.list()
        if scope == "imported" or (scope == "auto" and any(r.get("data_origin") == "user_import" for r in reports)):
            reports = [r for r in reports if r.get("data_origin") == "user_import"]
        return JSONResponse(official(reports), headers={"Content-Disposition": 'attachment; filename="submission.json"'})

    @app.get("/api/export/report")
    def export_report():
        return JSONResponse({"version": __version__, "reports": [store.get(r["email_id"]) for r in store.list()], "audit": store.audit()},
                            headers={"Content-Disposition": 'attachment; filename="harborlight-report.json"'})

    @app.get("/api/export/csv")
    def export_csv():
        out = io.StringIO(newline="")
        writer = csv.writer(out)
        writer.writerow(["email_id", "category", "status", "field", "SI", "BL", "outcome", "reason"])
        def cell(value):
            value = str(value if value is not None else "")
            return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value
        for report in store.list():
            for row in report.get("rows", []) or [{}]:
                writer.writerow([cell(v) for v in [report["email_id"], report["category"], report["status"], row.get("field"), row.get("si"), row.get("bl"), row.get("outcome"), row.get("reason")]])
        return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="discrepancies.csv"'})

    @app.get("/api/audit")
    def audit():
        return store.audit()

    app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT / "web" / "index.html")

    return app


app = create_app()
