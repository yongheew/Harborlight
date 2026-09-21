"""Read participant records only. Never extract archives or load answer keys."""
import io
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

MAX_FILE = 16 * 1024 * 1024
MAX_ARCHIVE = 120 * 1024 * 1024
MAX_MEMBERS = 2500
DOC_EXTENSIONS = {".txt", ".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
EXCLUDED = {"ground_truth.json", "sample_submission.json", "submission.json", "reports.json"}


def safe_name(name):
    name = str(name).replace("\\", "/")
    p = PurePosixPath(name)
    if not name or name.startswith("/") or ":" in name or ".." in p.parts or "\x00" in name:
        raise ValueError("Unsafe attachment/archive path")
    return str(p)


def validate_email(email):
    if not isinstance(email, dict) or not isinstance(email.get("email_id"), str):
        raise ValueError("An email record needs a string email_id")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", email["email_id"]):
        raise ValueError("email_id must contain only letters, digits, dots, underscores and hyphens")
    out = {"email_id": email["email_id"]}
    for key in ("subject", "body", "from"):
        value = email.get(key, "")
        if not isinstance(value, str) or len(value) > 100_000:
            raise ValueError(f"Invalid or overlong {key}")
        out[key] = value
    paths = email.get("attachments") or []
    if not isinstance(paths, list) or len(paths) > 20 or any(not isinstance(p, str) for p in paths):
        raise ValueError("attachments must be a list of at most 20 paths")
    out["attachments"] = [safe_name(p) for p in paths]
    if len(set(out["attachments"])) != len(out["attachments"]):
        raise ValueError("Duplicate attachment reference")
    return out


def unpack(files):
    """Return safe in-memory files, ignoring nonparticipant code and labels."""
    result, ignored = {}, []
    total, members = 0, 0
    for filename, data in files:
        name = safe_name(filename)
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_MEMBERS:
                    raise ValueError("Archive has too many members")
                if sum(e.file_size for e in entries) > MAX_ARCHIVE:
                    raise ValueError("Archive expands beyond 120 MB")
                incoming = []
                for entry in entries:
                    n = safe_name(entry.filename)
                    if entry.flag_bits & 0x1:
                        raise ValueError("Encrypted archives are not supported; upload unencrypted participant files")
                    if stat.S_ISLNK(entry.external_attr >> 16):
                        raise ValueError("Archive symlinks are not allowed")
                    if entry.is_dir():
                        continue
                    if entry.file_size > MAX_FILE:
                        raise ValueError("Archive member exceeds 16 MB")
                    if PurePosixPath(n).name.lower() in EXCLUDED or PurePosixPath(n).suffix.lower() not in DOC_EXTENSIONS | {".json"}:
                        ignored.append(n)
                        continue
                    incoming.append((n, archive.read(entry)))
        else:
            incoming = [(name, data)]
        for n, blob in incoming:
            members += 1
            total += len(blob)
            if len(blob) > MAX_FILE or total > MAX_ARCHIVE or members > MAX_MEMBERS:
                raise ValueError("Import exceeds the file or batch size limit")
            if n in result:
                raise ValueError(f"Duplicate path in import: {n}")
            if PurePosixPath(n).name.lower() in EXCLUDED:
                ignored.append(n)
            else:
                result[n] = blob
    return result, ignored


def records_from_files(files):
    blobs, ignored = unpack(files)
    emails, errors, seen = [], [], set()
    for name, blob in blobs.items():
        if not name.lower().endswith(".json"):
            continue
        try:
            raw = json.loads(blob.decode("utf-8-sig"))
            records = raw if isinstance(raw, list) else [raw]
            for raw_email in records:
                email = validate_email(raw_email)
                if email["email_id"] in seen:
                    raise ValueError("Duplicate email_id in import")
                seen.add(email["email_id"])
                resolved = {}
                for idx, path in enumerate(email["attachments"]):
                    candidates = [p for p in blobs if p == path or p.endswith("/" + path)]
                    if not candidates:
                        candidates = [p for p in blobs if PurePosixPath(p).name == PurePosixPath(path).name]
                    if len(candidates) > 1:
                        errors.append(f"{email['email_id']}: ambiguous attachment {path}; needs review")
                    elif candidates:
                        resolved[idx] = (path, blobs[candidates[0]])
                emails.append((email, resolved))
        except (ValueError, UnicodeError, TypeError) as exc:
            errors.append(f"{name}: {exc}")
    if not emails and not errors:
        errors.append("No email JSON records found. Include inbox/*.json with the referenced attachments.")
    return emails, errors, ignored


def folder_records(folder):
    root = Path(folder).resolve()
    inbox = root / "inbox"
    if not inbox.is_dir():
        raise ValueError("Expected a data directory containing inbox/ and attachments/")
    for path in sorted(inbox.glob("*.json")):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Inbox symlinks are not accepted")
        email = validate_email(json.loads(path.read_text(encoding="utf-8-sig")))
        files = {}
        for idx, filename in enumerate(email["attachments"]):
            target = (root / filename).resolve()
            if not target.is_relative_to(root):
                raise ValueError("Attachment outside dataset")
            if target.is_file():
                if target.stat().st_size > MAX_FILE:
                    continue
                files[idx] = (filename, target.read_bytes())
        yield email, files
