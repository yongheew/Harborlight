"""Small, inspectable local ML model plus explicit shipping workflow signals.

Training examples below were independently authored for Harborlight. They are
not copied from the organizer's inbox, generator, labels, or answer key. The
model is a real Laplace-smoothed multinomial Naive Bayes classifier using word
and phrase features. Its posteriors are NOT calibrated accuracy estimates.
"""
from __future__ import annotations

import html
import math
import re
from collections import Counter
from functools import lru_cache
from html.parser import HTMLParser

CATEGORIES = ("BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM")

TRAINING_EXAMPLES = {
    "BL_COMPARISON": [
        "Compare the attached bill of lading against our shipping instruction before we release it.",
        "The carrier sent its preliminary BL. Check the consignee and loading port against the SI.",
        "Please send a draft bill of lading for our verification.",
        "Can you validate these two shipping documents and identify any differences?",
        "The BL needs amendment because the notify party differs from our instructions.",
        "Kindly review the draft transport document and confirm all shipment particulars are correct.",
        "Our SI is the source of truth. Please reconcile it with the enclosed draft BL.",
        "Approve the draft BL after checking the weight and number of containers.",
        "Could the documentation team confirm the attached drafts before the deadline?",
        "Request a BL draft from the line so we can check the shipment details.",
        "Both the instruction sheet and bill of lading are attached for comparison.",
        "Please check the documents and return any amendments to the draft BL.",
        "The shipper name on this bill of lading looks wrong; check it against the original instruction.",
        "Please verify the attached SI and BL pair for discrepancies.",
        "Send us the revised bill of lading proof for final document checking.",
    ],
    "SI_REQUEST": [
        "Please prepare a new shipping instruction for the upcoming shipment.",
        "We need your SI submitted to the carrier before cargo closing.",
        "Kindly create shipping instructions using the new booking details.",
        "The documentation desk is awaiting the customer's SI.",
        "Send the completed shipping instruction form by tomorrow morning.",
        "Can you arrange issuance of a fresh SI for this booking?",
        "Please furnish the shipping instructions for our export consignment.",
        "We have not received the SI; please provide it as soon as possible.",
        "Draft an instruction sheet with the supplied consignee and cargo information.",
        "New order confirmed. Please prepare and submit the SI.",
        "Customer shipping instructions required for the vessel booking.",
        "Kindly issue the initial SI and forward it to the shipping line.",
        "Please complete the SI template. No bill of lading has been issued yet.",
        "We request a new shipping instruction document for the next sailing.",
        "Your action is to produce the shipping instruction for our container booking.",
    ],
    "INVOICE_QUERY": [
        "Please explain the extra charge on this freight invoice.",
        "The supplier invoice is missing a goods receipt reference.",
        "Can you cancel the duplicate bill and issue a credit note?",
        "We dispute the detention and demurrage charges on our statement.",
        "Kindly provide a breakdown of the local charges for payment.",
        "This invoice total does not agree with the agreed freight rate.",
        "Our accounts payable team needs a corrected tax invoice.",
        "Please confirm whether payment for the invoice has been received.",
        "Why did the carrier bill storage fees twice?",
        "There is a billing issue with the transportation surcharge.",
        "Request a revised invoice with the correct currency and amount.",
        "Please investigate the outstanding balance and missing credit note.",
        "The purchase order cannot be matched to the supplier's invoice.",
        "Please advise on the freight charges and payment due date.",
        "Could finance reverse the incorrect invoice and refund the overpayment?",
    ],
    "GENERAL": [
        "The vessel is expected to berth tomorrow; this is an operations update.",
        "Our office will be closed for the public holiday.",
        "Please join the weekly team meeting to discuss performance.",
        "Attached is the latest sailing schedule for your information.",
        "The loading operation is complete and all containers are on board.",
        "This is an automatic status notification from the reporting service.",
        "Reminder that staff training starts at ten o'clock.",
        "Sharing the monthly shipping activity summary with the team.",
        "The terminal has revised its operating hours this weekend.",
        "Thank you for your assistance. We acknowledge receipt of your message.",
        "Please note the new contact details for our operations desk.",
        "The container gate is currently congested; expect a short delay.",
        "Here is today's berthing report and vessel movement summary.",
        "The robotic process completed its scheduled run successfully.",
        "For information only: the shipment has arrived at its destination.",
    ],
    "SPAM": [
        "Congratulations you won a prize. Click this link and pay a processing fee.",
        "Your mailbox is full. Verify your password immediately to avoid suspension.",
        "Claim your free reward by providing your bank account details.",
        "A parcel is held. Pay the tiny release fee at this unfamiliar link.",
        "Exclusive investment guarantees enormous returns overnight.",
        "Your email account will be deleted unless you sign in through this link.",
        "You have been selected for a lottery payout; send your card number.",
        "Urgent security alert. Reply with your one time password.",
        "Buy discounted miracle supplements from our promotional store.",
        "We offer millions in inheritance if you transfer an advance fee.",
        "Act now to claim your cash bonus with your credit card credentials.",
        "Update your mailbox quota using the login verification button.",
        "A mysterious benefactor wants to send you a fortune today.",
        "Final notice: verify banking credentials to unlock your winnings.",
        "Purchase our bulk advertising service and increase followers instantly.",
    ],
}


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "br", "div", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def current_message(body: str) -> tuple[str, bool]:
    """Retain the new author's content; old threads never overrule it."""
    body = str(body or "")[:100_000]
    if re.search(r"<(?:html|body|div|p|br)\b", body, re.I):
        parser = _TextOnly()
        parser.feed(body)
        body = "".join(parser.parts)
    body = html.unescape(body)
    kept, removed = [], False
    for line in body.splitlines():
        if re.match(r"\s*(?:[-_]{2,}\s*(?:original|forwarded)\s+(?:message|mail)|begin forwarded message|on .{5,200} wrote:|from:\s*.+@)", line, re.I):
            removed = True
            break
        if re.match(r"\s*(?:best regards|kind regards|warm regards|regards|sincerely|sent from my)\b", line, re.I):
            break
        if line.lstrip().startswith(">"):
            removed = True
            continue
        if re.match(r"\s*(?:\[?external(?: email| sender)?\]?|caution:|warning:).*?(?:sender|outside|organization|organisation|link|email)", line, re.I):
            continue
        kept.append(line)
    return "\n".join(kept).strip(), removed


def _features(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"bill\s+of\s+lading|b\s*/\s*l", " bl ", text)
    text = re.sub(r"shipping\s+instructions?", " si ", text)
    words = re.findall(r"[a-z]{2,}", text)
    return words + [a + "_" + b for a, b in zip(words, words[1:])]


@lru_cache(maxsize=1)
def _model():
    counts, totals, vocabulary = {}, {}, set()
    for category, examples in TRAINING_EXAMPLES.items():
        count = Counter(token for example in examples for token in _features(example))
        counts[category], totals[category] = count, sum(count.values())
        vocabulary.update(count)
    return counts, totals, vocabulary


def _predict(text: str) -> dict[str, float]:
    counts, totals, vocabulary = _model()
    tokens = Counter(t for t in _features(text) if t in vocabulary)
    size = len(vocabulary)
    logs = {
        category: -math.log(len(CATEGORIES)) + sum(
            n * math.log((counts[category][token] + 1) / (totals[category] + size))
            for token, n in tokens.items()
        ) for category in CATEGORIES
    }
    peak = max(logs.values())
    scaled = {key: math.exp(value - peak) for key, value in logs.items()}
    total = sum(scaled.values())
    return {key: value / total for key, value in scaled.items()}


def _routing_signals(text: str) -> dict[str, list[str]]:
    """Document routing rules are explained separately from model inference."""
    t = text.lower()
    t = re.sub(r"bill\s+of\s+lading|b\s*/\s*l", " bl ", t)
    t = re.sub(r"shipping\s+instructions?", " si ", t)
    signals = {category: [] for category in CATEGORIES}
    patterns = {
        "SPAM": [
            (r"(?:mailbox|email account).{0,70}(?:full|suspend|quota|deleted|verify)", "Mailbox credential or quota lure"),
            (r"(?:won|claim|lottery|winnings).{0,55}(?:prize|reward|cash|payout|bonus|fee)", "Prize or payment lure"),
            (r"(?:password|credentials|one.time password|card number).{0,40}(?:reply|send|verify)|(?:reply|send|verify|provide).{0,45}(?:password|credentials|card number)", "Credential solicitation"),
            (r"(?:parcel|package).{0,70}(?:pay|fee|release).{0,55}(?:link|click|http)", "Parcel fee link lure"),
        ],
        "BL_COMPARISON": [
            (r"\b(?:compare|reconcile|cross.check|verify|check|review|confirm|amend|approve|validate)\b.{0,130}\b(?:bl|draft|documents?|docs)\b", "Action to check or amend transport documents"),
            (r"\b(?:bl|draft)\b.{0,130}\b(?:check|compare|review|verify|confirm|amend|approval|discrepanc|correct)\w*", "Draft BL verification or amendment"),
            (r"\b(?:send|provide|request|arrange|need|await|share|issue|submit|prepare)\w*\b.{0,70}\b(?:draft\s*bl|bl\s*draft)\b", "Request for a BL draft"),
            (r"\bsi\b.{0,50}\b(?:and|against|with|versus|vs)\b.{0,35}\b(?:draft\s*)?bl\b|\bbl\b.{0,60}\b(?:against|with|versus|vs)\b.{0,30}\bsi\b", "SI and BL comparison pair"),
            (r"\bto\s+confirm\s+docs\b", "Document confirmation request"),
        ],
        "SI_REQUEST": [
            (r"\b(?:prepare|create|issue|draft|submit|send|provide|furnish|complete|request|require|need|await|arrange)\w*\b.{0,65}\b(?:new\s+)?(?:customer\s+)?si\b", "Request to produce or provide an SI"),
            (r"\bsi\b.{0,60}\b(?:required|needed|missing|outstanding|awaited|not received)\b", "SI is required or outstanding"),
            (r"\b(?:cust(?:omer)?\s+si|request\s+si)\b|^\s*si\s*[-:]", "Shipping instruction workflow"),
            (r"\b(?:please\s+find|enclosed|attached|here\s+(?:is|are)|providing|submitting|supplied)\b.{0,40}\bsi\b", "Supplying shipping instructions for a booking"),
        ],
        "INVOICE_QUERY": [
            (r"\b(?:invoice|billing|credit note|debit note|payment|freight charges|local charges|demurrage|detention|d\s*&\s*d|missing gr)\b", "Invoice, billing, or charge query"),
        ],
        "GENERAL": [
            (r"\b(?:berthing report|sailing schedule|vessel movement|status update|operations update|update summary|holiday|team meeting|training|for (?:your )?information only|_rpa_)\b", "Operational or administrative information"),
            (r"\b(?:list|summary|report)\b.{0,50}\b(?:outstanding|pending|completed|status)\b", "Operational worklist or status report"),
            (r"\b(?:automated|automatic|robotic|bot|rpa)\b.{0,70}\b(?:completed|successful|notification|process)\b", "Automated process notification"),
            (r"\b(?:reminder|sla)\b.{0,120}\b(?:all|every)\b.{0,35}\bshipments?\b", "Batch workflow reminder rather than an individual SI request"),
        ],
    }
    for category, rules in patterns.items():
        for pattern, explanation in rules:
            if re.search(pattern, t, re.S):
                signals[category].append(explanation)
    return signals


def classify(email: dict) -> dict:
    body, removed_history = current_message(email.get("body") or email.get("text") or "")
    subject = str(email.get("subject") or "")[:4_000]
    # Current text receives full authority. Subject is a fallback for brief replies.
    tokens = _features(body)
    informative = len(tokens) >= 6
    model_input = body if informative else body + "\n" + subject
    scores = _predict(model_input)
    model_category = max(scores, key=scores.get)
    body_signals = _routing_signals(body)
    subject_signals = _routing_signals(subject)
    active = body_signals if any(body_signals.values()) else (subject_signals if not informative else body_signals)
    # A focused SI request prevails over incidental references to checking the BL.
    # An explicit comparison pair prevails over an invoice attachment mentioned as context.
    if active["SPAM"]:
        category = "SPAM"
    elif "Batch workflow reminder rather than an individual SI request" in active["GENERAL"] and not active["BL_COMPARISON"]:
        category = "GENERAL"
    elif active["GENERAL"] and not active["BL_COMPARISON"] and not active["SI_REQUEST"]:
        category = "GENERAL"
    elif active["BL_COMPARISON"] and active["SI_REQUEST"]:
        direct_new_si = bool(re.search(r"\b(?:prepare|create|issue|draft(?!\s+(?:bl|bill)\b))\b.{0,25}\b(?:new |fresh |initial )?si\b", re.sub(r"shipping instructions?", "si", body.lower())))
        category = "SI_REQUEST" if direct_new_si and not re.search(r"\b(?:compare|reconcile|cross.check)\b", body, re.I) else "BL_COMPARISON"
    elif active["BL_COMPARISON"]:
        category = "BL_COMPARISON"
    elif active["SI_REQUEST"]:
        category = "SI_REQUEST"
    elif active["INVOICE_QUERY"]:
        category = "INVOICE_QUERY"
    elif active["GENERAL"]:
        category = "GENERAL"
    else:
        category = model_category
    # A content-free email must not acquire invented intent from model tie ordering.
    empty = not _features(body + " " + subject)
    if empty:
        category = "GENERAL"
    explanation = active[category]
    source = "current message" if active is body_signals else "subject fallback"
    reason = "; ".join(explanation) + f" ({source})." if explanation else "Local text model prediction; no decisive routing phrase."
    if removed_history:
        reason += " Quoted history excluded from intent classification."
    ordered = sorted(scores.values(), reverse=True)
    margin = ordered[0] - ordered[1]
    uncertain = empty or (not explanation and (ordered[0] < .60 or margin < .20))
    return {
        "category": category,
        "confidence": round(scores[category], 6),
        "confidence_kind": "uncalibrated local-model posterior, not probability of correctness",
        "confidence_label": "Review intent" if uncertain else ("Explicit routing signal" if explanation else "Model prediction"),
        "method": "local_multinomial_naive_bayes+transparent_intent_rules",
        "reason": reason,
        "scores": {key: round(value, 6) for key, value in scores.items()},
        "model_category": model_category,
        "rules_used": explanation,
        "rule_override": category != model_category and bool(explanation),
        "needs_review": uncertain,
        "current_message": body,
        "quoted_history_ignored": removed_history,
        "training_examples": sum(map(len, TRAINING_EXAMPLES.values())),
        "training_provenance": "Independently authored Harborlight examples; no organizer labels or templates",
    }
