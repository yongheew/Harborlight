"""Transactional SQLite case storage and a verifiable, locally hash-chained audit log.

This detects accidental edits; it is not externally anchored or tamper-proof against
an administrator who can rewrite the entire database and recompute the chain.
"""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(Exception):
    pass


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY, report TEXT NOT NULL, version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attachments (
                    case_id TEXT NOT NULL, idx INTEGER NOT NULL,
                    filename TEXT NOT NULL, data BLOB NOT NULL, sha256 TEXT NOT NULL,
                    PRIMARY KEY(case_id, idx)
                );
                CREATE TABLE IF NOT EXISTS audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
                    event TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, case_id):
        with self.connect() as db:
            row = db.execute("SELECT report FROM cases WHERE id=?", (case_id,)).fetchone()
            if row is None:
                raise KeyError(case_id)
            report = json.loads(row[0])
            report["audit"] = [json.loads(r[0]) | {"hash": r[1]} for r in db.execute(
                "SELECT event,hash FROM audit WHERE case_id=? ORDER BY seq", (case_id,))]
            return report

    def list(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT report FROM cases ORDER BY id")]

    def attachment(self, case_id, idx):
        with self.connect() as db:
            row = db.execute("SELECT filename,data,sha256 FROM attachments WHERE case_id=? AND idx=?",
                             (case_id, idx)).fetchone()
            if row is None:
                raise KeyError((case_id, idx))
            return dict(row)

    def save(self, report, action, payload=None, files=None, expected_version=None):
        report = {k: v for k, v in report.items() if k != "audit"}
        case_id = report["email_id"]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT version,report FROM cases WHERE id=?", (case_id,)).fetchone()
            previous = existing[0] if existing else 0
            if expected_version is not None and expected_version != previous:
                raise Conflict("This case changed. Refresh before saving your review.")
            report.update(id=case_id, version=previous + 1, updated_at=now())
            report["created_at"] = json.loads(existing[1])["created_at"] if existing else report["updated_at"]
            if files is not None:
                db.execute("DELETE FROM attachments WHERE case_id=?", (case_id,))
                for idx, (filename, data) in files.items():
                    db.execute("INSERT INTO attachments VALUES(?,?,?,?,?)", (
                        case_id, idx, filename, data, hashlib.sha256(data).hexdigest()))
            file_manifest = {str(r[0]): r[1] for r in db.execute(
                "SELECT idx,sha256 FROM attachments WHERE case_id=?", (case_id,))}
            report["source_hashes"] = file_manifest
            db.execute("INSERT INTO cases VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET report=excluded.report,version=excluded.version",
                       (case_id, canonical(report), report["version"]))
            tail = db.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
            prev = tail[0] if tail else "0" * 64
            event = {"case_id": case_id, "action": action, "timestamp": now(), "version": report["version"],
                     "report_hash": digest(report), "payload": payload or {}}
            event_hash = digest({"previous": prev, "event": event})
            db.execute("INSERT INTO audit(case_id,event,prev_hash,hash) VALUES(?,?,?,?)",
                       (case_id, canonical(event), prev, event_hash))
        return self.get(case_id)

    def audit(self):
        with self.connect() as db:
            rows = list(db.execute("SELECT * FROM audit ORDER BY seq"))
            latest = {}
            valid, prev, events, errors = True, "0" * 64, [], []
            for row in rows:
                try:
                    event = json.loads(row["event"])
                    if not isinstance(event, dict) or not all(key in event for key in ("case_id", "report_hash", "version")):
                        raise ValueError("Invalid event schema")
                except (ValueError, TypeError):
                    valid = False
                    errors.append(f"Audit event {row['seq']} is invalid JSON or has an invalid schema")
                    prev = row["hash"]
                    continue
                valid &= row["prev_hash"] == prev and row["hash"] == digest({"previous": prev, "event": event})
                valid &= row["case_id"] == event["case_id"]
                latest[row["case_id"]] = event["report_hash"]
                prev = row["hash"]
                events.append(event | {"seq": row["seq"], "hash": row["hash"], "previous_hash": row["prev_hash"]})
            reports = {}
            for row in db.execute("SELECT id,report,version FROM cases"):
                try:
                    report = json.loads(row["report"])
                    if not isinstance(report, dict):
                        raise ValueError("Invalid report schema")
                    reports[row["id"]] = report
                    valid &= report.get("version") == row["version"]
                    valid &= report.get("id") == row["id"] == report.get("email_id")
                    valid &= latest.get(row["id"]) == digest(report)
                except (ValueError, TypeError):
                    valid = False
                    errors.append(f"Case {row['id']} has invalid stored JSON")
            valid &= set(latest) == set(reports)
            for row in db.execute("SELECT case_id,idx,data,sha256 FROM attachments"):
                manifest = reports.get(row["case_id"], {}).get("source_hashes", {})
                if not isinstance(manifest, dict) or not isinstance(row["data"], bytes):
                    valid = False
                    errors.append(f"Attachment manifest or bytes for {row['case_id']} is invalid")
                    continue
                valid &= hashlib.sha256(row["data"]).hexdigest() == row["sha256"] == manifest.get(str(row["idx"]))
            for case_id, report in reports.items():
                expected = report.get("source_hashes", {})
                actual = {str(r[0]): r[1] for r in db.execute("SELECT idx,sha256 FROM attachments WHERE case_id=?", (case_id,))}
                valid &= expected == actual
            return {"events": events, "valid": bool(valid), "errors": errors, "scope": "Local hash chain; not externally anchored"}
