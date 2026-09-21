"""Batch analysis and organizer-compatible evaluation without the web UI."""
import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .ingest import MAX_FILE, folder_records, validate_email
from .service import official, process, statistics


def http_read(url, limit=MAX_FILE):
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Remote response exceeds size limit")
    return data


def source_records(source):
    if not source.startswith(("http://", "https://")):
        yield from folder_records(source)
        return
    base = source.rstrip("/")
    emails = json.loads(http_read(base + "/emails"))
    for raw in emails:
        email = validate_email(raw)
        files = {}
        for idx, path in enumerate(email["attachments"]):
            suffix = path.removeprefix("attachments/")
            try:
                files[idx] = (path, http_read(base + "/attachments/" + urllib.parse.quote(suffix, safe="/")))
            except (OSError, ValueError):
                pass  # process records a visible missing-attachment case
        yield email, files


def main():
    parser = argparse.ArgumentParser(description="Harborlight evidence-first document verification")
    parser.add_argument("source", help="Dataset folder containing inbox/, or organizer HTTP service URL")
    parser.add_argument("--out", default="results", help="Output directory")
    parser.add_argument("--ai", action="store_true", help="Opt in to sending email text and incomplete document text to OpenAI")
    parser.add_argument("--evaluate", metavar="URL", help="POST output to an organizer /submit endpoint; returns aggregate scoreboard only")
    args = parser.parse_args()
    destination = Path(args.out)
    destination.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    reports = []
    for email, files in source_records(args.source):
        reports.append(process(email, files, args.ai))
        if len(reports) % 100 == 0:
            print(f"Processed {len(reports)} emails", flush=True)
    if not reports:
        raise SystemExit("No inbox records found. Nothing was exported.")
    submission = official(reports)
    (destination / "submission.json").write_text(json.dumps(submission, indent=2, ensure_ascii=False), encoding="utf-8")
    (destination / "reports.json").write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
    metrics = statistics(reports) | {"wall_seconds": round(time.perf_counter() - started, 3), "cloud_requested": args.ai}
    (destination / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    if args.evaluate:
        endpoint = args.evaluate.rstrip("/")
        if not endpoint.endswith("/submit"):
            endpoint += "/submit"
        request = urllib.request.Request(endpoint, data=json.dumps(submission).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            score = json.loads(response.read(2_000_000))
        (destination / "scoreboard.json").write_text(json.dumps(score, indent=2), encoding="utf-8")
        print("Organizer aggregate scoreboard:")
        print(json.dumps(score, indent=2))


if __name__ == "__main__":
    main()
