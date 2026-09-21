# Harborlight: five-minute demonstration

**Opening sentence:** “Before cargo moves, an operator needs three things: the correct request, the exact difference, and enough evidence to stand behind the decision. Harborlight puts those three things on one review desk.”

Use the running local application and click **Explore demo** before presenting. Confirm OCR availability in the runtime status. Keep cloud mode off unless you have actually configured and tested it. Use [VALIDATION.md](VALIDATION.md) for measured claims; do not quote an expected score as a result.

## 0:00–0:35 — Make the operational problem visible

Show the queue and the four summary counts. Explain that five kinds of email share one inbox, but only comparison requests enter the SI-versus-BL check.

Say: “The product is an evidence desk, not just a discrepancy list. A busy operator can see what matters first, why it matters, and what still cannot be decided.”

## 0:35–1:20 — Prove the core check with one real difference

Search **HL-001** (“Draft BL - closing today”). Show the PDF source pair, SI reference column, differing fields and page evidence. Open a source citation/download and identify the printed value.

Explain the seven-field scope. The risk score combines disclosed field weights, evidence gaps and any explicit imminent deadline; it is priority points, not a probability of shipment failure.

Say: “Every highlighted difference has two source values and a reason. The system cannot mark a shipment clean just because one source was unreadable.”

## 1:20–1:55 — Show why formatting should not create work

Open **HL-002**. Show an equivalent formatting/unit example and its normalized values. Explain that decimal arithmetic, explicit units and conservative abbreviation handling remove avoidable alerts. A real count or decimal weight difference is still preserved.

Briefly show a classified-only case (**HL-007**, **HL-008**, **HL-009** or **HL-010**). Explain the local model is trained on 75 independently authored examples plus transparent intent rules. The routing score is uncalibrated; it is not a claim of 99% accuracy.

## 1:55–2:45 — Demonstrate the hard cases, including abstention

Open **HL-004** for a wrong attachment type and **HL-005** for a missing BL. Show that both require human attention and explain the exact reason.

Open **HL-006** only after checking the environment. If OCR is installed, show its extracted source evidence and method. If OCR is unavailable, show the visible failure and retry route honestly. **HL-011** demonstrates a broken source; **HL-012** exercises an XLSX SI and Word BL.

Say: “Abstention is a useful result. Missing information is not proof of a mismatch, and it is never proof that everything matches.”

## 2:45–3:45 — The distinctive moment: preview the smallest useful change

Return to **HL-001** and open **Review desk**. Choose **Correct extracted values**, change only a highlighted BL field to the SI reference, and click **Preview impact**.

Describe this explicitly as a **hypothetical** correction. Show the unsaved before/after result and risk movement. If multiple fields differ, correcting one should leave the remaining discrepancy visible. Do not save a value that contradicts the actual source.

Say: “This is a reversible what-if. An operator can see whether a proposed amendment actually resolves the case before anything is recorded. The original files remain intact.”

Switch back to **Confirm the current findings**, enter a reviewer name and a source-based note, and record the review. For a genuine transcription error, demonstrate a correction only when the source evidence actually supports it.

## 3:45–4:25 — Establish accountability

Open **Audit trail** and show the recorded human decision. Mention the version check that prevents one reviewer silently overwriting another. Show source hashes and the audit-integrity indicator.

Say: “The local hash chain detects changes to reports, events and source files. It is not an externally anchored or tamper-proof ledger. A retry starts again from the preserved sources and retains the earlier review history.”

Show **Official JSON**, **Full evidence report** and **Discrepancy CSV**. The official export fits the evaluator; the richer report serves operations.

## 4:25–5:00 — Close with evidence and a credible next step

Quote only the measured validation results in `docs/VALIDATION.md`. State the environment and whether OCR/cloud calls actually ran.

Say: “The code covers classification, mixed-format extraction, scanned-document handling, seven-field comparison, visible failures, human correction, retries and evaluator export. The differentiator is the complete decision loop: evidence, priority, preview, review and traceability. The next step is a representative held-out pilot and a tested cloud deployment with the organization's access controls.”

If cloud hosting has not been performed, say: **“Deployment configuration is included; a live cloud deployment has not yet been verified.”** If cloud AI was not invoked, say: **“This demonstration uses the local trained classifier and deterministic verification.”**

## Short answers for likely questions

- **Where is the AI?** A real local Naive Bayes email classifier is trained from the included independent corpus. Transparent rules handle explicit workflow intent. Optional configured cloud classification/extraction is separate and disclosed.
- **Why not let an LLM decide every mismatch?** The final comparison uses inspectable normalization and decimal arithmetic. Cloud suggestions still require evidence and cannot silently resolve conflicting source values.
- **How do you avoid false confidence?** Missing values stay uncertain, all seven fields are required for clean comparison, and routing/risk scores have explicit meanings and limits.
- **Can a reviewer erase a real discrepancy?** A human can correct an extraction with attribution; source files remain unchanged and previous values/events remain traceable. The tool is not a shipment approval system.
- **What is actually distinctive?** A source-linked review desk with explained priority, unsaved counterfactual impact, versioned human decisions and verifiable local audit history, delivered as a runnable system.
- **Will this win?** No result is guaranteed. Demonstrate the working behavior and measured evidence, then explain the limits clearly.
