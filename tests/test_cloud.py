"""Cloud boundary tests with mocked transport; no paid API calls are made."""
import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from harborlight import cloud


def response(payload):
    return io.BytesIO(json.dumps(payload).encode())


class CloudTests(unittest.TestCase):
    def test_no_key_never_calls_network(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), patch("urllib.request.urlopen") as network:
            docs, meta = cloud.enrich([])
            self.assertFalse(meta["used"])
            self.assertTrue(meta["errors"])
            with self.assertRaises(RuntimeError):
                cloud.classify_email({"subject": "Hello", "body": "Please compare the draft BL"})
            network.assert_not_called()

    def test_request_is_structured_and_not_stored(self):
        payload = {"status": "completed", "output": [{"content": [{"type": "output_text", "text": '{"answer":"ok"}'}]}]}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-test-key"}), patch("urllib.request.urlopen", return_value=response(payload)) as network:
            data, meta = cloud.request_json("Extract", {}, {"type": "object"})
            body = json.loads(network.call_args.args[0].data)
            self.assertFalse(body["store"])
            self.assertTrue(body["text"]["format"]["strict"])
            self.assertEqual(data["answer"], "ok")

    def test_refusal_and_truncation_are_failures(self):
        for payload in [{"status": "incomplete"}, {"status": "completed", "output": [{"content": [{"type": "refusal", "refusal": "No"}]}]}, [], {"output": [{"content": [{"type": "output_text", "text": "[]"}]}]}]:
            with self.subTest(payload=payload), patch.dict(os.environ, {"OPENAI_API_KEY": "fake-test-key"}), patch("urllib.request.urlopen", return_value=response(payload)):
                with self.assertRaises(RuntimeError):
                    cloud.request_json("Extract", {}, {})

    def test_retry_only_transient_http_errors(self):
        error = urllib.error.HTTPError("https://api.openai.com", 429, "rate", {}, None)
        success = response({"output": [{"content": [{"type": "output_text", "text": "{}"}]}]})
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-test-key"}), patch("urllib.request.urlopen", side_effect=[error, success]) as network, patch("time.sleep"):
            cloud.request_json("Extract", {}, {})
            self.assertEqual(network.call_count, 2)

    def test_category_requires_literal_email_evidence(self):
        email = {"subject": "Check documents", "body": "Please compare the SI and BL."}
        for value in [{"category": "HACK", "quote": "Please compare"}, {"category": "BL_COMPARISON", "quote": "invented"}]:
            with patch.object(cloud, "request_json", return_value=(value, {"model": "test"})):
                with self.assertRaises(RuntimeError):
                    cloud.classify_email(email)
        with patch.object(cloud, "request_json", return_value=({"category": "BL_COMPARISON", "quote": "Please compare", "reason": "Comparison requested"}, {"model": "test"})):
            result, _ = cloud.classify_email(email)
            self.assertIsNone(result["confidence"])
            self.assertEqual(result["category"], "BL_COMPARISON")

    def test_ungrounded_extraction_is_rejected(self):
        doc = {"filename": "si.txt", "kind": "SI", "text": "Shipper: Meridian", "pages": [{"page": 1, "text": "Shipper: Meridian"}], "fields": {}}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-test-key"}), patch.object(cloud, "request_json", return_value=({"shipper": {"value": "Invented Ltd", "quote": "Shipper: Invented Ltd", "page": 1}}, {"model": "test"})):
            docs, meta = cloud.enrich([doc])
            self.assertEqual(meta["accepted_fields"], 0)
            self.assertTrue(docs[0]["warnings"])
            self.assertEqual(doc["fields"], {})

    def test_grounded_extraction_preserves_quote_and_page(self):
        doc = {"filename": "si.txt", "kind": "SI", "text": "Shipper: Meridian", "pages": [{"page": 2, "text": "Shipper: Meridian"}], "fields": {}}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-test-key"}), patch.object(cloud, "request_json", return_value=({"shipper": {"value": "Meridian", "quote": "Shipper: Meridian", "page": 2}}, {"model": "test"})):
            docs, meta = cloud.enrich([doc])
            self.assertEqual(meta["accepted_fields"], 1)
            self.assertEqual(docs[0]["fields"]["shipper"]["page"], 2)
            self.assertEqual(doc["fields"], {})

    def test_conflicting_local_and_cloud_value_abstains(self):
        doc = {"filename": "si.txt", "kind": "SI", "text": "Shipper: Meridian\nShipper: Other", "pages": [{"page": 1, "text": "Shipper: Meridian\nShipper: Other"}], "fields": {"shipper": {"value": "Meridian", "evidence": "Shipper: Meridian"}}}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-test-key"}), patch.object(cloud, "request_json", return_value=({"shipper": {"value": "Other", "quote": "Shipper: Other", "page": 1}}, {"model": "test"})):
            docs, meta = cloud.enrich([doc])
            self.assertIsNone(docs[0]["fields"]["shipper"]["value"])
            self.assertTrue(docs[0]["fields"]["shipper"]["conflict"])


if __name__ == "__main__":
    unittest.main()
