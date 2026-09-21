"""Evidence-based shipping comparison. SI is always the reference.

This module is intentionally side-effect free: it cannot send emails, approve
shipments, mutate source files, read answer keys, or execute document content.
"""
from __future__ import annotations

import copy
import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from .classifier import CATEGORIES, classify

FIELDS = ("shipper", "consignee", "notify_party", "port_of_loading", "port_of_discharge", "container_count", "gross_weight_kg")
MISSING = {"", "n/a", "na", "none", "null", "unknown", "tba", "tbd", "tbc", "pending", "not available", "not provided", "not specified", "to be advised", "to be confirmed", "nil"}
FIELD_WEIGHTS = {"shipper": 15, "consignee": 20, "notify_party": 10, "port_of_loading": 18, "port_of_discharge": 20, "container_count": 22, "gross_weight_kg": 18}


def _value(doc: dict, field: str) -> tuple[object, dict]:
    item = doc.get("fields", {}).get(field, {})
    if isinstance(item, dict):
        return item.get("value"), item
    return item, {"value": item, "evidence": "", "method": "unspecified"}


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    text = str(value).strip().casefold()
    return text in MISSING or not re.search(r"[\w\d]", text, re.UNICODE) or bool(re.fullmatch(r"[?_\-\s.*]+", text))


def _decimal(text: str) -> Decimal:
    """Parse grouped and decimal notation, rejecting malformed separators."""
    text = re.sub(r"[\s\u00a0\u202f']", "", text.strip())
    if not re.fullmatch(r"\+?\d+(?:[.,]\d+)*", text):
        raise ValueError("Number is not a non-negative decimal")
    if "," in text and "." in text:
        decimal_mark = "," if text.rfind(",") > text.rfind(".") else "."
        group_mark = "." if decimal_mark == "," else ","
        integer, fraction = text.rsplit(decimal_mark, 1)
        if not re.fullmatch(r"\+?\d{1,3}(?:" + re.escape(group_mark) + r"\d{3})+", integer):
            raise ValueError("Inconsistent thousands separators")
        text = integer.replace(group_mark, "") + "." + fraction
    elif "," in text:
        if re.fullmatch(r"\+?\d{1,3}(?:,\d{3})+", text):
            text = text.replace(",", "")
        elif text.count(",") == 1 and len(text.rsplit(",", 1)[1]) in (1, 2):
            text = text.replace(",", ".")
        else:
            raise ValueError("Ambiguous comma notation")
    elif text.count(".") > 1:
        if re.fullmatch(r"\+?\d{1,3}(?:\.\d{3})+", text):
            text = text.replace(".", "")
        else:
            raise ValueError("Ambiguous dot notation")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Invalid number") from exc
    if not value.is_finite() or value < 0:
        raise ValueError("Value must be a finite non-negative number")
    return value


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _count(value: object) -> tuple[str | None, str]:
    text = unicodedata.normalize("NFKC", str(value)).lower().strip()
    text = text.replace("×", "x")
    if re.fullmatch(r"\d+(?:\.0+)?", text):
        number = _decimal(text)
        if number == number.to_integral_value():
            return str(int(number)), "Integer container quantity"
    # Sum quantity-by-equipment expressions, never mistake 40-foot size for count.
    pattern = r"(\d+)\s*x\s*(?:20|40|45)\s*(?:['\"′’\-]|ft|feet)?\s*(?:hc|hq|gp|dv|dc|rf|fcl|reefer|high\s*cube|standard)?(?:\s*containers?)?"
    matches = list(re.finditer(pattern, text))
    if matches:
        remainder = re.sub(pattern, "", text)
        if re.fullmatch(r"[\s,+;&/]*(?:(?:and|plus)[\s,+;&/]*)?", remainder):
            return str(sum(int(match.group(1)) for match in matches)), "Summed quantity × equipment entries; size is not quantity"
        return None, "Container text includes an unresolved number or qualifier"
    match = re.fullmatch(r"(?:total\s*[:=]?\s*)?(\d+)\s*(?:containers?|ctnrs?|units?|boxes?|nos?\.?)", text)
    if match:
        return str(int(match.group(1))), "Explicit container quantity"
    return None, "Container quantity is ambiguous; ranges, package counts, and IDs cannot establish a count"


def _weight(value: object) -> tuple[Decimal, str, Decimal]:
    text = unicodedata.normalize("NFKC", str(value)).lower().strip()
    text = re.sub(r"^(?:gross\s*(?:weight|wt)\s*[:=]?\s*)", "", text)
    match = re.fullmatch(r"([+\d][\d\s.,'\u00a0\u202f]*)\s*([a-z. ]*)", text)
    if not match:
        raise ValueError("Weight contains multiple values or an unsupported expression")
    value = _decimal(match.group(1))
    unit = re.sub(r"[.\s]", "", match.group(2))
    units = {
        "": ("kg", Decimal(1)), "kg": ("kg", Decimal(1)), "kgs": ("kg", Decimal(1)),
        "kilogram": ("kg", Decimal(1)), "kilograms": ("kg", Decimal(1)),
        "mt": ("tonne", Decimal(1000)), "t": ("tonne", Decimal(1000)),
        "tonne": ("tonne", Decimal(1000)), "tonnes": ("tonne", Decimal(1000)),
        "metricton": ("tonne", Decimal(1000)), "metrictons": ("tonne", Decimal(1000)),
        "metrictonne": ("tonne", Decimal(1000)), "metrictonnes": ("tonne", Decimal(1000)),
        "lb": ("lb", Decimal("0.45359237")), "lbs": ("lb", Decimal("0.45359237")),
        "pound": ("lb", Decimal("0.45359237")), "pounds": ("lb", Decimal("0.45359237")),
    }
    if unit not in units:
        raise ValueError("Unknown or ambiguous weight unit (plain 'ton' is not assumed metric)")
    name, factor = units[unit]
    resolution = Decimal(10) ** value.as_tuple().exponent * factor
    return value * factor, name, resolution


def _text(value: object, field: str) -> str:
    value = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    value = value.replace("&", " and ")
    # Dotted initialisms: U.A.E. -> UAE. Do not remove whole legal suffixes.
    value = re.sub(r"\b(?:[a-z]\.){2,}", lambda m: m.group(0).replace(".", ""), value)
    value = re.sub(r"[^\w\s]", " ", value)
    words = value.split()
    if field in {"shipper", "consignee", "notify_party"}:
        aliases = {"ltd": "limited", "inc": "incorporated", "corp": "corporation", "co": "company", "pte": "private", "sdn": "sendirian", "bhd": "berhad"}
        words = [aliases.get(word, word) for word in words]
    if field in {"port_of_loading", "port_of_discharge"} and words[:2] == ["port", "of"]:
        words = words[2:]
    return " ".join(words)


def _resolve_notify(value: object, doc: dict) -> tuple[object, str | None]:
    if re.fullmatch(r"(?:same\s+as\s+(?:the\s+)?)consignee|as\s+(?:per\s+)?consignee", str(value or "").strip(), re.I):
        consignee, _ = _value(doc, "consignee")
        return consignee, "Resolved 'same as consignee' within the same document"
    return value, None


def _evidence_issue(evidence: dict, depth: int = 0) -> str | None:
    """Do not let a populated string erase uncertainty in its source evidence."""
    if evidence.get("ambiguous") or evidence.get("candidates") and len(evidence["candidates"]) > 1:
        return "Conflicting source candidates require human selection."
    if evidence.get("uncertain"):
        return "Source extraction is marked uncertain and requires human verification."
    method = str(evidence.get("method", "")).lower()
    if "ocr" in method or "tesseract" in method:
        confidence = evidence.get("confidence")
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0.65 <= confidence <= 1):
            return "OCR confidence is low, missing, or invalid; verify the source image before comparing."
    if method == "cloud_quote_verified" and isinstance(evidence.get("original"), dict):
        if depth >= 4:
            return "Source evidence has an unresolved provenance chain; human verification is required."
        original_issue = _evidence_issue(evidence["original"], depth + 1)
        if original_issue:
            return "Cloud quotation does not resolve uncertainty in the underlying extraction. " + original_issue
    return None


def compare(si: dict, bl: dict) -> list[dict]:
    rows = []
    for field in FIELDS:
        left, left_evidence = _value(si, field)
        right, right_evidence = _value(bl, field)
        row = {"field": field, "si": left, "bl": right, "si_normalized": None, "bl_normalized": None,
               "outcome": "uncertain", "reason": "", "si_evidence": left_evidence, "bl_evidence": right_evidence}
        notes = []
        supporting_evidence = [("SI", left_evidence), ("BL", right_evidence)]
        if field == "notify_party":
            left, note = _resolve_notify(left, si)
            if note:
                notes.append("SI: " + note)
                _, reference = _value(si, "consignee")
                row["si_reference_evidence"] = reference
                supporting_evidence.append(("SI consignee reference", reference))
            right, note = _resolve_notify(right, bl)
            if note:
                notes.append("BL: " + note)
                _, reference = _value(bl, "consignee")
                row["bl_reference_evidence"] = reference
                supporting_evidence.append(("BL consignee reference", reference))
        issues = [side + ": " + issue for side, evidence in supporting_evidence if (issue := _evidence_issue(evidence))]
        if issues:
            row["reason"] = " ".join(issues)
            rows.append(row)
            continue
        if _is_missing(left) or _is_missing(right):
            missing = "/".join(side for side, value in (("SI", left), ("BL", right)) if _is_missing(value))
            row["reason"] = f"Required {missing} value is missing or unresolved; absence is not a discrepancy."
            rows.append(row)
            continue
        try:
            if field == "gross_weight_kg":
                a, a_unit, a_resolution = _weight(left)
                b, b_unit, b_resolution = _weight(right)
                row.update(si_normalized=_format_decimal(a) + " kg", bl_normalized=_format_decimal(b) + " kg")
                tolerance = Decimal(0)
                if a_unit != b_unit and "lb" in {a_unit, b_unit}:
                    tolerance = min(a_resolution / 2, b_resolution / 2, Decimal("0.005"))
                match = abs(a - b) <= tolerance
                reason = "Compared decimal values after explicit conversion to kilograms"
                if a != b and match:
                    reason += f"; conversion rounding difference {_format_decimal(abs(a - b))} kg is within {_format_decimal(tolerance)} kg"
                elif not match:
                    reason += f"; BL minus SI is {_format_decimal(b - a)} kg"
                notes.append(reason)
            elif field == "container_count":
                a, a_reason = _count(left)
                b, b_reason = _count(right)
                row.update(si_normalized=a, bl_normalized=b)
                if a is None or b is None:
                    row["reason"] = "; ".join(note for note in (a_reason if a is None else None, b_reason if b is None else None) if note)
                    rows.append(row)
                    continue
                match = a == b
                notes.append("Compared total container counts; equipment dimensions are excluded")
            else:
                a, b = _text(left, field), _text(right, field)
                row.update(si_normalized=a, bl_normalized=b)
                match = a == b
                notes.append("Compared after case, spacing, punctuation, and documented legal-suffix abbreviation normalization")
            row["outcome"] = "match" if match else "mismatch"
            row["reason"] = "; ".join(notes) + (". Values agree." if match else ". BL differs from the SI reference.")
        except (ValueError, InvalidOperation) as error:
            row["reason"] = str(error) + "; human verification required."
        rows.append(row)
    return rows


def _risk(status: str, reason: str | None, rows: list, classification: dict) -> tuple[int, list]:
    components = []
    if status == "MISMATCH":
        components.append({"label": "Confirmed comparison discrepancy", "points": 20})
    if status == "NEEDS_REVIEW":
        points = {"wrong_doc_type": 60, "missing_attachment": 45, "unreadable": 55, "missing_value": 40}.get(reason, 40)
        components.append({"label": "Evidence gap: " + str(reason).replace("_", " "), "points": points})
    for row in rows:
        if row["outcome"] == "mismatch":
            components.append({"label": row["field"].replace("_", " ") + " discrepancy", "points": FIELD_WEIGHTS[row["field"]]})
    if classification.get("needs_review"):
        components.append({"label": "Email intent requires confirmation", "points": 15})
    current = classification.get("current_message", "")
    if status != "OK" and re.search(r"\b(?:cut.?off|closing|deadline)\b.{0,25}\b(?:today|now|imminent|hour)\b", current, re.I):
        components.append({"label": "Explicit near-term deadline in current message", "points": 10})
    return min(100, sum(component["points"] for component in components)), components


def analyze(email: dict, documents: list[dict], use_ai: bool = False, classification: dict | None = None) -> dict:
    if classification is None:
        classification = classify(email)
    elif classification.get("category") not in CATEGORIES:
        raise ValueError("Classification must use one of the five allowed categories")
    classification = copy.deepcopy(classification)
    if classification.get("method") == "human_review":
        if not isinstance(classification.get("reviewer"), str) or not classification["reviewer"].strip():
            raise ValueError("Human classification requires a named reviewer")
        classification["needs_review"] = False
        classification["confidence_label"] = "Intent confirmed by reviewer"
    category = classification["category"]
    intent_uncertain = bool(classification.get("needs_review"))
    report = {
        "email_id": str(email.get("email_id") or email.get("id") or "unidentified"),
        "category": category, "status": "OK", "review_reason": None,
        "has_defect": False, "defect_fields": [], "observed_defect_fields": [],
        "classification": classification, "rows": [], "reasons": [], "summary": "",
        "risk_score": 0, "risk_components": [], "risk_policy": "Operational priority points (0–100), not a probability. Evidence gaps 40–60, confirmed mismatch 20, field impact 10–22, ambiguous intent 15, explicit imminent deadline 10; total capped at 100.",
        "documents": documents,
        "ai": {"requested": bool(use_ai), "used": False, "mode": "local", "message": "Local ML classification and deterministic evidence comparison used." if not use_ai else "Cloud assistance was requested but is not configured in this engine. Local analysis completed; no document was transmitted."},
    }
    if intent_uncertain:
        report["reasons"].append("Email intent is uncertain; confirm the predicted category before routing. Classification evidence: " + str(classification.get("reason") or "No decisive intent evidence was found."))
    if category != "BL_COMPARISON":
        if intent_uncertain:
            report.update(status="NEEDS_REVIEW", review_reason="uncertain_intent",
                          summary="Predicted " + category.replace("_", " ").lower() + "; confirm email intent before routing.")
        else:
            report["summary"] = "Classified as " + category.replace("_", " ").lower() + "; no document comparison required."
        report["risk_score"], report["risk_components"] = _risk(report["status"], report["review_reason"], [], classification)
        return report

    si_docs = [doc for doc in documents if doc.get("kind") == "SI" and not doc.get("error")]
    bl_docs = [doc for doc in documents if doc.get("kind") == "BL" and not doc.get("error")]
    errors = [doc for doc in documents if doc.get("error")]
    others = [doc for doc in documents if doc.get("kind") == "OTHER" and not doc.get("error")]
    unknowns = [doc for doc in documents if doc.get("kind") not in {"SI", "BL", "OTHER"} and not doc.get("error")]
    reason = None
    if errors:
        missing_errors = [doc for doc in errors if re.search(r"(?:not found|missing attachment|not supplied|unavailable attachment)", str(doc.get("error")), re.I)]
        reason = "missing_attachment" if len(missing_errors) == len(errors) else "unreadable"
        report["reasons"].extend(f"{doc.get('filename', 'Attachment')}: {doc.get('error')}" for doc in errors)
    elif len(si_docs) > 1 or len(bl_docs) > 1:
        reason = "missing_value"
        report["reasons"].append("Multiple SI or BL documents are present. Select the matching shipment/version pair before comparison; the engine never chooses one arbitrarily.")
    elif not si_docs or not bl_docs:
        if others or unknowns:
            reason = "wrong_doc_type"
            report["reasons"].append("A readable attachment could not be verified as the required SI or draft BL from its content.")
        else:
            reason = "missing_attachment"
            missing_roles = [role for role, found in (("Shipping Instruction", si_docs), ("Bill of Lading", bl_docs)) if not found]
            report["reasons"].append("Missing required attachment: " + " and ".join(missing_roles) + ".")
    if len(si_docs) == 1 and len(bl_docs) == 1:
        report["rows"] = compare(si_docs[0], bl_docs[0])
        report["compared_documents"] = {"si": si_docs[0].get("filename"), "bl": bl_docs[0].get("filename")}
        report["observed_defect_fields"] = [row["field"] for row in report["rows"] if row["outcome"] == "mismatch"]
        uncertain = [row["field"] for row in report["rows"] if row["outcome"] == "uncertain"]
        if uncertain:
            reason = reason or "missing_value"
            report["reasons"].append("Required fields could not be compared reliably: " + ", ".join(uncertain) + ".")
    if intent_uncertain:
        reason = reason or "uncertain_intent"
    if reason:
        report["status"], report["review_reason"] = "NEEDS_REVIEW", reason
        report["summary"] = "Human review required: " + reason.replace("_", " ") + "."
        if report["observed_defect_fields"]:
            report["summary"] += " Evidence also shows differences in " + ", ".join(report["observed_defect_fields"]) + "; full verification is incomplete."
    elif report["observed_defect_fields"]:
        report["status"], report["has_defect"] = "MISMATCH", True
        report["defect_fields"] = report["observed_defect_fields"][:]
        report["summary"] = f"{len(report['defect_fields'])} mismatched field(s): " + ", ".join(report["defect_fields"]) + "."
    else:
        report["summary"] = "No mismatch detected. All seven fields agree with the SI reference."
    report["risk_score"], report["risk_components"] = _risk(report["status"], reason, report["rows"], classification)
    report["reasons"].extend(warning for doc in documents for warning in doc.get("warnings", []))
    return report
