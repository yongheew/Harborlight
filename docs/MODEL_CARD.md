# Harborlight model and decision card

Harborlight turns an email and its shipping attachments into an inspectable decision. It classifies five email workflows, compares the seven required fields with the Shipping Instruction (SI) as reference, and separates confirmed differences from insufficient evidence. It does not approve shipments or send messages.

## What actually uses AI

| Component | Implemented approach | Meaning of its output |
|---|---|---|
| Local email classifier | Multinomial Naive Bayes with word and adjacent-word features, uniform class priors, and Laplace smoothing | A trained statistical model; always available without a key |
| Intent routing | Explicit, inspectable shipping workflow rules applied to the current message | A disclosed rule may override the model; both decisions are retained |
| Document readers | Format-specific text/table extraction; optional local Tesseract OCR | Extracted values with original evidence, page, method, warnings and source hash |
| Optional cloud assistance | Opted-in structured classification and extraction through the configured OpenAI model | Cloud use, accepted fields, call metadata and failures are recorded; missing configuration never masquerades as successful AI use |
| Comparison | Deterministic normalization and decimal arithmetic | An explainable field result, independent of generated prose |

The local training corpus contains 75 independently authored English examples, 15 per category. It is embedded in `harborlight/classifier.py` and trained reproducibly at runtime. It contains no organizer answer keys, generated labels, copied email templates, or identifiers used as answers. The categories are `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`, `GENERAL` and `SPAM`.

Current email body content takes priority over misleading subjects. Quoted threads, common signatures, HTML scripts/styles, and external-sender boilerplate are removed where recognized. Short messages can fall back to their subject. A document checklist mentioning an invoice is distinguishable from a billing query; a batch workflow reminder is distinguishable from an individual SI request. Attachment filenames do not supply classification answers or prove document type.

## Scores are not measured correctness

The displayed local routing score is the selected category's actual Naive Bayes posterior. It is **uncalibrated**: 0.99 does not mean 99% real-world accuracy. A transparent rule override can select a category with a lower model score. The report exposes `model_category`, `scores`, `rules_used`, `rule_override`, `needs_review` and training provenance so that disagreement remains visible. Cloud classification does not invent a numerical confidence score.

The queue's 0–100 risk score is an **operational priority policy**, not an accident probability or financial loss prediction:

| Contribution | Points |
|---|---:|
| Confirmed comparison discrepancy | 20 |
| Missing attachment / unreadable source / wrong document type / missing value | 45 / 55 / 60 / 40 |
| Differing field: shipper / consignee / notify party | 15 / 20 / 10 |
| Differing field: loading port / discharge port / container count / gross weight | 18 / 20 / 22 / 18 |
| Ambiguous email intent | 15 |
| Explicit imminent deadline in the current message | 10 |

Contributions are added and capped at 100; the report lists each contribution. These weights are editable policy assumptions and require stakeholder validation before operational deployment.

## Comparison policy

The seven fields are shipper, consignee, notify party, loading port, discharge port, container count and gross weight in kilograms. Each row preserves the SI value, BL value, both normalized values, evidence and the reason for its decision.

- Names use case/spacing/punctuation normalization and a small disclosed legal-suffix abbreviation map. Legal suffixes are retained, and fuzzy similarity does not silently make unequal parties equivalent.
- Ports receive conservative formatting normalization. The system does not invent port-code mappings or equate different terminals using an LLM.
- An explicit “same as consignee” notify party is resolved within its own document.
- Container expressions such as `2 x 40HC + 1 x 20GP` are summed by quantity. Equipment dimensions, container IDs, package counts and ambiguous ranges are not treated as counts.
- Gross weights use decimal arithmetic, explicit kilograms/metric tonnes/pounds conversion, and preserve decimal differences. A narrowly bounded allowance of at most 0.005 kg handles representational rounding when converting pounds. The ambiguous unit “ton” requires review.
- Blank, placeholder, conflicting, unreadable or unsupported values produce uncertainty, not a discrepancy. Multiple SI/BL versions require selection rather than an arbitrary first file.

All seven fields must be accounted for before a clean result. If some values are uncertain, provable differences remain visible in `observed_defect_fields` and evidence rows, but the final status remains `NEEDS_REVIEW`. The official export uses `has_defect: false` and an empty `defect_fields` while verification is incomplete.

An email asking for a BL draft without supplying it remains a comparison workflow with `NEEDS_REVIEW / missing_attachment`. This intentionally prioritizes the actual evidence over a benchmark convention that may label such requests `OK`.

## Human review, counterfactuals and evidence

The Review desk supports an unsaved “Preview impact” calculation. Proposed changes affect extracted values in a copy of the report; they do not alter source files, persist a decision, or invoke cloud AI. This provides a small, understandable remediation view: the operator can inspect the exact fields needed to resolve the finding and see the resulting status and risk points. It is not an automated optimization algorithm or authority to rewrite a BL.

Recording a correction requires reviewer attribution and a note through the application. Corrected fields retain their previous value/evidence and `human_review` provenance. A genuine source mismatch should be confirmed and sent through the team's normal amendment process, not overwritten merely to obtain a clean result. Missing/wrong/unreadable attachments require replacement or re-import before corrections.

SQLite transactions and version checks protect against stale concurrent reviews. Original attachment bytes and SHA-256 hashes remain available. The audit chain links actions to report hashes and checks attachment manifests. It detects accidental or partial edits; it is not externally anchored and is not tamper-proof against an administrator rewriting the entire database. Re-analysis starts from preserved source bytes and resets current extraction overrides while retaining prior review events in the audit history.

## Evaluation and known limits

See [VALIDATION.md](VALIDATION.md) for the actual test runs, environment details and any organizer scoreboard obtained for this build. Output category counts are not accuracy measurements. Unit tests use independently authored fixtures and cover misleading subjects, quoted history, units, decimal preservation, uncertainty, source-role checks, review lifecycle, concurrency and audit mutation detection. No winning result or unseen-data accuracy is guaranteed.

The small English corpus is a starting model, not a large production language model. Unknown layouts, languages, unusual legal names, locale-dependent numeric notation, aliases and highly ambiguous email intent can need review. Layout extraction and OCR are dependent on installed libraries and Tesseract; low OCR confidence must remain an evidence gap. Document-content checks do not authenticate a document or establish that matching documents are truthful. Seven matching fields do not validate every legal or operational detail in a shipment.

Cloud mode can send email/document text externally only after explicit opt-in and server configuration. Quote grounding reduces fabricated field acceptance but cannot prove semantic correctness. API limits, connectivity and model availability remain failure modes, with visible local fallback. Configure and test the cloud provider before demonstrating cloud claims.

This package is a local application with deployment scaffolding. A public cloud deployment, authenticated organizational rollout, external audit anchoring, representative held-out evaluation and stakeholder approval of risk weights remain deployment/production work. Do not describe an unrun deployment or an untested API call as completed.
