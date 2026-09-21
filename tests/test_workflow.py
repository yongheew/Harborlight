"""Persisted workflow tests with entirely independent shipping fixtures."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harborlight.service import official, process, simulate, statistics
from harborlight.store import Conflict, Store


def pair(case_id="workflow-case", count=4):
    fields = "\nShipper: Atlas Paper Limited\nConsignee: Beacon Trading Limited\nNotify Party: Beacon Trading Limited\nPort of Loading: Shanghai\nPort of Discharge: Rotterdam\nContainer Count: {count}\nGross Weight (KG): 22000\n"
    email = {"email_id": case_id, "subject": "Verification", "body": "Please compare the attached SI and draft BL.", "attachments": ["instruction.txt", "bill.txt"]}
    files = {0: ("instruction.txt", ("SHIPPING INSTRUCTION" + fields.format(count=3)).encode()),
             1: ("bill.txt", ("DRAFT BILL OF LADING" + fields.format(count=count)).encode())}
    return email, files


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "cases.db"
        self.store = Store(self.path)
        self.email, self.files = pair()
        self.report = self.store.save(process(self.email, self.files), "import", files=self.files)

    def tearDown(self):
        self.temp.cleanup()

    def test_simulation_changes_verdict_without_persistence_or_source_mutation(self):
        before = copy.deepcopy(self.report)
        result = simulate(self.report, {"bl": {"container_count": "3"}})
        self.assertFalse(result["persisted"])
        self.assertEqual(result["after"]["status"], "OK")
        self.assertEqual(result["before"]["status"], "MISMATCH")
        self.assertEqual(self.report, before)
        self.assertEqual(self.store.get(self.email["email_id"])["status"], "MISMATCH")
        self.assertEqual(self.store.get(self.email["email_id"])["version"], 1)
        self.assertEqual(len(self.store.audit()["events"]), 1)
        self.assertEqual(self.store.attachment(self.email["email_id"], 1)["data"], self.files[1][1])

    def test_human_correction_persists_provenance_and_source_hash(self):
        preview = simulate(self.report, {"bl": {"container_count": "3"}})
        after = preview["after"]
        after["reviewed"] = True
        saved = self.store.save(after, "review_correct", {"reviewer": "Operator", "note": "Source count verified", "changes": preview["changes"]}, expected_version=1)
        reopened = Store(self.path).get(self.email["email_id"])
        self.assertEqual(reopened["status"], "OK")
        self.assertTrue(reopened["reviewed"])
        self.assertEqual(reopened["version"], 2)
        self.assertEqual(reopened["created_at"], self.report["created_at"])
        corrected = next(d for d in reopened["documents"] if d["kind"] == "BL")["fields"]["container_count"]
        self.assertEqual(corrected["method"], "human_review")
        self.assertEqual(corrected["original"]["value"], "4")
        self.assertIn("4", corrected["evidence"])
        self.assertEqual(corrected["value"], "3")
        self.assertEqual(saved["source_hashes"], self.report["source_hashes"])
        self.assertTrue(self.store.audit()["valid"])

    def test_retry_reads_immutable_sources_and_resets_override_with_audit(self):
        corrected = simulate(self.report, {"bl": {"container_count": "3"}})["after"]
        corrected["reviewed"] = True
        saved = self.store.save(corrected, "review_correct", {"reviewer": "Operator"}, expected_version=1)
        stored_files = {idx: (self.store.attachment(self.email["email_id"], idx)["filename"], self.store.attachment(self.email["email_id"], idx)["data"]) for idx in self.files}
        retry = self.store.save(process(self.email, stored_files), "retry", {"reset_overrides": True}, expected_version=saved["version"])
        self.assertEqual(retry["status"], "MISMATCH")
        self.assertFalse(retry["reviewed"])
        self.assertEqual(retry["version"], 3)
        self.assertEqual([event["action"] for event in retry["audit"]], ["import", "review_correct", "retry"])
        self.assertTrue(self.store.audit()["valid"])

    def test_stale_review_is_atomic_and_adds_no_event(self):
        current = self.store.save(self.report, "review_confirm", expected_version=1)
        with self.assertRaises(Conflict):
            self.store.save(self.report, "review_correct", expected_version=1)
        self.assertEqual(self.store.get(self.email["email_id"])["version"], current["version"])
        self.assertEqual(len(self.store.audit()["events"]), 2)
        self.assertTrue(self.store.audit()["valid"])

    def test_failed_file_mutation_rolls_back_transaction(self):
        invalid_files = {0: ("instruction.txt", self.files[0][1]), 1: ("broken.txt", None)}
        with self.assertRaises(TypeError):
            self.store.save(self.report, "replace", files=invalid_files, expected_version=1)
        self.assertEqual(self.store.get(self.email["email_id"])["version"], 1)
        self.assertEqual(self.store.attachment(self.email["email_id"], 1)["data"], self.files[1][1])
        self.assertTrue(self.store.audit()["valid"])

    def test_cloud_classification_survives_preview_without_new_cloud_call(self):
        report = copy.deepcopy(self.report)
        report["email"]["body"] = "The new document is available."
        report["classification"] = {"category": "BL_COMPARISON", "method": "cloud_structured", "confidence": None, "reason": "Validated intent", "evidence": "The new document is available."}
        report["ai"] = {"requested": True, "used": True, "model": "test-model"}
        with patch("harborlight.service.cloud.classify_email", side_effect=AssertionError("Preview must not call cloud")):
            after = simulate(report, {"bl": {"container_count": "3"}})["after"]
        self.assertEqual(after["category"], "BL_COMPARISON")
        self.assertEqual(after["classification"], report["classification"])
        self.assertEqual(after["ai"], report["ai"])
        self.assertEqual(len(after["rows"]), 7)

    def test_source_fingerprint_is_canonical_not_dict_insertion_order(self):
        reordered = dict(reversed(list(self.email.items())))
        self.assertEqual(process(reordered, self.files)["source_fingerprint"], process(self.email, self.files)["source_fingerprint"])

    def test_corrections_reject_incomplete_pair_and_bad_input(self):
        incomplete = process(dict(self.email, attachments=["instruction.txt"]), {0: self.files[0]})
        with self.assertRaises(ValueError):
            simulate(incomplete, {"si": {"shipper": "Updated shipper"}})
        for corrections in ({"other": {}}, {"bl": {"unknown": "3"}}, {"bl": {"container_count": True}}, {"bl": {"gross_weight_kg": float("nan")}}, {"bl": {"shipper": ""}}):
            with self.subTest(corrections=corrections), self.assertRaises(ValueError):
                simulate(self.report, corrections)

    def test_parser_failure_is_visible(self):
        with patch("harborlight.service.read_document", side_effect=RuntimeError("broken parser")):
            report = process(self.email, self.files)
        self.assertEqual(report["status"], "NEEDS_REVIEW")
        self.assertEqual(report["review_reason"], "unreadable")
        self.assertTrue(all("Reader failed" in doc["error"] for doc in report["documents"]))

    def test_export_strips_internal_fields_and_stats_are_consistent(self):
        output = official([self.report])
        self.assertEqual(set(output[self.email["email_id"]]), {"category", "status", "review_reason", "has_defect", "defect_fields"})
        self.assertEqual(statistics([self.report])["mismatches"], 1)
        self.assertEqual(statistics([self.report])["observed_field_discrepancies"], 1)


class AuditTamperTests(unittest.TestCase):
    def assert_detected(self, sql, parameters=()):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "tamper.db")
            email, files = pair()
            store.save(process(email, files), "import", files=files)
            self.assertTrue(store.audit()["valid"])
            with store.connect() as db:
                db.execute(sql, parameters)
            self.assertFalse(store.audit()["valid"])

    def test_report_edit_detected(self):
        self.assert_detected("UPDATE cases SET report=json_set(report, '$.status', 'OK')")

    def test_attachment_edit_detected(self):
        self.assert_detected("UPDATE attachments SET data=? WHERE idx=1", (b"replaced document",))

    def test_attachment_delete_detected(self):
        self.assert_detected("DELETE FROM attachments WHERE idx=1")

    def test_event_edit_detected(self):
        self.assert_detected("UPDATE audit SET event=json_set(event, '$.action', 'forged')")

    def test_event_delete_detected(self):
        self.assert_detected("DELETE FROM audit")

    def test_case_delete_detected(self):
        self.assert_detected("DELETE FROM cases")

    def test_sql_version_edit_detected(self):
        self.assert_detected("UPDATE cases SET version=99")

    def test_invalid_event_json_returns_invalid_result(self):
        self.assert_detected("UPDATE audit SET event='broken json'")

    def test_invalid_case_json_returns_invalid_result(self):
        self.assert_detected("UPDATE cases SET report='broken json'")

    def test_invalid_manifest_shape_returns_invalid_result(self):
        self.assert_detected("UPDATE cases SET report=json_set(report, '$.source_hashes', NULL)")

    def test_invalid_attachment_storage_type_returns_invalid_result(self):
        self.assert_detected("UPDATE attachments SET data='not a blob' WHERE idx=1")


if __name__ == "__main__":
    unittest.main()
