"""Shared application operations used by the web server and CLI."""
import copy
import hashlib
import math
import time
from pathlib import PurePosixPath

from . import cloud
from .engine import FIELDS, analyze
from .readers import read_document
from .store import digest


def process(email, files, use_ai=False):
    start = time.perf_counter()
    docs = []
    for idx, filename in enumerate(email.get("attachments", [])):
        if idx in files:
            _, data = files[idx]
            try:
                doc = read_document(data, filename)
            except Exception as exc:
                # A broken parser may never turn a failed read into a clean match.
                doc = {"filename": filename, "kind": "UNKNOWN", "text": "", "pages": [], "fields": {},
                       "warnings": [], "error": f"Reader failed ({type(exc).__name__}); retry or replace attachment", "sha256": hashlib.sha256(data).hexdigest()}
        else:
            doc = {"filename": filename, "kind": "UNKNOWN", "text": "", "pages": [], "fields": {},
                   "warnings": [], "error": "Referenced attachment was not supplied", "missing": True, "sha256": None}
        doc["source_index"] = idx
        docs.append(doc)
    ai = {"requested": False, "used": False, "mode": "local_ml", "errors": []}
    classification = None
    if use_ai:
        docs, ai = cloud.enrich(docs)
        try:
            classification, call = cloud.classify_email(email)
            ai.setdefault("calls", []).append(call)
            ai.update(used=True, mode="local_ml+cloud")
        except (RuntimeError, ValueError, TypeError) as exc:
            ai.setdefault("errors", []).append(str(exc))
    report = analyze(email, docs, classification=classification)
    report["documents"] = docs
    report["ai"] = dict(report.get("ai", {}), **ai)
    report["email"] = email
    report["processing_ms"] = round((time.perf_counter() - start) * 1000, 2)
    report["reviewed"] = False
    report["source_fingerprint"] = digest({"email": email, "document_hashes": [d.get("sha256") for d in docs]})
    # Missing referenced bytes are an attachment problem regardless of filename hints.
    if report["category"] == "BL_COMPARISON" and any(d.get("missing") for d in docs):
        report.update(status="NEEDS_REVIEW", review_reason="missing_attachment", has_defect=False, defect_fields=[],
                      summary="Referenced SI or BL attachment is missing. Supply the source and retry.")
    return report


def simulate(report, corrections):
    if not isinstance(corrections, dict) or set(corrections) - {"si", "bl"}:
        raise ValueError("Corrections must contain only si and bl field mappings")
    docs = copy.deepcopy(report.get("documents", []))
    changes = []
    if any(bool(fields) for fields in corrections.values()):
        for kind in ("SI", "BL"):
            candidates = [doc for doc in docs if doc.get("kind") == kind and not doc.get("error")]
            if len(candidates) != 1:
                raise ValueError("Replace/re-import missing, unreadable or ambiguous source documents before correcting fields")
    for side, fields in corrections.items():
        if not isinstance(fields, dict) or set(fields) - set(FIELDS):
            raise ValueError("Unknown correction field")
        candidates = [d for d in docs if d.get("kind", "").upper() == side.upper()]
        if fields and (len(candidates) != 1 or candidates[0].get("error")):
            raise ValueError("Replace/re-import missing, unreadable or ambiguous source documents before correcting fields")
        if not fields:
            continue
        doc = candidates[0]
        for field, value in fields.items():
            if not isinstance(value, (str, int, float)) or isinstance(value, bool) or (isinstance(value, float) and not math.isfinite(value)) or len(str(value)) > 2000 or not str(value).strip():
                raise ValueError("Corrections must be non-empty values of at most 2000 characters")
            original = copy.deepcopy(doc.setdefault("fields", {}).get(field, {}))
            value = str(value).strip()
            if str(original.get("value", "")) == value:
                continue
            doc["fields"][field] = {"value": value, "evidence": original.get("evidence", ""),
                "page": original.get("page", 1), "confidence": 1.0, "method": "human_review", "original": original,
                "review_note": "Operator-supplied value; original source document is unchanged"}
            changes.append({"side": side, "field": field, "before": original.get("value"), "after": value})
    # A preview changes extracted fields only. Re-running local classification
    # here would silently discard an opted-in, evidence-grounded cloud decision.
    after = analyze(report["email"], docs, classification=copy.deepcopy(report.get("classification")))
    after.update(email=report["email"], documents=docs, ai=report.get("ai", {}), reviewed=report.get("reviewed", False))
    for key in ("id", "version", "created_at", "processing_ms", "source_fingerprint", "source_hashes", "data_origin"):
        if key in report:
            after[key] = report[key]
    return {"before": report, "after": after, "changes": changes, "persisted": False}


def official(reports):
    keys = ("category", "status", "review_reason", "has_defect", "defect_fields")
    result = {r["email_id"]: {key: r.get(key) for key in keys} for r in reports}
    # The organizer's v2 reason vocabulary has no uncertain-intent label.
    # Keep NEEDS_REVIEW; retain the richer reason in the full evidence export.
    for record in result.values():
        if record["review_reason"] not in (None, "wrong_doc_type", "missing_attachment", "unreadable", "missing_value"):
            record["review_reason"] = None
    return result


def statistics(reports):
    return {"total": len(reports), "clean": sum(r["status"] == "OK" and r["category"] == "BL_COMPARISON" for r in reports),
        "mismatches": sum(r["status"] == "MISMATCH" for r in reports), "review": sum(r["status"] == "NEEDS_REVIEW" for r in reports),
        "classified": sum(r["category"] != "BL_COMPARISON" and r["status"] == "OK" for r in reports), "reviewed": sum(bool(r.get("reviewed")) for r in reports),
        "observed_field_discrepancies": sum(sum(row["outcome"] == "mismatch" for row in r.get("rows", [])) for r in reports),
        "processing_ms": round(sum(r.get("processing_ms", 0) for r in reports), 1)}
