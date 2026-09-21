"""HTTP integration tests: import -> evidence -> simulate -> review -> export -> retry."""
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from harborlight.app import create_app, ROOT


def fixture_files(case_id="HTTP-001", missing=False):
    email = json.loads((ROOT / "demo/inbox/HL-002.json").read_text())
    email["email_id"] = case_id
    files = [("inbox/" + case_id + ".json", json.dumps(email).encode())]
    for path in email["attachments"]:
        if missing and "_BL" in path:
            continue
        data = (ROOT / "demo" / path).read_bytes()
        if "_BL" in path:
            data = data.replace(b"3 x 40HC", b"4 x 40HC")
        files.append((path, data))
    return files


def archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files:
            z.writestr(name, content)
    return buffer.getvalue()


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"HARBORLIGHT_SEED_DEMO": "0", "HARBORLIGHT_PASSWORD": "", "OPENAI_API_KEY": ""})
        self.env.start()
        self.path = Path(self.temp.name) / "api.sqlite3"
        self.app = create_app(self.path)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop()
        self.temp.cleanup()

    def upload(self, files=None):
        return self.client.post("/api/import", files=[("files", ("participant.zip", archive(files or fixture_files()), "application/zip"))])

    def test_complete_http_workflow_and_persistence(self):
        result = self.upload()
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["processed"], 1)
        report = self.client.get("/api/cases/HTTP-001").json()
        self.assertEqual(report["defect_fields"], ["container_count"])
        original = self.client.get("/api/cases/HTTP-001/attachments/1").content
        correction = {"bl": {"container_count": "3 x 40HC"}}
        preview = self.client.post("/api/cases/HTTP-001/simulate", json={"corrections": correction}).json()
        self.assertEqual(preview["after"]["status"], "OK")
        self.assertFalse(preview["persisted"])
        self.assertEqual(self.client.get("/api/cases/HTTP-001").json()["version"], 1)
        request = {"version": report["version"], "reviewer": "Test operator", "note": "Verified count against source", "decision": "correct", "corrections": correction}
        saved = self.client.post("/api/cases/HTTP-001/review", json=request)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["status"], "OK")
        self.assertTrue(saved.json()["reviewed"])
        self.assertEqual(self.client.post("/api/cases/HTTP-001/review", json=request).status_code, 409)
        self.assertEqual(self.client.get("/api/cases/HTTP-001/attachments/1").content, original)
        with TestClient(create_app(self.path)) as reopened:
            self.assertEqual(reopened.get("/api/cases/HTTP-001").json()["version"], 2)
        export = self.client.get("/api/export/submission").json()["HTTP-001"]
        self.assertEqual(set(export), {"category", "status", "review_reason", "has_defect", "defect_fields"})
        self.assertEqual(export["status"], "OK")
        full = self.client.get("/api/export/report").json()
        self.assertEqual(len(full["reports"][0]["audit"]), 2)
        self.assertTrue(full["audit"]["valid"])
        csv = self.client.get("/api/export/csv")
        self.assertIn("container_count", csv.text)
        self.assertIn("attachment", csv.headers["content-disposition"])
        retry = self.client.post("/api/cases/HTTP-001/retry", json={"use_ai": False})
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["status"], "MISMATCH")
        self.assertFalse(retry.json()["reviewed"])
        self.assertEqual(len(retry.json()["audit"]), 3)
        self.assertTrue(self.client.get("/api/audit").json()["valid"])

    def test_official_export_excludes_demo_cases_after_participant_import(self):
        with patch.dict(os.environ, {"HARBORLIGHT_SEED_DEMO": "1"}):
            with TestClient(create_app(Path(self.temp.name) / "mixed.sqlite3")) as mixed:
                self.assertEqual(len(mixed.get("/api/export/submission").json()), 12)
                result = mixed.post("/api/import", files=[("files", ("participant.zip", archive(fixture_files()), "application/zip"))])
                self.assertEqual(result.json()["processed"], 1)
                default_export = mixed.get("/api/export/submission").json()
                self.assertEqual(set(default_export), {"HTTP-001"})
                self.assertEqual(set(mixed.get("/api/export/submission?scope=imported").json()), {"HTTP-001"})
                self.assertEqual(len(mixed.get("/api/export/submission?scope=all").json()), 13)
                self.assertEqual(mixed.get("/api/export/submission?scope=invalid").status_code, 422)

    def test_broken_archive_is_actionable_error(self):
        response = self.client.post("/api/import", files=[("files", ("bad.zip", b"bad", "application/zip"))])
        self.assertEqual(response.status_code, 422)
        self.assertIn("zip", response.json()["detail"].lower())

    def test_zip_traversal_rejected_without_writes(self):
        self.assertEqual(self.upload([("../escape.txt", b"no")]).status_code, 422)
        self.assertEqual(self.client.get("/api/cases").json()["stats"]["total"], 0)

    def test_no_answer_keys_or_code_imported(self):
        files = fixture_files() + [("data/ground_truth.json", b"private"), ("data/generate.py", b"raise Exception()")]
        response = self.upload(files).json()
        self.assertEqual(response["processed"], 1)
        self.assertEqual(len(response["ignored_files"]), 2)
        self.assertFalse(response["errors"])

    def test_missing_source_is_review_not_clean(self):
        self.upload(fixture_files(missing=True))
        report = self.client.get("/api/cases/HTTP-001").json()
        self.assertEqual(report["status"], "NEEDS_REVIEW")
        self.assertEqual(report["review_reason"], "missing_attachment")
        response = self.client.post("/api/cases/HTTP-001/review", json={"version": 1, "reviewer": "Ops", "note": "Waiting for carrier", "decision": "confirm"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "NEEDS_REVIEW")
        self.assertFalse(response.json()["review"]["resolved"])
        self.assertEqual(self.client.get("/api/cases/HTTP-001/attachments/1").status_code, 404)

    def test_loose_files_match_referenced_basename(self):
        files = [("files", (Path(name).name, data, "application/octet-stream")) for name, data in fixture_files()]
        response = self.client.post("/api/import", files=files)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["cases"][0]["status"], "MISMATCH")

    def test_duplicate_attachment_candidates_require_review(self):
        files = fixture_files()
        files.append(("other/" + files[-1][0], files[-1][1]))
        result = self.upload(files).json()
        self.assertTrue(result["errors"])
        self.assertEqual(result["cases"][0]["status"], "NEEDS_REVIEW")

    def test_review_validation_and_no_cloud_key(self):
        self.upload()
        self.assertEqual(self.client.post("/api/cases/HTTP-001/review", json={"version": 1, "reviewer": " ", "note": " ", "decision": "confirm"}).status_code, 422)
        self.assertEqual(self.client.post("/api/cases/HTTP-001/simulate", json={"corrections": {"bl": {"fake": "value"}}}).status_code, 422)
        self.assertEqual(self.client.post("/api/cases/HTTP-001/retry", json={"use_ai": True}).status_code, 422)
        self.assertEqual(self.client.get("/api/cases/not-found").status_code, 404)

    def test_cross_origin_post_blocked_and_security_headers(self):
        response = self.client.post("/api/demo", json={}, headers={"Origin": "https://other.example"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/").headers["x-content-type-options"], "nosniff")

    def test_optional_basic_auth_and_public_health(self):
        with patch.dict(os.environ, {"HARBORLIGHT_PASSWORD": "example-test-password"}):
            self.assertEqual(self.client.get("/api/health").status_code, 200)
            self.assertEqual(self.client.get("/api/cases").status_code, 401)
            self.assertEqual(self.client.get("/api/cases", auth=("judge", "example-test-password")).status_code, 200)

    def test_csv_formula_injection_is_escaped(self):
        files = fixture_files()
        files[-1] = (files[-1][0], files[-1][1].replace(b"Singapore", b"=HYPERLINK('bad')"))
        self.upload(files)
        self.assertIn("'=HYPERLINK", self.client.get("/api/export/csv").text)

    def test_uncertain_category_can_be_confirmed_by_human(self):
        email = {"email_id": "UNCERTAIN-1", "subject": "", "body": "", "attachments": []}
        response = self.upload([("inbox/UNCERTAIN-1.json", json.dumps(email).encode())])
        self.assertEqual(response.json()["cases"][0]["status"], "NEEDS_REVIEW")
        preview = self.client.post("/api/cases/UNCERTAIN-1/simulate", json={"category": "GENERAL"}).json()
        self.assertFalse(preview["persisted"])
        self.assertEqual(preview["after"]["status"], "OK")
        saved = self.client.post("/api/cases/UNCERTAIN-1/review", json={"version": 1, "reviewer": "Ops", "note": "Confirmed blank operational email", "category": "GENERAL", "decision": "confirm"})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["status"], "OK")
        self.assertEqual(saved.json()["classification"]["method"], "human_review")
        self.assertTrue(saved.json()["classification"]["previous"]["needs_review"])

    def test_reclassifying_to_comparison_reuses_preserved_documents(self):
        files = fixture_files()
        email = json.loads(files[0][1])
        email["subject"], email["body"] = "Invoice amount", "Please explain the invoice charges."
        files[0] = (files[0][0], json.dumps(email).encode())
        self.upload(files)
        before = self.client.get("/api/cases/HTTP-001").json()
        self.assertEqual(before["category"], "INVOICE_QUERY")
        after = self.client.post("/api/cases/HTTP-001/review", json={"version": 1, "reviewer": "Ops", "note": "Confirmed correct workflow using attached request", "category": "BL_COMPARISON", "decision": "confirm"}).json()
        self.assertEqual(after["category"], "BL_COMPARISON")
        self.assertEqual(after["defect_fields"], ["container_count"])


if __name__ == "__main__":
    unittest.main()
